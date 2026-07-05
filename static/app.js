// ===== State =====
let selectedFile = null;
let currentJobId = null;
let pollInterval = null;

const STEM_META = {
  vocals:       { emoji: '🎤', name: 'Vocal',       desc: 'Apenas a voz' },
  no_vocals:    { emoji: '🎸', name: 'Instrumental', desc: 'Música sem voz' },
  drums:        { emoji: '🥁', name: 'Bateria',      desc: 'Faixa de percussão' },
  bass:         { emoji: '🎸', name: 'Baixo',        desc: 'Faixa de baixo' },
  other:        { emoji: '🎹', name: 'Outros',       desc: 'Demais instrumentos' },
  guitar:       { emoji: '🎸', name: 'Guitarra',     desc: 'Faixa de guitarra' },
  piano:        { emoji: '🎹', name: 'Piano',        desc: 'Faixa de piano' },
};

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  setupDropzone();
  setupFileInput();
  setupRadioCards();
});

// ===== Dropzone =====
function setupDropzone() {
  const dz = document.getElementById('dropzone');
  dz.addEventListener('click', (e) => {
    if (!e.target.closest('.btn')) {
      document.getElementById('file-input').click();
    }
  });
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length) setFile(files[0]);
  });
}

function setupFileInput() {
  document.getElementById('file-input').addEventListener('change', (e) => {
    if (e.target.files.length) setFile(e.target.files[0]);
  });
}

function setupRadioCards() {
  document.querySelectorAll('.radio-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.radio-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      card.querySelector('input[type=radio]').checked = true;
    });
  });
}

// ===== File Handling =====
function setFile(file) {
  selectedFile = file;
  document.getElementById('dropzone').classList.add('hidden');
  document.getElementById('file-preview').classList.remove('hidden');
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('file-size').textContent = formatSize(file.size);
  document.getElementById('process-btn').disabled = false;
}

function clearFile() {
  selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('dropzone').classList.remove('hidden');
  document.getElementById('file-preview').classList.add('hidden');
  document.getElementById('process-btn').disabled = true;
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ===== Processing =====
async function startProcessing() {
  if (!selectedFile) return;

  const stems = document.querySelector('input[name=stems]:checked')?.value || 'vocals';
  const model = document.getElementById('model-select').value;

  showSection('progress-section');
  document.getElementById('progress-file').textContent = selectedFile.name;
  document.getElementById('progress-msg').textContent = 'Enviando arquivo...';
  setProgress(5);

  const fd = new FormData();
  fd.append('file', selectedFile);
  fd.append('stems', stems);
  fd.append('model', model);

  try {
    const res = await fetch('/api/process', { method: 'POST', body: fd });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Erro ao iniciar processamento');

    currentJobId = data.job_id;
    startPolling();
  } catch (err) {
    showError(err.message);
  }
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollStatus, 1500);
}

async function pollStatus() {
  if (!currentJobId) return;

  try {
    const res = await fetch(`/api/status/${currentJobId}`);
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Erro desconhecido');

    document.getElementById('progress-msg').textContent = data.message || '';
    setProgress(data.progress || 0);

    if (data.status === 'done') {
      clearInterval(pollInterval);
      showResults(data);
    } else if (data.status === 'error') {
      clearInterval(pollInterval);
      showError(data.error_detail || 'Ocorreu um erro durante o processamento.');
    }
  } catch (err) {
    // Silent – keep polling
  }
}

function setProgress(pct) {
  document.getElementById('progress-bar').style.width = pct + '%';
}

function cancelProcessing() {
  clearInterval(pollInterval);
  currentJobId = null;
  resetApp();
}

// ===== Results =====
function showResults(data) {
  const grid = document.getElementById('stems-grid');
  grid.innerHTML = '';

  const stems = data.stems || [];
  stems.forEach(stem => {
    const meta = STEM_META[stem] || { emoji: '🎵', name: stem, desc: 'Faixa separada' };
    const card = document.createElement('div');
    card.className = 'stem-card';
    card.innerHTML = `
      <span class="stem-emoji">${meta.emoji}</span>
      <div class="stem-info">
        <p class="stem-name">${meta.name}</p>
        <p class="stem-desc">${meta.desc}</p>
      </div>
      <a class="btn-download" href="/api/download/${currentJobId}/${stem}" download>
        ⬇️ Baixar
      </a>
    `;
    grid.appendChild(card);
  });

  document.getElementById('download-all-btn').onclick = downloadAll;
  document.getElementById('results-sub').textContent =
    `${stems.length} faixa${stems.length !== 1 ? 's' : ''} separada${stems.length !== 1 ? 's' : ''} com sucesso!`;

  showSection('results-section');
}

function downloadAll() {
  if (!currentJobId) return;
  window.location.href = `/api/download/${currentJobId}/zip`;
}

// ===== Error =====
function showError(msg) {
  document.getElementById('error-msg').textContent = msg;
  showSection('error-section');
}

// ===== Sections =====
const SECTIONS = ['upload-section', 'progress-section', 'results-section', 'error-section'];

function showSection(id) {
  SECTIONS.forEach(s => {
    document.getElementById(s).classList.toggle('hidden', s !== id);
  });
}

function resetApp() {
  clearInterval(pollInterval);
  currentJobId = null;
  selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('dropzone').classList.remove('hidden');
  document.getElementById('file-preview').classList.add('hidden');
  document.getElementById('process-btn').disabled = true;
  setProgress(0);
  showSection('upload-section');
}
