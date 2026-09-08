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
  return new Promise((resolve) => {
    const tryCall = (attemptsLeft) => {
      const api = window.pywebview && window.pywebview.api;
      if (api && typeof api[name] === 'function') {
        api[name](...args).then(resolve).catch(() => resolve(null));
        return;
      }
      if (attemptsLeft <= 0) {
        resolve(null);
        return;
      }
      // pywebview a veces avisa que ya está listo una fracción de
      // segundo antes de terminar de registrar cada método; reintenta
      // en vez de fallar con "no es una función".
      setTimeout(() => tryCall(attemptsLeft - 1), 100);
    };
    tryCall(150); // hasta ~15s de reintentos
  });
}

// Las llamadas que hablan por internet con la tienda (login, listar,
// subir, etc.) usan este otro camino: el método de Python corre la
// parte de red en un hilo aparte y regresa de inmediato ("true"), y el
// resultado de verdad llega después por __resolveAsyncApi(). Así, si
// el servidor/túnel está lento o caído, la ventana nunca se queda
// esperando esa respuesta (que es justo lo que Windows interpreta
// como "No responde"): la interfaz sigue viva y el resultado llega en
// cuanto esté, por lento que tarde.
let _asyncReqSeq = 0;
window.__asyncApiCallbacks = {};
window.__resolveAsyncApi = function (reqId, result) {
  const cb = window.__asyncApiCallbacks[reqId];
  if (cb) {
    delete window.__asyncApiCallbacks[reqId];
    cb(result);
  }
};

