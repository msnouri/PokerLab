import unittest
from dataclasses import asdict
import random
import numpy as np
import eval7
from treys import Card as TC,Evaluator
from pokerkit import NoLimitTexasHoldem,Automation
from pokerlab.strategies import all_strategies,baseline_strategies,registry_rows
from pokerlab.engine import play_hand
from pokerlab.agent import Observation,Agent,equity,preflop_table,CARD_TEXT,ECARDS,hand_key
from pokerlab.experiment import icm,tournament


class CoreTests(unittest.TestCase):
    def test_registry(self):
        s=all_strategies()
        self.assertEqual(len(s),80)
        self.assertEqual(len({a.id for a in s}),80)
        self.assertEqual(len({a.family for a in s}),16)
        self.assertTrue(all(sum(a.family==b.family for b in s)==5 for a in s))
        # No two candidates differ solely in identifier or attribution.
        params=[{k:v for k,v in asdict(a).items() if k not in ['id','label','source']} for a in s]
        self.assertEqual(len({repr(x) for x in params}),80)

    def test_asset(self):
        t=preflop_table()
        self.assertEqual(len(t),169)
        self.assertEqual(sum(v['combos'] for v in t.values()),1326)
        self.assertGreater(t['AA']['equity'][0],.8)
        self.assertLess(t['72o']['equity'][0],.4)
        for row in t.values():
            self.assertTrue(all(0<=p<=1 for p in row['equity']))
            self.assertTrue(all(a>=b for a,b in zip(row['equity'],row['equity'][1:])))

    def test_deterministic_and_conserving(self):
        lineup=[all_strategies()[77]]+baseline_strategies()
        a=play_hand(lineup,[2000]*8,20,111,trace=True)
        b=play_hand(lineup,[2000]*8,20,111,trace=True)
        self.assertEqual(a['net'],b['net'])
        self.assertEqual(a['actions'],b['actions'])
        self.assertEqual(sum(a['net']),0)
        # Observation does not expose a deck, opponent hands, or future board.
        self.assertEqual(a['observations'][0]['board'],())
        for o in a['observations']:
            self.assertEqual(len(o['hole']),2)
            self.assertNotIn('holes',o);self.assertNotIn('deck',o)

    def test_equity_known_nuts_and_board_tie(self):
        self.assertGreater(equity(('As','Ks'),('Qs','Js','Ts'),7),.95)
        self.assertAlmostEqual(equity(('2c','3d'),('As','Ks','Qs','Js','Ts'),1),.5)

    def test_evaluators_agree(self):
        # Independent evaluator cross-check of 400 random showdown comparisons.
        e=Evaluator();rng=random.Random(43)
        for _ in range(400):
            c=rng.sample(CARD_TEXT,9);board=c[:5];a=c[5:7];b=c[7:]
            x=eval7.evaluate([ECARDS[s] for s in board+a])
            y=eval7.evaluate([ECARDS[s] for s in board+b])
            u=e.evaluate([TC.new(s) for s in board],[TC.new(s) for s in a])
            v=e.evaluate([TC.new(s) for s in board],[TC.new(s) for s in b])
            self.assertEqual((x>y)-(x<y),(u<v)-(u>v))

    def test_sidepot_tie_known_hand(self):
        automations=tuple(a for a in Automation if a not in [Automation.HOLE_DEALING,Automation.BOARD_DEALING,Automation.CARD_BURNING])
        s=NoLimitTexasHoldem.create_state(automations,True,0,(10,20),20,[100,200,300],3)
        for i,h in enumerate(['AsAh','KsKh','QsQh']):s.deal_hole(h,i)
        s.complete_bet_or_raise_to(300) # seat 2
        s.check_or_call();s.check_or_call()
        s.burn_card('2c');s.deal_board('3c4d7h')
        s.burn_card('5c');s.deal_board('8s')
        s.burn_card('6c');s.deal_board('Jd')
        self.assertFalse(s.status)
        self.assertEqual(s.stacks,[300,200,100])
        # Royal-flush board: every surviving hand ties, split is exact.
        s=NoLimitTexasHoldem.create_state(automations,True,0,(10,20),20,[100]*3,3)
        for i,h in enumerate(['2c3c','4c5c','6c7c']):s.deal_hole(h,i)
        s.complete_bet_or_raise_to(100);s.check_or_call();s.check_or_call()
        s.burn_card('2d');s.deal_board('AsKsQs')
        s.burn_card('3d');s.deal_board('Js')
        s.burn_card('4d');s.deal_board('Ts')
        self.assertEqual(s.stacks,[100]*3)

    def test_icm_and_tournament(self):
        self.assertTrue(np.allclose(icm((2000,)*8,(50.,30.,20.,0.,0.,0.,0.,0.)),12.5))
        self.assertEqual(icm((100,),(50.,)),(50.,))
        r=tournament(all_strategies()[77],1737,cap=40)
        self.assertLessEqual(r['hands'],40)
        self.assertGreaterEqual(r['points'],0)
        self.assertLessEqual(r['points'],50)

    def test_varied_stacks_all_profiles(self):
        # Every strategy exercises short/all-in stacks and legal raise handling.
        strategies=all_strategies()
        for k in range(80):
            lineup=[strategies[(k+j*7)%80] for j in range(8)]
            r=play_hand(lineup,[15,40,65,120,200,400,800,1600],20,9000+k)
            self.assertEqual(sum(r['net']),0)


if __name__=='__main__':unittest.main()
