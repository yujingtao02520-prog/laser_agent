from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from record_episode import record_episode
from utils import (
    METADATA_DIR,
    ensure_dir,
    load_scoring_rule,
    round_float,
)


DEFAULT_PLAN = METADATA_DIR / "orthogonal_plan_L9.csv"
DEFAULT_LOG = METADATA_DIR / "experiment_log.csv"
DEFAULT_SUMMARY = METADATA_DIR / "quality_summary.csv"


def score_quality(metrics: dict[str, Any], scoring_rule: dict[str, Any]) -> float:
    coeffs = scoring_rule["coefficients"]
    target_kerf = scoring_rule["target_kerf_width_mm"]
    failure_case = metrics["failure_case"]
    penalty = scoring_rule["penalties"].get(failure_case, 0)

    score = (
        100.0
        - coeffs["alpha_dross"] * metrics["dross_height_max_mm"]
        - coeffs["beta_roughness"] * metrics["roughness_Sa_um"]
        - coeffs["gamma_kerf_error"] * abs(metrics["kerf_width_top_mm"] - target_kerf)
        - coeffs["delta_taper"] * metrics["taper_mm"]
        - penalty
    )

    for capped_case, cap in scoring_rule["failure_caps"].items():
        if failure_case == capped_case:
            score = min(score, float(cap))
    if not metrics["cut_through"]:
        score = min(score, float(scoring_rule["failure_caps"]["incomplete_cut"]))
    return round_float(max(0.0, min(100.0, score)), 2)


def classify_failure(
    cut_through: bool,
    energy_index: float,
    air_pressure_mpa: float,
    kerf_width_top_mm: float,
    dross_height_max_mm: float,
    roughness_sa_um: float,
) -> str:
    if not cut_through:
        return "incomplete_cut"
    if air_pressure_mpa >= 1.8 and energy_index < 55:
        return "unstable_cut"
    if energy_index > 88:
        return "overburn"
    if kerf_width_top_mm > 1.35:
        return "overcut"
    if dross_height_max_mm > 1.2:
        return "dross"
    if roughness_sa_um > 18:
        return "rough_surface"
    return "normal"


