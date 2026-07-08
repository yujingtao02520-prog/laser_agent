from __future__ import annotations

import math
import os
import sys
from typing import Any, Dict, List, Optional

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import gui_db


FACTORS = ["power_kw", "speed_m_min", "air_pressure_mpa", "focus_mm"]
METRICS = ["quality_score", "dross_height_max_mm", "roughness_Sa_um"]


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def format_value(value: Any, digits: int = 3) -> str:
    if is_blank(value):
        return "-"
    try:
        return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def parse_optional_float(field: QLineEdit, label: str) -> Optional[float]:
    text = field.text().strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc


def make_spin(value: float, minimum: float, maximum: float, decimals: int, step: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
    return spin


class StatCard(QFrame):
    def __init__(self, title: str, value: str = "-"):
        super().__init__()
        self.setObjectName("statCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class QualityDialog(QDialog):
    def __init__(self, run: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.run = run
        self.setWindowTitle(f"补充质量检测数据 - {run['episode_id']}")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel(f"检测记录: {run['episode_id']}")
        title.setObjectName("dialogTitle")
        power_val = run.get('power_kw')
        power_pct = float(power_val) / 0.6 if power_val is not None else None
        subtitle = QLabel(
            f"{format_value(power_pct, 1)}% | "
            f"{format_value(run.get('speed_m_min'))} m/min | "
            f"{format_value(run.get('air_pressure_mpa'))} MPa | "
            f"{format_value(run.get('focus_mm'))} mm"
        )
        subtitle.setObjectName("mutedLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.cut_through = QCheckBox("板材是否切透")
        self.cut_through.setChecked(bool(run.get("cut_through")))

        self.failure_case = QComboBox()
        self.failure_case.addItems(["正常 (normal)", "未切透 (incomplete_cut)", "过烧 (overburn)", "挂渣 (dross)", "切割不稳定 (unstable_cut)"])
        failure = run.get("failure_case") or "normal"
        idx = 0
        for i in range(self.failure_case.count()):
            text = self.failure_case.itemText(i)
            if f"({failure})" in text:
                idx = i
                break
        self.failure_case.setCurrentIndex(idx)

        self.kerf_top = self._line("kerf_width_top_mm", "例如 1.05")
        self.kerf_bottom = self._line("kerf_width_bottom_mm", "例如 0.82")
        self.taper = self._line("taper_mm", "自动计算/选填")
        self.dross_max = self._line("dross_height_max_mm", "例如 0.35")
        self.dross_mean = self._line("dross_height_mean_mm", "例如 0.18")
        self.roughness = self._line("roughness_Sa_um", "例如 9.8")
        self.defect_area = self._line("defect_area_mm2", "例如 0.0")
        self.quality_score = self._line("quality_score", "留空则自动根据挂渣与粗糙度评分")
        self.comment = QTextEdit()
        self.comment.setPlaceholderText("切面外观、挂渣剥离难易度、检测备注等...")
        self.comment.setFixedHeight(78)
        self.comment.setPlainText(run.get("manual_comment") or "")

        form.addRow("", self.cut_through)
        form.addRow("异常模式", self.failure_case)
        form.addRow("上切缝宽度 (mm)", self.kerf_top)
        form.addRow("下切缝宽度 (mm)", self.kerf_bottom)
        form.addRow("切割锥度 (mm)", self.taper)
        form.addRow("最大挂渣高度 (mm)", self.dross_max)
        form.addRow("平均挂渣高度 (mm)", self.dross_mean)
        form.addRow("表面粗糙度 Sa (um)", self.roughness)
        form.addRow("缺陷面积 (mm2)", self.defect_area)
        form.addRow("综合质量得分", self.quality_score)
        form.addRow("检测备注", self.comment)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostButton")
        save = QPushButton("保存检测数据")
        save.setObjectName("primaryButton")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._accept_if_valid)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _line(self, key: str, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        value = self.run.get(key)
        if not is_blank(value):
            field.setText(format_value(value))
        return field

    def _accept_if_valid(self):
        try:
            self.payload()
        except ValueError as exc:
            QMessageBox.warning(self, "输入数据无效", str(exc))
            return
        self.accept()

    def payload(self) -> Dict[str, Any]:
        display_text = self.failure_case.currentText()
        code = "normal"
        for label, val in {
            "正常 (normal)": "normal",
            "未切透 (incomplete_cut)": "incomplete_cut",
            "过烧 (overburn)": "overburn",
            "挂渣 (dross)": "dross",
            "切割不稳定 (unstable_cut)": "unstable_cut"
        }.items():
            if display_text == label:
                code = val
                break

        return {
            "cut_through": self.cut_through.isChecked(),
            "failure_case": code,
            "kerf_width_top_mm": parse_optional_float(self.kerf_top, "上切缝宽度"),
            "kerf_width_bottom_mm": parse_optional_float(self.kerf_bottom, "下切缝宽度"),
            "taper_mm": parse_optional_float(self.taper, "切割锥度"),
            "dross_height_max_mm": parse_optional_float(self.dross_max, "最大挂渣高度"),
            "dross_height_mean_mm": parse_optional_float(self.dross_mean, "平均挂渣高度"),
            "roughness_Sa_um": parse_optional_float(self.roughness, "表面粗糙度"),
            "defect_area_mm2": parse_optional_float(self.defect_area, "缺陷面积"),
            "quality_score": parse_optional_float(self.quality_score, "综合质量得分"),
            "manual_comment": self.comment.toPlainText().strip(),
        }


class EditParamsDialog(QDialog):
    def __init__(self, run: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.run = run
        self.setWindowTitle(f"修改工艺参数与名称 - {run['episode_id']}")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("修改切割参数与名称")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.episode_id = QLineEdit(run['episode_id'])
        self.power = make_spin(float(run.get('power_kw') or 54) / 0.6, 0.0, 100.0, 1, 1.0)
        self.speed = make_spin(float(run.get('speed_m_min') or 0.8), 0.1, 10.0, 2, 0.05)
        self.pressure = make_spin(float(run.get('air_pressure_mpa') or 1.5), 0.0, 100.0, 2, 0.05)
        self.focus = make_spin(float(run.get('focus_mm') or -9), -30.0, 10.0, 1, 0.5)
        self.material = QLineEdit(run.get('material') or "carbon_steel")
        self.thickness = make_spin(float(run.get('thickness_mm') or 30), 0.1, 200.0, 1, 0.5)
        self.gas = QLineEdit(run.get('gas') or "air")
        self.nozzle_height = make_spin(float(run.get('nozzle_height_mm') or 1.0), 0.0, 20.0, 2, 0.1)
        self.nozzle_diameter = make_spin(float(run.get('nozzle_diameter_mm') or 4.0), 0.1, 20.0, 2, 0.1)

        form.addRow("试验名称/ID", self.episode_id)
        form.addRow("激光功率 (%)", self.power)
        form.addRow("切割速度 (m/min)", self.speed)
        form.addRow("辅助气压 (MPa)", self.pressure)
        form.addRow("焦点位置 (mm)", self.focus)
        form.addRow("材料材质", self.material)
        form.addRow("材料厚度 (mm)", self.thickness)
        form.addRow("辅助气体", self.gas)
        form.addRow("喷嘴高度 (mm)", self.nozzle_height)
        form.addRow("喷嘴直径 (mm)", self.nozzle_diameter)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostButton")
        save = QPushButton("保存修改")
        save.setObjectName("primaryButton")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._accept_if_valid)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _accept_if_valid(self):
        new_id = self.episode_id.text().strip()
        if not new_id:
            QMessageBox.warning(self, "输入无效", "试验名称/ID 不能为空！")
            return
        self.accept()

    def payload(self) -> Dict[str, Any]:
        return {
            "new_episode_id": self.episode_id.text().strip(),
            "power_kw": self.power.value() * 0.6,
            "speed_m_min": self.speed.value(),
            "air_pressure_mpa": self.pressure.value(),
            "focus_mm": self.focus.value(),
            "material": self.material.text().strip(),
            "thickness_mm": self.thickness.value(),
            "gas": self.gas.text().strip(),
            "nozzle_height_mm": self.nozzle_height.value(),
            "nozzle_diameter_mm": self.nozzle_diameter.value()
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.runs: List[Dict[str, Any]] = []
        self.setWindowTitle("激光切割智能助手 - 本地试验数据记录工具")
        self.resize(1320, 820)

        self._build_ui()
        self.initialize_inputs_from_last_run()
        self.refresh_data()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        page = QVBoxLayout(root)
        page.setContentsMargins(22, 18, 22, 18)
        page.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("激光切割智能工艺助手")
        title.setObjectName("appTitle")
        subtitle = QLabel("本地 PyQt6 工艺测试数据记录与极差分析工具")
        subtitle.setObjectName("mutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        refresh_btn = QPushButton("刷新数据")
        refresh_btn.setObjectName("ghostButton")
        refresh_btn.clicked.connect(self.refresh_data)
        header.addWidget(refresh_btn)
        page.addLayout(header)

        stats = QHBoxLayout()
        self.total_card = StatCard("总试验次数")
        self.penetration_card = StatCard("成功切透率")
        self.score_card = StatCard("平均质量得分")
        stats.addWidget(self.total_card)
        stats.addWidget(self.penetration_card)
        stats.addWidget(self.score_card)
        page.addLayout(stats)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_form_panel())
        splitter.addWidget(self._build_table_panel())
        splitter.setSizes([360, 920])
        page.addWidget(splitter, stretch=1)

        page.addWidget(self._build_analysis_panel())

    def _build_form_panel(self) -> QWidget:
        panel = QGroupBox("记录新切割试验")
        panel.setObjectName("panel")
        panel.setMinimumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.episode_id_input = QLineEdit()
        self.episode_id_input.setPlaceholderText("留空则自动生成名称/ID")
        self.power = make_spin(83.0, 0.0, 100.0, 1, 1.0)
        self.speed = make_spin(0.9, 0.1, 10.0, 2, 0.05)
        self.pressure = make_spin(1.5, 0.0, 100.0, 2, 0.05)
        self.focus = make_spin(-9.0, -30.0, 10.0, 1, 0.5)
        self.material = QLineEdit("carbon_steel")
        self.thickness = make_spin(30.0, 0.1, 200.0, 1, 0.5)
        self.gas = QLineEdit("air")
        self.nozzle_height = make_spin(1.0, 0.0, 20.0, 2, 0.1)
        self.nozzle_diameter = make_spin(4.0, 0.1, 20.0, 2, 0.1)

        form.addRow("试验名称/ID", self.episode_id_input)
        form.addRow("激光功率 (%)", self.power)
        form.addRow("切割速度 (m/min)", self.speed)
        form.addRow("辅助气压 (MPa)", self.pressure)
        form.addRow("焦点位置 (mm)", self.focus)
        form.addRow("材料材质", self.material)
        form.addRow("材料厚度 (mm)", self.thickness)
        form.addRow("辅助气体", self.gas)
        form.addRow("喷嘴高度 (mm)", self.nozzle_height)
        form.addRow("喷嘴直径 (mm)", self.nozzle_diameter)
        layout.addLayout(form)

        save = QPushButton("保存切割参数")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.add_run)
        layout.addWidget(save)
        layout.addStretch()

        return panel

    def _build_table_panel(self) -> QWidget:
        panel = QGroupBox("切割试验记录表")
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "试验名称/ID",
                "激光功率",
                "切割速度",
                "辅助气压",
                "焦点位置",
                "是否切透",
                "异常模式",
                "质量得分",
                "操作栏",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(8, 280)
        layout.addWidget(self.table)

        return panel

    def _build_analysis_panel(self) -> QWidget:
        panel = QGroupBox("正交极差分析结果")
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        run_btn = QPushButton("运行正交极差分析")
        run_btn.setObjectName("primaryButton")
        run_btn.clicked.connect(self.run_analysis)
        toolbar.addWidget(run_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.analysis_output = QTextEdit()
        self.analysis_output.setObjectName("analysisOutput")
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setFixedHeight(170)
        self.analysis_output.setPlainText("录入完试验参数与检测数据后，点击上方按钮运行极差分析。")
        layout.addWidget(self.analysis_output)
        return panel

    def refresh_data(self):
        self.runs = gui_db.get_all_runs()
        self._refresh_stats()
        self._refresh_table()

    def _refresh_stats(self):
        total = len(self.runs)
        self.total_card.set_value(str(total))

        if total == 0:
            self.penetration_card.set_value("-")
            self.score_card.set_value("-")
            return

        cut_count = sum(1 for run in self.runs if run.get("cut_through"))
        self.penetration_card.set_value(f"{cut_count / total * 100:.1f}%")

        scored = [float(run["quality_score"]) for run in self.runs if not is_blank(run.get("quality_score"))]
        self.score_card.set_value(f"{sum(scored) / len(scored):.1f} / 100" if scored else "暂无评分")

    def _refresh_table(self):
        self.table.setRowCount(len(self.runs))

        for row_idx, run in enumerate(self.runs):
            values = [
                run.get("episode_id"),
                f"{format_value(float(run.get('power_kw')) / 0.6 if run.get('power_kw') is not None else None, 1)}%",
                f"{format_value(run.get('speed_m_min'))} m/min",
                f"{format_value(run.get('air_pressure_mpa'))} MPa",
                f"{format_value(run.get('focus_mm'))} mm",
                "是" if run.get("cut_through") else "否",
                run.get("failure_case") or "-",
                format_value(run.get("quality_score"), 1),
            ]

            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col_idx in [1, 2, 3, 4, 7]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col_idx == 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

            self.table.setCellWidget(row_idx, 8, self._row_actions(run))
            self.table.setRowHeight(row_idx, 42)

    def _row_actions(self, run: Dict[str, Any]) -> QWidget:
        episode_id = str(run["episode_id"])
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        load_btn = QPushButton("载入")
        load_btn.setObjectName("smallButton")
        load_btn.clicked.connect(lambda _, eid=episode_id: self.load_to_inputs(eid))

        edit = QPushButton("检测")
        edit.setObjectName("smallButton")
        edit.clicked.connect(lambda _, eid=episode_id: self.edit_quality(eid))

        modify = QPushButton("修改")
        modify.setObjectName("smallButton")
        modify.clicked.connect(lambda _, eid=episode_id: self.modify_parameters(eid))

        delete = QPushButton("删除")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(lambda _, eid=episode_id: self.delete_run(eid))

        layout.addWidget(load_btn)
        layout.addWidget(edit)
        layout.addWidget(modify)
        layout.addWidget(delete)
        layout.addStretch()
        return holder

    def add_run(self):
        eid = self.episode_id_input.text().strip()
        params = {
            "episode_id": eid if eid else None,
            "stage": "manual_run",
            "material": self.material.text().strip() or "carbon_steel",
            "thickness_mm": self.thickness.value(),
            "gas": self.gas.text().strip() or "air",
            "power_kw": self.power.value() * 0.6,
            "speed_m_min": self.speed.value(),
            "air_pressure_mpa": self.pressure.value(),
            "focus_mm": self.focus.value(),
            "nozzle_height_mm": self.nozzle_height.value(),
            "nozzle_diameter_mm": self.nozzle_diameter.value(),
        }

        try:
            episode_id = gui_db.add_run(params)
            self.episode_id_input.clear()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return

        self.refresh_data()
        run = self._find_run(episode_id)
        if run:
            self.edit_quality(episode_id)

    def initialize_inputs_from_last_run(self):
        last_params = gui_db.get_last_run_parameters()
        if last_params:
            self.power.setValue(float(last_params.get('power_kw') or 54) / 0.6)
            self.speed.setValue(float(last_params.get('speed_m_min') or 0.8))
            self.pressure.setValue(float(last_params.get('air_pressure_mpa') or 1.5))
            self.focus.setValue(float(last_params.get('focus_mm') or -9))
            self.material.setText(last_params.get('material') or "carbon_steel")
            self.thickness.setValue(float(last_params.get('thickness_mm') or 30))
            self.gas.setText(last_params.get('gas') or "air")
            self.nozzle_height.setValue(float(last_params.get('nozzle_height_mm') or 1.0))
            self.nozzle_diameter.setValue(float(last_params.get('nozzle_diameter_mm') or 4.0))

    def load_to_inputs(self, episode_id: str):
        run = self._find_run(episode_id)
        if not run:
            QMessageBox.warning(self, "未找到记录", f"未找到试验记录 {episode_id}")
            return

        self.power.setValue(float(run.get('power_kw') or 54) / 0.6)
        self.speed.setValue(float(run.get('speed_m_min') or 0.8))
        self.pressure.setValue(float(run.get('air_pressure_mpa') or 1.5))
        self.focus.setValue(float(run.get('focus_mm') or -9))
        self.material.setText(run.get('material') or "carbon_steel")
        self.thickness.setValue(float(run.get('thickness_mm') or 30))
        self.gas.setText(run.get('gas') or "air")
        self.nozzle_height.setValue(float(run.get('nozzle_height_mm') or 1.0))
        self.nozzle_diameter.setValue(float(run.get('nozzle_diameter_mm') or 4.0))

        QMessageBox.information(self, "参数已载入", f"已成功将试验 {episode_id} 的参数填入左侧输入栏！")

    def modify_parameters(self, episode_id: str):
        run = self._find_run(episode_id)
        if not run:
            QMessageBox.warning(self, "未找到记录", f"未找到试验记录 {episode_id}")
            return

        dialog = EditParamsDialog(run, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.payload()
        new_id = payload["new_episode_id"]
        try:
            gui_db.update_run_parameters(episode_id, new_id, payload)
        except Exception as exc:
            QMessageBox.critical(self, "修改参数失败", str(exc))
            return

        self.analysis_output.setPlainText("试验工艺参数已修改，请重新运行极差分析以更新结果。")
        self.refresh_data()

    def edit_quality(self, episode_id: str):
        run = self._find_run(episode_id)
        if not run:
            QMessageBox.warning(self, "记录丢失", f"未找到试验记录 {episode_id}。")
            return

        dialog = QualityDialog(run, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            gui_db.update_run_quality(episode_id, dialog.payload())
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return

        self.analysis_output.setPlainText("检测数据已更新。请点击运行分析以更新极差分析结果。")
        self.refresh_data()

    def delete_run(self, episode_id: str):
        answer = QMessageBox.question(
            self,
            "删除切割试验",
            f"是否确认从本地数据库和 CSV 日志中删除该试验记录 {episode_id}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = gui_db.delete_run(episode_id)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "记录丢失", f"未找到试验记录 {episode_id}。")
            return

        self.analysis_output.setPlainText("一条切割试验已删除，请点击运行分析以更新极差分析结果。")
        self.refresh_data()

    def run_analysis(self):
        report = self._build_analysis_report()
        if report["status"] == "warning":
            QMessageBox.warning(self, "分析不可用", report["message"])
            self.analysis_output.setPlainText(report["message"])
            return
        self.analysis_output.setPlainText(report["text"])

    def _build_analysis_report(self) -> Dict[str, str]:
        if not os.path.exists(gui_db.CSV_FILE):
            return {"status": "warning", "message": "未找到切割试验日志 CSV 文件。"}

        df = pd.read_csv(gui_db.CSV_FILE)
        if len(df) < 3:
            return {"status": "warning", "message": "录入至少 3 次试验后才能进行正交极差分析。"}

        df = df.dropna(subset=FACTORS)
        scored = df.dropna(subset=["quality_score"]) if "quality_score" in df.columns else pd.DataFrame()
        if df.empty or scored.empty:
            return {"status": "warning", "message": "当前没有已打分的切割记录可用于分析。"}

        best = scored.sort_values("quality_score", ascending=False).iloc[0]
        lines = [
            "★ 最优切割试验记录 ★",
            (
                f"  试验 ID: {best['episode_id']} | 综合得分: {float(best['quality_score']):.1f}\n"
                f"  工艺参数: 功率 {float(best['power_kw']) / 0.6:.1f}%, 速度 {float(best['speed_m_min']):.2f} m/min, "
                f"气压 {float(best['air_pressure_mpa']):.2f} MPa, 焦点 {float(best['focus_mm']):.1f} mm"
            ),
            "",
        ]

        for metric in METRICS:
            if metric not in df.columns or df[metric].isnull().all():
                continue

            metric_data = df.dropna(subset=[metric])
            if metric_data.empty:
                continue

            ranges: Dict[str, float] = {}
            best_levels: Dict[str, float] = {}
            for factor in FACTORS:
                means = metric_data.groupby(factor)[metric].mean()
                ranges[factor] = round(float(means.max() - means.min()), 3)
                best_levels[factor] = round(float(means.idxmax() if metric == "quality_score" else means.idxmin()), 3)

            metric_name_zh = {
                "quality_score": "综合质量得分 (quality_score)",
                "dross_height_max_mm": "最大挂渣高度 (dross_height_max_mm)",
                "roughness_Sa_um": "表面粗糙度 Sa (roughness_Sa_um)"
            }.get(metric, metric)

            lines.append(f"指标: {metric_name_zh}")
            for factor, range_value in sorted(ranges.items(), key=lambda item: item[1], reverse=True):
                r_val = range_value
                b_lvl = best_levels[factor]
                
                factor_zh = {
                    "power_kw": "激光功率",
                    "speed_m_min": "切割速度",
                    "air_pressure_mpa": "辅助气压",
                    "focus_mm": "焦点位置"
                }.get(factor, factor)

                if factor == "power_kw":
                    r_val = round(r_val / 0.6, 3)
                    b_lvl = round(b_lvl / 0.6, 3)
                    lines.append(f"  因素 [{factor_zh}]: 极差值 R={r_val}%, 最优水平={b_lvl}%")
                else:
                    lines.append(f"  因素 [{factor_zh}]: 极差值 R={r_val}, 最优水平={b_lvl}")
            lines.append("")

        return {"status": "success", "text": "\n".join(lines).strip()}

    def _find_run(self, episode_id: str) -> Optional[Dict[str, Any]]:
        return next((run for run in self.runs if run.get("episode_id") == episode_id), None)


def apply_theme(app: QApplication):
    app.setStyleSheet(
        """
        QWidget {
            background: #0f172a;
            color: #e5e7eb;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
            font-size: 13px;
        }
        QGroupBox#panel {
            border: 1px solid #263449;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 14px;
            background: #111c30;
            font-weight: 600;
        }
        QGroupBox#panel::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            color: #dbeafe;
        }
        QLabel#appTitle {
            color: #f8fafc;
            font-size: 24px;
            font-weight: 700;
        }
        QLabel#dialogTitle {
            color: #f8fafc;
            font-size: 18px;
            font-weight: 700;
        }
        QLabel#mutedLabel, QLabel#statTitle {
            color: #94a3b8;
        }
        QLabel#statValue {
            color: #67e8f9;
            font-size: 24px;
            font-weight: 700;
        }
        QFrame#statCard {
            background: #111c30;
            border: 1px solid #263449;
            border-radius: 8px;
        }
        QLineEdit, QDoubleSpinBox, QComboBox, QTextEdit {
            background: #0b1220;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 7px;
            selection-background-color: #2563eb;
        }
        QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border-color: #38bdf8;
        }
        QPushButton {
            border-radius: 6px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton#primaryButton {
            background: #2563eb;
            border: 1px solid #3b82f6;
            color: #ffffff;
        }
        QPushButton#primaryButton:hover {
            background: #1d4ed8;
        }
        QPushButton#ghostButton, QPushButton#smallButton {
            background: #172554;
            border: 1px solid #334155;
            color: #dbeafe;
        }
        QPushButton#ghostButton:hover, QPushButton#smallButton:hover {
            background: #1e3a8a;
        }
        QPushButton#dangerButton {
            background: #3b1118;
            border: 1px solid #dc2626;
            color: #fecaca;
        }
        QPushButton#dangerButton:hover {
            background: #7f1d1d;
            color: #ffffff;
        }
        QTableWidget {
            background: #0b1220;
            alternate-background-color: #101b2e;
            border: 1px solid #263449;
            border-radius: 6px;
            gridline-color: #1f2a3d;
        }
        QHeaderView::section {
            background: #162033;
            color: #cbd5e1;
            border: 0;
            border-bottom: 1px solid #263449;
            padding: 8px;
            font-weight: 600;
        }
        QTextEdit#analysisOutput {
            color: #dbeafe;
            font-family: Consolas, "Cascadia Mono", monospace;
        }
        QMessageBox QLabel {
            color: #e5e7eb;
        }
        """
    )


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()
