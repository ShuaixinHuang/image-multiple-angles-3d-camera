import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import core
from generation_recipes import export_recipes, restore_recipe


def successful_response():
    return SimpleNamespace(
        status_code=200,
        output=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=[{"image": "https://example.invalid/result.png"}]
        ))]),
    )


class GenerationSeedTests(unittest.TestCase):
    def test_fixed_seed_is_sent_to_the_provider_and_returned(self):
        with patch.object(core.MultiModalConversation, "call", return_value=successful_response()) as call:
            _, seed, _ = core.infer_camera_edit(
                Image.new("RGB", (8, 8)), seed=123456, randomize_seed=False
            )
        self.assertEqual(seed, 123456)
        self.assertEqual(call.call_args.kwargs.get("seed"), seed)

    def test_random_seed_matches_the_reported_seed(self):
        with patch.object(core.MultiModalConversation, "call", return_value=successful_response()) as call:
            with patch.object(core.random, "randint", return_value=7654321):
                _, seed, _ = core.infer_camera_edit(Image.new("RGB", (8, 8)))
        self.assertEqual(seed, 7654321)
        self.assertEqual(call.call_args.kwargs["seed"], seed)

    def test_invalid_fixed_seed_is_rejected_before_a_paid_call(self):
        for seed in (True, -1, core.MAX_SEED + 1, 1.5, float("nan"), float("inf")):
            with self.subTest(seed=seed), patch.object(core.MultiModalConversation, "call") as call:
                with self.assertRaises(core.gr.Error):
                    core.infer_camera_edit(Image.new("RGB", (8, 8)), seed=seed, randomize_seed=False)
                call.assert_not_called()

    def test_random_batch_records_each_actual_seed_in_gallery_order(self):
        with patch.object(core.MultiModalConversation, "call", return_value=successful_response()) as call:
            with patch.object(core.random, "randint", side_effect=[71, 82]):
                results, final_seed, recipes = core.batch_infer_camera_edit(
                    Image.new("RGB", (8, 8)), ["right", "aerial"],
                    negative_prompt="不需要文字", include_recipes=True,
                )
        self.assertEqual([key for _, key in results], ["right", "aerial"])
        self.assertEqual(final_seed, 82)
        self.assertEqual([r["seed"] for r in recipes], [71, 82])
        self.assertEqual([c.kwargs["seed"] for c in call.call_args_list], [71, 82])
        self.assertEqual([r["azimuth"] for r in recipes], [90, 0])
        self.assertEqual([r["elevation"] for r in recipes], [0, 60])
        self.assertEqual(restore_recipe(export_recipes(recipes), 2)[4], 82)

    def test_fixed_batch_keeps_the_same_seed_and_legacy_return_shape(self):
        with patch.object(core.MultiModalConversation, "call", return_value=successful_response()) as call:
            results, final_seed = core.batch_infer_camera_edit(
                Image.new("RGB", (8, 8)), ["front", "right"],
                seed=0, randomize_seed=False,
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(final_seed, 0)
        self.assertEqual([c.kwargs["seed"] for c in call.call_args_list], [0, 0])

    def test_invalid_batch_selection_does_not_charge_for_an_earlier_valid_view(self):
        with patch.object(core.MultiModalConversation, "call") as call:
            with self.assertRaises(core.gr.Error):
                core.batch_infer_camera_edit(Image.new("RGB", (8, 8)), ["front", "missing"])
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
