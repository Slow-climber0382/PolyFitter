import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { TransformControls } from './vendor/TransformControls.js';

const canvas = document.getElementById('viewport');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x14171f, 1);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, 1, 1, 5000);
camera.position.set(320, 230, 390);

const orbit = new OrbitControls(camera, canvas);
orbit.target.set(0, 120, 0);
orbit.enableDamping = true;
orbit.dampingFactor = 0.08;
orbit.update();

const gizmo = new TransformControls(camera, canvas);
gizmo.setSize(0.85);
const gizmoHelper = typeof gizmo.getHelper === 'function' ? gizmo.getHelper() : gizmo;
scene.add(gizmoHelper);

gizmo.addEventListener('dragging-changed', (ev) => {
  orbit.enabled = !ev.value;
  if (!ev.value && currentPart()) {
    syncSelectedFromMesh(true);
  }
});

gizmo.addEventListener('objectChange', () => {
  if (currentPart()) {
    syncSelectedFromMesh(false);
  }
});

// Oświetlenie studyjne
scene.add(new THREE.HemisphereLight(0xdce8ff, 0x262c3a, 1.15));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.35);
keyLight.position.set(260, 420, 340);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x77e9ca, 0.55);
rimLight.position.set(-280, 180, -260);
scene.add(rimLight);

// Siatka stołu (podziałka 10 mm / 50 mm) i osie Y-up
const grid = new THREE.GridHelper(500, 50, 0x3b465b, 0x232936);
scene.add(grid);
scene.add(new THREE.AxesHelper(90));

let headMeshObj = null;
const partMeshes = new Map();
let appState = null;
let lockProportions = true;
let transformSyncTimer = null;

function decodeBinaryGeometry(arrayBuffer) {
  const triCount = new Uint32Array(arrayBuffer, 0, 1)[0];
  const floatCount = triCount * 9;
  const posBytes = floatCount * 4;
  const positions = new Float32Array(arrayBuffer, 4, floatCount);
  const normals = new Float32Array(arrayBuffer, 4 + posBytes, floatCount);
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geom.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  geom.computeBoundingSphere();
  return geom;
}

async function rebuildHeadMesh() {
  const res = await fetch('/api/head/geometry');
  const buf = await res.arrayBuffer();
  const geom = decodeBinaryGeometry(buf);
  if (headMeshObj) {
    headMeshObj.geometry.dispose();
    headMeshObj.geometry = geom;
  } else {
    const mat = new THREE.MeshStandardMaterial({
      color: 0xd8c3b2,
      roughness: 0.58,
      metalness: 0.04,
      transparent: true,
      opacity: appState?.head?.opacity ?? 0.92,
    });
    headMeshObj = new THREE.Mesh(geom, mat);
    scene.add(headMeshObj);
  }
  if (appState?.head) {
    headMeshObj.visible = appState.head.visible;
    headMeshObj.material.opacity = appState.head.opacity;
  }
}

async function ensurePartMesh(part) {
  let obj = partMeshes.get(part.part_id);
  if (!obj) {
    const res = await fetch(`/api/parts/${part.part_id}/geometry`);
    const buf = await res.arrayBuffer();
    const geom = decodeBinaryGeometry(buf);
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(part.color || '#79c7ff'),
      roughness: 0.42,
      metalness: 0.14,
      transparent: true,
      opacity: part.opacity,
      side: THREE.DoubleSide,
      depthWrite: part.opacity >= 0.98,
    });
    obj = new THREE.Mesh(geom, mat);
    scene.add(obj);
    partMeshes.set(part.part_id, obj);
  }
  applyPartPropsToThree(part, obj);
  return obj;
}

function applyPartPropsToThree(part, obj) {
  obj.visible = part.visible;
  obj.material.opacity = part.opacity;
  obj.material.depthWrite = part.opacity >= 0.98;
  obj.position.set(...part.transform.position);
  obj.rotation.order = 'XYZ';
  obj.rotation.set(
    THREE.MathUtils.degToRad(part.transform.rotation[0]),
    THREE.MathUtils.degToRad(part.transform.rotation[1]),
    THREE.MathUtils.degToRad(part.transform.rotation[2]),
  );
  obj.scale.set(...part.transform.scale);
}

function currentPart() {
  if (!appState || !appState.selected_part_id) return null;
  return appState.parts.find((p) => p.part_id === appState.selected_part_id) || null;
}

