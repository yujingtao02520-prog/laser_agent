from __future__ import annotations

import math
import os
import sys
import numpy as np
from typing import Any, Dict, List, Optional

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QMatrix4x4, QPainter, QPen, QPixmap
from PyQt6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVersionFunctionsFactory,
    QOpenGLVersionProfile,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
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
    QSpinBox,
    QSlider,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QScrollArea,
    QFileDialog,
    QStackedWidget,
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
        self.setWindowTitle(f"录入检测数据与整理文件 - {run['episode_id']}")
        self.setMinimumWidth(580)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel(f"检测记录: {run['episode_id']}")
        title.setObjectName("dialogTitle")
        power_val = run.get('power_kw')
        power_pct = float(power_val) / 0.6 if power_val is not None else None
        subtitle = QLabel(
            f"功率: {format_value(power_pct, 1)}% | "
            f"速度: {format_value(run.get('speed_m_min'))} m/min | "
            f"气压: {format_value(run.get('air_pressure_mpa'))} MPa | "
            f"焦点位置: {format_value(run.get('focus_mm'))} mm"
        )
        subtitle.setObjectName("mutedLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Tab Widget
        self.tabs = QTabWidget()

        # Tab 1: Regular Quality Data
        self.tab1 = QWidget()
        tab1_layout = QVBoxLayout(self.tab1)
        tab1_layout.setContentsMargins(10, 10, 10, 10)
        
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1_content = QWidget()
        form = QFormLayout(scroll1_content)
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
        self.comment.setFixedHeight(60)
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
        
        scroll1.setWidget(scroll1_content)
        tab1_layout.addWidget(scroll1)

        # Tab 2: Point Cloud & Image Files
        self.tab2 = QWidget()
        tab2_layout = QVBoxLayout(self.tab2)
        tab2_layout.setContentsMargins(10, 10, 10, 10)

        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2_content = QWidget()
        files_form = QFormLayout(scroll2_content)
        files_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        files_form.setHorizontalSpacing(14)
        files_form.setVerticalSpacing(10)

        self.file_fields = {}
        file_definitions = [
            ("point_cloud_front", "前切面点云"),
            ("point_cloud_back", "后切面点云"),
            ("point_cloud_left", "左切面点云"),
            ("point_cloud_right", "右切面点云"),
            ("point_cloud_top", "上表面点云 (Up/Top)"),
            ("point_cloud_dross", "下切面挂渣点云 (Down/Dross)"),
            ("image_front", "前切面图像"),
            ("image_back", "后切面图像"),
            ("image_left", "左切面图像"),
            ("image_right", "右切面图像"),
            ("image_top", "上表面图像 (Up/Top)"),
            ("image_bottom", "下表面图像 (Down/Bottom)"),
        ]

        for field_key, field_label in file_definitions:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            line_edit = QLineEdit()
            line_edit.setReadOnly(True)
            db_val = run.get(field_key)
            if db_val:
                line_edit.setText(db_val)
                line_edit.setToolTip(db_val)

            browse_btn = QPushButton("浏览...")
            browse_btn.setObjectName("smallButton")
            browse_btn.clicked.connect(lambda _, key=field_key, le=line_edit: self._browse_file(key, le))

            row_layout.addWidget(line_edit, stretch=1)
            row_layout.addWidget(browse_btn)

            files_form.addRow(field_label, row_widget)
            self.file_fields[field_key] = {
                "line_edit": line_edit,
                "selected_path": ""
            }

        scroll2.setWidget(scroll2_content)
        tab2_layout.addWidget(scroll2)

        self.tabs.addTab(self.tab1, "常规检测数据")
        self.tabs.addTab(self.tab2, "点云与图像整理")
        layout.addWidget(self.tabs)

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

    def _browse_file(self, field_key: str, line_edit: QLineEdit):
        filter_str = "All Files (*)"
        if "cloud" in field_key:
            filter_str = "Point Cloud Files (*.ply *.pcd *.xyz *.pts);;All Files (*)"
        else:
            filter_str = "Image Files (*.png *.jpg *.jpeg *.bmp *.tiff);;All Files (*)"
            
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"选择 {field_key} 文件",
            "",
            filter_str
        )
        if file_path:
            line_edit.setText(file_path)
            line_edit.setToolTip(file_path)
            self.file_fields[field_key]["selected_path"] = file_path

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
        }

