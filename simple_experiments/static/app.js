let allExperiments = [];
let analysisData = null;
let activeAnalysisMetric = 'quality_score';

document.addEventListener('DOMContentLoaded', () => {
    loadExperiments();

    // Event listeners
    document.getElementById('form-new-run').addEventListener('submit', handleNewRunSubmit);
    document.getElementById('form-supplement-quality').addEventListener('submit', handleSupplementQualitySubmit);
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

// Fetch all experiment runs
async function loadExperiments() {
    try {
        const res = await fetch('/api/experiments');
        if (!res.ok) throw new Error('Failed to load experiments');
        
        allExperiments = await res.json();
        renderTable();
        calculateStats();
    } catch (err) {
        console.error(err);
        alert('Error loading experiments: ' + err.message);
    }
}

// Render data table
function renderTable() {
    const tbody = document.getElementById('experiments-table-body');
    tbody.innerHTML = '';

    if (allExperiments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">No experiment records found. Add a new run above to get started.</td></tr>';
        return;
    }

    allExperiments.forEach(run => {
        const tr = document.createElement('tr');
        
        const isCutThrough = run.cut_through;
        const cutBadge = isCutThrough 
            ? '<span class="badge badge-success">Yes</span>' 
            : '<span class="badge badge-danger">No</span>';
            
        let failBadge = '<span class="badge badge-neutral">normal</span>';
        if (run.failure_case !== 'normal') {
            failBadge = `<span class="badge badge-warning">${run.failure_case}</span>`;
        }

        const scoreText = run.quality_score !== null 
            ? parseFloat(run.quality_score).toFixed(1) 
            : '<span class="text-muted">No data</span>';

        tr.innerHTML = `
            <td><strong>${run.episode_id}</strong></td>
            <td>${run.power_kw} kW</td>
            <td>${run.speed_m_min} m/min</td>
            <td>${run.air_pressure_mpa} MPa</td>
            <td>${run.focus_mm} mm</td>
            <td>${cutBadge}</td>
            <td>${failBadge}</td>
            <td><strong>${scoreText}</strong></td>
            <td>
                <button class="btn btn-secondary-outline btn-sm" onclick="openSupplementModal('${run.episode_id}')">
                    <i class="fa-solid fa-edit"></i> Supplement Quality
                </button>
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
        document.getElementById('stat-avg-score').textContent = 'No scores';
    }
}

// Handle adding a new run
async function handleNewRunSubmit(e) {
    e.preventDefault();

    const data = {
        power_kw: parseFloat(document.getElementById('input-power').value),
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

        if (!res.ok) throw new Error('Failed to record run');
        const result = await res.json();
        
        // Reset form (keep materials/thickness as default helper)
        document.getElementById('input-power').value = '';
        document.getElementById('input-speed').value = '';
        document.getElementById('input-pressure').value = '';
        document.getElementById('input-focus').value = '';

        // Reload data
        await loadExperiments();
        
        // Open modal for the newly created run immediately
        openSupplementModal(result.episode_id);
    } catch (err) {
        alert('Error saving run: ' + err.message);
    }
}

// Open modal to edit quality parameters
function openSupplementModal(episodeId) {
    const run = allExperiments.find(r => r.episode_id === episodeId);
    if (!run) return;

    document.getElementById('modal-episode-id').textContent = run.episode_id;
    document.getElementById('modal-hidden-episode-id').value = run.episode_id;
    document.getElementById('modal-params-summary').textContent = 
        `${run.power_kw}kW | ${run.speed_m_min}m/min | ${run.air_pressure_mpa}MPa | ${run.focus_mm}mm`;

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
        const res = await fetch(`/api/experiments/${episodeId}/quality`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!res.ok) throw new Error('Failed to update quality inspection data');
        
        closeQualityModal();
        await loadExperiments();
    } catch (err) {
        alert('Error saving inspection data: ' + err.message);
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
        if (!res.ok) throw new Error('Range analysis failed');
        
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
        alert('Error running analysis: ' + err.message);
    }
}

function renderAnalysisDetails() {
    if (!analysisData || analysisData.status !== 'success') return;

    // Render best observed trial
    const best = analysisData.best_observed;
    document.getElementById('best-observed-score').textContent = best.quality_score ? best.quality_score.toFixed(1) : '--';
    document.getElementById('best-observed-params').innerHTML = `
        <div>Episode: <strong>${best.episode_id}</strong></div>
        <div>Power: <strong>${best.power_kw} kW</strong></div>
        <div>Speed: <strong>${best.speed_m_min} m/min</strong></div>
        <div>Pressure: <strong>${best.air_pressure_mpa} MPa</strong></div>
        <div>Focus: <strong>${best.focus_mm} mm</strong></div>
    `;

    // Render rankings for active tab metric
    renderMetricAnalysis(activeAnalysisMetric);
}

function switchAnalysisMetric(metric) {
    activeAnalysisMetric = metric;
    
    // Update active tab styling
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(btn => {
        if (btn.textContent.toLowerCase().includes('score') && metric === 'quality_score' ||
            btn.textContent.toLowerCase().includes('dross') && metric === 'dross_height_max_mm' ||
            btn.textContent.toLowerCase().includes('roughness') && metric === 'roughness_Sa_um') {
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
        container.innerHTML = '<p class="text-muted">No analysis data available for this metric. Make sure inspection results are logged.</p>';
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
        if (factor === 'power_kw') labelName = 'Laser Power';
        if (factor === 'speed_m_min') labelName = 'Cutting Speed';
        if (factor === 'air_pressure_mpa') labelName = 'Assist Gas Pressure';
        if (factor === 'focus_mm') labelName = 'Focus Position';

        listHtml += `
            <div class="factor-rank-item">
                <div class="factor-name">
                    <span class="rank-badge rank-${idx+1}">${idx+1}</span>
                    <span>${labelName}</span>
                </div>
                <div class="factor-stats">
                    <span class="text-muted mr-4">Range (R) = ${range}</span>
                    <span class="factor-best-level">Best Level: ${bestLvl}</span>
                </div>
            </div>
        `;
    });
    listHtml += '</div>';

    // Append K-means table
    let tableHtml = `
        <h4 class="mt-4" style="font-size: 0.9rem; font-weight:600; margin-bottom: 0.5rem;">K-Means (Averages per Level)</h4>
        <table class="k-means-table">
            <thead>
                <tr>
                    <th>Factor</th>
                    <th>Level Means</th>
                </tr>
            </thead>
            <tbody>
    `;

    Object.entries(metricInfo.k_means).forEach(([factor, means]) => {
        let labelName = factor;
        if (factor === 'power_kw') labelName = 'Power (kW)';
        if (factor === 'speed_m_min') labelName = 'Speed (m/min)';
        if (factor === 'air_pressure_mpa') labelName = 'Pressure (MPa)';
        if (factor === 'focus_mm') labelName = 'Focus (mm)';

        const meansStr = Object.entries(means)
            .map(([lvl, val]) => `<strong>${lvl}</strong>: ${val}`)
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
