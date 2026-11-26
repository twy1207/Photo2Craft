import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const stage = $('stage');
const canvas = $('model');
const reference = $('reference');
const extent = $('extent');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
scene.background = new THREE.Color('#edf2f6');
scene.add(new THREE.HemisphereLight(0xffffff, 0x8796a0, 2.4));
const light = new THREE.DirectionalLight(0xffffff, 2.4);
light.position.set(-40, 80, -50);
scene.add(light);
const camera = new THREE.OrthographicCamera(-40, 40, 40, -40, .1, 2000);
const clayCamera = new THREE.PerspectiveCamera(36, 1, .1, 2000);
const orbitBackground = scene.background;
const clayBackground = new THREE.Color(0x000000);
const controls = new OrbitControls(camera, canvas);
controls.listenToKeyEvents(canvas);
controls.minZoom = .4;
controls.maxZoom = 6;
controls.minPolarAngle = .05;
controls.maxPolarAngle = Math.PI - .05;
const grid = new THREE.GridHelper(160, 40, 0xbdcad4, 0xd5e0e7);
grid.position.y = -.06;
scene.add(grid);

let mesh, current, catalog, activeClay;
let span = 80, distance = 150, generation = 0, pending;
const target = new THREE.Vector3();
const viewButtons = [...document.querySelectorAll('[data-view]')];

function draw() {
  const width = stage.clientWidth, height = stage.clientHeight;
  if (!width || !height) return;
  const square = Math.max(1, Math.min(width, height) - 28);
  scene.background = activeClay ? clayBackground : orbitBackground;
  grid.visible = !activeClay;
  if (activeClay) renderer.setViewport((width - square) / 2, (height - square) / 2, square, square);
  else renderer.setViewport(0, 0, width, height);
  renderer.render(scene, activeClay ? clayCamera : camera);
}
controls.addEventListener('change', draw);
function clearViewSelection() { viewButtons.forEach((b) => b.setAttribute('aria-pressed', 'false')); }
controls.addEventListener('start', clearViewSelection);
canvas.addEventListener('keydown', (event) => { if (event.key.startsWith('Arrow')) clearViewSelection(); });
function resize() {
  const width = stage.clientWidth, height = stage.clientHeight;
  if (!width || !height) return;
  renderer.setSize(width, height, false);
  camera.left = -span * width / height / 2;
  camera.right = -camera.left;
  camera.top = span / 2;
  camera.bottom = -camera.top;
  camera.updateProjectionMatrix();
  draw();
}
new ResizeObserver(resize).observe(stage);

function setView(name) {
  if (!current) return;
  const yaw = name === 'front' ? 0 : name === 'side' ? 90 : name === 'back' ? 180 : current.view === 'front_left' ? -35 : current.view === 'front' ? 0 : 35;
  const elevation = name === 'reset' ? 18 : 0;
  const a = THREE.MathUtils.degToRad(yaw), b = THREE.MathUtils.degToRad(elevation);
  controls.target.copy(target);
  camera.position.copy(target).add(new THREE.Vector3(Math.sin(a)*Math.cos(b), Math.sin(b), Math.cos(a)*Math.cos(b)).multiplyScalar(distance));
  camera.zoom = 1;
  camera.updateProjectionMatrix();
  controls.update();
  camera.updateMatrixWorld();
  const [w, h, d] = current.size;
  const projected = [];
  for (const x of [-w/2, w/2]) for (const y of [0, h]) for (const z of [-d/2, d/2]) {
    projected.push(new THREE.Vector3(x, y, z).applyMatrix4(camera.matrixWorldInverse));
  }
  const width = Math.max(...projected.map((p) => p.x)) - Math.min(...projected.map((p) => p.x));
  const height = Math.max(...projected.map((p) => p.y)) - Math.min(...projected.map((p) => p.y));
  span = Math.max(height, width / (stage.clientWidth/stage.clientHeight)) * 1.2;
  resize();
  viewButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.view === name)));
  draw();
}
viewButtons.forEach((button) => button.addEventListener('click', () => {
  if (activeClay) {
    reference.value = 'photo';
    showReference();
  }
  setView(button.dataset.view);
}));

