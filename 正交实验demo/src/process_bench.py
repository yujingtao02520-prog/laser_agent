from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from agent_recommendation import run_recommendation
from analyze_orthogonal import analyze_orthogonal
from generate_orthogonal_plan import generate_orthogonal_plan
from generate_pretest_plan import generate_pretest_plan
from simulate_quality_result import simulate_plan
from utils import CONFIG_DIR, PROJECT_ROOT, ensure_dir, load_yaml, round_float, write_json


BENCH_CONFIG_PATH = CONFIG_DIR / "bench_config.yaml"


@dataclass(frozen=True)
class BenchArtifacts:
    pretest_plan: Path
    orthogonal_plan: Path
    experiment_log: Path
    quality_summary: Path
    analysis_csv: Path
    analysis_report: Path
    recommendation_json: Path
    recommendation_md: Path
    bench_summary_json: Path
    bench_summary_md: Path


def load_bench_config() -> dict[str, Any]:
    return load_yaml(BENCH_CONFIG_PATH)


def list_benches() -> dict[str, Any]:
    return load_bench_config()["benches"]


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def select_recommendation_episode(log: pd.DataFrame, strategy: str) -> str:
    if strategy == "first_failure":
        failures = log.loc[log["failure_case"] != "normal"]
        if not failures.empty:
            return str(failures.iloc[0]["episode_id"])
    if strategy == "worst_score":
        return str(log.sort_values("quality_score", ascending=True).iloc[0]["episode_id"])
    if strategy == "best_score":
        return str(log.sort_values("quality_score", ascending=False).iloc[0]["episode_id"])
    return str(log.iloc[0]["episode_id"])


def summarize_bench(
    bench_id: str,
    bench: dict[str, Any],
    log: pd.DataFrame,
    recommendation: dict[str, Any],
    artifacts: BenchArtifacts,
) -> dict[str, Any]:
    best = log.sort_values("quality_score", ascending=False).iloc[0]
    worst = log.sort_values("quality_score", ascending=True).iloc[0]
    target_score = float(bench.get("target_score", 75))
    pass_rate = float((log["quality_score"] >= target_score).mean())

    return {
        "bench_id": bench_id,
        "bench_name": bench["name"],
        "description": bench["description"].strip(),
        "condition": {
            "material": bench["material"],
            "thickness_mm": bench["thickness_mm"],
            "assist_gas": bench["assist_gas"],
            "plan": bench["plan"],
        },
        "scoring_metric": bench["scoring_metric"],
        "target_score": target_score,
        "episode_count": int(len(log)),
        "pass_rate": round_float(pass_rate, 3),
        "failure_distribution": log["failure_case"].value_counts().to_dict(),
        "best_episode": {
            "episode_id": best["episode_id"],
            "quality_score": round_float(best["quality_score"], 2),
            "failure_case": best["failure_case"],
            "parameters": {
                "power_kw": round_float(best["power_kw"], 3),
                "speed_m_min": round_float(best["speed_m_min"], 3),
                "air_pressure_mpa": round_float(best["air_pressure_mpa"], 3),
                "focus_mm": round_float(best["focus_mm"], 3),
            },
        },
        "worst_episode": {
            "episode_id": worst["episode_id"],
            "quality_score": round_float(worst["quality_score"], 2),
            "failure_case": worst["failure_case"],
        },
        "agent_recommendation": {
            "episode_id": recommendation["episode_id"],
            "failure_case": recommendation["failure_case"],
            "next_parameters": recommendation["next_parameters"],
            "recommended_changes": recommendation["recommended_changes"],
        },
        "artifacts": {
            key: str(value.relative_to(PROJECT_ROOT))
            for key, value in artifacts.__dict__.items()
        },
    }


def write_summary_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        f"# Process Experiment Bench - {summary['bench_id']}",
        "",
        summary["description"],
        "",
        "## Condition",
        f"- Material: {summary['condition']['material']}",
        f"- Thickness: {summary['condition']['thickness_mm']} mm",
        f"- Assist gas: {summary['condition']['assist_gas']}",
        f"- Plan: {summary['condition']['plan']}",
        "",
        "## Scoreboard",
        f"- Episodes: {summary['episode_count']}",
        f"- Target score: {summary['target_score']}",
        f"- Pass rate: {summary['pass_rate']}",
        f"- Failure distribution: {summary['failure_distribution']}",
        "",
        "## Best Episode",
        f"- Episode: {summary['best_episode']['episode_id']}",
        f"- Quality score: {summary['best_episode']['quality_score']}",
        f"- Failure case: {summary['best_episode']['failure_case']}",
        f"- Parameters: {summary['best_episode']['parameters']}",
        "",
        "## Agent Recommendation",
        f"- Episode: {summary['agent_recommendation']['episode_id']}",
        f"- Failure case: {summary['agent_recommendation']['failure_case']}",
        f"- Next parameters: {summary['agent_recommendation']['next_parameters']}",
        f"- Recommended changes: {summary['agent_recommendation']['recommended_changes']}",
        "",
        "## Artifacts",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in summary["artifacts"].items())
    ensure_dir(output_path.parent)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_process_bench(bench_id: str = "cs30_air_l9", seed: int | None = None) -> dict[str, Any]:
    benches = list_benches()
    if bench_id not in benches:
        known = ", ".join(sorted(benches))
        raise ValueError(f"Unknown bench_id={bench_id}. Known benches: {known}")

    bench = benches[bench_id]
    run_seed = seed if seed is not None else int(bench.get("seed", 2026))

    generate_pretest_plan()
    generate_orthogonal_plan()
    log = simulate_plan(seed=run_seed)
    analysis = analyze_orthogonal()
    if analysis.empty:
        raise RuntimeError("Orthogonal analysis returned no rows.")

    strategy = bench.get("recommendation_episode_strategy", "first_failure")
    recommendation_episode_id = select_recommendation_episode(log, strategy)
    recommendation = run_recommendation(recommendation_episode_id)

    summary_json = resolve_project_path(bench["outputs"]["summary_json"])
    summary_md = resolve_project_path(bench["outputs"]["summary_md"])
    artifacts = BenchArtifacts(
        pretest_plan=PROJECT_ROOT / "data" / "metadata" / "pretest_plan.csv",
        orthogonal_plan=PROJECT_ROOT / "data" / "metadata" / "orthogonal_plan_L9.csv",
        experiment_log=PROJECT_ROOT / "data" / "metadata" / "experiment_log.csv",
        quality_summary=PROJECT_ROOT / "data" / "metadata" / "quality_summary.csv",
        analysis_csv=PROJECT_ROOT / "outputs" / "reports" / "orthogonal_analysis_result.csv",
        analysis_report=PROJECT_ROOT / "outputs" / "reports" / "orthogonal_analysis_report.md",
        recommendation_json=PROJECT_ROOT
        / "outputs"
        / "reports"
        / f"agent_recommendation_{recommendation_episode_id}.json",
        recommendation_md=PROJECT_ROOT
        / "outputs"
        / "reports"
        / f"agent_recommendation_{recommendation_episode_id}.md",
        bench_summary_json=summary_json,
        bench_summary_md=summary_md,
    )

    summary = summarize_bench(bench_id, bench, log, recommendation, artifacts)
    write_json(summary_json, summary)
    write_summary_markdown(summary, summary_md)
    return summary
