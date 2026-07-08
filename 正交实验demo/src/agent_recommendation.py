from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from utils import PROCESSED_DATA_DIR, REPORT_DIR, ensure_dir, read_json, round_float, write_json


def next_higher(values: list[float], current: float) -> float:
    higher = [value for value in values if value > current]
    return min(higher) if higher else current


def next_lower(values: list[float], current: float) -> float:
    lower = [value for value in values if value < current]
    return max(lower) if lower else current


def nearest_allowed(values: list[float], current: float) -> float:
    return min(values, key=lambda value: abs(value - current))


def base_parameters(process: dict[str, Any]) -> dict[str, float]:
    return {
        "power_kw": float(process["laser_power_kw"]),
        "speed_m_min": float(process["cutting_speed_m_min"]),
        "air_pressure_mpa": float(process["air_pressure_mpa"]),
        "focus_mm": float(process["focus_position_mm"]),
    }


def make_local_validation_plan(next_params: dict[str, float], action_space: dict[str, list[float]]) -> list[dict[str, float]]:
    lower_speed = next_lower(action_space["speed_m_min"], next_params["speed_m_min"])
    higher_speed = next_higher(action_space["speed_m_min"], next_params["speed_m_min"])
    lower_pressure = next_lower(action_space["air_pressure_mpa"], next_params["air_pressure_mpa"])
    higher_pressure = next_higher(action_space["air_pressure_mpa"], next_params["air_pressure_mpa"])

    candidates = [
        next_params,
        {**next_params, "speed_m_min": lower_speed},
        {**next_params, "speed_m_min": higher_speed, "air_pressure_mpa": higher_pressure},
        {**next_params, "air_pressure_mpa": lower_pressure},
    ]
    unique: list[dict[str, float]] = []
    seen: set[tuple[tuple[str, float], ...]] = set()
    for candidate in candidates:
        normalized = {key: round_float(value, 3) for key, value in candidate.items()}
        key = tuple(sorted(normalized.items()))
        if key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def recommend_from_agent_input(agent_input: dict[str, Any]) -> dict[str, Any]:
    process = agent_input["process_parameters"]
    observation = agent_input["quality_observation"]
    action_space = agent_input["candidate_action_space"]
    failure_cases = agent_input.get("failure_case") or [observation["failure_case"]]
    failure_case = failure_cases[0]
    current = base_parameters(process)
    next_params = current.copy()
    changes: list[str] = []
    rationale: list[str] = []

    if failure_case == "incomplete_cut":
        next_params["power_kw"] = next_higher(action_space["power_kw"], current["power_kw"])
        next_params["speed_m_min"] = next_lower(action_space["speed_m_min"], current["speed_m_min"])
        next_params["focus_mm"] = next_lower(action_space["focus_mm"], current["focus_mm"])
        changes.extend(["increase power", "reduce speed", "move focus downward"])
        rationale.append("Incomplete cutting indicates insufficient effective energy density.")
    elif failure_case == "dross":
        next_params["air_pressure_mpa"] = next_higher(
            action_space["air_pressure_mpa"], current["air_pressure_mpa"]
        )
        next_params["speed_m_min"] = next_lower(action_space["speed_m_min"], current["speed_m_min"])
        changes.extend(["increase air pressure", "slightly reduce speed", "inspect nozzle height"])
        rationale.append("High dross suggests melt evacuation is not strong or stable enough.")
    elif failure_case == "overburn":
        next_params["power_kw"] = next_lower(action_space["power_kw"], current["power_kw"])
        next_params["speed_m_min"] = next_higher(action_space["speed_m_min"], current["speed_m_min"])
        changes.extend(["reduce power", "increase speed"])
        rationale.append("Overburn is consistent with excessive line energy.")
    elif failure_case == "overcut":
        next_params["power_kw"] = next_lower(action_space["power_kw"], current["power_kw"])
        next_params["speed_m_min"] = next_higher(action_space["speed_m_min"], current["speed_m_min"])
        next_params["focus_mm"] = nearest_allowed(action_space["focus_mm"], current["focus_mm"])
        changes.extend(["reduce power", "increase speed", "verify focus"])
        rationale.append("Overcut means kerf width is larger than the benchmark target.")
    elif failure_case == "rough_surface":
        next_params["focus_mm"] = nearest_allowed(action_space["focus_mm"], -9.0)
        next_params["speed_m_min"] = nearest_allowed(action_space["speed_m_min"], current["speed_m_min"])
        next_params["air_pressure_mpa"] = nearest_allowed(action_space["air_pressure_mpa"], 1.5)
        changes.extend(["refine focus near -9 mm", "run local speed-pressure sweep"])
        rationale.append("Roughness is sensitive to focus position, speed, and gas flow stability.")
    elif failure_case == "unstable_cut":
        next_params["air_pressure_mpa"] = nearest_allowed(action_space["air_pressure_mpa"], 1.5)
        next_params["speed_m_min"] = next_lower(action_space["speed_m_min"], current["speed_m_min"])
        changes.extend(["return pressure toward 1.5 MPa", "reduce speed for stability"])
        rationale.append("Unstable cut points to an imbalanced pressure and energy window.")
    else:
        changes.extend(["repeat around current parameters", "run small-range confirmation"])
        rationale.append("The current episode is normal; next step is robustness confirmation.")

    next_params = {key: round_float(value, 3) for key, value in next_params.items()}
    validation_plan = make_local_validation_plan(next_params, action_space)
    recommendation = {
        "episode_id": process["episode_id"],
        "failure_case": failure_case,
        "current_parameters": {key: round_float(value, 3) for key, value in current.items()},
        "quality_observation": {
            "quality_score": observation["quality_score"],
            "overall_quality": observation["overall_quality"],
            "dross_height_max_mm": observation["dross_height_max_mm"],
            "roughness_Sa_um": observation["roughness_Sa_um"],
            "kerf_width_top_mm": observation["kerf_width_top_mm"],
            "taper_mm": observation["taper_mm"],
        },
        "recommended_changes": changes,
        "next_parameters": next_params,
        "local_validation_plan": validation_plan,
        "rationale": rationale,
    }
    return recommendation


