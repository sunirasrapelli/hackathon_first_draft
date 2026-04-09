/**
 * FinAnalyse AI — Frontend Logic
 * Handles: file selection, form validation, job submission,
 *          progress polling, download link activation, floating chatbot.
 */

/* ── State ─────────────────────────────────────────────────────── */
let selectedFiles  = [];
let pollTimer      = null;
let currentJobId   = null;
let chatHistory    = [];   // [{role: "user"|"assistant", content: string}]
let chatBusy       = false;
let chatPanelOpen  = false;

/* ── DOM refs ──────────────────────────────────────────────────── */
const dropZone       = document.getElementById('drop-zone');
const fileInput      = document.getElementById('file-input');
const fileListEl     = document.getElementById('file-list');
const fileCountHint  = document.getElementById('file-count-hint');
const companyInput   = document.getElementById('company-input');
const yearsInput     = document.getElementById('years-input');
const currencySelect = document.getElementById('currency-select');
const unitSelect     = document.getElementById('unit-select');
const analyzeBtn     = document.getElementById('analyze-btn');
const errorBanner    = document.getElementById('error-banner');

const uploadCard       = document.getElementById('upload-card');
const progressPanel    = document.getElementById('progress-panel');
const resultsPanel     = document.getElementById('results-panel');
const mainSpinner      = document.getElementById('main-spinner');
const progressHeadline = document.getElementById('progress-headline');
const dlReport         = document.getElementById('dl-report');
const resultsSub       = document.getElementById('results-sub');
const newAnalysisBtn   = document.getElementById('new-analysis-btn');

// Floating chat widget
const chatWidget      = document.getElementById('chat-widget');
const chatFab         = document.getElementById('chat-fab');
const chatUnread      = document.getElementById('chat-unread');
const chatPanel       = document.getElementById('chat-panel');
const chatPanelClose  = document.getElementById('chat-panel-close');
const chatPanelSub    = document.getElementById('chat-panel-sub');
const chatMessagesEl  = document.getElementById('chat-messages');
const chatInput       = document.getElementById('chat-input');
const chatSendBtn     = document.getElementById('chat-send');

/* ── Markdown renderer ─────────────────────────────────────────── */
/**
 * Convert a subset of Markdown to safe HTML.
 * Order matters: escape HTML first, then apply patterns.
 */
function renderMarkdown(text) {
  // 1. Escape HTML to prevent XSS
  let s = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  // 2. Inline code  (`code`)  — before bold/italic so asterisks inside aren't touched
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // 3. Bold  (**text**)
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // 4. Italic  (*text*)  — single asterisk, not adjacent to another asterisk
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  // 5. Bullet lists: lines starting with "• " or "- " or "* "
  //    Wrap consecutive bullet lines in <ul>
  s = s.replace(/((?:^|\n)[•\-\*] .+)+/g, match => {
    const items = match.trim().split(/\n/).map(line =>
      `<li>${line.replace(/^[•\-\*] /, '')}</li>`
    ).join('');
    return `<ul>${items}</ul>`;
  });

  // 6. Convert remaining newlines to <br>
  s = s.replace(/\n/g, '<br>');

  return s;
}

/* ── File helpers ──────────────────────────────────────────────── */
function formatBytes(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function addFiles(fileList) {
  let added = 0;
  for (const file of fileList) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['json', 'pdf'].includes(ext)) {
      showError(`'${file.name}' is not supported. Only .json and .pdf files are allowed.`);
      continue;
    }
    if (!selectedFiles.find(f => f.name === file.name && f.size === file.size)) {
      selectedFiles.push(file);
      added++;
    }
  }
  if (added > 0) hideError();
  renderFileList();
  validateForm();
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  renderFileList();
  validateForm();
}

function renderFileList() {
  fileListEl.innerHTML = selectedFiles.map((file, i) => {
    const ext  = file.name.split('.').pop().toLowerCase();
    const icon = ext === 'pdf' ? '📕' : '📋';
    return `
      <div class="file-badge">
        <span class="file-icon">${icon}</span>
        <div class="file-info">
          <div class="file-name">${escapeHtml(file.name)}</div>
          <div class="file-size">${formatBytes(file.size)}</div>
        </div>
        <button class="file-clear" onclick="removeFile(${i})" title="Remove">✕</button>
      </div>
    `;
  }).join('');

  if (selectedFiles.length === 0) {
    fileCountHint.style.display = 'none';
  } else {
    fileCountHint.style.display = 'block';
    if (selectedFiles.length < 3) {
      fileCountHint.className = 'file-count-hint warn';
      fileCountHint.textContent = `${selectedFiles.length} file(s) selected — upload at least 3 for full trend analysis`;
    } else {
      fileCountHint.className = 'file-count-hint';
      fileCountHint.textContent = `${selectedFiles.length} file(s) ready`;
    }
  }
}

