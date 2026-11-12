import json
import unittest

from generation_recipes import export_recipes, make_recipe, restore_recipe


def recipe(**changes):
    value = make_recipe(90, 30, 1.25, 123456, "1024*768", "不需要文字", "<sks> right side view")
    value.update(changes)
    return value


class GenerationRecipeTests(unittest.TestCase):
    def test_round_trip_restores_controls_and_disables_randomization(self):
        restored = restore_recipe(export_recipes([recipe()]))
        self.assertEqual(restored, (
            {"azimuth": 90, "elevation": 30, "distance": 1.25},
            90, 30, 1.25, 123456, False, "1024*768", "不需要文字",
        ))

    def test_batch_selection_uses_one_based_index(self):
        text = export_recipes([recipe(seed=10), recipe(seed=20)])
        self.assertEqual(restore_recipe(text, 2.0)[4], 20)

    def test_export_contains_no_source_image_result_url_or_credentials(self):
        record = recipe()
        self.assertEqual(set(json.loads(export_recipes([record]))["recipes"][0]), {
            "azimuth", "elevation", "distance", "seed", "size", "negative_prompt", "prompt",
        })

    def test_prompt_is_information_and_cannot_override_camera_controls(self):
        self.assertEqual(restore_recipe(export_recipes([recipe(prompt="arbitrary pasted text")]))[1], 90)

    def test_invalid_parameter_values_are_rejected(self):
        for changes in (
            {"azimuth": True}, {"azimuth": 1}, {"elevation": 90},
            {"distance": float("nan")}, {"distance": 0}, {"distance": 10**400},
            {"seed": True}, {"seed": 1.2}, {"seed": -1}, {"seed": 2147483648},
            {"size": "0*1024"}, {"size": "file:///tmp/input"}, {"negative_prompt": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                document = json.loads(export_recipes([recipe()]))
                document["recipes"][0].update(changes)
                restore_recipe(json.dumps(document))

    def test_unknown_formats_and_versions_are_rejected(self):
        for changes in ({"format": "other"}, {"version": True}, {"version": 2}, {"model": "other"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                document = json.loads(export_recipes([recipe()]))
                document.update(changes)
                restore_recipe(json.dumps(document))

    def test_missing_empty_and_oversized_input_is_rejected(self):
        for text in (None, "", "[]", "null", "{" * 2000, " " * (64 * 1024 + 1), export_recipes([])):
            with self.subTest(text=str(text)[:30]), self.assertRaises(ValueError):
                restore_recipe(text)

    def test_invalid_entry_does_not_silently_select_another_generation(self):
        for entry in (0, 2, 1.5, True, "1", float("inf"), 10**400):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                restore_recipe(export_recipes([recipe()]), entry)
