let allExperiments = [];
let analysisData = null;
let activeAnalysisMetric = 'quality_score';

document.addEventListener('DOMContentLoaded', () => {
    loadExperiments();
    initializeInputsFromLastRun();

    // Event listeners
    document.getElementById('form-new-run').addEventListener('submit', handleNewRunSubmit);
    document.getElementById('form-supplement-quality').addEventListener('submit', handleSupplementQualitySubmit);
    document.getElementById('form-edit-parameters').addEventListener('submit', handleEditParametersSubmit);
    document.getElementById('btn-run-analysis').addEventListener('click', runRangeAnalysis);
    initDragAndDrop();
    initImageControls();
});

// Toggle Advanced settings in form
function toggleAdvancedSettings() {
    const fields = document.getElementById('advanced-fields');
    const arrow = document.getElementById('adv-arrow');
    fields.classList.toggle('hidden');
    arrow.classList.toggle('fa-chevron-down');
    arrow.classList.toggle('fa-chevron-up');
}

// Initialize parameters from the last run (Memory on start-up)
async function initializeInputsFromLastRun() {
    try {
        const res = await fetch('/api/experiments/last');
        if (!res.ok) throw new Error('无法加载历史记忆参数');
        const lastParams = await res.json();
        
        if (lastParams && lastParams.power_kw) {
            document.getElementById('input-power').value = Math.round(lastParams.power_kw / 0.6);
            document.getElementById('input-speed').value = lastParams.speed_m_min;
            document.getElementById('input-pressure').value = lastParams.air_pressure_mpa;
            document.getElementById('input-focus').value = lastParams.focus_position_mm || lastParams.focus_mm;
            document.getElementById('input-material').value = lastParams.material || 'carbon_steel';
            document.getElementById('input-thickness').value = lastParams.thickness_mm || 30;
            document.getElementById('input-gas').value = lastParams.assist_gas || lastParams.gas || 'air';
            document.getElementById('input-nozzle-h').value = lastParams.nozzle_height_mm || 1.0;
        }
    } catch (err) {
        console.warn('初始化历史输入参数失败:', err);
    }
}

// Load parameters of a historical run into the left inputs
function loadToInputs(episodeId) {
    const run = allExperiments.find(r => r.episode_id === episodeId);
    if (!run) return;

    document.getElementById('input-power').value = Math.round(run.power_kw / 0.6);
    document.getElementById('input-speed').value = run.speed_m_min;
    document.getElementById('input-pressure').value = run.air_pressure_mpa;
    document.getElementById('input-focus').value = run.focus_mm;
    document.getElementById('input-material').value = run.material;
    document.getElementById('input-thickness').value = run.thickness_mm;
    document.getElementById('input-gas').value = run.gas;
    document.getElementById('input-nozzle-h').value = run.nozzle_height_mm;

    alert(`已将试验 [${episodeId}] 的参数复制并载入左侧输入栏！`);
}

// Fetch all experiment runs
async function loadExperiments() {
    try {
        const res = await fetch('/api/experiments');
        if (!res.ok) throw new Error('加载数据失败');
        
        allExperiments = await res.json();
        renderTable();
        calculateStats();
        refreshPreviewTrialsCombo();
    } catch (err) {
        console.error(err);
        alert('加载试验记录出错: ' + err.message);
    }
}

