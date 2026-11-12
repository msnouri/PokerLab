import json
import unittest

from pokerlab.agent import Agent, Observation, hand_key
from pokerlab.engine import play_hand
from pokerlab.strategies import all_strategies, selectable_strategies, library_strategies
from pokerlab.library import entries, Policy, register, REGISTRY
from pokerlab.library.positions import position_name, seats_off_button
from pokerlab.library.pushfold import table, frequency, ASSET
from pokerlab.library.positional import ordering, open_frequency, RFI
from pokerlab.library.mdf import geometric_fraction, percentile


def spot(**changes):
    base = dict(hole=('As', 'Kd'), board=(), seat=0, players=6, active=2, stack=190, big_blind=20, pot=30,
                to_call=10, bet=10, min_raise_to=40, max_raise_to=200, position=0., street_raises=0,
                preflop_raiser=False, checked_before=False)
    base.update(changes)
    return Observation(**base)


class RegistryTests(unittest.TestCase):
    def test_library_extends_selection_without_touching_the_original_eighty(self):
        self.assertEqual(len(all_strategies()), 80)
        ids = [s.id for s in library_strategies()]
        self.assertEqual(ids, ['T01', 'T02', 'T03', 'T04'])
        self.assertEqual(len({s.id for s in selectable_strategies()}), len(selectable_strategies()))
        for entry in entries():
            self.assertTrue(entry.source and entry.scope and entry.label)

    def test_a_new_policy_is_one_decorated_class(self):
        @register('T99', 'Always check or fold', 'test', 'everything')
        class Passive(Policy):
            def decide(self, o, draw):
                self.details = {'policy_path': 'passive'}
                return ('call', 0) if not o.to_call else ('fold', 0)
        try:
            strategy = next(s for s in library_strategies() if s.id == 'T99')
            agent = Agent(strategy)
            self.assertEqual(agent.decide(spot(), .5), ('fold', 0))
            self.assertEqual(agent.last_details['policy_path'], 'passive')
        finally:
            del REGISTRY['Passive']


class PushFoldTests(unittest.TestCase):
    def test_equilibrium_asset_is_sane(self):
        data, index = table()
        self.assertEqual(len(data['classes']), 169)
        previous = 1.
        for depth in range(2, 21):
            row = data['depths'][str(depth)]
            self.assertLess(row['exploitability_bb'], .01)
            self.assertEqual(row['push'][index['AA']], 1.)
            self.assertEqual(row['call'][index['AA']], 1.)
            self.assertLessEqual(row['push_fraction'], previous + .02)
            previous = row['push_fraction']
        ten = data['depths']['10']
        # Published Nash charts put these near 58 % and 37 %.
        self.assertTrue(.55 < ten['push_fraction'] < .62)
        self.assertTrue(.34 < ten['call_fraction'] < .41)
        self.assertEqual(ten['push'][index['72o']], 0.)
        self.assertEqual(json.loads(ASSET.read_text())['schema_version'], 1)

    def test_scope_jam_call_and_fallback(self):
        agent = Agent(next(s for s in library_strategies() if s.id == 'T01'))
        self.assertEqual(agent.decide(spot(), .5), ('raise', 200))
        self.assertEqual(agent.last_details['policy_path'], 'nash_jam')
        self.assertEqual(agent.decide(spot(hole=('7s', '2d')), .5), ('fold', 0))
        facing = spot(seat=1, bet=20, to_call=180, stack=180, pot=220, street_raises=1,
                      min_raise_to=None, max_raise_to=None, position=.2)
        self.assertEqual(agent.decide(facing, .5), ('call', 0))
        self.assertEqual(agent.last_details['policy_path'], 'nash_call')
        self.assertEqual(agent.decide(spot(**{**facing.__dict__, 'hole': ('7s', '2d')}), .5), ('fold', 0))
        agent.decide(spot(stack=1990, max_raise_to=2000), .5)
        self.assertTrue(agent.last_details['policy_path'].startswith('fallback_'))
        agent.decide(spot(active=4), .5)
        self.assertTrue(agent.last_details['policy_path'].startswith('fallback_'))
        self.assertAlmostEqual(frequency('push', 'AA', 50), 1.)


class PositionalTests(unittest.TestCase):
    def test_seat_names(self):
        self.assertEqual([position_name(i, 6) for i in range(6)], ['SB', 'BB', 'UTG', 'HJ', 'CO', 'BTN'])
        self.assertEqual([position_name(i, 2) for i in range(2)], ['BB', 'BTN/SB'])
        self.assertEqual([position_name(i, 3) for i in range(3)], ['SB', 'BB', 'BTN'])
        self.assertEqual(position_name(2, 8), 'UTG')
        self.assertEqual([seats_off_button(i, 6) for i in range(6)], [None, None, 3, 2, 1, 0])

    def test_ranges_have_the_published_width(self):
        order = ordering()
        combos = {k: (6 if len(k) == 2 else 4 if k[2] == 's' else 12) for k in order}
        self.assertEqual(sum(combos.values()), 1326)
        for seat in (2, 3, 4, 5):
            target = open_frequency(seat, 6)
            self.assertEqual(target, RFI[5 - seat])
            width = sum(c for k, c in combos.items() if order[k] <= target) / 1326
            self.assertAlmostEqual(width, target, delta=.012)
        self.assertLess(order['AA'], order['72o'])
        self.assertIsNone(open_frequency(1, 6))

    def test_opens_only_when_first_in(self):
        agent = Agent(next(s for s in library_strategies() if s.id == 'T02'))
        button = dict(seat=5, active=3, bet=0, to_call=20, stack=2000, min_raise_to=40, max_raise_to=2000, position=1.)
        self.assertEqual(agent.decide(spot(**button), .5), ('raise', 50))
        self.assertEqual(agent.decide(spot(hole=('7s', '2d'), **button), .5), ('fold', 0))
        agent.decide(spot(pot=80, street_raises=1, to_call=50, **{k: v for k, v in button.items() if k != 'to_call'}), .5)
        self.assertTrue(agent.last_details['policy_path'].startswith('fallback_'))


class MdfTests(unittest.TestCase):
    def test_formulas(self):
        # Pot-sized bets on three streets put in 13 pots: 1 -> 3 -> 9 -> 27.
        self.assertAlmostEqual(geometric_fraction(13, 3), 1.)
        self.assertAlmostEqual(geometric_fraction(1, 1), 1.)
        self.assertEqual(percentile(.2, 5), 0.)
        self.assertEqual(percentile(1., 5), 1.)


class EngineTests(unittest.TestCase):
    def test_library_policies_play_only_legal_actions_at_every_depth(self):
        registry = {s.id: s for s in selectable_strategies()}
        used = set()
        for sid in ('T01', 'T02', 'T03', 'T04'):
            for players, depth in ((2, 8), (2, 15), (2, 100), (6, 12), (6, 100)):
                for seed in range(40):
                    table_ = [registry['S55']] * players
                    seat = seed % players
                    table_[seat] = registry[sid]
                    result = play_hand(table_, [depth * 20] * players, 20, seed=5000 + seed)
                    self.assertEqual(sum(result['net']), 0)
                    used.update((sid, m) for m in result['seat_modes'][seat])
        paths = {m for _, m in used}
        for expected in ('nash_jam', 'rfi_chart', 'mdf_bet', 'mdf_defend'):
            self.assertIn(expected, paths)
        self.assertIn(('T04', 'nash_jam'), used)
        self.assertIn(('T04', 'rfi_chart'), used)


if __name__ == '__main__':
    unittest.main()