function setStatus(msg) {
  document.getElementById('importReport').textContent = msg;
}

function renderClearance(clr) {
  const pill = document.getElementById('clearanceStatusPill');
  const mMin = document.getElementById('mMin');
  const mCol = document.getElementById('mCol');
  const mCran = document.getElementById('mCranium');
  const mLow = document.getElementById('mLower');

  if (!clr) {
    pill.textContent = 'Nie sprawdzono';
    pill.className = 'pill';
    mMin.textContent = '—';
    mCol.textContent = '—';
    mCran.textContent = '—';
    mLow.textContent = '—';
    return;
  }

  mMin.textContent = `${clr.min_clearance_mm.toFixed(2)} mm`;
  mCol.textContent = `${clr.intersecting_triangles}`;
  if (clr.intersecting_triangles > 0 || clr.min_clearance_mm < 0) {
    pill.textContent = 'KOLIZJA';
    pill.className = 'pill fail';
  } else if (clr.min_clearance_mm < 2.0) {
    pill.textContent = 'CIASNO (<2 mm)';
    pill.className = 'pill warn';
  } else {
    pill.textContent = 'BEZ KOLIZJI';
    pill.className = 'pill pass';
  }

  const reg = clr.regional;
  if (reg && reg.cranium && reg.cranium.min_clearance_mm != null) {
    mCran.textContent = `${reg.cranium.min_clearance_mm.toFixed(1)}..${reg.cranium.max_clearance_mm.toFixed(1)} mm`;
  } else {
    mCran.textContent = `śr. ${clr.mean_clearance_mm.toFixed(1)} mm`;
  }
  if (reg && reg.lower && reg.lower.min_clearance_mm != null) {
    mLow.textContent = `${reg.lower.min_clearance_mm.toFixed(1)}..${reg.lower.max_clearance_mm.toFixed(1)} mm`;
  } else {
    mLow.textContent = `max ${clr.max_clearance_mm.toFixed(1)} mm`;
  }
}

