import json
import shutil
import subprocess
import unittest

from camera_geometry import build_camera_prompt, camera_math_js


class CameraGeometryTests(unittest.TestCase):
    def test_azimuth_wraps_across_front_view_seam(self):
        for angle in (350, 359.9, 360, 710, -10, -360):
            with self.subTest(angle=angle):
                self.assertEqual(
                    build_camera_prompt(angle, 0, 1),
                    "<sks> front view eye-level shot medium shot",
                )
        self.assertIn("front-left quarter view", build_camera_prompt(330, 0, 1))
        self.assertIn("front-right quarter view", build_camera_prompt(45, 0, 1))

    def test_finite_camera_values_required(self):
        for value in (True, "90", float("nan"), float("inf")):
            for controls in ((value, 0, 1), (0, value, 1), (0, 0, value)):
                with self.subTest(controls=controls), self.assertRaises(ValueError):
                    build_camera_prompt(*controls)

    @unittest.skipUnless(
        shutil.which("node"), "Node.js required for actual browser math"
    )
    def test_browser_preview_and_provider_prompt_match_across_controls(self):
        controls = [
            [az, el, round(0.6 + distance * 0.05, 2)]
            for az in (-10, 0, 22.5, 45, 180, 315, 330, 337.5, 350, 360, 710)
            for el in (-30, 0, 15, 30, 60)
            for distance in range(25)
        ]
        program = (
            camera_math_js()
            + "\nconst values = "
            + json.dumps(controls)
            + ";\n"
            + 'console.log(JSON.stringify(values.map(([az,el,d]) => "<sks> " + azimuthNames[snapAzimuth(az)] + " " + elevationNames[snapToNearest(el,elevationSteps)] + " " + distanceNameOf(d))));'
        )
        result = subprocess.run(
            [shutil.which("node"), "-e", program],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(
            json.loads(result.stdout), [build_camera_prompt(*row) for row in controls]
        )
        self.assertIn("medium shot", build_camera_prompt(0, 0, 1.3))
        self.assertIn("wide shot", build_camera_prompt(0, 0, 1.8))


if __name__ == "__main__":
    unittest.main()
