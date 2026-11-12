import importlib
import json
import unittest
from unittest.mock import patch

from PIL import Image

import core
from test_generation import successful_response


class RecipeUiTests(unittest.TestCase):
    def test_both_real_gradio_uis_export_and_restore_without_an_api_call(self):
        for edition in ("app_zh", "app_en"):
            with self.subTest(edition=edition):
                app = importlib.import_module(edition)
                demo = app.build_ui()
                try:
                    functions = {f.fn.__name__: f for f in demo.fns.values() if f.fn}
                    generate = functions["on_run"]
                    apply = functions["on_apply_recipe"]
                    self.assertIsInstance(generate.outputs[-1], core.gr.Code)
                    self.assertIs(apply.inputs[0], generate.outputs[-1])
                    self.assertEqual(len(apply.outputs), 8)
                    old_history = [("https://example.invalid/old.png", "previous")]
                    with patch.object(core.MultiModalConversation, "call", return_value=successful_response()) as call:
                        output = generate.fn(Image.new("RGB", (8, 8)), 90, 30, 1.25, 123456, False, "1024*768", "text", old_history)
                        self.assertEqual(len(old_history), 1)
                        self.assertEqual(len(output[2]), 2)
                        self.assertEqual(json.loads(output[-1])["recipes"][0]["seed"], 123456)
                        call.reset_mock()
                        controls = apply.fn(output[-1], 1)
                        self.assertEqual(controls[1:], (90, 30, 1.25, 123456, False, "1024*768", "text"))
                        call.assert_not_called()
                        with self.assertRaises(core.gr.Error):
                            apply.fn("not json", 1)
                        call.assert_not_called()
                        with self.assertRaises(core.gr.Error) as invalid_seed:
                            generate.fn(Image.new("RGB", (8, 8)), 0, 0, 1.0, -1, False, "1024*1024", " ", [])
                        self.assertEqual(invalid_seed.exception.message, app.T["err_seed"])
                        call.assert_not_called()
                    with patch.object(core.MultiModalConversation, "call", return_value=successful_response()):
                        with patch.object(core.random, "randint", side_effect=[42, 73]):
                            batch = functions["on_batch_run"].fn(Image.new("RGB", (8, 8)), ["front", "right"], 0, True, "1024*1024", " ", [])
                    self.assertIn("seed=42", batch[0][0][1])
                    self.assertIn("seed=73", batch[0][1][1])
                    self.assertEqual(json.loads(batch[-1])["recipes"][1]["seed"], 73)
                finally:
                    demo.close()


if __name__ == "__main__":
    unittest.main()