async function renderState(newState, reloadHead = false) {
  appState = newState;
  document.getElementById('projectTitle').textContent = `${appState.project_name} (mm, Y-up)`;
  document.getElementById('undo').disabled = !appState.can_undo;
  document.getElementById('redo').disabled = !appState.can_redo;
  document.getElementById('partCount').textContent = String(appState.parts.length);

  const m = appState.head.measurements;
  document.getElementById('editMeasurementsBtn').textContent =
    `Wymiary głowy (${Math.round(m.circumference_mm)} mm)…`;
  document.getElementById('headVisibleChk').checked = appState.head.visible;
  document.getElementById('headOpacityRange').value = Math.round(appState.head.opacity * 100);

  if (reloadHead || !headMeshObj) {
    await rebuildHeadMesh();
  } else {
    headMeshObj.visible = appState.head.visible;
    headMeshObj.material.opacity = appState.head.opacity;
  }

  // Usuń z Three.js siatki, których nie ma już w stanie
  const activeIds = new Set(appState.parts.map((p) => p.part_id));
  for (const [pid, obj] of partMeshes.entries()) {
    if (!activeIds.has(pid)) {
      gizmo.detach();
      scene.remove(obj);
      obj.geometry.dispose();
      partMeshes.delete(pid);
    }
  }

  const listEl = document.getElementById('partsList');
  listEl.innerHTML = '';

  for (const part of appState.parts) {
    await ensurePartMesh(part);
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'part-btn' + (part.part_id === appState.selected_part_id ? ' selected' : '');
    btn.innerHTML = `<span class="part-name">${part.name}</span><span class="part-meta">${part.triangles.toLocaleString('pl-PL')} tris • ${part.scaled_size_mm.join('×')} mm</span>`;
    btn.onclick = async () => {
      const r = await fetch(`/api/parts/${part.part_id}/select`, { method: 'POST' });
      await renderState(await r.json());
    };

    const vis = document.createElement('button');
    vis.className = 'vis-btn';
    vis.textContent = part.visible ? '👁' : '🚫';
    vis.title = 'Pokaż / ukryj element';
    vis.onclick = async () => {
      const r = await fetch(`/api/parts/${part.part_id}/transform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visible: !part.visible }),
      });
      const data = await r.json();
      await renderState(data.state);
    };

    li.append(btn, vis);
    listEl.appendChild(li);
  }

  const sel = currentPart();
  const hasSel = Boolean(sel);
  document.getElementById('exportStlBtn').disabled = !hasSel;
  document.getElementById('removePartBtn').disabled = !hasSel;
  document.getElementById('autoFitBtn').disabled = !hasSel;
  document.getElementById('checkClearanceBtn').disabled = !hasSel;
  document.getElementById('selectedBadge').textContent = sel ? sel.name : 'Brak';

  const controlIds = [
    'scaleXRange', 'scaleXNum', 'scaleYRange', 'scaleYNum', 'scaleZRange', 'scaleZNum',
    'posXRange', 'posXNum', 'posYRange', 'posYNum', 'posZRange', 'posZNum',
    'rotXRange', 'rotXNum', 'rotYRange', 'rotYNum', 'rotZRange', 'rotZNum',
    'rotMinus90X', 'rotPlus90X', 'rot180Y', 'centerOnHeadBtn', 'partOpacityRange',
  ];
  for (const id of controlIds) {
    document.getElementById(id).disabled = !hasSel;
  }

  if (sel) {
    const obj = partMeshes.get(sel.part_id);
    if (obj && sel.visible) gizmo.attach(obj);
    else gizmo.detach();

    const [sx, sy, sz] = sel.transform.scale.map((v) => +(v * 100).toFixed(2));
    setPair('scaleX', sx);
    setPair('scaleY', sy);
    setPair('scaleZ', sz);

    const [px, py, pz] = sel.transform.position;
    setPair('posX', px);
    setPair('posY', py);
    setPair('posZ', pz);

    const [rx, ry, rz] = sel.transform.rotation;
    setPair('rotX', rx);
    setPair('rotY', ry);
    setPair('rotZ', rz);

    document.getElementById('dimX').textContent = `${sel.scaled_size_mm[0]} mm`;
    document.getElementById('dimY').textContent = `${sel.scaled_size_mm[1]} mm`;
    document.getElementById('dimZ').textContent = `${sel.scaled_size_mm[2]} mm`;

    const opPct = Math.round(sel.opacity * 100);
    document.getElementById('partOpacityRange').value = opPct;
    document.getElementById('partOpacityVal').textContent = `${opPct}%`;
    renderClearance(sel.last_clearance);
  } else {
    gizmo.detach();
    document.getElementById('dimX').textContent = '—';
    document.getElementById('dimY').textContent = '—';
    document.getElementById('dimZ').textContent = '—';
    renderClearance(null);
  }
}

function setPair(prefix, val) {
  document.getElementById(`${prefix}Range`).value = val;
  document.getElementById(`${prefix}Num`).value = val;
}

function pushTransformToServer(recordUndo = false) {
  const sel = currentPart();
  if (!sel) return;
  const payload = {
    record_undo: recordUndo,
    scale: [
      parseFloat(document.getElementById('scaleXNum').value) / 100.0,
      parseFloat(document.getElementById('scaleYNum').value) / 100.0,
      parseFloat(document.getElementById('scaleZNum').value) / 100.0,
    ],
    position: [
      parseFloat(document.getElementById('posXNum').value),
      parseFloat(document.getElementById('posYNum').value),
      parseFloat(document.getElementById('posZNum').value),
    ],
    rotation: [
      parseFloat(document.getElementById('rotXNum').value),
      parseFloat(document.getElementById('rotYNum').value),
      parseFloat(document.getElementById('rotZNum').value),
    ],
  };

  // Natychmiastowa aktualizacja w Three.js bez czekania na HTTP
  const obj = partMeshes.get(sel.part_id);
  if (obj) {
    sel.transform.scale = payload.scale;
    sel.transform.position = payload.position;
    sel.transform.rotation = payload.rotation;
    applyPartPropsToThree(sel, obj);
    document.getElementById('dimX').textContent = `${(sel.raw_size_mm[0] * payload.scale[0]).toFixed(1)} mm`;
    document.getElementById('dimY').textContent = `${(sel.raw_size_mm[1] * payload.scale[1]).toFixed(1)} mm`;
    document.getElementById('dimZ').textContent = `${(sel.raw_size_mm[2] * payload.scale[2]).toFixed(1)} mm`;
  }

  clearTimeout(transformSyncTimer);
  transformSyncTimer = setTimeout(async () => {
    const r = await fetch(`/api/parts/${sel.part_id}/transform`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      const data = await r.json();
      appState = data.state;
      renderClearance(null);
    }
  }, 60);
}

function syncSelectedFromMesh(commitToServer) {
  const sel = currentPart();
  if (!sel) return;
  const obj = partMeshes.get(sel.part_id);
  if (!obj) return;
  setPair('posX', +obj.position.x.toFixed(1));
  setPair('posY', +obj.position.y.toFixed(1));
  setPair('posZ', +obj.position.z.toFixed(1));
  setPair('rotX', +THREE.MathUtils.radToDeg(obj.rotation.x).toFixed(1));
  setPair('rotY', +THREE.MathUtils.radToDeg(obj.rotation.y).toFixed(1));
  setPair('rotZ', +THREE.MathUtils.radToDeg(obj.rotation.z).toFixed(1));
  setPair('scaleX', +(obj.scale.x * 100).toFixed(2));
  setPair('scaleY', +(obj.scale.y * 100).toFixed(2));
  setPair('scaleZ', +(obj.scale.z * 100).toFixed(2));
  document.getElementById('dimX').textContent = `${(sel.raw_size_mm[0] * obj.scale.x).toFixed(1)} mm`;
  document.getElementById('dimY').textContent = `${(sel.raw_size_mm[1] * obj.scale.y).toFixed(1)} mm`;
  document.getElementById('dimZ').textContent = `${(sel.raw_size_mm[2] * obj.scale.z).toFixed(1)} mm`;
  if (commitToServer) pushTransformToServer(true);
}

// Powiązanie suwaków i pól liczbowych
for (const axis of ['X', 'Y', 'Z']) {
  for (const kind of ['scale', 'pos', 'rot']) {
    const rEl = document.getElementById(`${kind}${axis}Range`);
    const nEl = document.getElementById(`${kind}${axis}Num`);
    const handleInput = (val, commit) => {
      if (!Number.isFinite(val)) return;
      if (kind === 'scale' && lockProportions) {
        const prev = parseFloat(nEl.value) || 100;
        const ratio = prev > 0 ? val / prev : 1;
        for (const a of ['X', 'Y', 'Z']) {
          const cur = parseFloat(document.getElementById(`scale${a}Num`).value) || 100;
          const next = a === axis ? val : +(cur * ratio).toFixed(2);
          setPair(`scale${a}`, next);
        }
      } else {
        setPair(`${kind}${axis}`, val);
      }
      pushTransformToServer(commit);
    };
    rEl.addEventListener('input', () => handleInput(parseFloat(rEl.value), false));
    rEl.addEventListener('change', () => handleInput(parseFloat(rEl.value), true));
    nEl.addEventListener('change', () => handleInput(parseFloat(nEl.value), true));
  }
}

document.getElementById('lockScaleBtn').onclick = (e) => {
  lockProportions = !lockProportions;
  e.currentTarget.setAttribute('aria-pressed', String(lockProportions));
  e.currentTarget.textContent = lockProportions ? '🔒 Proporcje' : '🔓 Niezależne X/Y/Z';
};

document.getElementById('rotMinus90X').onclick = () => {
  const cur = parseFloat(document.getElementById('rotXNum').value) || 0;
  setPair('rotX', ((cur - 90 + 180) % 360) - 180);
  pushTransformToServer(true);
};
document.getElementById('rotPlus90X').onclick = () => {
  const cur = parseFloat(document.getElementById('rotXNum').value) || 0;
  setPair('rotX', ((cur + 90 + 180) % 360) - 180);
  pushTransformToServer(true);
};
document.getElementById('rot180Y').onclick = () => {
  const cur = parseFloat(document.getElementById('rotYNum').value) || 0;
  setPair('rotY', ((cur + 180 + 180) % 360) - 180);
  pushTransformToServer(true);
};

document.getElementById('centerOnHeadBtn').onclick = () => {
  const sel = currentPart();
  if (!sel) return;
  const obj = partMeshes.get(sel.part_id);
  if (!obj) return;
  obj.geometry.computeBoundingBox();
  const box = obj.geometry.boundingBox;
  const cx = 0.5 * (box.min.x + box.max.x) * obj.scale.x;
  const cy = 0.5 * (box.min.y + box.max.y) * obj.scale.y;
  const cz = 0.5 * (box.min.z + box.max.z) * obj.scale.z;
  const headCenterY = (appState?.head?.measurements?.height_mm ?? 240) * 0.5;
  setPair('posX', +(-cx).toFixed(1));
  setPair('posY', +(headCenterY - cy).toFixed(1));
  setPair('posZ', +(-cz).toFixed(1));
  pushTransformToServer(true);
};

document.getElementById('partOpacityRange').oninput = async (e) => {
  const sel = currentPart();
  if (!sel) return;
  const op = parseFloat(e.target.value) / 100.0;
  document.getElementById('partOpacityVal').textContent = `${e.target.value}%`;
  const obj = partMeshes.get(sel.part_id);
  if (obj) {
    obj.material.opacity = op;
    obj.material.depthWrite = op >= 0.98;
  }
  await fetch(`/api/parts/${sel.part_id}/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opacity: op }),
  });
};