def write_markdown(recommendation: dict[str, Any], output_path: Path) -> None:
    lines = [
        f"# Agent Recommendation - {recommendation['episode_id']}",
        "",
        f"- Failure case: {recommendation['failure_case']}",
        f"- Current quality score: {recommendation['quality_observation']['quality_score']}",
        "",
        "## Recommended Changes",
    ]
    lines.extend(f"- {change}" for change in recommendation["recommended_changes"])
    lines.extend(["", "## Next Parameters"])
    lines.extend(f"- {key}: {value}" for key, value in recommendation["next_parameters"].items())
    lines.extend(["", "## Rationale"])
    lines.extend(f"- {item}" for item in recommendation["rationale"])
    lines.extend(["", "## Local Validation Plan"])
    for index, candidate in enumerate(recommendation["local_validation_plan"], start=1):
        param_text = ", ".join(f"{key}={value}" for key, value in candidate.items())
        lines.append(f"{index}. {param_text}")
    ensure_dir(output_path.parent)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_recommendation(
    episode_id: str,
    processed_root: Path = PROCESSED_DATA_DIR,
    report_root: Path = REPORT_DIR,
) -> dict[str, Any]:
    agent_input_path = processed_root / episode_id / "agent_input.json"
    if not agent_input_path.exists():
        raise FileNotFoundError(f"Missing agent input: {agent_input_path}")
    agent_input = read_json(agent_input_path)
    recommendation = recommend_from_agent_input(agent_input)

    json_path = report_root / f"agent_recommendation_{episode_id}.json"
    md_path = report_root / f"agent_recommendation_{episode_id}.md"
    write_json(json_path, recommendation)
    write_markdown(recommendation, md_path)
    return recommendation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend next cutting parameters from an episode.")
    parser.add_argument("--episode_id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recommendation = run_recommendation(args.episode_id)
    print(f"Saved recommendation for {recommendation['episode_id']}")
    print(f"Next parameters: {recommendation['next_parameters']}")


if __name__ == "__main__":
    main()
