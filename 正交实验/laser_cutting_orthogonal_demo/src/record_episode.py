from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from utils import (
    PROCESSED_DATA_DIR,
    candidate_action_space,
    ensure_dir,
    load_experiment_config,
    quality_band,
    read_json,
    write_json,
)


def normalize_plan_record(plan_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": plan_record["episode_id"],
        "material": plan_record["material"],
        "thickness_mm": int(plan_record["thickness_mm"]),
        "assist_gas": plan_record.get("gas", plan_record.get("assist_gas", "air")),
        "laser_power_kw": float(plan_record["power_kw"]),
        "cutting_speed_m_min": float(plan_record["speed_m_min"]),
        "air_pressure_mpa": float(plan_record["air_pressure_mpa"]),
        "focus_position_mm": float(plan_record["focus_mm"]),
        "nozzle_height_mm": float(plan_record["nozzle_height_mm"]),
        "nozzle_diameter_mm": float(plan_record["nozzle_diameter_mm"]),
        "path_type": plan_record["path_type"],
        "experiment_stage": plan_record.get("stage", "unknown"),
    }


def normalize_quality_record(quality_record: dict[str, Any]) -> dict[str, Any]:
    cut_through = bool(quality_record["cut_through"])
    score = float(quality_record["quality_score"])
    failure_case = str(quality_record["failure_case"])
    return {
        "episode_id": quality_record["episode_id"],
        "cut_through": cut_through,
        "overall_quality": quality_band(score, cut_through, failure_case),
        "quality_score": score,
        "failure_case": failure_case,
        "kerf_width_top_mm": float(quality_record["kerf_width_top_mm"]),
        "kerf_width_bottom_mm": float(quality_record["kerf_width_bottom_mm"]),
        "taper_mm": float(quality_record["taper_mm"]),
        "dross_height_max_mm": float(quality_record["dross_height_max_mm"]),
        "dross_height_mean_mm": float(quality_record["dross_height_mean_mm"]),
        "roughness_Sa_um": float(quality_record["roughness_Sa_um"]),
        "defect_area_mm2": float(quality_record["defect_area_mm2"]),
        "manual_comment": quality_record.get("manual_comment", ""),
    }


def build_agent_input(params: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    config = load_experiment_config()
    return {
        "process_parameters": params,
        "quality_observation": quality,
        "failure_case": [quality["failure_case"]],
        "candidate_action_space": candidate_action_space(config),
    }


def record_episode(
    plan_record: dict[str, Any],
    quality_record: dict[str, Any],
    processed_root: Path = PROCESSED_DATA_DIR,
) -> Path:
    episode_id = str(plan_record["episode_id"])
    episode_dir = ensure_dir(processed_root / episode_id)
    params = normalize_plan_record(plan_record)
    quality = normalize_quality_record(quality_record)
    agent_input = build_agent_input(params, quality)

    write_json(episode_dir / "params.json", params)
    write_json(episode_dir / "quality.json", quality)
    write_json(episode_dir / "agent_input.json", agent_input)
    return episode_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create episode JSON files.")
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--plan", type=Path, default=Path("data/metadata/orthogonal_plan_L9.csv"))
    parser.add_argument("--quality-json", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan_path = args.plan if args.plan.is_absolute() else Path.cwd() / args.plan
    quality_path = args.quality_json if args.quality_json.is_absolute() else Path.cwd() / args.quality_json
    plan = pd.read_csv(plan_path)
    plan_row = plan.loc[plan["episode_id"] == args.episode_id]
    if plan_row.empty:
        raise ValueError(f"Episode not found in plan: {args.episode_id}")
    quality = read_json(quality_path)
    episode_dir = record_episode(plan_row.iloc[0].to_dict(), quality)
    print(f"Recorded episode files: {episode_dir}")


if __name__ == "__main__":
    main()
