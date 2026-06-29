from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import METADATA_DIR, ensure_dir, load_experiment_config


DEFAULT_OUTPUT = METADATA_DIR / "pretest_plan.csv"


def build_episode_id(stage_code: str, index: int) -> str:
    return f"LC_CS30_AIR_PRE_{stage_code}_{index:04d}"


def generate_pretest_plan(output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    config = load_experiment_config()
    base = config["base_condition"]
    fixed = config["fixed_parameters"]
    center = config["pretest_center"]
    scans = config["pretest_scans"]

    rows: list[dict[str, object]] = []

    for index, speed in enumerate(scans["speed_scan"]["speed_m_min"], start=1):
        rows.append(
            {
                "episode_id": build_episode_id("SPEED", index),
                "stage": "pretest_speed_scan",
                "material": base["material"],
                "thickness_mm": base["thickness_mm"],
                "gas": base["assist_gas"],
                "power_kw": center["power_kw"],
                "speed_m_min": speed,
                "air_pressure_mpa": center["air_pressure_mpa"],
                "focus_mm": center["focus_mm"],
                "nozzle_height_mm": fixed["nozzle_height_mm"],
                "nozzle_diameter_mm": fixed["nozzle_diameter_mm"],
                "path_type": fixed["path_type"],
            }
        )

    for index, focus in enumerate(scans["focus_scan"]["focus_mm"], start=1):
        rows.append(
            {
                "episode_id": build_episode_id("FOCUS", index),
                "stage": "pretest_focus_scan",
                "material": base["material"],
                "thickness_mm": base["thickness_mm"],
                "gas": base["assist_gas"],
                "power_kw": center["power_kw"],
                "speed_m_min": center["speed_m_min"],
                "air_pressure_mpa": center["air_pressure_mpa"],
                "focus_mm": focus,
                "nozzle_height_mm": fixed["nozzle_height_mm"],
                "nozzle_diameter_mm": fixed["nozzle_diameter_mm"],
                "path_type": fixed["path_type"],
            }
        )

    for index, pressure in enumerate(scans["pressure_scan"]["air_pressure_mpa"], start=1):
        rows.append(
            {
                "episode_id": build_episode_id("PRESS", index),
                "stage": "pretest_pressure_scan",
                "material": base["material"],
                "thickness_mm": base["thickness_mm"],
                "gas": base["assist_gas"],
                "power_kw": center["power_kw"],
                "speed_m_min": center["speed_m_min"],
                "air_pressure_mpa": pressure,
                "focus_mm": center["focus_mm"],
                "nozzle_height_mm": fixed["nozzle_height_mm"],
                "nozzle_diameter_mm": fixed["nozzle_diameter_mm"],
                "path_type": fixed["path_type"],
            }
        )

    plan = pd.DataFrame(rows)
    ensure_dir(output_path.parent)
    plan.to_csv(output_path, index=False, encoding="utf-8-sig")
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate pretest cutting plan.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = generate_pretest_plan(args.output)
    print(f"Generated {len(plan)} pretest episodes: {args.output}")


if __name__ == "__main__":
    main()
