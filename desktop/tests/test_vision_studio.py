import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
from dataclasses import asdict
from pathlib import Path
import json,sys,tempfile,time,unittest
from PIL import Image,ImageDraw
from desktop.v2.state import Field,Snapshot,Tracker,validate_snapshot,field_specs
from desktop.v2.layout import Layout,Registration,propose_cards
from desktop.v2.reader import IncrementalReader,readiness,critical_keys
from desktop.v2.ocr import TextRead,decode_text,make_engine,map_text_boxes,AppleVision
from desktop.v2.replay import Recorder,load_session
from desktop.v2.demo import sample_frames,write_examples
from desktop.v2.metrics import percentile
from desktop.v2.runtime import VisionProcess


class CountingOCR:
    name='test double'
    def __init__(self):self.calls=0
    def recognize(self,*args,**kwargs):self.calls+=1;return TextRead('100',.99)


def snapshot(values,frame=1):
    return Snapshot(frame,time.monotonic(),'test',{k:Field(k,v,'read',.99) for k,v in values.items()})


class SchemaTests(unittest.TestCase):
    def test_unknown_is_distinct_from_zero(self):
        s=Snapshot(1,0,'test',{'pot':Field('pot')})
        self.assertIsNone(s.value('pot'))
        s.fields['pot']=Field('pot',0,'read',.99)
        self.assertEqual(s.value('pot'),0)

    def test_unknown_board_is_not_preflop(self):
        self.assertEqual(snapshot({'pot':10}).to_dict()['summary']['street'],'unknown')
        s=snapshot({f'board_{i}':None for i in range(1,6)})
        self.assertEqual(s.to_dict()['summary']['street'],'preflop')

    def test_partial_board_does_not_invent_street(self):
        t=Tracker();t.accept(snapshot({'board_1':None}))
        t.accept(snapshot({'board_1':'As','board_2':'Kh','board_3':'Qd'},2))
        self.assertFalse(any(e['kind']=='street' for e in t.events))

    def test_duplicate_cards_and_invalid_board(self):
        s=snapshot({'hole_1':'As','hole_2':'As',**{f'board_{i}':None for i in range(1,6)}})
        self.assertIn('Duplicate visible cards',validate_snapshot(s))
        s=snapshot({'board_1':'As','board_2':None,'board_3':'Kh','board_4':None,'board_5':None})
        self.assertIn('Invalid board sequence',validate_snapshot(s))

    def test_conflicting_chips_and_dealers(self):
        s=snapshot({'seat_0_dealer':True,'seat_1_dealer':True,'seat_0_stack':20,'to_call':30})
        issues=validate_snapshot(s)
        self.assertIn('Multiple dealer markers',issues);self.assertIn('Call cost exceeds remaining stack',issues)

    def test_history_never_invents_raise_order(self):
        t=Tracker()
        t.accept(snapshot({'seat_0_bet':0,'seat_1_bet':0}))
        s=snapshot({'seat_0_bet':100,'seat_1_bet':200},2);t.accept(s)
        self.assertFalse(s.history_complete)
        self.assertTrue(any(e['kind']=='gap' for e in t.events))
        self.assertFalse(any('raises' in e['message'] for e in t.events))

    def test_out_of_order_is_rejected(self):
        t=Tracker();t.accept(snapshot({'pot':10},2))
        self.assertFalse(t.accept(snapshot({'pot':5},1)))
        self.assertEqual(t.previous.value('pot'),10)

    def test_stability_resets_after_conflict(self):
        t=Tracker();a=snapshot({'pot':20});t.accept(a)
        b=snapshot({'pot':20},2);t.accept(b);self.assertTrue(b.stable)
        c=snapshot({'hole_1':'As','hole_2':'As'},3);t.accept(c);self.assertFalse(c.stable)

    def test_timer_does_not_block_critical_stability(self):
        t=Tracker();t.accept(snapshot({'pot':20,'timer':20}))
        s=snapshot({'pot':20,'timer':19},2);t.accept(s)
        self.assertTrue(s.stable)
        # Completeness is still required separately; stability never fills gaps.
        self.assertEqual(readiness(s,Layout())[0],'Needs review')

    def test_fields_scale_to_nine_seats(self):
        self.assertTrue(any(s['key']=='seat_8_stack' for s in field_specs(9)))
        self.assertEqual(len(field_specs(6)),53)

    def test_decoders_do_not_guess(self):
        self.assertEqual(decode_text('ALL-IN','status',1),'all-in')
        self.assertEqual(decode_text('OFF','turn',1),False)
        self.assertEqual(decode_text('$1.25','money',100),125)
        with self.assertRaises(ValueError):decode_text('O.25','money',100)
        with self.assertRaises(ValueError):decode_text('maybe','turn',1)