function callApiAsync(name, ...args) {
  const reqId = 'r' + (++_asyncReqSeq) + '_' + Date.now();
  return new Promise((resolve) => {
    window.__asyncApiCallbacks[reqId] = resolve;
    callApi(name, reqId, ...args).then((started) => {
      if (!started) {
        // la API de Python nunca respondió que arrancó el hilo (ni
        // siquiera existe window.pywebview.api todavía): no va a
        // llegar ningún __resolveAsyncApi, así que resolvemos aquí
        // para no dejar a quien llamó esperando para siempre.
        delete window.__asyncApiCallbacks[reqId];
        resolve(null);
      }
    });
  });
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

const newSheetName = document.getElementById('newSheetName');
const saveSheetBtn = document.getElementById('saveSheetBtn');
const importBtn = document.getElementById('importBtn');

saveSheetBtn.addEventListener('click', () => {
  const name = newSheetName.value.trim();
  if (!name) {
    setStatus('Ponle un nombre a la partitura antes de guardar.');
    return;
  }
  callApi('save_sheet', name, songText.value).then((res) => {
    if (res && res.ok) {
      newSheetName.value = '';
    } else if (res && res.errors && res.errors.length) {
      setStatus('Partitura inválida: ' + res.errors.join(' '));
    }
  });
});

importBtn.addEventListener('click', () => {
  callApi('import_files');
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

// ---------- Editor de teclado (controlador) ----------
const ctrlStartDelay = document.getElementById('ctrlStartDelay');
const ctrlSheetSelect = document.getElementById('ctrlSheetSelect');
const ctrlScriptText = document.getElementById('ctrlScriptText');
const ctrlRefreshBtn = document.getElementById('ctrlRefreshBtn');
const ctrlLoadBtn = document.getElementById('ctrlLoadBtn');
const ctrlNewSheetName = document.getElementById('ctrlNewSheetName');
const ctrlSaveBtn = document.getElementById('ctrlSaveBtn');
const ctrlImportBtn = document.getElementById('ctrlImportBtn');
const ctrlValidateBtn = document.getElementById('ctrlValidateBtn');
const ctrlValidateResult = document.getElementById('ctrlValidateResult');
const ctrlStartBtn = document.getElementById('ctrlStartBtn');
const ctrlStopBtn = document.getElementById('ctrlStopBtn');
const ctrlProgressFill = document.getElementById('ctrlProgressFill');
const ctrlNow = document.getElementById('ctrlNow');
const ctrlTutorialBtn = document.getElementById('ctrlTutorialBtn');
const ctrlTutorialOverlay = document.getElementById('ctrlTutorialOverlay');
const ctrlTutorialClose = document.getElementById('ctrlTutorialClose');

function refreshControllers(files) {
  const prev = ctrlSheetSelect.value;
  ctrlSheetSelect.innerHTML = '';
  (files || []).forEach((f) => {
    const opt = document.createElement('option');
    opt.value = f; opt.textContent = f;
    ctrlSheetSelect.appendChild(opt);
  });
  if (files && files.includes(prev)) ctrlSheetSelect.value = prev;
}

function setCtrlStatus(text) { setStatus(text); }

function setCtrlProgress(pct) {
  ctrlProgressFill.style.width = Math.max(0, Math.min(100, pct)) + '%';
}

function setCtrlPlaying(playing) {
  ctrlStartBtn.classList.toggle('active', !!playing);
  document.getElementById('ctrlEq').classList.toggle('show', !!playing);
}

function setCtrlNow(label) {
  ctrlNow.textContent = label || '';
  ctrlNow.classList.remove('show');
  void ctrlNow.offsetWidth;
  ctrlNow.classList.add('show');
}

ctrlRefreshBtn.addEventListener('click', () => {
  ctrlRefreshBtn.querySelector('.icon').classList.add('spinning');
  setTimeout(() => ctrlRefreshBtn.querySelector('.icon').classList.remove('spinning'), 500);
  callApi('list_controllers').then((files) => refreshControllers(files));
});

ctrlLoadBtn.addEventListener('click', () => {
  const name = ctrlSheetSelect.value;
  if (!name) return;
  callApi('load_controller', name).then((content) => {
    ctrlScriptText.value = content;
  });
});

ctrlSaveBtn.addEventListener('click', () => {
  const name = ctrlNewSheetName.value.trim();
  if (!name) {
    setStatus('Ponle un nombre al controlador antes de guardar.');
    return;
  }
  callApi('save_controller', name, ctrlScriptText.value).then((res) => {
    if (res && res.ok) {
      ctrlNewSheetName.value = '';
    } else if (res && res.errors && res.errors.length) {
      setStatus('Controlador inválido: ' + res.errors.join(' '));
    }
  });
});

ctrlImportBtn.addEventListener('click', () => {
  callApi('import_controller_files');
});

ctrlValidateBtn.addEventListener('click', () => {
  ctrlValidateResult.textContent = 'Validando...';
  callApi('validate_controller_text', ctrlScriptText.value).then((res) => {
    if (!res) { ctrlValidateResult.textContent = ''; return; }
    if (res.ok) {
      ctrlValidateResult.textContent = `✅ Válido: ${res.steps} instrucción(es).`;
    } else {
      ctrlValidateResult.textContent = '❌ ' + (res.errors || []).join(' ');
    }
  });
});

ctrlStartBtn.addEventListener('click', () => {
  callApi('start_controller', ctrlStartDelay.value, ctrlScriptText.value);
});

ctrlStopBtn.addEventListener('click', () => {
  callApi('stop_controller');
});

ctrlTutorialBtn.addEventListener('click', () => ctrlTutorialOverlay.classList.remove('hidden'));
ctrlTutorialClose.addEventListener('click', () => ctrlTutorialOverlay.classList.add('hidden'));
ctrlTutorialOverlay.addEventListener('click', (e) => {
  if (e.target === ctrlTutorialOverlay) ctrlTutorialOverlay.classList.add('hidden');
});

// ---------- tabs ----------
const tabPiano = document.getElementById('tabPiano');
const tabEditor = document.getElementById('tabEditor');
const tabTienda = document.getElementById('tabTienda');
const tabSupervision = document.getElementById('tabSupervision');
const viewPiano = document.getElementById('viewPiano');
const viewEditor = document.getElementById('viewEditor');
const viewTienda = document.getElementById('viewTienda');
const viewSupervision = document.getElementById('viewSupervision');

function showTab(tab) {
  tabPiano.classList.toggle('active', tab === 'piano');
  tabEditor.classList.toggle('active', tab === 'editor');
  tabTienda.classList.toggle('active', tab === 'tienda');
  tabSupervision.classList.toggle('active', tab === 'supervision');
  viewPiano.classList.toggle('hidden', tab !== 'piano');
  viewEditor.classList.toggle('hidden', tab !== 'editor');
  viewTienda.classList.toggle('hidden', tab !== 'tienda');
  viewSupervision.classList.toggle('hidden', tab !== 'supervision');
  if (tab === 'editor') {
    callApi('list_controllers').then((files) => refreshControllers(files));
  } else if (tab === 'tienda') {
    if (typeof closeProfile === 'function') closeProfile();
    refreshTienda();
  } else if (tab === 'supervision') {
    refreshPending();
    refreshUsers();
  }
}
tabPiano.addEventListener('click', () => showTab('piano'));
tabEditor.addEventListener('click', () => showTab('editor'));
tabTienda.addEventListener('click', () => showTab('tienda'));
tabSupervision.addEventListener('click', () => showTab('supervision'));

// ---------- gate de login obligatorio ----------
const gateUser = document.getElementById('gateUser');
const gatePass = document.getElementById('gatePass');
const gateLoginBtn = document.getElementById('gateLoginBtn');
const gateRegisterBtn = document.getElementById('gateRegisterBtn');
const gatePickPhotoBtn = document.getElementById('gatePickPhotoBtn');
const gatePhotoName = document.getElementById('gatePhotoName');
const gateError = document.getElementById('gateError');

function showGateError(msg) {
  gateError.textContent = msg || '';
}

function unlockApp(session) {
  document.body.classList.remove('auth-checking');
  document.body.classList.remove('gate-locked');
  applySessionUI(session);
  refreshTienda();
}

function lockApp() {
  document.body.classList.remove('auth-checking');
  document.body.classList.add('gate-locked');
  gateUser.value = '';
  gatePass.value = '';
  showGateError('');
}

gatePickPhotoBtn.addEventListener('click', () => {
  callApi('tienda_pick_photo').then((filename) => {
    gatePhotoName.textContent = filename || '';
  });
});

gateRegisterBtn.addEventListener('click', () => {
  const u = gateUser.value.trim();
  const p = gatePass.value;
  if (!u || !p) { showGateError('Pon usuario y contraseña para registrarte.'); return; }
  gateRegisterBtn.disabled = true;
  callApiAsync('tienda_register', u, p).then((res) => {
    gateRegisterBtn.disabled = false;
    if (res && res.ok) {
      unlockApp(res.session);
      toast('Cuenta creada. ¡Bienvenido, ' + u + '!');
    } else {
      showGateError(res && res.error ? res.error : 'No se pudo registrar.');
    }
  });
});

gateLoginBtn.addEventListener('click', () => {
  const u = gateUser.value.trim();
  const p = gatePass.value;
  if (!u || !p) { showGateError('Pon usuario y contraseña para entrar.'); return; }
  gateLoginBtn.disabled = true;
  callApiAsync('tienda_login', u, p).then((res) => {
    gateLoginBtn.disabled = false;
    if (res && res.ok) {
      unlockApp(res.session);
      toast('Sesión iniciada como ' + u);
    } else {
      showGateError(res && res.error ? res.error : 'No se pudo iniciar sesión.');
    }
  });
});

// ---------- tienda: sesión (login / registro / logout) ----------
let tiendaSessionInfo = null; // { username, isAdmin, photo }
let myPostItem = null; // publicación propia: { id, name, status, reject_reason, photo, ... } o null

const tiendaLoggedOut = document.getElementById('tiendaLoggedOut');
const tiendaLoggedIn = document.getElementById('tiendaLoggedIn');
const tMyPhoto = document.getElementById('tMyPhoto');
const tMyUsername = document.getElementById('tMyUsername');
const tLogoutBtn = document.getElementById('tLogoutBtn');
const tRefreshBtn = document.getElementById('tRefreshBtn');
const tiendaList = document.getElementById('tiendaList');
const tiendaSearch = document.getElementById('tiendaSearch');
const feedPanel = document.getElementById('feedPanel');
const profilePanel = document.getElementById('profilePanel');
const profileBackBtn = document.getElementById('profileBackBtn');
const profileAvatar = document.getElementById('profileAvatar');
const profileUsername = document.getElementById('profileUsername');
const profileCount = document.getElementById('profileCount');
const profileSearch = document.getElementById('profileSearch');
const profileList = document.getElementById('profileList');
const myPostStatus = document.getElementById('myPostStatus');
const adminPendingPanel = document.getElementById('adminPendingPanel');
const pendingList = document.getElementById('pendingList');
const pendingRefreshBtn = document.getElementById('pendingRefreshBtn');
const newPostFab = document.getElementById('newPostFab');

function applySessionUI(session) {
  tiendaSessionInfo = session;
  const loggedIn = !!(session && session.username);
  tiendaLoggedOut.classList.toggle('hidden', loggedIn);
  tiendaLoggedIn.classList.toggle('hidden', !loggedIn);
  if (loggedIn) {
    tMyUsername.textContent = session.username + (session.isAdmin ? ' (admin)' : '');
    tMyPhoto.src = session.photo || '';
  }
  const isAdmin = !!(loggedIn && session.isAdmin);
  tabSupervision.classList.toggle('hidden', !isAdmin);
  if (isAdmin) {
    refreshPending();
    refreshUsers();
  } else if (!viewSupervision.classList.contains('hidden')) {
    // si deja de ser admin (o cierra sesión) mientras estaba viendo
    // Supervisión, lo regresamos a Piano en vez de dejarlo en un tab
    // que ya no le corresponde
    showTab('piano');
  }
  renderTiendaList(lastTiendaItems);
  refreshMyPost();
}

tLogoutBtn.addEventListener('click', () => {
  callApiAsync('tienda_logout').then(() => {
    applySessionUI(null);
    lockApp();
  });
});

// ---------- tienda: estado de mi propia publicación ----------
function refreshMyPost() {
  if (!tiendaSessionInfo) { myPostItem = null; renderMyPostStatus(); return; }
  callApiAsync('tienda_mine', currentTiendaKind).then((res) => {
    myPostItem = (res && res.ok) ? res.item : null;
    renderMyPostStatus();
  });
}

function renderMyPostStatus() {
  myPostStatus.classList.remove('pending', 'approved', 'rejected');
  myPostStatus.innerHTML = '';
  if (!tiendaSessionInfo) {
    myPostStatus.classList.add('hidden');
    newPostFab.classList.add('hidden');
    return;
  }
  if (!myPostItem) {
    myPostStatus.classList.add('hidden');
    newPostFab.classList.remove('hidden');
    return;
  }
  myPostStatus.classList.remove('hidden');

  const textEl = document.createElement('span');
  myPostStatus.appendChild(textEl);

  if (myPostItem.status === 'pending') {
    myPostStatus.classList.add('pending');
    textEl.textContent = `⏳ Tu publicación "${myPostItem.name}" está esperando la aprobación del admin.`;
    newPostFab.classList.add('hidden');
  } else if (myPostItem.status === 'approved') {
    myPostStatus.classList.add('approved');
    textEl.textContent = `✅ Tu publicación "${myPostItem.name}" ya está en la tienda.`;
    newPostFab.classList.add('hidden');
  } else if (myPostItem.status === 'rejected') {
    myPostStatus.classList.add('rejected');
    const reason = myPostItem.reject_reason ? (': ' + myPostItem.reject_reason) : '.';
    textEl.textContent = `❌ Tu publicación "${myPostItem.name}" fue rechazada${reason} Puedes intentar de nuevo.`;
    newPostFab.classList.remove('hidden');
  }

  // se puede borrar la propia publicación en cualquier estado (pendiente,
  // aprobada o rechazada), no solo el admin
  if (myPostItem.status === 'pending' || myPostItem.status === 'approved') {
    const delBtn = document.createElement('button');
    delBtn.className = 'ghost-btn danger my-post-delete-btn';
    delBtn.textContent = '🗑️ Eliminar';
    delBtn.addEventListener('click', () => {
      if (!window.confirm('¿Seguro que quieres eliminar tu publicación "' + myPostItem.name + '"?')) return;
      callApiAsync('tienda_delete', myPostItem.id).then((res) => {
        if (res && res.ok) {
          toast('Publicación eliminada.');
          refreshMyPost();
          refreshTienda();
        } else {
          setStatus(res && res.error ? res.error : 'No se pudo eliminar.');
        }
      });
    });
    myPostStatus.appendChild(delBtn);
  }
}

// ---------- tienda: apartado (Partituras / Controladores) ----------
let currentTiendaKind = 'sheet';
const tiendaKindSheetBtn = document.getElementById('tiendaKindSheetBtn');
const tiendaKindCtrlBtn = document.getElementById('tiendaKindCtrlBtn');
const feedPanelTitle = document.getElementById('feedPanelTitle');

function setTiendaKind(kind) {
  if (kind === currentTiendaKind) return;
  currentTiendaKind = kind;
  tiendaKindSheetBtn.classList.toggle('active', kind === 'sheet');
  tiendaKindCtrlBtn.classList.toggle('active', kind === 'controller');
  feedPanelTitle.textContent = kind === 'controller' ? '🛒 Tienda · Controladores' : '🛒 Tienda · Partituras';
  if (typeof closeProfile === 'function') closeProfile();
  refreshTienda();
  refreshMyPost();
}
tiendaKindSheetBtn.addEventListener('click', () => setTiendaKind('sheet'));
tiendaKindCtrlBtn.addEventListener('click', () => setTiendaKind('controller'));

// ---------- tienda: listar / descargar / borrar (feed público) ----------
let lastTiendaItems = [];

tRefreshBtn.addEventListener('click', refreshTienda);

function refreshTienda() {
  callApiAsync('tienda_list', currentTiendaKind).then((res) => {
    lastTiendaItems = (res && res.ok) ? (res.items || []) : [];
    if (!res || !res.ok) setStatus(res && res.error ? res.error : 'No se pudo cargar la tienda.');
    renderTiendaList(lastTiendaItems);
  });
}

function timeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  if (isNaN(d.getTime())) return '';
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  return `hace ${Math.floor(hrs / 24)} d`;
}

// texto usado para buscar dentro de una publicación: nombre de la
// canción/proyecto, usuario, y nombre del archivo de la foto (para que
// "buscar el nombre de la foto" también encuentre algo)
function postSearchText(item) {
  const photoName = (item.photo || '').split('/').pop() || '';
  return ((item.name || '') + ' ' + (item.username || '') + ' ' + photoName).toLowerCase();
}

function filterPosts(items, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items;
  return (items || []).filter((item) => postSearchText(item).includes(q));
}

// renderiza una cuadrícula de publicaciones (se usa tanto para la
// Tienda como para el perfil de un usuario). "onAvatarClick" recibe el
// username cuando se pica la foto de perfil de la publicación.
function renderPostGrid(container, items, { isAdmin, currentUsername, onAvatarClick, emptyText } = {}) {
  container.innerHTML = '';

  if (!items || !items.length) {
    const empty = document.createElement('div');
    empty.className = 'feed-empty';
    empty.textContent = emptyText || 'No hay publicaciones.';
    container.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'post-card';

    const header = document.createElement('div');
    header.className = 'post-header';
    const avatarBtn = document.createElement('button');
    avatarBtn.className = 'post-avatar-btn';
    avatarBtn.title = 'Ver perfil de @' + item.username;
    const avatar = document.createElement('img');
    avatar.className = 'avatar';
    avatar.src = item.user_photo || '';
    avatarBtn.appendChild(avatar);
    if (onAvatarClick) {
      avatarBtn.addEventListener('click', () => onAvatarClick(item.username));
    }
    header.appendChild(avatarBtn);
    const headInfo = document.createElement('div');
    headInfo.className = 'post-header-info';
    const userEl = document.createElement('div');
    userEl.className = 'post-username';
    userEl.textContent = '@' + item.username;
    if (onAvatarClick) {
      userEl.style.cursor = 'pointer';
      userEl.addEventListener('click', () => onAvatarClick(item.username));
    }
    const timeEl = document.createElement('div');
    timeEl.className = 'post-time';
    timeEl.textContent = timeAgo(item.created_at);
    headInfo.appendChild(userEl);
    headInfo.appendChild(timeEl);
    header.appendChild(headInfo);
    card.appendChild(header);

    const imgWrap = document.createElement('div');
    imgWrap.className = 'post-image-wrap';
    if (item.photo) {
      const img = document.createElement('img');
      img.src = item.photo;
      imgWrap.appendChild(img);
    } else {
      const noimg = document.createElement('span');
      noimg.className = 'post-noimg';
      noimg.textContent = '🎼';
      imgWrap.appendChild(noimg);
    }
    card.appendChild(imgWrap);

    const body = document.createElement('div');
    body.className = 'post-body';
    const nameEl = document.createElement('div');
    nameEl.className = 'post-name';
    nameEl.textContent = item.name;
    body.appendChild(nameEl);

    const actions = document.createElement('div');
    actions.className = 'post-actions';
    const dlBtn = document.createElement('button');
    dlBtn.className = 'accent-btn';
    dlBtn.textContent = '⬇️ Descargar';
    dlBtn.addEventListener('click', () => {
      callApiAsync('tienda_download', item.id, item.kind || 'sheet').then((res) => {
        if (res && res.ok) toast('Descargada: ' + res.name);
        else setStatus(res && res.error ? res.error : 'No se pudo descargar.');
      });
    });
    actions.appendChild(dlBtn);

    const isOwner = !!(currentUsername && item.username &&
      currentUsername.toLowerCase() === item.username.toLowerCase());
    if (isAdmin || isOwner) {
      const delBtn = document.createElement('button');
      delBtn.className = 'ghost-btn danger';
      delBtn.textContent = '🗑️';
      delBtn.addEventListener('click', () => {
        callApiAsync('tienda_delete', item.id).then((res) => {
          if (res && res.ok) {
            toast('Eliminada de la tienda.');
            refreshTienda();
            refreshMyPost();
            if (currentProfileUsername) loadProfile(currentProfileUsername);
          } else {
            setStatus(res && res.error ? res.error : 'No se pudo eliminar.');
          }
        });
      });
      actions.appendChild(delBtn);
    }
    body.appendChild(actions);
    card.appendChild(body);

    container.appendChild(card);
  });
}

function renderTiendaList(items) {
  const isAdmin = !!(tiendaSessionInfo && tiendaSessionInfo.isAdmin);
  renderPostGrid(tiendaList, filterPosts(items, tiendaSearch.value), {
    isAdmin,
    currentUsername: tiendaSessionInfo && tiendaSessionInfo.username,
    onAvatarClick: openProfile,
    emptyText: 'Todavía no hay publicaciones en la tienda.',
  });
}

tiendaSearch.addEventListener('input', () => renderTiendaList(lastTiendaItems));

// ---------- tienda: perfil de un usuario (se abre al picar su foto) ----------
let currentProfileUsername = null;
let lastProfileItems = [];

function openProfile(username) {
  if (!username) return;
  currentProfileUsername = username;
  profileSearch.value = '';
  feedPanel.classList.add('hidden');
  profilePanel.classList.remove('hidden');
  newPostFab.classList.add('hidden');
  loadProfile(username);
}

function closeProfile() {
  currentProfileUsername = null;
  profilePanel.classList.add('hidden');
  feedPanel.classList.remove('hidden');
  renderMyPostStatus();
}

profileBackBtn.addEventListener('click', closeProfile);

function loadProfile(username) {
  profileUsername.textContent = '@' + username;
  profileCount.textContent = 'Cargando...';
  callApiAsync('tienda_user_profile', username).then((res) => {
    if (!res || !res.ok) {
      profileCount.textContent = '';
      renderPostGrid(profileList, [], { emptyText: res && res.error ? res.error : 'No se pudo cargar el perfil.' });
      return;
    }
    profileAvatar.src = (res.profile && res.profile.photo) || '';
    lastProfileItems = res.items || [];
    profileCount.textContent = lastProfileItems.length + (lastProfileItems.length === 1 ? ' publicación' : ' publicaciones');
    renderProfileList(lastProfileItems);
  });
}

function renderProfileList(items) {
  const isAdmin = !!(tiendaSessionInfo && tiendaSessionInfo.isAdmin);
  renderPostGrid(profileList, filterPosts(items, profileSearch.value), {
    isAdmin,
    currentUsername: tiendaSessionInfo && tiendaSessionInfo.username,
    emptyText: 'Este usuario todavía no tiene publicaciones.',
  });
}

profileSearch.addEventListener('input', () => renderProfileList(lastProfileItems));

// ---------- tienda: panel de admin (solicitudes pendientes) ----------
const pendingSearch = document.getElementById('pendingSearch');
pendingRefreshBtn.addEventListener('click', refreshPending);
pendingSearch.addEventListener('input', () => renderPendingList(lastPendingItems));

let currentPendingKind = 'sheet';
const pendingKindSheetBtn = document.getElementById('pendingKindSheetBtn');
const pendingKindCtrlBtn = document.getElementById('pendingKindCtrlBtn');
pendingKindSheetBtn.addEventListener('click', () => {
  if (currentPendingKind === 'sheet') return;
  currentPendingKind = 'sheet';
  pendingKindSheetBtn.classList.add('active');
  pendingKindCtrlBtn.classList.remove('active');
  refreshPending();
});
pendingKindCtrlBtn.addEventListener('click', () => {
  if (currentPendingKind === 'controller') return;
  currentPendingKind = 'controller';
  pendingKindCtrlBtn.classList.add('active');
  pendingKindSheetBtn.classList.remove('active');
  refreshPending();
});

let lastPendingItems = [];

function refreshPending() {
  callApiAsync('tienda_pending', currentPendingKind).then((res) => {
    if (!res || !res.ok) {
      lastPendingItems = [];
      renderPendingList([]);
      return;
    }
    lastPendingItems = res.items || [];
    renderPendingList(lastPendingItems);
  });
}

function filterPending(items, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items || [];
  return (items || []).filter((item) =>
    (item.name || '').toLowerCase().includes(q) || (item.username || '').toLowerCase().includes(q)
  );
}

function renderPendingList(allItems) {
  const items = filterPending(allItems, pendingSearch.value);
  pendingList.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'feed-empty';
    empty.textContent = 'No hay solicitudes pendientes.';
    pendingList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const box = document.createElement('div');
    box.className = 'pending-item';

    const head = document.createElement('div');
    head.className = 'pending-item-head';
    const thumb = document.createElement('img');
    thumb.className = 'post-thumb';
    thumb.src = item.photo || item.user_photo || '';
    head.appendChild(thumb);
    const nameWrap = document.createElement('div');
    nameWrap.style.flex = '1';
    nameWrap.style.minWidth = '0';
    const nameEl = document.createElement('div');
    nameEl.className = 'pending-item-name';
    nameEl.textContent = item.name;
    const userEl = document.createElement('div');
    userEl.className = 'pending-item-user';
    userEl.textContent = '@' + item.username;
    nameWrap.appendChild(nameEl);
    nameWrap.appendChild(userEl);
    head.appendChild(nameWrap);
    box.appendChild(head);

    const contentEl = document.createElement('div');
    contentEl.className = 'pending-item-content';
    contentEl.textContent = item.content || '';
    box.appendChild(contentEl);

    const actions = document.createElement('div');
    actions.className = 'pending-item-actions';
    const okBtn = document.createElement('button');
    okBtn.className = 'approve-btn';
    okBtn.textContent = '✅ Aprobar';
    okBtn.addEventListener('click', () => {
      callApiAsync('tienda_approve', item.id).then((res) => {
        if (res && res.ok) { toast('Publicación aprobada.'); refreshPending(); refreshTienda(); }
        else setStatus(res && res.error ? res.error : 'No se pudo aprobar.');
      });
    });
    const noBtn = document.createElement('button');
    noBtn.className = 'reject-btn';
    noBtn.textContent = '❌ Rechazar';
    noBtn.addEventListener('click', () => {
      const reason = window.prompt('¿Por qué la rechazas? (opcional, se le mostrará a la persona)', '') || '';
      callApiAsync('tienda_reject', item.id, reason).then((res) => {
        if (res && res.ok) { toast('Publicación rechazada.'); refreshPending(); }
        else setStatus(res && res.error ? res.error : 'No se pudo rechazar.');
      });
    });
    actions.appendChild(okBtn);
    actions.appendChild(noBtn);
    box.appendChild(actions);

    pendingList.appendChild(box);
  });
}