document.getElementById('headVisibleChk').onchange = async (e) => {
  const r = await fetch('/api/head', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visible: e.target.checked }),
  });
  await renderState(await r.json());
};

document.getElementById('headOpacityRange').oninput = async (e) => {
  const op = parseFloat(e.target.value) / 100.0;
  if (headMeshObj) headMeshObj.material.opacity = op;
  await fetch('/api/head', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opacity: op }),
  });
};

// Import plików z przeglądarki
const fileInput = document.getElementById('fileInput');
document.getElementById('importBtn').onclick = () => fileInput.click();
fileInput.onchange = async () => {
  if (!fileInput.files.length) return;
  setStatus('Wczytywanie siatki 3D...');
  const fd = new FormData();
  fd.append('unit_scale', document.getElementById('unitsSelect').value);
  for (const f of fileInput.files) fd.append('files', f);
  const r = await fetch('/api/import/upload', { method: 'POST', body: fd });
  fileInput.value = '';
  if (!r.ok) {
    const err = await r.json();
    setStatus(`Błąd: ${err.detail}`);
    return;
  }
  const data = await r.json();
  setStatus(`Zaimportowano ${data.imported.length} el.`);
  await renderState(data.state);
};

// Import z lokalnej ścieżki dysku
document.getElementById('loadLocalBtn').onclick = async () => {
  const p = document.getElementById('localPathInput').value.trim();
  if (!p) return;
  setStatus('Wczytywanie pliku z dysku...');
  const r = await fetch('/api/import/local', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: p,
      unit_scale: parseFloat(document.getElementById('unitsSelect').value),
    }),
  });
  if (!r.ok) {
    const err = await r.json();
    setStatus(`Błąd: ${err.detail}`);
    return;
  }
  const data = await r.json();
  setStatus(`Wczytano: ${data.part.name}`);
  await renderState(data.state);
};

