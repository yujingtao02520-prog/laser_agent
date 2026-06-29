# 30 mm Carbon Steel Air-Assisted Laser Cutting Orthogonal Demo

这是一个面向工业视觉与激光加工数据工程的最小可行原型，用于展示 30 mm 碳钢、空气辅助、60 kW 激光切割场景下的正交实验数据闭环。当前 demo 不连接真实设备，重点是实验数据结构、质量评分、episode 记录、正交极差分析和 Agent 参数重规划建议。

## 项目结构

```text
laser_cutting_orthogonal_demo/
  README.md
  requirements.txt
  configs/
    experiment_config.yaml
    scoring_rule.yaml
    bench_config.yaml
  data/
    raw_data/
    processed_data/
    metadata/
      experiment_plan.csv
      experiment_log.csv
      quality_summary.csv
  src/
    generate_pretest_plan.py
    generate_orthogonal_plan.py
    simulate_quality_result.py
    record_episode.py
    analyze_orthogonal.py
    agent_recommendation.py
    process_bench.py
    run_process_bench.py
    utils.py
  notebooks/
    demo_analysis.ipynb
    demo_analysis.py
  outputs/
    reports/
    figures/
```

## 完整流程

1. 建立 Benchmark 评价指标：在 `configs/scoring_rule.yaml` 中定义切透、挂渣、粗糙度、切缝、锥度、缺陷面积、综合评分和 failure case。
2. 生成预实验试切计划：`src/generate_pretest_plan.py` 输出速度扫描、焦点扫描、气压扫描。
3. 根据预实验结果确定参数窗口：demo 中将窗口固化到 `configs/experiment_config.yaml`，后续可由真实预实验数据更新。
4. 生成 `L9(3^4)` 正交实验表：`src/generate_orthogonal_plan.py` 输出 9 组 power、speed、pressure、focus 组合。
5. 记录每次实验 episode：`src/record_episode.py` 为每个 episode 生成 `params.json`、`quality.json`、`agent_input.json`。
6. 模拟或录入 RGB / 点云 / 质量指标：`src/simulate_quality_result.py` 当前生成质量指标，后续可扩展真实图像和点云路径。
7. 进行极差分析和主效应分析：`src/analyze_orthogonal.py` 计算 K 均值、R 极差、影响排序并绘制主效应图。
8. 输出较优参数组合：分析报告中按指标给出较优水平组合，质量分数以最大化为目标，挂渣/粗糙度/锥度以最小化为目标。
9. 生成 Agent 可读取 JSON：每个 episode 的 `agent_input.json` 统一封装工艺参数、质量观测和候选动作空间。
10. Agent 根据 failure case 给出下一轮参数建议：`src/agent_recommendation.py` 根据 `incomplete_cut`、`dross`、`overburn` 等规则输出下一轮参数。

## Benchmark 评分

综合评分公式：

```text
quality_score = 100
  - alpha * dross_height_max_mm
  - beta * roughness_Sa_um
  - gamma * abs(kerf_width_top_mm - target_kerf_width_mm)
  - delta * taper_mm
  - penalty
```

评分约束：

- 未切透时 `quality_score <= 30`
- 切割不稳定时 `quality_score <= 20`
- 严重过烧时 `quality_score <= 60`
- 严重挂渣时 `quality_score <= 70`

## 模块说明

- `configs/experiment_config.yaml`：基础工况、固定参数、预实验中心点、L9 因素水平。
- `configs/scoring_rule.yaml`：质量指标、评分系数、failure case 惩罚和封顶规则。
- `src/generate_pretest_plan.py`：生成速度、焦点、气压三类预实验计划。
- `src/generate_orthogonal_plan.py`：生成标准 `L9(3^4)` 正交实验表。
- `src/simulate_quality_result.py`：基于单位长度能量、气压和焦点偏差模拟质量结果。
- `src/record_episode.py`：将每次实验整理为 episode 级 JSON 数据。
- `src/analyze_orthogonal.py`：输出极差分析 CSV、Markdown 报告和主效应图。
- `src/agent_recommendation.py`：读取单个 episode 的 Agent 输入，输出下一轮参数建议。
- `src/run_process_bench.py`：统一工艺试验 bench 入口，用于一键运行完整数据闭环并生成 scoreboard。
- `notebooks/demo_analysis.ipynb`：端到端演示 notebook。

## 快速运行

建议使用 Python 3.10+。

```bash
pip install -r requirements.txt

python src/generate_pretest_plan.py
python src/generate_orthogonal_plan.py
python src/simulate_quality_result.py --plan data/metadata/orthogonal_plan_L9.csv
python src/analyze_orthogonal.py
python src/agent_recommendation.py --episode_id LC_CS30_AIR_L9_0005
```

也可以直接运行统一的工艺试验 bench：

```bash
python src/run_process_bench.py --bench-id cs30_air_l9 --seed 2026
```

bench 会一次性执行预实验计划、L9 正交计划、质量模拟、正交分析和 Agent 建议，并输出：

- `outputs/bench/cs30_air_l9/bench_summary.json`
- `outputs/bench/cs30_air_l9/bench_summary.md`

如需可复现实验，可给模拟脚本传入随机种子：

```bash
python src/simulate_quality_result.py --plan data/metadata/orthogonal_plan_L9.csv --seed 2026
```

## 主要输出

- `data/metadata/pretest_plan.csv`
- `data/metadata/orthogonal_plan_L9.csv`
- `data/metadata/experiment_plan.csv`
- `data/metadata/experiment_log.csv`
- `data/metadata/quality_summary.csv`
- `data/processed_data/{episode_id}/params.json`
- `data/processed_data/{episode_id}/quality.json`
- `data/processed_data/{episode_id}/agent_input.json`
- `outputs/reports/orthogonal_analysis_report.md`
- `outputs/reports/orthogonal_analysis_result.csv`
- `outputs/reports/agent_recommendation_{episode_id}.json`
- `outputs/reports/agent_recommendation_{episode_id}.md`
- `outputs/bench/cs30_air_l9/bench_summary.json`
- `outputs/bench/cs30_air_l9/bench_summary.md`
- `outputs/figures/main_effect_quality_score.png`
- `outputs/figures/main_effect_dross_height.png`
- `outputs/figures/main_effect_roughness.png`

## 扩展到真实视觉与点云

当前 demo 的 episode 结构已经预留了闭环入口。后续接入真实系统时，可以在 `params.json` 中加入设备状态和路径，在 `quality.json` 中加入视觉检测结果，并在 `agent_input.json` 中增加 RGB 图像、点云、切面 ROI、检测模型版本和异常定位结果。分析脚本可以继续复用相同的 `episode_id` 和质量指标列。
