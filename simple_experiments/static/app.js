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