// ---------- supervisión: usuarios (bloquear / desbloquear) ----------
const usersList = document.getElementById('usersList');
const usersRefreshBtn = document.getElementById('usersRefreshBtn');
const usersSearch = document.getElementById('usersSearch');
usersRefreshBtn.addEventListener('click', refreshUsers);
usersSearch.addEventListener('input', () => renderUsersList(lastUsersItems));

let lastBlockedDevices = [];
let lastUsersItems = [];

function refreshUsers() {
  callApiAsync('tienda_admin_users').then((res) => {
    if (!res || !res.ok) {
      lastUsersItems = [];
      renderUsersList([]);
      return;
    }
    lastBlockedDevices = res.blocked_devices || [];
    lastUsersItems = res.users || [];
    renderUsersList(lastUsersItems);
  });
}

function isDeviceBlocked(deviceId) {
  if (!deviceId) return false;
  return lastBlockedDevices.some((d) => d.device_id === deviceId);
}

function filterUsers(items, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items || [];
  return (items || []).filter((u) => (u.username || '').toLowerCase().includes(q));
}

function renderUsersList(allUsers) {
  const users = filterUsers(allUsers, usersSearch.value);
  usersList.innerHTML = '';
  if (!users.length) {
    const empty = document.createElement('div');
    empty.className = 'feed-empty';
    empty.textContent = 'No hay usuarios.';
    usersList.appendChild(empty);
    return;
  }

  users.forEach((u) => {
    const box = document.createElement('div');
    box.className = 'pending-item';

    const head = document.createElement('div');
    head.className = 'pending-item-head';
    const thumb = document.createElement('img');
    thumb.className = 'post-thumb';
    thumb.src = u.photo || '';
    head.appendChild(thumb);
    const nameWrap = document.createElement('div');
    nameWrap.style.flex = '1';
    nameWrap.style.minWidth = '0';
    const nameEl = document.createElement('div');
    nameEl.className = 'pending-item-name';
    nameEl.textContent = '@' + u.username + (u.isAdmin ? ' (admin)' : '');
    nameWrap.appendChild(nameEl);

    const statusEl = document.createElement('div');
    statusEl.className = 'pending-item-user';
    const accountBlocked = u.blocked_permanent || !!u.blocked_until;
    const deviceBlocked = isDeviceBlocked(u.last_device_id);
    const bits = [];
    if (u.blocked_permanent) bits.push('cuenta bloqueada permanentemente');
    else if (u.blocked_until) bits.push('cuenta bloqueada hasta ' + u.blocked_until + ' UTC');
    if (deviceBlocked) bits.push('dispositivo bloqueado');
    statusEl.textContent = bits.length ? bits.join(' · ') : 'sin bloqueos';
    nameWrap.appendChild(statusEl);
    head.appendChild(nameWrap);
    box.appendChild(head);

    if (!u.isAdmin) {
      const actions = document.createElement('div');
      actions.className = 'pending-item-actions';
      actions.style.flexWrap = 'wrap';

      function doBlock(scope, permanent) {
        let hours = null;
        if (!permanent) {
          const input = window.prompt('¿Por cuántas horas bloquear' + (scope === 'device' ? ' el dispositivo' : ' la cuenta') + '?', '24');
          if (input === null) return;
          hours = parseFloat(input);
          if (!hours || hours <= 0) { toast('Pon un número de horas válido.'); return; }
        }
        const reason = window.prompt('Motivo (opcional, se le mostrará a la persona):', '') || '';
        callApiAsync('tienda_admin_block', u.username, scope, permanent, hours, reason).then((res) => {
          if (res && res.ok) { toast('Bloqueo aplicado.'); refreshUsers(); }
          else setStatus(res && res.error ? res.error : 'No se pudo bloquear.');
        });
      }

      function doUnblock(scope) {
        callApiAsync('tienda_admin_unblock', u.username, scope).then((res) => {
          if (res && res.ok) { toast('Desbloqueado.'); refreshUsers(); }
          else setStatus(res && res.error ? res.error : 'No se pudo desbloquear.');
        });
      }

      if (accountBlocked) {
        const btn = document.createElement('button');
        btn.className = 'approve-btn';
        btn.textContent = '✅ Desbloquear cuenta';
        btn.addEventListener('click', () => doUnblock('account'));
        actions.appendChild(btn);
      } else {
        const btnTemp = document.createElement('button');
        btnTemp.className = 'reject-btn';
        btnTemp.textContent = '⏳ Bloquear cuenta (temporal)';
        btnTemp.addEventListener('click', () => doBlock('account', false));
        actions.appendChild(btnTemp);

        const btnPerm = document.createElement('button');
        btnPerm.className = 'reject-btn';
        btnPerm.textContent = '⛔ Bloquear cuenta (permanente)';
        btnPerm.addEventListener('click', () => doBlock('account', true));
        actions.appendChild(btnPerm);
      }

      if (u.last_device_id) {
        if (deviceBlocked) {
          const btn = document.createElement('button');
          btn.className = 'approve-btn';
          btn.textContent = '✅ Desbloquear dispositivo';
          btn.addEventListener('click', () => doUnblock('device'));
          actions.appendChild(btn);
        } else {
          const btnTemp = document.createElement('button');
          btnTemp.className = 'reject-btn';
          btnTemp.textContent = '⏳ Bloquear dispositivo (temporal)';
          btnTemp.addEventListener('click', () => doBlock('device', false));
          actions.appendChild(btnTemp);

          const btnPerm = document.createElement('button');
          btnPerm.className = 'reject-btn';
          btnPerm.textContent = '⛔ Bloquear dispositivo (permanente)';
          btnPerm.addEventListener('click', () => doBlock('device', true));
          actions.appendChild(btnPerm);
        }
      }

      const delUserBtn = document.createElement('button');
      delUserBtn.className = 'danger-btn';
      delUserBtn.textContent = '🗑️ Eliminar usuario';
      delUserBtn.addEventListener('click', () => {
        if (!window.confirm('¿Seguro que quieres eliminar la cuenta "' + u.username + '"? Se borra su publicación y su usuario/contraseña quedan libres para registrarse de nuevo. Esto no se puede deshacer.')) return;
        callApiAsync('tienda_admin_delete_user', u.username).then((res) => {
          if (res && res.ok) {
            toast('Usuario "' + u.username + '" eliminado.');
            refreshUsers();
            refreshTienda();
          } else {
            setStatus(res && res.error ? res.error : 'No se pudo eliminar el usuario.');
          }
        });
      });
      actions.appendChild(delUserBtn);

      box.appendChild(actions);
    }

    usersList.appendChild(box);
  });
}

