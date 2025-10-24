// API Base URL
const API_BASE = '';

// State
let currentPage = 1;
const pageSize = 20;
let totalIndicators = 0;
let currentFilters = {
    search: '',
    type: '',
    risk: ''
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeUpload();
    loadStats();
    loadIndicators();
    
    // Auto-refresh every 30 seconds
    setInterval(() => {
        loadStats();
    }, 30000);

    // Initialize file input accept types
    document.getElementById('fileInput').accept = '.csv,.json';
});

// === Upload Functionality ===

function initializeUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const chooseFileButton = document.getElementById('chooseFileButton');
    
    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            handleFileUpload(file);
        }
    });
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            handleFileUpload(file);
        }
    });
    
    // Choose file button (prevent double-trigger from bubbling)
    if (chooseFileButton) {
        chooseFileButton.addEventListener('click', (event) => {
            event.stopPropagation();
            fileInput.click();
        });
    }
    
    // Click to upload
    uploadArea.addEventListener('click', () => {
        fileInput.click();
    });
}

// Tab switching functionality
function switchTab(tab) {
    const bulkTab = document.getElementById('bulkTab');
    const singleTab = document.getElementById('singleTab');
    const bulkSection = document.getElementById('bulkUploadSection');
    const singleSection = document.getElementById('singleUploadSection');
    
    if (tab === 'bulk') {
        bulkTab.classList.add('active');
        singleTab.classList.remove('active');
        bulkSection.style.display = 'block';
        singleSection.style.display = 'none';
    } else {
        bulkTab.classList.remove('active');
        singleTab.classList.add('active');
        bulkSection.style.display = 'none';
        singleSection.style.display = 'block';
    }
}

