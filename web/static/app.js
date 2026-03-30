/**
 * FinAnalyse AI — Frontend Logic
 * Handles: file selection, form validation, job submission,
 *          progress polling, download link activation.
 */

/* ── State ─────────────────────────────────────────────────────── */
let selectedFile = null;
let pollTimer    = null;
let currentJobId = null;

/* ── DOM refs ──────────────────────────────────────────────────── */
const dropZone       = document.getElementById('drop-zone');
const fileInput      = document.getElementById('file-input');
const fileSelected   = document.getElementById('file-selected');
const fileNameLabel  = document.getElementById('file-name-label');
const fileSizeLabel  = document.getElementById('file-size-label');
const fileTypeIcon   = document.getElementById('file-type-icon');
const fileClearBtn   = document.getElementById('file-clear-btn');
const companyInput   = document.getElementById('company-input');
const yearsInput     = document.getElementById('years-input');
const currencySelect = document.getElementById('currency-select');
const unitSelect     = document.getElementById('unit-select');
const analyzeBtn     = document.getElementById('analyze-btn');
const errorBanner    = document.getElementById('error-banner');

const uploadCard     = document.getElementById('upload-card');
const progressPanel  = document.getElementById('progress-panel');
const resultsPanel   = document.getElementById('results-panel');

const mainSpinner    = document.getElementById('main-spinner');
const progressHeadline = document.getElementById('progress-headline');
const dlExcel        = document.getElementById('dl-excel');
const dlReport       = document.getElementById('dl-report');
const resultsSub     = document.getElementById('results-sub');
const newAnalysisBtn = document.getElementById('new-analysis-btn');

/* ── File helpers ──────────────────────────────────────────────── */
function formatBytes(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function setFile(file) {
  if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['json', 'pdf'].includes(ext)) {
    showError('Only .json and .pdf files are supported.');
    return;
  }
  selectedFile = file;
  fileNameLabel.textContent = file.name;
  fileSizeLabel.textContent = formatBytes(file.size);
  fileTypeIcon.textContent  = ext === 'pdf' ? '📕' : '📋';
  fileSelected.classList.add('show');
  hideError();
  validateForm();
}

function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  fileSelected.classList.remove('show');
  validateForm();
}

/* ── Drag & Drop ───────────────────────────────────────────────── */
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});
fileClearBtn.addEventListener('click', clearFile);

/* ── Form validation ───────────────────────────────────────────── */
function validateForm() {
  const hasFile    = !!selectedFile;
  const isPdf      = hasFile && selectedFile.name.endsWith('.pdf');
  const hasCompany = companyInput.value.trim().length > 0;
  analyzeBtn.disabled = !hasFile || (isPdf && !hasCompany);
}

companyInput.addEventListener('input', validateForm);

/* ── Error helpers ─────────────────────────────────────────────── */
function showError(msg) {
  errorBanner.textContent = '⚠ ' + msg;
  errorBanner.classList.add('show');
}
function hideError() {
  errorBanner.classList.remove('show');
}

/* ── Submit ────────────────────────────────────────────────────── */
analyzeBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  hideError();

  const fd = new FormData();
  fd.append('file',     selectedFile);
  fd.append('company',  companyInput.value.trim());
  fd.append('years',    yearsInput.value.trim());
  fd.append('currency', currencySelect.value);
  fd.append('unit',     unitSelect.value);

  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = '<span class="spinner" style="width:16px;height:16px;display:inline-block;border:2px solid rgba(13,27,42,.3);border-top-color:#0D1B2A;border-radius:50%;animation:spin .7s linear infinite"></span> Submitting…';

  try {
    const res  = await fetch('/analyze', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) { showError(data.detail || 'Server error'); resetBtn(); return; }
    currentJobId = data.job_id;
    switchToProgress();
    startPolling(data.job_id);
  } catch (err) {
    showError('Network error: ' + err.message);
    resetBtn();
  }
});

function resetBtn() {
  analyzeBtn.disabled = false;
  analyzeBtn.innerHTML = '<span>⚡</span> Run Financial Analysis';
}

/* ── Panel switching ───────────────────────────────────────────── */
function switchToProgress() {
  uploadCard.style.display    = 'none';
  progressPanel.classList.add('show');
  resultsPanel.classList.remove('show');
}