/* ── Drag & Drop ───────────────────────────────────────────────── */
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) addFiles(fileInput.files);
  fileInput.value = '';
});

/* ── Form validation ───────────────────────────────────────────── */
function validateForm() {
  const hasFiles   = selectedFiles.length > 0;
  const hasPdf     = selectedFiles.some(f => f.name.endsWith('.pdf'));
  const hasCompany = companyInput.value.trim().length > 0;
  analyzeBtn.disabled = !hasFiles || (hasPdf && !hasCompany);
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
  if (selectedFiles.length === 0) return;
  hideError();

  const fd = new FormData();
  selectedFiles.forEach(f => fd.append('files', f));
  fd.append('company',  companyInput.value.trim());
  fd.append('years',    yearsInput.value.trim());
  fd.append('currency', currencySelect.value);
  fd.append('unit',     unitSelect.value);

  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = '<span class="spinner" style="width:16px;height:16px;display:inline-block;border:2px solid rgba(0,0,0,.2);border-top-color:#000;border-radius:50%;animation:spin .7s linear infinite"></span> Submitting…';

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
  uploadCard.style.display = 'none';
  progressPanel.classList.add('show');
  resultsPanel.classList.remove('show');
  hideChatWidget();
}

function switchToResults(jobId, data) {
  progressPanel.classList.remove('show');
  resultsPanel.classList.add('show');
  mainSpinner.style.display = 'none';

  dlReport.href = `/download/${jobId}/report`;
  resultsSub.textContent = 'Analysis complete — click below to download';

  // Render next steps
  const nextSteps = (data && data.next_steps) || [];
  const listEl    = document.getElementById('next-steps-list');
  const section   = document.getElementById('next-steps-section');
  if (nextSteps.length > 0 && listEl && section) {
    listEl.innerHTML = nextSteps.map(s => `
      <div class="next-step-row">
        <span class="priority-badge priority-${escapeHtml(s.priority || 'medium')}">${escapeHtml((s.priority || 'medium').toUpperCase())}</span>
        <div class="next-step-body">
          <strong>${escapeHtml(s.title || '')}</strong>
          <span>${escapeHtml(s.description || '')}</span>
        </div>
      </div>
    `).join('');
    section.style.display = 'block';
  }

  // Init chatbot for this analysis
  const companyName = data.company_name || 'this company';
  chatHistory = [];
  chatMessagesEl.innerHTML = '';
  if (chatPanelSub) chatPanelSub.textContent = companyName;
  appendChatMessage('ai',
    `Hi! I've analysed the report for **${companyName}**. Ask me anything about the financials, trends, risks, or next steps.`
  );

  showChatWidget();
  // Show unread dot since the widget is collapsed
  chatUnread.classList.add('show');
}

function switchToUpload() {
  resultsPanel.classList.remove('show');
  progressPanel.classList.remove('show');
  uploadCard.style.display = '';

  const errBlock = document.getElementById('progress-error-block');
  if (errBlock) errBlock.remove();

  selectedFiles  = [];
  chatHistory    = [];
  currentJobId   = null;
  fileInput.value = '';
  renderFileList();
  companyInput.value = '';
  yearsInput.value   = '';
  resetSteps();
  resetBtn();

  const section = document.getElementById('next-steps-section');
  if (section) section.style.display = 'none';
  const listEl = document.getElementById('next-steps-list');
  if (listEl) listEl.innerHTML = '';

  hideChatWidget();
}

/* ── Step UI helpers ───────────────────────────────────────────── */
const STEPS = ['extract', 'commentary', 'report', 'next_steps'];

function resetSteps() {
  STEPS.forEach(s => {
    document.getElementById(`ind-${s}`).className = 'step-indicator pending';
    document.getElementById(`msg-${s}`).textContent = 'Waiting…';
  });
  progressHeadline.textContent = 'Initialising pipeline…';
}

function applyProgress(progress) {
  progress.forEach(p => {
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
      switchToResults(jobId, data);
    } else if (data.status === 'error') {
      clearInterval(pollTimer);
      progressHeadline.textContent = 'Analysis failed';
      mainSpinner.style.display = 'none';
      if (data.progress && data.progress.length > 0) {
        const last = data.progress[data.progress.length - 1];
        const ind  = document.getElementById(`ind-${last.step}`);
        if (ind) { ind.className = 'step-indicator error-ind'; ind.textContent = '✕'; }
      }
      showProgressError(data.error || 'Unknown error. Please try again.');
    }
  } catch (e) {
    console.warn('Poll error:', e);
  }
}

