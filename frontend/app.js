// Global State
const state = {
    materials: {},
    selectedMaterial: "SUS304",
    selectedThickness: 3.0,
    precheckDone: false,
    precheckData: null,
    recommendationData: null,
    runningParams: {
        power: 0,
        speed: 0,
        gasType: "N2",
        pressure: 0.0,
        focus: 0.0,
        nozzle: "1.5",
        compensation: 0.0,
        piercing: "pulse"
    },
    lastReport: null,
    tuningHistory: [], // array of score values: [score1, score2, ...]
    currentTab: "db-view"
};

const BASE_API = ""; // Relative url works since they share port and host

// DOM Elements
const materialSelect = document.getElementById("material-select");
const thicknessSelect = document.getElementById("thickness-select");
const drawingSelect = document.getElementById("drawing-select");

const btnPrecheck = document.getElementById("btn-precheck");
const btnRecommend = document.getElementById("btn-recommend");
const btnCut = document.getElementById("btn-cut");
const btnApplyTune = document.getElementById("btn-apply-tune");

// Slider Inputs & Labels
const inputPower = document.getElementById("input-power");
const inputSpeed = document.getElementById("input-speed");
const inputGasType = document.getElementById("input-gas-type");
const inputPressure = document.getElementById("input-pressure");
const inputFocus = document.getElementById("input-focus");
const inputNozzle = document.getElementById("input-nozzle");
const inputCompensation = document.getElementById("input-compensation");
const inputPiercing = document.getElementById("input-piercing");

const lblPower = document.getElementById("val-power");
const lblSpeed = document.getElementById("val-speed");
const lblPressure = document.getElementById("val-pressure");
const lblFocus = document.getElementById("val-focus");
const lblNozzle = document.getElementById("val-nozzle");
const lblPiercing = document.getElementById("val-piercing");

// Pre-check Outputs
const precheckStatus = document.getElementById("precheck-status");
const precheckWarnings = document.getElementById("precheck-warnings");
const precutCanvas = document.getElementById("precut-canvas");

// Recommendations
const confProgress = document.getElementById("conf-progress");
const confVal = document.getElementById("conf-val");
const recommendLogs = document.getElementById("recommendation-logs");

// Quality Report
const scoreText = document.getElementById("score-text");
const gaugeFill = document.getElementById("gauge-fill");
const postcutCanvas = document.getElementById("postcut-canvas");
const lblDross = document.getElementById("lbl-dross");
const lblBurn = document.getElementById("lbl-burn");
const lblKerf = document.getElementById("lbl-kerf");
const lblRough = document.getElementById("lbl-rough");
const summaryBox = document.getElementById("quality-summary-box");

// Closed Loop
const adviceContent = document.getElementById("advice-content");

// DB Panels
const recipesTableBody = document.querySelector("#recipes-table tbody");
const tabDbViewBtn = document.getElementById("tab-db-view");
const tabDbAddBtn = document.getElementById("tab-db-add");
const dbViewPanel = document.getElementById("db-view-panel");
const dbAddPanel = document.getElementById("db-add-panel");
const dbSearchInput = document.getElementById("db-search-input");
const addRecipeForm = document.getElementById("add-recipe-form");

// Canvas Contexts
const ctxPrecut = precutCanvas.getContext("2d");
const ctxPostcut = postcutCanvas.getContext("2d");

// DPI scaling for crisp canvas rendering on high-DPI screens
function scaleCanvas(canvas, ctx) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = canvas.width;  // use HTML attribute as logical size
    const h = canvas.height;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.scale(dpr, dpr);
}
scaleCanvas(precutCanvas, ctxPrecut);
scaleCanvas(postcutCanvas, ctxPostcut);

// Logical canvas dimensions (used for drawing)
const PRECUT_W = parseInt(precutCanvas.style.width);
const PRECUT_H = parseInt(precutCanvas.style.height);
const POSTCUT_W = parseInt(postcutCanvas.style.width);
const POSTCUT_H = parseInt(postcutCanvas.style.height);

/* ==========================================
   INITIALIZATION & API CALLS
   ========================================== */
