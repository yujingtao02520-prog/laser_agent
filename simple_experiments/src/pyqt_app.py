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
        self.setWindowTitle(f"Supplement Quality - {run['episode_id']}")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel(f"Inspection Data: {run['episode_id']}")
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

        self.cut_through = QCheckBox("Successfully cut through")
        self.cut_through.setChecked(bool(run.get("cut_through")))

        self.failure_case = QComboBox()
        self.failure_case.addItems(["normal", "incomplete_cut", "overburn", "dross", "unstable_cut"])
        failure = run.get("failure_case") or "normal"
        self.failure_case.setCurrentText(failure if failure in [self.failure_case.itemText(i) for i in range(self.failure_case.count())] else "normal")

        self.kerf_top = self._line("kerf_width_top_mm", "e.g. 1.05")
        self.kerf_bottom = self._line("kerf_width_bottom_mm", "e.g. 0.82")
        self.taper = self._line("taper_mm", "auto/optional")
        self.dross_max = self._line("dross_height_max_mm", "e.g. 0.35")
        self.dross_mean = self._line("dross_height_mean_mm", "e.g. 0.18")
        self.roughness = self._line("roughness_Sa_um", "e.g. 9.8")
        self.defect_area = self._line("defect_area_mm2", "e.g. 0.0")
        self.quality_score = self._line("quality_score", "empty = auto score")
        self.comment = QTextEdit()
        self.comment.setPlaceholderText("Cut surface, dross removability, inspection notes...")
        self.comment.setFixedHeight(78)
        self.comment.setPlainText(run.get("manual_comment") or "")

        form.addRow("", self.cut_through)
        form.addRow("Failure mode", self.failure_case)
        form.addRow("Kerf top (mm)", self.kerf_top)
        form.addRow("Kerf bottom (mm)", self.kerf_bottom)
        form.addRow("Taper (mm)", self.taper)
        form.addRow("Max dross (mm)", self.dross_max)
        form.addRow("Mean dross (mm)", self.dross_mean)
        form.addRow("Roughness Sa (um)", self.roughness)
        form.addRow("Defect area (mm2)", self.defect_area)
        form.addRow("Quality score", self.quality_score)
        form.addRow("Comment", self.comment)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghostButton")
        save = QPushButton("Save Inspection")
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
            QMessageBox.warning(self, "Invalid inspection data", str(exc))
            return
        self.accept()

    def payload(self) -> Dict[str, Any]:
        return {
            "cut_through": self.cut_through.isChecked(),
            "failure_case": self.failure_case.currentText(),
            "kerf_width_top_mm": parse_optional_float(self.kerf_top, "Kerf top"),
            "kerf_width_bottom_mm": parse_optional_float(self.kerf_bottom, "Kerf bottom"),
            "taper_mm": parse_optional_float(self.taper, "Taper"),
            "dross_height_max_mm": parse_optional_float(self.dross_max, "Max dross"),
            "dross_height_mean_mm": parse_optional_float(self.dross_mean, "Mean dross"),
            "roughness_Sa_um": parse_optional_float(self.roughness, "Roughness"),
            "defect_area_mm2": parse_optional_float(self.defect_area, "Defect area"),
            "quality_score": parse_optional_float(self.quality_score, "Quality score"),
            "manual_comment": self.comment.toPlainText().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.runs: List[Dict[str, Any]] = []
        self.setWindowTitle("Laser Cut Copilot - Local Experiment Logger")
        self.resize(1320, 820)

        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        page = QVBoxLayout(root)
        page.setContentsMargins(22, 18, 22, 18)
        page.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Laser Cut Copilot")
        title.setObjectName("appTitle")
        subtitle = QLabel("Local PyQt6 experiment logger for laser cutting trials")
        subtitle.setObjectName("mutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("ghostButton")
        refresh_btn.clicked.connect(self.refresh_data)
        header.addWidget(refresh_btn)
        page.addLayout(header)

        stats = QHBoxLayout()
        self.total_card = StatCard("Total Trials")
        self.penetration_card = StatCard("Penetration Rate")
        self.score_card = StatCard("Average Quality Score")
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
        panel = QGroupBox("Log New Experiment Run")
        panel.setObjectName("panel")
        panel.setMinimumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.power = make_spin(83.0, 0.0, 100.0, 1, 1.0)
        self.speed = make_spin(0.9, 0.1, 10.0, 2, 0.05)
        self.pressure = make_spin(1.5, 0.1, 5.0, 2, 0.05)
        self.focus = make_spin(-9.0, -30.0, 10.0, 1, 0.5)
        self.material = QLineEdit("carbon_steel")
        self.thickness = make_spin(30.0, 0.1, 200.0, 1, 0.5)
        self.gas = QLineEdit("air")
        self.nozzle_height = make_spin(1.0, 0.0, 20.0, 2, 0.1)
        self.nozzle_diameter = make_spin(4.0, 0.1, 20.0, 2, 0.1)

        form.addRow("Laser power (%)", self.power)
        form.addRow("Cut speed (m/min)", self.speed)
        form.addRow("Gas pressure (MPa)", self.pressure)
        form.addRow("Focus (mm)", self.focus)
        form.addRow("Material", self.material)
        form.addRow("Thickness (mm)", self.thickness)
        form.addRow("Assist gas", self.gas)
        form.addRow("Nozzle height (mm)", self.nozzle_height)
        form.addRow("Nozzle dia. (mm)", self.nozzle_diameter)
        layout.addLayout(form)

        save = QPushButton("Save Run Parameters")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.add_run)
        layout.addWidget(save)
        layout.addStretch()

        return panel

    def _build_table_panel(self) -> QWidget:
        panel = QGroupBox("Experiment Runs Log")
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Episode ID",
                "Power",
                "Speed",
                "Pressure",
                "Focus",
                "Cut Through",
                "Failure",
                "Score",
                "Actions",
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
        self.table.setColumnWidth(8, 210)
        layout.addWidget(self.table)

        return panel

    def _build_analysis_panel(self) -> QWidget:
        panel = QGroupBox("Orthogonal Range Analysis")
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        run_btn = QPushButton("Run Range Analysis")
        run_btn.setObjectName("primaryButton")
        run_btn.clicked.connect(self.run_analysis)
        toolbar.addWidget(run_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.analysis_output = QTextEdit()
        self.analysis_output.setObjectName("analysisOutput")
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setFixedHeight(170)
        self.analysis_output.setPlainText("Run analysis after recording or editing inspection data.")
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
        self.score_card.set_value(f"{sum(scored) / len(scored):.1f} / 100" if scored else "No scores")

    def _refresh_table(self):
        self.table.setRowCount(len(self.runs))

        for row_idx, run in enumerate(self.runs):
            values = [
                run.get("episode_id"),
                f"{format_value(float(run.get('power_kw')) / 0.6 if run.get('power_kw') is not None else None, 1)}%",
                f"{format_value(run.get('speed_m_min'))} m/min",
                f"{format_value(run.get('air_pressure_mpa'))} MPa",
                f"{format_value(run.get('focus_mm'))} mm",
                "Yes" if run.get("cut_through") else "No",
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
        layout.setSpacing(8)

        edit = QPushButton("Quality")
        edit.setObjectName("smallButton")
        edit.clicked.connect(lambda _, eid=episode_id: self.edit_quality(eid))

        delete = QPushButton("Delete")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(lambda _, eid=episode_id: self.delete_run(eid))

        layout.addWidget(edit)
        layout.addWidget(delete)
        layout.addStretch()
        return holder

    def add_run(self):
        params = {
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
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        self.refresh_data()
        run = self._find_run(episode_id)
        if run:
            self.edit_quality(episode_id)

    def edit_quality(self, episode_id: str):
        run = self._find_run(episode_id)
        if not run:
            QMessageBox.warning(self, "Missing run", f"Episode {episode_id} was not found.")
            return

        dialog = QualityDialog(run, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            gui_db.update_run_quality(episode_id, dialog.payload())
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        self.analysis_output.setPlainText("Inspection data changed. Run analysis again for updated results.")
        self.refresh_data()

    def delete_run(self, episode_id: str):
        answer = QMessageBox.question(
            self,
            "Delete experiment",
            f"Delete experiment {episode_id} from the local database and CSV log?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = gui_db.delete_run(episode_id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Missing run", f"Episode {episode_id} was not found.")
            return

        self.analysis_output.setPlainText("A run was deleted. Run analysis again for updated results.")
        self.refresh_data()

    def run_analysis(self):
        report = self._build_analysis_report()
        if report["status"] == "warning":
            QMessageBox.warning(self, "Analysis unavailable", report["message"])
            self.analysis_output.setPlainText(report["message"])
            return
        self.analysis_output.setPlainText(report["text"])

    def _build_analysis_report(self) -> Dict[str, str]:
        if not os.path.exists(gui_db.CSV_FILE):
            return {"status": "warning", "message": "No experiment log CSV file found."}

        df = pd.read_csv(gui_db.CSV_FILE)
        if len(df) < 3:
            return {"status": "warning", "message": "Add at least 3 runs before range analysis."}

        df = df.dropna(subset=FACTORS)
        scored = df.dropna(subset=["quality_score"]) if "quality_score" in df.columns else pd.DataFrame()
        if df.empty or scored.empty:
            return {"status": "warning", "message": "No scored runs are available for analysis."}

        best = scored.sort_values("quality_score", ascending=False).iloc[0]
        lines = [
            "Best observed trial",
            (
                f"  {best['episode_id']}: score {float(best['quality_score']):.1f}, "
                f"{float(best['power_kw']) / 0.6:.1f}%, {float(best['speed_m_min']):.2f} m/min, "
                f"{float(best['air_pressure_mpa']):.2f} MPa, focus {float(best['focus_mm']):.1f} mm"
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

            lines.append(f"{metric}")
            for factor, range_value in sorted(ranges.items(), key=lambda item: item[1], reverse=True):
                r_val = range_value
                b_lvl = best_levels[factor]
                if factor == "power_kw":
                    r_val = round(r_val / 0.6, 3)
                    b_lvl = round(b_lvl / 0.6, 3)
                    lines.append(f"  {factor}: R={r_val}%, best={b_lvl}%")
                else:
                    lines.append(f"  {factor}: R={r_val}, best={b_lvl}")
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
