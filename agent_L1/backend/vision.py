import random
from typing import Dict, Any, List

def run_precut_inspection(material: str, thickness: float) -> Dict[str, Any]:
    """
    Simulates a 2D camera scanning the board surface and a 3D sensor measuring sheet flatness.
    """
    # Seed or generate semi-stable mock conditions based on material
    mat_upper = material.upper()
    
    if "Q235" in mat_upper:
        rust_level = "medium"
        contamination = "none"
        max_warp = 1.4  # mm (relatively high for hot-rolled steel)
        flatness_profile = [0.2, 0.5, 0.8, 1.2, 1.4, 1.1, 0.8, 0.3, 0.1]
        surface_notes = "中心区域检测到氧化皮和轻微锈蚀。板材翘曲度超出 1.0mm 限制。"
    elif "304" in mat_upper or "SUS" in mat_upper:
        rust_level = "none"
        contamination = "oil_spot"
        max_warp = 0.4  # mm (cold-rolled stainless is usually flat)
        flatness_profile = [0.1, 0.2, 0.3, 0.4, 0.3, 0.2, 0.1, 0.1, 0.0]
        surface_notes = "表面可见保护膜残留和润滑油斑。平整度在正常允许误差范围内。"
    elif "AL" in mat_upper or "ALUM" in mat_upper:
        rust_level = "none"
        contamination = "scratches"
        max_warp = 0.8  # mm
        flatness_profile = [0.1, 0.3, 0.6, 0.8, 0.7, 0.5, 0.3, 0.2, 0.1]
        surface_notes = "检测到轻微表面划痕。无氧化皮及油污风险。"
    else:
        rust_level = "none"
        contamination = "none"
        max_warp = 0.3  # mm
        flatness_profile = [0.0, 0.1, 0.2, 0.3, 0.2, 0.1, 0.0, 0.0, 0.0]
        surface_notes = "板材表面干净、平整。"

    # Generate warnings
    warnings = []
    if max_warp > 1.0:
        warnings.append({
            "sensor": "3D Keyence Profiler",
            "type": "plate_warp",
            "severity": "high",
            "message": f"板材最大翘曲 ({max_warp}mm) 超过安全限制 (1.0mm)。存在焦点偏移或喷嘴碰撞风险！建议检查夹具或开启随动高度跟踪功能。"
        })
    if rust_level in ["medium", "high"]:
        warnings.append({
            "sensor": "2D High-Res Vision",
            "type": "rust_scale",
            "severity": "medium",
            "message": f"表面生锈程度为 {rust_level}。氧化铁对激光能量的吸收具有不可预测性，可能导致熔渣飞溅或切不透。"
        })
    if contamination == "oil_spot":
        warnings.append({
            "sensor": "2D High-Res Vision",
            "type": "contamination",
            "severity": "low",
            "message": "表面检测到油污。高温可能会使油脂燃烧，留下炭黑沉积并导致边缘变色。"
        })

    return {
        "rust_level": rust_level,
        "contamination": contamination,
        "max_warp": max_warp,
        "flatness_profile": flatness_profile,
        "surface_notes": surface_notes,
        "warnings": warnings,
        "ready_to_cut": len([w for w in warnings if w["severity"] == "high"]) == 0
    }

