from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from utils import (
    FIGURE_DIR,
    METADATA_DIR,
    REPORT_DIR,
    ensure_dir,
    factor_levels_from_config,
    load_experiment_config,
    load_scoring_rule,
)


DEFAULT_LOG = METADATA_DIR / "experiment_log.csv"
DEFAULT_REPORT = REPORT_DIR / "orthogonal_analysis_report.md"
DEFAULT_RESULT = REPORT_DIR / "orthogonal_analysis_result.csv"

METRICS = [
    "quality_score",
    "dross_height_max_mm",
    "roughness_Sa_um",
    "kerf_width_top_mm",
    "taper_mm",
]

FACTOR_LABELS = {
    "power_kw": "A_power_kw",
    "speed_m_min": "B_speed_m_min",
    "air_pressure_mpa": "C_air_pressure_mpa",
    "focus_mm": "D_focus_mm",
}


def metric_objective(metric: str) -> str:
    if metric == "quality_score":
        return "maximize"
    if metric == "kerf_width_top_mm":
        return "target"
    return "minimize"


def select_best_level(metric: str, means: pd.Series, target_kerf: float) -> float:
    objective = metric_objective(metric)
    if objective == "maximize":
        return means.idxmax()
    if objective == "target":
        return (means - target_kerf).abs().idxmin()
    return means.idxmin()


def analyze_metric(
    log: pd.DataFrame,
    metric: str,
    factor_levels: dict[str, list[float]],
    target_kerf: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranges: dict[str, float] = {}
    best_levels: dict[str, float] = {}

    for factor, levels in factor_levels.items():
        means = log.groupby(factor)[metric].mean().reindex(levels)
        level_range = float(means.max() - means.min())
        ranges[factor] = level_range
        best_level = select_best_level(metric, means, target_kerf)
        best_levels[factor] = best_level
        for level, mean_value in means.items():
            rows.append(
                {
                    "metric": metric,
                    "factor": factor,
                    "factor_label": FACTOR_LABELS[factor],
                    "level": level,
                    "K_mean": round(float(mean_value), 4),
                    "R_range": round(level_range, 4),
                    "objective": metric_objective(metric),
                    "is_best_level": bool(level == best_level),
                }
            )

    ranking = sorted(ranges.items(), key=lambda item: item[1], reverse=True)
    rank_lookup = {factor: rank for rank, (factor, _) in enumerate(ranking, start=1)}
    result = pd.DataFrame(rows)
    result["factor_rank"] = result["factor"].map(rank_lookup)

    summary = {
        "metric": metric,
        "objective": metric_objective(metric),
        "ranges": ranges,
        "ranking": ranking,
        "best_levels": best_levels,
    }
    return result, summary


def plot_main_effect(log: pd.DataFrame, metric: str, output_path: Path) -> None:
    factor_order = ["power_kw", "speed_m_min", "air_pressure_mpa", "focus_mm"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    axes_flat = axes.ravel()

    for axis, factor in zip(axes_flat, factor_order):
        means = log.groupby(factor)[metric].mean().sort_index()
        axis.plot(means.index, means.values, marker="o", linewidth=2)
        axis.set_title(FACTOR_LABELS[factor])
        axis.set_xlabel(factor)
        axis.set_ylabel(metric)
        axis.grid(True, alpha=0.3)

    fig.suptitle(f"Main Effects - {metric}")
    ensure_dir(output_path.parent)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def build_report(
    log: pd.DataFrame,
    summaries: list[dict[str, Any]],
    output_path: Path,
) -> None:
    best_observed = log.sort_values("quality_score", ascending=False).iloc[0]
    lines = [
        "# Orthogonal Analysis Report",
        "",
        "## Dataset",
        f"- Episodes: {len(log)}",
        f"- Best observed episode: {best_observed['episode_id']}",
        f"- Best observed quality_score: {best_observed['quality_score']}",
        f"- Best observed parameters: power={best_observed['power_kw']} kW, "
        f"speed={best_observed['speed_m_min']} m/min, "
        f"pressure={best_observed['air_pressure_mpa']} MPa, "
        f"focus={best_observed['focus_mm']} mm",
        "",
    ]

    for summary in summaries:
        ranking_text = ", ".join(
            f"{FACTOR_LABELS[factor]}(R={range_value:.3f})"
            for factor, range_value in summary["ranking"]
        )
        best_combo = ", ".join(
            f"{FACTOR_LABELS[factor]}={level}" for factor, level in summary["best_levels"].items()
        )
        lines.extend(
            [
                f"## Metric: {summary['metric']}",
                f"- Objective: {summary['objective']}",
                f"- Influence ranking: {ranking_text}",
                f"- Better level combination: {best_combo}",
                "",
            ]
        )

    ensure_dir(output_path.parent)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def analyze_orthogonal(
    log_path: Path = DEFAULT_LOG,
    result_path: Path = DEFAULT_RESULT,
    report_path: Path = DEFAULT_REPORT,
) -> pd.DataFrame:
    log = pd.read_csv(log_path)
    config = load_experiment_config()
    scoring_rule = load_scoring_rule()
    factor_levels = factor_levels_from_config(config)
    target_kerf = float(scoring_rule["target_kerf_width_mm"])

    all_results: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    for metric in METRICS:
        result, summary = analyze_metric(log, metric, factor_levels, target_kerf)
        all_results.append(result)
        summaries.append(summary)

    analysis_result = pd.concat(all_results, ignore_index=True)
    ensure_dir(result_path.parent)
    analysis_result.to_csv(result_path, index=False, encoding="utf-8-sig")
    build_report(log, summaries, report_path)

    plot_main_effect(log, "quality_score", FIGURE_DIR / "main_effect_quality_score.png")
    plot_main_effect(log, "dross_height_max_mm", FIGURE_DIR / "main_effect_dross_height.png")
    plot_main_effect(log, "roughness_Sa_um", FIGURE_DIR / "main_effect_roughness.png")
    return analysis_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run range analysis for L9 results.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = analyze_orthogonal(args.log, args.result, args.report)
    print(f"Saved orthogonal analysis rows={len(result)}: {args.result}")
    print(f"Saved report: {args.report}")


if __name__ == "__main__":
    main()