function showReference() {
  const wasClay = activeClay;
  activeClay = current.clay?.find((view) => String(view.index) === reference.value);
  const photo = $('photo');
  const credit = $('credit');
  const url = activeClay?.url ?? current.photo;
  photo.hidden = !url;
  $('reference-empty').hidden = Boolean(url);
  if (url) photo.src = url;
  else photo.removeAttribute('src');
  $('photo-title').textContent = activeClay ? 'Clay 미리보기' : '원본 사진';
  photo.alt = activeClay ? `Clay 시점 ${activeClay.index + 1}` : `${current.title} 원본 사진`;
  credit.replaceChildren();
  stage.dataset.clay = String(Boolean(activeClay));
  controls.enabled = !activeClay;
  $('gesture-help').textContent = activeClay
    ? 'Clay와 같은 카메라입니다. 시점 버튼을 누르면 자유 회전으로 돌아갑니다.'
    : '드래그 회전 · 휠 확대 · 오른쪽 드래그·방향키 이동';

  if (activeClay) {
    const { target: center, radius, fov } = current.clay_camera;
    const a = THREE.MathUtils.degToRad(activeClay.yaw), b = THREE.MathUtils.degToRad(activeClay.elevation);
    const look = new THREE.Vector3(...center);
    clayCamera.fov = fov;
    clayCamera.position.copy(look).addScaledVector(
      new THREE.Vector3(Math.sin(a) * Math.cos(b), Math.sin(b), Math.cos(a) * Math.cos(b)), radius,
    );
    clayCamera.lookAt(look);
    clayCamera.updateProjectionMatrix();
    clearViewSelection();
    const percent = (value) => `${(100 * value).toFixed(1)}%`;
    credit.textContent = activeClay.matched
      ? `GLB와 Clay 윤곽 일치 ${percent(activeClay.alignment)}`
      : '윤곽 정렬이 낮아 이 시점을 보정에서 제외했습니다.';
    if (activeClay.before_iou != null) {
      credit.textContent += ` · 블록 ${percent(activeClay.before_iou)} → ${percent(activeClay.after_iou)}`;
    }
  } else if (current.credit) {
    const link = document.createElement('a');
    link.textContent = '사진 출처';
    link.href = current.credit.page;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    credit.append(`${current.credit.author} · ${current.credit.license} `, link);
  }
  if (wasClay && !activeClay) setView('reset');
  else draw();
}

reference.addEventListener('change', showReference);