// Render data table
function renderTable() {
    const tbody = document.getElementById('experiments-table-body');
    tbody.innerHTML = '';

    if (allExperiments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">暂无试验记录。请在左侧输入参数以录入第一条切割数据。</td></tr>';
        return;
    }

    allExperiments.forEach(run => {
        const tr = document.createElement('tr');
        
        const isCutThrough = run.cut_through;
        const cutBadge = isCutThrough 
            ? '<span class="badge badge-success">是</span>' 
            : '<span class="badge badge-danger">否</span>';
            
        let failBadge = '<span class="badge badge-neutral">正常</span>';
        if (run.failure_case !== 'normal') {
            const failZh = {
                'incomplete_cut': '未切透',
                'overburn': '过烧',
                'dross': '挂渣',
                'unstable_cut': '不稳定'
            }[run.failure_case] || run.failure_case;
            failBadge = `<span class="badge badge-warning">${failZh}</span>`;
        }

        const scoreText = run.quality_score !== null 
            ? parseFloat(run.quality_score).toFixed(1) 
            : '<span class="text-muted">暂无数据</span>';

        tr.innerHTML = `
            <td><strong>${run.episode_id}</strong></td>
            <td>${(run.power_kw / 0.6).toFixed(1)}%</td>
            <td>${run.speed_m_min} m/min</td>
            <td>${run.air_pressure_mpa} MPa</td>
            <td>${run.focus_mm} mm</td>
            <td>${cutBadge}</td>
            <td>${failBadge}</td>
            <td><strong>${scoreText}</strong></td>
            <td>
                <div style="display:flex; gap: 4px;">
                    <button class="btn btn-secondary-outline btn-sm" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="loadToInputs('${run.episode_id}')">
                        <i class="fa-solid fa-file-import"></i> 载入
                    </button>
                    <button class="btn btn-secondary-outline btn-sm" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="openSupplementModal('${run.episode_id}')">
                        <i class="fa-solid fa-edit"></i> 检测
                    </button>
                    <button class="btn btn-secondary-outline btn-sm" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="openEditModal('${run.episode_id}')">
                        <i class="fa-solid fa-sliders"></i> 修改
                    </button>
                    <button class="btn btn-secondary-outline btn-sm btn-danger-custom" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="deleteExperiment('${run.episode_id}')">
                        <i class="fa-solid fa-trash"></i> 删除
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Calculate and show summary stats
function calculateStats() {
    const total = allExperiments.length;
    document.getElementById('stat-total-runs').textContent = total;

    if (total === 0) {
        document.getElementById('stat-penetration-rate').textContent = '--';
        document.getElementById('stat-avg-score').textContent = '--';
        return;
    }

    const cutThroughCount = allExperiments.filter(r => r.cut_through).length;
    const penRate = ((cutThroughCount / total) * 100).toFixed(1);
    document.getElementById('stat-penetration-rate').textContent = `${penRate}%`;

    const scoredRuns = allExperiments.filter(r => r.quality_score !== null);
    if (scoredRuns.length > 0) {
        const sum = scoredRuns.reduce((acc, r) => acc + r.quality_score, 0);
        const avg = (sum / scoredRuns.length).toFixed(1);
        document.getElementById('stat-avg-score').textContent = `${avg} / 100`;
    } else {
        document.getElementById('stat-avg-score').textContent = '暂无评分';
    }
}

// Delete experiment run
async function deleteExperiment(episodeId) {
    if (!confirm(`确认要删除试切记录 [${episodeId}] 吗？`)) {
        return;
    }

    try {
        const res = await fetch(`/api/experiments/${episodeId}`, {
            method: 'DELETE'
        });

        if (!res.ok) throw new Error('删除失败');
        
        await loadExperiments();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

// Handle adding a new run
async function handleNewRunSubmit(e) {
    e.preventDefault();

    const episodeIdVal = document.getElementById('input-episode-id').value.trim();
    const data = {
        episode_id: episodeIdVal ? episodeIdVal : null,
        power_kw: parseFloat(document.getElementById('input-power').value) * 0.6,
        speed_m_min: parseFloat(document.getElementById('input-speed').value),
        air_pressure_mpa: parseFloat(document.getElementById('input-pressure').value),
        focus_mm: parseFloat(document.getElementById('input-focus').value),
        material: document.getElementById('input-material').value,
        thickness_mm: parseFloat(document.getElementById('input-thickness').value),
        gas: document.getElementById('input-gas').value,
        nozzle_height_mm: parseFloat(document.getElementById('input-nozzle-h').value),
    };

    try {
        const res = await fetch('/api/experiments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!res.ok) throw new Error('保存失败');
        const result = await res.json();
        
        // Clear custom ID input on success
        document.getElementById('input-episode-id').value = '';
        
        // CRITICAL MEMORY FEATURE: Do NOT reset the form input values!
        // This keeps the values in fields so users can adjust and log next run easily.

        // Reload data
        await loadExperiments();
        
        // Open modal for the newly created run immediately
        openSupplementModal(result.episode_id);
    } catch (err) {
        alert('保存切割参数出错: ' + err.message);
    }
}

// Switch modal tabs between 'data' and 'files'
function switchModalTab(tab) {
    const btnData = document.getElementById('btn-tab-data');
    const btnFiles = document.getElementById('btn-tab-files');
    const contentData = document.getElementById('modal-tab-data-content');
    const contentFiles = document.getElementById('modal-tab-files-content');
    
    if (tab === 'data') {
        btnData.classList.add('active');
        btnFiles.classList.remove('active');
        contentData.classList.remove('hidden');
        contentFiles.classList.add('hidden');
    } else {
        btnData.classList.remove('active');
        btnFiles.classList.add('active');
        contentData.classList.add('hidden');
        contentFiles.classList.remove('hidden');
    }
}

// Open modal to edit quality parameters
function openSupplementModal(episodeId) {
    const run = allExperiments.find(r => r.episode_id === episodeId);
    if (!run) return;

    // Reset active tab to 'data'
    switchModalTab('data');

    document.getElementById('modal-episode-id').textContent = run.episode_id;
    document.getElementById('modal-hidden-episode-id').value = run.episode_id;
    document.getElementById('modal-params-summary').textContent = 
        `${(run.power_kw / 0.6).toFixed(1)}% | ${run.speed_m_min}m/min | ${run.air_pressure_mpa}MPa | ${run.focus_mm}mm`;

    // Populate inputs
    document.getElementById('modal-cut-through').checked = run.cut_through;
    document.getElementById('modal-failure').value = run.failure_case || 'normal';
    document.getElementById('modal-dross-max').value = run.dross_height_max_mm !== null ? run.dross_height_max_mm : '';
    document.getElementById('modal-dross-mean').value = run.dross_height_mean_mm !== null ? run.dross_height_mean_mm : '';
    document.getElementById('modal-roughness').value = run.roughness_Sa_um !== null ? run.roughness_Sa_um : '';
    document.getElementById('modal-kerf-top').value = run.kerf_width_top_mm !== null ? run.kerf_width_top_mm : '';
    document.getElementById('modal-kerf-bottom').value = run.kerf_width_bottom_mm !== null ? run.kerf_width_bottom_mm : '';
    document.getElementById('modal-defect-area').value = run.defect_area_mm2 !== null ? run.defect_area_mm2 : '';
    document.getElementById('modal-quality-score').value = run.quality_score !== null ? run.quality_score : '';
    document.getElementById('modal-comment').value = run.manual_comment || '';

    // Reset file picker inputs
    const fileInputs = [
        'file-pc-front', 'file-pc-back', 'file-pc-left', 'file-pc-right', 'file-pc-dross',
        'file-img-front', 'file-img-back', 'file-img-left', 'file-img-right', 'file-img-top', 'file-img-bottom'
    ];
    fileInputs.forEach(id => {
        document.getElementById(id).value = '';
    });

    // Populate file status labels
    const fileFieldsMapping = {
        'status-pc-front': run.point_cloud_front,
        'status-pc-back': run.point_cloud_back,
        'status-pc-left': run.point_cloud_left,
        'status-pc-right': run.point_cloud_right,
        'status-pc-dross': run.point_cloud_dross,
        'status-img-front': run.image_front,
        'status-img-back': run.image_back,
        'status-img-left': run.image_left,
        'status-img-right': run.image_right,
        'status-img-top': run.image_top,
        'status-img-bottom': run.image_bottom
    };

    Object.entries(fileFieldsMapping).forEach(([statusId, dbVal]) => {
        const el = document.getElementById(statusId);
        if (dbVal) {
            const filename = dbVal.split('/').pop();
            el.textContent = `已归档: ${filename}`;
            el.classList.add('uploaded');
        } else {
            el.textContent = '未归档';
            el.classList.remove('uploaded');
        }
    });

    // Show modal
    document.getElementById('quality-modal').classList.remove('hidden');
}

function closeQualityModal() {
    document.getElementById('quality-modal').classList.add('hidden');
}

// Handle quality submission
async function handleSupplementQualitySubmit(e) {
    e.preventDefault();
    const episodeId = document.getElementById('modal-hidden-episode-id').value;

    const data = {
        cut_through: document.getElementById('modal-cut-through').checked,
        failure_case: document.getElementById('modal-failure').value,
        dross_height_max_mm: getFloatOrNull('modal-dross-max'),
        dross_height_mean_mm: getFloatOrNull('modal-dross-mean'),
        roughness_Sa_um: getFloatOrNull('modal-roughness'),
        kerf_width_top_mm: getFloatOrNull('modal-kerf-top'),
        kerf_width_bottom_mm: getFloatOrNull('modal-kerf-bottom'),
        defect_area_mm2: getFloatOrNull('modal-defect-area'),
        quality_score: getFloatOrNull('modal-quality-score'),
        manual_comment: document.getElementById('modal-comment').value
    };

    try {
        // 1. Save quality metrics data
        const res = await fetch(`/api/experiments/${episodeId}/quality`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!res.ok) throw new Error('保存检测数据失败');
        
        // 2. Upload any selected files
        const fileFieldsMapping = {
            'point_cloud_front': document.getElementById('file-pc-front').files[0],
            'point_cloud_back': document.getElementById('file-pc-back').files[0],
            'point_cloud_left': document.getElementById('file-pc-left').files[0],
            'point_cloud_right': document.getElementById('file-pc-right').files[0],
            'point_cloud_dross': document.getElementById('file-pc-dross').files[0],
            'image_front': document.getElementById('file-img-front').files[0],
            'image_back': document.getElementById('file-img-back').files[0],
            'image_left': document.getElementById('file-img-left').files[0],
            'image_right': document.getElementById('file-img-right').files[0],
            'image_top': document.getElementById('file-img-top').files[0],
            'image_bottom': document.getElementById('file-img-bottom').files[0]
        };

        const formData = new FormData();
        let hasFilesToUpload = false;

        Object.entries(fileFieldsMapping).forEach(([key, fileObj]) => {
            if (fileObj) {
                formData.append(key, fileObj);
                hasFilesToUpload = true;
            }
        });

        if (hasFilesToUpload) {
            const uploadRes = await fetch(`/api/experiments/${episodeId}/files`, {
                method: 'POST',
                body: formData
            });
            if (!uploadRes.ok) throw new Error('检测文件归档上传失败');
        }
        
        closeQualityModal();
        await loadExperiments();
    } catch (err) {
        alert('保存检测数据及文件出错: ' + err.message);
    }
}

// Open modal to modify parameters and rename ID
function openEditModal(episodeId) {
    const run = allExperiments.find(r => r.episode_id === episodeId);
    if (!run) return;

    document.getElementById('edit-hidden-old-id').value = run.episode_id;
    document.getElementById('edit-episode-id').value = run.episode_id;
    document.getElementById('edit-power').value = Math.round(run.power_kw / 0.6);
    document.getElementById('edit-speed').value = run.speed_m_min;
    document.getElementById('edit-pressure').value = run.air_pressure_mpa;
    document.getElementById('edit-focus').value = run.focus_mm;
    document.getElementById('edit-material').value = run.material;
    document.getElementById('edit-thickness').value = run.thickness_mm;
    document.getElementById('edit-gas').value = run.gas;
    document.getElementById('edit-nozzle-h').value = run.nozzle_height_mm;

    // Show modal
    document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.add('hidden');
}

// Handle parameters modification submit
async function handleEditParametersSubmit(e) {
    e.preventDefault();
    const oldId = document.getElementById('edit-hidden-old-id').value;

    const data = {
        new_episode_id: document.getElementById('edit-episode-id').value.trim(),
        power_kw: parseFloat(document.getElementById('edit-power').value) * 0.6,
        speed_m_min: parseFloat(document.getElementById('edit-speed').value),
        air_pressure_mpa: parseFloat(document.getElementById('edit-pressure').value),
        focus_mm: parseFloat(document.getElementById('edit-focus').value),
        material: document.getElementById('edit-material').value.trim(),
        thickness_mm: parseFloat(document.getElementById('edit-thickness').value),
        gas: document.getElementById('edit-gas').value.trim(),
        nozzle_height_mm: parseFloat(document.getElementById('edit-nozzle-h').value),
        nozzle_diameter_mm: 4.0 // Fixed / inherited
    };

    try {
        const res = await fetch(`/api/experiments/${oldId}/parameters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!res.ok) {
            const errBody = await res.json();
            throw new Error(errBody.detail || '修改保存失败');
        }
        
        closeEditModal();
        await loadExperiments();
    } catch (err) {
        alert('修改参数出错: ' + err.message);
    }
}