// ---------- tienda: modal de nueva publicación ----------
const postModalOverlay = document.getElementById('postModalOverlay');
const postModalClose = document.getElementById('postModalClose');
const postSourceFileBtn = document.getElementById('postSourceFileBtn');
const postSourceFileName = document.getElementById('postSourceFileName');
const postNameInput = document.getElementById('postName');
const postContentText = document.getElementById('postContentText');
const postPickPhotoBtn = document.getElementById('postPickPhotoBtn');
const postPhotoName = document.getElementById('postPhotoName');
const postModalError = document.getElementById('postModalError');
const postSubmitBtn = document.getElementById('postSubmitBtn');

const postModalTitle = document.getElementById('postModalTitle');
const postContentLabel = document.getElementById('postContentLabel');
let postModalKind = 'sheet';

function openPostModal() {
  postModalKind = currentTiendaKind;
  postNameInput.value = '';
  postContentText.value = '';
  postSourceFileName.textContent = '';
  postPhotoName.textContent = '';
  postModalError.textContent = '';
  if (postModalKind === 'controller') {
    postModalTitle.textContent = '⌨️ Nuevo controlador';
    postContentLabel.textContent = 'Tu controlador';
    postContentText.placeholder = 'Escribe o pega aquí tu controlador (ver Tutorial en Editar teclado)...';
  } else {
    postModalTitle.textContent = '🎹 Nueva publicación';
    postContentLabel.textContent = 'Tu partitura';
    postContentText.placeholder = 'Escribe o pega aquí tu partitura/proyecto...';
  }
  postModalOverlay.classList.remove('hidden');
}
function closePostModal() {
  postModalOverlay.classList.add('hidden');
}

