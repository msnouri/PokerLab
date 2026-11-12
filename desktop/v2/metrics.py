"""Latency statistics distinguish UI dispatch, reading, and frame freshness."""
from collections import deque
import math


def percentile(values,p):
    if not values:return None
    a=sorted(values);i=(len(a)-1)*p;lo=int(i);hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(i-lo)


class Metrics:
    def __init__(self):
        self.processing=deque(maxlen=1000);self.age=deque(maxlen=1000);self.dispatch=deque(maxlen=1000)
        self.frames=0;self.stale=0;self.timeouts=0;self.accepted=0;self.incomplete=0
        self.ocr_calls=0;self.cache_hits=0;self.started=None

    def summary(self):
        def p(a,n):
            v=percentile(a,n)
            return round(v,2) if v is not None else None
        return {'frames':self.frames,'stale_results_discarded':self.stale,'timeouts':self.timeouts,
                'complete_snapshots':self.accepted,'incomplete_snapshots':self.incomplete,
                'read_p50_ms':p(self.processing,.5),'read_p95_ms':p(self.processing,.95),
                'read_p99_ms':p(self.processing,.99),'source_age_p95_ms':p(self.age,.95),
                'ui_dispatch_p95_ms':p(self.dispatch,.95),'ui_dispatch_p99_ms':p(self.dispatch,.99),
                'ocr_calls':self.ocr_calls,'cache_hits':self.cache_hits,
                'note':'UI dispatch measures queued heartbeat delivery, not physical click latency or screen refresh FPS.'}