function getFloatOrNull(id) {
    const val = document.getElementById(id).value;
    return val === '' ? null : parseFloat(val);
}

// Range Analysis API execution
async function runRangeAnalysis() {
    try {
        const res = await fetch('/api/analyze', { method: 'POST' });
        if (!res.ok) throw new Error('极差分析执行失败');
        
        analysisData = await res.json();
        if (analysisData.status === 'warning') {
            alert(analysisData.message);
            return;
        }

        // Render analysis UI
        document.getElementById('analysis-section').classList.remove('hidden');
        renderAnalysisDetails();
        
        // Scroll to analysis
        document.getElementById('analysis-section').scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        alert('运行极差分析出错: ' + err.message);
    }
}

function renderAnalysisDetails() {
    if (!analysisData || analysisData.status !== 'success') return;

    // Render best observed trial
    const best = analysisData.best_observed;
    document.getElementById('best-observed-score').textContent = best.quality_score ? best.quality_score.toFixed(1) : '--';
    document.getElementById('best-observed-params').innerHTML = `
        <div>试验 ID: <strong>${best.episode_id}</strong></div>
        <div>激光功率: <strong>${(best.power_kw / 0.6).toFixed(1)}%</strong></div>
        <div>切割速度: <strong>${best.speed_m_min} m/min</strong></div>
        <div>辅助气压: <strong>${best.air_pressure_mpa} MPa</strong></div>
        <div>焦点位置: <strong>${best.focus_mm} mm</strong></div>
    `;

    // Render rankings for active tab metric
    renderMetricAnalysis(activeAnalysisMetric);
}