newPostFab.addEventListener('click', openPostModal);
postModalClose.addEventListener('click', closePostModal);
postModalOverlay.addEventListener('click', (e) => {
  if (e.target === postModalOverlay) closePostModal();
});

postSourceFileBtn.addEventListener('click', () => {
  callApi('tienda_pick_sheet_file').then((res) => {
    if (!res) return;
    postContentText.value = res.content || '';
    if (!postNameInput.value.trim()) postNameInput.value = res.name || '';
    postSourceFileName.textContent = res.name ? (res.name + '.txt') : '';
  });
});

postPickPhotoBtn.addEventListener('click', () => {
  callApi('tienda_pick_post_photo').then((filename) => {
    postPhotoName.textContent = filename || '';
  });
});

postSubmitBtn.addEventListener('click', () => {
  const name = postNameInput.value.trim();
  const content = postContentText.value;
  if (!name) { postModalError.textContent = 'Ponle un nombre a tu publicación.'; return; }
  if (!content.trim()) {
    postModalError.textContent = postModalKind === 'controller'
      ? 'Escribe tu controlador o elige un archivo .txt.'
      : 'Escribe tu partitura o elige un archivo .txt.';
    return;
  }
  postSubmitBtn.disabled = true;
  callApiAsync('tienda_upload', name, content, postModalKind).then((res) => {
    postSubmitBtn.disabled = false;
    if (res && res.ok) {
      closePostModal();
      refreshMyPost();
      if (res.status === 'approved') refreshTienda();
    } else {
      postModalError.textContent = res && res.error ? res.error : 'No se pudo publicar.';
    }
  });
});

