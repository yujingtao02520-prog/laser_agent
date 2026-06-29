# Process Experiment Bench - cs30_air_l9

End-to-end process experiment bench for 30 mm carbon steel with air assist, including pretest plan generation, L9 orthogonal plan, simulated quality results, range analysis, main-effect figures, and Agent recommendation.

## Condition
- Material: carbon_steel
- Thickness: 30 mm
- Assist gas: air
- Plan: orthogonal_L9

## Scoreboard
- Episodes: 9
- Target score: 75.0
- Pass rate: 0.111
- Failure distribution: {'normal': 4, 'incomplete_cut': 3, 'overburn': 2}

## Best Episode
- Episode: LC_CS30_AIR_L9_0002
- Quality score: 78.76
- Failure case: normal
- Parameters: {'power_kw': 48.0, 'speed_m_min': 0.9, 'air_pressure_mpa': 1.5, 'focus_mm': -9.0}

## Agent Recommendation
- Episode: LC_CS30_AIR_L9_0003
- Failure case: incomplete_cut
- Next parameters: {'power_kw': 54.0, 'speed_m_min': 0.9, 'air_pressure_mpa': 1.8, 'focus_mm': -12.0}
- Recommended changes: ['increase power', 'reduce speed', 'move focus downward']

## Artifacts
- pretest_plan: `data\metadata\pretest_plan.csv`
- orthogonal_plan: `data\metadata\orthogonal_plan_L9.csv`
- experiment_log: `data\metadata\experiment_log.csv`
- quality_summary: `data\metadata\quality_summary.csv`
- analysis_csv: `outputs\reports\orthogonal_analysis_result.csv`
- analysis_report: `outputs\reports\orthogonal_analysis_report.md`
- recommendation_json: `outputs\reports\agent_recommendation_LC_CS30_AIR_L9_0003.json`
- recommendation_md: `outputs\reports\agent_recommendation_LC_CS30_AIR_L9_0003.md`
- bench_summary_json: `outputs\bench\cs30_air_l9\bench_summary.json`
- bench_summary_md: `outputs\bench\cs30_air_l9\bench_summary.md`