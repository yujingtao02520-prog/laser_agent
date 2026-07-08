from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
METADATA_DIR = DATA_DIR / "metadata"
PROCESSED_DATA_DIR = DATA_DIR / "processed_data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
REPORT_DIR = OUTPUT_DIR / "reports"
FIGURE_DIR = OUTPUT_DIR / "figures"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def write_json(path: Path, data: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_experiment_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "experiment_config.yaml")


def load_scoring_rule() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "scoring_rule.yaml")


def factor_levels_from_config(config: dict[str, Any]) -> dict[str, list[float]]:
    factors = config["orthogonal_factors"]
    return {
        "power_kw": factors["A_power_kw"],
        "speed_m_min": factors["B_speed_m_min"],
        "air_pressure_mpa": factors["C_air_pressure_mpa"],
        "focus_mm": factors["D_focus_mm"],
    }


def candidate_action_space(config: dict[str, Any]) -> dict[str, list[float]]:
    return factor_levels_from_config(config)


def round_float(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def quality_band(score: float, cut_through: bool, failure_case: str) -> str:
    if not cut_through:
        return "not_cut_through"
    if failure_case in {"unstable_cut", "incomplete_cut"}:
        return "failed"
    if score >= 85:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "acceptable"
    return "poor"