function renderBuilding(data) {
  if (mesh) {
    scene.remove(mesh);
    mesh.geometry.dispose();
    mesh.material.dispose();
    mesh.dispose();
  }
  const { size, scene: blocks } = data;
  mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial(), blocks.blocks.length);
  const matrix = new THREE.Matrix4();
  const colors = blocks.palette.map((name) => new THREE.Color(data.colors[name] || '#f000ff'));
  blocks.blocks.forEach(([x, y, z, palette], index) => {
    // Data: +x is screen-right and +z goes back. Map data z to Three's -z
    // so its right-handed camera matches the CPU preview rather than mirroring it.
    matrix.makeTranslation(x+.5-size[0]/2, y+.5, size[2]/2-z-.5);
    mesh.setMatrixAt(index, matrix);
    mesh.setColorAt(index, colors[palette]);
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
  scene.add(mesh);
  target.set(0, size[1]/2, 0);
  span = Math.hypot(...size) * 1.12;
  distance = Math.max(...size)*3;
  resize();
  setView('reset');
}

function status(text, error=false) {
  const box = $('status');
  box.hidden = false;
  box.className = 'status' + (error ? ' error' : '');
  const content = document.createElement('div');
  content.textContent = text;
  if (error) {
    const button = document.createElement('button');
    button.textContent = '다시 불러오기';
    button.addEventListener('click', () => location.reload());
    content.append(document.createElement('br'), button);
  }
  box.replaceChildren(content);
}

async function getJSON(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function loadExample(id) {
  const request = ++generation;
  pending?.abort();
  pending = new AbortController();
  stage.setAttribute('aria-busy', 'true');
  viewButtons.forEach((b) => { b.disabled = true; });
  status('건축물 불러오는 중…');
  try {
    const data = await getJSON('/api/examples/' + encodeURIComponent(id), pending.signal);
    if (request !== generation) return;
    const selectedReference = current?.building === data.building && activeClay ? String(activeClay.index) : 'photo';
    const clayViews = data.clay ?? [];
    const referenceValues = ['photo', ...clayViews.map((view) => String(view.index))];
    current = data;
    activeClay = undefined;
    controls.enabled = true;
    renderBuilding(data);
    if (reference.length !== referenceValues.length || referenceValues.some((value, i) => reference.options[i].value !== value)) {
      reference.replaceChildren(new Option('원본 사진', 'photo'), ...clayViews.map(
        (view) => new Option(`Clay ${view.index + 1}`, String(view.index)),
      ));
    }
    reference.hidden = !clayViews.length;
    reference.value = referenceValues.includes(selectedReference) ? selectedReference : 'photo';
    showReference();
    $('photo-name').textContent = data.title;
    $('photo-name').hidden = !reference.hidden;
    $('variant-label').textContent = data.variant;
    $('summary').textContent = `${data.size.join(' × ')} 블록 · ${data.block_count.toLocaleString('ko-KR')}개`;
    $('notes').replaceChildren(...data.notes.map((text) => {
      const li = document.createElement('li'); li.textContent = text; return li;
    }));
    document.querySelectorAll('[data-example]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.example === id)));
    $('status').hidden = true;
    stage.setAttribute('aria-busy', 'false');
    viewButtons.forEach((b) => { b.disabled = false; });
  } catch (error) {
    if (error.name === 'AbortError' || request !== generation) return;
    stage.setAttribute('aria-busy', 'false');
    status('건축물을 불러오지 못했습니다. 로컬 서버가 실행 중인지 확인해 주세요.', true);
  }
}

function showVariants(variants, preferred) {
  $('variants').replaceChildren(...variants.map((variant) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = variant.variant;
    button.dataset.example = variant.id;
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => loadExample(variant.id));
    return button;
  }));
  const initial = variants.find((variant) => variant.variant === preferred) ?? variants[0];
  loadExample(initial.id);
}

function selectBuilding(id) {
  const entries = catalog.filter((item) => item.building === id);
  const sizes = [...new Set(entries.map((entry) => entry.extent))].filter(Number.isInteger).sort((a, b) => a - b);
  $('extent-control').hidden = sizes.length < 2;
  extent.replaceChildren(...sizes.map((size) => new Option(`${size}블록`, String(size))));
  extent.value = String(entries[0].extent);
  showVariants(entries.filter((entry) => entry.extent === entries[0].extent));
}
$('building').addEventListener('change', (event) => selectBuilding(event.target.value));
extent.addEventListener('change', () => {
  const building = $('building').value;
  const entries = catalog.filter((entry) => entry.building === building && entry.extent === Number(extent.value));
  showVariants(entries, current?.building === building ? current.variant : undefined);
});
$('photo').addEventListener('error', () => {
  $('photo').alt = '비교 이미지를 불러오지 못했습니다.';
});

try {
  catalog = (await getJSON('/api/examples')).examples;
  if (!catalog.length) throw new Error('empty catalog');
  const unique = [...new Map(catalog.map((entry) => [entry.building, entry])).values()];
  $('building').replaceChildren(...unique.map((entry) => {
    const option = document.createElement('option'); option.value = entry.building; option.textContent = entry.title; return option;
  }));
  $('building').disabled = false;
  selectBuilding(unique[0].building);
} catch {
  status('예제 목록을 불러오지 못했습니다. 로컬 서버가 실행 중인지 확인해 주세요.', true);
}
