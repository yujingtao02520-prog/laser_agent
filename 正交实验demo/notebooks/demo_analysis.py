from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from agent_recommendation import run_recommendation  # noqa: E402
from analyze_orthogonal import analyze_orthogonal  # noqa: E402
from generate_orthogonal_plan import generate_orthogonal_plan  # noqa: E402
from generate_pretest_plan import generate_pretest_plan  # noqa: E402
from simulate_quality_result import simulate_plan  # noqa: E402


def main() -> None:
    config_path = PROJECT_ROOT / "configs" / "experiment_config.yaml"
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    print("Base condition:", config["base_condition"])

    pretest_plan = generate_pretest_plan()
    print("Pretest plan:")
    print(pretest_plan.head())

    orthogonal_plan = generate_orthogonal_plan()
    print("L9 plan:")
    print(orthogonal_plan)

    log = simulate_plan(seed=2026)
    print("Experiment log:")
    print(log[["episode_id", "failure_case", "quality_score"]])

    figure_dir = PROJECT_ROOT / "outputs" / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    score_fig = figure_dir / "quality_score_distribution.png"
    log["quality_score"].plot(kind="bar", figsize=(8, 4), title="Quality Score Distribution")
    plt.xlabel("Run index")
    plt.ylabel("quality_score")
    plt.tight_layout()
    plt.savefig(score_fig, dpi=180)
    plt.close()

    analysis = analyze_orthogonal()
    print("Analysis result:")
    print(analysis.head())

    failure_rows = log.loc[log["failure_case"] != "normal"]
    selected = failure_rows.iloc[0] if not failure_rows.empty else log.sort_values("quality_score").iloc[0]
    recommendation = run_recommendation(selected["episode_id"])
    print("Selected episode:", selected["episode_id"])
    print("Agent recommendation:", recommendation["next_parameters"])


if __name__ == "__main__":
    main()