function switchAnalysisMetric(metric) {
    activeAnalysisMetric = metric;
    
    // Update active tab styling
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(btn => {
        if (btn.textContent.includes('综合得分') && metric === 'quality_score' ||
            btn.textContent.includes('最大挂渣') && metric === 'dross_height_max_mm' ||
            btn.textContent.includes('表面粗糙') && metric === 'roughness_Sa_um') {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    renderMetricAnalysis(metric);
}

function renderMetricAnalysis(metric) {
    const container = document.getElementById('metric-analysis-details');
    container.innerHTML = '';

    const metricInfo = analysisData.metrics_analysis[metric];
    if (!metricInfo) {
        container.innerHTML = '<p class="text-muted">本指标暂无足够的数据进行分析。确保至少有一些切割记录完成了质量打分。</p>';
        return;
    }

    // Convert ranges object to sorted array of [factor, range_value]
    const sortedRanges = Object.entries(metricInfo.ranges).sort((a, b) => b[1] - a[1]);
    
    let listHtml = '<div class="factor-rank-list">';
    sortedRanges.forEach((entry, idx) => {
        const factor = entry[0];
        const range = entry[1];
        const bestLvl = metricInfo.best_levels[factor];
        
        let labelName = factor;
        if (factor === 'power_kw') labelName = '激光功率';
        if (factor === 'speed_m_min') labelName = '切割速度';
        if (factor === 'air_pressure_mpa') labelName = '辅助气压';
        if (factor === 'focus_mm') labelName = '焦点位置';

        const rangeDisplay = factor === 'power_kw' ? (range / 0.6).toFixed(1) + '%' : range;
        const bestLvlDisplay = factor === 'power_kw' ? (bestLvl / 0.6).toFixed(1) + '%' : bestLvl;

        listHtml += `
            <div class="factor-rank-item">
                <div class="factor-name">
                    <span class="rank-badge rank-${idx+1}">${idx+1}</span>
                    <span>${labelName}</span>
                </div>
                <div class="factor-stats">
                    <span class="text-muted mr-4">极差值 R = ${rangeDisplay}</span>
                    <span class="factor-best-level">最优水平: ${bestLvlDisplay}</span>
                </div>
            </div>
        `;
    });
    listHtml += '</div>';

    // Append K-means table
    let tableHtml = `
        <h4 class="mt-4" style="font-size: 0.9rem; font-weight:600; margin-bottom: 0.5rem;">K平均值 (不同水平的平均得分情况)</h4>
        <table class="k-means-table">
            <thead>
                <tr>
                    <th>工艺因素</th>
                    <th>各水平平均值</th>
                </tr>
            </thead>
            <tbody>
    `;

    Object.entries(metricInfo.k_means).forEach(([factor, means]) => {
        let labelName = factor;
        if (factor === 'power_kw') labelName = '激光功率 (%)';
        if (factor === 'speed_m_min') labelName = '切割速度 (m/min)';
        if (factor === 'air_pressure_mpa') labelName = '辅助气压 (MPa)';
        if (factor === 'focus_mm') labelName = '焦点位置 (mm)';

        const meansStr = Object.entries(means)
            .map(([lvl, val]) => {
                let lvlLabel = lvl;
                if (factor === 'power_kw') {
                    lvlLabel = (parseFloat(lvl) / 0.6).toFixed(0) + '%';
                }
                return `<strong>${lvlLabel}</strong>: ${val}`;
            })
            .join(' | ');

        tableHtml += `
            <tr>
                <td style="text-align: left; font-weight:600;">${labelName}</td>
                <td>${meansStr}</td>
            </tr>
        `;
    });

    tableHtml += '</tbody></table>';

    container.innerHTML = listHtml + tableHtml;
}

function closeAnalysis() {
    document.getElementById('analysis-section').classList.add('hidden');
}

// ==========================================
// 3D Point Cloud & 2D Image Previewer Tab
// ==========================================

let threeScene, threeCamera, threeRenderer, threeControls, threePointsObj;
let originalPointsData = [];
let currentPointsData = [];
let currentPreviewFieldKey = "";
let currentPreviewEpisodeId = "";
let currentActualPointCount = null;
let currentFullMorphology = null;

// Main Tab switching
function switchMainTab(tab) {
    const btnExp = document.getElementById('btn-main-tab-experiments');
    const btnPrev = document.getElementById('btn-main-tab-preview');
    const contentExp = document.getElementById('tab-experiments-content');
    const contentPrev = document.getElementById('tab-preview-content');
    
    if (tab === 'experiments') {
        btnExp.classList.add('active');
        btnPrev.classList.remove('active');
        contentExp.classList.remove('hidden');
        contentPrev.classList.add('hidden');
    } else {
        btnExp.classList.remove('active');
        btnPrev.classList.add('active');
        contentExp.classList.add('hidden');
        contentPrev.classList.remove('hidden');
        
        refreshPreviewTrialsCombo();
        setTimeout(resizeThreeJS, 100);
    }
}

// Populate the preview trials select dropdown
function refreshPreviewTrialsCombo() {
    const select = document.getElementById('preview-trial-select');
    if (!select) return;
    
    const currentVal = select.value;
    select.innerHTML = '';
    
    if (allExperiments.length === 0) {
        select.innerHTML = '<option value="">-- 无试验记录 --</option>';
        onPreviewTrialChanged();
        return;
    }
    
    allExperiments.forEach(run => {
        const opt = document.createElement('option');
        opt.value = run.episode_id;
        opt.textContent = run.episode_id;
        select.appendChild(opt);
    });
    
    if (currentVal && allExperiments.some(r => r.episode_id === currentVal)) {
        select.value = currentVal;
    } else {
        select.selectedIndex = 0;
    }
    onPreviewTrialChanged();
}

// When selected trial dropdown changes in preview tab
function onPreviewTrialChanged() {
    const select = document.getElementById('preview-trial-select');
    const slotsContainer = document.getElementById('preview-file-slots');
    slotsContainer.innerHTML = '';
    
    const episodeId = select.value;
    if (!episodeId) {
        slotsContainer.innerHTML = '<div class="text-muted text-center py-4">请先选择一个试验记录</div>';
        resetWebPreviewControls();
        return;
    }
    
    const run = allExperiments.find(r => r.episode_id === episodeId);
    if (!run) return;
    
    const fileDefinitions = [
        ["point_cloud_front", "前切面点云 (3D)"],
        ["point_cloud_back", "后切面点云 (3D)"],
        ["point_cloud_left", "左切面点云 (3D)"],
        ["point_cloud_right", "右切面点云 (3D)"],
        ["point_cloud_dross", "挂渣底面点云 (3D)"],
        ["image_front", "前切面图像 (2D)"],
        ["image_back", "后切面图像 (2D)"],
        ["image_left", "左切面图像 (2D)"],
        ["image_right", "右切面图像 (2D)"],
        ["image_top", "上表面图像 (2D)"],
        ["image_bottom", "下表面图像 (2D)"],
    ];
    
    fileDefinitions.forEach(([fieldKey, label]) => {
        const val = run[fieldKey];
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.justifyContent = 'space-between';
        row.style.padding = '0.4rem 0.6rem';
        row.style.borderRadius = '6px';
        row.style.background = 'rgba(255,255,255,0.02)';
        row.style.border = '1px solid rgba(255,255,255,0.04)';
        
        const lblSpan = document.createElement('span');
        lblSpan.textContent = label;
        lblSpan.style.fontWeight = 'bold';
        lblSpan.style.fontSize = '0.85rem';
        
        const statusSpan = document.createElement('span');
        statusSpan.style.fontSize = '0.75rem';
        
        const btn = document.createElement('button');
        btn.textContent = '查看';
        btn.className = 'btn btn-secondary btn-sm';
        btn.style.padding = '0.2rem 0.5rem';
        
        if (val) {
            const filename = val.split('/').pop();
            statusSpan.textContent = `已录入 (${filename})`;
            statusSpan.style.color = '#2ec4b6';
            btn.disabled = false;
            btn.onclick = () => viewInspectionFileInWeb(fieldKey, val, run);
        } else {
            statusSpan.textContent = '未录入';
            statusSpan.style.color = '#94a3b8';
            btn.disabled = true;
        }
        
        const rightDiv = document.createElement('div');
        rightDiv.style.display = 'flex';
        rightDiv.style.alignItems = 'center';
        rightDiv.style.gap = '0.75rem';
        rightDiv.appendChild(statusSpan);
        rightDiv.appendChild(btn);
        
        row.appendChild(lblSpan);
        row.appendChild(rightDiv);
        slotsContainer.appendChild(row);
    });
}

function resetWebPreviewControls() {
    document.getElementById('web-pc-count').textContent = '--';
    document.getElementById('web-pc-size-x').textContent = '--';
    document.getElementById('web-pc-size-y').textContent = '--';
    document.getElementById('web-pc-size-z').textContent = '--';
    document.getElementById('web-btn-denoise').disabled = true;
    document.getElementById('web-btn-downsample').disabled = true;
    document.getElementById('web-btn-reset').disabled = true;
    document.getElementById('web-core-ratio').disabled = true;
    document.getElementById('web-btn-extract-core').disabled = true;
    document.getElementById('web-btn-adaptive-core').disabled = true;
    document.getElementById('web-btn-adaptive-core').textContent = '自适应识别并提取中心切面';
    document.getElementById('web-btn-remove-spikes').disabled = true;
    document.getElementById('web-btn-remove-spikes').textContent = '提取真实切面层（去底面/毛刺）';
    document.getElementById('web-btn-morphology').disabled = true;
    clearWebMorphologyResult();
    
    document.getElementById('preview-placeholder').classList.remove('hidden');
    document.getElementById('webgl-canvas').classList.add('hidden');
    document.getElementById('image-viewer').classList.add('hidden');
}

// Display selected file in Web viewer
async function viewInspectionFileInWeb(fieldKey, relPath, run) {
    resetWebPreviewControls();
    currentPreviewFieldKey = fieldKey;
    currentPreviewEpisodeId = run.episode_id;
    
    const isPointCloud = fieldKey.includes('cloud');
    document.getElementById('preview-placeholder').classList.add('hidden');
    
    if (isPointCloud) {
        document.getElementById('webgl-canvas').classList.remove('hidden');
        document.getElementById('image-viewer').classList.add('hidden');
        
        initThreeJS();
        
        // Fetch point cloud file content
        try {
            // Prepend relative path from FastAPI static root
            const url = `/api/experiments/${run.episode_id}/pointcloud?field=${fieldKey}`;
            const response = await fetch(url);
            if (!response.ok) throw new Error('从服务器获取点云数据失败');
            const data = await response.json();
            
            originalPointsData = data.points.map(pt => ({ x: pt[0], y: pt[1], z: pt[2] }));
            currentPointsData = [...originalPointsData];
            currentActualPointCount = null;
            currentFullMorphology = null;
            
            document.getElementById('web-btn-denoise').disabled = false;
            document.getElementById('web-btn-downsample').disabled = false;
            document.getElementById('web-btn-reset').disabled = false;
            document.getElementById('web-core-ratio').disabled = false;
            document.getElementById('web-btn-extract-core').disabled = false;
            document.getElementById('web-btn-adaptive-core').disabled = false;
            document.getElementById('web-btn-remove-spikes').disabled = false;
            document.getElementById('web-btn-morphology').disabled = false;
            
            updateWebPointCloudView();
        } catch (err) {
            alert('加载点云文件出错: ' + err.message);
            resetWebPreviewControls();
        }
    } else {
        // 2D Image View
        document.getElementById('webgl-canvas').classList.add('hidden');
        const imgViewer = document.getElementById('image-viewer');
        imgViewer.classList.remove('hidden');
        resetImageTransform();
        
        let displayPath = `/${relPath}`;
        const ext = relPath.split('.').pop().toLowerCase();
        
        // If it's a TIF file, show the pre-converted PNG copy
        if (ext === 'tif' || ext === 'tiff') {
            const baseWithoutExt = relPath.substring(0, relPath.lastIndexOf('.'));
            displayPath = `/${baseWithoutExt}.png`;
        }
        
        imgViewer.src = displayPath;
        imgViewer.onerror = () => {
            imgViewer.alt = "图片加载失败 (如果是TIF，请确认服务已自动转换PNG)";
        };
    }
}

// Initialize Three.js WebGL canvas
function initThreeJS() {
    const container = document.getElementById('webgl-canvas');
    if (threeRenderer) {
        resizeThreeJS();
        return;
    }
    
    threeScene = new THREE.Scene();
    threeScene.background = new THREE.Color(0x0b101d);
    
    threeCamera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.05, 100);
    threeCamera.position.set(0, 0, 2);
    
    threeRenderer = new THREE.WebGLRenderer({ antialias: true });
    threeRenderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(threeRenderer.domElement);
    
    threeControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
    threeControls.enableDamping = true;
    threeControls.dampingFactor = 0.05;
    
    const axesHelper = new THREE.AxesHelper(0.3);
    threeScene.add(axesHelper);
    
    function animate() {
        requestAnimationFrame(animate);
        if (threeControls) threeControls.update();
        if (threeRenderer) threeRenderer.render(threeScene, threeCamera);
    }
    animate();
    
    window.addEventListener('resize', resizeThreeJS);
}

function resizeThreeJS() {
    const container = document.getElementById('webgl-canvas');
    if (threeRenderer && threeCamera && container && container.clientWidth > 0) {
        threeCamera.aspect = container.clientWidth / container.clientHeight;
        threeCamera.updateProjectionMatrix();
        threeRenderer.setSize(container.clientWidth, container.clientHeight);
    }
}

// Render points using buffer geometry
function renderPointsInThree(points) {
    if (threePointsObj) {
        threeScene.remove(threePointsObj);
        threePointsObj.geometry.dispose();
        threePointsObj.material.dispose();
        threePointsObj = null;
    }
    
    if (points.length === 0) return;
    
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    points.forEach(p => {
        if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
        if (p.z < minZ) minZ = p.z; if (p.z > maxZ) maxZ = p.z;
    });
    
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const centerZ = (minZ + maxZ) / 2;
    
    const maxRange = Math.max(maxX - minX, maxY - minY, maxZ - minZ) || 1.0;
    
    points.forEach((p, idx) => {
        const px = (p.x - centerX) / maxRange;
        const py = (p.y - centerY) / maxRange;
        const pz = (p.z - centerZ) / maxRange;
        
        positions[idx * 3] = px;
        positions[idx * 3 + 1] = py;
        positions[idx * 3 + 2] = pz;
        
        // Depth gradient color map: Cyan (56, 189, 248) -> Purple (168, 85, 247)
        const t = pz + 0.5; // map normalized [-0.5, 0.5] depth to [0, 1]
        colors[idx * 3] = (56 + (168 - 56) * t) / 255;
        colors[idx * 3 + 1] = (189 + (85 - 189) * t) / 255;
        colors[idx * 3 + 2] = (248 + (247 - 248) * t) / 255;
    });
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    
    const material = new THREE.PointsMaterial({
        size: 0.015,
        vertexColors: true,
        transparent: true,
        opacity: 0.85
    });
    
    threePointsObj = new THREE.Points(geometry, material);
    threeScene.add(threePointsObj);
    
    threeCamera.position.set(0, 0, 1.4);
    threeControls.reset();
}

// Parse PCD, PLY, ASC, CSV content in JS
function parsePointCloudData(text, ext) {
    const points = [];
    const lines = text.split('\n');
    
    if (ext === 'pcd') {
        let headerEnded = false;
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line) continue;
            if (!headerEnded) {
                if (line.startsWith('DATA ascii')) {
                    headerEnded = true;
                }
                continue;
            }
            const parts = line.split(/\s+/);
            if (parts.length >= 3) {
                const x = parseFloat(parts[0]);
                const y = parseFloat(parts[1]);
                const z = parseFloat(parts[2]);
                if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
                    points.push({ x, y, z });
                }
            }
        }
    } else {
        const isPly = (ext === 'ply');
        let headerEnded = !isPly;
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line) continue;
            if (isPly && !headerEnded) {
                if (line === 'end_header') {
                    headerEnded = true;
                }
                continue;
            }
            
            let parts = [];
            if (line.includes(',')) parts = line.split(',');
            else if (line.includes(';')) parts = line.split(';');
            else if (line.includes('\t')) parts = line.split('\t');
            else parts = line.split(/\s+/);
            
            if (parts.length >= 3) {
                const x = parseFloat(parts[0]);
                const y = parseFloat(parts[1]);
                const z = parseFloat(parts[2]);
                if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
                    points.push({ x, y, z });
                }
            }
        }
    }
    return points;
}