/* ── Inline error in progress panel ────────────────────────────── */
function showProgressError(msg) {
  const existing = document.getElementById('progress-error-block');
  if (existing) existing.remove();

  const block = document.createElement('div');
  block.id = 'progress-error-block';
  block.style.cssText = `
    margin-top: 20px;
    background: rgba(248,113,113,0.08);
    border: 1px solid rgba(248,113,113,0.3);
    border-radius: 8px;
    padding: 14px 16px;
    color: #F87171;
    font-size: .88rem;
  `;
  block.innerHTML = `
    <div style="font-weight:700;margin-bottom:6px;">⚠ Error</div>
    <div style="margin-bottom:14px;word-break:break-word;">${escapeHtml(msg)}</div>
    <button onclick="switchToUpload()" style="
      background: none;
      border: 1px solid rgba(248,113,113,0.5);
      border-radius: 6px;
      color: #F87171;
      padding: 8px 16px;
      font-size: .85rem;
      cursor: pointer;
    ">← Try Again</button>
  `;
  progressPanel.appendChild(block);
}

/* ── Floating chat widget ──────────────────────────────────────── */
function showChatWidget() {
  chatWidget.style.display = 'block';
}

function hideChatWidget() {
  chatWidget.style.display = 'none';
  closeChatPanel();
}

function openChatPanel() {
  chatPanel.classList.add('open');
  chatPanelOpen = true;
  chatUnread.classList.remove('show');
  chatFab.style.display = 'none';
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  chatInput.focus();
}

function closeChatPanel() {
  chatPanel.classList.remove('open');
  chatPanelOpen = false;
  chatFab.style.display = 'flex';
}

chatFab.addEventListener('click', openChatPanel);
chatPanelClose.addEventListener('click', closeChatPanel);

/* ── Chatbot messages ──────────────────────────────────────────── */
function appendChatMessage(role, text) {
  const isUser = role === 'user';
  const div    = document.createElement('div');
  div.className = `chat-msg ${isUser ? 'user' : 'ai'}`;

  const bubbleContent = isUser ? escapeHtml(text) : renderMarkdown(text);
  div.innerHTML = `
    <div class="chat-avatar">${isUser ? 'You' : 'AI'}</div>
    <div class="chat-bubble">${bubbleContent}</div>
  `;
  chatMessagesEl.appendChild(div);
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  return div;
}

function showTypingIndicator() {
  const div = document.createElement('div');
  div.className = 'chat-msg ai';
  div.id = 'chat-typing';
  div.innerHTML = `
    <div class="chat-avatar">AI</div>
    <div class="chat-bubble" style="padding:10px 14px;">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
  `;
  chatMessagesEl.appendChild(div);
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById('chat-typing');
  if (el) el.remove();
}

async function sendChatMessage() {
  const text = chatInput.value.trim();
  if (!text || chatBusy || !currentJobId) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';
  chatBusy = true;
  chatSendBtn.disabled = true;
  chatInput.disabled   = true;

  appendChatMessage('user', text);
  chatHistory.push({ role: 'user', content: text });
  showTypingIndicator();

  try {
    const res = await fetch(`/chat/${currentJobId}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        message: text,
        history: chatHistory.slice(0, -1),  // history before this message
      }),
    });
    const data = await res.json();
    removeTypingIndicator();

    if (!res.ok) {
      appendChatMessage('ai', `⚠ ${escapeHtml(data.detail || 'Failed to get a response.')}`);
    } else {
      const reply = data.reply || '';
      appendChatMessage('ai', reply);
      chatHistory.push({ role: 'assistant', content: reply });
    }
  } catch (err) {
    removeTypingIndicator();
    appendChatMessage('ai', `⚠ Network error: ${escapeHtml(err.message)}`);
  } finally {
    chatBusy = false;
    chatSendBtn.disabled = false;
    chatInput.disabled   = false;
    chatInput.focus();
    // Show unread dot if panel is closed
    if (!chatPanelOpen) chatUnread.classList.add('show');
  }
}

chatSendBtn.addEventListener('click', sendChatMessage);

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
});

// Auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 96) + 'px';
});

/* ── New analysis ──────────────────────────────────────────────── */
newAnalysisBtn.addEventListener('click', switchToUpload);

/* ── Utility ───────────────────────────────────────────────────── */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
