import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtWidgets import QApplication
from desktop.labmodel import (LabTable, Coach, STRATEGIES, DEPTHS, RANDOM, PRESETS, RANDOM_POOL, autoplay, bet_presets,
                              grade, explain)


class LabModelTests(unittest.TestCase):
    def test_tables_conserve_chips_and_keep_opponent_cards_private(self):
        for players in (2, 6):
            for depth in DEPTHS:
                table = LabTable(seed=depth + players, players=players, depth_bb=depth)
                coach = Coach(seed=1)
                reveals = 0
                for _ in range(25):
                    if not table.state.status:
                        table.new_hand()
                    while True:
                        view = table.view()
                        if not view['pending']:
                            break
                        self.assertEqual(view['shown'], {})
                        self.assertNotIn('holes', view)
                        result = coach.advise(view['observation'], 'S55')
                        table.act(result['action'], result['raise_to'] or 0)
                    view = table.view()
                    self.assertTrue(view['done'])
                    self.assertEqual(sum(table.state.stacks), sum(table.start))
                    self.assertAlmostEqual(sum(view['deltas']), 0)
                    for seat in view['shown']:
                        self.assertTrue(view['active'][seat])
                        self.assertNotEqual(seat, view['hero'])
                    reveals += bool(view['shown'])
                    if sum(view['active']) < 2:
                        self.assertEqual(view['shown'], {})
                self.assertIn(table.session()['hands'], (25, 26))   # a walk can end the opening hand
                self.assertAlmostEqual(table.session()['series'][-1], sum(table.results))

    def test_players_keep_their_seat_while_the_button_moves(self):
        table = LabTable(seed=2, opponents=['S03', 'S18', 'S23', 'S33', 'S55'])
        coach = Coach(seed=2)
        self.assertEqual(table.lineup, ('S03', 'S18', 'S23', 'S33', 'S55'))
        names, seen, carried = list(table.names), [], None
        for _ in range(12):
            if not table.state.status:
                table.new_hand()
            view = table.view()
            self.assertEqual(sorted(view['order']), list(range(6)))
            self.assertEqual(view['order'][0], view['hero'])
            for player, seat in enumerate(view['order']):
                self.assertEqual(view['names'][seat], names[player])
                self.assertEqual(view['strategies'][seat], None if player == 0 else table.lineup[player - 1])
            if carried is not None:
                self.assertEqual(table.start, [carried[table.player_at(s)] for s in range(6)])
            seen.append(view['positions'][view['hero']])
            autoplay(table, coach, 'S55', 1)
            carried = list(table.stacks)
            self.assertTrue(all(x >= 0 for x in carried))
            if min(carried) < table.bb:
                table.new_hand()
                self.assertTrue(any('rebuy' in note for note in table.view()['notes']))
                self.assertGreaterEqual(min(table.start), table.bb)
        self.assertEqual(set(seen), {'SB', 'BB', 'UTG', 'HJ', 'CO', 'BTN'})

    def test_random_and_chosen_opponents(self):
        a = LabTable(seed=1, opponents=[RANDOM] * 5)
        b = LabTable(seed=2, opponents=[RANDOM] * 5)
        self.assertTrue(set(a.lineup) <= set(RANDOM_POOL))
        self.assertNotEqual(a.lineup, b.lineup)
        self.assertEqual(LabTable(seed=1, opponents=[RANDOM] * 5).lineup, a.lineup)
        mixed = LabTable(seed=3, opponents=['T04', RANDOM, 'S55', RANDOM, 'R06'])
        self.assertEqual((mixed.lineup[0], mixed.lineup[2], mixed.lineup[4]), ('T04', 'S55', 'R06'))
        self.assertEqual(LabTable(seed=3, players=2, opponents=['T01']).lineup, ('T01',))
        for spec in PRESETS.values():
            self.assertEqual(len(spec), 5)
            LabTable(seed=4, opponents=spec)
        fixed = LabTable(seed=5, carry=False)
        autoplay(fixed, Coach(seed=5), 'S55', 8)
        fixed.new_hand() if not fixed.state.status else None
        self.assertEqual(set(fixed.start), {100 * fixed.bb})
        with self.assertRaises(ValueError):
            LabTable(opponents=['S55'])
        with self.assertRaises(ValueError):
            LabTable(opponents=['nope'] * 5)

    def test_deals_are_reproducible_and_hands_cannot_be_skipped(self):
        a, b = LabTable(seed=9), LabTable(seed=9)
        self.assertEqual(a.view(), b.view())
        if a.view()['pending']:
            with self.assertRaises(ValueError):
                a.new_hand()
        with self.assertRaises(ValueError):
            LabTable(players=4)
        with self.assertRaises(ValueError):
            LabTable(depth_bb=33)

    def test_every_selectable_policy_returns_legal_advice_and_a_full_matrix(self):
        table = LabTable(seed=4)
        data = table.view()['observation']
        self.assertEqual(data['board'], ())
        coach = Coach(seed=2)
        for sid in STRATEGIES:
            result = coach.advise(data, sid)
            self.assertIn(result['action'], ('fold', 'call', 'check', 'raise'))
            if result['action'] == 'raise':
                self.assertTrue(data['min_raise_to'] <= result['raise_to'] <= data['max_raise_to'])
            self.assertTrue(result['reasons'])
        for sid in ('S55', 'S03', 'T01', 'T02', 'T04', 'R06'):
            m = coach.matrix(data, sid)
            self.assertEqual((len(m['cells']), len(m['cells'][0])), (13, 13))
            self.assertAlmostEqual(m['raise'] + m['call'] + m['fold'], 1)
            self.assertEqual(m['cells'][0][0]['hand'], 'AA')
            self.assertEqual(m['cells'][0][1]['hand'], 'AKs')
            self.assertEqual(m['cells'][1][0]['hand'], 'AKo')
            self.assertGreaterEqual(m['cells'][0][0]['raise'] + m['cells'][0][0]['call'], .8)
            self.assertIs(coach.matrix(data, sid), m)
        self.assertEqual([r['id'] for r in coach.compare(data, ['S55', 'T04'])], ['S55', 'T04'])

    def test_matrix_is_preflop_only_and_presets_are_legal(self):
        table = LabTable(seed=11)
        coach = Coach(seed=3)
        seen_postflop = False
        for _ in range(80):
            if not table.state.status:
                table.new_hand()
            view = table.view()
            if not view['pending']:
                continue
            data = view['observation']
            for _, value in bet_presets(data):
                self.assertTrue(data['min_raise_to'] <= value <= data['max_raise_to'])
            if data['board']:
                seen_postflop = True
                self.assertIsNone(coach.matrix(data, 'S55'))
                facts = explain(data)
                self.assertTrue(0 <= facts['equity'] <= 1)
            table.act('call')
        self.assertTrue(seen_postflop)

    def test_grading(self):
        raise_ = {'action': 'raise', 'raise_to': 100}
        self.assertEqual(grade('raise', 110, raise_), 'match')
        self.assertEqual(grade('raise', 300, raise_), 'size')
        self.assertEqual(grade('call', 0, raise_), 'differs')
        self.assertEqual(grade('call', 0, {'action': 'check', 'raise_to': None}), 'match')
        self.assertEqual(grade('fold', 0, {'action': 'fold', 'raise_to': None}), 'match')

    def test_autoplay_is_fast_enough_for_the_watch_mode(self):
        table = LabTable(seed=5)
        seconds = autoplay(table, Coach(seed=5), 'S55', 60)
        self.assertGreaterEqual(table.session()['hands'], 60)
        self.assertLess(seconds, 20)


class LabWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from desktop.lab import prepare
        prepare(cls.app)

    def setUp(self):
        from desktop.lab import LabWindow
        self.window = LabWindow(seed=21)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_opens_with_a_live_decision_all_policies_and_a_range(self):
        w = self.window
        self.assertEqual(w.strategy.count(), len(STRATEGIES))
        self.assertEqual(w.sid(), 'S55')
        self.assertTrue(w.view['pending'])
        self.assertIsNotNone(w.advice)
        self.assertIsNotNone(w.grid.matrix)
        self.assertEqual(w.compare_box.count(), len(w.pinned))
        self.assertFalse(w.grab().isNull())

    def test_playing_hands_updates_session_and_grades_decisions(self):
        w = self.window
        for _ in range(200):
            if w.table.session()['hands'] >= 6:
                break
            if w.view['done']:
                w.deal.click()
            elif w.view['pending']:
                w.follow.click()
        self.assertGreaterEqual(w.table.session()['hands'], 6)
        self.assertEqual(w.coach.agreement(), 1.)
        self.assertEqual(w.stat['hands'].text(), str(w.table.session()['hands']))
        self.assertTrue(w.verdict.isVisible())

    def test_quiz_hides_the_answer_until_the_player_acts(self):
        w = self.window
        w.set_mode('quiz')
        self.assertEqual(w.action.text(), 'Your move first')
        self.assertIsNone(w.grid.matrix)
        self.assertFalse(w.follow.isEnabled())
        graded = w.coach.graded
        w.call.click()
        self.assertEqual(w.coach.graded, graded + 1)
        self.assertIn(w.sid(), w.verdict.text())

    def test_watch_mode_plays_without_the_user(self):
        w = self.window
        w.set_mode('watch')
        self.assertFalse(w.call.isEnabled())
        for _ in range(60):
            w.watch_step()
        self.assertGreaterEqual(w.table.session()['hands'], 3)
        self.assertEqual(w.coach.graded, 0)
        w.set_mode('coach')
        self.assertFalse(w.timer.isActive())

    def test_table_options_and_policy_switch_rebuild_cleanly(self):
        w = self.window
        w.players.setCurrentIndex(w.players.findData(2))
        w.depth.setCurrentIndex(w.depth.findData(12))
        self.assertEqual((w.table.players, w.table.depth_bb), (2, 12))
        w.strategy.setCurrentIndex(w.strategy.findData('T01'))
        self.assertEqual(w.advice['strategy'], 'T01')
        w.pin_current()
        self.assertIn('T01', w.pinned)
        w.unpin('T01')
        self.assertNotIn('T01', w.pinned)
        w.four.setChecked(True)
        self.assertFalse(w.grab().isNull())

    def test_opponents_can_be_chosen_or_random_and_hidden(self):
        from desktop.lab import OpponentsDialog
        w = self.window
        dialog = OpponentsDialog(w, w.opponents, True, True)
        dialog.preset.setCurrentIndex(dialog.preset.findData('All random'))
        dialog.apply_preset()
        self.assertEqual(dialog.spec(), [RANDOM] * 5)
        dialog.seats[0].setCurrentIndex(dialog.seats[0].findData('T04'))
        w.set_opponents(dialog.spec(), reveal=False, carry=False)
        self.assertEqual(w.table.lineup[0], 'T04')
        self.assertEqual(len(w.table.lineup), 5)
        self.assertFalse(w.felt.reveal)
        self.assertFalse(w.table.carry)
        self.assertLessEqual(w.table.session()['hands'], 1)
        self.assertFalse(w.grab().isNull())
        w.players.setCurrentIndex(w.players.findData(2))
        self.assertEqual(w.table.lineup, ('T04',))
        dialog.close()

    def test_illegal_clicks_are_ignored(self):
        w = self.window
        hands = w.table.hand_no
        w.next_hand()                      # hand still running
        self.assertEqual(w.table.hand_no, hands)
        if not w.view['observation']['to_call']:
            w.play('fold')
            self.assertTrue(w.view['pending'])


if __name__ == '__main__':
    unittest.main()