function updateWebPointCloudView() {
    renderPointsInThree(currentPointsData);
    
    const countEl = document.getElementById('web-pc-count');
    const xEl = document.getElementById('web-pc-size-x');
    const yEl = document.getElementById('web-pc-size-y');
    const zEl = document.getElementById('web-pc-size-z');
    
    countEl.textContent = currentActualPointCount === null
        ? currentPointsData.length.toLocaleString()
        : `${currentActualPointCount.toLocaleString()}（渲染 ${currentPointsData.length.toLocaleString()}）`;
    
    if (currentPointsData.length > 0) {
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;
        let minZ = Infinity, maxZ = -Infinity;
        
        currentPointsData.forEach(p => {
            if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
            if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
            if (p.z < minZ) minZ = p.z; if (p.z > maxZ) maxZ = p.z;
        });
        
        xEl.textContent = (maxX - minX).toFixed(2) + ' mm';
        yEl.textContent = (maxY - minY).toFixed(2) + ' mm';
        zEl.textContent = (maxZ - minZ).toFixed(2) + ' mm';
    } else {
        xEl.textContent = '--';
        yEl.textContent = '--';
        zEl.textContent = '--';
    }
}

// Denoise point cloud in JS
function webDenoisePointCloud() {
    if (currentPointsData.length < 10) return;
    
    // Compute mean
    let sumX = 0, sumY = 0, sumZ = 0;
    currentPointsData.forEach(p => {
        sumX += p.x; sumY += p.y; sumZ += p.z;
    });
    const meanX = sumX / currentPointsData.length;
    const meanY = sumY / currentPointsData.length;
    const meanZ = sumZ / currentPointsData.length;
    
    // Compute standard deviation
    let sqSumX = 0, sqSumY = 0, sqSumZ = 0;
    currentPointsData.forEach(p => {
        sqSumX += Math.pow(p.x - meanX, 2);
        sqSumY += Math.pow(p.y - meanY, 2);
        sqSumZ += Math.pow(p.z - meanZ, 2);
    });
    const stdX = Math.sqrt(sqSumX / currentPointsData.length) || 1.0;
    const stdY = Math.sqrt(sqSumY / currentPointsData.length) || 1.0;
    const stdZ = Math.sqrt(sqSumZ / currentPointsData.length) || 1.0;
    
    // Keep points within 3 std
    currentPointsData = currentPointsData.filter(p => {
        return Math.abs(p.x - meanX) < 3 * stdX &&
               Math.abs(p.y - meanY) < 3 * stdY &&
               Math.abs(p.z - meanZ) < 3 * stdZ;
    });
    currentActualPointCount = null;
    currentFullMorphology = null;
    clearWebMorphologyResult();
    updateWebPointCloudView();
}

// Downsample point cloud in JS
function webDownsamplePointCloud() {
    const target = 5000;
    if (currentPointsData.length <= target) return;
    
    const step = Math.floor(currentPointsData.length / target);
    const downsampled = [];
    for (let i = 0; i < currentPointsData.length; i += step) {
        downsampled.push(currentPointsData[i]);
        if (downsampled.length >= target) break;
    }
    currentPointsData = downsampled;
    currentActualPointCount = null;
    currentFullMorphology = null;
    clearWebMorphologyResult();
    updateWebPointCloudView();
}

// Extract a centered X/Y region from the original cloud and retain full Z depth.
function webExtractCoreRegion() {
    if (originalPointsData.length === 0) return;

    const keepRatio = Number(document.getElementById('web-core-ratio').value) / 100;
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;

    originalPointsData.forEach(p => {
        if (p.x < minX) minX = p.x;
        if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.y > maxY) maxY = p.y;
    });

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const halfWidth = (maxX - minX) * keepRatio / 2;
    const halfHeight = (maxY - minY) * keepRatio / 2;

    const corePoints = originalPointsData.filter(p =>
        p.x >= centerX - halfWidth && p.x <= centerX + halfWidth &&
        p.y >= centerY - halfHeight && p.y <= centerY + halfHeight
    );

    if (corePoints.length === 0) {
        alert('当前比例内没有点，请增大核心区域比例后重试。');
        return;
    }

    currentPointsData = [...corePoints];
    currentActualPointCount = null;
    currentFullMorphology = null;
    clearWebMorphologyResult();
    updateWebPointCloudView();
}

