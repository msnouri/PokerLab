"""Local session files. Recorded OCR is not ground truth for benchmarks."""
from pathlib import Path
import json,time
from dataclasses import asdict
from PIL import Image


class Recorder:
    def __init__(self,folder,layout,max_bytes=500_000_000):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/'frames').mkdir(exist_ok=True)
        self.layout=layout;self.max_bytes=max_bytes;self.bytes=0;self.count=0
        self.path=self.folder/'session.json'
        self.rows=[]

    def add(self,image,snapshot):
        rel=f'frames/{self.count:06d}.png';target=self.folder/rel
        image.save(target);size=target.stat().st_size
        if self.bytes+size>self.max_bytes:
            target.unlink();raise RuntimeError('Recording reached its 500 MB limit')
        self.bytes+=size;self.count+=1
        self.rows.append({'image':rel,'captured_at':snapshot.captured_at,'observed':snapshot.to_dict(),
                          'ground_truth':None})
        self.flush()

    def flush(self):
        data={'version':2,'layout':asdict(self.layout),'labelled':False,'frames':self.rows,
              'note':'Observed fields are reader output. Add independently checked ground_truth for evaluation.'}
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(self.path)


def load_session(path):
    path=Path(path);data=json.loads(path.read_text())
    if data.get('version')!=2 or not isinstance(data.get('frames'),list) or not 1<=len(data['frames'])<=10000:
        raise ValueError('Unsupported or oversized replay session')
    for row in data['frames']:
        if not isinstance(row,dict) or not isinstance(row.get('image'),str):raise ValueError('Replay frame needs an image path')
        target=(path.parent/row['image']).resolve()
        if not target.is_relative_to(path.parent.resolve()):raise ValueError('Replay image points outside its session folder')
        if not target.is_file():raise ValueError('Replay frame is missing')
    return data