class SectionExtractorDialog(QDialog):
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("交互式切面裁剪提取器")
        self.resize(1000, 700)
        self.setModal(True)
        
        self.file_path = file_path
        # Load full points (we will save the full cropped points, but preview downsampled)
        self.full_points = gui_db.parse_point_cloud(file_path)
        if len(self.full_points) == 0:
            QMessageBox.warning(self, "读取失败", "无法加载点云数据，或点云为空")
            self.reject()
            return
            
        # Get coordinate bounds
        self.x_bounds = (float(np.min(self.full_points[:, 0])), float(np.max(self.full_points[:, 0])))
        self.y_bounds = (float(np.min(self.full_points[:, 1])), float(np.max(self.full_points[:, 1])))
        self.z_bounds = (float(np.min(self.full_points[:, 2])), float(np.max(self.full_points[:, 2])))
        
        # Current slider bounds (in coordinates)
        self.curr_x_min, self.curr_x_max = self.x_bounds
        self.curr_y_min, self.curr_y_max = self.y_bounds
        self.curr_z_min, self.curr_z_max = self.z_bounds
        
        self._init_ui()
        self._update_preview()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        
        # Left Panel: Controls
        control_panel = QGroupBox("裁剪参数调整")
        control_panel.setFixedWidth(320)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(12)
        
        # Slider helper function
        def create_slider_row(label_text, bounds):
            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet("font-weight: bold;")
            
            min_val, max_val = bounds
            
            slider_min = QSlider(Qt.Orientation.Horizontal)
            slider_min.setRange(0, 1000)
            slider_min.setValue(0)
            
            slider_max = QSlider(Qt.Orientation.Horizontal)
            slider_max.setRange(0, 1000)
            slider_max.setValue(1000)
            
            val_lbl = QLabel(f"{min_val:.2f} ~ {max_val:.2f}")
            val_lbl.setStyleSheet("color: #38bdf8; font-size: 11px;")
            
            control_layout.addWidget(lbl)
            control_layout.addWidget(slider_min)
            control_layout.addWidget(slider_max)
            control_layout.addWidget(val_lbl)
            
            return slider_min, slider_max, val_lbl
            
        self.sld_x_min, self.sld_x_max, self.lbl_x_val = create_slider_row("X 轴切片区间", self.x_bounds)
        self.sld_y_min, self.sld_y_max, self.lbl_y_val = create_slider_row("Y 轴切片区间", self.y_bounds)
        self.sld_z_min, self.sld_z_max, self.lbl_z_val = create_slider_row("Z 轴高度区间", self.z_bounds)
        
        # Connect slider events
        for s in [self.sld_x_min, self.sld_x_max, self.sld_y_min, self.sld_y_max, self.sld_z_min, self.sld_z_max]:
            s.valueChanged.connect(self._on_slider_changed)
            
        # Quick Actions
        actions_group = QGroupBox("快速操作")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setSpacing(8)
        
        btn_auto = QPushButton("自动估计并定位")
        btn_auto.setObjectName("ghostButton")
        btn_auto.clicked.connect(self._on_auto_estimate)
        actions_layout.addWidget(btn_auto)
        
        btn_reset = QPushButton("重置为全选")
        btn_reset.setObjectName("ghostButton")
        btn_reset.clicked.connect(self._on_reset_clicked)
        actions_layout.addWidget(btn_reset)
        
        control_layout.addWidget(actions_group)
        control_layout.addStretch()
        
        # Bottom Save buttons
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("确认裁剪并覆盖保存")
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.clicked.connect(self._on_save_clicked)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghostButton")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(btn_cancel)
        control_layout.addLayout(btn_layout)
        
        layout.addWidget(control_panel)
        
        # Right Panel: 3D Preview
        preview_group = QGroupBox("3D 点云裁剪效果实时预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(4, 4, 4, 4)
        
        self.pc_viewer = PointCloudViewer()
        preview_layout.addWidget(self.pc_viewer)
        
        # Tip label
        tip_lbl = QLabel("💡 拖动左侧滑块，右侧视图会实时滤除区间外的杂点。确认后会将结果覆盖存回原文件。")
        tip_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        preview_layout.addWidget(tip_lbl)
        
        layout.addWidget(preview_group, stretch=1)

    def _get_slider_value(self, sld_min, sld_max, bounds):
        min_c, max_c = bounds
        range_c = max_c - min_c
        
        val_min = min_c + (sld_min.value() / 1000.0) * range_c
        val_max = min_c + (sld_max.value() / 1000.0) * range_c
        
        # Keep min <= max
        if val_min > val_max:
            val_min, val_max = val_max, val_min
            
        return val_min, val_max

    def _on_slider_changed(self):
        self.curr_x_min, self.curr_x_max = self._get_slider_value(self.sld_x_min, self.sld_x_max, self.x_bounds)
        self.curr_y_min, self.curr_y_max = self._get_slider_value(self.sld_y_min, self.sld_y_max, self.y_bounds)
        self.curr_z_min, self.curr_z_max = self._get_slider_value(self.sld_z_min, self.sld_z_max, self.z_bounds)
        
        # Update text labels
        self.lbl_x_val.setText(f"{self.curr_x_min:.2f} ~ {self.curr_x_max:.2f} (mm)")
        self.lbl_y_val.setText(f"{self.curr_y_min:.2f} ~ {self.curr_y_max:.2f} (mm)")
        self.lbl_z_val.setText(f"{self.curr_z_min:.2f} ~ {self.curr_z_max:.2f} (mm)")
        
        self._update_preview()

    def _update_preview(self):
        # Filter full points to show in preview
        mask = (
            (self.full_points[:, 0] >= self.curr_x_min) & (self.full_points[:, 0] <= self.curr_x_max) &
            (self.full_points[:, 1] >= self.curr_y_min) & (self.full_points[:, 1] <= self.curr_y_max) &
            (self.full_points[:, 2] >= self.curr_z_min) & (self.full_points[:, 2] <= self.curr_z_max)
        )
        filtered = self.full_points[mask]
        
        # Downsample to 10,000 for preview performance
        if len(filtered) > 10000:
            step = len(filtered) // 10000
            filtered = filtered[::step][:10000]
            
        self.pc_viewer.set_points(filtered)
        self.pc_viewer.update()

    def _on_reset_clicked(self):
        self.sld_x_min.setValue(0)
        self.sld_x_max.setValue(1000)
        self.sld_y_min.setValue(0)
        self.sld_y_max.setValue(1000)
        self.sld_z_min.setValue(0)
        self.sld_z_max.setValue(1000)
        self._on_slider_changed()

    def _on_auto_estimate(self):
        # Auto estimate core bounds using existing API
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            res = gui_db.extract_full_resolution_surface(self.file_path, self.full_points)
            QApplication.restoreOverrideCursor()
            
            # Map coordinates to slider values
            xy_bounds = res["xy_bounds"]
            
            # Set X
            x_min_val, x_max_val = xy_bounds["x_min"], xy_bounds["x_max"]
            # Set Y
            y_min_val, y_max_val = xy_bounds["y_min"], xy_bounds["y_max"]
            
            # Set Z (plane fitting residual height is a bit complex, so we estimate from Z coordinates of extracted surface)
            surf_z = res["surface_points"][:, 2]
            z_min_val, z_max_val = float(np.min(surf_z)), float(np.max(surf_z))
            
            # Helper to map coordinate back to slider value (0 to 1000)
            def map_to_slider(val, bounds):
                b_min, b_max = bounds
                b_range = b_max - b_min
                if b_range == 0:
                    return 500
                frac = (val - b_min) / b_range
                return int(max(0, min(1000, frac * 1000)))
                
            self.sld_x_min.setValue(map_to_slider(x_min_val, self.x_bounds))
            self.sld_x_max.setValue(map_to_slider(x_max_val, self.x_bounds))
            self.sld_y_min.setValue(map_to_slider(y_min_val, self.y_bounds))
            self.sld_y_max.setValue(map_to_slider(y_max_val, self.y_bounds))
            self.sld_z_min.setValue(map_to_slider(z_min_val, self.z_bounds))
            self.sld_z_max.setValue(map_to_slider(z_max_val, self.z_bounds))
            
            self._on_slider_changed()
            QMessageBox.information(self, "自动估计成功", "已为您自动计算并定位到切面的核心高度与X/Y范围！")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "估计失败", f"无法自动提取切面: {e}\n请使用滑块手动裁剪。")

    def _on_save_clicked(self):
        # Slice full-resolution point cloud
        mask = (
            (self.full_points[:, 0] >= self.curr_x_min) & (self.full_points[:, 0] <= self.curr_x_max) &
            (self.full_points[:, 1] >= self.curr_y_min) & (self.full_points[:, 1] <= self.curr_y_max) &
            (self.full_points[:, 2] >= self.curr_z_min) & (self.full_points[:, 2] <= self.curr_z_max)
        )
        final_points = self.full_points[mask]
        
        if len(final_points) == 0:
            QMessageBox.warning(self, "无法保存", "当前裁剪区间内没有任何点！")
            return
            
        confirm = QMessageBox.question(
            self,
            "确认保存",
            f"确认保存该裁剪区间？\n将保留 {len(final_points):,} 个点并覆盖原点云文件。\n此操作不可逆！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                success = gui_db.save_point_cloud_data(self.file_path, final_points)
                if success:
                    QMessageBox.information(self, "保存成功", "点云裁剪切面提取成功，已写入原归档路径。")
                    self.accept()
                else:
                    QMessageBox.critical(self, "保存失败", "写入文件出错！")
            except Exception as e:
                QMessageBox.critical(self, "保存错误", f"保存过程发生错误: {e}")

class ImageViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self.label)
        
        self.pixmap = None
        self.annotation_boxes: List[Dict[str, Any]] = []
        self.zoom_factor = 1.0
        
        # Cursor & Pan states
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.pan_active = False
        self.last_mouse_pos = None
        
    def set_image(
        self,
        file_path: str,
        annotation_boxes: Optional[List[Dict[str, Any]]] = None,
    ):
        self.pixmap = QPixmap(file_path)
        self.annotation_boxes = list(annotation_boxes or [])
        self.zoom_factor = 1.0
        self.update_view()

    def set_annotations(self, annotation_boxes: List[Dict[str, Any]]):
        self.annotation_boxes = list(annotation_boxes or [])
        self.update_view()
        
    def update_view(self):
        if self.pixmap is None or self.pixmap.isNull():
            self.label.setText("无法加载图片")
            return
            
        annotated_pixmap = QPixmap(self.pixmap)
        if self.annotation_boxes:
            painter = QPainter(annotated_pixmap)
            line_width = max(4, int(round(self.pixmap.width() / 1500.0)))
            painter.setPen(QPen(QColor(239, 68, 68), line_width))
            font = QFont()
            font.setBold(True)
            font.setPixelSize(max(24, int(round(self.pixmap.width() / 220.0))))
            painter.setFont(font)
            for box in self.annotation_boxes:
                x_min = int(box["x_min"])
                y_min = int(box["y_min"])
                width = max(1, int(box["x_max"]) - x_min)
                height = max(1, int(box["y_max"]) - y_min)
                painter.drawRect(x_min, y_min, width, height)
                label = (
                    f"{box.get('label', '挂渣')}  "
                    f"H={box.get('max_height_mm', 0):.3f} mm"
                )
                metrics = painter.fontMetrics()
                label_width = metrics.horizontalAdvance(label) + 18
                label_height = metrics.height() + 10
                label_y = max(0, y_min - label_height)
                painter.fillRect(
                    x_min,
                    label_y,
                    label_width,
                    label_height,
                    QColor(239, 68, 68, 220),
                )
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(
                    x_min + 9,
                    label_y + metrics.ascent() + 5,
                    label,
                )
                painter.setPen(QPen(QColor(239, 68, 68), line_width))
            painter.end()

        # Calculate zoomed size
        target_size = annotated_pixmap.size() * self.zoom_factor
        scaled_pix = annotated_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(scaled_pix)
        self.label.resize(scaled_pix.size())
        
    def wheelEvent(self, event):
        if self.pixmap is None or self.pixmap.isNull():
            super().wheelEvent(event)
            return
            
        # Zoom Factor modification
        angle = event.angleDelta().y()
        if angle > 0:
            self.zoom_factor *= 1.15
        else:
            self.zoom_factor /= 1.15
            
        self.zoom_factor = max(0.1, min(10.0, self.zoom_factor))
        self.update_view()
        event.accept()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pan_active = True
            self.last_mouse_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pan_active = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.pan_active and self.last_mouse_pos is not None:
            delta = event.position().toPoint() - self.last_mouse_pos
            self.last_mouse_pos = event.position().toPoint()
            
            # Scroll scrollbars programmatically
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