document.getElementById('removePartBtn').onclick = async () => {
  const sel = currentPart();
  if (!sel) return;
  const r = await fetch(`/api/parts/${sel.part_id}`, { method: 'DELETE' });
  await renderState(await r.json());
};

// Przyciski pomocnicze: Auto-Fit i Sprawdź luz 3D
document.getElementById('autoFitBtn').onclick = async () => {
  const sel = currentPart();
  if (!sel) return;
  const btn = document.getElementById('autoFitBtn');
  btn.disabled = true;
  setStatus('Obliczanie wstępnego Auto-Fit w tle...');
  try {
    const r = await fetch(`/api/parts/${sel.part_id}/auto-fit`, { method: 'POST' });
    const data = await r.json();
    setStatus('Auto-Fit zakończony — możesz teraz ręcznie skorygować skalę X/Y/Z.');
    await renderState(data.state);
  } finally {
    btn.disabled = false;
  }
};

document.getElementById('checkClearanceBtn').onclick = async () => {
  const sel = currentPart();
  if (!sel) return;
  const btn = document.getElementById('checkClearanceBtn');
  btn.disabled = true;
  setStatus('Analiza prześwitu 3D i kolizji BVH...');
  try {
    const r = await fetch(`/api/parts/${sel.part_id}/clearance`, { method: 'POST' });
    const data = await r.json();
    setStatus('Zaktualizowano analizę prześwitu 3D.');
    await renderState(data.state);
  } finally {
    btn.disabled = false;
  }
};

// Eksport STL oraz zapis/odczyt projektu JSON
document.getElementById('exportStlBtn').onclick = () => {
  const sel = currentPart();
  if (!sel) return;
  window.location.href = `/api/parts/${sel.part_id}/export-stl`;
};