function setupManualInputSync(inputEl, sliderEl, minVal, maxVal, stepVal, unitStr, updateCallback) {
    const commitChange = () => {
        let valStr = inputEl.value.trim();
        // Remove units and parentheses
        valStr = valStr.replace(unitStr, "").replace(/\(.*?\)/g, "").replace(/bar/g, "").replace(/W/g, "").replace(/mm\/min/g, "").replace(/mm/g, "").trim();
        let val = parseFloat(valStr);
        if (isNaN(val)) {
            val = parseFloat(sliderEl.value);
        } else {
            val = Math.max(minVal, Math.min(maxVal, val));
            val = Math.round(val / stepVal) * stepVal;
        }
        sliderEl.value = val;
        updateCallback(val);
    };

    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            commitChange();
            inputEl.blur();
        }
    });

    inputEl.addEventListener("focusout", commitChange);
}
window.addEventListener("DOMContentLoaded", async () => {
    // 1. Load Material data
    await loadMaterials();
    
    // 2. Load DB Recipes
    await loadRecipes();

    // 3. Draw initial clean canvas
    drawCleanPrecutCanvas();
    drawCleanPostcutCanvas();

    // 4. Attach event listeners
    btnPrecheck.addEventListener("click", runPrecheck);
    btnRecommend.addEventListener("click", getRecommendation);
    btnCut.addEventListener("click", runSimulationCut);
    btnApplyTune.addEventListener("click", applyTuningSuggestions);
    
    materialSelect.addEventListener("change", (e) => {
        state.selectedMaterial = e.target.value;
        populateThicknesses();
        resetWorkflow();
    });
    
    thicknessSelect.addEventListener("change", (e) => {
        state.selectedThickness = parseFloat(e.target.value);
        resetWorkflow();
    });

    // Slider Event Listeners
    inputPower.addEventListener("input", (e) => {
        state.runningParams.power = parseFloat(e.target.value);
        lblPower.value = `${state.runningParams.power} W`;
    });
    inputSpeed.addEventListener("input", (e) => {
        state.runningParams.speed = parseFloat(e.target.value);
        lblSpeed.value = `${state.runningParams.speed} mm/min`;
    });
    inputPressure.addEventListener("input", (e) => {
        state.runningParams.pressure = parseFloat(e.target.value);
        lblPressure.value = `${state.runningParams.pressure} bar (${state.runningParams.gasType})`;
    });
    inputGasType.addEventListener("change", (e) => {
        state.runningParams.gasType = e.target.value;
        lblPressure.value = `${state.runningParams.pressure} bar (${state.runningParams.gasType})`;
    });
    inputFocus.addEventListener("input", (e) => {
        state.runningParams.focus = parseFloat(e.target.value);
        lblFocus.value = `${state.runningParams.focus} mm`;
    });
    inputNozzle.addEventListener("input", (e) => {
        state.runningParams.nozzle = e.target.value;
        lblNozzle.textContent = `${state.runningParams.nozzle} mm / C:${state.runningParams.compensation}mm`;
    });
    inputCompensation.addEventListener("input", (e) => {
        state.runningParams.compensation = parseFloat(e.target.value);
        lblNozzle.textContent = `${state.runningParams.nozzle} mm / C:${state.runningParams.compensation}mm`;
    });
    inputPiercing.addEventListener("change", (e) => {
        state.runningParams.piercing = e.target.value;
        lblPiercing.textContent = getPiercingName(state.runningParams.piercing);
    });

    // Set up manual inputs synchronization
    setupManualInputSync(lblPower, inputPower, 500, 6000, 50, "W", (val) => {
        state.runningParams.power = val;
        lblPower.value = `${val} W`;
    });
    setupManualInputSync(lblSpeed, inputSpeed, 100, 25000, 50, "mm/min", (val) => {
        state.runningParams.speed = val;
        lblSpeed.value = `${val} mm/min`;
    });
    setupManualInputSync(lblPressure, inputPressure, 0.1, 20.0, 0.1, "bar", (val) => {
        state.runningParams.pressure = val;
        lblPressure.value = `${val} bar (${state.runningParams.gasType})`;
    });
    setupManualInputSync(lblFocus, inputFocus, -8.0, 8.0, 0.1, "mm", (val) => {
        state.runningParams.focus = val;
        lblFocus.value = `${val} mm`;
    });

    // Tab events
    tabDbViewBtn.addEventListener("click", () => switchTab("db-view"));
    tabDbAddBtn.addEventListener("click", () => switchTab("db-add"));
    
    // DB search
    dbSearchInput.addEventListener("input", filterRecipesTable);

    // Form submit
    addRecipeForm.addEventListener("submit", handleAddRecipeSubmit);
});

// Load materials from backend
async function loadMaterials() {
    try {
        const response = await fetch(`${BASE_API}/api/materials`);
        state.materials = await response.json();
        
        // Populate materials select
        materialSelect.innerHTML = "";
        const matLabels = {
            "Q235": "碳素钢",
            "SUS304": "不锈钢",
            "Aluminum": "铝合金",
            "Copper": "紫铜"
        };
        Object.keys(state.materials).forEach(mat => {
            const opt = document.createElement("option");
            opt.value = mat;
            const label = matLabels[mat] || "";
            opt.textContent = label ? `${mat} (${label})` : mat;
            if (mat === "SUS304") opt.selected = true;
            materialSelect.appendChild(opt);
        });

        populateThicknesses();
    } catch (err) {
        console.error("Failed to load materials", err);
    }
}

// Populate thickness options based on material
function populateThicknesses() {
    const mat = materialSelect.value;
    const thicknesses = state.materials[mat] || [1.0, 2.0, 3.0];
    
    thicknessSelect.innerHTML = "";
    thicknesses.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = `${t.toFixed(1)} mm`;
        if (t === 3.0 || (thicknesses.indexOf(3.0) === -1 && t === thicknesses[0])) {
            opt.selected = true;
            state.selectedThickness = t;
        }
        thicknessSelect.appendChild(opt);
    });
}

// Load all recipes for the database tab
async function loadRecipes() {
    try {
        const response = await fetch(`${BASE_API}/api/recipes`);
        state.recipes = await response.json();
        renderRecipesTable(state.recipes);
    } catch (err) {
        console.error("Failed to load recipes", err);
    }
}

// Reset workflow back to step 1
function resetWorkflow() {
    state.precheckDone = false;
    state.precheckData = null;
    state.recommendationData = null;
    state.lastReport = null;
    state.tuningHistory = [];
    
    btnRecommend.disabled = true;
    btnCut.disabled = true;
    btnApplyTune.disabled = true;
    
    drawCleanPrecutCanvas();
    drawCleanPostcutCanvas();
    
    precheckStatus.textContent = "等待检测...";
    precheckStatus.className = "status-badge info";
    precheckWarnings.innerHTML = '<p class="placeholder-text">请先点击“第一步：板材切前检测”按钮分析板材表面。</p>';
    
    confVal.textContent = "--";
    confProgress.style.background = `conic-gradient(rgba(255,255,255,0.05) 0deg, rgba(255,255,255,0.05) 360deg)`;
    recommendLogs.innerHTML = '<p class="placeholder-text">// 等待任务触发，智能体将在此输出工艺参数检索与校验推理日志...</p>';
    
    disableParamInputs();
    resetSliders();
    
    scoreText.textContent = "--";
    updateGauge(0);
    lblDross.textContent = "--";
    lblBurn.textContent = "--";
    lblKerf.textContent = "--";
    lblRough.textContent = "--";
    summaryBox.className = "inspection-summary";
    summaryBox.innerHTML = '<p class="placeholder-text">// 切割完成后，此处将实时展示质量评估报告与缺陷归因诊断。</p>';
    
    adviceContent.innerHTML = '<p class="placeholder-text">等待首轮试切完成。如果质量评分较低，智能体将在这里对缺陷进行物理归因并提出参数修正案。</p>';
    
    drawWarpChart([]);
    drawTrendChart();
}