function adaptiveDenseBounds(values, binCount = 64) {
    const sorted = [...values].sort((a, b) => a - b);
    const percentile = q => {
        const pos = (sorted.length - 1) * q;
        const lower = Math.floor(pos);
        const upper = Math.ceil(pos);
        const weight = pos - lower;
        return sorted[lower] * (1 - weight) + sorted[upper] * weight;
    };

    const robustMin = percentile(0.005);
    const robustMax = percentile(0.995);
    if (robustMax <= robustMin) return [robustMin, robustMax];

    const hist = new Array(binCount).fill(0);
    values.forEach(value => {
        if (value < robustMin || value > robustMax) return;
        const normalized = (value - robustMin) / (robustMax - robustMin);
        const index = Math.min(binCount - 1, Math.floor(normalized * binCount));
        hist[index] += 1;
    });

    const smooth = hist.map((_, index) => {
        let total = 0;
        let count = 0;
        for (let offset = -2; offset <= 2; offset++) {
            const sampleIndex = index + offset;
            if (sampleIndex >= 0 && sampleIndex < binCount) {
                total += hist[sampleIndex];
                count += 1;
            }
        }
        return total / count;
    });

    const center = Math.floor(binCount / 2);
    const radius = Math.max(2, Math.floor(binCount / 6));
    let seed = Math.max(0, center - radius);
    for (let i = seed + 1; i <= Math.min(binCount - 1, center + radius); i++) {
        if (smooth[i] > smooth[seed]) seed = i;
    }

    const positive = smooth.filter(value => value > 0).sort((a, b) => a - b);
    if (smooth[seed] <= 0 || positive.length === 0) return [robustMin, robustMax];
    const densityFloor = positive[Math.floor((positive.length - 1) * 0.5)];
    const threshold = Math.min(
        Math.max(smooth[seed] * 0.25, densityFloor),
        smooth[seed] * 0.8
    );

    let left = seed;
    let right = seed;
    while (left > 0 && smooth[left - 1] >= threshold) left--;
    while (right < binCount - 1 && smooth[right + 1] >= threshold) right++;
    left = Math.max(0, left - 1);
    right = Math.min(binCount - 1, right + 1);

    const binWidth = (robustMax - robustMin) / binCount;
    return [robustMin + left * binWidth, robustMin + (right + 1) * binWidth];
}

function numericPercentile(values, q) {
    const sorted = [...values].sort((a, b) => a - b);
    const pos = (sorted.length - 1) * q;
    const lower = Math.floor(pos);
    const upper = Math.ceil(pos);
    const weight = pos - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function solveThreeByThree(matrix, vector) {
    const augmented = matrix.map((row, index) => [...row, vector[index]]);
    for (let column = 0; column < 3; column++) {
        let pivot = column;
        for (let row = column + 1; row < 3; row++) {
            if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) {
                pivot = row;
            }
        }
        if (Math.abs(augmented[pivot][column]) < 1e-12) return null;
        [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
        const divisor = augmented[column][column];
        for (let j = column; j < 4; j++) augmented[column][j] /= divisor;
        for (let row = 0; row < 3; row++) {
            if (row === column) continue;
            const factor = augmented[row][column];
            for (let j = column; j < 4; j++) {
                augmented[row][j] -= factor * augmented[column][j];
            }
        }
    }
    return augmented.map(row => row[3]);
}

function fitBackgroundPlane(points) {
    let sx = 0, sy = 0, sz = 0;
    let sxx = 0, syy = 0, sxy = 0, sxz = 0, syz = 0;
    points.forEach(p => {
        sx += p.x; sy += p.y; sz += p.z;
        sxx += p.x * p.x; syy += p.y * p.y; sxy += p.x * p.y;
        sxz += p.x * p.z; syz += p.y * p.z;
    });
    return solveThreeByThree(
        [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, points.length]],
        [sxz, syz, sz]
    );
}

function detectHeightCoreBounds(points, binCount = 64) {
    const xs = points.map(p => p.x);
    const ys = points.map(p => p.y);
    const minX = numericPercentile(xs, 0.005);
    const maxX = numericPercentile(xs, 0.995);
    const minY = numericPercentile(ys, 0.005);
    const maxY = numericPercentile(ys, 0.995);
    const rangeX = maxX - minX;
    const rangeY = maxY - minY;
    if (rangeX <= 0 || rangeY <= 0) return null;

    const normalized = points.map(p => ({
        point: p,
        nx: (p.x - minX) / rangeX,
        ny: (p.y - minY) / rangeY
    }));
    let outer = normalized.filter(item =>
        item.nx <= 0.15 || item.nx >= 0.85 ||
        item.ny <= 0.15 || item.ny >= 0.85
    ).map(item => item.point);
    if (outer.length < 30) return null;

    let plane = fitBackgroundPlane(outer);
    if (!plane) return null;
    for (let iteration = 0; iteration < 2; iteration++) {
        const errors = outer.map(p => p.z - (plane[0] * p.x + plane[1] * p.y + plane[2]));
        const errorCenter = numericPercentile(errors, 0.5);
        const mad = numericPercentile(errors.map(value => Math.abs(value - errorCenter)), 0.5);
        if (mad <= 1e-9) break;
        const limit = 3.5 * 1.4826 * mad;
        const inliers = outer.filter((_, index) => Math.abs(errors[index] - errorCenter) <= limit);
        if (inliers.length < 30) break;
        outer = inliers;
        plane = fitBackgroundPlane(outer);
        if (!plane) return null;
    }

    const residuals = normalized.map(item =>
        item.point.z - (plane[0] * item.point.x + plane[1] * item.point.y + plane[2])
    );
    const outerResiduals = outer.map(p =>
        p.z - (plane[0] * p.x + plane[1] * p.y + plane[2])
    );
    const backgroundCenter = numericPercentile(outerResiduals, 0.5);
    const backgroundMad = numericPercentile(
        outerResiduals.map(value => Math.abs(value - backgroundCenter)),
        0.5
    ) * 1.4826;
    const centeredResiduals = residuals.map(value => value - backgroundCenter);
    const centerResiduals = centeredResiduals.filter((_, index) => {
        const item = normalized[index];
        return item.nx >= 0.38 && item.nx <= 0.62 &&
               item.ny >= 0.38 && item.ny <= 0.62;
    });
    if (centerResiduals.length < 10) return null;
    const centerHeight = numericPercentile(centerResiduals, 0.5);
    if (Math.abs(centerHeight) < Math.max(backgroundMad * 6, 0.05)) return null;

    const direction = centerHeight >= 0 ? 1 : -1;
    let signed = centeredResiduals.map(value => direction * value);
    const clipLow = numericPercentile(signed, 0.01);
    const clipHigh = numericPercentile(signed, 0.99);
    signed = signed.map(value => Math.max(clipLow, Math.min(clipHigh, value)));

    const bounds = [];
    for (const axis of ['nx', 'ny']) {
        const sums = new Array(binCount).fill(0);
        const counts = new Array(binCount).fill(0);
        normalized.forEach((item, index) => {
            const bin = Math.max(0, Math.min(binCount - 1, Math.floor(item[axis] * binCount)));
            sums[bin] += signed[index];
            counts[bin] += 1;
        });
        let profile = sums.map((sum, index) => counts[index] ? sum / counts[index] : 0);
        profile = profile.map((_, index) => {
            let total = 0;
            for (let offset = -1; offset <= 1; offset++) {
                const sample = index + offset;
                if (sample >= 0 && sample < binCount) total += profile[sample];
            }
            return total / 3;
        });

        const center = Math.floor(binCount / 2);
        const radius = Math.max(2, Math.floor(binCount / 6));
        let seed = center - radius;
        for (let i = seed + 1; i <= center + radius; i++) {
            if (profile[i] > profile[seed]) seed = i;
        }
        const threshold = Math.max(backgroundMad * 4, profile[seed] * 0.40);
        if (profile[seed] <= threshold) return null;
        let left = seed;
        let right = seed;
        while (left > 0 && profile[left - 1] >= threshold) left--;
        while (right < binCount - 1 && profile[right + 1] >= threshold) right++;
        bounds.push([left, right]);
    }

    return {
        x: [minX + bounds[0][0] * rangeX / binCount,
            minX + (bounds[0][1] + 1) * rangeX / binCount],
        y: [minY + bounds[1][0] * rangeY / binCount,
            minY + (bounds[1][1] + 1) * rangeY / binCount]
    };
}