def simulate_one_episode(plan_record: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    scoring_rule = load_scoring_rule()
    power_kw = float(plan_record["power_kw"])
    speed_m_min = float(plan_record["speed_m_min"])
    air_pressure_mpa = float(plan_record["air_pressure_mpa"])
    focus_mm = float(plan_record["focus_mm"])

    energy_index = power_kw / speed_m_min
    ideal_energy = 62.0
    target_kerf = scoring_rule["target_kerf_width_mm"]
    focus_error = abs(focus_mm - (-9.0))

    cut_through = bool(
        energy_index >= 48
        and not (energy_index < 52 and (air_pressure_mpa < 1.35 or focus_error >= 3.0))
    )

    dross_height_max_mm = (
        0.32
        + max(0.0, 1.5 - air_pressure_mpa) * 1.45
        + max(0.0, 56.0 - energy_index) * 0.026
        + max(0.0, focus_error - 1.5) * 0.08
        + rng.normal(0.0, 0.07)
    )
    if not cut_through:
        dross_height_max_mm += 1.0 + max(0.0, 50.0 - energy_index) * 0.08
    dross_height_max_mm = max(0.05, dross_height_max_mm)

    roughness_sa_um = (
        8.5
        + abs(energy_index - ideal_energy) * 0.13
        + focus_error * 0.95
        + max(0.0, air_pressure_mpa - 1.65) * 3.0
        + rng.normal(0.0, 0.8)
    )
    roughness_sa_um = max(4.0, roughness_sa_um)

    kerf_width_top_mm = (
        target_kerf
        + (energy_index - ideal_energy) * 0.006
        + (air_pressure_mpa - 1.5) * 0.09
        + rng.normal(0.0, 0.025)
    )
    kerf_width_top_mm = max(0.6, kerf_width_top_mm)

    taper_base = (
        0.08
        + speed_m_min * 0.055
        + focus_error * 0.035
        + max(0.0, 54.0 - energy_index) * 0.006
        + max(0.0, energy_index - 82.0) * 0.003
        + rng.normal(0.0, 0.018)
    )
    taper_mm = max(0.02, taper_base)
    kerf_width_bottom_mm = max(0.45, kerf_width_top_mm - taper_mm)

    defect_area_mm2 = (
        max(0.0, dross_height_max_mm - 0.8) * 9.0
        + max(0.0, roughness_sa_um - 16.0) * 1.3
        + (0.0 if cut_through else 25.0)
        + rng.normal(0.0, 1.2)
    )
    defect_area_mm2 = max(0.0, defect_area_mm2)

    failure_case = classify_failure(
        cut_through,
        energy_index,
        air_pressure_mpa,
        kerf_width_top_mm,
        dross_height_max_mm,
        roughness_sa_um,
    )

    manual_comments = {
        "normal": "Simulated cut is stable with acceptable kerf and dross.",
        "incomplete_cut": "Energy density is insufficient for full penetration.",
        "dross": "Lower-edge dross is high, likely linked to gas evacuation or energy balance.",
        "overburn": "Energy input is excessive and heat affected symptoms are expected.",
        "overcut": "Kerf is wider than target and may reduce dimensional accuracy.",
        "rough_surface": "Cut face roughness is elevated, focus and speed need refinement.",
        "unstable_cut": "Gas/energy balance may cause unstable melt removal.",
    }

    metrics: dict[str, Any] = {
        "episode_id": plan_record["episode_id"],
        "energy_index": round_float(energy_index, 3),
        "cut_through": cut_through,
        "failure_case": failure_case,
        "kerf_width_top_mm": round_float(kerf_width_top_mm, 3),
        "kerf_width_bottom_mm": round_float(kerf_width_bottom_mm, 3),
        "taper_mm": round_float(abs(kerf_width_top_mm - kerf_width_bottom_mm), 3),
        "dross_height_max_mm": round_float(dross_height_max_mm, 3),
        "dross_height_mean_mm": round_float(dross_height_max_mm * rng.uniform(0.45, 0.68), 3),
        "roughness_Sa_um": round_float(roughness_sa_um, 3),
        "defect_area_mm2": round_float(defect_area_mm2, 3),
        "manual_comment": manual_comments[failure_case],
    }
    metrics["quality_score"] = score_quality(metrics, scoring_rule)
    return metrics


def simulate_plan(
    plan_path: Path = DEFAULT_PLAN,
    log_path: Path = DEFAULT_LOG,
    summary_path: Path = DEFAULT_SUMMARY,
    seed: int | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    plan = pd.read_csv(plan_path)

    rows: list[dict[str, Any]] = []
    for _, plan_row in plan.iterrows():
        plan_record = plan_row.to_dict()
        quality = simulate_one_episode(plan_record, rng)
        record_episode(plan_record, quality)
        rows.append({**plan_record, **quality})

    log = pd.DataFrame(rows)
    ensure_dir(log_path.parent)
    log.to_csv(log_path, index=False, encoding="utf-8-sig")

    summary_columns = [
        "episode_id",
        "stage",
        "power_kw",
        "speed_m_min",
        "air_pressure_mpa",
        "focus_mm",
        "cut_through",
        "failure_case",
        "quality_score",
        "dross_height_max_mm",
        "roughness_Sa_um",
        "kerf_width_top_mm",
        "taper_mm",
    ]
    log[summary_columns].to_csv(summary_path, index=False, encoding="utf-8-sig")
    return log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate quality data for a cutting plan.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log = simulate_plan(args.plan, args.log, args.summary, args.seed)
    best = log.sort_values("quality_score", ascending=False).iloc[0]
    print(f"Simulated {len(log)} episodes: {args.log}")
    print(
        "Best episode: "
        f"{best['episode_id']} score={best['quality_score']} "
        f"failure_case={best['failure_case']}"
    )


if __name__ == "__main__":
    main()
