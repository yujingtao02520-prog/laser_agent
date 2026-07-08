from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import METADATA_DIR, ensure_dir, load_experiment_config


DEFAULT_OUTPUT = METADATA_DIR / "orthogonal_plan_L9.csv"
DEFAULT_EXPERIMENT_PLAN = METADATA_DIR / "experiment_plan.csv"

L9_TABLE = [
    [1, 1, 1, 1],
    [1, 2, 2, 2],
    [1, 3, 3, 3],
    [2, 1, 2, 3],
    [2, 2, 3, 1],
    [2, 3, 1, 2],
    [3, 1, 3, 2],
    [3, 2, 1, 3],
    [3, 3, 2, 1],
]


def generate_orthogonal_plan(
    output_path: Path = DEFAULT_OUTPUT,
    experiment_plan_path: Path = DEFAULT_EXPERIMENT_PLAN,
) -> pd.DataFrame:
    config = load_experiment_config()
    base = config["base_condition"]
    fixed = config["fixed_parameters"]
    factors = config["orthogonal_factors"]

    power_levels = factors["A_power_kw"]
    speed_levels = factors["B_speed_m_min"]
    pressure_levels = factors["C_air_pressure_mpa"]
    focus_levels = factors["D_focus_mm"]

    rows: list[dict[str, object]] = []
    for run_index, (a_level, b_level, c_level, d_level) in enumerate(L9_TABLE, start=1):
        rows.append(
            {
                "episode_id": f"LC_CS30_AIR_L9_{run_index:04d}",
                "stage": "orthogonal_L9",
                "material": base["material"],
                "thickness_mm": base["thickness_mm"],
                "gas": base["assist_gas"],
                "power_kw": power_levels[a_level - 1],
                "speed_m_min": speed_levels[b_level - 1],
                "air_pressure_mpa": pressure_levels[c_level - 1],
                "focus_mm": focus_levels[d_level - 1],
                "A_level": a_level,
                "B_level": b_level,
                "C_level": c_level,
                "D_level": d_level,
                "nozzle_height_mm": fixed["nozzle_height_mm"],
                "nozzle_diameter_mm": fixed["nozzle_diameter_mm"],
                "path_type": fixed["path_type"],
            }
        )

    plan = pd.DataFrame(rows)
    ensure_dir(output_path.parent)
    plan.to_csv(output_path, index=False, encoding="utf-8-sig")
    plan.to_csv(experiment_plan_path, index=False, encoding="utf-8-sig")
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate L9 orthogonal cutting plan.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--experiment-plan", type=Path, default=DEFAULT_EXPERIMENT_PLAN)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = generate_orthogonal_plan(args.output, args.experiment_plan)
    print(f"Generated {len(plan)} L9 episodes: {args.output}")


if __name__ == "__main__":
    main()
