// ---------- fondo animado: partículas tipo constelación ----------
const canvas = document.getElementById('bg');
const ctx = canvas.getContext('2d');
let particles = [];
const LINK_DIST = 130;

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

const colors = ['#c084fc', '#a855f7', '#22e598', '#38d0ff'];
const PARTICLE_COUNT = 42;
for (let i = 0; i < PARTICLE_COUNT; i++) {
  particles.push({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    r: Math.random() * 1.8 + 1,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28,
    c: colors[Math.floor(Math.random() * colors.length)],
  });
}

function animateBg() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // líneas de conexión entre partículas cercanas
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const a = particles[i], b = particles[j];
      const dx = a.x - b.x, dy = a.y - b.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < LINK_DIST) {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(168, 130, 255, ' + (0.14 * (1 - dist / LINK_DIST)) + ')';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
  }

  for (const p of particles) {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
    if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = p.c;
    ctx.globalAlpha = 0.65;
    ctx.shadowBlur = 6;
    ctx.shadowColor = p.c;
    ctx.fill();
  }
  ctx.shadowBlur = 0;
  ctx.globalAlpha = 1;
  requestAnimationFrame(animateBg);
}
animateBg();

// ---------- tira decorativa de "teclas" con brillo aleatorio ----------
const keysStrip = document.getElementById('keysStrip');
for (let i = 0; i < 28; i++) {
  const span = document.createElement('span');
  span.style.animationDelay = (Math.random() * 2.6).toFixed(2) + 's';
  span.style.animationDuration = (2 + Math.random() * 1.6).toFixed(2) + 's';
  keysStrip.appendChild(span);
}

// ---------- efecto ripple en botones ----------
function attachRipple(el) {
  el.addEventListener('click', (e) => {
    const rect = el.getBoundingClientRect();
    const ripple = document.createElement('span');
    const size = Math.max(rect.width, rect.height);
    ripple.className = 'ripple';
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
    el.appendChild(ripple);
    setTimeout(() => ripple.remove(), 500);
  });
}
document.querySelectorAll('button').forEach(attachRipple);

// ---------- elementos ----------
const startDelay = document.getElementById('startDelay');
const interval = document.getElementById('interval');
const sheetSelect = document.getElementById('sheetSelect');
const songText = document.getElementById('songText');
const refreshBtn = document.getElementById('refreshBtn');
const loadBtn = document.getElementById('loadBtn');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const progressFill = document.getElementById('progressFill');
const statusText = document.getElementById('statusText');
const nowPlaying = document.getElementById('nowPlaying');
const syncPill = document.getElementById('syncPill');
const syncDot = document.getElementById('syncDot');
const syncText = document.getElementById('syncText');
const toastStack = document.getElementById('toastStack');

// ---------- llamadas a Python ----------
function callApi(name, ...args) {
  if (window.pywebview && window.pywebview.api) {
    return window.pywebview.api[name](...args);
  }
  return Promise.resolve(null);
}

refreshBtn.addEventListener('click', () => {
  refreshBtn.querySelector('.icon').classList.add('spinning');
  setTimeout(() => refreshBtn.querySelector('.icon').classList.remove('spinning'), 500);
  callApi('list_sheets').then((files) => refreshSheets(files));
});

loadBtn.addEventListener('click', () => {
  const name = sheetSelect.value;
  if (!name) return;
  callApi('load_sheet', name).then((content) => {
    songText.value = content;
  });
});

startBtn.addEventListener('click', () => {
  callApi('start', startDelay.value, interval.value, songText.value);
});

stopBtn.addEventListener('click', () => {
  callApi('stop');
});

// ---------- funciones que Python invoca ----------
function setStatus(text) {
  statusText.textContent = text;
}

function setProgress(pct) {
  progressFill.style.width = Math.max(0, Math.min(100, pct)) + '%';
}

function setPlaying(playing) {
  startBtn.classList.toggle('active', !!playing);
  document.getElementById('eq').classList.toggle('show', !!playing);
}

function setNowPlaying(label) {
  nowPlaying.textContent = label || '';
  nowPlaying.classList.remove('show');
  void nowPlaying.offsetWidth;
  nowPlaying.classList.add('show');
}

function refreshSheets(files) {
  const prev = sheetSelect.value;
  sheetSelect.innerHTML = '';
  (files || []).forEach((f) => {
    const opt = document.createElement('option');
    opt.value = f; opt.textContent = f;
    sheetSelect.appendChild(opt);
  });
  if (files && files.includes(prev)) sheetSelect.value = prev;
}

function setSyncState(state, text) {
  syncPill.classList.remove('ok', 'err');
  if (state === 'ok') syncPill.classList.add('ok');
  if (state === 'err') syncPill.classList.add('err');
  syncText.textContent = text;
}

function toast(msg) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  toastStack.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

// ---------- carga inicial ----------
window.addEventListener('pywebviewready', () => {
  callApi('list_sheets').then((files) => refreshSheets(files));
  callApi('get_song_text').then((text) => {
    if (text) songText.value = text;
  });
});