// Enable/Disable parameter sliders
function enableParamInputs() {
    inputPower.disabled = false;
    inputSpeed.disabled = false;
    inputGasType.disabled = false;
    inputPressure.disabled = false;
    inputFocus.disabled = false;
    inputNozzle.disabled = false;
    inputCompensation.disabled = false;
    inputPiercing.disabled = false;
    
    lblPower.disabled = false;
    lblSpeed.disabled = false;
    lblPressure.disabled = false;
    lblFocus.disabled = false;
}

function disableParamInputs() {
    inputPower.disabled = true;
    inputSpeed.disabled = true;
    inputGasType.disabled = true;
    inputPressure.disabled = true;
    inputFocus.disabled = true;
    inputNozzle.disabled = true;
    inputCompensation.disabled = true;
    inputPiercing.disabled = true;
    
    lblPower.disabled = true;
    lblSpeed.disabled = true;
    lblPressure.disabled = true;
    lblFocus.disabled = true;
}

function resetSliders() {
    lblPower.value = "--";
    lblSpeed.value = "--";
    lblPressure.value = "--";
    lblFocus.value = "--";
    lblNozzle.textContent = "--";
    lblPiercing.textContent = "--";
    
    inputPower.value = 1000;
    inputSpeed.value = 1000;
    inputPressure.value = 1;
    inputFocus.value = 0;
    inputNozzle.value = "--";
    inputCompensation.value = 0;
}

/* ==========================================
   STEP 1: PRE-CUT INSPECTION
   ========================================== */
async function runPrecheck() {
    btnPrecheck.disabled = true;
    precheckStatus.textContent = "2D相机扫描 & 3D测高仪采集数据中...";
    precheckStatus.className = "status-badge info";
    
    // Simple visual delay to make it feel like hardware scanner is working
    setTimeout(async () => {
        try {
            const url = `${BASE_API}/api/precut-inspect?material=${state.selectedMaterial}&thickness=${state.selectedThickness}`;
            const response = await fetch(url);
            const data = await response.json();
            
            state.precheckData = data;
            state.precheckDone = true;
            
            // UI updates
            if (data.ready_to_cut) {
                precheckStatus.textContent = "已就绪";
                precheckStatus.className = "status-badge success";
            } else {
                precheckStatus.textContent = "警告：检测到异常风险";
                precheckStatus.className = "status-badge warning";
            }
            
            // Warnings listing
            precheckWarnings.innerHTML = "";
            if (data.warnings.length === 0) {
                precheckWarnings.innerHTML = `<div class="warning-item low" style="border-left-color: var(--emerald); background: rgba(16,185,129,0.05)">
                    <h4>✅ 表面完整</h4>
                    <p>${data.surface_notes}</p>
                </div>`;
            } else {
                data.warnings.forEach(warn => {
                    const item = document.createElement("div");
                    item.className = `warning-item ${warn.severity}`;
                    item.innerHTML = `
                        <h4>⚠️ ${warn.sensor} [${warn.type.toUpperCase()}]</h4>
                        <p>${warn.message}</p>
                    `;
                    precheckWarnings.appendChild(item);
                });
            }
            
            // Draw visual features
            drawPrecutVisuals(data);
            drawWarpChart(data.flatness_profile);
            
            // Unlock step 2
            btnRecommend.disabled = false;
        } catch (err) {
            console.error(err);
            precheckStatus.textContent = "检测错误";
            precheckStatus.className = "status-badge warning";
        } finally {
            btnPrecheck.disabled = false;
        }
    }, 800);
}

/* ==========================================
   STEP 2: SMART RECOMMENDATION
   ========================================== */
async function getRecommendation() {
    btnRecommend.disabled = true;
    recommendLogs.innerHTML = '<p class="placeholder-text">// Agent 正在调度专家数据库并检索相似厚度切缝模型...</p>';
    
    setTimeout(async () => {
        try {
            const url = `${BASE_API}/api/recommend?material=${state.selectedMaterial}&thickness=${state.selectedThickness}`;
            const response = await fetch(url);
            const data = await response.json();
            
            state.recommendationData = data;
            
            // Render logs in console
            recommendLogs.innerHTML = "";
            data.reasoning.forEach(line => {
                const p = document.createElement("div");
                p.className = "log-line";
                p.textContent = `> ${line}`;
                recommendLogs.appendChild(p);
            });
            
            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(warn => {
                    const p = document.createElement("div");
                    p.className = "log-line warn";
                    p.textContent = `[⚠️安全规则拦截] ${warn}`;
                    recommendLogs.appendChild(p);
                });
            }
            
            // Progress circle for confidence
            const angle = (data.confidence / 100) * 360;
            const strokeColor = data.confidence > 85 ? "var(--emerald)" : data.confidence > 70 ? "var(--amber)" : "var(--rose)";
            confVal.textContent = data.confidence;
            confVal.style.color = strokeColor;
            confProgress.style.background = `conic-gradient(${strokeColor} ${angle}deg, rgba(255,255,255,0.05) ${angle}deg)`;
            
            // Populate actual sliders and variables
            state.runningParams = {
                power: data.laser_power,
                speed: data.speed,
                gasType: data.gas_type,
                pressure: data.gas_pressure,
                focus: data.focus_position,
                nozzle: data.nozzle,
                compensation: data.kerf_compensation,
                piercing: data.piercing_method
            };
            
            loadRunningParamsToSliders(data);
            enableParamInputs();
            btnCut.disabled = false;
            
        } catch (err) {
            console.error(err);
            recommendLogs.innerHTML = '<p class="log-line warn">> Failed to fetch parameters from the expert copilot recommender.</p>';
        } finally {
            btnRecommend.disabled = false;
        }
    }, 600);
}

