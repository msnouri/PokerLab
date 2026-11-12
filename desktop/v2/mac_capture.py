"""Selected-window ScreenCaptureKit adapter. No display-coordinate scraping."""
import sys,threading,time
import numpy as np
from PIL import Image


def require_mac():
    if sys.platform!='darwin':raise RuntimeError('Live window capture is available on macOS only. Use replay or practice here.')


def permission(grant=False):
    require_mac()
    import Quartz
    return bool(Quartz.CGRequestScreenCaptureAccess() if grant else Quartz.CGPreflightScreenCaptureAccess())


def shareable():
    require_mac()
    import ScreenCaptureKit as SC
    done=threading.Event();result={}
    def complete(content,error):
        result.update(content=content,error=error);done.set()
    SC.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True,True,complete)
    if not done.wait(6):raise TimeoutError('Window discovery timed out; check Screen Recording permission')
    if result.get('error'):raise RuntimeError(str(result['error']))
    return result['content']


def list_windows():
    content=shareable();rows=[]
    for w in content.windows():
        if w.frame().size.width<150 or w.frame().size.height<120:continue
        app=w.owningApplication()
        rows.append({'id':int(w.windowID()),'title':str(w.title() or 'Untitled window'),
                     'app':str(app.applicationName() if app else 'App'),
                     'width':float(w.frame().size.width),'height':float(w.frame().size.height)})
    return rows


def pixel_buffer_image(pixel):
    import Quartz as CoreVideo
    flags=CoreVideo.kCVPixelBufferLock_ReadOnly
    status=CoreVideo.CVPixelBufferLockBaseAddress(pixel,flags)
    if status:raise RuntimeError('Cannot lock captured image')
    try:
        w=int(CoreVideo.CVPixelBufferGetWidth(pixel));h=int(CoreVideo.CVPixelBufferGetHeight(pixel))
        stride=int(CoreVideo.CVPixelBufferGetBytesPerRow(pixel));base=CoreVideo.CVPixelBufferGetBaseAddress(pixel)
        if hasattr(base,'as_buffer'):raw=base.as_buffer(h*stride)
        elif hasattr(base,'__buffer__') or isinstance(base,(bytes,bytearray,memoryview)):raw=memoryview(base)
        else:raw=base[:h*stride]
        pixels=np.frombuffer(raw,dtype=np.uint8,count=h*stride).reshape(h,stride)[:,:w*4].reshape(h,w,4)
        return Image.fromarray(pixels[:,:,[2,1,0]].copy(),'RGB')
    finally:CoreVideo.CVPixelBufferUnlockBaseAddress(pixel,flags)


def sink_class():
    import objc,Foundation,ScreenCaptureKit as SC,CoreMedia
    class PokerStudioStreamSink(Foundation.NSObject,protocols=[objc.protocolNamed('SCStreamOutput'),objc.protocolNamed('SCStreamDelegate')]):
        def stream_didOutputSampleBuffer_ofType_(self,stream,sample,kind):
            if kind!=SC.SCStreamOutputTypeScreen:return
            with objc.autorelease_pool():
                try:
                    if not CoreMedia.CMSampleBufferIsValid(sample):return
                    # Idle/blank/incomplete surfaces must not become readings.
                    attachments=CoreMedia.CMSampleBufferGetSampleAttachmentsArray(sample,False)
                    if attachments:
                        status=attachments[0].get(SC.SCStreamFrameInfoStatus)
                        if status is not None and int(status)!=int(SC.SCFrameStatusComplete):return
                    pixel=CoreMedia.CMSampleBufferGetImageBuffer(sample)
                    if pixel is None:return
                    stamp=time.monotonic()
                    self.callback(pixel_buffer_image(pixel),stamp)
                except Exception as exc:self.error_callback(str(exc))
        def stream_didStopWithError_(self,stream,error):
            self.error_callback(str(error))
    return PokerStudioStreamSink


_SINK=None


class MacWindowCapture:
    def __init__(self,window_id,on_frame,on_error,fps=20):
        require_mac()
        if not permission():raise PermissionError('Allow Screen Recording for this app in System Settings → Privacy & Security, then relaunch.')
        import ScreenCaptureKit as SC,CoreMedia,dispatch
        import Quartz as CoreVideo
        window=next((w for w in shareable().windows() if int(w.windowID())==window_id),None)
        if window is None:raise RuntimeError('The selected window is no longer available')
        self.window_id=window_id;self.callback=on_frame;self.on_error=on_error;self.running=False
        self.ratio=float(window.frame().size.width)/float(window.frame().size.height)
        self.SC=SC;self.CoreMedia=CoreMedia;self.fps=fps
        self.config=SC.SCStreamConfiguration.alloc().init()
        self._size(float(window.frame().size.width),float(window.frame().size.height))
        self.config.setPixelFormat_(CoreVideo.kCVPixelFormatType_32BGRA)
        self.config.setShowsCursor_(False);self.config.setCapturesAudio_(False)
        self.config.setQueueDepth_(3)
        self.config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1,fps))
        filter_=SC.SCContentFilter.alloc().initWithDesktopIndependentWindow_(window)
        global _SINK
        if _SINK is None:_SINK=sink_class()
        self.sink=_SINK.alloc().init();self.sink.callback=on_frame;self.sink.error_callback=on_error
        self.stream=SC.SCStream.alloc().initWithFilter_configuration_delegate_(filter_,self.config,self.sink)
        self.queue=dispatch.dispatch_queue_create(b'org.pokerlab.capture',None)
        ok,error=self.stream.addStreamOutput_type_sampleHandlerQueue_error_(self.sink,SC.SCStreamOutputTypeScreen,self.queue,None)
        if not ok:raise RuntimeError(str(error))
        self.stream.startCaptureWithCompletionHandler_(self._started)

    def _started(self,error):
        if error:self.on_error(str(error))
        else:self.running=True

    def _size(self,w,h):
        # Explicit 2x logical dimensions support Retina; cap memory/IPC traffic.
        scale=min(2.,1920/max(w,1),1300/max(h,1))
        self.config.setWidth_(max(2,int(w*scale)//2*2))
        self.config.setHeight_(max(2,int(h*scale)//2*2))
        self.logical_size=(w,h)

    def refresh_geometry(self):
        import Quartz
        rows=Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,Quartz.kCGNullWindowID)
        row=next((r for r in rows if int(r.get('kCGWindowNumber',-1))==self.window_id),None)
        if row is None:raise RuntimeError('Selected window closed')
        bounds=row['kCGWindowBounds'];size=(float(bounds['Width']),float(bounds['Height']))
        if size!=self.logical_size:
            self._size(*size)
            self.stream.updateConfiguration_completionHandler_(self.config,lambda error:self.on_error(str(error)) if error else None)
            return True
        return False

    def stop(self):
        self.running=False
        if self.stream:self.stream.stopCaptureWithCompletionHandler_(lambda error:None)
        self.stream=None
