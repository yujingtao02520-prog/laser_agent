from __future__ import annotations

import math
import os
import sys
import numpy as np
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
            ("point_cloud_dross", "挂渣底面点云"),
            ("image_front", "前切面图像"),
            ("image_back", "后切面图像"),
            ("image_left", "左切面图像"),
            ("image_right", "右切面图像"),
            ("image_top", "上表面图像"),
            ("image_bottom", "下表面图像"),
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

class ImageViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self.label)
        
        self.pixmap = None
        self.zoom_factor = 1.0
        
        # Cursor & Pan states
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.pan_active = False
        self.last_mouse_pos = None
        
    def set_image(self, file_path: str):
        from PyQt6.QtGui import QPixmap
        self.pixmap = QPixmap(file_path)
        self.zoom_factor = 1.0
        self.update_view()
        
    def update_view(self):
        if self.pixmap is None or self.pixmap.isNull():
            self.label.setText("无法加载图片")
            return
            
        # Calculate zoomed size
        target_size = self.pixmap.size() * self.zoom_factor
        scaled_pix = self.pixmap.scaled(
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

class PointCloudViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = np.zeros((0, 3), dtype=np.float32)
        self.points_centered = np.zeros((0, 3), dtype=np.float32)
        self.theta = 0.5  # Yaw angle
        self.phi = 0.5    # Pitch angle
        self.zoom = 1.0
        self.last_mouse_pos = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 300)
        
    def set_points(self, pts: np.ndarray):
        self.points = pts
        if len(pts) > 0:
            # Center the point cloud around its geometric mean
            self.center = np.mean(pts, axis=0)
            self.points_centered = pts - self.center
            # Compute scaling factor to fit inside a unit cube
            max_range = np.max(np.max(self.points_centered, axis=0) - np.min(self.points_centered, axis=0))
            if max_range > 0:
                self.points_centered = self.points_centered / max_range
            else:
                self.points_centered = np.zeros_like(self.points_centered)
        else:
            self.points_centered = np.zeros((0, 3), dtype=np.float32)
        self.update()
        
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
        
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QPen
        from PyQt6.QtCore import QPointF
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        # Slate 900 dark theme canvas
        painter.fillRect(self.rect(), QColor(15, 23, 42))
        
        if len(self.points_centered) == 0:
            painter.setPen(QColor(148, 163, 184))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无三维点云数据或文件未归档")
            return
            
        w = self.width()
        h = self.height()
        scale = min(w, h) * 0.7
        
        # Compute projection transformation
        cos_t, sin_t = np.cos(self.theta), np.sin(self.theta)
        cos_p, sin_p = np.cos(self.phi), np.sin(self.phi)
        
        xs = self.points_centered[:, 0]
        ys = self.points_centered[:, 1]
        zs = self.points_centered[:, 2]
        
        # Rotation around Y axis
        x_rot = xs * cos_t + zs * sin_t
        z_rot1 = -xs * sin_t + zs * cos_t
        
        # Rotation around X axis
        y_rot = ys * cos_p - z_rot1 * sin_p
        z_rot2 = ys * sin_p + z_rot1 * cos_p # Depth
        
        # Orthographic screen mapping
        u_arr = w / 2.0 + x_rot * scale * self.zoom
        v_arr = h / 2.0 - y_rot * scale * self.zoom
        
        # Render layers by depth (Painter's Algorithm)
        num_layers = 8
        if len(z_rot2) > 0:
            indices = np.argsort(z_rot2)
            chunk_size = len(indices) // num_layers + 1
            
            for i in range(num_layers):
                start_idx = i * chunk_size
                end_idx = min(start_idx + chunk_size, len(indices))
                if start_idx >= end_idx:
                    break
                    
                chunk_indices = indices[start_idx:end_idx]
                
                # Depth color gradient: Cyan (56, 189, 248) to Purple (168, 85, 247)
                t = i / (num_layers - 1) if num_layers > 1 else 0.5
                r = int(56 + (168 - 56) * t)
                g = int(189 + (85 - 189) * t)
                b = int(248 + (247 - 248) * t)
                
                painter.setPen(QPen(QColor(r, g, b, 210), 2))
                
                qpoints = [QPointF(u_arr[idx], v_arr[idx]) for idx in chunk_indices]
                painter.drawPoints(qpoints)
                
        # Status overlay
        painter.setPen(QColor(255, 255, 255, 140))
        painter.drawText(15, 25, f"点数: {len(self.points_centered)}")
        painter.drawText(15, 45, f"旋转: Yaw={self.theta:.2f}, Pitch={self.phi:.2f}")
        painter.drawText(15, 65, f"缩放: {self.zoom:.2f}x (滚轮/滑动)")


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
            ("point_cloud_dross", "挂渣底面点云", "3d"),
            ("image_front", "前切面图像", "2d"),
            ("image_back", "后切面图像", "2d"),
            ("image_left", "左切面图像", "2d"),
            ("image_right", "右切面图像", "2d"),
            ("image_top", "上表面图像", "2d"),
            ("image_bottom", "下表面图像", "2d"),
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
        
        # Point Cloud processing controls
        proc_box = QGroupBox("三维点云处理控制台")
        proc_layout = QVBoxLayout(proc_box)
        proc_layout.setSpacing(6)
        
        self.lbl_points_count = QLabel("点数: --")
        self.lbl_bbox_x = QLabel("X 尺寸 (宽): --")
        self.lbl_bbox_y = QLabel("Y 尺寸 (高): --")
        self.lbl_bbox_z = QLabel("Z 尺寸 (深): --")
        
        proc_layout.addWidget(self.lbl_points_count)
        proc_layout.addWidget(self.lbl_bbox_x)
        proc_layout.addWidget(self.lbl_bbox_y)
        proc_layout.addWidget(self.lbl_bbox_z)
        
        btn_layout = QHBoxLayout()
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
        
        btn_layout.addWidget(self.btn_denoise)
        btn_layout.addWidget(self.btn_downsample)
        btn_layout.addWidget(self.btn_reset_pc)
        proc_layout.addLayout(btn_layout)
        
        left_layout.addWidget(proc_box)
        
        # Right Panel: Canvas
        right_panel = QGroupBox("检测结果可视化窗口")
        right_panel.setObjectName("panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        
        self.stacked_view = QStackedWidget()
        
        self.placeholder_lbl = QLabel("请在左侧选择需要预览的检测文件 (.pcd/.asc/.csv/.tif)")
        self.placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_lbl.setStyleSheet("color: #94a3b8; font-size: 14px;")
        self.stacked_view.addWidget(self.placeholder_lbl)
        
        self.pc_viewer = PointCloudViewer()
        self.stacked_view.addWidget(self.pc_viewer)
        
        self.image_viewer = ImageViewer()
        self.stacked_view.addWidget(self.image_viewer)
        
        right_layout.addWidget(self.stacked_view)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([380, 900])
        
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
            "point_cloud_front", "point_cloud_back", "point_cloud_left", "point_cloud_right", "point_cloud_dross",
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
            
            self.btn_denoise.setEnabled(True)
            self.btn_downsample.setEnabled(True)
            self.btn_reset_pc.setEnabled(True)
            
            self.stacked_view.setCurrentIndex(1) # PointCloudViewer
            self._update_point_cloud_view()
        else:
            self.btn_denoise.setEnabled(False)
            self.btn_downsample.setEnabled(False)
            self.btn_reset_pc.setEnabled(False)
            
            self.lbl_points_count.setText("点数: --")
            self.lbl_bbox_x.setText("X 尺寸 (宽): --")
            self.lbl_bbox_y.setText("Y 尺寸 (高): --")
            self.lbl_bbox_z.setText("Z 尺寸 (深): --")
            
            self.stacked_view.setCurrentIndex(2) # ImageViewer
            self.image_viewer.set_image(abs_path)

    def _update_point_cloud_view(self):
        pts = self.current_pts
        self.pc_viewer.set_points(pts)
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
        self._update_point_cloud_view()

    def _on_downsample_clicked(self):
        if not hasattr(self, 'current_pts') or len(self.current_pts) == 0:
            return
        self.current_pts = gui_db.downsample_point_cloud(self.current_pts, target_count=5000)
        self._update_point_cloud_view()

    def _on_reset_pc_clicked(self):
        if not hasattr(self, 'original_pts') or len(self.original_pts) == 0:
            return
        self.current_pts = self.original_pts.copy()
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
        QLineEdit, QDoubleSpinBox, QComboBox, QTextEdit {
            background: #0b1220;
            color: #e2e8f0;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 7px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }
        QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
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
