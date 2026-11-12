"""Portable generation settings, without API keys, source images or result URLs."""

import json
import math
import re

MODEL = "qwen-image-edit-plus"
FORMAT = "camera-control-generation-recipes"
MAX_RECIPE_BYTES = 64 * 1024


def make_recipe(azimuth, elevation, distance, seed, size, negative_prompt, prompt):
    return {
        "azimuth": azimuth,
        "elevation": elevation,
        "distance": distance,
        "seed": seed,
        "size": size,
        "negative_prompt": negative_prompt or " ",
        "prompt": prompt,
    }


def export_recipes(recipes):
    """Serialize completed generations in their displayed order."""
    return json.dumps(
        {"format": FORMAT, "version": 1, "model": MODEL, "recipes": recipes},
        ensure_ascii=False, indent=2, allow_nan=False,
    )


def restore_recipe(text, entry=1):
    """Validate a pasted recipe and return controls; never generate or load a URL.

    The prompt is informational. It is rebuilt from camera controls on Generate.
    Randomization is disabled so the exported seed is reused deliberately.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_RECIPE_BYTES:
        raise ValueError("Recipe JSON must be at most 64 KiB.")
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Paste valid recipe JSON.") from exc
    if (
        not isinstance(document, dict)
        or document.get("format") != FORMAT
        or type(document.get("version")) is not int
        or document["version"] != 1
        or document.get("model") != MODEL
    ):
        raise ValueError("Unsupported recipe format, version or model.")
    recipes = document.get("recipes")
    if not isinstance(recipes, list) or not 1 <= len(recipes) <= 6:
        raise ValueError("Expected between 1 and 6 generation recipes.")
    if (
        isinstance(entry, bool) or not isinstance(entry, (int, float))
        or not 1 <= entry <= len(recipes)
        or not math.isfinite(entry) or int(entry) != entry
    ):
        raise ValueError("Choose an existing recipe number, starting at 1.")
    recipe = recipes[int(entry) - 1]
    if not isinstance(recipe, dict):
        raise ValueError("The selected recipe must be an object.")
    az, el, dist = (recipe.get(key) for key in ("azimuth", "elevation", "distance"))
    if (
        any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (az, el, dist))
        or az not in range(0, 316, 45) or el not in (-30, 0, 30, 60)
        or not 0.6 <= dist <= 1.8 or not math.isfinite(dist)
    ):
        raise ValueError("Camera values are outside the supported controls.")
    seed = recipe.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("Seed must be an integer between 0 and 2147483647.")
    size, negative = recipe.get("size"), recipe.get("negative_prompt")
    if not isinstance(size, str) or re.fullmatch(r"[1-9][0-9]{0,4}\*[1-9][0-9]{0,4}", size) is None:
        raise ValueError("Size must use width*height, for example 1024*1024.")
    if not isinstance(negative, str):
        raise ValueError("Negative prompt must be text.")
    camera = {"azimuth": az, "elevation": el, "distance": dist}
    return camera, az, el, dist, seed, False, size, negative