function loadRunningParamsToSliders(data) {
    inputPower.value = data.laser_power;
    lblPower.value = `${data.laser_power} W`;
    
    inputSpeed.value = data.speed;
    lblSpeed.value = `${data.speed} mm/min`;
    
    inputGasType.value = data.gas_type;
    inputPressure.value = data.gas_pressure;
    lblPressure.value = `${data.gas_pressure} bar (${data.gas_type})`;
    
    inputFocus.value = data.focus_position;
    lblFocus.value = `${data.focus_position} mm`;
    
    inputNozzle.value = data.nozzle;
    inputCompensation.value = data.kerf_compensation;
    lblNozzle.textContent = `${data.nozzle} mm / C:${data.kerf_compensation}mm`;
    
    inputPiercing.value = data.piercing_method;
    lblPiercing.textContent = getPiercingName(data.piercing_method);
}

/* ==========================================
   STEP 3: SIMULATED TEST CUT
   ========================================== */
async function runSimulationCut() {
    btnCut.disabled = true;
    btnCut.textContent = "⚡ 切割头运动中，激光点燃并进行同轴气体喷吹...";
    
    setTimeout(async () => {
        try {
            const body = {
                material: state.selectedMaterial,
                thickness: state.selectedThickness,
                laser_power: state.runningParams.power,
                speed: state.runningParams.speed,
                gas_type: state.runningParams.gasType,
                gas_pressure: state.runningParams.pressure,
                focus_position: state.runningParams.focus,
                source_recipe_id: state.recommendationData ? state.recommendationData.source_recipe_id : null
            };
            
            const response = await fetch(`${BASE_API}/api/simulate-cut`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            });
            const data = await response.json();
            
            state.lastReport = data;
            
            // Show score gauge
            const report = data.report;
            scoreText.textContent = report.quality_score;
            updateGauge(report.quality_score);
            
            // Display features
            lblDross.textContent = report.penetrated ? `${report.dross_height} mm` : "未切透";
            lblBurn.textContent = getBurnText(report.burning_level);
            lblKerf.textContent = report.penetrated ? `${report.kerf_width} mm` : "--";
            lblRough.textContent = report.penetrated ? `${report.roughness_ra} um` : "极粗糙";
            
            // Summary text
            summaryBox.innerHTML = `<h4>📋 切缝视觉检测结果：</h4><p>${report.visual_summary}</p>`;
            if (report.quality_score >= 90) {
                summaryBox.className = "inspection-summary success-summary";
            } else {
                summaryBox.className = "inspection-summary";
            }
            
            // Draw visual cut defects on canvas
            drawPostcutVisuals(report);
            
            // Add to optimization history
            state.tuningHistory.push(report.quality_score);
            drawTrendChart();
            
            // Call diagnosis to populate tab 4
            await getDiagnosis();
            
        } catch (err) {
            console.error(err);
            summaryBox.innerHTML = '<h4>⚠️ System Error</h4><p>Failed to retrieve visual simulation cutting results.</p>';
        } finally {
            btnCut.disabled = false;
            btnCut.textContent = "🔥 启动模拟试切 (Simulate Cut)";
        }
    }, 1200);
}

/* ==========================================
   STEP 4: CLOSED-LOOP DIAGNOSTICS & TUNING
   ========================================== */
