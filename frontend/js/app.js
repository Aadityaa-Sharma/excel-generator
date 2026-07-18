/**
 * DocExcel — Universal Document to Excel Converter
 * Complete frontend application logic.
 */
(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────
    const state = {
        files: [],
        jobId: null,
        pollInterval: null,
        currentTab: 0,
        tableData: [],
        validationData: [],
        hasEdits: false,
        theme: localStorage.getItem('docexcel-theme') || 'dark',
    };

    // ── DOM References ─────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const els = {
        uploadZone: $('#upload-zone'),
        fileInput: $('#file-input'),
        fileList: $('#file-list'),
        fileItems: $('#file-items'),
        passwordSection: $('#password-section'),
        pdfPassword: $('#pdf-password'),
        btnConvert: $('#btn-convert'),
        btnClearFiles: $('#btn-clear-files'),
        btnCancel: $('#btn-cancel'),
        btnDownload: $('#btn-download'),
        btnNewConversion: $('#btn-new-conversion'),
        btnSaveEdits: $('#btn-save-edits'),
        btnSettings: $('#btn-settings'),
        btnCloseSettings: $('#btn-close-settings'),
        btnCancelSettings: $('#btn-cancel-settings'),
        btnSaveSettings: $('#btn-save-settings'),
        btnTheme: $('#btn-theme'),
        sectionUpload: $('#section-upload'),
        sectionProcessing: $('#section-processing'),
        sectionResults: $('#section-results'),
        progressFill: $('#progress-fill'),
        progressText: $('#progress-text'),
        progressPercent: $('#progress-percent'),
        currentFileInfo: $('#current-file-info'),
        processingLog: $('#processing-log'),
        statsGrid: $('#stats-grid'),
        validationAlerts: $('#validation-alerts'),
        previewTabs: $('#preview-tabs'),
        previewThead: $('#preview-thead'),
        previewTbody: $('#preview-tbody'),
        modalSettings: $('#modal-settings'),
        confidenceSlider: $('#confidence-slider'),
        confidenceValue: $('#confidence-value'),
        toastContainer: $('#toast-container'),
    };

    // ── Initialize ─────────────────────────────────────────────
    function init() {
        applyTheme(state.theme);
        bindEvents();
        checkEngines();
    }

    // ── Theme ──────────────────────────────────────────────────
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        state.theme = theme;
        localStorage.setItem('docexcel-theme', theme);
    }

    function toggleTheme() {
        applyTheme(state.theme === 'dark' ? 'light' : 'dark');
    }

    // ── Event Binding ──────────────────────────────────────────
    function bindEvents() {
        // Upload zone
        els.uploadZone.addEventListener('click', () => els.fileInput.click());
        els.uploadZone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') els.fileInput.click();
        });
        els.fileInput.addEventListener('change', handleFileSelect);

        // Drag & Drop
        els.uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            els.uploadZone.classList.add('dragover');
        });
        els.uploadZone.addEventListener('dragleave', () => {
            els.uploadZone.classList.remove('dragover');
        });
        els.uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            els.uploadZone.classList.remove('dragover');
            handleDroppedFiles(e.dataTransfer.files);
        });

        // Buttons
        els.btnConvert.addEventListener('click', startConversion);
        els.btnClearFiles.addEventListener('click', clearFiles);
        els.btnCancel.addEventListener('click', cancelJob);
        els.btnDownload.addEventListener('click', downloadExcel);
        els.btnNewConversion.addEventListener('click', resetToUpload);
        els.btnSaveEdits.addEventListener('click', saveEditsAndRegenerate);
        els.btnTheme.addEventListener('click', toggleTheme);

        // Settings
        els.btnSettings.addEventListener('click', () => openSettings());
        els.btnCloseSettings.addEventListener('click', () => closeSettings());
        els.btnCancelSettings.addEventListener('click', () => closeSettings());
        els.btnSaveSettings.addEventListener('click', saveSettings);

        // Confidence slider
        els.confidenceSlider.addEventListener('input', () => {
            els.confidenceValue.textContent = Math.round(els.confidenceSlider.value * 100) + '%';
        });
    }

    // ── File Handling ──────────────────────────────────────────
    function handleFileSelect(e) {
        addFiles(Array.from(e.target.files));
        e.target.value = '';
    }

    function handleDroppedFiles(fileList) {
        addFiles(Array.from(fileList));
    }

    function addFiles(newFiles) {
        const allowedExts = new Set([
            'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'tif', 'webp',
            'heic', 'heif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
            'txt', 'rtf', 'odt', 'ods', 'xml', 'json', 'html', 'htm',
            'eml', 'msg', 'zip',
        ]);

        let hasPdf = false;

        for (const file of newFiles) {
            const ext = file.name.split('.').pop().toLowerCase();
            if (!allowedExts.has(ext)) {
                showToast(`Unsupported format: .${ext}`, 'warning');
                continue;
            }
            state.files.push(file);
            if (ext === 'pdf') hasPdf = true;
        }

        if (hasPdf) {
            els.passwordSection.style.display = 'flex';
        }

        renderFileList();
    }

    function clearFiles() {
        state.files = [];
        els.passwordSection.style.display = 'none';
        els.pdfPassword.value = '';
        renderFileList();
    }

    function removeFile(index) {
        state.files.splice(index, 1);
        if (!state.files.some(f => f.name.toLowerCase().endsWith('.pdf'))) {
            els.passwordSection.style.display = 'none';
        }
        renderFileList();
    }

    function renderFileList() {
        if (state.files.length === 0) {
            els.fileList.style.display = 'none';
            return;
        }

        els.fileList.style.display = 'block';
        els.fileItems.innerHTML = '';

        state.files.forEach((file, idx) => {
            const ext = file.name.split('.').pop().toLowerCase();
            const category = getFileCategory(ext);
            const size = formatFileSize(file.size);

            const item = document.createElement('div');
            item.className = 'file-item';
            item.style.animationDelay = `${idx * 0.05}s`;
            item.innerHTML = `
                <div class="file-item-icon ${category}">${ext.toUpperCase().slice(0, 4)}</div>
                <div class="file-item-info">
                    <div class="file-item-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
                    <div class="file-item-size">${size}</div>
                </div>
                <button class="file-item-remove" data-index="${idx}" title="Remove file" aria-label="Remove ${escapeHtml(file.name)}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
            `;
            els.fileItems.appendChild(item);
        });

        // Bind remove buttons
        $$('.file-item-remove').forEach(btn => {
            btn.addEventListener('click', () => removeFile(parseInt(btn.dataset.index)));
        });
    }

    function getFileCategory(ext) {
        if (ext === 'pdf') return 'pdf';
        if (['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'tif', 'webp', 'heic', 'heif'].includes(ext)) return 'image';
        if (['doc', 'docx'].includes(ext)) return 'word';
        if (['xls', 'xlsx', 'ods'].includes(ext)) return 'excel';
        return 'other';
    }

    // ── Conversion ─────────────────────────────────────────────
    async function startConversion() {
        if (state.files.length === 0) {
            showToast('Please select files first', 'warning');
            return;
        }

        const formData = new FormData();
        state.files.forEach(file => formData.append('files', file));

        const password = els.pdfPassword.value.trim();
        if (password) {
            formData.append('password', password);
        }

        showSection('processing');

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Upload failed');
            }

            const data = await response.json();
            state.jobId = data.job_id;

            // Show duplicate warnings
            if (data.duplicates && data.duplicates.length > 0) {
                data.duplicates.forEach(d => {
                    addLog(`⚠ Duplicate: "${d.file}" matches "${d.duplicate_of}"`, 'warning');
                });
            }

            addLog(`Processing ${data.files_accepted} file(s)...`, 'info');
            startPolling();

        } catch (error) {
            showToast(error.message, 'error');
            showSection('upload');
        }
    }

    function startPolling() {
        if (state.pollInterval) clearInterval(state.pollInterval);
        state.pollInterval = setInterval(pollJobStatus, 1000);
    }

    function stopPolling() {
        if (state.pollInterval) {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    }

    async function pollJobStatus() {
        if (!state.jobId) return;

        try {
            const response = await fetch(`/api/job/${state.jobId}`);
            if (!response.ok) throw new Error('Failed to get job status');

            const data = await response.json();
            updateProgress(data);

            if (data.status === 'completed') {
                stopPolling();
                addLog('✓ Processing complete!', 'success');
                await loadPreview();
                showResults(data);
            } else if (data.status === 'failed' || data.status === 'cancelled') {
                stopPolling();
                addLog(`✗ ${data.status}: ${data.error || 'Unknown error'}`, 'error');
                showToast(data.error || `Job ${data.status}`, 'error');
                setTimeout(() => showSection('upload'), 2000);
            }
        } catch (error) {
            console.error('Poll error:', error);
        }
    }

    function updateProgress(data) {
        const percent = data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0;
        els.progressFill.style.width = percent + '%';
        els.progressPercent.textContent = percent + '%';
        els.progressText.textContent = `File ${data.progress + 1} of ${data.total}`;
        els.currentFileInfo.textContent = data.current_file || 'Preparing...';

        // Log completed files
        if (data.results) {
            data.results.forEach(r => {
                const logId = `result-${r.filename}`;
                if (!document.getElementById(logId)) {
                    const status = r.status === 'completed' ? 'success' : (r.status === 'failed' ? 'error' : 'info');
                    const msg = r.status === 'completed'
                        ? `✓ ${r.filename}: ${r.tables} tables, ${r.rows} rows (${r.processing_time}s)`
                        : `✗ ${r.filename}: ${r.error || r.status}`;
                    addLog(msg, status, logId);
                }
            });
        }
    }

    async function cancelJob() {
        if (!state.jobId) return;
        try {
            await fetch(`/api/job/${state.jobId}/cancel`, { method: 'POST' });
            stopPolling();
            showToast('Job cancelled', 'info');
            showSection('upload');
        } catch (e) {
            console.error('Cancel error:', e);
        }
    }

    // ── Preview ────────────────────────────────────────────────
    async function loadPreview() {
        try {
            const response = await fetch(`/api/job/${state.jobId}/preview`);
            if (!response.ok) return;

            const data = await response.json();
            state.tableData = data.tables || [];
            state.validationData = data.validations || [];
        } catch (e) {
            console.error('Preview load error:', e);
        }
    }

    function showResults(jobData) {
        showSection('results');

        // Stats
        const results = jobData.results || [];
        const totalTables = results.reduce((sum, r) => sum + (r.tables || 0), 0);
        const totalRows = results.reduce((sum, r) => sum + (r.rows || 0), 0);
        const totalValidations = results.reduce((sum, r) => sum + (r.validations || 0), 0);
        const totalTime = results.reduce((sum, r) => sum + (r.processing_time || 0), 0);

        els.statsGrid.innerHTML = `
            <div class="stat-card">
                <div class="stat-label">Tables Extracted</div>
                <div class="stat-value primary">${totalTables}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Rows</div>
                <div class="stat-value success">${totalRows.toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Validation Checks</div>
                <div class="stat-value ${totalValidations > 0 ? 'warning' : 'success'}">${totalValidations}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Processing Time</div>
                <div class="stat-value primary">${totalTime.toFixed(1)}s</div>
            </div>
        `;

        // Validation alerts
        renderValidationAlerts();

        // Table tabs & preview
        renderPreviewTabs();
        if (state.tableData.length > 0) {
            renderTable(0);
        }
    }

    function renderValidationAlerts() {
        els.validationAlerts.innerHTML = '';

        if (!state.validationData || state.validationData.length === 0) {
            els.validationAlerts.innerHTML = `
                <div class="alert alert-success">
                    <span class="alert-icon">✓</span>
                    All validation checks passed. No issues detected.
                </div>
            `;
            return;
        }

        const errors = state.validationData.filter(v => v.severity === 'error');
        const warnings = state.validationData.filter(v => v.severity === 'warning');
        const infos = state.validationData.filter(v => v.severity === 'info');

        if (errors.length > 0) {
            els.validationAlerts.innerHTML += `
                <div class="alert alert-error">
                    <span class="alert-icon">✗</span>
                    <div><strong>${errors.length} error(s) found:</strong> ${errors.slice(0, 3).map(e => e.message).join('; ')}${errors.length > 3 ? '...' : ''}</div>
                </div>
            `;
        }

        if (warnings.length > 0) {
            els.validationAlerts.innerHTML += `
                <div class="alert alert-warning">
                    <span class="alert-icon">⚠</span>
                    <div><strong>${warnings.length} warning(s):</strong> ${warnings.slice(0, 3).map(w => w.message).join('; ')}${warnings.length > 3 ? '...' : ''}</div>
                </div>
            `;
        }

        if (infos.length > 0) {
            els.validationAlerts.innerHTML += `
                <div class="alert alert-info">
                    <span class="alert-icon">ℹ</span>
                    <div>${infos.length} informational note(s)</div>
                </div>
            `;
        }
    }

    function renderPreviewTabs() {
        els.previewTabs.innerHTML = '';

        state.tableData.forEach((table, idx) => {
            const tab = document.createElement('button');
            tab.className = `preview-tab${idx === 0 ? ' active' : ''}`;
            tab.textContent = table.title || `Table ${idx + 1}`;
            tab.addEventListener('click', () => {
                $$('.preview-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                state.currentTab = idx;
                renderTable(idx);
            });
            els.previewTabs.appendChild(tab);
        });
    }

    function renderTable(tableIndex) {
        const table = state.tableData[tableIndex];
        if (!table || !table.cells || table.cells.length === 0) {
            els.previewThead.innerHTML = '';
            els.previewTbody.innerHTML = '<tr><td class="empty-state" colspan="100">No data in this table</td></tr>';
            return;
        }

        const cells = table.cells;
        const validationLookup = {};
        (state.validationData || []).forEach(v => {
            if (v.row >= 0 && v.col >= 0) {
                validationLookup[`${v.row}-${v.col}`] = v;
            }
        });

        // Header
        if (cells.length > 0) {
            let headerHtml = '<tr>';
            cells[0].forEach(cell => {
                headerHtml += `<th>${escapeHtml(String(cell.value || ''))}</th>`;
            });
            headerHtml += '</tr>';
            els.previewThead.innerHTML = headerHtml;
        }

        // Body
        let bodyHtml = '';
        for (let r = 1; r < cells.length; r++) {
            bodyHtml += '<tr>';
            for (let c = 0; c < cells[r].length; c++) {
                const cell = cells[r][c];
                const value = cell.value !== null && cell.value !== undefined ? String(cell.value) : '';
                const confidence = cell.confidence || 1;
                const dataType = cell.data_type || 'text';
                const valKey = `${r}-${c}`;
                const validation = validationLookup[valKey];

                let classes = [];
                if (['number', 'currency', 'percentage'].includes(dataType)) classes.push('cell-number');
                if (dataType === 'date') classes.push('cell-date');
                if (confidence < 0.6) classes.push('cell-low-confidence');
                if (validation && !validation.is_valid) classes.push('cell-error');

                const title = confidence < 0.6
                    ? `Confidence: ${Math.round(confidence * 100)}% | Original: ${cell.raw_value || ''}`
                    : validation && !validation.is_valid
                        ? validation.message
                        : '';

                bodyHtml += `<td class="${classes.join(' ')}" data-table="${tableIndex}" data-row="${r}" data-col="${c}" ${title ? `title="${escapeHtml(title)}"` : ''} ondblclick="this.contentEditable=true;this.focus();" onblur="window.DocExcel.onCellEdit(this)">${escapeHtml(value)}</td>`;
            }
            bodyHtml += '</tr>';
        }

        els.previewTbody.innerHTML = bodyHtml || '<tr><td colspan="100" class="empty-state">No data rows</td></tr>';
    }

    function onCellEdit(td) {
        td.contentEditable = false;
        const tableIdx = parseInt(td.dataset.table);
        const row = parseInt(td.dataset.row);
        const col = parseInt(td.dataset.col);
        const newValue = td.textContent.trim();

        if (state.tableData[tableIdx] && state.tableData[tableIdx].cells[row]) {
            state.tableData[tableIdx].cells[row][col].value = newValue;
            state.tableData[tableIdx].cells[row][col].confidence = 1.0;
            state.hasEdits = true;
            els.btnSaveEdits.style.display = 'inline-flex';

            // Also send to backend
            fetch(`/api/job/${state.jobId}/edit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    table_index: tableIdx,
                    row: row,
                    col: col,
                    value: newValue,
                }),
            }).catch(console.error);
        }
    }

    // ── Download ───────────────────────────────────────────────
    async function downloadExcel() {
        if (!state.jobId) return;

        try {
            const response = await fetch(`/api/job/${state.jobId}/download`);
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Download failed');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'output.xlsx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            showToast('Excel downloaded successfully!', 'success');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function saveEditsAndRegenerate() {
        if (!state.jobId) return;

        els.btnSaveEdits.innerHTML = '<span class="spinner"></span> Regenerating...';
        els.btnSaveEdits.disabled = true;

        try {
            const response = await fetch(`/api/job/${state.jobId}/regenerate`, { method: 'POST' });
            if (!response.ok) throw new Error('Regeneration failed');

            showToast('Excel regenerated with your edits!', 'success');
            state.hasEdits = false;
            els.btnSaveEdits.style.display = 'none';
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            els.btnSaveEdits.innerHTML = 'Save & Regenerate Excel';
            els.btnSaveEdits.disabled = false;
        }
    }

    // ── Settings ───────────────────────────────────────────────
    async function openSettings() {
        els.modalSettings.style.display = 'flex';
    }

    function closeSettings() {
        els.modalSettings.style.display = 'none';
    }

    async function checkEngines() {
        try {
            const response = await fetch('/api/engines');
            if (!response.ok) return;
            const data = await response.json();
            const available = data.available || [];

            ['paddleocr', 'tesseract', 'easyocr'].forEach(engine => {
                const el = $(`#status-${engine}`);
                if (el) {
                    if (available.includes(engine)) {
                        el.textContent = 'Available';
                        el.className = 'engine-status available';
                    } else {
                        el.textContent = 'Not installed';
                        el.className = 'engine-status unavailable';
                    }
                }
            });
        } catch (e) {
            // Engines check failed, that's ok
        }
    }

    async function saveSettings() {
        const threshold = parseFloat(els.confidenceSlider.value);
        const languages = Array.from($$('#language-grid input:checked')).map(cb => cb.value);

        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    confidence_threshold: threshold,
                    languages: languages,
                }),
            });
            showToast('Settings saved', 'success');
            closeSettings();
        } catch (error) {
            showToast('Failed to save settings', 'error');
        }
    }

    // ── Navigation ─────────────────────────────────────────────
    function showSection(name) {
        els.sectionUpload.style.display = name === 'upload' ? 'block' : 'none';
        els.sectionProcessing.style.display = name === 'processing' ? 'block' : 'none';
        els.sectionResults.style.display = name === 'results' ? 'block' : 'none';
    }

    function resetToUpload() {
        stopPolling();
        state.files = [];
        state.jobId = null;
        state.tableData = [];
        state.validationData = [];
        state.hasEdits = false;
        state.currentTab = 0;
        els.fileItems.innerHTML = '';
        els.fileList.style.display = 'none';
        els.passwordSection.style.display = 'none';
        els.pdfPassword.value = '';
        els.processingLog.innerHTML = '';
        els.btnSaveEdits.style.display = 'none';
        showSection('upload');
    }

    // ── Logging ────────────────────────────────────────────────
    function addLog(message, type = 'info', id = '') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        if (id) entry.id = id;
        entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        els.processingLog.appendChild(entry);
        els.processingLog.scrollTop = els.processingLog.scrollHeight;
    }

    // ── Toast Notifications ────────────────────────────────────
    function showToast(message, type = 'info', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${escapeHtml(message)}</span>
            <button class="toast-close" aria-label="Dismiss">×</button>
        `;
        toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
        els.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // ── Utilities ──────────────────────────────────────────────
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Public API (for inline event handlers) ─────────────────
    window.DocExcel = { onCellEdit };

    // ── Boot ───────────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