document.getElementById('saveProjectBtn').onclick = () => {
  window.location.href = '/api/project/export';
};

const projectFileInput = document.getElementById('projectFileInput');
document.getElementById('openProjectBtn').onclick = () => projectFileInput.click();
projectFileInput.onchange = async () => {
  if (!projectFileInput.files.length) return;
  const fd = new FormData();
  fd.append('file', projectFileInput.files[0]);
  const r = await fetch('/api/project/import', { method: 'POST', body: fd });
  projectFileInput.value = '';
  if (r.ok) {
    setStatus('Wczytano projekt JSON.');
    await renderState(await r.json(), true);
  }
};

document.getElementById('newProject').onclick = async () => {
  const r = await fetch('/api/reset', { method: 'POST' });
  setStatus('Nowy projekt.');
  await renderState(await r.json(), true);
};

document.getElementById('undo').onclick = async () => {
  const r = await fetch('/api/undo', { method: 'POST' });
  await renderState(await r.json(), true);
};
document.getElementById('redo').onclick = async () => {
  const r = await fetch('/api/redo', { method: 'POST' });
  await renderState(await r.json(), true);
};

// Modal wymiarów głowy
const headDialog = document.getElementById('headDialog');
document.getElementById('editMeasurementsBtn').onclick = () => {
  const m = appState.head.measurements;
  document.getElementById('inpCirc').value = m.circumference_mm;
  document.getElementById('inpWidth').value = m.width_mm;
  document.getElementById('inpDepth').value = m.depth_mm;
  document.getElementById('inpHeight').value = m.height_mm;
  headDialog.showModal();
};
document.getElementById('cancelHeadBtn').onclick = () => headDialog.close();
for (const btn of headDialog.querySelectorAll('[data-preset]')) {
  btn.onclick = () => {
    const [c, w, d, h] = btn.dataset.preset.split(',');
    document.getElementById('inpCirc').value = c;
    document.getElementById('inpWidth').value = w;
    document.getElementById('inpDepth').value = d;
    document.getElementById('inpHeight').value = h;
  };
}
document.getElementById('headForm').onsubmit = async (e) => {
  e.preventDefault();
  const r = await fetch('/api/head', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      circumference_mm: parseFloat(document.getElementById('inpCirc').value),
      width_mm: parseFloat(document.getElementById('inpWidth').value),
      depth_mm: parseFloat(document.getElementById('inpDepth').value),
      height_mm: parseFloat(document.getElementById('inpHeight').value),
    }),
  });
  headDialog.close();
  if (r.ok) await renderState(await r.json(), true);
};

// Tryby gizma i skróty klawiszowe W / E / R
function setGizmoMode(mode) {
  gizmo.setMode(mode);
  for (const b of document.querySelectorAll('.gizmo-tools button')) {
    b.classList.toggle('active-toggle', b.dataset.mode === mode);
  }
}
for (const b of document.querySelectorAll('.gizmo-tools button')) {
  b.onclick = () => setGizmoMode(b.dataset.mode);
}

window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'w' || e.key === 'W') setGizmoMode('translate');
  if (e.key === 'e' || e.key === 'E') setGizmoMode('rotate');
  if (e.key === 'r' || e.key === 'R') setGizmoMode('scale');
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    document.getElementById(e.shiftKey ? 'redo' : 'undo').click();
  }
});

// Szybkie kamery widoku
const views = {
  front: [0, 130, 440],
  back: [0, 130, -440],
  left: [-440, 130, 0],
  right: [440, 130, 0],
  top: [0, 560, 1],
  reset: [320, 230, 390],
};
for (const b of document.querySelectorAll('.view-tools button')) {
  b.onclick = () => {
    const pos = views[b.dataset.view];
    if (pos) {
      camera.position.set(...pos);
      orbit.target.set(0, 120, 0);
      orbit.update();
    }
  };
}

function resizeViewport() {
  const rect = canvas.parentElement.getBoundingClientRect();
  camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
  camera.updateProjectionMatrix();
  renderer.setSize(rect.width, rect.height, false);
}
window.addEventListener('resize', resizeViewport);
resizeViewport();

function animate() {
  requestAnimationFrame(animate);
  orbit.update();
  renderer.render(scene, camera);
}
animate();

// Start aplikacji
const initRes = await fetch('/api/state');
await renderState(await initRes.json(), true);
