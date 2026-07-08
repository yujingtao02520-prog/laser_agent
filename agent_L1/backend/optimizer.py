from typing import Dict, Any, List

def diagnose_and_optimize(
    material: str,
    thickness: float,
    current_power: float,
    current_speed: float,
    current_gas_type: str,
    current_gas_pressure: float,
    current_focus: float,
    quality_report: Dict[str, Any],
    target_recipe: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Diagnoses cutting issues based on the quality report and generates recommendations for the next test cut.
    Suggests safe, small-step corrections inside defined boundaries.
    """
    suggestions = []
    
    # If the plate was not penetrated, we need aggressive corrective action
    if not quality_report.get("penetrated", True):
        # 1. Power increase suggestion (if below maximum machine limits)
        if current_power < target_recipe["laser_power"] * 1.1:
            suggested_power = min(target_recipe["laser_power"], current_power + 200.0)
            power_delta = suggested_power - current_power
            if power_delta > 0:
                suggestions.append({
                    "parameter": "laser_power",
                    "action": "increase",
                    "delta": power_delta,
                    "target_value": suggested_power,
                    "reason": "板材未切透。建议提高激光功率以提供更多的熔化能量。",
                    "risk": "medium",
                    "requires_approval": True
                })

        # 2. Speed decrease suggestion
        suggested_speed = max(target_recipe["speed"] * 0.8, current_speed - 500.0)
        speed_delta = suggested_speed - current_speed
        if speed_delta < 0:
            suggestions.append({
                "parameter": "speed",
                "action": "decrease",
                "delta": speed_delta,
                "target_value": suggested_speed,
                "reason": "板材未切透。建议降低切割速度，给激光留出足够的穿透时间。",
                "risk": "low",
                "requires_approval": False
            })

        # 3. Gas pressure increase suggestion (if pressure is too low)
        if current_gas_pressure < target_recipe["gas_pressure"]:
            suggested_press = min(target_recipe["gas_pressure"], current_gas_pressure + 2.0)
            press_delta = suggested_press - current_gas_pressure
            if press_delta > 0:
                suggestions.append({
                    "parameter": "gas_pressure",
                    "action": "increase",
                    "delta": press_delta,
                    "target_value": suggested_press,
                    "reason": "辅助气压不足，无法有效吹除挂渣。建议提高气压以清空切缝。",
                    "risk": "low",
                    "requires_approval": False
                })
        return suggestions

    # If penetrated, diagnose specific sub-defects (dross, burning, roughness, kerf)
    # Check for dross (slag accumulation)
    dross_score = quality_report.get("dross_score", 100.0)
    if dross_score < 85.0:
        # Check if speed is too fast
        if current_speed > target_recipe["speed"] * 1.05:
            # Recommend slow down
            suggested_speed = round((current_speed * 0.95) / 10.0) * 10.0
            suggestions.append({
                "parameter": "speed",
                "action": "decrease",
                "delta": suggested_speed - current_speed,
                "target_value": suggested_speed,
                "reason": "检测到底部挂渣（粘渣）严重。建议降低 5% 的切割速度，以保证熔渣吹除前有充足的热消融。",
                "risk": "low",
                "requires_approval": False
            })
        
        # Check if focus is wrong (For N2 cutting, focus should be negative/deep; for O2 cutting, focus should be positive/high)
        focus_diff = current_focus - target_recipe["focus_position"]
        if abs(focus_diff) > 0.2:
            suggested_focus = current_focus - (0.5 * focus_diff)  # move halfway back to target
            suggested_focus = round(suggested_focus, 2)
            suggestions.append({
                "parameter": "focus_position",
                "action": "decrease" if focus_diff > 0 else "increase",
                "delta": suggested_focus - current_focus,
                "target_value": suggested_focus,
                "reason": f"焦点位置偏离（实际：{current_focus}mm，基准：{target_recipe['focus_position']}mm）导致光斑发散。建议调节焦点更靠近标准值。",
                "risk": "low",
                "requires_approval": False
            })

        # Check if gas pressure is low
        if current_gas_pressure < target_recipe["gas_pressure"] * 0.95:
            suggested_press = min(target_recipe["gas_pressure"], current_gas_pressure + 1.0)
            suggested_press = round(suggested_press, 1)
            suggestions.append({
                "parameter": "gas_pressure",
                "action": "increase",
                "delta": suggested_press - current_gas_pressure,
                "target_value": suggested_press,
                "reason": "吹气压力偏低导致熔融金属挂渣。建议提高辅助气压 +1.0 bar。",
                "risk": "low",
                "requires_approval": False
            })

    # Check for burning (melt edge, overburn)
    burning_score = quality_report.get("burning_score", 100.0)
    if burning_score < 85.0:
        # Check if speed is too slow
        if current_speed < target_recipe["speed"] * 0.95:
            suggested_speed = round((current_speed * 1.05) / 10.0) * 10.0
            suggestions.append({
                "parameter": "speed",
                "action": "increase",
                "delta": suggested_speed - current_speed,
                "target_value": suggested_speed,
                "reason": "由于热量累积过多，切口边缘出现熔边和过烧。建议提高 5% 的速度以减少热积聚。",
                "risk": "low",
                "requires_approval": False
            })
            
        # Check if power is too high
        if current_power > target_recipe["laser_power"] * 1.05:
            suggested_power = round((current_power * 0.95) / 50.0) * 50.0
            suggestions.append({
                "parameter": "laser_power",
                "action": "decrease",
                "delta": suggested_power - current_power,
                "target_value": suggested_power,
                "reason": "激光输入功率过高。建议调低 5% 的功率，以防拐角烧蚀。",
                "risk": "low",
                "requires_approval": False
            })

        # For Q235 (O2): pressure too high causes excessive oxidation reaction
        if "Q235" in material.upper() and current_gas_pressure > target_recipe["gas_pressure"] * 1.05:
            suggested_press = round(current_gas_pressure - 0.1, 1)
            suggestions.append({
                "parameter": "gas_pressure",
                "action": "decrease",
                "delta": suggested_press - current_gas_pressure,
                "target_value": suggested_press,
                "reason": "过高的氧气压力会加速碳钢剧烈燃烧。建议调低气压 -0.1 bar。",
                "risk": "low",
                "requires_approval": False
            })

    # Check for roughness (striations)
    roughness_score = quality_report.get("roughness_score", 100.0)
    if roughness_score < 85.0 and not suggestions:  # only suggest if we haven't already made speed/focus corrections
        focus_diff = current_focus - target_recipe["focus_position"]
        if abs(focus_diff) > 0.1:
            suggested_focus = target_recipe["focus_position"]
            suggestions.append({
                "parameter": "focus_position",
                "action": "set",
                "delta": suggested_focus - current_focus,
                "target_value": suggested_focus,
                "reason": f"断面粗糙度高。建议将焦点位置重置为专家基准值 {suggested_focus}mm。",
                "risk": "low",
                "requires_approval": False
            })

    # Check for kerf width deviation
    dimension_score = quality_report.get("dimension_score", 100.0)
    if dimension_score < 80.0 and not suggestions:
        # Kerf too wide -> lower power or increase speed
        if quality_report.get("kerf_width", 0.3) > target_recipe["kerf_compensation"] * 2.0:
            if current_power > target_recipe["laser_power"]:
                suggested_power = target_recipe["laser_power"]
                suggestions.append({
                    "parameter": "laser_power",
                    "action": "decrease",
                    "delta": suggested_power - current_power,
                    "target_value": suggested_power,
                    "reason": "切缝过宽。建议调低激光功率至标准值，以收窄光束熔化半径。",
                    "risk": "low",
                    "requires_approval": False
                })
            else:
                suggested_speed = round((current_speed * 1.03) / 10.0) * 10.0
                suggestions.append({
                    "parameter": "speed",
                    "action": "increase",
                    "delta": suggested_speed - current_speed,
                    "target_value": suggested_speed,
                    "reason": "切缝过宽。建议适当提高切割速度以缩短热停留时间。",
                    "risk": "low",
                    "requires_approval": False
                })

    return suggestions
