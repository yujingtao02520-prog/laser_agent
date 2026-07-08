from typing import Dict, Any, Optional
from . import db

def recommend_parameters(
    material: str,
    thickness: float,
    max_machine_power: float = 6000.0,
    max_machine_pressure: float = 20.0
) -> Dict[str, Any]:
    """
    Retrieves the nearest expert recipe, adjusts it using physical heuristics for thickness deviation,
    validates physical machine constraints, and outputs a confidence score with explanations.
    """
    baseline = db.find_nearest_recipe(material, thickness)
    
    if not baseline:
        # Fallback recipe if material is unknown
        baseline = {
            "material": material,
            "thickness": thickness,
            "laser_power": 2000.0,
            "speed": 2000.0,
            "gas_type": "Air",
            "gas_pressure": 6.0,
            "focus_position": 0.0,
            "nozzle": "2.0",
            "piercing_method": "pulse",
            "kerf_compensation": 0.20,
            "quality_score": 70.0,
            "operator_note": "未找到历史工艺，已使用默认安全参数。"
        }
        is_exact_material = False
    else:
        is_exact_material = True

    # Initial values from baseline
    power = baseline["laser_power"]
    speed = baseline["speed"]
    gas_type = baseline["gas_type"]
    gas_pressure = baseline["gas_pressure"]
    focus = baseline["focus_position"]
    nozzle = baseline["nozzle"]
    piercing = baseline["piercing_method"]
    kerf = baseline["kerf_compensation"]
    
    confidence = 95.0
    reasoning_steps = []
    warnings = []

    # 1. Scaling for thickness deviation
    thickness_ratio = thickness / baseline["thickness"]
    thick_diff_pct = abs(thickness_ratio - 1.0)
    
    if is_exact_material:
        reasoning_steps.append(f"检索到最邻近工艺规程 (ID: {baseline['id']})，对应材质 {material} ({baseline['thickness']}mm)。")
        if thick_diff_pct > 0.01:
            # Scaled thickness rule
            # Power scales with sqrt of thickness ratio, speed scales inversely with thickness ratio
            power_factor = thickness_ratio ** 0.5
            speed_factor = 1.0 / thickness_ratio
            
            power = baseline["laser_power"] * power_factor
            speed = baseline["speed"] * speed_factor
            
            # Linearly scale focus position based on thickness
            # For positive focus (O2 cutting, e.g. Q235): scale linearly with thickness
            # For negative focus (N2 cutting, e.g. SUS304): scale magnitude, preserve sign
            base_focus = baseline["focus_position"]
            if base_focus >= 0:
                focus = base_focus * thickness_ratio
            else:
                focus = -(abs(base_focus) * thickness_ratio)
                
            # Linearly adjust nozzle size
            try:
                base_nozzle = float(baseline["nozzle"])
                nozzle = f"{round(base_nozzle * (thickness_ratio ** 0.3), 1)}"
            except ValueError:
                nozzle = baseline["nozzle"]

            # Kerf compensation scales with thickness
            kerf = baseline["kerf_compensation"] * (thickness_ratio ** 0.7)
            
            confidence -= min(thick_diff_pct * 30.0, 20.0)
            reasoning_steps.append(
                f"针对厚度偏差进行物理缩放 ({baseline['thickness']}mm -> {thickness}mm): "
                f"激光功率乘以 x{power_factor:.2f}, 切割速度乘以 x{speed_factor:.2f}。"
            )
        else:
            reasoning_steps.append(f"板厚与数据库配方完全匹配。")
    else:
        confidence -= 30.0
        reasoning_steps.append(f"警告：未找到关于材质 '{material}' 的数据库记录。已套用通用空气切割方案。")
        warnings.append(f"未找到关于 {material} 的直接匹配工艺，存在高优化风险。")

    # 2. Apply Machine Capping / Limits
    if power > max_machine_power:
        # Power capped: we must scale down the speed proportionally to maintain equivalent energy input
        original_power = power
        power_ratio = max_machine_power / power
        power = max_machine_power
        speed = speed * power_ratio
        confidence -= 10.0
        reasoning_steps.append(
            f"请求功率 ({original_power:.0f}W) 超出了机床最大激光功率限制 ({max_machine_power:.0f}W)。"
            f"功率已限制在最大范围内，并且切割速度下调了 {power_ratio:.2f} 倍以维持等效热输入。"
        )
        warnings.append("已达到机床激光功率极限。下调速度以防切不透。")

    if gas_pressure > max_machine_pressure:
        original_pressure = gas_pressure
        gas_pressure = max_machine_pressure
        confidence -= 5.0
        reasoning_steps.append(
            f"辅助气压 ({original_pressure:.1f} bar) 被限制在机床最大气压 ({max_machine_pressure:.1f} bar) 内。"
        )
        warnings.append("已达到辅助气压上限，熔融吹渣效率可能会受到影响。")

    # 3. Material-specific Expert safety warnings
    mat_upper = material.upper()
    if "COPPER" in mat_upper or "CU" in mat_upper:
        warnings.append("高反射性材质（紫铜）。存在激光回返反射风险。请保持保护镜片清洁并监控温度。")
        reasoning_steps.append("已套用紫铜切割安全曲线：请注意检查保护镜。")
    elif "AL" in mat_upper or "ALUM" in mat_upper:
        warnings.append("高反射性材质（铝合金）。存在回返反射风险。请确保高压氮气流持续喷吹。")
    elif "Q235" in mat_upper:
        # Oxygen cutting specific safety
        if thickness >= 6.0 and speed > 2200:
            warnings.append("厚板氧气切割：过高的速度会触发剧烈的剧化氧化反应。切割速度已被限制在安全范围内。")
            speed = min(speed, 2000.0)

    # Round results to clean values
    power = round(power / 50.0) * 50.0  # round to nearest 50W
    speed = round(speed / 10.0) * 10.0  # round to nearest 10mm/min
    gas_pressure = round(gas_pressure, 1)
    focus = round(focus, 2)
    kerf = round(kerf, 3)

    # Suggest piercing method based on thickness
    if thickness < 3.0:
        piercing = "direct"
    elif thickness < 6.0:
        piercing = "pulse"
    else:
        piercing = "stage"

    return {
        "material": material,
        "thickness": thickness,
        "laser_power": power,
        "speed": speed,
        "gas_type": gas_type,
        "gas_pressure": gas_pressure,
        "focus_position": focus,
        "nozzle": nozzle,
        "piercing_method": piercing,
        "kerf_compensation": kerf,
        "confidence": max(10.0, round(confidence, 1)),
        "reasoning": reasoning_steps,
        "warnings": warnings,
        "source_recipe_id": baseline.get("id") if is_exact_material else None
    }