class IncrementalTests(unittest.TestCase):
    def test_exact_pixel_cache_and_invalidation(self):
        engine=CountingOCR();layout=Layout(regions={'pot':[0,0,1,1]},confirmed=['pot'])
        reader=IncrementalReader(layout,Path('.'),engine=engine)
        im=Image.new('RGB',(100,40),'white')
        a,_=reader.read(im,1,time.monotonic());b,_=reader.read(im,2,time.monotonic())
        self.assertEqual(engine.calls,1);self.assertEqual(b.cache_hits,1)
        # A one-pixel change also invalidates money OCR: decimals must not vanish.
        im.putpixel((50,25),(0,0,0));c,_=reader.read(im,3,time.monotonic())
        self.assertEqual(engine.calls,2);self.assertEqual(c.cache_hits,0)

    def test_unconfirmed_proposals_are_not_read(self):
        e=CountingOCR();p=Layout(regions={'pot':[0,0,1,1]})
        s,_=IncrementalReader(p,Path('.'),engine=e).read(Image.new('RGB',(100,40),'white'),1,time.monotonic())
        self.assertEqual(e.calls,0);self.assertFalse(s.fields['pot'].known)

    def test_failed_ocr_attempts_are_counted(self):
        class Uncertain(CountingOCR):
            def recognize(self,*args,**kwargs):return TextRead('?',.1)
        p=Layout(regions={'pot':[0,0,1,1]},confirmed=['pot'])
        reader=IncrementalReader(p,Path('.'),engine=Uncertain());im=Image.new('RGB',(100,40),'white')
        s,_=reader.read(im,1,time.monotonic())
        self.assertEqual(s.ocr_calls,2);self.assertFalse(s.fields['pot'].known)
        repeated,_=reader.read(im,2,time.monotonic())
        self.assertEqual(repeated.ocr_calls,0);self.assertFalse(repeated.fields['pot'].known)

    def test_native_batch_reads_changed_fields_once(self):
        class BatchOCR:
            name='batch test double'
            def recognize_fields(self,image,regions,accurate=False):
                return {k:TextRead('100' if k=='pot' else '20',.99) for k in regions}
        p=Layout(regions={'pot':[0,0,.5,1],'to_call':[.5,0,.5,1]},confirmed=['pot','to_call'])
        reader=IncrementalReader(p,Path('.'),engine=BatchOCR());im=Image.new('RGB',(200,50),'white')
        a,_=reader.read(im,1,time.monotonic());b,_=reader.read(im,2,time.monotonic())
        self.assertEqual(a.ocr_calls,1);self.assertEqual(a.value('pot'),100);self.assertEqual(a.value('to_call'),20)
        self.assertEqual(b.ocr_calls,0);self.assertEqual(b.cache_hits,2)

    def test_crossing_ocr_line_is_withheld(self):
        regions={'pot':[0,0,.45,1],'to_call':[.55,0,.45,1]}
        reads=map_text_boxes([(.1,.2,.8,.2,'100 20',.99)],regions)
        self.assertFalse(reads['pot'].text);self.assertFalse(reads['to_call'].text)
        reads=map_text_boxes([(.1,.2,.2,.2,'100',.99)],regions)
        self.assertEqual(reads['pot'].text,'100')

    def test_learned_absence_and_color_only_indicators(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);off=Image.new('RGB',(80,30),(30,30,30));on=Image.new('RGB',(80,30),(190,190,190))
            off.save(folder/'off.png');on.save(folder/'on.png')
            layout=Layout(regions={'turn':[0,0,1,1]},confirmed=['turn'],templates={'turn':{'false':'off.png','true':'on.png'}})
            engine=CountingOCR();reader=IncrementalReader(layout,folder,engine=engine)
            a,_=reader.read(off,1,time.monotonic());b,_=reader.read(on,2,time.monotonic())
            self.assertIs(a.value('turn'),False);self.assertIs(b.value('turn'),True)
            c,_=reader.read(Image.new('RGB',(80,30),(31,31,31)),3,time.monotonic())
            self.assertIs(c.value('turn'),False)
            self.assertEqual(engine.calls,0)

    def test_indicator_ocr_keeps_table_context(self):
        engine=AppleVision.__new__(AppleVision);seen=[]
        def boxes(image,accurate):
            seen.append(image.size);return [(.1,.2,.2,.2,'ON',.99)]
        engine._boxes=boxes
        reads=engine.recognize_fields(Image.new('RGB',(200,100)),{'button_fold':[0,0,.5,1]})
        self.assertEqual(reads['button_fold'].text,'ON');self.assertEqual(seen,[(200,100)])

    def test_calibrated_fixture_indicators_change_correctly(self):
        with tempfile.TemporaryDirectory() as d:
            rows=sample_frames(9,example_folder=Path(d));reader=IncrementalReader(rows[0][1],Path(d),engine=CountingOCR())
            for i,(image,layout,truth) in enumerate(rows):
                snap,_=reader.read(image,i,time.monotonic())
                for key in layout.templates:
                    if key not in ('turn',) and not key.startswith('button_') and not key.endswith(('_status','_dealer')):continue
                    self.assertEqual(snap.value(key),truth[key],key)

    def test_numeric_examples_do_not_force_unknown_amounts_to_zero(self):
        from desktop.v2.demo import font
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);banks=write_examples(folder)
            p=Layout(regions={'to_call':[0,0,1,1]},confirmed=['to_call'],templates={'to_call':{'n_0':banks['to_call']['n_0']}})
            class AmountOCR(CountingOCR):
                def recognize(self,*args,**kwargs):self.calls+=1;return TextRead('25',.99)
            engine=AmountOCR();reader=IncrementalReader(p,folder,engine=engine)
            zero=Image.open(folder/banks['to_call']['n_0']).convert('RGB')
            a,_=reader.read(zero,1,time.monotonic());self.assertEqual(a.value('to_call'),0);self.assertEqual(engine.calls,0)
            positive=Image.new('RGB',(95,30),'#101e26');draw=ImageDraw.Draw(positive)
            draw.rounded_rectangle((0,0,95,30),5,fill='#192e37');draw.text((47.5,15),'25',font=font(18),fill='#f0f1e6',anchor='mm')
            b,_=reader.read(positive,2,time.monotonic());self.assertEqual(b.value('to_call'),25);self.assertEqual(engine.calls,1)

    def test_lost_anchor_withholds_entire_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);im=Image.new('RGB',(100,100),'black');draw=ImageDraw.Draw(im);draw.rectangle((20,20,39,39),fill='white');draw.line((20,20,39,39),fill='red',width=3)
            im.crop((20,20,40,40)).save(root/'anchor.png')
            p=Layout(anchor='anchor.png',anchor_rect=[.2,.2,.2,.2],reference_size=[100,100])
            with self.assertRaises(ValueError):Registration(p,root).align(Image.new('RGB',(100,100),'#334444'))

    def test_relative_assets_cannot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Layout(templates={'cards':{'As':'../outside.png'}})
            with self.assertRaises(ValueError):p.validate(Path(d))

    def test_card_proposals_on_generated_table(self):
        im,_,_=sample_frames(4)[3]
        proposals=propose_cards(im)
        self.assertIn('hole_1',proposals)
        if any(k.startswith('board') for k in proposals):self.assertIn('board_5',proposals)

    def test_recorded_ocr_is_not_ground_truth(self):
        with tempfile.TemporaryDirectory() as d:
            r=Recorder(d,Layout());r.add(Image.new('RGB',(20,20)),snapshot({'pot':100}))
            data=load_session(Path(d)/'session.json')
            self.assertIsNone(data['frames'][0]['ground_truth']);self.assertFalse(data['labelled'])
            data['frames'][0]['image']='../secret.png';(Path(d)/'session.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_session(Path(d)/'session.json')

    def test_percentiles(self):
        self.assertEqual(percentile([0,10],.95),9.5)
        self.assertIsNone(percentile([],.5))

    def test_benchmark_rejects_incomplete_ground_truth(self):
        from desktop.v2.benchmark import evaluate
        with self.assertRaises(ValueError):evaluate([(Image.new('RGB',(20,20)),{})],Layout(),Path('.'))


class RealRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.engine=make_engine('auto')
        except Exception as e:
            if sys.platform=='darwin':raise
            raise unittest.SkipTest(str(e))
        if cls.engine.name.startswith('Tesseract · subprocess'):raise unittest.SkipTest('Native optional OCR is not installed')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls.engine,'close'):cls.engine.close()

    def test_rich_fixture_no_silent_wrong_fields(self):
        im,p,truth=sample_frames(1)[0]
        s,_=IncrementalReader(p,Path('.'),engine=self.engine).read(im,1,time.monotonic(),budget=5)
        self.assertGreater(sum(f.known for f in s.fields.values()),40,
            {k:f.reason for k,f in s.fields.items() if not f.known})
        for key,f in s.fields.items():
            if f.known:self.assertEqual(f.value,truth[key],key)

    def test_process_latest_frame_contract(self):
        folder=tempfile.TemporaryDirectory();root=Path(folder.name)
        im,p,truth=sample_frames(1,example_folder=root)[0]
        v=VisionProcess(p,root,backend='auto')
        try:
            for i in range(1,8):v.submit(im,i,time.monotonic(),'test')
            end=time.monotonic()+(40 if sys.platform=='darwin' else 12);ids=[];errors=[]
            while time.monotonic()<end:
                for msg in v.poll():
                    if 'snapshot' in msg:ids.append(msg['snapshot'].frame_id)
                    if 'error' in msg:errors.append(msg['error'])
                if 7 in ids:break
                time.sleep(.02)
            self.assertIn(7,ids,str(errors));self.assertEqual(ids,sorted(ids));self.assertLess(len(ids),7)
        finally:v.stop();folder.cleanup()

    def test_process_deadline_terminates_old_worker(self):
        _,p,_=sample_frames(1)[0]
        v=VisionProcess(p,Path('.'),backend='auto');old=v.process
        try:
            v.active_at=time.monotonic()-6;v.boot_at=0
            messages=v.poll()
            self.assertFalse(old.is_alive());self.assertEqual(v.restarts,1)
            self.assertTrue(any('deadline' in m.get('error','') for m in messages))
        finally:v.stop()


class MacNativeTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='darwin','macOS native APIs')
    def test_native_bgra_stride_conversion(self):
        import Quartz
        from desktop.v2.mac_capture import pixel_buffer_image
        data=bytearray(bytes([7,19,231,255])*8*3)
        status,pixel=Quartz.CVPixelBufferCreateWithBytes(None,4,3,Quartz.kCVPixelFormatType_32BGRA,
            data,32,lambda refcon:None,None,{},None)
        self.assertEqual(status,0)
        image=pixel_buffer_image(pixel)
        self.assertEqual(image.size,(4,3));self.assertEqual(image.getpixel((3,2)),(231,19,7))

    @unittest.skipUnless(sys.platform=='darwin','macOS native APIs')
    def test_native_api_imports_and_protocols(self):
        import ScreenCaptureKit as SC,Quartz,CoreMedia,Vision,dispatch
        from desktop.v2.mac_capture import sink_class,permission
        self.assertTrue(hasattr(SC.SCShareableContent,'getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_'))
        self.assertTrue(hasattr(Quartz,'CVPixelBufferGetBaseAddress'))
        self.assertTrue(hasattr(CoreMedia,'CMSampleBufferGetImageBuffer'))
        self.assertTrue(sink_class())
        self.assertIsInstance(permission(),bool)


if __name__=='__main__':unittest.main()