async function getDiagnosis() {
    if (!state.lastReport) return;
    
    // Start progress bar animation
    startLLMProgress();
    
    try {
        const body = {
            material: state.selectedMaterial,
            thickness: state.selectedThickness,
            laser_power: state.runningParams.power,
            speed: state.runningParams.speed,
            gas_type: state.runningParams.gasType,
            gas_pressure: state.runningParams.pressure,
            focus_position: state.runningParams.focus,
            quality_report: state.lastReport.report,
            source_recipe_id: state.recommendationData ? state.recommendationData.source_recipe_id : null
        };
        
        const response = await fetch(`${BASE_API}/api/diagnose`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Stop progress bar animation with success
        stopLLMProgress(true);
        
        // If there's think log, display it in the reasoning console
        if (data.think_log) {
            recommendLogs.innerHTML = `<div class="log-line info" style="font-weight: bold; color: var(--amber);">🤖 [大模型智能体思维链(Thinking)]</div>` + 
                `<div class="log-line text-info" style="color: #94a3b8; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-top: 5px; max-height: 180px; overflow-y: auto; text-align: left; line-height: 1.4;">${data.think_log}</div>`;
        }
        
        // Show advisory items
        const suggestions = data.suggestions;
        adviceContent.innerHTML = "";
        
        if (suggestions.length === 0) {
            adviceContent.innerHTML = `
                <div class="advice-item">
                    <div class="advice-item-header">
                        <span class="param-name">✨ 工艺参数完全收敛</span>
                        <span class="change-badge success-badge">已优化</span>
                    </div>
                    <p>当前切割质量评分高达 ${state.lastReport.report.quality_score}，切缝宽度与粗糙度在极限公差内，挂渣可忽略。当前工艺已被记录至推荐缓冲栈中，建议保存至工艺库。</p>
                </div>
            `;
            btnApplyTune.disabled = true;
        } else {
            // Store suggestions in state to apply later
            state.pendingSuggestions = suggestions;
            
            suggestions.forEach(sug => {
                const item = document.createElement("div");
                item.className = "advice-item";
                
                const valUnit = sug.parameter === "laser_power" ? "W" : sug.parameter === "speed" ? "mm/min" : sug.parameter === "gas_pressure" ? "bar" : "mm";
                const directionSymbol = sug.action === "increase" ? "➕" : sug.action === "decrease" ? "➖" : "🎯";
                const changeColor = sug.action === "increase" ? "var(--emerald)" : "var(--rose)";
                const riskCN = sug.risk === "low" ? "低风险" : sug.risk === "medium" ? "中风险" : "高风险";
                
                item.innerHTML = `
                    <div class="advice-item-header">
                        <span class="param-name">${getParamNameCN(sug.parameter)}</span>
                        <span class="change-badge" style="color: ${changeColor}; background: rgba(255,255,255,0.02)">
                            ${directionSymbol} ${Math.abs(sug.delta).toFixed(1)}${valUnit} -> ${sug.target_value}${valUnit}
                        </span>
                    </div>
                    <p>${sug.reason}</p>
                    <div class="advice-item-meta">
                        <span>风险评估: <strong class="risk-badge ${sug.risk}">${riskCN}</strong></span>
                        <span>物理干预限制: <strong>${sug.requires_approval ? "需人工授信确认" : "系统自动修正"}</strong></span>
                    </div>
                `;
                adviceContent.appendChild(item);
            });
            btnApplyTune.disabled = false;
        }
        
    } catch (err) {
        console.error(err);
        stopLLMProgress(false);
        adviceContent.innerHTML = '<p class="placeholder-text">获取诊断修正建议失败。</p>';
    }
}

function applyTuningSuggestions() {
    if (!state.pendingSuggestions || state.pendingSuggestions.length === 0) return;
    
    // Disable button to prevent double-click
    btnApplyTune.disabled = true;
    btnApplyTune.textContent = "⏳ 正在注入参数修正...";
    
    state.pendingSuggestions.forEach(sug => {
        const param = sug.parameter;
        const tgt = sug.target_value;
        
        if (param === "laser_power") {
            state.runningParams.power = tgt;
            inputPower.value = tgt;
            lblPower.textContent = `${tgt} W`;
        } else if (param === "speed") {
            state.runningParams.speed = tgt;
            inputSpeed.value = tgt;
            lblSpeed.textContent = `${tgt} mm/min`;
        } else if (param === "gas_pressure") {
            state.runningParams.pressure = tgt;
            inputPressure.value = tgt;
            lblPressure.textContent = `${tgt} bar (${state.runningParams.gasType})`;
        } else if (param === "focus_position") {
            state.runningParams.focus = tgt;
            inputFocus.value = tgt;
            lblFocus.textContent = `${tgt} mm`;
        }
    });
    
    // Visual flash or log notice
    const log = document.createElement("div");
    log.className = "log-line warn";
    log.textContent = `[⚡闭环优化注入] 已成功注入第 ${state.tuningHistory.length} 轮校准偏置量。正在启动新一轮切割验证。`;
    recommendLogs.appendChild(log);
    recommendLogs.scrollTop = recommendLogs.scrollHeight;
    
    // Automatically trigger recut
    runSimulationCut();
}

/* ==========================================
   CANVAS DRAWING UTILITIES
   ========================================== */
function drawCleanPrecutCanvas() {
    ctxPrecut.fillStyle = "#0c1022";
    ctxPrecut.fillRect(0, 0, PRECUT_W, PRECUT_H);
    
    // Draw boundary line
    ctxPrecut.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctxPrecut.lineWidth = 1;
    ctxPrecut.strokeRect(10, 10, PRECUT_W - 20, PRECUT_H - 20);
    
    ctxPrecut.fillStyle = "rgba(255, 255, 255, 0.15)";
    ctxPrecut.font = "11px Outfit";
    ctxPrecut.textAlign = "center";
    ctxPrecut.fillText("等待切前视觉分析...", PRECUT_W/2, PRECUT_H/2);
}

function drawCleanPostcutCanvas() {
    ctxPostcut.fillStyle = "#0c1022";
    ctxPostcut.fillRect(0, 0, POSTCUT_W, POSTCUT_H);
    
    ctxPostcut.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctxPostcut.lineWidth = 1;
    ctxPostcut.strokeRect(10, 10, POSTCUT_W - 20, POSTCUT_H - 20);
    
    ctxPostcut.fillStyle = "rgba(255, 255, 255, 0.15)";
    ctxPostcut.font = "11px Outfit";
    ctxPostcut.textAlign = "center";
    ctxPostcut.fillText("等待切割结果成像...", POSTCUT_W/2, POSTCUT_H/2);
}

// 2D Precut plate scanner rendering
function drawPrecutVisuals(data) {
    ctxPrecut.fillStyle = "#1e293b"; // base grey metallic
    ctxPrecut.fillRect(0, 0, PRECUT_W, PRECUT_H);
    
    // Plate borders
    ctxPrecut.strokeStyle = "#475569";
    ctxPrecut.lineWidth = 2;
    ctxPrecut.strokeRect(15, 15, PRECUT_W - 30, PRECUT_H - 30);
    
    // Draw grid lines
    ctxPrecut.strokeStyle = "rgba(255, 255, 255, 0.03)";
    ctxPrecut.lineWidth = 1;
    for (let x = 20; x < PRECUT_W - 20; x += 20) {
        ctxPrecut.beginPath(); ctxPrecut.moveTo(x, 15); ctxPrecut.lineTo(x, PRECUT_H - 15); ctxPrecut.stroke();
    }
    for (let y = 20; y < PRECUT_H - 20; y += 20) {
        ctxPrecut.beginPath(); ctxPrecut.moveTo(15, y); ctxPrecut.lineTo(PRECUT_W - 15, y); ctxPrecut.stroke();
    }

    // Material specific surface textures
    const mat = state.selectedMaterial;
    if (mat === "Q235") {
        // Rust spots (orange-brown)
        ctxPrecut.fillStyle = "rgba(180, 83, 9, 0.4)"; // amber-700
        drawBlob(ctxPrecut, 60, 50, 20);
        drawBlob(ctxPrecut, 75, 45, 12);
        drawBlob(ctxPrecut, 140, 90, 25);
        ctxPrecut.fillStyle = "rgba(217, 119, 6, 0.25)";
        drawBlob(ctxPrecut, 145, 95, 32);
    } else if (mat === "SUS304") {
        // Oil spots (rainbow translucent circle / dark yellow-grey spots)
        ctxPrecut.fillStyle = "rgba(100, 116, 139, 0.25)";
        drawBlob(ctxPrecut, 110, 75, 15);
        ctxPrecut.fillStyle = "rgba(148, 163, 184, 0.2)";
        drawBlob(ctxPrecut, 105, 80, 25);
    } else if (mat === "Aluminum") {
        // Fine scratches
        ctxPrecut.strokeStyle = "rgba(255, 255, 255, 0.25)";
        ctxPrecut.lineWidth = 0.8;
        ctxPrecut.beginPath(); ctxPrecut.moveTo(40, 30); ctxPrecut.lineTo(100, 45); ctxPrecut.stroke();
        ctxPrecut.beginPath(); ctxPrecut.moveTo(42, 34); ctxPrecut.lineTo(80, 43); ctxPrecut.stroke();
        ctxPrecut.beginPath(); ctxPrecut.moveTo(120, 110); ctxPrecut.lineTo(170, 120); ctxPrecut.stroke();
    }
}

function drawBlob(ctx, cx, cy, r) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.fill();
}

