import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

from desktop.model import Advisor, example, validate, cards, CARD_TEXT
from desktop.practice import PracticeTable
from desktop.render import render_table, standard_profile
from desktop.vision import Reader, Profile, StableReadings, parse_amount, crop, card_image, tesseract_path


class BoundaryTests(unittest.TestCase):
    def test_cards_and_invalid_state(self):
        self.assertEqual(cards("10H, as"),("Th","As"))
        for update in ({"hole":"As As"},{"board":"As 2c 3c"},{"board":"2c 3c"},
                       {"to_call":1801},{"position":float("nan")},{"stack":2.5},
                       {"active":7},{"min_raise_to":100},{"max_raise_to":2001},
                       {"pot":10},{"seat":6},{"min_raise_to":None},{"preflop_raiser":"true"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate({**example(),**update})

    def test_valid_all_in_call_and_no_raises(self):
        data={**example(),"to_call":1800,"pot":2000,"min_raise_to":None,"max_raise_to":None}
        result=Advisor().recommend(data)
        self.assertNotEqual(result["action"],"raise")

    def test_strict_amounts_preserve_units(self):
        for raw,scale,expected in (("$1,234.50",100,123450),("2.5k",1,2500),("0",100,0),("18.75",100,1875)):
            self.assertEqual(parse_amount(raw,scale),expected)
        for raw in ("1,25","O.50","1.2.3","10 20 chips","-25","1,234,56"):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                parse_amount(raw)
        with self.assertRaises(ValueError):
            parse_amount("18.75",1)

    def test_profile_bounds_and_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"layout.json"
            profile=standard_profile();profile.save(path)
            self.assertEqual(Profile.load(path).regions,profile.regions)
            for data in ({"regions":{"pot":[0,0,2,1]}},{"templates":{"As":"../outside.png"}},
                         {"chip_scale":0},{"regions":{"secret":[0,0,1,1]}}):
                path.write_text(json.dumps({**profile.__dict__,**data}))
                with self.assertRaises(ValueError):
                    Profile.load(path)

    def test_stability_does_not_survive_missing_data(self):
        gate=StableReadings()
        good={"values":{"pot":200},"errors":{}}
        self.assertFalse(gate.add(good));self.assertTrue(gate.add(good))
        self.assertFalse(gate.add({"values":{},"errors":{"pot":"unreadable"}}))
        self.assertFalse(gate.add(good))
        self.assertFalse(gate.add({"values":{"pot":201},"errors":{}}))


class PracticeTests(unittest.TestCase):
    def test_interactive_hands_legal_conserving_private(self):
        table=PracticeTable(seed=1234);advisor=Advisor()
        decisions=0
        for hand in range(40):
            if hand:
                table.new_hand()
            while table.view()["pending"]:
                view=table.view();data=view["observation"]
                self.assertNotIn("holes",view)
                self.assertNotIn("deck",data)
                self.assertEqual(tuple(data["hole"]),view["hole"])
                self.assertEqual(sum(table.state.stacks)+table.state.total_pot_amount,12000)
                result=advisor.recommend(data)
                table.act(result["action"],result["raise_to"] or 0)
                decisions+=1
                self.assertLess(decisions,1000)
            self.assertEqual(sum(table.state.stacks),12000)
            self.assertTrue(all(v>=0 for v in table.state.stacks))
        self.assertGreater(decisions,40)


class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=Reader(Profile())

    def test_all_cards_survive_screen_resize(self):
        for card in CARD_TEXT:
            # Simulate a table rendered at 1.5x before returning a region crop.
            im=card_image(card).resize((96,132),Image.Resampling.LANCZOS)
            with self.subTest(card=card):
                self.assertEqual(self.reader.read_card(im)[0],card)

    def test_unknown_card_art_is_withheld(self):
        for image in (card_image(None),Image.new("RGB",(64,88),"white"),Image.new("RGB",(64,88),"black")):
            with self.assertRaises(ValueError):
                self.reader.read_card(image)

    @unittest.skipUnless(tesseract_path(),"optional Tesseract engine is absent")
    def test_rendered_table_to_public_state(self):
        table=PracticeTable(seed=788);view=table.view();profile=standard_profile()
        result=Reader(profile).read(render_table(view))
        self.assertFalse(result["errors"],result["errors"])
        values=result["values"];obs=view["observation"]
        self.assertEqual((values["hole_1"],values["hole_2"]),view["hole"])
        self.assertEqual(tuple(values[f"board_{i}"] for i in range(1,6) if values[f"board_{i}"]),view["board"])
        for key in ("pot","stack","to_call","bet","min_raise_to","max_raise_to"):
            self.assertEqual(values[key],obs[key],key)

    @unittest.skipUnless(tesseract_path(),"optional Tesseract engine is absent")
    def test_ocr_deadline_withholds_unread_amounts(self):
        table=PracticeTable(seed=788);profile=standard_profile()
        start=time.monotonic()
        result=Reader(profile).read(render_table(table.view()),budget=.001)
        self.assertIn("pot",result["errors"])
        self.assertLess(time.monotonic()-start,2)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.app import Window
        self.window=Window()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def wait_worker(self):
        end=time.monotonic()+10
        while (self.window.advising or self.window.practice_busy or self.window.scanning) and time.monotonic()<end:
            self.app.processEvents();time.sleep(.005)
        self.assertFalse(self.window.advising or self.window.practice_busy or self.window.scanning)

    def test_practice_suggestion_and_action(self):
        w=self.window
        before=len(w.table.history)
        w.analyze();self.wait_worker()
        self.assertIsNotNone(w.latest)
        self.assertTrue(w.use_advice.isEnabled())
        w.use_suggestion();self.wait_worker()
        self.assertGreater(len(w.table.history),before)

    def test_manual_review_and_edit_invalidate_advice(self):
        w=self.window;w.tabs.setCurrentIndex(1)
        self.assertEqual(w.edit["hole"].text(),"")
        w.load_example()
        self.assertFalse(w.analyze_button.isEnabled())
        w.confirm.setChecked(True)
        self.assertTrue(w.analyze_button.isEnabled())
        w.analyze();self.wait_worker();self.assertIsNotNone(w.latest)
        w.edit["pot"].setValue(310)
        self.assertIsNone(w.latest)
        self.assertFalse(w.confirm.isChecked())

    def test_old_worker_cannot_publish_after_edit(self):
        w=self.window;w.load_example();w.confirm.setChecked(True)
        original=w.advisor.recommend
        def delayed(*args):
            time.sleep(.08)
            return original(*args)
        w.advisor.recommend=delayed
        w.analyze();w.edit["pot"].setValue(320)
        self.wait_worker()
        self.assertIsNone(w.latest)
        self.assertNotIn(w.action.text(),("CALL 100","CHECK","FOLD"))

    def test_expired_live_frame_withholds_advice(self):
        w=self.window;w.load_example()
        w.source_is_live=True;w.source_time=time.monotonic()-11
        w.confirm.setChecked(True);w.analyze();self.wait_worker()
        self.assertIsNone(w.latest)
        self.assertEqual(w.action.text(),"Frame expired")

    def test_invalid_image_state_cannot_reach_policy(self):
        w=self.window;w.load_example();w.edit["hole"].setText("As As")
        w.confirm.setChecked(True);w.analyze();self.wait_worker()
        self.assertIsNone(w.latest)
        self.assertEqual(w.action.text(),"Needs review")


if __name__=="__main__":
    unittest.main()