async function handleFileUpload(file) {
    const fileName = file.name.toLowerCase();

    if (!fileName.endsWith('.csv') && !fileName.endsWith('.json')) {
        showUploadResult('Please select a CSV or JSON file', 'error');
        return;
    }
    
    const enrich = document.getElementById('enrichCheckbox').checked;
    const classify = document.getElementById('classifyCheckbox').checked;
    
    const formData = new FormData();
    formData.append('file', file);
    
    const progressDiv = document.getElementById('uploadProgress');
    const resultDiv = document.getElementById('uploadResult');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    progressDiv.classList.remove('hidden');
    resultDiv.classList.add('hidden');
    progressFill.style.width = '0%';
    
    try {
        progressFill.style.width = '30%';
        progressText.textContent = 'Uploading file...';
        
        // Choose endpoint based on file type
        const endpoint = fileName.endsWith('.csv') ? 'upload-csv' : 'upload-json';
        const response = await fetch(`${API_BASE}/api/ingest/${endpoint}?enrich=${enrich}&classify=${classify}`, {
            method: 'POST',
            body: formData
        });
        
        progressFill.style.width = '70%';
        progressText.textContent = 'Processing indicators...';
        
        const data = await response.json();
        
        progressFill.style.width = '100%';
        progressText.textContent = 'Complete!';
        
        if (response.ok && data.success) {
            const message = `✅ Success! Processed ${data.indicators_processed} indicators: ${data.indicators_created} created, ${data.indicators_updated} updated, ${data.indicators_failed} failed`;
            showUploadResult(message, 'success');
            
            // Refresh data
            setTimeout(() => {
                loadStats();
                loadIndicators();
            }, 2000);
        } else {
            showUploadResult(`❌ Error: ${data.detail || 'Upload failed'}`, 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showUploadResult(`❌ Error: ${error.message}`, 'error');
    } finally {
        setTimeout(() => {
            progressDiv.classList.add('hidden');
        }, 2000);
        // Clear file input so selecting the same file again triggers change
        try { document.getElementById('fileInput').value = ''; } catch (e) { /* ignore */ }
    }
}

// Submit single indicator
async function submitSingleIndicator() {
    const value = document.getElementById('indicatorValue').value.trim();
    if (!value) {
        showUploadResult('Please enter an indicator value', 'error');
        return;
    }
    
    const indicator = {
        value: value,
        indicator_type: document.getElementById('indicatorType').value,
        source: document.getElementById('sourceName').value.trim() || 'manual',
        source_url: document.getElementById('sourceUrl').value.trim(),
        tags: document.getElementById('tags').value.trim().split(',').map(t => t.trim()).filter(t => t),
        notes: document.getElementById('notes').value.trim()
    };
    
    const enrich = document.getElementById('singleEnrichCheckbox').checked;
    const classify = document.getElementById('singleClassifyCheckbox').checked;
    
    const progressDiv = document.getElementById('uploadProgress');
    const resultDiv = document.getElementById('uploadResult');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    progressDiv.classList.remove('hidden');
    resultDiv.classList.add('hidden');
    progressFill.style.width = '0%';
    
    try {
        progressFill.style.width = '30%';
        progressText.textContent = 'Submitting indicator...';
        
        const response = await fetch(`${API_BASE}/api/ingest/submit?enrich=${enrich}&classify=${classify}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(indicator)
        });
        
        const data = await response.json();
        
        progressFill.style.width = '100%';
        progressText.textContent = 'Complete!';
        
        if (response.ok) {
            showUploadResult('✅ Indicator submitted successfully', 'success');
            
            // Clear form
            document.getElementById('indicatorValue').value = '';
            document.getElementById('indicatorType').value = 'auto';
            document.getElementById('sourceName').value = '';
            document.getElementById('sourceUrl').value = '';
            document.getElementById('tags').value = '';
            document.getElementById('notes').value = '';
            
            // Refresh data
            setTimeout(() => {
                loadStats();
                loadIndicators();
            }, 2000);
        } else {
            showUploadResult(`❌ Error: ${data.detail || 'Submission failed'}`, 'error');
        }
    } catch (error) {
        console.error('Submit error:', error);
        showUploadResult(`❌ Error: ${error.message}`, 'error');
    } finally {
        setTimeout(() => {
            progressDiv.classList.add('hidden');
        }, 2000);
    }
}

function showUploadResult(message, type) {
    const resultDiv = document.getElementById('uploadResult');
    resultDiv.textContent = message;
    resultDiv.className = `upload-result ${type}`;
    resultDiv.classList.remove('hidden');
}

// === Stats Loading ===

async function loadStats() {
    try {
        // Load ingestion stats
        const ingestResponse = await fetch(`${API_BASE}/api/ingest/stats`);
        const ingestData = await ingestResponse.json();
        
        document.getElementById('totalIndicators').textContent = ingestData.total_indicators || 0;
        
        // Load classification stats
        const classifyResponse = await fetch(`${API_BASE}/api/classify/stats`);
        const classifyData = await classifyResponse.json();
        
        document.getElementById('highRisk').textContent = classifyData.by_risk_level.high || 0;
        document.getElementById('mediumRisk').textContent = classifyData.by_risk_level.medium || 0;
        document.getElementById('lowRisk').textContent = classifyData.by_risk_level.low || 0;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// === Indicators Loading ===

async function loadIndicators() {
    const tbody = document.getElementById('indicatorsTableBody');
    tbody.innerHTML = '<tr><td colspan="8" class="loading-cell"><div class="loading">Loading indicators...</div></td></tr>';
    
    try {
        const offset = (currentPage - 1) * pageSize;
        let url = `${API_BASE}/api/indicators?limit=${pageSize}&offset=${offset}`;
        
        if (currentFilters.search) {
            url += `&search=${encodeURIComponent(currentFilters.search)}`;
        }
        if (currentFilters.type) {
            url += `&indicator_type=${currentFilters.type}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        totalIndicators = data.total;
        displayIndicators(data.indicators);
        updatePagination();
        
        document.getElementById('tableCount').textContent = `${data.total} indicator${data.total !== 1 ? 's' : ''}`;
    } catch (error) {
        console.error('Error loading indicators:', error);
        tbody.innerHTML = '<tr><td colspan="8" class="loading-cell">Error loading indicators</td></tr>';
    }
}

function displayIndicators(indicators) {
    const tbody = document.getElementById('indicatorsTableBody');
    
    if (indicators.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="loading-cell">No indicators found</td></tr>';
        return;
    }
    
    tbody.innerHTML = indicators.map(indicator => {
        const classification = indicator.classification;
        const riskBadge = classification 
            ? `<span class="badge badge-${classification.risk_level}">${classification.risk_level}</span>`
            : '<span class="badge badge-unknown">unclassified</span>';
        
        const score = classification 
            ? `${classification.risk_score.toFixed(1)}/10`
            : '-';
        
        const enrichmentCount = indicator.enrichments?.length || 0;
        
        const createdDate = new Date(indicator.created_at).toLocaleDateString();
        
        return `
            <tr>
                <td><span class="badge badge-${indicator.indicator_type}">${indicator.indicator_type}</span></td>
                <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(indicator.value)}</td>
                <td>${riskBadge}</td>
                <td>${score}</td>
                <td>
                    ${enrichmentCount}
                    ${indicator.enrichments && indicator.enrichments.length > 0 
                        ? `<span class="enrichment-status ${indicator.enrichments.some(e => !e.success) ? 'enrichment-failed' : ''}" 
                            title="${indicator.enrichments.map(e => `${e.provider}: ${e.success ? 'Success' : 'Failed - ' + e.error_message}`).join('\n')}">
                            ${indicator.enrichments.some(e => !e.success) ? '⚠️' : '✓'}
                           </span>`
                        : ''}
                </td>
                <td>${escapeHtml(indicator.source_name || '-')}</td>
                <td>${createdDate}</td>
                <td>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <button class="btn btn-sm btn-success" onclick="submitFeedback(${indicator.id}, 'correct')" id="row-feedback-correct-${indicator.id}" title="Thumbs up">
                            👍
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="toggleCorrectionForm(${indicator.id}, true)" id="row-feedback-incorrect-${indicator.id}" title="Thumbs down">
                            👎
                        </button>
                                <div id="row-correction-form-${indicator.id}" class="row-correction-form hidden" style="display:none; margin-left:8px;">
                                    <select id="corrected-risk-row-${indicator.id}" style="margin-bottom:4px;">
                                        <option value="">-- corrected risk --</option>
                                        <option value="high">High</option>
                                        <option value="medium">Medium</option>
                                        <option value="low">Low</option>
                                    </select>
                                    <input id="feedback-comment-row-${indicator.id}" placeholder="Optional comment" style="width:180px; margin-right:6px;" />
                                    <button class="btn btn-sm btn-danger" onclick="submitFeedback(${indicator.id}, 'incorrect')">Submit</button>
                                    <button class="btn btn-sm" onclick="toggleCorrectionForm(${indicator.id}, true)" style="margin-left:6px;">Cancel</button>
                                </div>
                        <button class="btn btn-sm btn-primary" onclick="viewDetails(${indicator.id})">View</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    // After rendering, fetch feedback status for each indicator to mark rows with existing feedback
    indicators.forEach(ind => {
        (async function(id) {
            try {
                const resp = await fetch(`${API_BASE}/api/feedback/indicator/${id}`);
                if (!resp.ok) return;
                const fb = await resp.json();
                if (fb && fb.has_feedback) {
                    markRowFeedback(id, fb);
                }
            } catch (e) {
                // ignore network errors for per-row marking
            }
        })(ind.id);
    });
}

function markRowFeedback(indicatorId, feedback) {
    // Disable row-level buttons and show a small badge with feedback summary
    const rowCorrect = document.getElementById(`row-feedback-correct-${indicatorId}`);
    const rowIncorrect = document.getElementById(`row-feedback-incorrect-${indicatorId}`);

    if (rowCorrect) rowCorrect.disabled = true;
    if (rowIncorrect) rowIncorrect.disabled = true;

    // Create or update a small inline element showing stored feedback
    const existing = document.getElementById(`row-feedback-summary-${indicatorId}`);
    const container = rowCorrect ? rowCorrect.parentNode : (rowIncorrect ? rowIncorrect.parentNode : null);
    if (!container) return;

    const summaryText = (() => {
        if (!feedback || !feedback.has_feedback) return 'Feedback submitted';
        const type = feedback.feedback_type || '';
        const corrected = feedback.corrected_risk_level || null;
        if (type === 'true_positive' || type === 'true_negative') return 'Marked correct';
        if (type === 'false_positive') return corrected ? `Corrected → ${corrected}` : 'False positive';
        if (type === 'false_negative') return corrected ? `Corrected → ${corrected}` : 'False negative';
        return 'Feedback recorded';
    })();

    if (existing) {
        existing.textContent = summaryText;
    } else {
        const span = document.createElement('span');
        span.id = `row-feedback-summary-${indicatorId}`;
        span.style.marginLeft = '8px';
        span.style.fontSize = '0.95em';
        span.style.color = '#0f172a';
        span.textContent = summaryText;
        container.appendChild(span);
    }
}

// === Filters ===

function applyFilters() {
    currentFilters.search = document.getElementById('searchInput').value;
    currentFilters.type = document.getElementById('typeFilter').value;
    currentFilters.risk = document.getElementById('riskFilter').value;
    
    currentPage = 1;
    loadIndicators();
}

// === Pagination ===

function updatePagination() {
    const totalPages = Math.ceil(totalIndicators / pageSize);
    document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages}`;
    
    document.getElementById('prevBtn').disabled = currentPage === 1;
    document.getElementById('nextBtn').disabled = currentPage >= totalPages;
}

function previousPage() {
    if (currentPage > 1) {
        currentPage--;
        loadIndicators();
    }
}

function nextPage() {
    const totalPages = Math.ceil(totalIndicators / pageSize);
    if (currentPage < totalPages) {
        currentPage++;
        loadIndicators();
    }
}

// === View Details Modal ===

async function viewDetails(indicatorId) {
    const modal = document.getElementById('detailModal');
    const modalBody = document.getElementById('modalBody');
    
    modalBody.innerHTML = '<div class="loading">Loading details...</div>';
    modal.classList.remove('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/api/indicators/${indicatorId}`);
        const indicator = await response.json();
        
        modalBody.innerHTML = generateDetailsHTML(indicator);
    } catch (error) {
        console.error('Error loading details:', error);
        modalBody.innerHTML = '<div class="text-center text-muted">Error loading details</div>';
    }
}

function generateDetailsHTML(indicator) {
    let html = `
        <div class="detail-section">
            <h3>Basic Information</h3>
            <div class="detail-grid">
                <div class="detail-item">
                    <div class="detail-label">Type</div>
                    <div class="detail-value"><span class="badge badge-${indicator.indicator_type}">${indicator.indicator_type}</span></div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Value</div>
                    <div class="detail-value">${escapeHtml(indicator.value)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Source</div>
                    <div class="detail-value">${escapeHtml(indicator.source_name || '-')}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Created</div>
                    <div class="detail-value">${new Date(indicator.created_at).toLocaleString()}</div>
                </div>
            </div>
        </div>
    `;
    
    // Classification
    if (indicator.classification) {
        const c = indicator.classification;
        html += `
            <div class="detail-section">
                <h3>🎯 AI Classification</h3>
                <div class="classification-box">
                    <div class="classification-score">${c.risk_score.toFixed(1)} / 10.0</div>
                    <div style="font-size: 1.2em; margin-bottom: 10px;">
                        <span class="badge badge-${c.risk_level}">${c.risk_level.toUpperCase()} RISK</span>
                    </div>
                    <div style="margin-top: 10px; opacity: 0.9;">
                        Confidence: ${(c.confidence * 100).toFixed(0)}%
                    </div>
                </div>
                <div class="feedback-section" style="margin-top: 20px; text-align: center;">
                    <p style="margin-bottom: 10px; color: #666;">Was this classification accurate?</p>
                    <div class="feedback-buttons">
                        <button class="btn btn-success" onclick="submitFeedback(${indicator.id}, 'correct')" id="feedback-correct-${indicator.id}">
                            👍 Correct
                        </button>
                        <button class="btn btn-danger" onclick="submitFeedback(${indicator.id}, 'incorrect')" id="feedback-incorrect-${indicator.id}">
                                👎 Incorrect
                        </button>
                    </div>
                    <div id="feedback-result-${indicator.id}" style="margin-top: 10px;"></div>
                        <div id="correction-form-${indicator.id}" class="correction-form hidden" style="margin-top: 12px; text-align: left; display: inline-block;">
                            <div style="margin-bottom: 8px;">
                                <label for="corrected-risk-${indicator.id}" style="font-size: 0.9em; color:#444;">If incorrect, what should the risk be?</label>
                                <select id="corrected-risk-${indicator.id}" class="form-control" style="margin-top:4px;">
                                    <option value="">-- select corrected risk --</option>
                                    <option value="high">High</option>
                                    <option value="medium">Medium</option>
                                    <option value="low">Low</option>
                                </select>
                            </div>
                            <div style="margin-bottom: 8px;">
                                <label for="feedback-comment-${indicator.id}" style="font-size: 0.9em; color:#444;">Optional comment</label>
                                <textarea id="feedback-comment-${indicator.id}" rows="2" style="width: 300px; margin-top:4px;" placeholder="Why is this incorrect?"></textarea>
                            </div>
                            <div style="text-align: right;">
                                <button class="btn btn-sm btn-danger" onclick="submitFeedback(${indicator.id}, 'incorrect')">Submit Correction</button>
                                <button class="btn btn-sm" onclick="toggleCorrectionForm(${indicator.id})" style="margin-left:6px;">Cancel</button>
                            </div>
                        </div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="detail-section">
                <div class="text-center">
                    <p class="text-muted">Not yet classified</p>
                    <button class="btn btn-primary" onclick="classifyIndicator(${indicator.id})">
                        Classify Now
                    </button>
                </div>
            </div>
        `;
    }
    
    // Enrichments
    if (indicator.enrichments && indicator.enrichments.length > 0) {
        html += `
            <div class="detail-section">
                <h3>📊 Enrichment Data (${indicator.enrichments.length})</h3>
        `;
        
        indicator.enrichments.forEach(e => {
            html += `
                <div class="enrichment-card">
                    <div class="enrichment-header">
                        <strong>${e.enrichment_type}</strong>
                        <span class="badge ${e.success ? 'badge-low' : 'badge-high'}">
                            ${e.success ? 'Success' : 'Failed'}
                        </span>
                    </div>
                    <div>Provider: ${e.provider}</div>
                    ${e.score !== null ? `<div>Score: ${e.score.toFixed(1)}/10</div>` : ''}
                    <div style="margin-top: 10px; font-size: 0.85em; color: #666;">
                        ${new Date(e.enriched_at).toLocaleString()}
                    </div>
                </div>
            `;
        });
        
        html += `</div>`;
    }
    
    return html;
}

async function classifyIndicator(indicatorId) {
    try {
        const response = await fetch(`${API_BASE}/api/classify/${indicatorId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            // Reload details
            viewDetails(indicatorId);
            loadStats();
        } else {
            alert('Classification failed');
        }
    } catch (error) {
        console.error('Error classifying:', error);
        alert('Error classifying indicator');
    }
}

function closeModal() {
    document.getElementById('detailModal').classList.add('hidden');
}

// Close modal on background click
document.getElementById('detailModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeModal();
    }
});

// === Utility Functions ===

function refreshData() {
    loadStats();
    loadIndicators();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function toggleCorrectionForm(indicatorId, isRow = false) {
    if (isRow) {
        const form = document.getElementById(`row-correction-form-${indicatorId}`);
        if (!form) return;
        if (form.classList.contains('hidden') || getComputedStyle(form).display === 'none') {
            form.classList.remove('hidden');
            form.style.display = 'inline-block';
        } else {
            form.classList.add('hidden');
            form.style.display = 'none';
        }
        return;
    }

    const form = document.getElementById(`correction-form-${indicatorId}`);
    if (!form) return;
    if (form.classList.contains('hidden') || getComputedStyle(form).display === 'none') {
        form.classList.remove('hidden');
        form.style.display = 'inline-block';
    } else {
        form.classList.add('hidden');
        form.style.display = 'none';
    }
}

// === Feedback Functions ===

async function submitFeedback(indicatorId, feedbackType) {
    // Locate modal or row buttons
    const modalCorrect = document.getElementById(`feedback-correct-${indicatorId}`);
    const modalIncorrect = document.getElementById(`feedback-incorrect-${indicatorId}`);
    const rowCorrect = document.getElementById(`row-feedback-correct-${indicatorId}`);
    const rowIncorrect = document.getElementById(`row-feedback-incorrect-${indicatorId}`);
    const correctBtn = modalCorrect || rowCorrect;
    const incorrectBtn = modalIncorrect || rowIncorrect;

    // Find or create a result display element (modal has feedback-result-<id>, rows will get row-feedback-result-<id>)
    let resultDiv = document.getElementById(`feedback-result-${indicatorId}`) || document.getElementById(`row-feedback-result-${indicatorId}`);
    if (!resultDiv) {
        const anchor = rowCorrect || rowIncorrect;
        if (anchor && anchor.parentNode) {
            resultDiv = document.createElement('span');
            resultDiv.id = `row-feedback-result-${indicatorId}`;
            resultDiv.style.marginLeft = '8px';
            resultDiv.style.fontSize = '0.95em';
            anchor.parentNode.insertBefore(resultDiv, anchor.nextSibling);
        }
    }

    // Disable buttons to prevent duplicate submissions
    if (correctBtn) correctBtn.disabled = true;
    if (incorrectBtn) incorrectBtn.disabled = true;

    // Read row-level correction inputs first (if the user used the inline row form)
    let correctedRisk = null;
    let feedbackComment = null;
    try {
        const rowCorrectedEl = document.getElementById(`corrected-risk-row-${indicatorId}`);
        const rowCommentEl = document.getElementById(`feedback-comment-row-${indicatorId}`);
        if (rowCorrectedEl && rowCorrectedEl.value) correctedRisk = rowCorrectedEl.value;
        if (rowCommentEl && rowCommentEl.value) feedbackComment = rowCommentEl.value;

        // If no row inputs, fall back to modal inputs
        if (!correctedRisk) {
            const correctedEl = document.getElementById(`corrected-risk-${indicatorId}`);
            if (correctedEl && correctedEl.value) correctedRisk = correctedEl.value;
        }
        if (!feedbackComment) {
            const commentEl = document.getElementById(`feedback-comment-${indicatorId}`);
            if (commentEl && commentEl.value) feedbackComment = commentEl.value;
        }
    } catch (e) {
        // ignore DOM read errors
    }

    try {
        const response = await fetch(`${API_BASE}/api/feedback/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ indicator_id: indicatorId, feedback_type: feedbackType, corrected_risk_level: correctedRisk, comment: feedbackComment })
        });

        const data = await response.json();

        if (response.ok) {
            if (resultDiv) {
                resultDiv.innerHTML = '<span style="color: #10b981;">✓ Thank you</span>';
            } else {
                alert('Thank you for your feedback');
            }
            loadStats();
            // Refresh per-row feedback state
            try {
                const fbResp = await fetch(`${API_BASE}/api/feedback/indicator/${indicatorId}`);
                if (fbResp.ok) {
                    const fbData = await fbResp.json();
                    markRowFeedback(indicatorId, fbData);
                }
            } catch (e) {
                // ignore
            }
        } else {
            const msg = data.detail || 'Failed to submit feedback';
            if (resultDiv) {
                resultDiv.innerHTML = `<span style="color: #ef4444;">✗ ${msg}</span>`;
            } else {
                alert(msg);
            }
            if (correctBtn) correctBtn.disabled = false;
            if (incorrectBtn) incorrectBtn.disabled = false;
        }
    } catch (error) {
        console.error('Error submitting feedback:', error);
        if (resultDiv) {
            resultDiv.innerHTML = '<span style="color: #ef4444;">✗ Error submitting feedback</span>';
        } else {
            alert('Error submitting feedback');
        }
        if (correctBtn) correctBtn.disabled = false;
        if (incorrectBtn) incorrectBtn.disabled = false;
    }
}
