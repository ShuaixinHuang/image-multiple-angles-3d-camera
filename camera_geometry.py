"""Camera prompt geometry shared by the provider and Three.js preview."""

import json
import math

# —— 相机参数映射（送给模型的 prompt 必须是英文，与训练 LoRA 时一致）——
AZIMUTH_MAP = {
    0: "front view",
    45: "front-right quarter view",
    90: "right side view",
    135: "back-right quarter view",
    180: "back view",
    225: "back-left quarter view",
    270: "left side view",
    315: "front-left quarter view",
}

ELEVATION_MAP = {
    -30: "low-angle shot",
    0: "eye-level shot",
    30: "elevated shot",
    60: "high-angle shot",
}

DISTANCE_MAP = {
    0.6: "close-up",
    1.0: "medium shot",
    1.8: "wide shot",
}


def snap_to_nearest(value, options, *, period=None):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("Camera values must be finite numbers")
    if period is None:
        return min(options, key=lambda option: abs(option - value))
    value %= period
    return min(
        options,
        key=lambda option: min(abs(option - value), period - abs(option - value)),
    )


def build_camera_prompt(azimuth, elevation, distance):
    az = snap_to_nearest(azimuth, AZIMUTH_MAP, period=360)
    el = snap_to_nearest(elevation, ELEVATION_MAP)
    dist = snap_to_nearest(distance, DISTANCE_MAP)
    return f"<sks> {AZIMUTH_MAP[az]} {ELEVATION_MAP[el]} {DISTANCE_MAP[dist]}"


def camera_math_js():
    """Emit browser helpers from the same ordered options as the API prompt."""
    return (
        """
        const azimuthSteps = AZIMUTHS;
        const elevationSteps = ELEVATIONS;
        const distanceSteps = DISTANCES;
        const azimuthNames = AZIMUTH_NAMES;
        const elevationNames = ELEVATION_NAMES;
        const distanceNames = DISTANCE_NAMES;
        function snapToNearest(value, steps, period = null) {
            if (period !== null) value = ((value % period) + period) % period;
            const gap = step => {
                const delta = Math.abs(step - value);
                return period === null ? delta : Math.min(delta, period - delta);
            };
            return steps.reduce((prev, curr) => gap(curr) < gap(prev) ? curr : prev);
        }
        function snapAzimuth(value) {
            return snapToNearest(value, azimuthSteps, 360);
        }
        function distanceNameOf(value) {
            return distanceNames[String(snapToNearest(value, distanceSteps))];
        }
    """.replace("AZIMUTHS", json.dumps(list(AZIMUTH_MAP)))
        .replace("ELEVATIONS", json.dumps(list(ELEVATION_MAP)))
        .replace("DISTANCES", json.dumps(list(DISTANCE_MAP)))
        .replace("AZIMUTH_NAMES", json.dumps(AZIMUTH_MAP))
        .replace("ELEVATION_NAMES", json.dumps(ELEVATION_MAP))
        .replace(
            "DISTANCE_NAMES",
            json.dumps(
                {format(key, "g"): value for key, value in DISTANCE_MAP.items()}
            ),
        )
    )