def run_postcut_inspection(
    material: str,
    thickness: float,
    laser_power: float,
    speed: float,
    gas_type: str,
    gas_pressure: float,
    focus_position: float,
    target: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulates visual evaluation of the cutting result.
    Calculates sub-scores and detects defects (unpenetrated, bottom dross, burning, kerf, roughness)
    based on the deviation of current parameters from the expert target parameters.
    """
    # 1. Base check: Gas type mismatch is catastrophic
    if gas_type.upper() != target["gas_type"].upper():
        return {
            "penetrated": False,
            "quality_score": 10.0,
            "penetration_score": 0.0,
            "dross_score": 10.0,
            "burning_score": 20.0,
            "dimension_score": 10.0,
            "roughness_score": 10.0,
            "dross_height": 3.0,  # mm (massive dross or failure)
            "burning_level": "severe",
            "kerf_width": 0.8,
            "roughness_ra": 25.0,  # um
            "defects_2d": [{"x": 150, "y": 150, "type": "gas_mismatch", "severity": "critical"}],
            "visual_summary": f"严重失效：辅助气体类型不匹配。标准推荐 {target['gas_type']}，但实际使用了 {gas_type}。"
        }

    # Helper: calculate percentage deviation
    def p_dev(curr, tgt):
        return (curr - tgt) / tgt if tgt != 0 else 0

    power_dev = p_dev(laser_power, target["laser_power"])
    speed_dev = p_dev(speed, target["speed"])
    press_dev = p_dev(gas_pressure, target["gas_pressure"])
    focus_dev = focus_position - target["focus_position"]  # absolute deviation in mm

    # 2. Determine penetration
    penetrated = True
    penetration_factor = (laser_power / target["laser_power"]) * (target["speed"] / speed)
    if "Q235" in material.upper():
        o2_pressure_factor = gas_pressure / target["gas_pressure"] if target["gas_pressure"] > 0 else 1.0
        if penetration_factor < 0.70 or speed_dev > 0.40 or o2_pressure_factor < 0.40:
            penetrated = False
    else:
        pressure_factor = gas_pressure / target["gas_pressure"] if target["gas_pressure"] > 0 else 1.0
        if penetration_factor < 0.72 or pressure_factor < 0.65 or speed_dev > 0.35:
            penetrated = False

    if not penetrated:
        return {
            "penetrated": False,
            "quality_score": 15.0,
            "penetration_score": 0.0,
            "dross_score": 20.0,
            "burning_score": 30.0,
            "dimension_score": 20.0,
            "roughness_score": 10.0,
            "dross_height": 2.5,
            "burning_level": "none",
            "kerf_width": 0.1,  # incomplete kerf
            "roughness_ra": 30.0,
            "defects_2d": [{"x": 100, "y": 80, "type": "incomplete_penetration", "severity": "high"}],
            "visual_summary": "未切透：切割断面未完全分离。激光功率过低、速度过慢、焦点偏差过大或辅助气体流量不足。"
        }

    # 3. Calculate Dross Score (底部挂渣)
    # Causes: speed too fast, pressure too low, focus too high (for N2) or too low (for O2)
    dross_height = 0.05  # base normal dross (mm)
    
    # Speed effect: faster speed -> more dross
    if speed_dev > 0.0:
        dross_height += speed_dev * 1.5
    # Pressure effect: lower pressure -> more dross
    if press_dev < 0.0:
        dross_height += abs(press_dev) * 2.0
    # Focus effect: deviating from ideal focus increases dross
    dross_height += abs(focus_dev) * 0.8

    # Cap dross height at 2.0mm
    dross_height = min(dross_height, 2.0)
    
    # Dross score conversion: 0.05mm -> 100, >= 1.5mm -> 0
    dross_score = max(0.0, 100.0 - (dross_height - 0.05) * 65.0)

    # 4. Calculate Burning Score (过烧/烧边)
    # Causes: speed too slow (excess heat), power too high, gas pressure too high (for O2)
    burning_index = 0.0  # 0 to 10
    
    if "Q235" in material.upper():
        # Carbon steel with O2 is highly sensitive to slow speed (overburn) and high pressure (runaway combustion)
        if speed_dev < -0.1:
            burning_index += abs(speed_dev) * 20
        if power_dev > 0.15:
            burning_index += power_dev * 10
        if press_dev > 0.15:
            burning_index += press_dev * 12
    else:
        # Stainless/Alu/Copper: overburn is less severe but happens at very low speeds or extremely high power
        if speed_dev < -0.2:
            burning_index += abs(speed_dev) * 10
        if power_dev > 0.25:
            burning_index += power_dev * 5

    # Focus position can also affect burning at corners
    if abs(focus_dev) > 1.5:
        burning_index += abs(focus_dev) * 1.0

    burning_index = min(burning_index, 10.0)
    burning_score = max(0.0, 100.0 - burning_index * 10.0)
    
    if burning_index < 2.0:
        burning_level = "none"
    elif burning_index < 5.0:
        burning_level = "light"
    elif burning_index < 8.0:
        burning_level = "moderate"
    else:
        burning_level = "severe"

    # 5. Dimension / Kerf Width Score
    # Kerf width is wider if power is higher, speed is lower, or focus is higher (out of metal)
    ideal_kerf = target["kerf_compensation"] * 2.0
    if ideal_kerf == 0:
        ideal_kerf = 0.35  # default
        
    kerf_width = ideal_kerf
    if power_dev > 0:
        kerf_width += power_dev * 0.1
    if speed_dev < 0:
        kerf_width += abs(speed_dev) * 0.15
    kerf_width += abs(focus_dev) * 0.05
    
    # Kerf width limits
    kerf_width = max(0.1, min(kerf_width, 1.0))
    kerf_dev = abs(kerf_width - ideal_kerf)
    dimension_score = max(0.0, 100.0 - (kerf_dev / ideal_kerf) * 150.0)

    # 6. Roughness Score (断面粗糙度 Ra)
    # Roughness increases if focus is off, speed is wrong, or gas pressure is low
    base_ra = 3.0 + thickness * 0.5  # default base roughness
    roughness_ra = base_ra
    
    # Focus position offset is the biggest driver of roughness
    roughness_ra += (abs(focus_dev) ** 2) * 5.0
    if speed_dev > 0.1 or speed_dev < -0.1:
        roughness_ra += abs(speed_dev) * 8.0
    if press_dev < -0.1:
        roughness_ra += abs(press_dev) * 10.0

    # Roughness score: Ra = base_ra -> 100, Ra >= base_ra + 15 -> 30
    roughness_score = max(0.0, 100.0 - (roughness_ra - base_ra) * 4.5)

    # 7. Overall Score Calculation (using weights from phase 2)
    # penetration (30%), dross (25%), burning (15%), dimension (20%), roughness (10%)
    overall_score = (
        100.0 * 0.3 + 
        dross_score * 0.25 + 
        burning_score * 0.15 + 
        dimension_score * 0.20 + 
        roughness_score * 0.10
    )
    overall_score = round(overall_score, 1)

    # 8. Generate 2D visual defect coordinates
    defects_2d = []
    if dross_score < 80:
        defects_2d.append({
            "x": 120, "y": 280, 
            "type": "bottom_dross", 
            "severity": "medium" if dross_score > 50 else "high",
            "message": f"Bottom dross detected, avg height {dross_height:.2f}mm"
        })
    if burning_score < 80:
        defects_2d.append({
            "x": 250, "y": 50, 
            "type": "corner_burn", 
            "severity": "medium" if burning_score > 50 else "high",
            "message": f"Overburn at corner profile, level: {burning_level}"
        })
    if dimension_score < 75:
        defects_2d.append({
            "x": 50, "y": 150, 
            "type": "kerf_error", 
            "severity": "medium",
            "message": f"Kerf width {kerf_width:.3f}mm exceeds tolerance"
        })
    if roughness_score < 75:
        defects_2d.append({
            "x": 180, "y": 200, 
            "type": "rough_surface", 
            "severity": "low",
            "message": f"High section roughness Ra {roughness_ra:.1f}um"
        })

    # Summary
    summary_parts = []
    dross_val = dross_height
    burn_lvl = burning_level
    rough_val = roughness_ra - base_ra
    
    if overall_score >= 90.0:
        summary_parts.append("切口质量极佳，工艺参数已处于最优状态。")
    else:
        summary_parts.append(f"切口质量尚不理想 (评分: {overall_score})。")
        if dross_val > 0.5:
            summary_parts.append("检测到下边缘有显著挂渣（粘渣）堆积。")
        if burn_lvl in ["moderate", "severe"]:
            summary_parts.append("观测到边缘过烧或热过熔现象。")
        if rough_val > 4.5:
            summary_parts.append("切割断面较为粗糙，伴有明显的条纹起伏。")

    return {
        "penetrated": True,
        "quality_score": overall_score,
        "penetration_score": 100.0,
        "dross_score": round(dross_score, 1),
        "burning_score": round(burning_score, 1),
        "dimension_score": round(dimension_score, 1),
        "roughness_score": round(roughness_score, 1),
        "dross_height": round(dross_height, 2),
        "burning_level": burning_level,
        "kerf_width": round(kerf_width, 3),
        "roughness_ra": round(roughness_ra, 2),
        "defects_2d": defects_2d,
        "visual_summary": " ".join(summary_parts)
    }
