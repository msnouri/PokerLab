import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from desktop.model import Advisor, validate
from desktop.practice import PracticeTable
from desktop.render import render_table


class ResearchGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_heads_up_practice_is_private_legal_and_renderable(self):
        table = PracticeTable(seed=38021, players=2)
        advisor = Advisor(); decisions = 0
        for hand in range(18):
            if hand:
                table.new_hand()
            while table.view()['pending']:
                view = table.view(); data = view['observation']
                self.assertEqual(len(view['stacks']), 2)
                self.assertNotIn('holes', view)
                self.assertIsInstance(data['heads_up_in_position'], bool)
                image = render_table(view)
                self.assertGreater(image.width, 1000)
                self.assertIsNotNone(image.getbbox())
                result = advisor.recommend(data, 'R06')
                self.assertIn('policy_path', result['policy_details'])
                table.act(result['action'], result['raise_to'] or 0)
                decisions += 1
            self.assertEqual(sum(table.state.stacks), 4000)
        self.assertGreater(decisions, 18)

    def test_strategy_selector_and_async_table_switch(self):
        from desktop.app import Window
        window = Window()
        try:
            self.assertEqual(window.strategy.count(), 90)
            self.assertEqual(window.strategy.currentData(), 'S55')
            window.strategy.setCurrentIndex(window.strategy.findData('R03'))
            window.player_count.setCurrentIndex(window.player_count.findData(2))
            end = time.monotonic()+10
            while window.practice_busy and time.monotonic() < end:
                self.app.processEvents(); time.sleep(.005)
            self.assertFalse(window.practice_busy)
            self.assertEqual(window.table.players, 2)
            self.assertTrue(window.player_count.isEnabled())
            self.assertIsNone(window.latest)
            self.assertEqual(window.strategy.currentData(), 'R03')
        finally:
            window.close(); self.app.processEvents()

    def test_studio_opens_the_agent_selector_without_a_shell(self):
        from desktop.studio import Studio, ImageProvider
        studio = Studio(ImageProvider(), start_worker=False)
        try:
            with patch('subprocess.Popen') as spawn:
                studio.openAgentLab()
            arguments = spawn.call_args.args[0]
            self.assertEqual(arguments[1:], ['-m', 'desktop', '--lab'])
            self.assertFalse(spawn.call_args.kwargs.get('shell', False))
        finally:
            studio.close()

    def test_invalid_public_position_is_rejected(self):
        table = PracticeTable(seed=38021, players=2)
        with self.assertRaises(ValueError):
            validate({**table.view()['observation'], 'heads_up_in_position': 'true'})


if __name__ == '__main__':
    unittest.main()