// ---------- carga inicial ----------
// No confiamos solo en el evento 'pywebviewready': en algunas PCs (o
// versiones de WebView2) nunca llega, o llega antes de que este script
// termine de registrarse, y la app se queda en "Cargando..." para
// siempre. Por eso además sondeamos si window.pywebview.api ya existe,
// y si tras varios segundos no aparece, avisamos en vez de colgarnos.
let apiReady = false;

function initApp() {
  if (apiReady) return; // evita correr esto dos veces
  apiReady = true;

  callApi('list_sheets').then((files) => refreshSheets(files)).catch(() => {});
  callApi('get_song_text').then((text) => {
    if (text) songText.value = text;
  }).catch(() => {});
  callApi('tienda_session').then((cachedSession) => {
    if (!cachedSession || !cachedSession.username) {
      lockApp();
      return;
    }
    // hay una sesión guardada de una vez anterior: la mostramos de
    // inmediato para no dejar la pantalla pegada, y en paralelo se
    // revalida contra el servidor (por si el token ya no sirve, o si
    // la foto/rol de admin cambiaron desde la última vez)
    unlockApp(cachedSession);
    callApiAsync('tienda_restore_session').then((freshSession) => {
      if (freshSession && freshSession.username) {
        applySessionUI(freshSession);
      } else {
        // el token ya no era válido: hay que iniciar sesión de nuevo
        applySessionUI(null);
        lockApp();
      }
    }).catch(() => {});
  }).catch(() => {
    // si algo falla consultando la sesión, no nos quedamos pegados:
    // mostramos el login para que el usuario pueda entrar de todas formas
    lockApp();
  });
}

window.addEventListener('pywebviewready', initApp);

// respaldo: revisa cada 150ms si window.pywebview.api ya esta lista
const _apiPoll = setInterval(() => {
  if (window.pywebview && window.pywebview.api) {
    clearInterval(_apiPoll);
    initApp();
  }
}, 150);

// si tras 12s no aparecio la API de Python, algo salio mal de verdad:
// avisamos en vez de dejar "Cargando..." para siempre
setTimeout(() => {
  clearInterval(_apiPoll);
  if (!apiReady) {
    const boot = document.getElementById('bootLoading');
    boot.innerHTML =
      '<span class="brand-icon">⚠️</span>' +
      '<span>No se pudo conectar con el programa.<br>Cierra esta ventana y vuelve a abrir Piano Autoplayer.</span>';
  }
}, 12000);