// 2D top-down Circular Cut preview with defects
function drawPostcutVisuals(report) {
    ctxPostcut.fillStyle = "#111827"; // dark grey sheet metal background
    ctxPostcut.fillRect(0, 0, POSTCUT_W, POSTCUT_H);
    
    const cx = POSTCUT_W / 2;
    const cy = POSTCUT_H / 2;
    
    // Draw ideal circular cut line
    ctxPostcut.strokeStyle = "rgba(255, 255, 255, 0.15)";
    ctxPostcut.setLineDash([4, 4]);
    ctxPostcut.lineWidth = 1;
    ctxPostcut.beginPath();
    ctxPostcut.arc(cx, cy, 38, 0, 2 * Math.PI);
    ctxPostcut.stroke();
    ctxPostcut.setLineDash([]); // reset
    
    // Draw cut path width (representing kerf)
    let cutRadius = 38;
    let strokeColor = "#10b981"; // emerald-500 (good cut)
    let fillStyle = "#030712"; // void center hole cut
    
    if (!report.penetrated) {
        strokeColor = "var(--rose)";
        fillStyle = "#371c1c"; // red-hot molten uncut seam
    } else if (report.quality_score < 75) {
        strokeColor = "var(--amber)";
    }
    
    // Draw the main hole (cut outcome)
    ctxPostcut.fillStyle = fillStyle;
    ctxPostcut.beginPath();
    ctxPostcut.arc(cx, cy, cutRadius, 0, 2 * Math.PI);
    ctxPostcut.fill();
    
    // Draw cut seam edge representation
    ctxPostcut.strokeStyle = strokeColor;
    ctxPostcut.lineWidth = report.penetrated ? (report.kerf_width * 15) : 3; // scale kerf for viewing
    ctxPostcut.stroke();
    
    // Add visual defects if present
    if (report.penetrated) {
        // Draw dross (slag accumulation) around the cut edge
        const drossScore = report.dross_score;
        if (drossScore < 85) {
            const count = Math.round((100 - drossScore) / 4);
            ctxPostcut.fillStyle = "#d97706"; // amber-600 slag color
            for (let i = 0; i < count; i++) {
                // Slag attaches at the bottom edges of the cut line
                const angle = Math.PI * (0.1 + (i / count) * 1.8); // concentrate in the lower half of the circle
                const x = cx + Math.cos(angle) * (cutRadius + 2);
                const y = cy + Math.sin(angle) * (cutRadius + 2);
                const size = 2 + (report.dross_height * 2.5) * (0.5 + Math.random()*0.5);
                ctxPostcut.beginPath();
                ctxPostcut.arc(x, y, size, 0, 2 * Math.PI);
                ctxPostcut.fill();
            }
        }
        
        // Draw corner/edge over-burning (black carbonization ring)
        const burnScore = report.burning_score;
        if (burnScore < 85) {
            ctxPostcut.strokeStyle = "rgba(244, 63, 94, 0.4)"; // glowing rose burn ring
            ctxPostcut.lineWidth = 6;
            ctxPostcut.beginPath();
            ctxPostcut.arc(cx, cy, cutRadius - 2, 0.1, Math.PI * 0.4); // top corner overburning
            ctxPostcut.stroke();
            
            ctxPostcut.fillStyle = "rgba(0, 0, 0, 0.85)"; // black carbon soot
            ctxPostcut.beginPath();
            ctxPostcut.arc(cx, cy, cutRadius - 3, 0, 2 * Math.PI);
            ctxPostcut.stroke();
        }
        
        // Draw roughness (jagged edge)
        const roughScore = report.roughness_score;
        if (roughScore < 80) {
            ctxPostcut.strokeStyle = "rgba(148, 163, 184, 0.5)"; // grey uneven jitter
            ctxPostcut.lineWidth = 1;
            ctxPostcut.beginPath();
            for (let a = 0; a < 2 * Math.PI; a += 0.1) {
                const jitter = (Math.sin(a * 25) * 1.2) * (report.roughness_ra / 12.0);
                const x = cx + Math.cos(a) * (cutRadius + jitter);
                const y = cy + Math.sin(a) * (cutRadius + jitter);
                if (a === 0) ctxPostcut.moveTo(x, y);
                else ctxPostcut.lineTo(x, y);
            }
            ctxPostcut.closePath();
            ctxPostcut.stroke();
        }
    } else {
        // Unpenetrated cut - draw incomplete laser track line (red splash dots)
        ctxPostcut.strokeStyle = "rgba(239, 68, 68, 0.7)"; // red sparks
        ctxPostcut.lineWidth = 1.5;
        ctxPostcut.beginPath();
        for (let i = 0; i < 30; i++) {
            const angle = Math.random() * 2 * Math.PI;
            const dist = cutRadius + (Math.random() - 0.5) * 8;
            const x = cx + Math.cos(angle) * dist;
            const y = cy + Math.sin(angle) * dist;
            ctxPostcut.fillRect(x, y, 2, 2);
        }
    }
}