function switchToResults(jobId) {
  progressPanel.classList.remove('show');
  resultsPanel.classList.add('show');
  mainSpinner.style.display = 'none';

  dlExcel.href  = `/download/${jobId}/excel`;
  dlReport.href = `/download/${jobId}/report`;
  resultsSub.textContent = 'Analysis complete — click below to download';
}

function switchToUpload() {
  resultsPanel.classList.remove('show');
  progressPanel.classList.remove('show');
  uploadCard.style.display = '';
  // Clean up inline error block if present
  const errBlock = document.getElementById('progress-error-block');
  if (errBlock) errBlock.remove();
  clearFile();
  companyInput.value = '';
  yearsInput.value   = '';
  resetSteps();
  resetBtn();
}

/* ── Step UI helpers ───────────────────────────────────────────── */
const STEPS = ['extract', 'excel', 'verify', 'report'];

function resetSteps() {
  STEPS.forEach(s => {
    document.getElementById(`ind-${s}`).className = 'step-indicator pending';
    document.getElementById(`msg-${s}`).textContent = 'Waiting…';
  });
  progressHeadline.textContent = 'Initialising pipeline…';
}

function applyProgress(progress) {
  // progress = [{step, message, done}]
  const seen = new Set();
  progress.forEach(p => {
    seen.add(p.step);
    const ind = document.getElementById(`ind-${p.step}`);
    const msg = document.getElementById(`msg-${p.step}`);
    if (!ind) return;
    msg.textContent = p.message;
    if (p.done) {
      ind.className = 'step-indicator done';
      ind.textContent = '✓';
    } else {
      ind.className = 'step-indicator active';
    }
  });
  // Set headline to last active step message
  if (progress.length > 0) {
    progressHeadline.textContent = progress[progress.length - 1].message;
  }
}

/* ── Polling ───────────────────────────────────────────────────── */
function startPolling(jobId) {
  pollTimer = setInterval(() => pollStatus(jobId), 1500);
}

async function pollStatus(jobId) {
  try {
    const res  = await fetch(`/status/${jobId}`);
    const data = await res.json();

    applyProgress(data.progress || []);

    if (data.status === 'done') {
      clearInterval(pollTimer);
      switchToResults(jobId);
    } else if (data.status === 'error') {
      clearInterval(pollTimer);
      progressHeadline.textContent = 'Analysis failed';
      mainSpinner.style.display = 'none';
      // Mark the last active step as failed
      if (data.progress && data.progress.length > 0) {
        const last = data.progress[data.progress.length - 1];
        const ind  = document.getElementById(`ind-${last.step}`);
        if (ind) { ind.className = 'step-indicator error-ind'; ind.textContent = '✕'; }
      }
      // Show inline error message + retry button — no confirm() dialog
      showProgressError(data.error || 'Unknown error. Please try again.');
    }
  } catch (e) {
    console.warn('Poll error:', e);
  }
}

/* ── Inline error in progress panel ────────────────────────────── */
function showProgressError(msg) {
  // Remove any existing error block first
  const existing = document.getElementById('progress-error-block');
  if (existing) existing.remove();

  const block = document.createElement('div');
  block.id = 'progress-error-block';
  block.style.cssText = `
    margin-top: 20px;
    background: rgba(231,76,60,.1);
    border: 1px solid rgba(231,76,60,.4);
    border-radius: 8px;
    padding: 14px 16px;
    color: #F1948A;
    font-size: .88rem;
  `;
  block.innerHTML = `
    <div style="font-weight:700;margin-bottom:6px;">⚠ Error</div>
    <div style="margin-bottom:14px;word-break:break-word;">${escapeHtml(msg)}</div>
    <button onclick="switchToUpload()" style="
      background: none;
      border: 1px solid rgba(231,76,60,.5);
      border-radius: 6px;
      color: #F1948A;
      padding: 8px 16px;
      font-size: .85rem;
      cursor: pointer;
    ">← Try Again</button>
  `;
  progressPanel.appendChild(block);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── New analysis ──────────────────────────────────────────────── */
newAnalysisBtn.addEventListener('click', switchToUpload);
