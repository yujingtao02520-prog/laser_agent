# Orthogonal Analysis Report

## Dataset
- Episodes: 9
- Best observed episode: LC_CS30_AIR_L9_0002
- Best observed quality_score: 78.76
- Best observed parameters: power=48 kW, speed=0.9 m/min, pressure=1.5 MPa, focus=-9 mm

## Metric: quality_score
- Objective: maximize
- Influence ranking: B_speed_m_min(R=64.107), D_focus_mm(R=11.090), C_air_pressure_mpa(R=9.547), A_power_kw(R=7.823)
- Better level combination: A_power_kw=48, B_speed_m_min=0.9, C_air_pressure_mpa=1.2, D_focus_mm=-6

## Metric: dross_height_max_mm
- Objective: minimize
- Influence ranking: B_speed_m_min(R=1.751), C_air_pressure_mpa(R=0.474), A_power_kw(R=0.321), D_focus_mm(R=0.297)
- Better level combination: A_power_kw=60, B_speed_m_min=0.6, C_air_pressure_mpa=1.5, D_focus_mm=-9

## Metric: roughness_Sa_um
- Objective: minimize
- Influence ranking: D_focus_mm(R=2.549), B_speed_m_min(R=1.771), A_power_kw(R=1.241), C_air_pressure_mpa(R=0.950)
- Better level combination: A_power_kw=48, B_speed_m_min=0.9, C_air_pressure_mpa=1.2, D_focus_mm=-9

## Metric: kerf_width_top_mm
- Objective: target
- Influence ranking: B_speed_m_min(R=0.233), A_power_kw(R=0.126), C_air_pressure_mpa(R=0.074), D_focus_mm(R=0.034)
- Better level combination: A_power_kw=54, B_speed_m_min=0.9, C_air_pressure_mpa=1.2, D_focus_mm=-6

## Metric: taper_mm
- Objective: minimize
- Influence ranking: D_focus_mm(R=0.098), B_speed_m_min(R=0.066), C_air_pressure_mpa(R=0.031), A_power_kw(R=0.012)
- Better level combination: A_power_kw=48, B_speed_m_min=0.9, C_air_pressure_mpa=1.5, D_focus_mm=-9