// Draw the 3D sheet metal warp line on SVG
function drawWarpChart(profile) {
    const svg = document.getElementById("warp-svg");
    svg.innerHTML = "";
    
    if (profile.length === 0) return;
    
    // Dimensions: viewBox="0 0 200 60"
    const width = 200;
    const height = 60;
    const padding = 10;
    
    const pointsCount = profile.length;
    const stepX = (width - 2 * padding) / (pointsCount - 1);
    
    // Flatness base line at y = 45 (0mm)
    const baseY = 45;
    
    // Draw baseline
    const baseLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    baseLine.setAttribute("x1", padding);
    baseLine.setAttribute("y1", baseY);
    baseLine.setAttribute("x2", width - padding);
    baseLine.setAttribute("y2", baseY);
    baseLine.setAttribute("stroke", "rgba(255, 255, 255, 0.08)");
    baseLine.setAttribute("stroke-dasharray", "2,2");
    svg.appendChild(baseLine);
    
    // Construct polyline points
    // Scale profile values: 0mm -> baseY, max warp -> offset upwards
    // Say 2.0mm warp equals 30px height change
    let pointString = "";
    for (let i = 0; i < pointsCount; i++) {
        const x = padding + i * stepX;
        const val = profile[i];
        const y = baseY - (val * 15); // scaling: 1mm = 15px
        pointString += `${x},${y} `;
        
        // Draw individual data dots
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", x);
        circle.setAttribute("cy", y);
        circle.setAttribute("r", 2);
        circle.setAttribute("fill", val > 1.0 ? "var(--rose)" : "var(--cyan)");
        svg.appendChild(circle);
    }
    
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    path.setAttribute("points", pointString.trim());
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", state.precheckData.max_warp > 1.0 ? "var(--rose)" : "var(--cyan)");
    path.setAttribute("stroke-width", "1.5");
    svg.appendChild(path);
    
    // Display Max Warp text
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", width - padding);
    text.setAttribute("y", 20);
    text.setAttribute("text-anchor", "end");
    text.setAttribute("fill", state.precheckData.max_warp > 1.0 ? "var(--rose)" : "var(--cyan)");
    text.setAttribute("font-size", "8");
    text.setAttribute("font-family", "JetBrains Mono");
    text.textContent = `Max Warp: ${state.precheckData.max_warp.toFixed(1)}mm`;
    svg.appendChild(text);
}

// Draw the iteration optimization score trend line graph on SVG
function drawTrendChart() {
    const svg = document.getElementById("trend-svg");
    svg.innerHTML = "";
    
    // viewBox = "0 0 200 70"
    const width = 200;
    const height = 70;
    const paddingX = 20;
    const paddingY = 12;
    
    // Draw Y axis lines (50%, 90%, 100%)
    const yLevels = [0.5, 0.9, 1.0];
    yLevels.forEach(lvl => {
        const y = paddingY + (height - 2*paddingY) * (1 - lvl);
        const gridLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        gridLine.setAttribute("x1", paddingX);
        gridLine.setAttribute("y1", y);
        gridLine.setAttribute("x2", width - 10);
        gridLine.setAttribute("y2", y);
        gridLine.setAttribute("stroke", lvl === 0.9 ? "rgba(16, 185, 129, 0.15)" : "rgba(255, 255, 255, 0.03)");
        if (lvl === 0.9) gridLine.setAttribute("stroke-dasharray", "3,3");
        svg.appendChild(gridLine);
        
        // Add axis text
        const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
        txt.setAttribute("x", paddingX - 4);
        txt.setAttribute("y", y + 3);
        txt.setAttribute("fill", "rgba(255,255,255,0.3)");
        txt.setAttribute("font-size", "7");
        txt.setAttribute("text-anchor", "end");
        txt.setAttribute("font-family", "JetBrains Mono");
        txt.textContent = `${Math.round(lvl*100)}`;
        svg.appendChild(txt);
    });

    if (state.tuningHistory.length === 0) {
        // Draw empty text placeholder
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", width / 2 + 10);
        text.setAttribute("y", height / 2 + 3);
        text.setAttribute("fill", "rgba(255, 255, 255, 0.15)");
        text.setAttribute("font-size", "8");
        text.setAttribute("text-anchor", "middle");
        text.textContent = "等待优化反馈曲线...";
        svg.appendChild(text);
        return;
    }
    
    // Draw the curve line
    const pointsCount = state.tuningHistory.length;
    const stepX = pointsCount > 1 ? (width - paddingX - 20) / (pointsCount - 1) : 0;
    
    let pointString = "";
    for (let i = 0; i < pointsCount; i++) {
        const score = state.tuningHistory[i];
        const x = pointsCount > 1 ? (paddingX + i * stepX) : (paddingX + (width - paddingX - 20)/2);
        
        // scale score (0-100) inside [paddingY, height - paddingY]
        const y = paddingY + (height - 2*paddingY) * (1 - score/100);
        pointString += `${x},${y} `;
        
        // Draw dot
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", x);
        circle.setAttribute("cy", y);
        circle.setAttribute("r", 3);
        circle.setAttribute("fill", score >= 90 ? "var(--emerald)" : score >= 75 ? "var(--amber)" : "var(--rose)");
        
        // Add tiny iteration text above dot
        const txtNum = document.createElementNS("http://www.w3.org/2000/svg", "text");
        txtNum.setAttribute("x", x);
        txtNum.setAttribute("y", y - 5);
        txtNum.setAttribute("fill", "rgba(255,255,255,0.6)");
        txtNum.setAttribute("font-size", "7");
        txtNum.setAttribute("font-family", "JetBrains Mono");
        txtNum.setAttribute("text-anchor", "middle");
        txtNum.textContent = `#${i+1}`;
        svg.appendChild(txtNum);
        
        svg.appendChild(circle);
    }
    
    if (pointsCount > 1) {
        const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        polyline.setAttribute("points", pointString.trim());
        polyline.setAttribute("fill", "none");
        polyline.setAttribute("stroke", "var(--cyan)");
        polyline.setAttribute("stroke-width", "1.5");
        svg.insertBefore(polyline, svg.firstChild); // render line behind circles
    }
}

