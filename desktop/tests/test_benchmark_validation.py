"""Regression gates for wrong reads, abstention, and cached-frame corruption."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from desktop.v2.benchmark import evaluate,validation_checks
from desktop.v2.demo import sample_frames
from desktop.v2.state import Snapshot,Field


class BenchmarkValidationTests(unittest.TestCase):
    def report(self,**changes):
        return {'frames':24,'fields_total':1272,'fields_read':1270,'fields_wrong':0,
                'repeat_fields_wrong':0,'critical_correct_frames':22,**changes}

    def test_no_readings_cannot_pass_even_without_thresholds(self):
        self.assertFalse(validation_checks(self.report(fields_read=0))['passed'])

    def test_high_field_coverage_does_not_hide_missing_critical_frames(self):
        result=validation_checks(self.report(fields_read=1248,critical_correct_frames=0),.98,.85)
        self.assertFalse(result['passed'])
        self.assertTrue(any('Critical-frame' in s for s in result['errors']))

    def test_any_wrong_read_fails_including_repeated_frames(self):
        for key in ('fields_wrong','repeat_fields_wrong'):
            with self.subTest(key=key):
                self.assertFalse(validation_checks(self.report(**{key:1}),.98,.85)['passed'])

    def test_small_explicit_abstention_can_meet_stated_thresholds(self):
        self.assertTrue(validation_checks(self.report(),.98,.85)['passed'])

    def test_invalid_thresholds_are_rejected(self):
        for value in (-.1,1.1,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                validation_checks(self.report(),value,.85)

    def test_evaluation_checks_repeated_values_against_labels(self):
        image,layout,truth=sample_frames(1)[0]
        class CorruptSecondRead:
            def __init__(self,*args):
                self.calls=0;self.engine=SimpleNamespace(name='controlled fixture')
            def read(self,image,frame_id,captured_at,*args):
                self.calls+=1;values=dict(truth)
                if self.calls==2:values['pot']+=1
                snap=Snapshot(frame_id,captured_at,'test',
                    {k:Field(k,v,'read',1.) for k,v in values.items()},read_ms=1.)
                return snap,{}
            def close(self):pass
        with patch('desktop.v2.benchmark.IncrementalReader',CorruptSecondRead):
            report=evaluate([(image,truth)],layout,Path('.'))
        self.assertEqual(report['fields_wrong'],0)
        self.assertEqual(report['repeat_fields_wrong'],1)
        self.assertFalse(validation_checks(report,.98,.85)['passed'])


if __name__=='__main__':unittest.main()