function removeFloatingSpikes(points, sigmaThreshold = 8, minHeightMm = 0.5) {
    if (points.length < 20) return [...points];

    const xs = points.map(p => p.x);
    const ys = points.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = maxX - minX;
    const spanY = maxY - minY;
    const maxSpan = Math.max(spanX, spanY);
    if (maxSpan <= 0) return [...points];

    const target = Math.max(4, Math.floor(Math.sqrt(points.length / 8)));
    const gridX = Math.max(4, Math.round(target * spanX / maxSpan));
    const gridY = Math.max(4, Math.round(target * spanY / maxSpan));
    const cells = new Map();
    points.forEach((p, index) => {
        const ix = Math.max(0, Math.min(gridX - 1, Math.floor((p.x - minX) / Math.max(spanX, 1e-9) * gridX)));
        const iy = Math.max(0, Math.min(gridY - 1, Math.floor((p.y - minY) / Math.max(spanY, 1e-9) * gridY)));
        const key = `${ix},${iy}`;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(index);
    });

    const localMedian = points.map(p => p.z);
    cells.forEach((indices, key) => {
        const [ix, iy] = key.split(',').map(Number);
        const neighbors = [];
        for (let dx = -1; dx <= 1; dx++) {
            for (let dy = -1; dy <= 1; dy++) {
                const nearby = cells.get(`${ix + dx},${iy + dy}`);
                if (nearby) neighbors.push(...nearby);
            }
        }
        if (neighbors.length >= 6) {
            const medianZ = numericPercentile(neighbors.map(index => points[index].z), 0.5);
            indices.forEach(index => { localMedian[index] = medianZ; });
        }
    });

    const residuals = points.map((p, index) => p.z - localMedian[index]);
    const residualCenter = numericPercentile(residuals, 0.5);
    const noiseMad = numericPercentile(
        residuals.map(value => Math.abs(value - residualCenter)),
        0.5
    ) * 1.4826;
    const cutoff = Math.max(minHeightMm, sigmaThreshold * noiseMad);
    return points.filter((_, index) => residuals[index] <= cutoff);
}

function extractConnectedSurfaceLayer(points) {
    if (points.length < 30) return [...points];

    const minX = Math.min(...points.map(p => p.x));
    const maxX = Math.max(...points.map(p => p.x));
    const minY = Math.min(...points.map(p => p.y));
    const maxY = Math.max(...points.map(p => p.y));
    const spanX = maxX - minX;
    const spanY = maxY - minY;
    const maxSpan = Math.max(spanX, spanY);
    if (maxSpan <= 0) return removeFloatingSpikes(points);

    const normalized = points.map(p => ({
        nx: (p.x - minX) / Math.max(spanX, 1e-9),
        ny: (p.y - minY) / Math.max(spanY, 1e-9)
    }));
    const centerZ = points
        .filter((_, index) => {
            const item = normalized[index];
            return item.nx >= 0.35 && item.nx <= 0.65 &&
                   item.ny >= 0.35 && item.ny <= 0.65;
        })
        .map(p => p.z);
    if (centerZ.length < 10) return removeFloatingSpikes(points);

    const centerHeight = numericPercentile(centerZ, 0.5);
    const centerMad = numericPercentile(
        centerZ.map(value => Math.abs(value - centerHeight)),
        0.5
    ) * 1.4826;
    const neighborTolerance = Math.max(0.6, 8 * centerMad);
    const layerTolerance = Math.max(1.2, 12 * centerMad);
    const pointTolerance = Math.max(0.5, 8 * centerMad);

    const target = Math.max(6, Math.floor(Math.sqrt(points.length / 4)));
    const gridX = Math.max(6, Math.round(target * spanX / maxSpan));
    const gridY = Math.max(6, Math.round(target * spanY / maxSpan));
    const cells = new Map();
    const pointCellKeys = [];
    normalized.forEach((item, index) => {
        const ix = Math.max(0, Math.min(gridX - 1, Math.floor(item.nx * gridX)));
        const iy = Math.max(0, Math.min(gridY - 1, Math.floor(item.ny * gridY)));
        const key = `${ix},${iy}`;
        pointCellKeys[index] = key;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(index);
    });

    const cellHeight = new Map();
    cells.forEach((indices, key) => {
        cellHeight.set(key, numericPercentile(indices.map(index => points[index].z), 0.5));
    });

    let seedKey = null;
    let seedScore = Infinity;
    cells.forEach((_, key) => {
        const [ix, iy] = key.split(',').map(Number);
        const nx = (ix + 0.5) / gridX;
        const ny = (iy + 0.5) / gridY;
        if (nx < 0.30 || nx > 0.70 || ny < 0.30 || ny > 0.70) return;
        const score = Math.abs(cellHeight.get(key) - centerHeight) +
            0.02 * (Math.pow(ix + 0.5 - gridX / 2, 2) +
                    Math.pow(iy + 0.5 - gridY / 2, 2));
        if (score < seedScore) {
            seedScore = score;
            seedKey = key;
        }
    });
    if (!seedKey) return removeFloatingSpikes(points);

    const selected = new Set([seedKey]);
    const queue = [seedKey];
    for (let queueIndex = 0; queueIndex < queue.length; queueIndex++) {
        const key = queue[queueIndex];
        const [ix, iy] = key.split(',').map(Number);
        for (let dx = -1; dx <= 1; dx++) {
            for (let dy = -1; dy <= 1; dy++) {
                const neighborKey = `${ix + dx},${iy + dy}`;
                if (!cells.has(neighborKey) || selected.has(neighborKey)) continue;
                if (
                    Math.abs(cellHeight.get(neighborKey) - cellHeight.get(key)) <= neighborTolerance &&
                    Math.abs(cellHeight.get(neighborKey) - centerHeight) <= layerTolerance
                ) {
                    selected.add(neighborKey);
                    queue.push(neighborKey);
                }
            }
        }
    }

    const surface = points.filter((p, index) => {
        const key = pointCellKeys[index];
        if (!selected.has(key)) return false;
        return Math.abs(p.z - cellHeight.get(key)) <= pointTolerance &&
               Math.abs(p.z - centerHeight) <= layerTolerance;
    });
    if (surface.length < Math.max(20, points.length * 0.10)) {
        return removeFloatingSpikes(points);
    }
    return surface;
}

async function webExtractAdaptiveCoreRegion() {
    if (!currentPreviewEpisodeId || !currentPreviewFieldKey) return;

    const button = document.getElementById('web-btn-adaptive-core');
    button.disabled = true;
    button.textContent = '正在从原始点云提取完整切面…';
    try {
        const response = await fetch(
            `/api/experiments/${encodeURIComponent(currentPreviewEpisodeId)}/surface-process` +
            `?field=${encodeURIComponent(currentPreviewFieldKey)}`,
            { method: 'POST' }
        );
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '原始切面提取失败');
        }
        const result = await response.json();
        currentPointsData = result.display_points.map(
            pt => ({ x: pt[0], y: pt[1], z: pt[2] })
        );
        currentActualPointCount = result.surface_point_count;
        currentFullMorphology = result.morphology;
        updateWebPointCloudView();

        button.textContent =
            `完整切面：${result.surface_point_count.toLocaleString()} / ` +
            `${result.source_point_count.toLocaleString()} 点`;
        const removed = result.roi_point_count - result.surface_point_count;
        document.getElementById('web-btn-remove-spikes').textContent =
            `已剔除 ${removed.toLocaleString()} 个底面/毛刺点`;
        document.getElementById('web-btn-remove-spikes').disabled = true;
        renderWebMorphologyResult(currentFullMorphology);
    } catch (error) {
        alert(`原始切面提取失败：${error.message}`);
        button.textContent = '自适应识别并提取中心切面';
    } finally {
        button.disabled = false;
    }
}