class PointCloudViewer(QOpenGLWidget):
    GL_COLOR_BUFFER_BIT = 0x00004000
    GL_DEPTH_BUFFER_BIT = 0x00000100
    GL_DEPTH_TEST = 0x0B71
    GL_PROGRAM_POINT_SIZE = 0x8642
    GL_POINTS = 0x0000
    GL_FLOAT = 0x1406

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = np.zeros((0, 3), dtype=np.float32)
        self.gpu_points = np.zeros((0, 3), dtype=np.float32)
        self.gpu_vertices = np.zeros((0, 4), dtype=np.float32)
        self.mask_point_count = 0
        self.total_point_count = 0
        self.render_point_count = 0
        self.theta = 0.5  # Yaw angle
        self.phi = 0.5    # Pitch angle
        self.zoom = 1.0
        self.last_mouse_pos = None
        self.gl_functions = None
        self.shader_program = None
        self.vertex_buffer = None
        self.gl_ready = False
        self.gl_error = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 300)
        
    def set_points(self, pts: np.ndarray, defect_mask: Optional[np.ndarray] = None):
        self.points = pts
        self.total_point_count = len(pts)
        if len(pts) > 0:
            # Normalize once on CPU, then keep every extracted surface point in a GPU VBO.
            point_min = np.min(pts, axis=0)
            point_max = np.max(pts, axis=0)
            center = (point_min + point_max) / 2.0
            max_range = float(np.max(point_max - point_min))
            if max_range > 0:
                self.gpu_points = np.ascontiguousarray(
                    (pts - center) / max_range,
                    dtype=np.float32,
                )
            else:
                self.gpu_points = np.zeros_like(pts, dtype=np.float32)
            if defect_mask is None or len(defect_mask) != len(pts):
                mask_values = np.zeros(len(pts), dtype=np.float32)
            else:
                mask_values = np.asarray(defect_mask, dtype=np.float32).reshape(-1)
                mask_values = np.clip(mask_values, 0.0, 1.0)
            self.mask_point_count = int(np.count_nonzero(mask_values > 0.5))
            self.gpu_vertices = np.ascontiguousarray(
                np.column_stack((self.gpu_points, mask_values)),
                dtype=np.float32,
            )
            self.render_point_count = len(self.gpu_points)
        else:
            self.render_point_count = 0
            self.mask_point_count = 0
            self.gpu_points = np.zeros((0, 3), dtype=np.float32)
            self.gpu_vertices = np.zeros((0, 4), dtype=np.float32)

        if self.gl_ready and self.isValid():
            self.makeCurrent()
            self._upload_points()
            self.doneCurrent()
        self.update()

    def initializeGL(self):
        try:
            version_profile = QOpenGLVersionProfile()
            version_profile.setVersion(2, 0)
            self.gl_functions = QOpenGLVersionFunctionsFactory.get(
                version_profile,
                self.context(),
            )
            if self.gl_functions is None:
                raise RuntimeError("当前显卡驱动不支持 OpenGL 2.0")
            self.gl_functions.initializeOpenGLFunctions()
            self.gl_functions.glEnable(self.GL_DEPTH_TEST)
            self.gl_functions.glEnable(self.GL_PROGRAM_POINT_SIZE)
            self.gl_functions.glClearColor(15 / 255.0, 23 / 255.0, 42 / 255.0, 1.0)

            self.shader_program = QOpenGLShaderProgram(self)
            vertex_shader = """
                #version 120
                attribute vec3 position;
                attribute float defectMask;
                uniform mat4 mvp;
                varying float depthColor;
                varying float maskColor;
                void main() {
                    gl_Position = mvp * vec4(position, 1.0);
                    gl_PointSize = mix(2.0, 5.0, defectMask);
                    depthColor = clamp(position.z + 0.5, 0.0, 1.0);
                    maskColor = defectMask;
                }
            """
            fragment_shader = """
                #version 120
                varying float depthColor;
                varying float maskColor;
                void main() {
                    vec3 cyan = vec3(56.0, 189.0, 248.0) / 255.0;
                    vec3 purple = vec3(168.0, 85.0, 247.0) / 255.0;
                    vec3 baseColor = mix(cyan, purple, depthColor);
                    vec3 maskRed = vec3(1.0, 0.18, 0.10);
                    gl_FragColor = vec4(mix(baseColor, maskRed, maskColor), 0.95);
                }
            """
            if not self.shader_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex,
                vertex_shader,
            ):
                raise RuntimeError(self.shader_program.log())
            if not self.shader_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment,
                fragment_shader,
            ):
                raise RuntimeError(self.shader_program.log())
            self.shader_program.bindAttributeLocation("position", 0)
            self.shader_program.bindAttributeLocation("defectMask", 1)
            if not self.shader_program.link():
                raise RuntimeError(self.shader_program.log())

            self.vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not self.vertex_buffer.create():
                raise RuntimeError("无法创建 OpenGL 点云缓冲区")
            self.vertex_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
            self.gl_ready = True
            self._upload_points()
            self.context().aboutToBeDestroyed.connect(self._cleanup_gl)
        except Exception as exc:
            self.gl_error = str(exc)
            self.gl_ready = False

    def _upload_points(self):
        if not self.gl_ready or self.vertex_buffer is None:
            return
        if not self.vertex_buffer.bind():
            self.gl_error = "无法绑定 OpenGL 点云缓冲区"
            return
        raw = self.gpu_vertices.tobytes(order="C")
        self.vertex_buffer.allocate(raw, len(raw))
        self.vertex_buffer.release()

    def _cleanup_gl(self):
        if not self.gl_ready:
            return
        self.makeCurrent()
        if self.vertex_buffer is not None and self.vertex_buffer.isCreated():
            self.vertex_buffer.destroy()
        if self.shader_program is not None:
            self.shader_program.removeAllShaders()
        self.doneCurrent()
        self.gl_ready = False
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.position()
            
    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            delta = event.position() - self.last_mouse_pos
            self.last_mouse_pos = event.position()
            self.theta += delta.x() * 0.007
            self.phi += delta.y() * 0.007
            # Avoid lock at pole
            self.phi = max(-1.5, min(1.5, self.phi))
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse_pos = None
            
    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle > 0:
            self.zoom *= 1.15
        else:
            self.zoom /= 1.15
        self.zoom = max(0.1, min(20.0, self.zoom))
        self.update()

    def paintGL(self):
        if self.gl_functions is None:
            return
        self.gl_functions.glEnable(self.GL_DEPTH_TEST)
        self.gl_functions.glEnable(self.GL_PROGRAM_POINT_SIZE)
        self.gl_functions.glClear(self.GL_COLOR_BUFFER_BIT | self.GL_DEPTH_BUFFER_BIT)

        if self.gl_ready and self.render_point_count > 0:
            aspect = self.width() / max(1.0, float(self.height()))
            projection = QMatrix4x4()
            if aspect >= 1.0:
                projection.ortho(-aspect, aspect, -1.0, 1.0, -10.0, 10.0)
            else:
                projection.ortho(-1.0, 1.0, -1.0 / aspect, 1.0 / aspect, -10.0, 10.0)

            model = QMatrix4x4()
            model.scale(1.55 * self.zoom)
            model.rotate(math.degrees(self.phi), 1.0, 0.0, 0.0)
            model.rotate(math.degrees(self.theta), 0.0, 1.0, 0.0)
            mvp = projection * model

            self.shader_program.bind()
            self.shader_program.setUniformValue("mvp", mvp)
            self.vertex_buffer.bind()
            self.shader_program.enableAttributeArray(0)
            self.shader_program.enableAttributeArray(1)
            self.shader_program.setAttributeBuffer(0, self.GL_FLOAT, 0, 3, 16)
            self.shader_program.setAttributeBuffer(1, self.GL_FLOAT, 12, 1, 16)
            self.gl_functions.glDrawArrays(self.GL_POINTS, 0, self.render_point_count)
            self.shader_program.disableAttributeArray(0)
            self.shader_program.disableAttributeArray(1)
            self.vertex_buffer.release()
            self.shader_program.release()

        painter = QPainter(self)
        painter.setPen(QColor(255, 255, 255, 160))
        if self.gl_error:
            painter.setPen(QColor(248, 113, 113))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"OpenGL 初始化失败：{self.gl_error}")
        elif self.render_point_count == 0:
            painter.setPen(QColor(148, 163, 184))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无三维点云数据或文件未归档")
        else:
            painter.drawText(15, 25, f"GPU 渲染点数: {self.render_point_count:,}")
            painter.drawText(15, 45, f"旋转: Yaw={self.theta:.2f}, Pitch={self.phi:.2f}")
            painter.drawText(15, 65, f"缩放: {self.zoom:.2f}x (滚轮/拖动)")
            if self.mask_point_count:
                painter.setPen(QColor(255, 82, 55))
                painter.drawText(
                    15,
                    85,
                    f"● 3D 起渣面 mask: {self.mask_point_count:,} 点",
                )
        painter.end()


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
        subtitle = QLabel("本地 PyQt6 工艺数据记录、极差分析与点云图片预览工具")
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

        # Tab Widget Layout
        self.tabs = QTabWidget()
        
        # --- Tab 1: 试验记录与数据录入 ---
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 10, 0, 0)
        tab1_layout.setSpacing(12)
        
        stats = QHBoxLayout()
        self.total_card = StatCard("总试验次数")
        self.penetration_card = StatCard("成功切透率")
        self.score_card = StatCard("平均质量得分")
        stats.addWidget(self.total_card)
        stats.addWidget(self.penetration_card)
        stats.addWidget(self.score_card)
        tab1_layout.addLayout(stats)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_form_panel())
        splitter.addWidget(self._build_table_panel())
        splitter.setSizes([360, 920])
        tab1_layout.addWidget(splitter, stretch=1)
        
        self.tabs.addTab(tab1, "试验运行与参数录入")
        
        # --- Tab 2: 极差分析与数据报告 ---
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(10, 10, 10, 10)
        tab2_layout.addWidget(self._build_analysis_panel(), stretch=1)
        self.tabs.addTab(tab2, "极差分析与质量分析")
        
        # --- Tab 3: 三维与二维检测预览 ---
        tab3 = self._build_preview_tab()
        self.tabs.addTab(tab3, "检测文件三维/二维预览")
        
        page.addWidget(self.tabs, stretch=1)

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Panel: File list and control
        left_panel = QGroupBox("检测文件选择")
        left_panel.setObjectName("panel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(12)
        
        trial_sel = QHBoxLayout()
        trial_sel.addWidget(QLabel("选择试验记录:"))
        self.preview_trial_combo = QComboBox()
        self.preview_trial_combo.currentTextChanged.connect(self._on_preview_trial_changed)
        trial_sel.addWidget(self.preview_trial_combo, stretch=1)
        left_layout.addLayout(trial_sel)
        
        left_layout.addWidget(QLabel("已归档文件列表:"))
        
        slots_scroll = QScrollArea()
        slots_scroll.setWidgetResizable(True)
        slots_content = QWidget()
        self.slots_layout = QVBoxLayout(slots_content)
        self.slots_layout.setContentsMargins(0, 0, 0, 0)
        self.slots_layout.setSpacing(8)
        
        self.slot_buttons = {}
        self.slot_status_labels = {}
        
        file_definitions = [
            ("point_cloud_front", "前切面点云", "3d"),
            ("point_cloud_back", "后切面点云", "3d"),
            ("point_cloud_left", "左切面点云", "3d"),
            ("point_cloud_right", "右切面点云", "3d"),
            ("point_cloud_top", "上表面点云 (Up/Top)", "3d"),
            ("point_cloud_dross", "下切面挂渣点云 (Down/Dross)", "3d"),
            ("image_front", "前切面图像", "2d"),
            ("image_back", "后切面图像", "2d"),
            ("image_left", "左切面图像", "2d"),
            ("image_right", "右切面图像", "2d"),
            ("image_top", "上表面图像 (Up/Top)", "2d"),
            ("image_bottom", "下表面图像 (Down/Bottom)", "2d"),
        ]
        
        for field_key, field_name, file_type in file_definitions:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(8)
            
            lbl_name = QLabel(field_name)
            lbl_name.setStyleSheet("font-weight: bold;")
            
            lbl_status = QLabel("未录入")
            lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self.slot_status_labels[field_key] = lbl_status
            
            view_btn = QPushButton("预览")
            view_btn.setObjectName("smallButton")
            view_btn.setEnabled(False)
            view_btn.clicked.connect(lambda _, key=field_key: self._view_inspection_file(key))
            self.slot_buttons[field_key] = view_btn
            
            row_layout.addWidget(lbl_name)
            row_layout.addWidget(lbl_status, stretch=1)
            row_layout.addWidget(view_btn)
            self.slots_layout.addWidget(row)
            
        self.slots_layout.addStretch()
        slots_scroll.setWidget(slots_content)
        left_layout.addWidget(slots_scroll)
        
        # Add One-Click Auto Scan & Archive Button
        self.btn_auto_scan = QPushButton("一键扫描归档本地文件")
        self.btn_auto_scan.setObjectName("primaryButton")
        self.btn_auto_scan.clicked.connect(self._on_auto_scan_clicked)
        left_layout.addWidget(self.btn_auto_scan)

        # Add One-Click Multi-Luminance Import Button
        self.btn_import_luminance = QPushButton("一键多选导入亮度图 (Luminance)")
        self.btn_import_luminance.setObjectName("ghostButton")
        self.btn_import_luminance.setToolTip("多选包含 luminance / up / down 的基恩士亮度图/TIF，自动分配入库")
        self.btn_import_luminance.clicked.connect(self._on_import_luminance_clicked)
        left_layout.addWidget(self.btn_import_luminance)
        
        # Right Panel: Canvas & Bottom Console
        right_panel = QGroupBox("检测结果可视化窗口")
        right_panel.setObjectName("panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(10)
        
        # Visualizers Splitter (3D + 2D)
        visual_splitter = QSplitter(Qt.Orientation.Horizontal)

        pc_group = QGroupBox("3D 点云（保留交互视图）")
        pc_group_layout = QVBoxLayout(pc_group)
        pc_group_layout.setContentsMargins(4, 4, 4, 4)
        
        self.dross_mask_visible = True
        mask_toolbar = QHBoxLayout()
        mask_toolbar.addStretch()
        self.btn_toggle_dross_mask = QPushButton("显示起渣 mask")
        self.btn_toggle_dross_mask.setObjectName("smallButton")
        self.btn_toggle_dross_mask.setEnabled(False)
        self.btn_toggle_dross_mask.clicked.connect(self._on_toggle_dross_mask_clicked)
        mask_toolbar.addWidget(self.btn_toggle_dross_mask)
        pc_group_layout.addLayout(mask_toolbar)
        
        self.pc_stack = QStackedWidget()
        self.pc_placeholder_lbl = QLabel("请选择 3D 点云文件")
        self.pc_placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pc_placeholder_lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        self.pc_stack.addWidget(self.pc_placeholder_lbl)
        self.pc_viewer = PointCloudViewer()
        self.pc_stack.addWidget(self.pc_viewer)
        pc_group_layout.addWidget(self.pc_stack)

        image_group = QGroupBox("2D 图像 / 挂渣标注")
        image_group_layout = QVBoxLayout(image_group)
        image_group_layout.setContentsMargins(4, 4, 4, 4)
        
        self.image_stack = QStackedWidget()
        self.image_placeholder_lbl = QLabel("映射完成后在此显示 2D 挂渣框")
        self.image_placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_placeholder_lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        self.image_stack.addWidget(self.image_placeholder_lbl)
        self.image_viewer = ImageViewer()
        self.image_stack.addWidget(self.image_viewer)
        image_group_layout.addWidget(self.image_stack)

        visual_splitter.addWidget(pc_group)
        visual_splitter.addWidget(image_group)
        visual_splitter.setSizes([560, 440])
        right_layout.addWidget(visual_splitter, stretch=1)

        # Bottom Panel: Point Cloud Algorithms & Analysis Results
        bottom_panel = QWidget()
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        
        # 1. Point Cloud processing console (proc_box)
        proc_box = QGroupBox("三维点云算法工具箱")
        proc_box.setObjectName("panel")
        proc_layout = QGridLayout(proc_box)
        proc_layout.setContentsMargins(10, 10, 10, 10)
        proc_layout.setSpacing(8)
        
        self.btn_denoise = QPushButton("滤波降噪")
        self.btn_denoise.setObjectName("ghostButton")
        self.btn_denoise.setEnabled(False)
        self.btn_denoise.clicked.connect(self._on_denoise_clicked)
        
        self.btn_downsample = QPushButton("降采样(5k)")
        self.btn_downsample.setObjectName("ghostButton")
        self.btn_downsample.setEnabled(False)
        self.btn_downsample.clicked.connect(self._on_downsample_clicked)
        
        self.btn_reset_pc = QPushButton("重置点云")
        self.btn_reset_pc.setObjectName("ghostButton")
        self.btn_reset_pc.setEnabled(False)
        self.btn_reset_pc.clicked.connect(self._on_reset_pc_clicked)
        
        proc_layout.addWidget(self.btn_denoise, 0, 0)
        proc_layout.addWidget(self.btn_downsample, 0, 1)
        proc_layout.addWidget(self.btn_reset_pc, 0, 2)
        
        core_ratio_lbl = QLabel("核心比例:")
        core_ratio_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.core_ratio_spin = QSpinBox()
        self.core_ratio_spin.setRange(10, 100)
        self.core_ratio_spin.setSingleStep(5)
        self.core_ratio_spin.setValue(50)
        self.core_ratio_spin.setSuffix("%")
        self.core_ratio_spin.setEnabled(False)
        self.core_ratio_spin.setMinimumWidth(70)
        
        self.btn_extract_core = QPushButton("提取核心区域")
        self.btn_extract_core.setObjectName("primaryButton")
        self.btn_extract_core.setEnabled(False)
        self.btn_extract_core.clicked.connect(self._on_extract_core_clicked)
        
        proc_layout.addWidget(core_ratio_lbl, 1, 0)
        proc_layout.addWidget(self.core_ratio_spin, 1, 1)
        proc_layout.addWidget(self.btn_extract_core, 1, 2)
        
        self.btn_adaptive_core = QPushButton("自适应识别并提取中心切面")
        self.btn_adaptive_core.setObjectName("primaryButton")
        self.btn_adaptive_core.setEnabled(False)
        self.btn_adaptive_core.clicked.connect(self._on_adaptive_core_clicked)
        
        self.btn_remove_spikes = QPushButton("提取真实切面层（去底面/毛刺）")
        self.btn_remove_spikes.setObjectName("ghostButton")
        self.btn_remove_spikes.setEnabled(False)
        self.btn_remove_spikes.clicked.connect(self._on_remove_spikes_clicked)
        
        proc_layout.addWidget(self.btn_adaptive_core, 2, 0, 1, 2)
        proc_layout.addWidget(self.btn_remove_spikes, 2, 2)
        
        self.btn_analyze_surface = QPushButton("计算切面形貌")
        self.btn_analyze_surface.setObjectName("primaryButton")
        self.btn_analyze_surface.setEnabled(False)
        self.btn_analyze_surface.clicked.connect(self._on_analyze_surface_clicked)
        
        self.btn_map_dross = QPushButton("3D 凸起映射到 2D 挂渣框")
        self.btn_map_dross.setObjectName("primaryButton")
        self.btn_map_dross.setEnabled(False)
        self.btn_map_dross.clicked.connect(self._on_map_dross_clicked)
        
        proc_layout.addWidget(self.btn_analyze_surface, 3, 0, 1, 1)
        proc_layout.addWidget(self.btn_map_dross, 3, 1, 1, 2)
        
        self.btn_interactive_crop = QPushButton("💡 交互式切面裁剪提取器")
        self.btn_interactive_crop.setObjectName("primaryButton")
        self.btn_interactive_crop.setEnabled(False)
        self.btn_interactive_crop.clicked.connect(self._on_interactive_crop_clicked)
        proc_layout.addWidget(self.btn_interactive_crop, 4, 0, 1, 3)
        
        bottom_layout.addWidget(proc_box, stretch=4)
        
        # 2. Results & Metrics Console (results_group)
        results_group = QGroupBox("切面形貌与挂渣检测结果")
        results_group.setObjectName("panel")
        results_group_layout = QHBoxLayout(results_group)
        results_group_layout.setContentsMargins(10, 10, 10, 10)
        results_group_layout.setSpacing(10)
        
        metrics_widget = QWidget()
        metrics_layout = QVBoxLayout(metrics_widget)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(4)
        
        self.lbl_points_count = QLabel("点数: --")
        self.lbl_bbox_x = QLabel("X 尺寸 (宽): --")
        self.lbl_bbox_y = QLabel("Y 尺寸 (高): --")
        self.lbl_bbox_z = QLabel("Z 尺寸 (深): --")
        self.lbl_points_count.setStyleSheet("font-weight: bold; color: #38bdf8;")
        self.lbl_bbox_x.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_bbox_y.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_bbox_z.setStyleSheet("color: #94a3b8; font-size: 11px;")
        
        metrics_layout.addWidget(self.lbl_points_count)
        metrics_layout.addWidget(self.lbl_bbox_x)
        metrics_layout.addWidget(self.lbl_bbox_y)
        metrics_layout.addWidget(self.lbl_bbox_z)
        metrics_layout.addStretch()
        
        self.morphology_output = QTextEdit()
        self.morphology_output.setReadOnly(True)
        self.morphology_output.setPlaceholderText("提取真实切面后，可计算 Sa、Sq、Sz 等形貌指标")
        self.morphology_output.setStyleSheet("background: rgba(15, 23, 42, 0.6); border: 1px solid var(--card-border); color: #e2e8f0;")
        
        results_group_layout.addWidget(metrics_widget, stretch=1)
        results_group_layout.addWidget(self.morphology_output, stretch=3)
        
        bottom_layout.addWidget(results_group, stretch=5)
        
        right_layout.addWidget(bottom_panel)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([320, 960])
        
        layout.addWidget(splitter)
        return widget

    def _refresh_preview_trials(self):
        self.preview_trial_combo.blockSignals(True)
        current_text = self.preview_trial_combo.currentText()
        self.preview_trial_combo.clear()
        for r in self.runs:
            self.preview_trial_combo.addItem(r["episode_id"])
        if current_text and self.preview_trial_combo.findText(current_text) >= 0:
            self.preview_trial_combo.setCurrentText(current_text)
        elif self.preview_trial_combo.count() > 0:
            self.preview_trial_combo.setCurrentIndex(0)
        self.preview_trial_combo.blockSignals(False)
        self._on_preview_trial_changed(self.preview_trial_combo.currentText())

    def _on_preview_trial_changed(self, episode_id: str):
        if not episode_id:
            for btn in self.slot_buttons.values():
                btn.setEnabled(False)
            for lbl in self.slot_status_labels.values():
                lbl.setText("未录入")
                lbl.setStyleSheet("color: #94a3b8;")
            return
            
        run = self._find_run(episode_id)
        if not run:
            return
            
        self.current_preview_run = run
        file_keys = [
            "point_cloud_front", "point_cloud_back", "point_cloud_left", "point_cloud_right", "point_cloud_top", "point_cloud_dross",
            "image_front", "image_back", "image_left", "image_right", "image_top", "image_bottom"
        ]
        for key in file_keys:
            val = run.get(key)
            btn = self.slot_buttons[key]
            lbl = self.slot_status_labels[key]
            
            if val:
                filename = val.split('/')[-1]
                lbl.setText(f"已录入 ({filename})")
                lbl.setStyleSheet("color: #2ec4b6; font-weight: 500;")
                btn.setEnabled(True)
            else:
                lbl.setText("未录入")
                lbl.setStyleSheet("color: #94a3b8;")
                btn.setEnabled(False)

    def _view_inspection_file(self, field_key: str):
        if not hasattr(self, 'current_preview_run') or not self.current_preview_run:
            return
            
        rel_path = self.current_preview_run.get(field_key)
        if not rel_path:
            return
            
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_path = os.path.join(project_dir, rel_path)
        if not os.path.exists(abs_path):
            QMessageBox.warning(self, "文件不存在", f"找不到归档物理文件: {abs_path}")
            return
            
        self.current_file_key = field_key
        self.current_file_path = abs_path
        
        if "cloud" in field_key:
            self.original_pts = gui_db.parse_point_cloud(abs_path)
            self.current_pts = self.original_pts.copy()
            self.current_dross_mask = None
            self.dross_mask_visible = True
            self.full_surface_result = None
            
            self.btn_denoise.setEnabled(True)
            self.btn_downsample.setEnabled(True)
            self.btn_reset_pc.setEnabled(True)
            self.core_ratio_spin.setEnabled(True)
            self.btn_extract_core.setEnabled(True)
            self.btn_adaptive_core.setEnabled(True)
            self.btn_adaptive_core.setText("自适应识别并提取中心切面")
            self.btn_remove_spikes.setEnabled(True)
            self.btn_remove_spikes.setText("提取真实切面层（去底面/毛刺）")
            self.btn_interactive_crop.setEnabled(True)
            self.btn_analyze_surface.setEnabled(True)
            self.btn_map_dross.setEnabled(False)
            self.btn_map_dross.setText("3D 凸起映射到 2D 挂渣框")
            self.morphology_output.clear()
            
            self.pc_stack.setCurrentIndex(1)
            self.image_stack.setCurrentIndex(0)
            self._update_point_cloud_view()
        else:
            self.btn_denoise.setEnabled(False)
            self.btn_downsample.setEnabled(False)
            self.btn_reset_pc.setEnabled(False)
            self.core_ratio_spin.setEnabled(False)
            self.btn_extract_core.setEnabled(False)
            self.btn_adaptive_core.setEnabled(False)
            self.btn_interactive_crop.setEnabled(False)
            self.btn_remove_spikes.setEnabled(False)
            self.btn_analyze_surface.setEnabled(False)
            self.btn_map_dross.setEnabled(False)
            self.morphology_output.clear()
            
            self.lbl_points_count.setText("点数: --")
            self.lbl_bbox_x.setText("X 尺寸 (宽): --")
            self.lbl_bbox_y.setText("Y 尺寸 (高): --")
            self.lbl_bbox_z.setText("Z 尺寸 (深): --")
            
            self.image_viewer.set_image(abs_path)
            self.image_stack.setCurrentIndex(1)

    def _update_point_cloud_view(self):
        pts = self.current_pts
        defect_mask = getattr(self, "current_dross_mask", None)
        if defect_mask is not None and len(defect_mask) != len(pts):
            defect_mask = None
        has_mask = bool(
            defect_mask is not None and np.count_nonzero(defect_mask) > 0
        )
        visible_mask = defect_mask if has_mask and self.dross_mask_visible else None
        self.pc_viewer.set_points(pts, visible_mask)
        self.btn_toggle_dross_mask.setEnabled(has_mask)
        self.btn_toggle_dross_mask.setText(
            "隐藏起渣 mask"
            if has_mask and self.dross_mask_visible
            else "显示起渣 mask"
        )
        self.lbl_points_count.setText(f"点数: {len(pts):,}")
        if len(pts) > 0:
            pt_min = np.min(pts, axis=0)
            pt_max = np.max(pts, axis=0)
            ranges = pt_max - pt_min
            self.lbl_bbox_x.setText(f"X 尺寸 (宽): {ranges[0]:.2f} mm")
            self.lbl_bbox_y.setText(f"Y 尺寸 (高): {ranges[1]:.2f} mm")
            self.lbl_bbox_z.setText(f"Z 尺寸 (深): {ranges[2]:.2f} mm")
        else:
            self.lbl_bbox_x.setText("X 尺寸: --")
            self.lbl_bbox_y.setText("Y 尺寸: --")
            self.lbl_bbox_z.setText("Z 尺寸: --")

    def _on_denoise_clicked(self):
        if not hasattr(self, 'current_pts') or len(self.current_pts) == 0:
            return
        self.current_pts = gui_db.denoise_point_cloud(self.current_pts)
        self.current_dross_mask = None
        self._update_point_cloud_view()

    def _on_downsample_clicked(self):
        if not hasattr(self, 'current_pts') or len(self.current_pts) == 0:
            return
        self.current_pts = gui_db.downsample_point_cloud(self.current_pts, target_count=5000)
        self.current_dross_mask = None
        self._update_point_cloud_view()

    def _on_extract_core_clicked(self):
        if not hasattr(self, 'original_pts') or len(self.original_pts) == 0:
            return
        keep_ratio = self.core_ratio_spin.value() / 100.0
        core_pts = gui_db.extract_core_region(self.original_pts, keep_ratio)
        if len(core_pts) == 0:
            QMessageBox.warning(
                self,
                "核心区域为空",
                "当前比例内没有点，请增大核心区域比例后重试。",
            )
            return
        self.current_pts = core_pts
        self.current_dross_mask = None
        self._update_point_cloud_view()

    def _on_interactive_crop_clicked(self):
        if not hasattr(self, 'current_file_path') or not self.current_file_path:
            return
            
        dialog = SectionExtractorDialog(self.current_file_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload point cloud file
            self.original_pts = gui_db.parse_point_cloud(self.current_file_path)
            self.current_pts = self.original_pts.copy()
            self.current_dross_mask = None
            self._update_point_cloud_view()
            self._on_analyze_surface_clicked()

    def _on_adaptive_core_clicked(self):
        if (
            not hasattr(self, 'original_pts')
            or len(self.original_pts) == 0
            or not hasattr(self, 'current_file_path')
        ):
            return

        self.btn_adaptive_core.setEnabled(False)
        self.btn_adaptive_core.setText("正在从原始点云提取完整切面…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            result = gui_db.extract_full_resolution_surface(
                self.current_file_path,
                self.original_pts,
            )
        except Exception as exc:
            QMessageBox.warning(self, "原始切面提取失败", str(exc))
            self.btn_adaptive_core.setText("自适应识别并提取中心切面")
            self.btn_adaptive_core.setEnabled(True)
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.current_pts = result["surface_points"]
        self.current_dross_mask = None
        self.full_surface_result = result
        self._update_point_cloud_view()
        self.btn_adaptive_core.setText(
            f"完整切面：{result['surface_point_count']:,} / "
            f"{result['source_point_count']:,} 点"
        )
        self.btn_adaptive_core.setEnabled(True)
        removed = result["roi_point_count"] - result["surface_point_count"]
        self.btn_remove_spikes.setText(f"已剔除 {removed:,} 个底面/毛刺点")
        self.btn_remove_spikes.setEnabled(False)
        self._on_analyze_surface_clicked()
        if self.current_file_key in {"point_cloud_top", "point_cloud_dross"}:
            self.btn_map_dross.setEnabled(True)
            self._map_dross_to_2d(show_messages=False)

    def _on_remove_spikes_clicked(self):
        if not hasattr(self, 'current_pts') or len(self.current_pts) == 0:
            return
        before = len(self.current_pts)
        self.current_pts = gui_db.extract_connected_surface_layer(self.current_pts)
        self.current_dross_mask = None
        removed = before - len(self.current_pts)
        self.btn_remove_spikes.setText(f"已剔除 {removed} 个底面/毛刺点")
        self.btn_remove_spikes.setEnabled(False)
        self._update_point_cloud_view()
        self._on_analyze_surface_clicked()

    def _on_analyze_surface_clicked(self):
        if not hasattr(self, 'current_pts') or len(self.current_pts) < 3:
            return
        try:
            result = gui_db.analyze_surface_morphology(self.current_pts)
        except Exception as exc:
            QMessageBox.warning(self, "形貌计算失败", str(exc))
            return

        lines = [f"有效点数：{result['point_count']:,}"]
        for item in result["metrics"]:
            unit = f" {item['unit']}" if item["unit"] else ""
            lines.append(f"{item['label']}：{item['value']}{unit}")
        plane = result["reference_plane"]
        lines.extend(
            [
                f"基准面倾角 X/Y：{plane['slope_x_deg']:.4f}° / {plane['slope_y_deg']:.4f}°",
                "",
                result["note"],
            ]
        )
        self.morphology_output.setPlainText("\n".join(lines))

    def _on_map_dross_clicked(self):
        self._map_dross_to_2d(show_messages=True)

    def _map_dross_to_2d(self, show_messages: bool = True):
        if (
            not hasattr(self, "current_pts")
            or len(self.current_pts) < 30
            or not hasattr(self, "current_preview_run")
        ):
            return
        # Select corresponding 2D image: top for point_cloud_top, bottom (or top) for point_cloud_dross
        is_top = (getattr(self, "current_file_key", None) == "point_cloud_top")
        image_key = "image_top" if is_top else "image_bottom"
        image_rel_path = self.current_preview_run.get(image_key) or self.current_preview_run.get("image_top") or self.current_preview_run.get("image_bottom")
        if not image_rel_path:
            if show_messages:
                QMessageBox.warning(
                    self,
                    "缺少对应图像",
                    "当前试验没有归档对应的 2D 图像 (image_top / image_bottom)，无法绘制映射框。",
                )
            return

        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        image_path = os.path.join(project_dir, image_rel_path)
        if not os.path.exists(image_path):
            if show_messages:
                QMessageBox.warning(
                    self,
                    "图像不存在",
                    f"找不到对应的 2D 图像：{image_path}",
                )
            return

        self.btn_map_dross.setEnabled(False)
        self.btn_map_dross.setText("正在识别凸起并映射…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            detection = gui_db.detect_surface_protrusions(
                self.current_pts,
                min_area_mm2=2.0,
                max_regions=1,
            )
            if not detection["regions"]:
                self.btn_map_dross.setText("未发现显著挂渣凸起")
                if show_messages:
                    QMessageBox.information(
                        self,
                        "未发现挂渣",
                        "当前自适应阈值下未发现面积足够的显著凸起。",
                    )
                return
            self.current_dross_mask = gui_db.build_protrusion_region_mask(
                self.current_pts,
                detection,
            )
            self.dross_mask_visible = True
            self._update_point_cloud_view()
            image_roi = gui_db.detect_workpiece_image_roi(image_path)
            mapped = gui_db.map_protrusions_to_image(
                detection,
                image_roi,
                transform="rotate_ccw",
            )
            self.dross_mapping_result = mapped
            self.image_viewer.set_image(image_path, mapped["boxes"])
            # Keep the 3D point cloud visible and show the mapped 2D result in
            # the neighboring pane instead of replacing the point-cloud view.
            self.pc_stack.setCurrentIndex(1)
            self.image_stack.setCurrentIndex(1)
            main_box = mapped["boxes"][0]
            self.btn_map_dross.setText(
                f"已映射挂渣框（峰高 {main_box['max_height_mm']:.3f} mm）"
            )
            existing = self.morphology_output.toPlainText().rstrip()
            mapping_lines = [
                "",
                "3D → 2D 挂渣映射：",
                f"3D 起渣面 mask：{np.count_nonzero(self.current_dross_mask):,} 点（红色）",
                f"自适应凸起阈值：{mapped['threshold_mm']:.3f} mm",
                (
                    "像素框："
                    f"({main_box['x_min']}, {main_box['y_min']}) – "
                    f"({main_box['x_max']}, {main_box['y_max']})"
                ),
                "方向：点云逆时针旋转 90° 后映射到上表面图像",
            ]
            self.morphology_output.setPlainText(existing + "\n".join(mapping_lines))
        except Exception as exc:
            self.btn_map_dross.setText("3D 凸起映射到 2D 挂渣框")
            if show_messages:
                QMessageBox.warning(self, "挂渣映射失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.btn_map_dross.setEnabled(True)

    def _on_toggle_dross_mask_clicked(self):
        mask = getattr(self, "current_dross_mask", None)
        if mask is None or len(mask) != len(self.current_pts):
            return
        self.dross_mask_visible = not self.dross_mask_visible
        self._update_point_cloud_view()

    def _on_reset_pc_clicked(self):
        if not hasattr(self, 'original_pts') or len(self.original_pts) == 0:
            return
        self.current_pts = self.original_pts.copy()
        self.current_dross_mask = None
        self.dross_mask_visible = True
        self.full_surface_result = None
        self.btn_adaptive_core.setText("自适应识别并提取中心切面")
        self.btn_remove_spikes.setText("提取真实切面层（去底面/毛刺）")
        self.btn_remove_spikes.setEnabled(True)
        self.btn_map_dross.setText("3D 凸起映射到 2D 挂渣框")
        self.btn_map_dross.setEnabled(False)
        self.morphology_output.clear()
        self._update_point_cloud_view()

    def _on_auto_scan_clicked(self):
        selected_dir = QFileDialog.getExistingDirectory(self, "选择存放2D图片和3D点云的文件夹")
        if not selected_dir:
            return
            
        res = gui_db.auto_archive_local_directory(selected_dir)
        if res.get("status") == "error":
            QMessageBox.critical(self, "归档失败", res.get("message", "未知错误"))
            return
            
        count = res.get("archived_count", 0)
        details = res.get("details", {})
        
        if count == 0:
            QMessageBox.information(self, "扫描完成", "在该文件夹下未发现任何包含已知试验 ID 并且匹配名称关键字的 2D 或 3D 文件。")
            return
            
        detail_lines = []
        for eid, fields in details.items():
            field_names_zh = []
            for f in fields:
                if "cloud" in f:
                    field_names_zh.append("点云")
                else:
                    field_names_zh.append("图片")
            detail_lines.append(f"• 试验 {eid}: 导入了 {len(fields)} 个文件 ({', '.join(field_names_zh)})")
            
        summary_msg = f"一键归档成功！\n共整理并关联了 {count} 个文件到数据库。\n\n" + "\n".join(detail_lines)
        QMessageBox.information(self, "归档成功", summary_msg)
        
        self.refresh_data()

    def _on_import_luminance_clicked(self):
        if not hasattr(self, "current_preview_run") or not self.current_preview_run:
            QMessageBox.warning(self, "未选择试验", "请先在列表中选中一条试验记录！")
            return
        episode_id = self.current_preview_run.get("episode_id")
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "多选选择基恩士/亮度图文件 (Luminance)",
            "",
            "Image Files (*.tif *.tiff *.png *.jpg *.bmp *.jpeg);;All Files (*)"
        )
        if not file_paths:
            return
        res = gui_db.import_luminance_images(episode_id, file_paths)
        if res.get("status") == "success":
            count = res.get("imported_count", 0)
            slots = ", ".join(res.get("assigned_slots", {}).keys())
            QMessageBox.information(
                self,
                "亮度图多选导入成功",
                f"为试验 [{episode_id}] 成功导入并归档 {count} 个亮度图文件：\n{slots}"
            )
            self.refresh_data()
        else:
            QMessageBox.warning(self, "导入失败", res.get("message", "导入出错"))

    def resizeEvent(self, event):
        super().resizeEvent(event)

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
        self.episode_id_input.setPlaceholderText("例如 SY-n001-v5.5-p8-f8；留空则自动生成")
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
        if hasattr(self, 'preview_trial_combo'):
            self._refresh_preview_trials()

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
            
            # Save any selected local files
            for field_key, file_info in dialog.file_fields.items():
                selected_path = file_info["selected_path"]
                if selected_path:
                    gui_db.save_local_inspection_file(episode_id, field_key, selected_path)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return

        self.analysis_output.setPlainText("检测数据与文件已更新。请点击运行分析以更新极差分析结果。")
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
            color: #e2e8f0;
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
        QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTextEdit {
            background: #0b1220;
            color: #e2e8f0;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 7px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }
        QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border-color: #38bdf8;
        }
        QComboBox QAbstractItemView {
            background-color: #0b1220;
            color: #e2e8f0;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            border: 1px solid #263449;
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
            color: #e2e8f0;
            border: 1px solid #263449;
            border-radius: 6px;
            gridline-color: #1f2a3d;
        }
        QTableWidget::item {
            color: #e2e8f0;
            padding: 5px;
        }
        QTableWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }
        QHeaderView::section {
            background: #162033;
            color: #cbd5e1;
            border: none;
            border-bottom: 1px solid #263449;
            border-right: 1px solid #263449;
            padding: 8px;
            font-weight: 600;
        }
        QTextEdit#analysisOutput {
            color: #dbeafe;
            font-family: Consolas, "Cascadia Mono", monospace;
        }
        QMessageBox {
            background-color: #0f172a;
        }
        QMessageBox QLabel {
            color: #e2e8f0;
        }
        QMessageBox QPushButton {
            background: #2563eb;
            color: #ffffff;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QMessageBox QPushButton:hover {
            background: #1d4ed8;
        }
        QDialog {
            background: #0f172a;
            color: #e2e8f0;
        }
        QCheckBox {
            color: #e2e8f0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            background-color: #0b1220;
            border: 1px solid #334155;
            border-radius: 3px;
        }
        QCheckBox::indicator:checked {
            background-color: #2563eb;
            border-color: #3b82f6;
        }
        QScrollArea {
            border: none;
            background: #0f172a;
        }
        QTabWidget::pane {
            border: 1px solid #263449;
            background: #0f172a;
            border-radius: 6px;
        }
        QTabBar::tab {
            background: #1e293b;
            color: #94a3b8;
            padding: 8px 16px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            border: 1px solid #263449;
            border-bottom: none;
        }
        QTabBar::tab:hover {
            background: #334155;
            color: #ffffff;
        }
        QTabBar::tab:selected {
            background: #0f172a;
            color: #38bdf8;
            font-weight: 600;
            border: 1px solid #263449;
            border-bottom: 1px solid #0f172a;
        }
        QScrollBar:vertical {
            border: none;
            background: #0b1220;
            width: 10px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #1e293b;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background: #334155;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #0b1220;
            height: 10px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:horizontal {
            background: #1e293b;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #334155;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
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