/* ==========================================
   EXPERT DATABASE UI LOGIC
   ========================================== */
function switchTab(tabId) {
    state.currentTab = tabId;
    
    if (tabId === "db-view") {
        tabDbViewBtn.classList.add("active");
        tabDbAddBtn.classList.remove("active");
        dbViewPanel.classList.add("active");
        dbAddPanel.classList.remove("active");
    } else {
        tabDbViewBtn.classList.remove("active");
        tabDbAddBtn.classList.add("active");
        dbViewPanel.classList.remove("active");
        dbAddPanel.classList.add("active");
    }
}

function renderRecipesTable(recipes) {
    recipesTableBody.innerHTML = "";
    recipes.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${r.material}</strong></td>
            <td>${r.thickness.toFixed(1)}</td>
            <td>${r.laser_power}</td>
            <td>${r.speed}</td>
            <td><span class="gas-badge" style="color: ${r.gas_type === "N2" ? "var(--cyan)" : "var(--amber)"}">${r.gas_type}</span></td>
            <td>${r.focus_position}</td>
        `;
        recipesTableBody.appendChild(tr);
    });
}

function filterRecipesTable() {
    const q = dbSearchInput.value.toUpperCase();
    const filtered = state.recipes.filter(r => r.material.toUpperCase().includes(q));
    renderRecipesTable(filtered);
}

async function handleAddRecipeSubmit(e) {
    e.preventDefault();
    
    const body = {
        material: document.getElementById("add-material").value,
        thickness: parseFloat(document.getElementById("add-thickness").value),
        laser_power: parseFloat(document.getElementById("add-power").value),
        speed: parseFloat(document.getElementById("add-speed").value),
        gas_type: document.getElementById("add-gas").value,
        gas_pressure: parseFloat(document.getElementById("add-pressure").value),
        focus_position: parseFloat(document.getElementById("add-focus").value),
        nozzle: document.getElementById("add-nozzle").value,
        piercing_method: "pulse",
        kerf_compensation: parseFloat(document.getElementById("add-comp").value) || 0.15
    };
    
    try {
        const response = await fetch(`${BASE_API}/api/recipes`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        
        if (response.ok) {
            showToast("✅ 成功保存至专家参数库！", "success");
            addRecipeForm.reset();
            switchTab("db-view");
            
            // Reload all
            await loadMaterials();
            await loadRecipes();
        } else {
            showToast("❌ 保存失败，请检查参数合法性。", "error");
        }
    } catch (err) {
        console.error(err);
        showToast("❌ 网络接口调用失败。", "error");
    }
}

/* ==========================================
   GENERAL HELPER UTILITIES
   ========================================== */
function updateGauge(score) {
    // Circumference of semi-circle: dasharray = 126 (pi * r = 3.14159 * 40 = 125.6px)
    // 0 score = 126 offset, 100 score = 0 offset
    const offset = 126 - (score / 100) * 126;
    gaugeFill.style.strokeDashoffset = offset;
}

function getPiercingName(val) {
    if (val === "direct") return "直穿孔 (Direct)";
    if (val === "pulse") return "脉冲穿孔 (Pulse)";
    if (val === "stage") return "分段渐进 (Stage)";
    return val;
}

function getBurnText(level) {
    if (level === "none") return "理想断面 (无烧边)";
    if (level === "light") return "轻微溶边";
    if (level === "moderate") return "中度过熔";
    if (level === "severe") return "严重过烧 (缺口)";
    return level;
}

function getParamNameCN(param) {
    const names = {
        laser_power: "🔥 激光功率",
        speed: "🚀 切割速度",
        gas_pressure: "💨 吹气压力",
        focus_position: "🎯 焦点位置",
        nozzle: "⭕ 喷嘴直径",
        kerf_compensation: "📐 割缝补偿"
    };
    return names[param] || param;
}

/* ==========================================
   TOAST NOTIFICATION SYSTEM
   ========================================== */
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add("toast-show");
    });
    
    // Auto-dismiss after 3 seconds
    setTimeout(() => {
        toast.classList.remove("toast-show");
        toast.classList.add("toast-hide");
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}

/* ==========================================
   LLM PROGRESS BAR ANIMATION SYSTEM
   ========================================== */
let progressInterval = null;
function startLLMProgress() {
    const container = document.getElementById("llm-progress-container");
    const fill = document.getElementById("llm-progress-fill");
    const label = document.getElementById("llm-progress-label");
    if (!container || !fill || !label) return;
    
    container.style.display = "block";
    fill.style.width = "0%";
    fill.style.backgroundColor = ""; // Reset custom background if red
    label.textContent = "大模型智能体正在进行推理诊断...";
    
    let progress = 0;
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(() => {
        if (progress < 90) {
            // Slower as it goes higher to simulate loading
            const step = (90 - progress) * 0.15;
            progress += Math.max(step, 1);
            fill.style.width = `${progress}%`;
            label.textContent = `大模型智能体推理诊断中... (${Math.round(progress)}%)`;
        }
    }, 200);
}

function stopLLMProgress(success = true) {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    const container = document.getElementById("llm-progress-container");
    const fill = document.getElementById("llm-progress-fill");
    const label = document.getElementById("llm-progress-label");
    if (!container || !fill || !label) return;
    
    if (success) {
        fill.style.width = "100%";
        label.textContent = "推理诊断完成！";
        setTimeout(() => {
            container.style.display = "none";
        }, 800);
    } else {
        label.textContent = "大模型诊断失败！";
        fill.style.backgroundColor = "var(--rose)";
        setTimeout(() => {
            container.style.display = "none";
            fill.style.backgroundColor = ""; // Reset
        }, 1500);
    }
}