function webRemoveFloatingSpikes() {
    if (currentPointsData.length === 0) return;
    const before = currentPointsData.length;
    currentPointsData = extractConnectedSurfaceLayer(currentPointsData);
    currentActualPointCount = null;
    currentFullMorphology = null;
    document.getElementById('web-btn-remove-spikes').textContent =
        `已剔除 ${before - currentPointsData.length} 个底面/毛刺点`;
    document.getElementById('web-btn-remove-spikes').disabled = true;
    updateWebPointCloudView();
    webAnalyzeSurfaceMorphology();
}

function clearWebMorphologyResult() {
    const container = document.getElementById('web-morphology-results');
    if (container) {
        container.textContent = '提取真实切面后，可计算 Sa、Sq、Sz 等形貌指标';
    }
}

async function webAnalyzeSurfaceMorphology() {
    if (currentPointsData.length < 3) return;
    if (currentFullMorphology) {
        renderWebMorphologyResult(currentFullMorphology);
        return;
    }
    const container = document.getElementById('web-morphology-results');
    container.textContent = '正在计算切面形貌…';
    try {
        const response = await fetch('/api/surface/morphology', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentPointsData.map(p => [p.x, p.y, p.z]))
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '形貌计算失败');
        }
        const result = await response.json();
        renderWebMorphologyResult(result);
    } catch (error) {
        container.textContent = `形貌计算失败：${error.message}`;
    }
}

function renderWebMorphologyResult(result) {
    const container = document.getElementById('web-morphology-results');
    container.replaceChildren();

    const count = document.createElement('div');
    const countLabel = result === currentFullMorphology ? '原始有效点数' : '当前点数';
    count.textContent = `${countLabel}：${result.point_count.toLocaleString()}`;
    count.style.marginBottom = '0.4rem';
    count.style.color = 'var(--text-main)';
    container.appendChild(count);

    result.metrics.forEach(item => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.gap = '0.75rem';
        row.style.padding = '0.22rem 0';
        const label = document.createElement('span');
        label.textContent = item.label;
        label.title = item.description;
        const value = document.createElement('strong');
        value.textContent = `${item.value}${item.unit ? ` ${item.unit}` : ''}`;
        value.style.color = '#38bdf8';
        row.append(label, value);
        container.appendChild(row);
    });

    const note = document.createElement('div');
    note.textContent = result.note;
    note.style.marginTop = '0.5rem';
    note.style.fontSize = '0.72rem';
    container.appendChild(note);
}

// Reset point cloud to original
function webResetPointCloud() {
    currentPointsData = [...originalPointsData];
    currentActualPointCount = null;
    currentFullMorphology = null;
    document.getElementById('web-btn-adaptive-core').textContent = '自适应识别并提取中心切面';
    document.getElementById('web-btn-remove-spikes').textContent = '提取真实切面层（去底面/毛刺）';
    document.getElementById('web-btn-remove-spikes').disabled = false;
    clearWebMorphologyResult();
    updateWebPointCloudView();
}

// ==========================================
// Web Drag & Drop Auto Scan & Archive
// ==========================================

function initDragAndDrop() {
    const dropzone = document.getElementById('web-dropzone');
    if (!dropzone) return;
    
    // Prevent defaults
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaultDragBehavior, false);
    });
    
    // Highlight dropzone
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.style.borderColor = 'var(--primary)';
            dropzone.style.background = 'rgba(58, 134, 255, 0.1)';
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.style.borderColor = 'var(--card-border)';
            dropzone.style.background = 'rgba(0,0,0,0.15)';
        }, false);
    });
    
    // Handle dropped files
    dropzone.addEventListener('drop', handleDrop, false);
}

function preventDefaultDragBehavior(e) {
    e.preventDefault();
    e.stopPropagation();
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        uploadBulkFiles(files);
    }
}

function handleBulkFilesSelected() {
    const fileInput = document.getElementById('web-bulk-file-input');
    const files = fileInput.files;
    if (files.length > 0) {
        uploadBulkFiles(files);
    }
}

async function uploadBulkFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }
    
    // Show loading state
    const dropzoneSpan = document.querySelector('#web-dropzone span');
    const originalText = dropzoneSpan.innerHTML;
    dropzoneSpan.textContent = '正在上传与自动分发归档中...';
    
    try {
        const res = await fetch('/api/archive/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) throw new Error('批量上传分发归档失败');
        
        const result = await res.json();
        const count = result.archived_count || 0;
        const details = result.details || {};
        
        if (count === 0) {
            alert('扫描上传的文件完成，未发现匹配任何已知试验 ID 的点云或图像。请确认文件名格式包含试验 ID！');
        } else {
            let detailMsg = `一键批量分发成功！共成功分发归档 ${count} 个检测文件：\n`;
            for (const [eid, fields] of Object.entries(details)) {
                detailMsg += `• 试验 [${eid}]: 归档了 ${fields.length} 个文件\n`;
            }
            alert(detailMsg);
        }
        
        // Refresh local table and preview
        await loadExperiments();
    } catch (err) {
        console.error(err);
        alert('一键批量归档出错: ' + err.message);
    } finally {
        dropzoneSpan.innerHTML = originalText;
        document.getElementById('web-bulk-file-input').value = '';
    }
}

// ==========================================
// Web 2D Image View Zoom & Pan Controls
// ==========================================

let imgZoom = 1.0;
let imgPanX = 0;
let imgPanY = 0;
let isImgDragging = false;
let startImgX = 0;
let startImgY = 0;

function initImageControls() {
    const container = document.getElementById('preview-canvas-container');
    const img = document.getElementById('image-viewer');
    if (!container || !img) return;
    
    // Mouse Scroll Wheel Zoom (Centered)
    container.addEventListener('wheel', (e) => {
        if (img.classList.contains('hidden')) return;
        e.preventDefault();
        
        const delta = e.deltaY;
        if (delta < 0) {
            imgZoom *= 1.15;
        } else {
            imgZoom /= 1.15;
        }
        
        // Limits: 0.1x to 10x
        imgZoom = Math.max(0.1, Math.min(10.0, imgZoom));
        updateImageTransform();
    }, { passive: false });
    
    // Mouse Drag Pan
    img.addEventListener('mousedown', (e) => {
        if (img.classList.contains('hidden')) return;
        isImgDragging = true;
        img.style.cursor = 'grabbing';
        startImgX = e.clientX - imgPanX;
        startImgY = e.clientY - imgPanY;
        e.preventDefault();
    });
    
    window.addEventListener('mousemove', (e) => {
        if (!isImgDragging) return;
        imgPanX = e.clientX - startImgX;
        imgPanY = e.clientY - startImgY;
        updateImageTransform();
    });
    
    window.addEventListener('mouseup', () => {
        if (isImgDragging) {
            isImgDragging = false;
            img.style.cursor = 'grab';
        }
    });
}

function updateImageTransform() {
    const img = document.getElementById('image-viewer');
    if (img) {
        img.style.transform = `translate(${imgPanX}px, ${imgPanY}px) scale(${imgZoom})`;
    }
}

function resetImageTransform() {
    imgZoom = 1.0;
    imgPanX = 0;
    imgPanY = 0;
    updateImageTransform();
    const img = document.getElementById('image-viewer');
    if (img) {
        img.style.cursor = 'grab';
    }
}
