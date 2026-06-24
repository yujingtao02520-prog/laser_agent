import os
import sys

# Fix TCL/TK library path issue in virtual environments on Windows
if sys.platform.startswith("win"):
    tcl_dir = os.path.join(sys.base_prefix, "tcl", "tcl8.6")
    tk_dir = os.path.join(sys.base_prefix, "tcl", "tk8.6")
    if os.path.exists(tcl_dir):
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.exists(tk_dir):
        os.environ["TK_LIBRARY"] = tk_dir

import json
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
import logging
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# Ensure workspace root is on PATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend import db, vision, recommender, optimizer, llm_client
import threading

# Set theme and color options
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class RunningParams:
    def __init__(self):
        self.power = 0
        self.speed = 0
        self.gasType = "N2"
        self.pressure = 0.0
        self.focus = 0.0
        self.nozzle = "1.5"
        self.compensation = 0.0
        self.piercing = "pulse"

def pad_visual(text, width, align="left"):
    visual_len = 0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            visual_len += 2
        else:
            visual_len += 1
    
    pad_needed = max(0, width - visual_len)
    if align == "left":
        return text + " " * pad_needed
    elif align == "right":
        return " " * pad_needed + text
    else:
        return " " * (pad_needed // 2) + text + " " * (pad_needed - pad_needed // 2)

class LaserCuttingCopilotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Configurations
        self.title("激光切割工艺 Copilot - 智能决策系统")
        self.geometry("1600x920")
        self.resizable(True, True)

        # State Variables
        self.materials_map = {}
        self.selected_material = "SUS304"
        self.selected_thickness = 3.0
        self.precheck_done = False
        self.precheck_data = None
        self.recommendation_data = None
        self.last_report = None
        self.tuning_history = []
        self.pending_suggestions = []

        self.running_params = RunningParams()

        # Initialize Data
        self.load_materials_data()

        # Grid Layout Setup
        # Columns: Sidebar (300), Center Work Area (1.0 weight), Right Control Panel (500)
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1, minsize=680)
        self.grid_columnconfigure(2, weight=0, minsize=500)
        self.grid_rowconfigure(0, weight=1)
        self.grid_propagate(False)

        # Build Panels
        self.create_sidebar()
        self.create_center_area()
        self.create_right_panel()

        # Draw Initial Visuals
        self.draw_clean_precut_canvas()
        self.draw_clean_postcut_canvas()
        self.draw_empty_warp_chart()
        self.draw_empty_trend_chart()

        # Bind closing event to clear resources
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Handle window resize and font scaling
        self.original_width = 1600
        self.original_height = 920
        self.register_fonts()
        self.bind("<Configure>", self.on_window_configure)

    def load_materials_data(self):
        # Fetch materials and thicknesses from db
        recipes = db.get_all_recipes()
        materials = list(set([r["material"] for r in recipes]))
        for mat in materials:
            self.materials_map[mat] = sorted(list(set([r["thickness"] for r in recipes if r["material"] == mat])))

    def on_closing(self):
        plt.close('all')
        self.destroy()

    def register_fonts(self, widget=None):
        if widget is None:
            widget = self
            self.font_registry = {} # maps font_obj_id -> (font_obj, original_size)
            self.widget_fonts = {}  # maps widget -> (original_font, original_size)
            
        try:
            font_obj = widget.cget("font")
            if font_obj:
                if hasattr(font_obj, "cget"): # It's a CTkFont
                    font_id = id(font_obj)
                    if font_id not in self.font_registry:
                        try:
                            size = font_obj.cget("size")
                            self.font_registry[font_id] = (font_obj, size)
                        except Exception:
                            pass
                else: # It's a tuple, string, or list
                    size = None
                    if isinstance(font_obj, (list, tuple)) and len(font_obj) >= 2:
                        try:
                            size = int(font_obj[1])
                        except ValueError:
                            pass
                    elif isinstance(font_obj, str):
                        parts = font_obj.split()
                        if len(parts) >= 2 and parts[-1].lstrip('-').isdigit():
                            size = abs(int(parts[-1]))
                    if size is not None:
                        self.widget_fonts[widget] = (font_obj, size)
        except Exception:
            pass
            
        for child in widget.winfo_children():
            self.register_fonts(child)

    def on_window_configure(self, event):
        if event.widget == self:
            w = event.width
            h = event.height
            if w <= 100 or h <= 100:
                return # Skip initial/unmapped state or minimized window
            
            # Calculate scaling factor based on current dimensions relative to design dimensions (1600x920)
            w_scale = w / self.original_width
            h_scale = h / self.original_height
            scale_factor = min(w_scale, h_scale)
            
            # Bound the scale factor to prevent text from becoming too tiny or huge
            scale_factor = max(0.75, min(1.5, scale_factor))
            
            # 1. Update all registered CTkFont objects
            for font_id, (font_obj, original_size) in self.font_registry.items():
                try:
                    new_size = int(original_size * scale_factor)
                    new_size = max(8, new_size)
                    font_obj.configure(size=new_size)
                except Exception:
                    pass
                
            # 2. Update all registered widgets with tuple/string fonts
            for widget, (original_font, original_size) in self.widget_fonts.items():
                try:
                    new_size = int(original_size * scale_factor)
                    new_size = max(8, new_size)
                    if isinstance(original_font, (list, tuple)):
                        new_font = list(original_font)
                        new_font[1] = new_size
                        widget.configure(font=tuple(new_font))
                    elif isinstance(original_font, str):
                        parts = original_font.split()
                        parts[-1] = str(new_size)
                        widget.configure(font=" ".join(parts))
                except Exception:
                    pass

    # ==========================================


    # PANEL CREATION: SIDEBAR (LEFT)


    # ==========================================
    def create_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=300, corner_radius=16, fg_color="#0b0f19", border_color="#1e293b", border_width=1)
        sidebar.grid(row=0, column=0, padx=(15, 5), pady=15, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        
        # System Logo Area
        logo_label = ctk.CTkLabel(sidebar, text="⚡ LASER COPILOT", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), text_color="#06b6d4")
        logo_label.pack(padx=20, pady=(25, 2))
        
        sub_label = ctk.CTkLabel(sidebar, text="激光切割智能决策系统", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        sub_label.pack(padx=20, pady=(0, 20))

        # Status indicators
        self.create_status_indicators(sidebar)

        # Form Controls Frame
        form_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        form_frame.pack(fill="x", padx=20, pady=10)

        # 1. Material Select
        mat_label = ctk.CTkLabel(form_frame, text="板材材质", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f8fafc")
        mat_label.pack(anchor="w", pady=(5, 2))
        
        mat_options = list(self.materials_map.keys())
        self.mat_menu = ctk.CTkOptionMenu(form_frame, values=mat_options, command=self.on_material_change, fg_color="#131b32", button_color="#0f172a", text_color="#f8fafc", dropdown_fg_color="#0d1324")
        self.mat_menu.pack(fill="x", pady=(0, 10))
        self.mat_menu.set("SUS304")

        # 2. Thickness Select
        thick_label = ctk.CTkLabel(form_frame, text="板材厚度 (mm)", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f8fafc")
        thick_label.pack(anchor="w", pady=(5, 2))
        
        self.thick_menu = ctk.CTkOptionMenu(form_frame, command=self.on_thickness_change, fg_color="#131b32", button_color="#0f172a", text_color="#f8fafc", dropdown_fg_color="#0d1324")
        self.thick_menu.pack(fill="x", pady=(0, 10))
        self.update_thickness_options("SUS304")

        # 3. Drawing Select
        draw_label = ctk.CTkLabel(form_frame, text="切割图纸 (DXF)", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f8fafc")
        draw_label.pack(anchor="w", pady=(5, 2))
        
        self.draw_menu = ctk.CTkOptionMenu(form_frame, values=["法兰盘 (flange.dxf)", "机械齿轮 (gear.dxf)", "固定支架 (bracket.dxf)"], fg_color="#131b32", button_color="#0f172a", text_color="#f8fafc", dropdown_fg_color="#0d1324")
        self.draw_menu.pack(fill="x", pady=(0, 20))

        # Hardware limits box
        self.create_hardware_limits(sidebar)

        # Trigger Buttons
        self.btn_precheck = ctk.CTkButton(sidebar, text="第一步：板材切前检测", font=ctk.CTkFont(size=13, weight="bold"), height=40, fg_color="#1e293b", hover_color="#334155", text_color="#f1f5f9", command=self.trigger_precut_check)
        self.btn_precheck.pack(fill="x", padx=20, pady=(20, 10))

        self.btn_recommend = ctk.CTkButton(sidebar, text="第二步：生成工艺推荐", font=ctk.CTkFont(size=13, weight="bold"), height=40, fg_color="#06b6d4", hover_color="#0891b2", text_color="#ffffff", state="disabled", command=self.trigger_recommendation)
        self.btn_recommend.pack(fill="x", padx=20, pady=10)

    def create_status_indicators(self, parent):
        indicator_frame = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=10)
        indicator_frame.pack(fill="x", padx=20, pady=10)
        
        l_lbl = ctk.CTkLabel(indicator_frame, text="● 激光发生器: 准备就绪", font=ctk.CTkFont(size=11), text_color="#10b981")
        l_lbl.pack(anchor="w", padx=10, pady=(8, 2))
        
        g_lbl = ctk.CTkLabel(indicator_frame, text="● 气路供应端: 正常", font=ctk.CTkFont(size=11), text_color="#10b981")
        g_lbl.pack(anchor="w", padx=10, pady=2)
        
        h_lbl = ctk.CTkLabel(indicator_frame, text="● 随动高度计: 已校准", font=ctk.CTkFont(size=11), text_color="#10b981")
        h_lbl.pack(anchor="w", padx=10, pady=(2, 8))

    def create_hardware_limits(self, parent):
        lim_frame = ctk.CTkFrame(parent, fg_color="#05070f", corner_radius=10)
        lim_frame.pack(fill="x", padx=20, pady=10)
        
        title = ctk.CTkLabel(lim_frame, text="设备硬件约束", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        title.pack(anchor="w", padx=10, pady=(8, 2))
        
        p_limit = ctk.CTkLabel(lim_frame, text="最大功率: 6000 W", font=ctk.CTkFont(family="JetBrains Mono", size=11), text_color="#06b6d4")
        p_limit.pack(anchor="w", padx=10, pady=2)
        
        g_limit = ctk.CTkLabel(lim_frame, text="最大气压: 20 bar", font=ctk.CTkFont(family="JetBrains Mono", size=11), text_color="#06b6d4")
        g_limit.pack(anchor="w", padx=10, pady=(2, 8))

    def update_thickness_options(self, material):
        thicknesses = self.materials_map.get(material, [1.0, 2.0, 3.0])
        thick_vals = [f"{t:.1f}" for t in thicknesses]
        self.thick_menu.configure(values=thick_vals)
        if "3.0" in thick_vals:
            self.thick_menu.set("3.0")
            self.selected_thickness = 3.0
        else:
            self.thick_menu.set(thick_vals[0])
            self.selected_thickness = thicknesses[0]

    def on_material_change(self, value):
        self.selected_material = value
        self.update_thickness_options(value)
        self.reset_workflow()

    def on_thickness_change(self, value):
        self.selected_thickness = float(value)
        self.reset_workflow()

    def reset_workflow(self):
        self.precheck_done = False
        self.precheck_data = None
        self.recommendation_data = None
        self.last_report = None
        self.tuning_history = []
        self.pending_suggestions = []
        
        self.btn_recommend.configure(state="disabled")
        self.btn_cut.configure(state="disabled")
        self.btn_apply_tune.configure(state="disabled")
        
        self.draw_clean_precut_canvas()
        self.draw_clean_postcut_canvas()
        self.draw_empty_warp_chart()
        self.draw_empty_trend_chart()
        
        self.precheck_badge.configure(text="等待检测...", fg_color="#0d1b3e", text_color="#3b82f6")
        self.precheck_warning_text.configure(state="normal")
        self.precheck_warning_text.delete("1.0", "end")
        self.precheck_warning_text.insert("end", "请先在侧边栏触发板材切前检测，以评估板面翘曲及表面污染风险。")
        self.precheck_warning_text.configure(state="disabled")

        self.conf_val_lbl.configure(text="--")
        self.conf_canvas.delete("all")
        self.draw_empty_confidence_gauge()
        
        self.log_console.configure(state="normal")
        self.log_console.delete("1.0", "end")
        self.log_console.insert("end", "// 等待任务设置完成。大模型智能体与工艺数据库检索推导日志将在此实时输出...")
        self.log_console.configure(state="disabled")
        
        self.disable_parameter_sliders()
        self.reset_sliders_labels()
        
        self.score_lbl.configure(text="--")
        self.draw_empty_score_gauge()
        
        self.dross_lbl.configure(text="--")
        self.burn_lbl.configure(text="--")
        self.kerf_lbl.configure(text="--")
        self.rough_lbl.configure(text="--")
        
        self.postcheck_summary_text.configure(state="normal")
        self.postcheck_summary_text.delete("1.0", "end")
        self.postcheck_summary_text.insert("end", "// 试切完成后，此处将实时展示质量评估报告与缺陷归因诊断。")
        self.postcheck_summary_text.configure(state="disabled")

        self.advice_console.configure(state="normal")
        self.advice_console.delete("1.0", "end")
        self.advice_console.insert("end", "等待首轮切割报告。若切割指标不佳，智能体将在此进行多维诊断并输出调参偏置建议。")
        self.advice_console.configure(state="disabled")

    # ==========================================


    # PANEL CREATION: CENTER WORK AREA


    # ==========================================
    def create_center_area(self):
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.grid(row=0, column=1, padx=10, pady=15, sticky="nsew")
        center_frame.grid_columnconfigure(0, weight=1)
        center_frame.grid_rowconfigure(0, weight=3) # Row 0: Pre-cut (needs most space for 3-col layout)
        center_frame.grid_rowconfigure(1, weight=3) # Row 1: Post-cut (equal to precut)
        center_frame.grid_rowconfigure(2, weight=4) # Row 2: Analysis & Trend (charts + log)
        
        # ==========================================
        # 1. Precheck Panel (Row 0)
        # ==========================================
        precheck_panel = ctk.CTkFrame(center_frame, corner_radius=16, border_color="#1e293b", border_width=1)
        precheck_panel.grid(row=0, column=0, padx=0, pady=(0, 10), sticky="nsew")
        
        title_pre = ctk.CTkLabel(precheck_panel, text="[01] 视觉感知：切前检测 (2D/3D)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#06b6d4")
        title_pre.pack(anchor="w", padx=15, pady=(12, 4))

        precheck_body_frame = ctk.CTkFrame(precheck_panel, fg_color="transparent")
        precheck_body_frame.pack(fill="both", expand=True, padx=15, pady=(0, 12))
        precheck_body_frame.grid_columnconfigure(0, weight=0, minsize=160)
        precheck_body_frame.grid_columnconfigure(1, weight=1, minsize=200)
        precheck_body_frame.grid_columnconfigure(2, weight=1, minsize=200)
        precheck_body_frame.grid_rowconfigure(0, weight=1)
        
        # Column 0: 2D Scanner Canvas
        left_precheck = ctk.CTkFrame(precheck_body_frame, fg_color="transparent")
        left_precheck.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        lbl_2d = ctk.CTkLabel(left_precheck, text="2D 表面缺陷相机", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_2d.pack(anchor="w")
        self.precut_canvas = tk.Canvas(left_precheck, width=150, height=100, bg="#02040a", highlightthickness=1, highlightbackground="#1e293b")
        self.precut_canvas.pack(pady=2)
        self.precheck_badge = ctk.CTkLabel(left_precheck, text="等待检测...", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#0d1b3e", text_color="#3b82f6", corner_radius=4)
        self.precheck_badge.pack(fill="x", pady=2)

        # Column 1: 3D Flatness Graph
        middle_precheck = ctk.CTkFrame(precheck_body_frame, fg_color="transparent")
        middle_precheck.grid(row=0, column=1, padx=(0, 10), sticky="nsew")
        lbl_3d = ctk.CTkLabel(middle_precheck, text="3D 表面翘曲高度 (mm)", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_3d.pack(anchor="w")
        self.fig_warp = plt.Figure(figsize=(3.2, 1.2), facecolor='#0f172a')
        self.ax_warp = self.fig_warp.add_subplot(111)
        self.canvas_warp = FigureCanvasTkAgg(self.fig_warp, master=middle_precheck)
        self.canvas_warp.get_tk_widget().pack(fill="both", expand=True, pady=2)

        # Column 2: Warnings box
        right_precheck = ctk.CTkFrame(precheck_body_frame, fg_color="transparent")
        right_precheck.grid(row=0, column=2, sticky="nsew")
        lbl_warn = ctk.CTkLabel(right_precheck, text="分析与警告日志", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_warn.pack(anchor="w")
        self.precheck_warning_text = ctk.CTkTextbox(right_precheck, font=ctk.CTkFont(size=11), fg_color="#090d16", text_color="#94a3b8", border_width=1, border_color="#1e293b")
        self.precheck_warning_text.pack(fill="both", expand=True, pady=2)
        self.precheck_warning_text.insert("end", "请先在侧边栏触发板材切前检测，以评估板面翘曲及表面污染风险。")
        self.precheck_warning_text.configure(state="disabled")

        # ==========================================
        # 2. Postcheck Panel (Row 1)
        # ==========================================
        postcheck_panel = ctk.CTkFrame(center_frame, corner_radius=16, border_color="#1e293b", border_width=1)
        postcheck_panel.grid(row=1, column=0, padx=0, pady=5, sticky="nsew")
        
        title_post = ctk.CTkLabel(postcheck_panel, text="[02] 视觉反馈：切缝分析与综合质量反馈", font=ctk.CTkFont(size=14, weight="bold"), text_color="#06b6d4")
        title_post.pack(anchor="w", padx=15, pady=(12, 4))

        postcheck_body_frame = ctk.CTkFrame(postcheck_panel, fg_color="transparent")
        postcheck_body_frame.pack(fill="both", expand=True, padx=15, pady=(0, 12))
        postcheck_body_frame.grid_columnconfigure(0, weight=0, minsize=110)
        postcheck_body_frame.grid_columnconfigure(1, weight=0, minsize=190)
        postcheck_body_frame.grid_columnconfigure(2, weight=1)
        postcheck_body_frame.grid_columnconfigure(3, weight=1)
        postcheck_body_frame.grid_rowconfigure(0, weight=1)

        # Column 0: Score Dial
        col0_post = ctk.CTkFrame(postcheck_body_frame, fg_color="#090d16", corner_radius=10)
        col0_post.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        col0_post.grid_propagate(False)
        self.score_canvas = tk.Canvas(col0_post, width=70, height=70, bg="#0b0f19", highlightthickness=0)
        self.score_canvas.pack(pady=(12, 0))
        self.score_lbl = ctk.CTkLabel(col0_post, text="--", font=ctk.CTkFont(family="JetBrains Mono", size=18, weight="bold"), text_color="#f43f5e")
        self.score_lbl.place(x=55, y=47, anchor="center")
        s_lbl = ctk.CTkLabel(col0_post, text="质量综合评分", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        s_lbl.pack(pady=(4, 5))

        # Column 1: 2D cut seam visual
        col1_post = ctk.CTkFrame(postcheck_body_frame, fg_color="transparent")
        col1_post.grid(row=0, column=1, padx=(0, 10), sticky="nsew")
        lbl_cut = ctk.CTkLabel(col1_post, text="切缝质量相机成像", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_cut.pack(anchor="w")
        self.postcut_canvas = tk.Canvas(col1_post, width=170, height=92, bg="#02040a", highlightthickness=1, highlightbackground="#1e293b")
        self.postcut_canvas.pack(fill="x", pady=2)

        # Column 2: 3D Metrology Metrics
        col2_post = ctk.CTkFrame(postcheck_body_frame, fg_color="#090d16", corner_radius=8)
        col2_post.grid(row=0, column=2, padx=(0, 10), sticky="nsew")
        lbl_m = ctk.CTkLabel(col2_post, text="3D测高物理量测：", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        lbl_m.pack(anchor="w", padx=10, pady=(5, 2))
        
        metrics_grid = ctk.CTkFrame(col2_post, fg_color="transparent")
        metrics_grid.pack(fill="both", expand=True, padx=5, pady=2)
        metrics_grid.grid_columnconfigure(0, weight=1)
        metrics_grid.grid_columnconfigure(1, weight=1)
        
        self.dross_lbl = self.add_metric_item(metrics_grid, "挂渣 (Dross):", 0, 0)
        self.burn_lbl = self.add_metric_item(metrics_grid, "溶边 (Burn):", 0, 1)
        self.kerf_lbl = self.add_metric_item(metrics_grid, "割缝 (Kerf):", 1, 0)
        self.rough_lbl = self.add_metric_item(metrics_grid, "粗糙 (Ra):", 1, 1)

        # Column 3: Inspection Text summary
        col3_post = ctk.CTkFrame(postcheck_body_frame, fg_color="transparent")
        col3_post.grid(row=0, column=3, sticky="nsew")
        lbl_sum = ctk.CTkLabel(col3_post, text="质量评估报告与归因", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_sum.pack(anchor="w")
        self.postcheck_summary_text = ctk.CTkTextbox(col3_post, font=ctk.CTkFont(size=11), fg_color="#16080b", text_color="#f1f5f9", border_width=1, border_color="#311018")
        self.postcheck_summary_text.pack(fill="both", expand=True, pady=2)
        self.postcheck_summary_text.insert("end", "// 试切完成后，此处将实时展示质量评估报告与缺陷归因诊断。")
        self.postcheck_summary_text.configure(state="disabled")

        # ==========================================
        # 3. Analysis & Trend Panel (Row 2)
        # ==========================================
        analysis_panel = ctk.CTkFrame(center_frame, corner_radius=16, border_color="#1e293b", border_width=1)
        analysis_panel.grid(row=2, column=0, padx=0, pady=(5, 0), sticky="nsew")
        
        title_analysis = ctk.CTkLabel(analysis_panel, text="[03] 智能诊断：优化趋势与推理链控制台", font=ctk.CTkFont(size=14, weight="bold"), text_color="#06b6d4")
        title_analysis.pack(anchor="w", padx=15, pady=(12, 4))

        analysis_body_frame = ctk.CTkFrame(analysis_panel, fg_color="transparent")
        analysis_body_frame.pack(fill="both", expand=True, padx=15, pady=(0, 12))
        analysis_body_frame.grid_columnconfigure(0, weight=0, minsize=110)
        analysis_body_frame.grid_columnconfigure(1, weight=1)
        analysis_body_frame.grid_columnconfigure(2, weight=1)
        analysis_body_frame.grid_rowconfigure(0, weight=1)

        # Column 0: Confidence Dial
        col0_an = ctk.CTkFrame(analysis_body_frame, fg_color="#090d16", corner_radius=10)
        col0_an.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        col0_an.grid_propagate(False)
        self.conf_canvas = tk.Canvas(col0_an, width=70, height=70, bg="#0b0f19", highlightthickness=0)
        self.conf_canvas.pack(pady=(12, 0))
        self.conf_val_lbl = ctk.CTkLabel(col0_an, text="--", font=ctk.CTkFont(family="JetBrains Mono", size=13, weight="bold"), text_color="#06b6d4")
        self.conf_val_lbl.place(x=55, y=47, anchor="center")
        c_lbl = ctk.CTkLabel(col0_an, text="推荐置信度", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        c_lbl.pack(pady=(4, 5))

        # Column 1: Matplotlib trend chart (Iteration Curve)
        col1_an = ctk.CTkFrame(analysis_body_frame, fg_color="transparent")
        col1_an.grid(row=0, column=1, padx=(0, 10), sticky="nsew")
        lbl_trend = ctk.CTkLabel(col1_an, text="闭环质量优化趋势 (Iteration Curve)", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_trend.pack(anchor="w")
        self.fig_trend = plt.Figure(figsize=(3.5, 1.2), facecolor='#0f172a')
        self.ax_trend = self.fig_trend.add_subplot(111)
        self.canvas_trend = FigureCanvasTkAgg(self.fig_trend, master=col1_an)
        self.canvas_trend.get_tk_widget().pack(fill="both", expand=True, pady=2)

        # Column 2: Decision Log Console
        col2_an = ctk.CTkFrame(analysis_body_frame, fg_color="transparent")
        col2_an.grid(row=0, column=2, sticky="nsew")
        log_lbl = ctk.CTkLabel(col2_an, text="决策推理引擎日志：", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        log_lbl.pack(anchor="w")
        self.log_console = ctk.CTkTextbox(col2_an, font=ctk.CTkFont(family="JetBrains Mono", size=10), fg_color="#020409", text_color="#a7f3d0", border_width=1, border_color="#1e293b")
        self.log_console.pack(fill="both", expand=True, pady=2)
        self.log_console.insert("end", "// 等待任务设置完成。大模型智能体与工艺数据库检索推导日志将在此实时输出...")
        self.log_console.configure(state="disabled")

    def add_metric_item(self, parent, label_text, r, c):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=r, column=c, padx=5, pady=4, sticky="nsew")
        parent.grid_columnconfigure(c, weight=1)
        
        lbl = ctk.CTkLabel(f, text=label_text, font=ctk.CTkFont(size=10), text_color="#64748b")
        lbl.pack(anchor="w")
        val = ctk.CTkLabel(f, text="--", font=ctk.CTkFont(family="JetBrains Mono", size=11, weight="bold"), text_color="#06b6d4")
        val.pack(anchor="w")
        return val

    def setup_parameter_widgets(self):
        # Power
        self.grp_p = self.create_slider_row("🔥 激光功率 (W)", 500, 6000, self.on_power_slide, 0, 0, columnspan=2)
        # Speed
        self.grp_s = self.create_slider_row("🚀 切割速度 (mm/min)", 100, 25000, self.on_speed_slide, 1, 0, columnspan=2)
        # Gas pressure
        self.grp_pr = self.create_slider_row("💨 辅助气压 (bar)", 0.1, 20.0, self.on_pressure_slide, 2, 0, is_float=True, columnspan=2)
        # Focus
        self.grp_f = self.create_slider_row("🎯 焦点位置 (mm)", -8.0, 8.0, self.on_focus_slide, 3, 0, is_float=True, columnspan=2)

        # Gas Type dropdown
        f_g = ctk.CTkFrame(self.sliders_frame, fg_color="transparent")
        f_g.grid(row=4, column=0, padx=8, pady=5, sticky="nsew")
        l_g = ctk.CTkLabel(f_g, text="💨 气体类型", font=ctk.CTkFont(size=11, weight="bold"), text_color="#e2e8f0")
        l_g.pack(anchor="w")
        self.gas_menu = ctk.CTkOptionMenu(f_g, values=["N2", "O2", "Air"], height=28, fg_color="#131b32", button_color="#0f172a", text_color="#06b6d4", state="disabled", command=self.on_gas_change)
        self.gas_menu.pack(fill="x", pady=2)

        # Piercing Method dropdown
        f_p = ctk.CTkFrame(self.sliders_frame, fg_color="transparent")
        f_p.grid(row=4, column=1, padx=8, pady=5, sticky="nsew")
        l_p = ctk.CTkLabel(f_p, text="📍 穿孔方式", font=ctk.CTkFont(size=11, weight="bold"), text_color="#e2e8f0")
        l_p.pack(anchor="w")
        self.piercing_menu = ctk.CTkOptionMenu(f_p, values=["direct", "pulse", "stage"], height=28, fg_color="#131b32", button_color="#0f172a", text_color="#06b6d4", state="disabled", command=self.on_piercing_change)
        self.piercing_menu.pack(fill="x", pady=2)

        # Nozzle & Compensation
        f_n = ctk.CTkFrame(self.sliders_frame, fg_color="transparent")
        f_n.grid(row=5, column=0, columnspan=2, padx=8, pady=5, sticky="nsew")
        l_n = ctk.CTkLabel(f_n, text="⭕ 喷嘴直径 / 割缝半径补偿 (mm)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#e2e8f0")
        l_n.pack(anchor="w")
        
        inputs_layout = ctk.CTkFrame(f_n, fg_color="transparent")
        inputs_layout.pack(fill="x", pady=2)
        
        self.nozzle_ent = ctk.CTkEntry(inputs_layout, height=28, font=ctk.CTkFont(family="JetBrains Mono", size=11), fg_color="#131b32", text_color="#06b6d4", border_color="#1e293b", state="disabled")
        self.nozzle_ent.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.comp_ent = ctk.CTkEntry(inputs_layout, height=28, font=ctk.CTkFont(family="JetBrains Mono", size=11), fg_color="#131b32", text_color="#06b6d4", border_color="#1e293b", state="disabled")
        self.comp_ent.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def create_slider_row(self, title, min_v, max_v, callback, r, c, is_float=False, columnspan=1):
        frame = ctk.CTkFrame(self.sliders_frame, fg_color="transparent")
        frame.grid(row=r, column=c, columnspan=columnspan, padx=8, pady=5, sticky="nsew")
        
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x")
        lbl = ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#e2e8f0")
        lbl.pack(side="left")
        
        val_ent = ctk.CTkEntry(hdr, width=80, height=20, font=ctk.CTkFont(family="JetBrains Mono", size=11, weight="bold"), fg_color="#131b32", border_color="#1e293b", text_color="#06b6d4", justify="right")
        val_ent.insert(0, "--")
        val_ent.configure(state="disabled")
        val_ent.pack(side="right")
        
        slider = ctk.CTkSlider(frame, from_=min_v, to=max_v, number_of_steps=100 if is_float else int(max_v - min_v), command=callback, state="disabled", height=14)
        slider.pack(fill="x", pady=4)
        
        def on_entry_commit(event=None):
            val_str = val_ent.get().strip()
            try:
                # Strip units
                val_str = val_str.replace("W", "").replace("mm/min", "").replace("bar", "").replace("mm", "").strip()
                val = float(val_str)
                val = max(min_v, min(max_v, val))
                slider.set(val)
                callback(val)
            except ValueError:
                # Revert
                callback(slider.get())
                
        val_ent.bind("<Return>", on_entry_commit)
        val_ent.bind("<FocusOut>", on_entry_commit)
        
        return {"slider": slider, "entry": val_ent, "is_float": is_float}

    def set_entry_value(self, entry_widget, text):
        current_state = entry_widget.cget("state")
        entry_widget.configure(state="normal")
        entry_widget.delete(0, "end")
        entry_widget.insert(0, text)
        entry_widget.configure(state=current_state)

    def on_power_slide(self, val):
        self.running_params.power = round(val / 50.0) * 50.0
        self.set_entry_value(self.grp_p["entry"], f"{self.running_params.power:.0f} W")

    def on_speed_slide(self, val):
        self.running_params.speed = round(val / 10.0) * 10.0
        self.set_entry_value(self.grp_s["entry"], f"{self.running_params.speed:.0f} mm/min")

    def on_pressure_slide(self, val):
        self.running_params.pressure = round(val, 1)
        self.set_entry_value(self.grp_pr["entry"], f"{self.running_params.pressure:.1f} bar")

    def on_focus_slide(self, val):
        self.running_params.focus = round(val, 2)
        self.set_entry_value(self.grp_f["entry"], f"{self.running_params.focus:.2f} mm")

    def on_gas_change(self, val):
        self.running_params.gasType = val

    def on_piercing_change(self, val):
        self.running_params.piercing = val

    def disable_parameter_sliders(self):
        self.grp_p["slider"].configure(state="disabled")
        self.grp_p["entry"].configure(state="disabled")
        self.grp_s["slider"].configure(state="disabled")
        self.grp_s["entry"].configure(state="disabled")
        self.grp_pr["slider"].configure(state="disabled")
        self.grp_pr["entry"].configure(state="disabled")
        self.grp_f["slider"].configure(state="disabled")
        self.grp_f["entry"].configure(state="disabled")
        self.gas_menu.configure(state="disabled")
        self.piercing_menu.configure(state="disabled")
        self.nozzle_ent.configure(state="disabled")
        self.comp_ent.configure(state="disabled")

    def enable_parameter_sliders(self):
        self.grp_p["slider"].configure(state="normal")
        self.grp_p["entry"].configure(state="normal")
        self.grp_s["slider"].configure(state="normal")
        self.grp_s["entry"].configure(state="normal")
        self.grp_pr["slider"].configure(state="normal")
        self.grp_pr["entry"].configure(state="normal")
        self.grp_f["slider"].configure(state="normal")
        self.grp_f["entry"].configure(state="normal")
        self.gas_menu.configure(state="normal")
        self.piercing_menu.configure(state="normal")
        self.nozzle_ent.configure(state="normal")
        self.comp_ent.configure(state="normal")

    def reset_sliders_labels(self):
        self.set_entry_value(self.grp_p["entry"], "--")
        self.set_entry_value(self.grp_s["entry"], "--")
        self.set_entry_value(self.grp_pr["entry"], "--")
        self.set_entry_value(self.grp_f["entry"], "--")
        self.nozzle_ent.configure(state="normal")
        self.nozzle_ent.delete(0, "end")
        self.nozzle_ent.insert(0, "--")
        self.nozzle_ent.configure(state="disabled")
        self.comp_ent.configure(state="normal")
        self.comp_ent.delete(0, "end")
        self.comp_ent.insert(0, "--")
        self.comp_ent.configure(state="disabled")
        self.gas_menu.set("--")
        self.piercing_menu.set("--")

    # ==========================================


    # PANEL CREATION: RIGHT CONTROL PANEL (RIGHT)


    def create_right_panel(self):
        right_panel = ctk.CTkFrame(self, width=500, corner_radius=16, fg_color="#0b0f19", border_color="#1e293b", border_width=1)
        right_panel.grid(row=0, column=2, padx=(5, 15), pady=15, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_propagate(False)

        # Unified Control Tabs
        self.control_tabs = ctk.CTkTabview(right_panel, corner_radius=12, border_color="#1e293b", border_width=1)
        self.control_tabs.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.tab_run = self.control_tabs.add("运行设置")
        self.tab_advice = self.control_tabs.add("调参建议")
        self.tab_view = self.control_tabs.add("工艺知识库")
        self.tab_add = self.control_tabs.add("新增工艺")
        self.tab_config = self.control_tabs.add("智能体配置")

        # Tab 1: Run parameters sliders & simulate cut button
        self.sliders_frame = ctk.CTkFrame(self.tab_run, fg_color="transparent")
        self.sliders_frame.pack(fill="both", expand=True, padx=10, pady=(5, 5))
        self.sliders_frame.grid_columnconfigure(0, weight=1)
        self.sliders_frame.grid_columnconfigure(1, weight=1)
        self.setup_parameter_widgets()

        self.btn_cut = ctk.CTkButton(self.tab_run, text="启动模拟试切 (Simulate Cut)", font=ctk.CTkFont(size=14, weight="bold"), height=42, fg_color="#3b82f6", hover_color="#2563eb", text_color="#ffffff", state="disabled", command=self.trigger_simulation_cut)
        self.btn_cut.pack(fill="x", padx=10, pady=(5, 10))

        # Tab 2: Closed-loop tuning advisor
        self.tab_advice.grid_columnconfigure(0, weight=1)
        self.lbl_advice = ctk.CTkLabel(self.tab_advice, text="智能体调参建议", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        self.lbl_advice.pack(anchor="w", padx=15, pady=(15, 2))
        
        # New progress bar (hidden by default)
        self.llm_progress = ctk.CTkProgressBar(self.tab_advice, height=6, fg_color="#1e293b", progress_color="#eab308")
        self.llm_progress.set(0)
        
        self.advice_console = ctk.CTkTextbox(self.tab_advice, font=ctk.CTkFont(size=11), fg_color="#05070f", text_color="#94a3b8", border_width=1, border_color="#1e293b")
        self.advice_console.pack(fill="both", expand=True, padx=15, pady=5)
        self.advice_console.insert("end", "等待首轮切割报告。若切割指标不佳，智能体将在此进行多维诊断并输出调参偏置建议。")
        self.advice_console.configure(state="disabled")

        self.btn_apply_tune = ctk.CTkButton(self.tab_advice, text="一键应用参数修正 & 重新试切", font=ctk.CTkFont(size=13, weight="bold"), height=42, fg_color="#10b981", hover_color="#059669", text_color="#ffffff", state="disabled", command=self.trigger_apply_tuning)
        self.btn_apply_tune.pack(fill="x", padx=15, pady=15)

        # Tab 3: Database View
        self.tab_view.grid_columnconfigure(0, weight=1)
        self.tab_view.grid_rowconfigure(1, weight=1)
        
        self.db_search_entry = ctk.CTkEntry(self.tab_view, placeholder_text="输入材质搜索 (如 Q235, SUS304)...", height=28, fg_color="#131b32", border_color="#1e293b")
        self.db_search_entry.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.db_search_entry.bind("<KeyRelease>", self.filter_db_table)
        
        self.db_text_box = ctk.CTkTextbox(self.tab_view, font=ctk.CTkFont(family="JetBrains Mono", size=12), fg_color="#020409", text_color="#cbd5e1", border_width=1, border_color="#1e293b")
        self.db_text_box.grid(row=1, column=0, sticky="nsew")
        self.populate_db_view()

        # Tab 4: Database Add Form
        self.setup_add_recipe_form()

        # Tab 5: Agent Config Form
        self.setup_agent_config_tab()
        self.load_llm_config_into_ui()

    def setup_add_recipe_form(self):
        self.tab_add.grid_columnconfigure(0, weight=1)
        self.tab_add.grid_columnconfigure(1, weight=1)
        
        # Row 0: Mat & Thick
        self.add_mat_ent = self.create_form_field("材质", 0, 0, "如 SUS316")
        self.add_thick_ent = self.create_form_field("厚度 (mm)", 0, 1, "如 5.0")
        # Row 1: Power & Speed
        self.add_pow_ent = self.create_form_field("功率 (W)", 1, 0, "如 3000")
        self.add_spd_ent = self.create_form_field("速度 (mm/min)", 1, 1, "如 5000")
        # Row 2: Gas & Pressure
        self.add_gas_opt = self.create_form_field_option("气型", 2, 0, ["N2", "O2", "Air"])
        self.add_press_ent = self.create_form_field("气压 (bar)", 2, 1, "如 14.0")
        # Row 3: Focus & Compensation
        self.add_foc_ent = self.create_form_field("焦点 (mm)", 3, 0, "如 -1.5")
        self.add_comp_ent = self.create_form_field("补偿 (mm)", 3, 1, "如 0.18")

        # Submit button
        btn_submit = ctk.CTkButton(self.tab_add, text="保存至专家库", height=32, font=ctk.CTkFont(size=12, weight="bold"), fg_color="#3b82f6", hover_color="#2563eb", command=self.handle_add_recipe)
        btn_submit.grid(row=4, column=0, columnspan=2, pady=(12, 0), sticky="ew")

    def create_form_field(self, label_text, r, c, placeholder):
        f = ctk.CTkFrame(self.tab_add, fg_color="transparent")
        f.grid(row=r, column=c, padx=5, pady=3, sticky="nsew")
        
        lbl = ctk.CTkLabel(f, text=label_text, font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl.pack(anchor="w")
        ent = ctk.CTkEntry(f, height=24, font=ctk.CTkFont(size=11), fg_color="#131b32", border_color="#1e293b", placeholder_text=placeholder)
        ent.pack(fill="x")
        return ent

    def create_form_field_option(self, label_text, r, c, values):
        f = ctk.CTkFrame(self.tab_add, fg_color="transparent")
        f.grid(row=r, column=c, padx=5, pady=3, sticky="nsew")
        
        lbl = ctk.CTkLabel(f, text=label_text, font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl.pack(anchor="w")
        opt = ctk.CTkOptionMenu(f, values=values, height=24, fg_color="#131b32", button_color="#0f172a", text_color="#06b6d4")
        opt.pack(fill="x")
        return opt

    def setup_agent_config_tab(self):
        # Use a scrollable frame so all controls are accessible
        config_scroll = ctk.CTkScrollableFrame(self.tab_config, fg_color="transparent")
        config_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        config_scroll.grid_columnconfigure(0, weight=1)
        
        # --- Section 1: Engine Mode ---
        sec1 = ctk.CTkFrame(config_scroll, fg_color="#0f172a", corner_radius=10)
        sec1.pack(fill="x", pady=(0, 10))
        
        lbl_mode = ctk.CTkLabel(sec1, text="⚙️ 优化与推荐决策引擎", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e2e8f0")
        lbl_mode.pack(anchor="w", padx=12, pady=(10, 5))
        
        self.engine_mode_var = tk.StringVar(value="local")
        
        radio_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        radio_frame.pack(fill="x", padx=12, pady=(0, 10))
        
        self.rad_local = ctk.CTkRadioButton(radio_frame, text="📚 本地专家规则库", variable=self.engine_mode_var, value="local", command=self.on_engine_mode_change, font=ctk.CTkFont(size=12))
        self.rad_local.pack(anchor="w", pady=2)
        
        self.rad_llm = ctk.CTkRadioButton(radio_frame, text="🤖 大模型智能体 (API)", variable=self.engine_mode_var, value="llm", command=self.on_engine_mode_change, font=ctk.CTkFont(size=12))
        self.rad_llm.pack(anchor="w", pady=2)
        
        # --- Section 2: LLM API Settings ---
        sec2 = ctk.CTkFrame(config_scroll, fg_color="#0f172a", corner_radius=10)
        sec2.pack(fill="x", pady=(0, 10))
        
        lbl_api = ctk.CTkLabel(sec2, text="🔗 大模型接口配置", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e2e8f0")
        lbl_api.pack(anchor="w", padx=12, pady=(10, 5))
        
        # API Base URL
        lbl_url = ctk.CTkLabel(sec2, text="API Base URL:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        lbl_url.pack(anchor="w", padx=12, pady=(5, 0))
        self.llm_url_ent = ctk.CTkEntry(sec2, height=30, font=ctk.CTkFont(size=11), fg_color="#131b32", border_color="#1e293b", placeholder_text="http://localhost:11434/v1")
        self.llm_url_ent.pack(fill="x", padx=12, pady=(2, 5))
        
        # Model Name
        lbl_model = ctk.CTkLabel(sec2, text="模型名称 (Model):", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        lbl_model.pack(anchor="w", padx=12, pady=(5, 0))
        
        model_row = ctk.CTkFrame(sec2, fg_color="transparent")
        model_row.pack(fill="x", padx=12, pady=(2, 5))
        
        self.llm_model_ent = ctk.CTkEntry(model_row, height=30, font=ctk.CTkFont(size=11), fg_color="#131b32", border_color="#1e293b", placeholder_text="deepseek-r1:7b")
        self.llm_model_ent.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_detect = ctk.CTkButton(model_row, text="检测模型", width=80, height=30, font=ctk.CTkFont(size=11), fg_color="#1e293b", hover_color="#334155", command=self.detect_local_models)
        self.btn_detect.pack(side="right")
        
        # Detected models dropdown (hidden initially)
        self.detected_models_var = tk.StringVar(value="")
        self.detected_models_menu = ctk.CTkOptionMenu(sec2, values=["点击“检测模型”获取列表..."], height=28, fg_color="#131b32", button_color="#0f172a", text_color="#64748b", command=self.on_model_selected)
        self.detected_models_menu.pack(fill="x", padx=12, pady=(0, 5))
        
        # API Key
        lbl_key = ctk.CTkLabel(sec2, text="API Key (选填):", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        lbl_key.pack(anchor="w", padx=12, pady=(5, 0))
        self.llm_key_ent = ctk.CTkEntry(sec2, height=30, show="*", font=ctk.CTkFont(size=11), fg_color="#131b32", border_color="#1e293b", placeholder_text="sk-... (本地Ollama无需填写)")
        self.llm_key_ent.pack(fill="x", padx=12, pady=(2, 10))
        
        # --- Section 3: Action Buttons ---
        btn_frame = ctk.CTkFrame(config_scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_test_conn = ctk.CTkButton(btn_frame, text="📡 测试连接", height=36, font=ctk.CTkFont(size=12, weight="bold"), fg_color="#475569", hover_color="#334155", command=self.test_llm_connection)
        self.btn_test_conn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.btn_save_config = ctk.CTkButton(btn_frame, text="💾 保存配置", height=36, font=ctk.CTkFont(size=12, weight="bold"), fg_color="#3b82f6", hover_color="#2563eb", command=self.save_llm_config)
        self.btn_save_config.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # --- Section 4: Status info ---
        self.config_status_lbl = ctk.CTkLabel(config_scroll, text="当前模式：本地专家规则库 (无需网络)", font=ctk.CTkFont(size=11), text_color="#10b981")
        self.config_status_lbl.pack(anchor="w", pady=(0, 5))

    def on_engine_mode_change(self):
        mode = self.engine_mode_var.get()
        if mode == "local":
            self.llm_url_ent.configure(state="disabled")
            self.llm_model_ent.configure(state="disabled")
            self.llm_key_ent.configure(state="disabled")
            self.btn_test_conn.configure(state="disabled")
            self.btn_detect.configure(state="disabled")
            self.detected_models_menu.configure(state="disabled")
            self.config_status_lbl.configure(text="当前模式：本地专家规则库 (无需网络)", text_color="#10b981")
        else:
            self.llm_url_ent.configure(state="normal")
            self.llm_model_ent.configure(state="normal")
            self.llm_key_ent.configure(state="normal")
            self.btn_test_conn.configure(state="normal")
            self.btn_detect.configure(state="normal")
            self.detected_models_menu.configure(state="normal")
            self.config_status_lbl.configure(text="当前模式：大模型智能体 (需要API服务)", text_color="#f59e0b")

    def detect_local_models(self):
        """Try to detect locally running Ollama models by querying the Ollama API."""
        self.btn_detect.configure(state="disabled", text="检测中...")
        
        def run_detect():
            models_found = []
            url = self.llm_url_ent.get().strip()
            base_url = url.rstrip('/').replace('/v1', '').replace('/v2', '')
            tags_url = f"{base_url}/api/tags"
            
            error_details = []
            
            # Helper to open with proxy bypass for localhost
            import urllib.request
            def get_opener(target_url):
                if "localhost" in target_url or "127.0.0.1" in target_url:
                    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
                return urllib.request.build_opener()
            
            try:
                opener = get_opener(tags_url)
                req = urllib.request.Request(tags_url, method="GET")
                with opener.open(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if 'models' in data:
                        for m in data['models']:
                            name = m.get('name', m.get('model', ''))
                            if name:
                                models_found.append(name)
            except Exception as e:
                error_details.append(f"Ollama tags endpoint error: {e}")
            
            # Also try OpenAI /models endpoint
            if not models_found:
                try:
                    models_url = f"{url.rstrip('/')}/models"
                    headers = {"Content-Type": "application/json"}
                    api_key = self.llm_key_ent.get().strip()
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    opener = get_opener(models_url)
                    req = urllib.request.Request(models_url, headers=headers, method="GET")
                    with opener.open(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        if 'data' in data:
                            for m in data['data']:
                                mid = m.get('id', '')
                                if mid:
                                    models_found.append(mid)
                except Exception as e:
                    error_details.append(f"OpenAI models endpoint error: {e}")
            
            def update_ui():
                self.btn_detect.configure(state="normal", text="检测模型")
                if models_found:
                    self.detected_models_menu.configure(values=models_found, text_color="#06b6d4")
                    self.detected_models_menu.set(models_found[0])
                    self.on_model_selected(models_found[0])
                    messagebox.showinfo("检测成功", f"发现 {len(models_found)} 个可用模型：\n" + "\n".join(models_found))
                else:
                    self.detected_models_menu.configure(values=["未检测到模型"], text_color="#f43f5e")
                    self.detected_models_menu.set("未检测到模型")
                    errs = "\n- ".join(error_details)
                    messagebox.showwarning("检测失败", f"未在 {base_url} 检测到运行中的模型。\n\n错误信息：\n- {errs}\n\n请确保：\n1. Ollama 已启动 (ollama serve)\n2. 已下载模型 (ollama pull deepseek-r1:7b)\n3. API URL 填写正确")
            self.after(0, update_ui)
        
        threading.Thread(target=run_detect, daemon=True).start()

    def on_model_selected(self, value):
        """When a detected model is selected from dropdown, auto-fill the model entry."""
        if value and value not in ["点击“检测模型”获取列表...", "未检测到模型"]:
            self.llm_model_ent.configure(state="normal")
            self.llm_model_ent.delete(0, "end")
            self.llm_model_ent.insert(0, value)

    def load_llm_config_into_ui(self):
        config = llm_client.load_config()
        self.engine_mode_var.set(config.get("mode", "local"))
        
        self.llm_url_ent.configure(state="normal")
        self.llm_url_ent.delete(0, "end")
        self.llm_url_ent.insert(0, config.get("url", "http://localhost:11434/v1"))
        
        self.llm_model_ent.configure(state="normal")
        self.llm_model_ent.delete(0, "end")
        self.llm_model_ent.insert(0, config.get("model", "deepseek-r1:7b"))
        
        self.llm_key_ent.configure(state="normal")
        self.llm_key_ent.delete(0, "end")
        self.llm_key_ent.insert(0, config.get("api_key", ""))
        
        self.on_engine_mode_change()

    def save_llm_config(self):
        config = {
            "mode": self.engine_mode_var.get(),
            "url": self.llm_url_ent.get().strip(),
            "model": self.llm_model_ent.get().strip(),
            "api_key": self.llm_key_ent.get().strip()
        }
        llm_client.save_config(config)
        messagebox.showinfo("成功", "智能体配置保存成功！")

    def test_llm_connection(self):
        url = self.llm_url_ent.get().strip()
        model = self.llm_model_ent.get().strip()
        api_key = self.llm_key_ent.get().strip()
        
        self.btn_test_conn.configure(state="disabled", text="测试中...")
        # Run test connection in background thread to prevent UI freezing
        def run_test():
            success, msg = llm_client.test_connection(url, model, api_key)
            def update_ui():
                self.btn_test_conn.configure(state="normal", text="测试连接")
                if success:
                    messagebox.showinfo("成功", msg)
                else:
                    messagebox.showerror("连接失败", msg)
            self.after(0, update_ui)
        threading.Thread(target=run_test, daemon=True).start()

    def populate_db_view(self, filter_query=None):
        self.db_text_box.configure(state="normal")
        self.db_text_box.delete("1.0", "end")
        
        recipes = db.get_all_recipes()
        if filter_query:
            q = filter_query.upper()
            recipes = [
                r for r in recipes 
                if q in r["material"].upper() 
                or q in r.get("gas_type", "").upper() 
                or q in r.get("nozzle", "").upper()
            ]
            
        h_mat = pad_visual("材质", 14)
        h_thick = pad_visual("厚度", 10)
        h_power = pad_visual("功率", 10)
        h_speed = pad_visual("速度", 12)
        h_gas = pad_visual("气体", 10)
        h_focus = pad_visual("焦点", 10)
        header = f"{h_mat}{h_thick}{h_power}{h_speed}{h_gas}{h_focus}\n"
        divider = "-" * 66 + "\n"
        self.db_text_box.insert("end", header)
        self.db_text_box.insert("end", divider)
        
        for r in recipes:
            r_mat = pad_visual(r['material'], 14)
            r_thick = pad_visual(f"{r['thickness']:.1f}", 10)
            r_power = pad_visual(f"{r['laser_power']:.0f}", 10)
            r_speed = pad_visual(f"{r['speed']:.0f}", 12)
            r_gas = pad_visual(r['gas_type'], 10)
            r_focus = pad_visual(f"{r['focus_position']:.1f}", 10)
            row_str = f"{r_mat}{r_thick}{r_power}{r_speed}{r_gas}{r_focus}\n"
            self.db_text_box.insert("end", row_str)
            
        self.db_text_box.configure(state="disabled")

    def filter_db_table(self, event):
        q = self.db_search_entry.get()
        self.populate_db_view(q)

    def handle_add_recipe(self):
        try:
            mat = self.add_mat_ent.get().strip()
            thick = float(self.add_thick_ent.get())
            power = float(self.add_pow_ent.get())
            speed = float(self.add_spd_ent.get())
            gas = self.add_gas_opt.get()
            pressure = float(self.add_press_ent.get())
            focus = float(self.add_foc_ent.get())
            comp = float(self.add_comp_ent.get())
            
            if not mat:
                raise ValueError("材质名称不能为空")
                
            recipe = {
                "material": mat,
                "thickness": thick,
                "laser_power": power,
                "speed": speed,
                "gas_type": gas,
                "gas_pressure": pressure,
                "focus_position": focus,
                "nozzle": "2.0",
                "piercing_method": "pulse",
                "kerf_compensation": comp,
                "operator_note": "User custom recipe"
            }
            
            db.add_recipe(recipe)
            messagebox.showinfo("成功", "新工艺成功保存至专家库！")
            
            # Reset form & reload data
            self.add_mat_ent.delete(0, "end")
            self.add_thick_ent.delete(0, "end")
            self.add_pow_ent.delete(0, "end")
            self.add_spd_ent.delete(0, "end")
            self.add_press_ent.delete(0, "end")
            self.add_foc_ent.delete(0, "end")
            self.add_comp_ent.delete(0, "end")
            
            self.load_materials_data()
            self.populate_db_view()
            
            # Refresh sidebar material menu
            mat_options = list(self.materials_map.keys())
            self.mat_menu.configure(values=mat_options)
            
        except Exception as e:
            messagebox.showerror("错误", f"保存工艺失败: {str(e)}\n请检查参数是否填写完整且格式正确。")

    # ==========================================


    # CANVAS & MATPLOTLIB CLEAN RENDERINGS


    # ==========================================
    def draw_clean_precut_canvas(self):
        self.precut_canvas.delete("all")
        self.precut_canvas.create_rectangle(5, 5, 145, 95, fill="#0c1022", outline="#1e293b", width=1)
        self.precut_canvas.create_text(75, 50, text="等待切前视觉分析...", fill="#64748b", font=("Segoe UI", 10))

    def draw_clean_postcut_canvas(self):
        self.postcut_canvas.delete("all")
        self.postcut_canvas.create_rectangle(5, 5, 165, 87, fill="#0c1022", outline="#1e293b", width=1)
        self.postcut_canvas.create_text(85, 46, text="等待切割结果成像...", fill="#64748b", font=("Segoe UI", 10))

    def draw_empty_warp_chart(self):
        self.ax_warp.clear()
        self.ax_warp.set_facecolor('#02040a')
        self.ax_warp.tick_params(axis='both', which='both', bottom=False, top=False, labelbottom=False, left=False, right=False, labelleft=False)
        for spine in self.ax_warp.spines.values():
            spine.set_visible(False)
        self.ax_warp.text(0.5, 0.5, '等待切前检测数据...', horizontalalignment='center', verticalalignment='center', color='#64748b', fontfamily='sans-serif', fontsize=9, transform=self.ax_warp.transAxes)
        self.canvas_warp.draw()

    def draw_empty_trend_chart(self):
        self.ax_trend.clear()
        self.ax_trend.set_facecolor('#02040a')
        self.ax_trend.tick_params(axis='both', which='both', bottom=False, top=False, labelbottom=False, left=False, right=False, labelleft=False)
        for spine in self.ax_trend.spines.values():
            spine.set_visible(False)
        self.ax_trend.text(0.5, 0.5, '等待闭环质量评分趋势...', horizontalalignment='center', verticalalignment='center', color='#64748b', fontfamily='sans-serif', fontsize=9, transform=self.ax_trend.transAxes)
        self.canvas_trend.draw()

    def draw_empty_confidence_gauge(self):
        cx, cy, r = 35, 35, 28
        self.conf_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=359.9, outline="#1e293b", width=4, style="arc")

    def draw_empty_score_gauge(self):
        cx, cy, r = 35, 35, 28
        self.score_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=359.9, outline="#1e293b", width=4, style="arc")

    # ==========================================


    # STEP 1 HANDLER: PRE-CUT INSPECTION


    # ==========================================
    def trigger_precut_check(self):
        self.btn_precheck.configure(state="disabled", text="📷 相机采集扫描中...")
        self.precheck_badge.configure(text="传感器读取中...", fg_color="#2d1a04", text_color="#f59e0b")
        
        self.after(800, self.finish_precut_check)

    def finish_precut_check(self):
        self.btn_precheck.configure(state="normal", text="第一步：板材切前检测")
        
        data = vision.run_precut_inspection(self.selected_material, self.selected_thickness)
        self.precheck_data = data
        self.precheck_done = True

        # Render 2D canvas visuals
        self.precut_canvas.delete("all")
        self.precut_canvas.create_rectangle(5, 5, 145, 95, fill="#1e293b", outline="#475569", width=2)
        # draw grid
        for i in range(10, 140, 15):
            self.precut_canvas.create_line(i, 5, i, 95, fill="#0f172a")
        for i in range(10, 90, 15):
            self.precut_canvas.create_line(5, i, 145, i, fill="#0f172a")

        if data["rust_level"] == "medium":
            # Rust spots (brown/orange)
            self.precut_canvas.create_oval(35, 30, 75, 60, fill="#9a3412", outline="")
            self.precut_canvas.create_oval(45, 45, 90, 75, fill="#ea580c", outline="")
        elif data["contamination"] == "oil_spot":
            # Oil spots
            self.precut_canvas.create_oval(60, 40, 100, 70, fill="#475569", outline="")
            self.precut_canvas.create_oval(55, 45, 80, 65, fill="#334155", outline="")
        elif data["contamination"] == "scratches":
            # Scratches
            self.precut_canvas.create_line(25, 20, 85, 35, fill="#64748b", width=1)
            self.precut_canvas.create_line(28, 25, 65, 33, fill="#64748b", width=1)
            self.precut_canvas.create_line(80, 70, 120, 80, fill="#64748b", width=1)

        # Plot Matplotlib 3D profile
        self.ax_warp.clear()
        self.ax_warp.set_facecolor('#02040a')
        self.fig_warp.patch.set_facecolor('#0b0f19')
        
        flatness = data["flatness_profile"]
        x = np.arange(len(flatness))
        line_color = '#f43f5e' if data["max_warp"] > 1.0 else '#06b6d4'
        
        self.ax_warp.plot(x, flatness, color=line_color, linewidth=1.5)
        self.ax_warp.scatter(x, flatness, color=line_color, s=8)
        self.ax_warp.axhline(0, color='#1e293b', linestyle='--', linewidth=1)
        self.ax_warp.tick_params(axis='both', which='both', bottom=False, top=False, labelbottom=False, left=False, labelleft=False)
        for spine in self.ax_warp.spines.values():
            spine.set_visible(False)
            
        self.ax_warp.text(0.95, 0.85, f"最大翘曲: {data['max_warp']:.1f}mm", horizontalalignment='right', color=line_color, fontfamily='Microsoft YaHei', fontsize=8, transform=self.ax_warp.transAxes)
        self.canvas_warp.draw()

        # Update warnings Text box
        self.precheck_warning_text.configure(state="normal")
        self.precheck_warning_text.delete("1.0", "end")
        
        if data["ready_to_cut"]:
            self.precheck_badge.configure(text="安全已检入 (就绪)", fg_color="#042a18", text_color="#10b981")
        else:
            self.precheck_badge.configure(text="警告：板面状态超限", fg_color="#2e050c", text_color="#f43f5e")

        if len(data["warnings"]) == 0:
            self.precheck_warning_text.insert("end", f"【正常】传感器显示表面平整度及清洁度符合标准。\n说明: {data['surface_notes']}")
        else:
            for w in data["warnings"]:
                self.precheck_warning_text.insert("end", f"[警告] 【{w['sensor']}】 {w['message']}\n\n")
        self.precheck_warning_text.configure(state="disabled")

        # Enable next step button
        self.btn_recommend.configure(state="normal")

    # ==========================================


    # STEP 2 HANDLER: PARAMETER RECOMMENDATION


    # ==========================================
    def trigger_recommendation(self):
        self.btn_recommend.configure(state="disabled")
        
        self.log_console.configure(state="normal")
        self.log_console.delete("1.0", "end")
        self.log_console.insert("end", "> 正在调用 RAG 检索结构化案例库...\n> 校验物理厚度与机床安全边界约束...")
        self.log_console.configure(state="disabled")

        self.after(600, self.finish_recommendation)

    def finish_recommendation(self):
        self.btn_recommend.configure(state="normal")
        
        rec = recommender.recommend_parameters(self.selected_material, self.selected_thickness)
        self.recommendation_data = rec

        # Log inferences in console
        self.log_console.configure(state="normal")
        self.log_console.delete("1.0", "end")
        for line in rec["reasoning"]:
            self.log_console.insert("end", f"> {line}\n")
        if len(rec["warnings"]) > 0:
            for w in rec["warnings"]:
                self.log_console.insert("end", f"[[!]安全限制] {w}\n", "warn_tag")
        self.log_console.tag_config("warn_tag", foreground="#f59e0b")
        self.log_console.configure(state="disabled")

        # Confidence gauge circle
        self.conf_canvas.delete("all")
        cx, cy, r = 35, 35, 28
        conf = rec["confidence"]
        angle = (conf / 100.0) * 360.0
        stroke_color = "#10b981" if conf > 85 else "#f59e0b" if conf > 70 else "#f43f5e"
        
        # draw background track circle
        self.conf_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=359.9, outline="#1e293b", width=4, style="arc")
        # draw progress arc
        self.conf_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-angle, outline=stroke_color, width=4, style="arc")
        self.conf_val_lbl.configure(text=f"{conf:.0f}%", text_color=stroke_color)

        # Set values to slider variables
        self.running_params = RunningParams()
        self.running_params.power = rec["laser_power"]
        self.running_params.speed = rec["speed"]
        self.running_params.gasType = rec["gas_type"]
        self.running_params.pressure = rec["gas_pressure"]
        self.running_params.focus = rec["focus_position"]
        self.running_params.nozzle = rec["nozzle"]
        self.running_params.compensation = rec["kerf_compensation"]
        self.running_params.piercing = rec["piercing_method"]

        # Populate GUI sliders
        self.grp_p["slider"].configure(state="normal")
        self.grp_p["slider"].set(rec["laser_power"])
        self.grp_p["entry"].configure(state="normal")
        self.set_entry_value(self.grp_p["entry"], f"{rec['laser_power']:.0f} W")
        
        self.grp_s["slider"].configure(state="normal")
        self.grp_s["slider"].set(rec["speed"])
        self.grp_s["entry"].configure(state="normal")
        self.set_entry_value(self.grp_s["entry"], f"{rec['speed']:.0f} mm/min")
        
        self.grp_pr["slider"].configure(state="normal")
        self.grp_pr["slider"].set(rec["gas_pressure"])
        self.grp_pr["entry"].configure(state="normal")
        self.set_entry_value(self.grp_pr["entry"], f"{rec['gas_pressure']:.1f} bar")
        
        self.grp_f["slider"].configure(state="normal")
        self.grp_f["slider"].set(rec["focus_position"])
        self.grp_f["entry"].configure(state="normal")
        self.set_entry_value(self.grp_f["entry"], f"{rec['focus_position']:.2f} mm")

        self.gas_menu.configure(state="normal")
        self.gas_menu.set(rec["gas_type"])
        self.piercing_menu.configure(state="normal")
        self.piercing_menu.set(rec["piercing_method"])

        # Nozzle & Comp text
        self.nozzle_ent.configure(state="normal")
        self.nozzle_ent.delete(0, "end")
        self.nozzle_ent.insert(0, rec["nozzle"])
        
        self.comp_ent.configure(state="normal")
        self.comp_ent.delete(0, "end")
        self.comp_ent.insert(0, f"{rec['kerf_compensation']:.3f}")

        self.enable_parameter_sliders()
        self.btn_cut.configure(state="normal")

    # ==========================================


    # STEP 3 HANDLER: SIMULATED CUT


    # ==========================================
    def trigger_simulation_cut(self):
        try:
            self.running_params.nozzle = self.nozzle_ent.get().strip()
            self.running_params.compensation = float(self.comp_ent.get().strip())
        except ValueError:
            pass
        self.btn_cut.configure(state="disabled", text="⚡ 切割头工作，机床喷吹气流中...")
        self.after(1000, self.finish_simulation_cut)

    def finish_simulation_cut(self):
        self.btn_cut.configure(state="normal", text="启动模拟试切 (Simulate Cut)")
        
        # Check source recipe id
        source_id = self.recommendation_data["source_recipe_id"] if self.recommendation_data else None
        if source_id:
            target = db.get_recipe_by_id(source_id)
        else:
            target = db.find_nearest_recipe(self.selected_material, self.selected_thickness)
            
        if not target:
            target = {
                "laser_power": self.running_params.power,
                "speed": self.running_params.speed,
                "gas_type": self.running_params.gasType,
                "gas_pressure": self.running_params.pressure,
                "focus_position": self.running_params.focus,
                "kerf_compensation": 0.20
            }

        # Calculate simulation result
        report = vision.run_postcut_inspection(
            material=self.selected_material,
            thickness=self.selected_thickness,
            laser_power=self.running_params.power,
            speed=self.running_params.speed,
            gas_type=self.running_params.gasType,
            gas_pressure=self.running_params.pressure,
            focus_position=self.running_params.focus,
            target=target
        )

        self.last_report = {"report": report, "target_recipe": target}
        score = report["quality_score"]

        # Log entry to database log history
        log_entry = {
            "material": self.selected_material,
            "thickness": self.selected_thickness,
            "laser_power": self.running_params.power,
            "speed": self.running_params.speed,
            "gas_type": self.running_params.gasType,
            "gas_pressure": self.running_params.pressure,
            "focus_position": self.running_params.focus,
            "quality_score": score,
            "dross_height": report["dross_height"],
            "burning_level": report["burning_level"],
            "penetrated": report["penetrated"]
        }
        db.log_cut_result(log_entry)

        # Update UI score gauge
        self.score_lbl.configure(text=f"{score:.1f}")
        self.draw_score_gauge(score)

        # Update metrics values labels
        self.dross_lbl.configure(text=f"{report['dross_height']} mm" if report["penetrated"] else "未切透")
        self.burn_lbl.configure(text=self.get_burn_text_cn(report["burning_level"]))
        self.kerf_lbl.configure(text=f"{report['kerf_width']} mm" if report["penetrated"] else "--")
        self.rough_lbl.configure(text=f"{report['roughness_ra']} um" if report["penetrated"] else "极高")

        # Update Summary text box
        self.postcheck_summary_text.configure(state="normal")
        self.postcheck_summary_text.delete("1.0", "end")
        self.postcheck_summary_text.insert("end", f"切缝质量反馈分析：\n{report['visual_summary']}")
        self.postcheck_summary_text.configure(state="disabled")

        # Draw 2D cut graphics
        self.draw_postcut_visuals(report)

        # Append to trend history & replot Matplotlib
        self.tuning_history.append(score)
        self.draw_trend_chart()

        # Execute optimization diagnostics
        self.run_closedloop_diagnose(target)

    def draw_score_gauge(self, score):
        self.score_canvas.delete("all")
        cx, cy, r = 35, 35, 28
        angle = (score / 100.0) * 360.0
        stroke_color = "#10b981" if score >= 90 else "#f59e0b" if score >= 75 else "#f43f5e"
        
        self.score_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=359.9, outline="#1e293b", width=4, style="arc")
        self.score_canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-angle, outline=stroke_color, width=4, style="arc")
        self.score_lbl.configure(text_color=stroke_color)

    def draw_postcut_visuals(self, report):
        self.postcut_canvas.delete("all")
        self.postcut_canvas.create_rectangle(5, 5, 165, 87, fill="#0f172a", outline="#1e293b", width=1)
        
        cx, cy = 85, 46
        r = 30
        
        # 1. Ideal path (white dotted)
        self.postcut_canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#334155", dash=(3, 3))

        # 2. Cut outcomes
        hole_fill = "#030712" # black void hole
        edge_color = "#10b981" # green normal cut
        edge_w = int(report["kerf_width"] * 15) if report["penetrated"] else 2
        
        if not report["penetrated"]:
            hole_fill = "#2d1616" # unpenetrated red hot metal
            edge_color = "#f43f5e"
        elif report["quality_score"] < 75:
            edge_color = "#f59e0b" # warning

        # Draw hole void
        self.postcut_canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=hole_fill, outline="")

        if report["penetrated"]:
            # Draw kerf width stroke
            self.postcut_canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=edge_color, width=edge_w)

            # Draw dross/slag spots if score low
            if report["dross_score"] < 85:
                dross_cnt = int((100 - report["dross_score"]) / 3)
                for i in range(dross_cnt):
                    # distribute on bottom half of circle
                    ang = np.pi * (0.1 + (i / dross_cnt) * 1.8)
                    sx = cx + np.cos(ang) * (r + 1)
                    sy = cy + np.sin(ang) * (r + 1)
                    sr = 1 + int(report["dross_height"] * 2.0)
                    self.postcut_canvas.create_oval(sx-sr, sy-sr, sx+sr, sy+sr, fill="#d97706", outline="") # slag dross blobs

            # Draw corner overburning (charred outer crescent)
            if report["burning_score"] < 85:
                # draw charcoal soot arc
                self.postcut_canvas.create_arc(cx-(r+3), cy-(r+3), cx+(r+3), cy+(r+3), start=45, extent=120, outline="#f43f5e", width=5, style="arc")
                self.postcut_canvas.create_arc(cx-(r+4), cy-(r+4), cx+(r+4), cy+(r+4), start=0, extent=359, outline="#111827", width=2, style="arc")

            # Draw roughness (jitter line)
            if report["roughness_score"] < 80:
                # draw a jittery border outline
                points = []
                for a in np.arange(0, 2*np.pi, 0.12):
                    jitter = (np.sin(a * 20) * 1.0) * (report["roughness_ra"] / 12.0)
                    px = cx + np.cos(a) * (r + jitter)
                    py = cy + np.sin(a) * (r + jitter)
                    points.extend([px, py])
                points.extend([points[0], points[1]]) # close loop
                self.postcut_canvas.create_line(points, fill="#475569", width=1)
        else:
            # draw unpenetrated spark dots
            for i in range(25):
                ang = np.random.rand() * 2 * np.pi
                dist = r + (np.random.rand() - 0.5) * 6
                px = cx + np.cos(ang) * dist
                py = cy + np.sin(ang) * dist
                self.postcut_canvas.create_rectangle(px-1, py-1, px+1, py+1, fill="#ef4444", outline="")

    def draw_trend_chart(self):
        self.ax_trend.clear()
        self.ax_trend.set_facecolor('#02040a')
        self.fig_trend.patch.set_facecolor('#0b0f19')

        scores = self.tuning_history
        iters = np.arange(1, len(scores) + 1)
        
        # Grid lines
        self.ax_trend.axhline(90, color='#064e3b', linestyle='--', linewidth=1)
        self.ax_trend.axhline(50, color='#0f172a', linestyle='-', linewidth=1)
        
        # Plot score line
        self.ax_trend.plot(iters, scores, color='#06b6d4', linewidth=1.5, marker='o', markersize=4, label="Quality")
        
        # Annotate labels for dots
        for x, y in zip(iters, scores):
            dot_color = '#10b981' if y >= 90 else '#f59e0b' if y >= 75 else '#f43f5e'
            self.ax_trend.scatter(x, y, color=dot_color, s=25, zorder=5)
            self.ax_trend.text(x, y + 4, f"#{x}", color="#94a3b8", fontsize=7, horizontalalignment='center', fontfamily='JetBrains Mono')

        self.ax_trend.set_xlim(0.8, max(2.2, len(scores) + 0.2))
        self.ax_trend.set_ylim(0, 115)
        self.ax_trend.set_xticks(iters)
        
        self.ax_trend.tick_params(axis='y', which='both', left=False, labelleft=True, labelsize=7, colors='#64748b', pad=2)
        self.ax_trend.tick_params(axis='x', which='both', bottom=False, labelbottom=False)
        for spine in self.ax_trend.spines.values():
            spine.set_visible(False)
            
        self.canvas_trend.draw()

    # ==========================================


    # STEP 4 HANDLER: CLOSED-LOOP DIAGNOSTICS


    # ==========================================
    def run_closedloop_diagnose(self, target):
        if not self.last_report: return
        
        mode = self.engine_mode_var.get()
        
        if mode == "local":
            self.run_local_diagnose(target)
        else:
            self.run_llm_diagnose_async(target)

    def run_local_diagnose(self, target):
        suggestions = optimizer.diagnose_and_optimize(
            material=self.selected_material,
            thickness=self.selected_thickness,
            current_power=self.running_params.power,
            current_speed=self.running_params.speed,
            current_gas_type=self.running_params.gasType,
            current_gas_pressure=self.running_params.pressure,
            current_focus=self.running_params.focus,
            quality_report=self.last_report["report"],
            target_recipe=target
        )

        self.pending_suggestions = suggestions

        self.advice_console.configure(state="normal")
        self.advice_console.delete("1.0", "end")

        if len(suggestions) == 0:
            self.advice_console.insert("end", "工艺参数已完全收敛，闭环优化完成！\n\n当前切割质量已达到理想状态（Score: {}）。已消除底部挂渣与溶边变形。推荐将此组参数录入为专家基准工艺。".format(self.last_report["report"]["quality_score"]))
            self.btn_apply_tune.configure(state="disabled")
        else:
            self.advice_console.insert("end", "决策引擎诊断与参数校正指令：\n\n")
            for i, sug in enumerate(suggestions):
                p_name = self.get_param_name_cn(sug["parameter"])
                unit = "W" if sug["parameter"] == "laser_power" else "mm/min" if sug["parameter"] == "speed" else "bar" if sug["parameter"] == "gas_pressure" else "mm"
                direction = "提高" if sug["action"] == "increase" else "降低" if sug["action"] == "decrease" else "重置为"
                
                risk_cn = "低风险" if str(sug.get("risk", "low")).lower() == "low" else "中风险" if str(sug.get("risk", "low")).lower() == "medium" else "高风险"
                self.advice_console.insert("end", f"建议 {i+1}：将【{p_name}】{direction}至 {sug['target_value']}{unit} (偏差: {sug['delta']:+.1f}{unit})\n")
                self.advice_console.insert("end", f"   ├ 归因说明: {sug['reason']}\n")
                self.advice_console.insert("end", f"   └ 运行风险: {risk_cn}  |  干预规则: {'人工确认' if sug['requires_approval'] else '自动校正'}\n\n")
            
            self.btn_apply_tune.configure(state="normal")
            
        self.advice_console.configure(state="disabled")

    def run_llm_diagnose_async(self, target):
        self.advice_console.configure(state="normal")
        self.advice_console.delete("1.0", "end")
        self.advice_console.insert("end", "🤖 大模型专家智能体正在分析质量缺陷并推理工艺偏置，请稍候...\n(可能需要几秒到十几秒，取决于大模型响应速度)...")
        self.advice_console.configure(state="disabled")
        self.btn_apply_tune.configure(state="disabled")

        # Show and start progress bar
        self.llm_progress.pack(fill="x", padx=15, pady=5, before=self.advice_console)
        self.llm_progress.set(0)
        self.llm_progress.start()

        # Clear reasoning log console and show thinking state
        self.log_console.configure(state="normal")
        self.log_console.delete("1.0", "end")
        self.log_console.insert("end", "> 正在调用本地/云端大模型接口...\n> Model: {}\n> 正在等待大模型思维链(CoT)及推荐建议生成...\n".format(self.llm_model_ent.get().strip()))
        self.log_console.configure(state="disabled")

        def run_llm():
            try:
                suggestions, think_log = llm_client.get_llm_suggestions(
                    material=self.selected_material,
                    thickness=self.selected_thickness,
                    current_power=self.running_params.power,
                    current_speed=self.running_params.speed,
                    current_gas_type=self.running_params.gasType,
                    current_gas_pressure=self.running_params.pressure,
                    current_focus=self.running_params.focus,
                    quality_report=self.last_report["report"],
                    target_recipe=target
                )
                
                def update_ui_success():
                    # Hide and stop progress bar
                    self.llm_progress.stop()
                    self.llm_progress.pack_forget()

                    self.pending_suggestions = suggestions
                    
                    # Update Log Console with think log
                    self.log_console.configure(state="normal")
                    self.log_console.delete("1.0", "end")
                    if think_log:
                        self.log_console.insert("end", "【大模型智能体思维链(Thinking)】\n" + think_log + "\n")
                    else:
                        self.log_console.insert("end", "> 大模型调用成功，未提供思维链详情。\n")
                    self.log_console.configure(state="disabled")
                    self.log_console.see("end")

                    # Update Advice Console
                    self.advice_console.configure(state="normal")
                    self.advice_console.delete("1.0", "end")

                    if not suggestions:
                        self.advice_console.insert("end", "🤖 大模型认为当前工艺参数已是理想状态，无需额外校准偏置。\n建议评分: {}/100".format(self.last_report["report"]["quality_score"]))
                        self.btn_apply_tune.configure(state="disabled")
                    else:
                        self.advice_console.insert("end", "🤖 大模型工艺智能体诊断与参数校正指令：\n\n")
                        for i, sug in enumerate(suggestions):
                            p_name = self.get_param_name_cn(sug["parameter"])
                            unit = "W" if sug["parameter"] == "laser_power" else "mm/min" if sug["parameter"] == "speed" else "bar" if sug["parameter"] == "gas_pressure" else "mm"
                            direction = "提高" if sug["action"] == "increase" else "降低" if sug["action"] == "decrease" else "重置为"
                            risk_cn = "低风险" if str(sug.get("risk", "low")).lower() == "low" else "中风险" if str(sug.get("risk", "low")).lower() == "medium" else "高风险"
                            
                            self.advice_console.insert("end", f"建议 {i+1}：将【{p_name}】{direction}至 {sug['target_value']}{unit} (偏差: {sug['delta']:+.1f}{unit})\n")
                            self.advice_console.insert("end", f"   ├ 归因说明: {sug.get('reason', '大模型未提供归因说明')}\n")
                            self.advice_console.insert("end", f"   └ 运行风险: {risk_cn}  |  干预规则: {'人工确认' if sug.get('requires_approval', False) else '自动校正'}\n\n")
                        self.btn_apply_tune.configure(state="normal")
                    self.advice_console.configure(state="disabled")

                self.after(0, update_ui_success)
            except Exception as e:
                def update_ui_error():
                    # Hide and stop progress bar
                    self.llm_progress.stop()
                    self.llm_progress.pack_forget()

                    self.log_console.configure(state="normal")
                    self.log_console.insert("end", f"\n[!] 异常: {str(e)}\n")
                    self.log_console.configure(state="disabled")
                    self.log_console.see("end")

                    self.advice_console.configure(state="normal")
                    self.advice_console.delete("1.0", "end")
                    self.advice_console.insert("end", f"[!] 智能体调用失败！\n\n原因: {str(e)}\n\n请在“智能体配置”标签页检查 API 接口配置，确保本地大模型已运行，或者网络 API-Key 输入正确。")
                    self.advice_console.configure(state="disabled")
                    self.btn_apply_tune.configure(state="disabled")
                self.after(0, update_ui_error)

        threading.Thread(target=run_llm, daemon=True).start()

    def trigger_apply_tuning(self):
        if len(self.pending_suggestions) == 0: return

        # Apply parameters dynamically to sliders and state
        for sug in self.pending_suggestions:
            param = sug["parameter"]
            tgt = sug["target_value"]
            
            if param == "laser_power":
                self.running_params.power = tgt
                self.grp_p["slider"].set(tgt)
                self.set_entry_value(self.grp_p["entry"], f"{tgt:.0f} W")
            elif param == "speed":
                self.running_params.speed = tgt
                self.grp_s["slider"].set(tgt)
                self.set_entry_value(self.grp_s["entry"], f"{tgt:.0f} mm/min")
            elif param == "gas_pressure":
                self.running_params.pressure = tgt
                self.grp_pr["slider"].set(tgt)
                self.set_entry_value(self.grp_pr["entry"], f"{tgt:.1f} bar")
            elif param == "focus_position":
                self.running_params.focus = tgt
                self.grp_f["slider"].set(tgt)
                self.set_entry_value(self.grp_f["entry"], f"{tgt:.2f} mm")

        # Visual log update
        self.log_console.configure(state="normal")
        self.log_console.insert("end", f"\n[⚡ 闭环优化注入] 已成功应用第 {len(self.tuning_history)} 轮校准偏置量。正在自动启动切割验证...\n")
        self.log_console.configure(state="disabled")
        self.log_console.see("end")

        # Automatically execute recut
        self.trigger_simulation_cut()

    # ==========================================


    # GENERAL STRING FORMATTING UTILITIES


    # ==========================================
    def get_burn_text_cn(self, level):
        lbls = {
            "none": "无烧边 (理想)",
            "light": "轻微溶边",
            "moderate": "中度过熔",
            "severe": "严重过烧"
        }
        return lbls.get(level, level)

    def get_param_name_cn(self, name):
        lbls = {
            "laser_power": "激光功率",
            "speed": "切割速度",
            "gas_pressure": "辅助气压",
            "focus_position": "焦点位置",
            "nozzle": "喷嘴型号",
            "kerf_compensation": "割缝补偿"
        }
        return lbls.get(name, name)

if __name__ == "__main__":
    app = LaserCuttingCopilotApp()
    app.mainloop()
