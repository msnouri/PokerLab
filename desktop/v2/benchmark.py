"""Reproducible field coverage / correctness / latency on labelled replays."""
import argparse,json,time,platform,statistics,tempfile
from pathlib import Path
from .demo import sample_frames
from .reader import IncrementalReader,critical_keys
from .layout import Layout
from .replay import load_session
from .metrics import percentile


def evaluate(frames,layout,folder,backend='auto'):
    expected_keys={s['key'] for s in layout.specs}
    if not frames or any(set(truth)!=expected_keys for _,truth in frames):
        raise ValueError('Every frame needs independent labels for every layout field, including explicit null values')
    layout.validate(Path(folder))
    reader=IncrementalReader(layout,folder,backend)
    changed=[];repeat=[];fully_correct=critical_correct=wrong=known=total=0;failures=[];hits=calls=repeat_calls=repeat_hits=0
    repeat_wrong=0;repeat_failures=[]
    for i,(image,truth) in enumerate(frames):
        snap,_=reader.read(image,2*i+1,time.monotonic(),'labelled replay')
        changed.append(snap.read_ms);hits+=snap.cache_hits;calls+=snap.ocr_calls
        mismatch={};missing=[]
        for key,expected in truth.items():
            f=snap.fields.get(key);total+=1
            if not f or not f.known:missing.append(key);continue
            known+=1
            if f.value!=expected:wrong+=1;mismatch[key]={'expected':expected,'read':f.value}
        if not mismatch and not missing:fully_correct+=1
        critical=set(critical_keys(layout))
        if not any(k in critical for k in set(mismatch)|set(missing)) and not snap.issues:critical_correct+=1
        if mismatch or missing or snap.issues:failures.append({'frame':i,'wrong':mismatch,'unknown':missing,'issues':snap.issues})
        repeated,_=reader.read(image,2*i+2,time.monotonic(),'same pixels')
        repeat.append(repeated.read_ms);repeat_calls+=repeated.ocr_calls;repeat_hits+=repeated.cache_hits
        repeated_mismatch={k:{'expected':expected,'read':repeated.fields[k].value}
            for k,expected in truth.items() if k in repeated.fields and repeated.fields[k].known and repeated.fields[k].value!=expected}
        repeat_wrong+=len(repeated_mismatch)
        if repeated_mismatch:repeat_failures.append({'frame':i,'wrong':repeated_mismatch})
    reader.close()
    return {'scope':'Generated or independently labelled image replay. Excludes native screen capture, UI paint, human review and one-time worker/model startup. Not a commercial-client or relative-to-Dickreuter benchmark.',
            'platform':platform.platform(),'backend':reader.engine.name,'frames':len(frames),
            'fully_correct_frames':fully_correct,'critical_correct_frames':critical_correct,
            'fields_total':total,'fields_read':known,'fields_wrong':wrong,
            'coverage':round(known/max(1,total),5),'accepted_field_accuracy':round((known-wrong)/max(1,known),5),
            'changed_frame_p50_ms':round(percentile(changed,.5),2),'changed_frame_p95_ms':round(percentile(changed,.95),2),
            'changed_frame_p99_ms':round(percentile(changed,.99),2),'repeat_p50_ms':round(percentile(repeat,.5),2),
            'ocr_calls':calls,'cache_hits':hits,'repeat_ocr_calls':repeat_calls,'repeat_cache_hits':repeat_hits,'failures':failures,
            'repeat_fields_wrong':repeat_wrong,'repeat_failures':repeat_failures}


def validation_checks(report,min_coverage=0.,min_critical_coverage=0.):
    """Separate abstention from correctness; both must meet CI's stated floor."""
    if not 0<=min_coverage<=1 or not 0<=min_critical_coverage<=1:
        raise ValueError('Coverage requirements must be between 0 and 1')
    errors=[]
    coverage=report['fields_read']/max(1,report['fields_total'])
    critical=report['critical_correct_frames']/max(1,report['frames'])
    if report['fields_wrong'] or report.get('repeat_fields_wrong',0):errors.append('Incorrect accepted values in changed or repeated frames')
    if not report['fields_read'] or not report['frames']:errors.append('No labelled fields were read')
    if coverage<min_coverage:errors.append(f'Field coverage {coverage:.2%} is below {min_coverage:.2%}')
    if critical<min_critical_coverage:errors.append(f'Critical-frame coverage {critical:.2%} is below {min_critical_coverage:.2%}')
    return {'passed':not errors,'min_coverage':min_coverage,'min_critical_coverage':min_critical_coverage,'errors':errors}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--session',type=Path);parser.add_argument('--frames',type=int,default=24)
    parser.add_argument('--backend',choices=['auto','vision','native','subprocess'],default='auto');parser.add_argument('--output',type=Path)
    parser.add_argument('--min-coverage',type=float,default=0.)
    parser.add_argument('--min-critical-coverage',type=float,default=0.)
    args=parser.parse_args()
    if not 1<=args.frames<=200:parser.error('Use 1–200 frames')
    if not 0<=args.min_coverage<=1 or not 0<=args.min_critical_coverage<=1:parser.error('Coverage requirements must be between 0 and 1')
    if args.session:
        data=load_session(args.session);layout=Layout(**data['layout']);folder=args.session.parent
        if any(not isinstance(row.get('ground_truth'),dict) for row in data['frames']):parser.error('Every benchmark frame needs independent ground_truth labels; recorded OCR output is insufficient')
        from PIL import Image
        frames=[(Image.open(folder/row['image']).convert('RGB'),row['ground_truth']) for row in data['frames'][:args.frames]]
        report=evaluate(frames,layout,folder,args.backend)
    else:
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);rows=sample_frames(args.frames,example_folder=folder);layout=rows[0][1]
            frames=[(im,truth) for im,_,truth in rows]
            report=evaluate(frames,layout,folder,args.backend)
        report['fixture_calibration']='Bundled card art and independent labelled ON/OFF/status and single-digit examples from write_examples(); other text/amounts use OCR. No per-hand labels enter the reader.'
    report['validation']=validation_checks(report,args.min_coverage,args.min_critical_coverage)
    text=json.dumps(report,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text)
    raise SystemExit(not report['validation']['passed'])

if __name__=='__main__':main()
