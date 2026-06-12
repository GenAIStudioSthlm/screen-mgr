// control.js — extracted verbatim from control.html prototype. Mock data + interactions; backend wiring layered on in later phases.
if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}
// ── THEME ────────────────────────────────────────────────────────────────────

const SUN_SVG  = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><circle cx="12" cy="12" r="5"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
const MOON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

function toggleTheme() {
  const isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('studio-theme', isLight ? 'light' : 'dark');
  syncThemeIcon();
  renderAllZones();   // zone off-fill changes between light (#D2D2CF) and dark (#1e1e1e)
  buildGradGrid();    // off swatch background + label colour changes
  cancelAnimationFrame(waveRaf);
  drawWave();
}

function syncThemeIcon() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const isLight = document.documentElement.classList.contains('light');
  btn.innerHTML = isLight ? MOON_SVG : SUN_SVG;
  btn.title = isLight ? 'Switch to dark mode' : 'Switch to light mode';
}

// ── DATA ──────────────────────────────────────────────────────────────────────

const LIGHT_PRESETS = [
  { id:'warm',    label:'Hue 1', color:'#FF9B3E', temp:2700 },
  { id:'neutral', label:'Hue 2', color:'#FFE5B4', temp:3500 },
  { id:'cool',    label:'Hue 3', color:'#C8DCFF', temp:6000 },
  { id:'blue',    label:'Hue 4', color:'#0058A3', temp:null },
  { id:'yellow',  label:'Hue 5', color:'#FFDA1A', temp:null },
  { id:'off',     label:'Off',   color:'#111111', temp:null },
];

const LIGHT_SCENES = {
  welcome:      { a:'warm',    b:'neutral', c:'neutral', d:'off',     e:'off',     f:'warm',    g:'off',     h:'off',     i:'off',     j:'off',     k:'off',     l:'off',     m:'off',     n:'warm'    },
  workshop:     { a:'blue',    b:'blue',    c:'blue',    d:'blue',    e:'neutral', f:'blue',    g:'blue',    h:'neutral', i:'neutral', j:'neutral', k:'blue',    l:'blue',    m:'cool',    n:'blue'    },
  breakout:     { a:'yellow',  b:'blue',    c:'blue',    d:'yellow',  e:'blue',    f:'yellow',  g:'blue',    h:'off',     i:'off',     j:'off',     k:'yellow',  l:'blue',    m:'cool',    n:'yellow'  },
  presentation: { a:'neutral', b:'cool',    c:'cool',    d:'cool',    e:'neutral', f:'off',     g:'off',     h:'off',     i:'off',     j:'off',     k:'off',     l:'off',     m:'cool',    n:'off'     },
  afterhours:   { a:'warm',    b:'warm',    c:'warm',    d:'warm',    e:'warm',    f:'warm',    g:'warm',    h:'off',     i:'off',     j:'off',     k:'warm',    l:'blue',    m:'off',     n:'warm'    },
  accenture:    { a:'cool',    b:'cool',    c:'cool',    d:'cool',    e:'cool',    f:'cool',    g:'off',     h:'off',     i:'off',     j:'off',     k:'cool',    l:'cool',    m:'cool',    n:'cool'    },
};

const GRADIENTS = [
  { id:'blue',      label:'Blue Deep',    css:'linear-gradient(180deg,#0058A3,#003F7A)',                          svgRef:'url(#gBlue)'      },
  { id:'yellow',    label:'Yellow Warm',  css:'linear-gradient(180deg,#FFDA1A,#F0C400)',                          svgRef:'url(#gYellow)'    },
  { id:'dark',      label:'Dark Night',   css:'linear-gradient(160deg,#0D1B2A,#001530,#00264D)',                  svgRef:'url(#gDark)'      },
  { id:'brand',     label:'Brand',        css:'linear-gradient(135deg,#003F7A,#0058A3 50%,#FFDA1A)',              svgRef:'url(#gBrand)'     },
  { id:'accenture', label:'Brand Dark',   css:'linear-gradient(135deg,#001A3D,#002D5C,#003F7A)', svgRef:'url(#gAccenture)' },
];

// Snapshot of default gradient labels/CSS for restoration when switching away from Accenture
const DEFAULT_GRADIENTS = GRADIENTS.map(g => ({...g}));

// The SVG gradient element IDs that correspond to each GRADIENTS[i] entry (index-aligned)
const GRADIENT_SVG_IDS = ['gBlue', 'gYellow', 'gDark', 'gBrand', 'gAccenture'];

// Original SVG stop colors baked into the HTML (IKEA / default palette) — used for restoration
const DEFAULT_SVG_STOPS = [
  ['#0058A3', '#003F7A'],               // gBlue   — 2 stops
  ['#FFDA1A', '#F0C400'],               // gYellow — 2 stops
  ['#0D1B2A', '#00264D'],               // gDark   — 2 stops
  ['#003F7A', '#0058A3', '#FFDA1A'],   // gBrand  — 3 stops
  ['#001A3D', '#002D5C', '#003F7A'],   // gAccenture — 3 stops
];

// Accenture-specific gradient overrides — ADS core purples only (no pink — secondary colors only)
// Each entry aligns with GRADIENTS[i] and updates the matching SVG gradient stops in both floor plans
const ACCENTURE_GRADIENTS = [
  { label:'Purple Deep', css:'#460073',                                           svgStops:['#460073','#460073']           },
  { label:'Violet',      css:'linear-gradient(180deg,#A100FF,#7500C0)',            svgStops:['#A100FF','#7500C0']           },
  { label:'Dark Purple', css:'linear-gradient(160deg,#07000F,#460073)',            svgStops:['#07000F','#460073']           },
  { label:'Brand Light', css:'linear-gradient(135deg,#C2A3FF,#A100FF,#7500C0)',   svgStops:['#C2A3FF','#A100FF','#7500C0'] },
  { label:'Brand Dark',  css:'linear-gradient(135deg,#07000F,#460073,#A100FF)',   svgStops:['#07000F','#460073','#A100FF'] },
];

const REINVENTION_ZONES = {
  a: { name:'Entrance',    area:28,  grad:'yellow', intensity:80,  anim:'static',   screens:[], light: { preset:'warm',    intensity:80,  temp:2800, fixtures:{ceiling:true,  strip:true,  accent:false, floor:false} } },
  b: { name:'Main Hall W', area:72,  grad:'blue',   intensity:100, anim:'animated', screens:['s1','s3'], light: { preset:'neutral', intensity:90,  temp:3500, fixtures:{ceiling:true,  strip:true,  accent:true,  floor:false} } },
  c: { name:'Main Hall E', area:50,  grad:'blue',   intensity:100, anim:'animated', screens:['s6'], light: { preset:'neutral', intensity:90,  temp:3500, fixtures:{ceiling:true,  strip:true,  accent:true,  floor:false} } },
  d: { name:'Main Upper',  area:65,  grad:'blue',   intensity:90,  anim:'static',   screens:['s2'], light: { preset:'cool',    intensity:85,  temp:5000, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  e: { name:'Studio North',area:60,  grad:'dark',   intensity:85,  anim:'static',   screens:['s5'], light: { preset:'cool',    intensity:100, temp:5500, fixtures:{ceiling:true,  strip:true,  accent:false, floor:false} } },
  f: { name:'Production',  area:55,  grad:'brand',  intensity:75,  anim:'animated', screens:['s4'], light: { preset:'warm',    intensity:70,  temp:3000, fixtures:{ceiling:true,  strip:false, accent:true,  floor:true}  } },
  g: { name:'Workshop',    area:42,  grad:'dark',   intensity:70,  anim:'static',   screens:[], light: { preset:'neutral', intensity:80,  temp:4000, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  h: { name:'Office South',area:38,  grad:'off',    intensity:50,  anim:'static',   screens:[], light: { preset:'neutral', intensity:60,  temp:3500, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  i: { name:'Office Mid',  area:44,  grad:'off',    intensity:50,  anim:'static',   screens:[], light: { preset:'neutral', intensity:60,  temp:3500, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  j: { name:'Office NE',   area:35,  grad:'off',    intensity:50,  anim:'static',   screens:[], light: { preset:'neutral', intensity:60,  temp:3500, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  k: { name:'Studio East', area:36,  grad:'dark',   intensity:80,  anim:'animated', screens:[], light: { preset:'cool',    intensity:85,  temp:5000, fixtures:{ceiling:true,  strip:true,  accent:false, floor:false} } },
  l: { name:'Lab',         area:24,  grad:'dark',   intensity:90,  anim:'trippy',   screens:[], light: { preset:'blue',    intensity:100, temp:null, fixtures:{ceiling:false, strip:true,  accent:true,  floor:false} } },
  m: { name:'Tech Room',   area:20,  grad:'dark',   intensity:100, anim:'static',   screens:[], light: { preset:'cool',    intensity:100, temp:6000, fixtures:{ceiling:true,  strip:false, accent:false, floor:false} } },
  n: { name:'Annex',       area:85,  grad:'blue',   intensity:100, anim:'static',   screens:[], light: { preset:'warm',    intensity:90,  temp:2700, fixtures:{ceiling:true,  strip:true,  accent:false, floor:true}  } },
};
let ZONES = REINVENTION_ZONES;

const REINVENTION_SCREENS = {
  s1:{ name:'Screen B-North', zone:'b', active:true },
  s2:{ name:'Screen D-North', zone:'d', active:true },
  s3:{ name:'Screen B-East',  zone:'b', active:true },
  s4:{ name:'Screen F-South', zone:'f', active:true },
  s5:{ name:'Screen E-West',  zone:'e', active:true },
  s6:{ name:'Screen C-East',  zone:'c', active:true },
};
let SCREENS = REINVENTION_SCREENS;

const POPUP_ZONES = {
  a: { name:'Main Cloud',       area:45,  grad:'off', intensity:80,  anim:'static',   screens:['pp-s2'], light: { preset:'warm',    intensity:80,  temp:2800, fixtures:{ceiling:true, strip:true,  accent:false,floor:false} } },
  b: { name:'Station 1',        area:30,  grad:'off', intensity:100, anim:'animated', screens:['pp-s6'], light: { preset:'neutral', intensity:90,  temp:3500, fixtures:{ceiling:true, strip:true,  accent:false,floor:false} } },
  c: { name:'Station 2',        area:30,  grad:'off', intensity:100, anim:'animated', screens:['pp-s7'], light: { preset:'neutral', intensity:90,  temp:3500, fixtures:{ceiling:true, strip:false, accent:false,floor:false} } },
  d: { name:'Main Hall',        area:65,  grad:'off', intensity:90,  anim:'static',   screens:['pp-s5'], light: { preset:'cool',    intensity:85,  temp:5000, fixtures:{ceiling:true, strip:false, accent:false,floor:false} } },
  e: { name:'Cloud R',          area:35,  grad:'off', intensity:85,  anim:'animated', screens:['pp-s4'], light: { preset:'cool',    intensity:100, temp:5500, fixtures:{ceiling:true, strip:true,  accent:false,floor:false} } },
  f: { name:'Cloud L',          area:35,  grad:'off', intensity:75,  anim:'animated', screens:['pp-s3'],         light: { preset:'warm',    intensity:70,  temp:3000, fixtures:{ceiling:true, strip:false, accent:true, floor:true } } },
  g: { name:'Control Center',   area:20,  grad:'off', intensity:70,  anim:'static',   screens:[],         light: { preset:'neutral', intensity:80,  temp:4000, fixtures:{ceiling:true, strip:false, accent:false,floor:false} } },
  h: { name:'Station 3',        area:28,  grad:'off', intensity:80,  anim:'animated', screens:['pp-s1'], light: { preset:'cool',    intensity:85,  temp:5000, fixtures:{ceiling:true, strip:true,  accent:false,floor:false} } },
  k: { name:'Tech',             area:22,  grad:'off', intensity:90,  anim:'static',   screens:[],         light: { preset:'cool',    intensity:100, temp:6000, fixtures:{ceiling:true, strip:false, accent:false,floor:false} } },
};

const POPUP_SCREENS = {
  'pp-s1': { name:'Station 3 — Top',      zone:'h', active:false },
  'pp-s2': { name:'Main Cloud — Side',    zone:'a', active:false },
  'pp-s3': { name:'Cloud — Upper Screen', zone:'f', active:false },
  'pp-s4': { name:'Cloud — Lower Screen', zone:'e', active:false },
  'pp-s5': { name:'Main Hall — Side',     zone:'d', active:false },
  'pp-s6': { name:'Station 1 — Base',     zone:'b', active:false },
  'pp-s7': { name:'Station 2 — Base',     zone:'c', active:false },
};

const SCENES = {
  welcome:      { a:'yellow',    b:'blue',      c:'blue',      d:'off',       e:'off',       f:'yellow',    g:'off',       h:'off', i:'off', j:'off', k:'off',       l:'off',       m:'off',       n:'blue'      },
  workshop:     { a:'brand',     b:'blue',      c:'blue',      d:'blue',      e:'brand',     f:'blue',      g:'brand',     h:'off', i:'off', j:'off', k:'blue',      l:'brand',     m:'dark',      n:'blue'      },
  breakout:     { a:'brand',     b:'brand',     c:'brand',     d:'brand',     e:'brand',     f:'brand',     g:'brand',     h:'off', i:'off', j:'off', k:'brand',     l:'brand',     m:'brand',     n:'brand'     },
  presentation: { a:'off',       b:'dark',      c:'dark',      d:'dark',      e:'off',       f:'off',       g:'off',       h:'off', i:'off', j:'off', k:'off',       l:'off',       m:'dark',      n:'off'       },
  afterhours:   { a:'dark',      b:'dark',      c:'dark',      d:'dark',      e:'dark',      f:'dark',      g:'dark',      h:'off', i:'off', j:'off', k:'dark',      l:'dark',      m:'dark',      n:'dark'      },
  accenture:    { a:'accenture', b:'accenture', c:'accenture', d:'accenture', e:'accenture', f:'accenture', g:'accenture', h:'off', i:'off', j:'off', k:'accenture', l:'accenture', m:'accenture', n:'accenture' },
  ikea:         { a:'yellow',    b:'dark',      c:'off',       d:'yellow',    e:'brand',     f:'brand',     g:'blue',      h:'dark',                k:'off'       },
};

const COMPANIES = {
  ikea:      { scene:'ikea',         anim:'animated' },
  hm:        { scene:'presentation', anim:'static'   },
  accenture: { scene:'accenture',    anim:'animated' },
};

// Scenes shown in the sidebar when each company is active
const COMPANY_SCENES = {
  ikea: [
    { id:'welcome',      label:'Welcome',          dot:'background:#FFDA1A; box-shadow:0 0 4px #FFDA1A55;' },
    { id:'workshop',     label:'Workshop',          dot:'background:#0058A3; box-shadow:0 0 4px #0058A355;' },
    { id:'breakout',     label:'Breakout Sessions', dot:'background:linear-gradient(135deg,#003F7A,#0058A3,#FFDA1A);' },
    { id:'presentation', label:'Presentation',      dot:'background:#001E3C; border:1px solid #0058A3;' },
    { id:'afterhours',   label:'After Hours',       dot:'background:#111; border:1px solid #333;' },
  ],
  accenture: [
    { id:'accenture', label:'Demo 12 June', dot:'background:linear-gradient(135deg,#460073,#A100FF);' },
  ],
  hm: [
    { id:'presentation', label:'Presentation', dot:'background:#E50010;' },
    { id:'afterhours',   label:'After Hours',  dot:'background:#111; border:1px solid #333;' },
  ],
};

// ── STATE ─────────────────────────────────────────────────────────────────────

let selectedZone = 'b';
let activeScene  = null;
let activeCompany = null;
let globalAnim = null; // set by company
let currentFloorplan = 'popup';

// Gradient color map for glow effects
const GRAD_COLORS = {
  blue:      '#0058A3',
  yellow:    '#FFDA1A',
  dark:      '#0D1B2A',
  brand:     '#0058A3',
  accenture: '#A100FF',
  off:       null,
};

// Screen-line representative colors when Accenture gradients are active
// (keyed by GRADIENTS[i].id, matching the Accenture override palette)
const ACCENTURE_GRAD_COLORS = {
  blue:      '#460073',  // Purple Deep
  yellow:    '#A100FF',  // Violet
  dark:      '#460073',  // Dark Purple
  brand:     '#A100FF',  // Brand Light
  accenture: '#A100FF',  // Brand Dark
  off:       null,
};

// ── INIT ──────────────────────────────────────────────────────────────────────

function init() {
  setFloorplan('popup');   // sets ZONES, SCREENS, shows correct SVG, activates button

  // Default side-panel gradient palette: Accenture
  ACCENTURE_GRADIENTS.forEach((ag, i) => { GRADIENTS[i].label = ag.label; GRADIENTS[i].css = ag.css; });
  GRADIENT_SVG_IDS.forEach((svgId, i) => _applyGradientStops(svgId, ACCENTURE_GRADIENTS[i].svgStops));
  Object.assign(GRAD_COLORS, ACCENTURE_GRAD_COLORS);
  activeCompany = 'accenture'; // so switching to another company correctly restores IKEA defaults

  buildGradGrid();
  attachZoneClicks();
  updateClock();
  setInterval(updateClock, 1000);
  syncThemeIcon();
}

// ── CLOCK ─────────────────────────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2,'0');
  const m = String(now.getMinutes()).padStart(2,'0');
  const s = String(now.getSeconds()).padStart(2,'0');
  document.getElementById('clock').textContent = `${h}:${m}:${s}`;
}

// ── GRADIENT GRID ──────────────────────────────────────────────────────────────

function buildGradGrid() {
  const isLight = document.documentElement.classList.contains('light');
  const grid = document.getElementById('grad-grid');
  grid.innerHTML = '';
  GRADIENTS.forEach(g => {
    const el = document.createElement('div');
    el.className = 'grad-swatch';
    el.dataset.grad = g.id;
    el.style.background = g.css;
    el.innerHTML = `<span>${g.label}</span>`;
    el.addEventListener('click', () => onGradChange(g.id));
    grid.appendChild(el);
  });
  // "Off" swatch — colours adapt to theme
  const offEl = document.createElement('div');
  offEl.className = 'grad-swatch';
  offEl.dataset.grad = 'off';
  if (isLight) {
    offEl.style.background = '#D2D2CF';
    offEl.style.border = '1.5px solid rgba(0,0,0,0.12)';
    offEl.innerHTML = `<span style="color:rgba(0,0,0,0.38)">Off</span>`;
  } else {
    offEl.style.background = '#1e1e1e';
    offEl.style.border = '1.5px solid #333';
    offEl.innerHTML = `<span style="color:rgba(255,255,255,0.3)">Off</span>`;
  }
  offEl.addEventListener('click', () => onGradChange('off'));
  grid.appendChild(offEl);
}

// ── ZONE CLICKS ───────────────────────────────────────────────────────────────

function attachZoneClicks() {
  document.querySelectorAll('.zone-rect').forEach(el => {
    el.addEventListener('click', () => selectZone(el.dataset.zone));
  });
}

function selectZone(zoneId) {
  if (!ZONES[zoneId]) return;

  const pfx = currentFloorplan === 'popup' ? 'pu-zone-' : 'zone-';

  // Deselect old
  const old = document.getElementById(pfx + selectedZone);
  if (old) {
    old.setAttribute('stroke', '#0a0a0a');
    old.setAttribute('stroke-width', '2');
  }

  selectedZone = zoneId;
  justAppliedToAll = false; // new zone selected — re-evaluate button state

  // Highlight new
  const el = document.getElementById(pfx + zoneId);
  if (el) {
    el.setAttribute('stroke', 'rgba(255,255,255,0.55)');
    el.setAttribute('stroke-width', '1.5');
  }

  // Sync upload-list to this zone's file (if any)
  const list = document.getElementById('upload-list');
  const zf   = zoneFiles[zoneId];
  if (list) {
    list.innerHTML = zf
      ? `<div class="upload-item"><span class="upload-item-name">${zf.name}</span><button class="upload-clear-btn" onclick="clearZoneFile()" title="Remove file">×</button></div>`
      : '';
  }

  renderRightPanel();
}

// ── RIGHT PANEL ───────────────────────────────────────────────────────────────

function renderRightPanel() {
  const z = ZONES[selectedZone];
  const zId = selectedZone.toUpperCase();

  // Title
  document.getElementById('zone-title').textContent = `${zId} — ${z.name}`;
  document.getElementById('zone-sub').textContent = `${z.area} m²  ·  Zone ${zId}`;

  // Preview
  renderPreview();

  // Gradient grid selection
  document.querySelectorAll('.grad-swatch').forEach(el => {
    el.classList.toggle('selected', el.dataset.grad === z.grad);
  });

  // Intensity
  const slider = document.getElementById('intensity-slider');
  slider.value = z.intensity;
  document.getElementById('intensity-val').textContent = z.intensity;

  // Animation — disable when a file is driving the zone colour
  const hasFile = !!zoneFiles[selectedZone];
  document.querySelectorAll('.anim-opt').forEach(el => {
    el.classList.toggle('active',   !hasFile && el.dataset.anim === z.anim);
    el.classList.toggle('disabled', hasFile);
  });


  // Screens
  renderScreenList();

  // Lighting panel (shown in lighting/combined views)
  if (currentView === 'lighting' || currentView === 'combined') {
    renderLightingPanel(selectedZone);
  }
  updateApplyAllState();
}

function renderPreview() {
  const z       = ZONES[selectedZone];
  const preview = document.getElementById('zone-preview');

  preview.className = '';
  preview.id = 'zone-preview';
  preview.innerHTML = '';
  preview.style.background = '';
  preview.style.filter = '';
  preview.style.opacity = '';

  // ── File upload takes priority in screens/combined view ──
  const fileData = zoneFiles[selectedZone];
  if (fileData && currentView !== 'lighting') {
    renderFilePreview(fileData, preview);
    return;
  }

  if (currentView === 'lighting' && z.light) {
    // ── LIGHTING VIEW: show light colour radial for the zone ──
    const light  = z.light;
    const preset = LIGHT_PRESETS.find(p => p.id === light.preset);
    if (light.preset === 'off' && !light.wheelColor) {
      preview.style.background = '#0a0a0a';
      preview.style.filter     = 'none';
      preview.style.opacity    = '0.45';
    } else {
      const col = light.wheelColor
        ? light.wheelColor
        : (preset && preset.temp !== null && light.temp)
          ? tempToColor(light.temp)
          : (preset ? preset.color : '#ffffff');
      const bri = (0.25 + (light.intensity / 100) * 0.75).toFixed(2);
      preview.style.background = `radial-gradient(ellipse at 50% 15%, ${col} 0%, #0a0a0a 100%)`;
      preview.style.filter     = `brightness(${bri})`;
      preview.style.opacity    = '1';
    }
    return;
  }

  // ── SCREENS / COMBINED VIEW: show zone gradient ──
  const gradObj = GRADIENTS.find(g => g.id === z.grad);
  preview.style.background = gradObj ? gradObj.css : '#1e1e1e';
  preview.style.opacity    = '1';
  const bri = z.grad === 'off' ? 0.25 : (0.3 + (z.intensity / 100) * 0.7);
  preview.style.filter     = `brightness(${bri.toFixed(2)})`;

  if (z.grad !== 'off') {
    if (z.anim === 'animated') preview.classList.add('preview-anim-animated');
    if (z.anim === 'trippy')   preview.classList.add('preview-anim-trippy');
  }
  if (z.grad === 'accenture')  preview.classList.add('preview-anim-accenture');
}

function renderScreenList() {
  const z = ZONES[selectedZone];
  const list = document.getElementById('screen-list');
  if (!list) return;
  list.innerHTML = '';

  if (!z.screens || z.screens.length === 0) {
    list.innerHTML = `<div id="no-screens">No screens in this zone</div>`;
    return;
  }

  z.screens.forEach(sid => {
    const sc = SCREENS[sid];
    if (!sc) return;
    const row = document.createElement('div');
    row.className = 'screen-row';

    const icon = document.createElement('div');
    icon.className = 'screen-icon';

    const name = document.createElement('div');
    name.className = 'screen-name';
    name.textContent = sc.name;

    const pill = document.createElement('button');
    pill.className = `toggle-pill ${sc.active ? 'on' : 'off'}`;
    pill.setAttribute('aria-label', `Toggle ${sc.name}`);
    pill.addEventListener('click', () => {
      sc.active = !sc.active;
      pill.className = `toggle-pill ${sc.active ? 'on' : 'off'}`;
      const zz = ZONES[sc.zone];
      if (!sc.active) {
        // Save and clear gradient so zone area goes dark
        sc._savedGrad = zz.grad;
        zz.grad = 'off';
      } else {
        // Restore saved gradient if there was one
        if (sc._savedGrad && sc._savedGrad !== 'off') zz.grad = sc._savedGrad;
        sc._savedGrad = null;
      }
      renderZone(sc.zone);
      renderScreenSvg(sid);
      renderPreview();
      // Refresh sidebar gradient/anim state if this zone is currently selected
      if (sc.zone === selectedZone) renderRightPanel();
    });

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(pill);
    list.appendChild(row);
  });
}

// ── ZONE SVG RENDERING ────────────────────────────────────────────────────────

function renderZone(zoneId) {
  const z = ZONES[zoneId];
  const el = currentFloorplan === 'popup'
    ? document.getElementById(`pu-zone-${zoneId}`)
    : document.getElementById(`zone-${zoneId}`);
  if (!el) return;

  // Fill — light mode uses a warm light-grey for off zones so they're readable
  const isLightMode = document.documentElement.classList.contains('light');
  const offFill = isLightMode ? '#D2D2CF' : '#1e1e1e';
  if (z.grad === 'off') {
    el.setAttribute('fill', offFill);
  } else {
    const gradObj = GRADIENTS.find(g => g.id === z.grad);
    if (gradObj) {
      const svgRef = currentFloorplan === 'popup'
        ? gradObj.svgRef.replace('url(#g', 'url(#pg')
        : gradObj.svgRef;
      el.setAttribute('fill', svgRef);
    } else {
      el.setAttribute('fill', offFill);
    }
  }

  // Opacity — light mode keeps full opacity so gradients stay vivid, not washed out
  if (isLightMode) {
    el.style.opacity = z.grad === 'off' ? '1' : '1';
  } else {
    el.style.opacity = z.grad === 'off' ? '0.4' : (0.4 + (z.intensity / 100) * 0.6);
  }

  // Animation class
  el.classList.remove('anim-animated', 'anim-trippy');
  if (z.grad !== 'off') {
    if (z.anim === 'animated') el.classList.add('anim-animated');
    if (z.anim === 'trippy')   el.classList.add('anim-trippy');
  }
}

function renderAllZones() {
  Object.keys(ZONES).forEach(zoneId => renderZone(zoneId));
}

// ── SCREEN SVG RENDERING ──────────────────────────────────────────────────────

function renderScreenSvg(sid) {
  const sc = SCREENS[sid];
  if (!sc) return;
  const el = document.getElementById(`screen-${sid}`);
  if (!el) return;

  const z = ZONES[sc.zone];
  const hasFile = !!z.uploadColor;
  const isActive = sc.active && (hasFile || z.grad !== 'off');
  const color = z.uploadColor || GRAD_COLORS[z.grad] || '#444';

  if (isActive) {
    el.setAttribute('fill', color);
    el.setAttribute('opacity', '0.9');
    el.style.filter = `drop-shadow(0 0 ${hasFile ? '18px' : '5px'} ${color})`;
    // subtle pulse when driven by uploaded file
    if (hasFile) el.classList.add('screen-file-active');
    else el.classList.remove('screen-file-active');
  } else {
    el.setAttribute('fill', '#333');
    el.setAttribute('opacity', '0');
    el.style.filter = 'none';
    el.classList.remove('screen-file-active');
  }
}

// True if the zone has at least one screen that is powered on.
// If none of the zone's screen IDs are in the current SCREENS map (e.g. wrong floor plan),
// treat the zone as always-on so it renders normally.
function isZoneScreenOn(zoneId) {
  const zone = ZONES[zoneId];
  if (!zone.screens || zone.screens.length === 0) return true;
  const known = zone.screens.filter(sid => SCREENS[sid]);
  if (known.length === 0) return true; // IDs not in current map → no control → always on
  return known.some(sid => SCREENS[sid].active);
}

function renderAllScreens() {
  Object.keys(SCREENS).forEach(sid => renderScreenSvg(sid));
  attachScreenHover();
}

// ── SCREEN HOVER FILE PREVIEW ─────────────────────────────────────────────────

function attachScreenHover() {
  document.querySelectorAll('[id^="screen-"]').forEach(el => {
    // Avoid attaching duplicates
    el.removeEventListener('mouseenter', _onScreenEnter);
    el.removeEventListener('mouseleave', _onScreenLeave);
    el.removeEventListener('mousemove',  _onScreenMove);
    el.addEventListener('mouseenter', _onScreenEnter);
    el.addEventListener('mouseleave', _onScreenLeave);
    el.addEventListener('mousemove',  _onScreenMove);
  });
}

function _getScreenZoneFile(el) {
  const key = el.id.replace('screen-', '');
  const sc  = SCREENS[key];
  if (!sc) return null;
  return zoneFiles[sc.zone] || null;
}

function _onScreenEnter(e) {
  const f       = _getScreenZoneFile(e.currentTarget);
  if (!f || !f.thumbnail) return;
  const tooltip = document.getElementById('screen-hover-preview');
  tooltip.innerHTML = '';
  const img = document.createElement('img');
  img.src = f.thumbnail;
  // Preserve original aspect ratio, cap width
  img.style.cssText = 'display:block;width:100%;height:auto;';
  tooltip.appendChild(img);
  tooltip.style.display = 'block';
  _positionTooltip(e, tooltip);
}

function _onScreenLeave() {
  document.getElementById('screen-hover-preview').style.display = 'none';
}

function _onScreenMove(e) {
  const tooltip = document.getElementById('screen-hover-preview');
  if (tooltip.style.display !== 'none') _positionTooltip(e, tooltip);
}

function _positionTooltip(e, tooltip) {
  const margin = 14;
  let x = e.clientX + margin;
  let y = e.clientY - tooltip.offsetHeight / 2;
  // Keep within viewport
  if (x + tooltip.offsetWidth  > window.innerWidth)  x = e.clientX - tooltip.offsetWidth  - margin;
  if (y < 4) y = 4;
  if (y + tooltip.offsetHeight > window.innerHeight - 4) y = window.innerHeight - tooltip.offsetHeight - 4;
  tooltip.style.left = x + 'px';
  tooltip.style.top  = y + 'px';
}

// ── CHANGE HANDLERS ───────────────────────────────────────────────────────────

// Auto-enable all screens for the given zone (called when content is added)
function enableZoneScreens(zoneId) {
  const zone = ZONES[zoneId];
  if (!zone.screens) return;
  zone.screens.forEach(sid => {
    if (SCREENS[sid]) {
      SCREENS[sid].active = true;
      SCREENS[sid]._savedGrad = null;
    }
  });
}

function onGradChange(gradId) {
  ZONES[selectedZone].grad = gradId;
  if (gradId !== 'off') enableZoneScreens(selectedZone);
  markZoneChanged();
  renderZone(selectedZone);
  renderAllScreens();
  renderRightPanel();
  clearSceneHighlight();
}

function onIntensityChange(val) {
  ZONES[selectedZone].intensity = parseInt(val, 10);
  document.getElementById('intensity-val').textContent = val;
  markZoneChanged();
  renderZone(selectedZone);
  renderPreview();
  clearSceneHighlight();
}

function onAnimChange(animId) {
  if (zoneFiles[selectedZone]) return; // file active — animations disabled
  ZONES[selectedZone].anim = animId;
  document.querySelectorAll('.anim-opt').forEach(el => {
    el.classList.toggle('active', el.dataset.anim === animId);
  });
  markZoneChanged();
  renderZone(selectedZone);
  renderPreview();
  clearSceneHighlight();
}

// ── FILE UPLOAD & PREVIEW ─────────────────────────────────────────────────────

const FILE_TYPES = {
  'image/jpeg':       { category: 'image', maxMB: 15  },
  'image/png':        { category: 'image', maxMB: 15  },
  'video/mp4':        { category: 'video', maxMB: 250 },
  'video/quicktime':  { category: 'video', maxMB: 250 },
  'application/pdf':  { category: 'pdf',   maxMB: 30  },
};

// Per-zone file state — lives only in memory, gone on page close
const zoneFiles = {};

function onFileUpload(input) {
  const file = input.files[0];
  input.value = '';
  if (!file) return;

  const info = FILE_TYPES[file.type];
  if (!info) { showToast('Unsupported format — use JPG, PNG, PDF, MP4 or MOV'); return; }
  if (file.size > info.maxMB * 1024 * 1024) {
    showToast(`File too large (max ${info.maxMB} MB for ${info.category})`); return;
  }

  // Revoke previous object URL for this zone to free memory
  const prev = zoneFiles[selectedZone];
  if (prev) {
    URL.revokeObjectURL(prev.url);
    if (prev.pdfDoc) prev.pdfDoc.destroy();
  }

  zoneFiles[selectedZone] = {
    url: URL.createObjectURL(file),
    category: info.category,
    name: file.name,
    pdfDoc: null, pdfPage: 1, pdfTotal: 1, thumbnail: null,
  };

  // Deactivate gradient so the file drives the screen colour
  ZONES[selectedZone].grad = 'off';

  // Show filename row with clear button
  const list = document.getElementById('upload-list');
  list.innerHTML = `<div class="upload-item">
    <span class="upload-item-name">${file.name}</span>
    <button class="upload-clear-btn" onclick="clearZoneFile()" title="Remove file">×</button>
  </div>`;

  enableZoneScreens(selectedZone); // auto-power the screen when a file is added
  renderZone(selectedZone);        // update floor plan zone fill to off
  renderAllScreens();              // update screen glow (uploadColor not yet set — fires again after extract)
  renderRightPanel();
}

function clearZoneFile() {
  const f = zoneFiles[selectedZone];
  if (f) {
    URL.revokeObjectURL(f.url);
    if (f.pdfDoc) f.pdfDoc.destroy();
    delete zoneFiles[selectedZone];
  }
  delete ZONES[selectedZone].uploadColor;
  document.getElementById('upload-list').innerHTML = '';
  renderPreview();
  renderAllScreens();
}

// ── FILE PREVIEW RENDERING ────────────────────────────────────────────────────

function renderFilePreview(fileData, preview) {
  preview.classList.add('has-media');
  preview.style.background = '#000';

  if (fileData.category === 'image') {
    const img = document.createElement('img');
    img.src = fileData.url;
    img.alt = fileData.name;
    img.onload = () => {
      extractAndApplyColor(img, selectedZone);
    };
    preview.appendChild(img);

  } else if (fileData.category === 'video') {
    const vid = document.createElement('video');
    vid.src = fileData.url;
    vid.autoplay = true; vid.loop = true; vid.muted = true; vid.playsInline = true;
    vid.addEventListener('loadeddata', () => { vid.currentTime = 1.5; });
    vid.addEventListener('seeked', () => {
      extractAndApplyColor(vid, selectedZone);
    }, { once: true });
    preview.appendChild(vid);

  } else if (fileData.category === 'pdf') {
    renderPdfPage(fileData, preview);
  }
}

async function renderPdfPage(fileData, preview) {
  if (!window.pdfjsLib) {
    preview.innerHTML = '<div style="padding:8px;font-size:10px;color:var(--text-dim)">PDF.js not available — check internet connection</div>';
    return;
  }

  // Load document once
  if (!fileData.pdfDoc) {
    try {
      fileData.pdfDoc  = await pdfjsLib.getDocument(fileData.url).promise;
      fileData.pdfTotal = fileData.pdfDoc.numPages;
    } catch(e) {
      preview.innerHTML = '<div style="padding:8px;font-size:10px;color:#ff5555">Could not load PDF</div>';
      return;
    }
  }

  const page         = await fileData.pdfDoc.getPage(fileData.pdfPage);
  const viewport     = page.getViewport({ scale: 1 });
  const scale        = (preview.clientHeight || 110) / viewport.height;
  const scaled       = page.getViewport({ scale });

  const canvas       = document.createElement('canvas');
  canvas.width       = scaled.width;
  canvas.height      = scaled.height;
  preview.appendChild(canvas);

  await page.render({ canvasContext: canvas.getContext('2d'), viewport: scaled }).promise;

  // Store a thumbnail dataURL for use in the screen hover tooltip
  if (!fileData.thumbnail) fileData.thumbnail = canvas.toDataURL('image/jpeg', 0.82);

  extractAndApplyColor(canvas, selectedZone);

  // Pagination overlay (shows on hover if multi-page)
  if (fileData.pdfTotal > 1) {
    const nav = document.createElement('div');
    nav.className = 'pdf-nav';
    nav.innerHTML = `
      <button class="pdf-nav-btn" onclick="changePdfPage(-1)"
        ${fileData.pdfPage <= 1 ? 'disabled' : ''}>‹</button>
      <span class="pdf-nav-info">${fileData.pdfPage} / ${fileData.pdfTotal}</span>
      <button class="pdf-nav-btn" onclick="changePdfPage(1)"
        ${fileData.pdfPage >= fileData.pdfTotal ? 'disabled' : ''}>›</button>`;
    preview.appendChild(nav);
  }
}

function changePdfPage(delta) {
  const f = zoneFiles[selectedZone];
  if (!f || f.category !== 'pdf') return;
  const next = f.pdfPage + delta;
  if (next < 1 || next > f.pdfTotal) return;
  f.pdfPage = next;
  const preview = document.getElementById('zone-preview');
  preview.innerHTML = '';
  renderPdfPage(f, preview);
}

// ── DOMINANT COLOUR EXTRACTION ────────────────────────────────────────────────

function extractAndApplyColor(sourceEl, zoneId) {
  // Draw source into a small offscreen canvas to sample
  const SIZE = 60;
  const tmp  = document.createElement('canvas');
  tmp.width  = SIZE; tmp.height = SIZE;
  try {
    tmp.getContext('2d').drawImage(sourceEl, 0, 0, SIZE, SIZE);
  } catch(e) { return; }

  const data   = tmp.getContext('2d').getImageData(0, 0, SIZE, SIZE).data;
  let rS = 0, gS = 0, bS = 0, n = 0;

  for (let i = 0; i < data.length; i += 16) {
    const r = data[i], g = data[i+1], b = data[i+2];
    const brightness   = (r + g + b) / 3;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const saturation   = max === 0 ? 0 : (max - min) / max;
    // Skip near-black, near-white, and low-saturation (grey) pixels
    if (brightness < 25 || brightness > 235 || saturation < 0.18) continue;
    rS += r; gS += g; bS += b; n++;
  }

  let color;
  if (n > 0) {
    color = `rgb(${Math.round(rS/n)},${Math.round(gS/n)},${Math.round(bS/n)})`;
  } else {
    // Fallback: plain average (handles greyscale or very desaturated images)
    let r2=0,g2=0,b2=0,c2=0;
    for (let i = 0; i < data.length; i += 16) { r2+=data[i];g2+=data[i+1];b2+=data[i+2];c2++; }
    color = c2 ? `rgb(${Math.round(r2/c2)},${Math.round(g2/c2)},${Math.round(b2/c2)})` : '#888';
  }

  ZONES[zoneId].uploadColor = color;

  // Store a medium-res thumbnail for the hover tooltip (images & video)
  const f = zoneFiles[zoneId];
  if (f && !f.thumbnail && (f.category === 'image' || f.category === 'video')) {
    const t2 = document.createElement('canvas');
    t2.width = 240; t2.height = Math.round(240 * (sourceEl.videoHeight || sourceEl.naturalHeight || 1) / (sourceEl.videoWidth || sourceEl.naturalWidth || 1)) || 160;
    t2.getContext('2d').drawImage(sourceEl, 0, 0, t2.width, t2.height);
    f.thumbnail = t2.toDataURL('image/jpeg', 0.82);
  }

  renderAllScreens();
}

// ── APPLY TO ALL ──────────────────────────────────────────────────────────────

let justAppliedToAll = false;
let profileDirty     = false;

function applyToAllZones() {
  const src = ZONES[selectedZone];
  const srcLight = JSON.parse(JSON.stringify(src.light));
  Object.keys(ZONES).forEach(zId => {
    ZONES[zId].grad      = src.grad;
    ZONES[zId].intensity = src.intensity;
    ZONES[zId].anim      = src.anim;
    ZONES[zId].light     = JSON.parse(JSON.stringify(srcLight));
  });
  renderAllZones();
  renderAllScreens();
  refreshAllLightOverlays();
  justAppliedToAll = true;
  renderRightPanel();
  showToast('Applied to all zones');
  clearSceneHighlight();
}

function updateApplyAllState() {
  const btn = document.querySelector('.btn-apply-all.btn-apply-all--full');
  if (!btn) return;
  const z = ZONES[selectedZone];
  const hasScreenContent = z && (z.grad !== 'off' || zoneFiles[selectedZone]);
  const hasLightContent  = z && z.light && z.light.preset && z.light.preset !== 'off';
  const hasContent = hasScreenContent || hasLightContent;
  btn.disabled = !hasContent || justAppliedToAll;
}

function markZoneChanged() {
  justAppliedToAll = false;
  updateApplyAllState();
  if (activeCompany !== null || activeScene !== null) {
    profileDirty = true;
    updateSaveState();
  }
}

function updateSaveState() {
  const btn = document.getElementById('btn-save-changes');
  if (!btn) return;
  const hasProfile = activeCompany !== null || activeScene !== null;
  btn.disabled = !(hasProfile && profileDirty);
}

function saveChanges() {
  if (!profileDirty) return;
  const names = { ikea:'IKEA', hm:'H&M', accenture:'Accenture' };
  const profileName = activeCompany
    ? (names[activeCompany] || activeCompany)
    : (activeScene || 'Profile');
  profileDirty = false;
  updateSaveState();
  showToast(`Saved to ${profileName} profile`);
}

// ── SCENES ─────────────────────────────────────────────────────────────────────

function applyScene(sceneId) {
  const scene = SCENES[sceneId];
  if (!scene) return;

  // Re-enable all screens so brand-profile zones light up correctly
  Object.values(SCREENS).forEach(sc => {
    sc.active = true;
    sc._savedGrad = null;
  });

  Object.keys(scene).forEach(zId => {
    if (ZONES[zId]) ZONES[zId].grad = scene[zId];
  });
  if (LIGHT_SCENES[sceneId]) {
    const ls = LIGHT_SCENES[sceneId];
    Object.keys(ls).forEach(zid => {
      if (ZONES[zid]) ZONES[zid].light.preset = ls[zid];
    });
    refreshAllLightOverlays();
  }
  renderAllZones();
  renderAllScreens();
  renderRightPanel();

  // Highlight scene button
  document.querySelectorAll('.scene-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.scene === sceneId);
  });
  document.querySelectorAll('.company-btn').forEach(btn => btn.classList.remove('active'));

  activeScene = sceneId;
  activeCompany = null;

  // Update header scene name
  const labels = {
    welcome:'Welcome', workshop:'Workshop', breakout:'Breakout Sessions',
    presentation:'Presentation', afterhours:'After Hours', accenture:'Demo 12 June'
  };
  const _asn = document.getElementById('active-scene-name'); if (_asn) _asn.textContent = (labels[sceneId] || sceneId).toUpperCase();

  // Update Scenes dropdown label + mark has-value + close
  const scenesLabel = document.querySelector('#hdr-scenes .hdr-dd-label');
  if (scenesLabel) scenesLabel.textContent = labels[sceneId] || sceneId;
  const scenesDdBtn = document.querySelector('#hdr-scenes .hdr-dd-btn');
  if (scenesDdBtn) scenesDdBtn.classList.add('has-value');
  document.querySelectorAll('.hdr-dd-panel').forEach(p => p.classList.remove('open'));
  document.querySelectorAll('.hdr-dd-btn').forEach(b => b.classList.remove('open'));

  showToast(`Scene: ${labels[sceneId] || sceneId}`);

  const editBtn = document.getElementById('company-edit-btn');
  if (editBtn) editBtn.style.display = 'none';

  profileDirty = false;
  updateSaveState();
}

// ── COMPANIES ─────────────────────────────────────────────────────────────────

// ── GRADIENT HELPERS ──────────────────────────────────────────────────────────
function _applyGradientStops(gradId, colors) {
  [gradId, 'p' + gradId].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const stops = el.querySelectorAll('stop');
    colors.forEach((c, i) => { if (stops[i]) stops[i].setAttribute('stop-color', c); });
  });
}

// Rebuild gradient stops from scratch — supports any number of stops for smooth multi-color gradients
function _rebuildGradientStops(gradId, colors, opacity) {
  const op = opacity !== undefined ? opacity : 0.75;
  [gradId, 'p' + gradId].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelectorAll('stop').forEach(s => s.remove());
    const ns = colors.length;
    colors.forEach((c, i) => {
      const stop = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
      stop.setAttribute('offset', (i / (ns - 1) * 100).toFixed(1) + '%');
      stop.setAttribute('stop-color', c);
      stop.setAttribute('stop-opacity', op.toString());
      el.appendChild(stop);
    });
  });
}

function applyCompany(companyId) {
  const co = COMPANIES[companyId];
  if (!co) return;

  // Restore default gradients (labels, CSS, SVG stops, screen colors) when leaving Accenture
  if (activeCompany === 'accenture' && companyId !== 'accenture') {
    DEFAULT_GRADIENTS.forEach((dg, i) => {
      GRADIENTS[i].label = dg.label;
      GRADIENTS[i].css   = dg.css;
    });
    GRADIENT_SVG_IDS.forEach((svgId, i) => _applyGradientStops(svgId, DEFAULT_SVG_STOPS[i]));
    Object.assign(GRAD_COLORS, { blue:'#0058A3', yellow:'#FFDA1A', dark:'#0D1B2A', brand:'#0058A3', accenture:'#A100FF' });
    buildGradGrid();
  }

  // Apply Accenture-specific gradient overrides: labels, CSS preview, SVG stop colors, screen-line colors
  if (companyId === 'accenture') {
    ACCENTURE_GRADIENTS.forEach((ag, i) => {
      GRADIENTS[i].label = ag.label;
      GRADIENTS[i].css   = ag.css;
    });
    GRADIENT_SVG_IDS.forEach((svgId, i) => _applyGradientStops(svgId, ACCENTURE_GRADIENTS[i].svgStops));
    Object.assign(GRAD_COLORS, ACCENTURE_GRAD_COLORS);
    buildGradGrid();
  }

  applyScene(co.scene);
  activeCompany = companyId; // restore after applyScene resets it
  activeScene = null;        // scene was applied as part of company load, not user-chosen

  // Reset Scenes dropdown label — no scene explicitly selected yet
  const scenesLabelEl = document.querySelector('#hdr-scenes .hdr-dd-label');
  if (scenesLabelEl) scenesLabelEl.textContent = '—';
  const scenesDdBtnEl = document.querySelector('#hdr-scenes .hdr-dd-btn');
  if (scenesDdBtnEl) scenesDdBtnEl.classList.remove('has-value');
  // Clear any scene button highlight
  document.querySelectorAll('.scene-btn').forEach(btn => btn.classList.remove('active'));

  // Populate scenes panel for this company
  buildCompanyScenes(companyId);

  // Override animation for all zones
  Object.keys(ZONES).forEach(zId => {
    ZONES[zId].anim = co.anim;
  });
  renderAllZones();
  renderRightPanel();

  // Highlight company button
  document.querySelectorAll('.company-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.company === companyId);
  });
  document.querySelectorAll('.scene-btn').forEach(btn => btn.classList.remove('active'));

  const names = {ikea:'IKEA', hm:'H&M', accenture:'Accenture'};
  const _asn = document.getElementById('active-scene-name'); if (_asn) _asn.textContent = `${names[companyId] || companyId} PROFILE`;

  // Update header dropdown label + mark has-value + close panel
  const profileLabel = document.querySelector('#hdr-profiles .hdr-dd-label');
  if (profileLabel) profileLabel.textContent = names[companyId] || companyId;
  const profileDdBtn = document.querySelector('#hdr-profiles .hdr-dd-btn');
  if (profileDdBtn) profileDdBtn.classList.add('has-value');
  document.querySelectorAll('.hdr-dd-panel').forEach(p => p.classList.remove('open'));
  document.querySelectorAll('.hdr-dd-btn').forEach(b => b.classList.remove('open'));

  showToast(`Company profile: ${names[companyId] || companyId}`);

  const editBtn = document.getElementById('company-edit-btn');
  if (editBtn) editBtn.style.display = 'inline-flex';

  profileDirty = false;
  updateSaveState();
}

// ── SCENES PANEL ──────────────────────────────────────────────────────────────

function buildCompanyScenes(companyId) {
  const body = document.getElementById('scenes-body');
  if (!body) return;
  const list = COMPANY_SCENES[companyId] || [];
  if (!list.length) {
    body.innerHTML = '<div class="hdr-dd-empty">No scenes for this profile</div>';
    return;
  }
  body.innerHTML = list.map(s =>
    `<button class="scene-btn" data-scene="${s.id}" onclick="applyScene('${s.id}')">
       <span class="scene-dot" style="${s.dot}"></span>${s.label}
     </button>`
  ).join('');
}

function clearCompanyScenes() {
  const body = document.getElementById('scenes-body');
  if (body) body.innerHTML = '<div class="hdr-dd-empty">Select a brand profile first</div>';
}

// ── QUICK ACTIONS ─────────────────────────────────────────────────────────────

function toggleHdrDropdown(id) {
  const wrap  = document.getElementById(id);
  const btn   = wrap.querySelector('.hdr-dd-btn');
  const panel = wrap.querySelector('.hdr-dd-panel');
  const isOpen = panel.classList.contains('open');
  // Close all first
  document.querySelectorAll('.hdr-dd-panel').forEach(p => p.classList.remove('open'));
  document.querySelectorAll('.hdr-dd-btn').forEach(b => b.classList.remove('open'));
  if (!isOpen) { panel.classList.add('open'); btn.classList.add('open'); }
}

// Close header dropdowns on outside click
document.addEventListener('click', e => {
  if (!e.target.closest('.hdr-dropdown')) {
    document.querySelectorAll('.hdr-dd-panel').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.hdr-dd-btn').forEach(b => b.classList.remove('open'));
  }
});

function triggerQuickAction(text, container) {
  // Clear contents but keep the container in the DOM — setQuickActions needs it
  if (container) container.innerHTML = '';
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = text;
  document.getElementById('chat-send').disabled = false;
  sendChatMessage();
}

// ── COMPANIES ─────────────────────────────────────────────────────────────────

function removeCompany(companyId, event) {
  event.stopPropagation();
  const btn = document.querySelector(`.company-btn[data-company="${companyId}"]`);
  if (btn) btn.remove();
  delete COMPANIES[companyId];
}

function editCompany(companyId, event) {
  event.stopPropagation();
  // Close the dropdown first
  document.querySelectorAll('.hdr-dd-panel').forEach(p => p.style.display = '');
  document.querySelectorAll('.hdr-dd-btn').forEach(b => b.classList.remove('open'));
  // Navigate to brand builder with the company pre-loaded for editing
  window.location.href = `brand.html?edit=${encodeURIComponent(companyId)}`;
}

// ── HELPERS ───────────────────────────────────────────────────────────────────

function clearSceneHighlight() {
  document.querySelectorAll('.scene-btn, .company-btn').forEach(btn => btn.classList.remove('active'));
  activeScene = null;
  const _asn = document.getElementById('active-scene-name'); if (_asn) _asn.textContent = '—';
  const editBtn = document.getElementById('company-edit-btn');
  if (editBtn) editBtn.style.display = 'none';
}

let toastTimer = null;
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
}

// ── FLOOR PLAN TOGGLE ─────────────────────────────────────────────────────────
function setFloorplan(plan) {
  currentFloorplan = plan;
  ZONES   = plan === 'reinvention' ? REINVENTION_ZONES : POPUP_ZONES;
  SCREENS = plan === 'reinvention' ? REINVENTION_SCREENS : POPUP_SCREENS;

  document.getElementById('fp-reinvention').style.display = plan === 'reinvention' ? 'flex' : 'none';
  document.getElementById('fp-popup').style.display       = plan === 'popup'        ? 'flex' : 'none';

  // Lighting layer
  const reinvLayer = document.getElementById('lighting-layer');
  const popupLayer = document.getElementById('pu-lighting-layer');
  if (reinvLayer) reinvLayer.style.display = 'none';
  if (popupLayer) popupLayer.style.display = 'none';

  // Reset to first zone in new plan
  renderAllZones();
  renderAllScreens();
  selectZone(Object.keys(ZONES)[0]);

  if (currentView === 'lighting' || currentView === 'combined') {
    const layer = plan === 'reinvention' ? reinvLayer : popupLayer;
    if (layer) layer.style.display = 'block';
    refreshAllLightOverlays();
  }
}

// ── VIEW SWITCHING ─────────────────────────────────────────────────────────────
let currentView = 'screens';

function setView(view) {
  currentView = view;
  document.body.classList.remove('view-screens','view-lighting','view-combined');
  document.body.classList.add('view-' + view);
  document.querySelectorAll('.sv-btn').forEach(t => {
    t.classList.toggle('active', t.dataset.view === view);
  });

  const lightingLayer = document.getElementById('lighting-layer');
  const popupLightingLayer = document.getElementById('pu-lighting-layer');
  const activeLightingLayer = currentFloorplan === 'reinvention' ? lightingLayer : popupLightingLayer;

  if (view === 'screens') {
    if (activeLightingLayer) activeLightingLayer.style.display = 'none';
    showLightingSections(false);
  } else if (view === 'lighting') {
    if (activeLightingLayer) activeLightingLayer.style.display = 'block';
    showLightingSections(true);
    refreshAllLightOverlays();
  } else { // combined
    if (activeLightingLayer) activeLightingLayer.style.display = 'block';
    showLightingSections(true);
    refreshAllLightOverlays();
  }
  renderRightPanel(); // re-render with new view context
}

function showLightingSections(show) {
  const ids = ['lighting-section','lighting-intensity-section','light-colorwheel-section'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? '' : 'none';
  });
  if (show) setTimeout(initColorWheel, 50);
}

// ── LIGHTING CONTROL ──────────────────────────────────────────────────────────
function renderLightingPanel(zone) {
  const z = ZONES[zone];
  const light = z.light;

  // Light preset swatches
  const grid = document.getElementById('light-preset-grid');
  if (grid) {
    grid.innerHTML = LIGHT_PRESETS.map(p => {
      // If this preset is selected and a wheel colour is active, tint its swatch
      const isSelected = light.preset === p.id;
      const bg = (isSelected && light.wheelColor) ? light.wheelColor : p.color;
      return `
        <div class="light-swatch ${isSelected ? 'selected' : ''}"
             data-id="${p.id}"
             style="background:${bg}"
             onclick="onLightPresetChange('${p.id}')">
          <span class="light-swatch-label">${p.label}</span>
        </div>`;
    }).join('');
  }

  // Temp slider — disable if preset has no temp
  const tempSlider = document.getElementById('light-temp-slider');
  const tempVal    = document.getElementById('light-temp-val');
  const tempSec    = document.getElementById('lighting-temp-section');
  const preset     = LIGHT_PRESETS.find(p => p.id === light.preset);
  if (tempSlider && tempVal && tempSec) {
    if (preset && preset.temp !== null) {
      tempSlider.value = light.temp || preset.temp;
      tempVal.textContent = (light.temp || preset.temp) + 'K';
      tempSlider.disabled = false;
      tempSec.style.opacity = '1';
    } else {
      tempVal.textContent = '—';
      tempSlider.disabled = true;
      tempSec.style.opacity = '0.4';
    }
  }

  // Light intensity slider
  const liSlider = document.getElementById('light-intensity-slider');
  const liVal    = document.getElementById('light-intensity-val');
  if (liSlider && liVal) {
    liSlider.value = light.intensity;
    liVal.textContent = light.intensity;
  }

  // Sync color wheel and HEX field to current light color
  const syncColor = light.wheelColor
    || (preset ? (preset.temp !== null && light.temp ? tempToColor(light.temp) : preset.color) : null);
  if (syncColor) setHexField(syncColor);
  setTimeout(() => updateColorWheelFromColor(syncColor), 10);
}

function onLightPresetChange(presetId) {
  const z = ZONES[selectedZone];
  z.light.preset = presetId;
  z.light.wheelColor = null; // clear custom wheel colour so swatch shows original
  const p = LIGHT_PRESETS.find(lp => lp.id === presetId);
  if (p && p.temp !== null) z.light.temp = p.temp;
  markZoneChanged();
  renderLightingPanel(selectedZone);
  updateLightOverlay(selectedZone);
  renderPreview();
  const col = (p && p.temp !== null && z.light.temp) ? tempToColor(z.light.temp) : (p ? p.color : null);
  if (col) {
    setHexField(col);
    setTimeout(() => updateColorWheelFromColor(col), 10);
  }
}

// Map Kelvin value to an approximate hex colour for overlay/preview
function tempToColor(k) {
  k = parseInt(k, 10);
  if (k <= 2700) return '#FF9B3E';
  if (k <= 3000) return '#FFB347';
  if (k <= 3500) return '#FFD080';
  if (k <= 4000) return '#FFE5B4';
  if (k <= 4500) return '#FFF0D8';
  if (k <= 5000) return '#E8EFFF';
  if (k <= 5500) return '#D0E4FF';
  return '#C8DCFF';
}

function onLightTempChange(val) {
  ZONES[selectedZone].light.temp = parseInt(val, 10);
  document.getElementById('light-temp-val').textContent = val + 'K';
  markZoneChanged();
  updateLightOverlay(selectedZone);
  renderPreview();
}

function onLightIntensityChange(val) {
  ZONES[selectedZone].light.intensity = parseInt(val, 10);
  document.getElementById('light-intensity-val').textContent = val;
  markZoneChanged();
  updateLightOverlay(selectedZone);
  renderPreview();
}

function onFixtureToggle(fixtureId) {
  const z = ZONES[selectedZone];
  z.light.fixtures[fixtureId] = !z.light.fixtures[fixtureId];
  markZoneChanged();
  renderLightingPanel(selectedZone);
}

function updateLightOverlay(zoneId) {
  const z      = ZONES[zoneId];
  const light  = z.light;
  const preset = LIGHT_PRESETS.find(p => p.id === light.preset);
  const rect   = currentFloorplan === 'popup'
    ? document.getElementById('pu-light-' + zoneId)
    : document.getElementById('light-' + zoneId);
  if (!rect) return;

  if (light.preset === 'off') {
    rect.setAttribute('fill-opacity', '0');
    return;
  }

  // Use wheel-picked colour if set, else temperature-derived, else preset colour
  const color = light.wheelColor
    ? light.wheelColor
    : (preset && preset.temp !== null && light.temp)
      ? tempToColor(light.temp)
      : (preset ? preset.color : '#ffffff');
  const opacity = (light.intensity / 100) * 0.72;
  rect.setAttribute('fill', color);
  rect.setAttribute('fill-opacity', opacity.toFixed(2));
}

function refreshAllLightOverlays() {
  Object.keys(ZONES).forEach(zid => updateLightOverlay(zid));
}

// ── COLOR WHEEL ───────────────────────────────────────────────────────────────
let colorWheelInitialized = false;
let colorWheelDragging    = false;

function setHexField(hex) {
  const el = document.getElementById('light-hex-input');
  if (el) el.value = hex.replace('#', '').toUpperCase();
}

function onHexInputCommit(val) {
  val = val.trim().replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(val)) return; // ignore invalid
  const hex = '#' + val.toUpperCase();
  const z = ZONES[selectedZone];
  if (!z) return;
  z.light.wheelColor = hex;
  // tint selected preset swatch
  const sel = document.querySelector('.light-preset-grid .light-swatch.selected');
  if (sel) sel.style.background = hex;
  markZoneChanged();
  updateLightOverlay(selectedZone);
  renderPreview();
  updateColorWheelFromColor(hex);
}

function hslToRgbArr(h, s, l) {
  s /= 100; l /= 100;
  const a = s * Math.min(l, 1 - l);
  const f = (n, k = (n + h / 30) % 12) => l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}
function hslToHex(h, s, l) {
  const [r, g, b] = hslToRgbArr(h, s, l);
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
}
function hexToRgbArr(hex) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  const n = parseInt(hex, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbToHslArr(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h *= 60;
  }
  return [h, s * 100, l * 100];
}

function drawColorWheelBase(canvas) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2;
  const imageData = ctx.createImageData(w, h);
  const data = imageData.data;
  for (let py = 0; py < h; py++) {
    for (let px = 0; px < w; px++) {
      const dx = px - cx, dy = py - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > r) continue;
      const angle = Math.atan2(dy, dx);
      const hue = ((angle * 180 / Math.PI) + 360) % 360;
      const sat = (dist / r) * 100;
      const [rr, gg, bb] = hslToRgbArr(hue, sat, 50);
      const idx = (py * w + px) * 4;
      data[idx] = rr; data[idx+1] = gg; data[idx+2] = bb; data[idx+3] = 255;
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

function drawColorWheelIndicator(canvas, hue, sat) {
  const ctx = canvas.getContext('2d');
  const cx = canvas.width / 2, cy = canvas.height / 2, r = Math.min(canvas.width, canvas.height) / 2;
  const angle = hue * Math.PI / 180;
  const dist  = (sat / 100) * r;
  const ix = cx + Math.cos(angle) * dist;
  const iy = cy + Math.sin(angle) * dist;
  ctx.beginPath(); ctx.arc(ix, iy, 7, 0, Math.PI * 2);
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2.5; ctx.stroke();
  ctx.beginPath(); ctx.arc(ix, iy, 7, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(0,0,0,0.45)'; ctx.lineWidth = 1; ctx.stroke();
}

function updateColorWheelFromColor(hexColor) {
  const canvas = document.getElementById('light-colorwheel');
  if (!canvas || !canvas.width) return;
  drawColorWheelBase(canvas);
  if (!hexColor || hexColor === '#ffffff') return;
  const [r, g, b] = hexToRgbArr(hexColor);
  const [h, s]    = rgbToHslArr(r, g, b);
  drawColorWheelIndicator(canvas, h, s);
}

function initColorWheel() {
  const canvas = document.getElementById('light-colorwheel');
  if (!canvas) return;
  const section = document.getElementById('light-colorwheel-section');
  if (!section || section.style.display === 'none') return;

  const size = canvas.parentElement.clientWidth - 24; // ctrl-section padding
  const dim  = Math.min(Math.max(size, 100), 180);
  canvas.width  = dim;
  canvas.height = dim;
  canvas.style.width  = dim + 'px';
  canvas.style.height = dim + 'px';

  drawColorWheelBase(canvas);

  // Sync indicator to current zone light color
  const z = ZONES[selectedZone];
  if (z) {
    const preset = LIGHT_PRESETS.find(p => p.id === z.light.preset);
    const color = z.light.wheelColor
      || (preset ? (preset.temp !== null && z.light.temp ? tempToColor(z.light.temp) : preset.color) : null);
    if (color) {
      const [r, g, b] = hexToRgbArr(color);
      const [h, s]    = rgbToHslArr(r, g, b);
      drawColorWheelIndicator(canvas, h, s);
    }
  }

  if (colorWheelInitialized) return; // attach event listeners only once
  colorWheelInitialized = true;

  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width  / rect.width;
    const scaleY = canvas.height / rect.height;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return [(clientX - rect.left) * scaleX, (clientY - rect.top) * scaleY];
  }

  function pickColor(e) {
    e.preventDefault();
    const [px, py] = getPos(e);
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const r  = Math.min(canvas.width, canvas.height) / 2;
    const dx = px - cx, dy = py - cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > r) return;
    const hue = ((Math.atan2(dy, dx) * 180 / Math.PI) + 360) % 360;
    const sat = (dist / r) * 100;
    const hex = hslToHex(hue, sat, 50);
    const z = ZONES[selectedZone];
    if (!z) return;
    z.light.wheelColor = hex;
    // keep z.light.preset so selected swatch stays highlighted but tinted
    markZoneChanged();
    // Tint the selected preset swatch with the picked colour
    const selectedSwatch = document.querySelector('.light-preset-grid .light-swatch.selected');
    if (selectedSwatch) selectedSwatch.style.background = hex;
    setHexField(hex);
    updateLightOverlay(selectedZone);
    renderPreview();
    drawColorWheelBase(canvas);
    drawColorWheelIndicator(canvas, hue, sat);
  }

  canvas.addEventListener('mousedown',  e => { colorWheelDragging = true;  pickColor(e); });
  canvas.addEventListener('touchstart', e => { colorWheelDragging = true;  pickColor(e); }, { passive: false });
  window.addEventListener('mousemove',  e => { if (colorWheelDragging) pickColor(e); });
  window.addEventListener('touchmove',  e => { if (colorWheelDragging) pickColor(e); }, { passive: false });
  window.addEventListener('mouseup',    () => { colorWheelDragging = false; });
  window.addEventListener('touchend',   () => { colorWheelDragging = false; });
}

// ── LIGHTS OFF / ON ───────────────────────────────────────────────────────────
let savedLightState = null;

function turnOffAllLights() {
  // Snapshot every zone's current light preset before killing them
  savedLightState = {};
  Object.keys(ZONES).forEach(zId => {
    savedLightState[zId] = {
      preset:    ZONES[zId].light.preset,
      intensity: ZONES[zId].light.intensity,
    };
    ZONES[zId].light.preset = 'off';
  });
  refreshAllLightOverlays();
  renderPreview();
  if (currentView === 'lighting' || currentView === 'combined') renderLightingPanel(selectedZone);
}

function restoreAllLights() {
  if (!savedLightState) {
    const msg = "The lights are already on — there's nothing to restore.";
    addChatMessage(msg, 'agent', 'error');
    speak(msg);
    return false;
  }
  Object.keys(savedLightState).forEach(zId => {
    if (!ZONES[zId]) return;
    ZONES[zId].light.preset    = savedLightState[zId].preset;
    ZONES[zId].light.intensity = savedLightState[zId].intensity;
  });
  savedLightState = null;
  refreshAllLightOverlays();
  renderPreview();
  if (currentView === 'lighting' || currentView === 'combined') renderLightingPanel(selectedZone);
  return true;
}

// ── BRAND PROFILE IMPORT ─────────────────────────────────────────────────────

let pendingBrandProfile = null;

function checkPendingBrand() {
  const raw = localStorage.getItem('studioBrandProfile');
  if (!raw) return;
  try {
    pendingBrandProfile = JSON.parse(raw);
    // Auto-apply immediately — no confirmation banner needed
    applyBrandProfile();
  } catch(e) { localStorage.removeItem('studioBrandProfile'); }
}

function applyBrandProfile() {
  const p = pendingBrandProfile;
  if (!p) return;

  // 1. Rebuild SVG gradient stops with full multi-stop arrays for smooth blends
  _rebuildGradientStops('gBlue',   p.gradients.blue.stops   || [p.gradients.blue.from,   p.gradients.blue.to],   0.72);
  _rebuildGradientStops('gYellow', p.gradients.yellow.stops || [p.gradients.yellow.from, p.gradients.yellow.to], 0.70);
  _rebuildGradientStops('gDark',   p.gradients.dark.stops   || [p.gradients.dark.from,   p.gradients.dark.to],   0.82);
  _rebuildGradientStops('gBrand',  p.gradients.brand.stops  || [p.gradients.brand.from,  p.colors.primary, p.colors.secondary], 0.78);

  // 2. Update GRADIENTS css strings — use stored full CSS for max smoothness, fall back to 2-stop
  GRADIENTS[0].css = p.gradients.blue.css    || `linear-gradient(155deg,${p.gradients.blue.from},${p.gradients.blue.to})`;
  GRADIENTS[1].css = p.gradients.yellow.css  || `linear-gradient(148deg,${p.gradients.yellow.from},${p.gradients.yellow.to})`;
  GRADIENTS[2].css = p.gradients.dark.css    || `linear-gradient(162deg,${p.gradients.dark.from},${p.gradients.dark.to})`;
  GRADIENTS[3].css = p.gradients.brand.css   || `linear-gradient(135deg,${p.gradients.brand.from},${p.colors.primary} 50%,${p.colors.secondary})`;
  if (p.gradients.accent) {
    GRADIENTS[4].css   = p.gradients.accent.css || `linear-gradient(135deg,${p.gradients.accent.from},${p.gradients.accent.to})`;
    GRADIENTS[4].label = p.gradients.accent.name || 'Brand Dark';
    _rebuildGradientStops('gAccenture', p.gradients.accent.stops || [p.gradients.accent.from, p.gradients.accent.to], 0.78);
  } else {
    // No explicit accent — use secondary colour so the 5th slot doesn't keep showing the previous brand's palette
    const sec = p.colors.secondary || p.colors.primary;
    const pri = p.colors.primary;
    GRADIENTS[4].css   = `linear-gradient(155deg,${sec} 0%,${pri} 60%,${p.gradients.dark.from || pri} 100%)`;
    GRADIENTS[4].label = 'Brand Warm';
    _rebuildGradientStops('gAccenture', [sec, pri, p.gradients.dark.from || pri], 0.72);
  }
  GRADIENTS[0].label = p.gradients.blue.name   || 'Brand Deep';
  GRADIENTS[1].label = p.gradients.yellow.name || 'Brand Accent';
  GRADIENTS[2].label = p.gradients.dark.name   || 'Brand Dark';
  GRADIENTS[3].label = p.gradients.brand.name  || 'Brand Hero';

  // 3. Add company to sidebar
  const key = p.name.toLowerCase().replace(/\s+/g,'_');
  COMPANIES[key] = { scene: 'workshop', anim: 'animated' };
  const compSection = document.querySelector('.sidebar-section:last-child .sidebar-section-label');
  const companiesWrap = document.getElementById('hdr-profiles-panel');
  if (companiesWrap) {
    const btn = document.createElement('button');
    btn.className = 'company-btn';
    btn.dataset.company = key;
    btn.onclick = () => applyCompany(key);
    // Build button DOM safely — p.name via textContent prevents XSS from localStorage data
    const swatch = document.createElement('span');
    swatch.className = 'company-swatch';
    // Sanitize colour values: only allow valid CSS colour strings (hex, rgb, named)
    const safeColor = (c) => /^#[0-9a-fA-F]{3,8}$|^rgb|^[a-zA-Z]+$/.test(String(c).trim()) ? String(c).trim() : '#888';
    swatch.style.background = `linear-gradient(135deg,${safeColor(p.colors.primary)},${safeColor(p.colors.secondary)})`;
    const nameNode = document.createTextNode(p.name);
    const removeBtn = document.createElement('span');
    removeBtn.className = 'edit-company-btn';
    removeBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
    removeBtn.addEventListener('click', (e) => editCompany(key, e));
    btn.appendChild(swatch);
    btn.appendChild(nameNode);
    btn.appendChild(removeBtn);
    // Insert before the "Add Profile" button
    const addBtn = companiesWrap.querySelector('.add-profile-btn');
    companiesWrap.insertBefore(btn, addBtn);
  }

  // 4. Register a default scene entry so the scenes panel is populated
  const safeColor2 = (c) => /^#[0-9a-fA-F]{3,8}$/.test(String(c).trim()) ? String(c).trim() : '#888';
  COMPANY_SCENES[key] = [
    {
      id: 'workshop',
      label: 'Brand Workshop',
      dot: `background:linear-gradient(135deg,${safeColor2(p.colors.primary)},${safeColor2(p.colors.secondary)});`,
    },
  ];

  // 5. Remap scene gradient IDs: brand.html uses 'deep'/'accent'/'hero' but control uses 'blue'/'yellow'/'brand'
  const _GRAD_REMAP = { deep:'blue', accent:'yellow', hero:'brand', dark:'dark', off:'off' };
  function _remapScene(scene) {
    if (!scene) return null;
    const out = {};
    Object.keys(scene).forEach(zId => { out[zId] = _GRAD_REMAP[scene[zId]] || scene[zId]; });
    return out;
  }

  if (p.scenes && (p.scenes.workshop || p.scenes.fullbrand)) {
    SCENES.workshop = _remapScene(p.scenes.workshop || p.scenes.fullbrand);
    if (p.scenes.welcome)      SCENES.welcome      = _remapScene(p.scenes.welcome);
    if (p.scenes.presentation) SCENES.presentation = _remapScene(p.scenes.presentation);
    if (p.scenes.afterhours)   SCENES.afterhours   = _remapScene(p.scenes.afterhours);
    if (p.scenes.show)         SCENES.show         = _remapScene(p.scenes.show);
  }

  // Update GRAD_COLORS so screen glows use the brand's actual palette
  Object.assign(GRAD_COLORS, {
    blue:   p.gradients.blue.from   || p.colors.primary,
    yellow: p.gradients.yellow.from || p.colors.secondary,
    brand:  p.colors.primary,
    dark:   p.gradients.dark.from   || p.colors.primary,
  });

  // Apply lighting scene
  if (p.lighting && p.lighting.lightScene) {
    LIGHT_SCENES.workshop = Object.fromEntries(
      Object.entries(p.lighting.lightScene).map(([k,v]) => [k, v === 'off' ? 'off' : p.lighting.preset])
    );
  }

  // 6. Land on a blank floor plan — no scene pre-applied, all zones off
  Object.keys(ZONES).forEach(zId => {
    ZONES[zId].grad = 'off';
    if (ZONES[zId].light) ZONES[zId].light.preset = 'off';
  });
  Object.values(SCREENS).forEach(sc => { sc.active = true; sc._savedGrad = null; });
  renderAllZones();
  renderAllScreens();
  refreshAllLightOverlays();
  activeCompany = key;
  activeScene   = null;
  document.querySelectorAll('.company-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.company === key);
  });
  const profileLabel = document.querySelector('#hdr-profiles .hdr-dd-label');
  if (profileLabel) profileLabel.textContent = p.name;
  const profileDdBtn = document.querySelector('#hdr-profiles .hdr-dd-btn');
  if (profileDdBtn) profileDdBtn.classList.add('has-value');
  buildCompanyScenes(key);
  buildGradGrid();
  renderRightPanel(selectedZone);
  refreshAllLightOverlays();

  localStorage.removeItem('studioBrandProfile');
  pendingBrandProfile = null;
  showToast('Brand profile applied: ' + p.name);
}

function dismissBrandBanner() {
  const banner = document.getElementById('brand-banner');
  if (banner) banner.style.display = 'none';
  document.getElementById('app').style.marginTop = '';
  localStorage.removeItem('studioBrandProfile');
  pendingBrandProfile = null;
}

// ── VOICE AGENT ──────────────────────────────────────────────────────────────

const MIC_SVG    = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" stroke-linejoin="miter"><rect x="9" y="2" width="6" height="13"/><path d="M5 10a7 7 0 0 0 14 0M12 19v3M8 22h8"/></svg>`;
const STOP_SVG   = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16"/></svg>`;
const SPEAKER_ON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>`;
const SPEAKER_OFF= `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>`;

// ── TTS ENGINE ────────────────────────────────────────────────────────────────
let ttsEnabled = false;
let ttsVoice   = null;

function initTTS() {
  function pickVoice() {
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return;
    const enUS  = voices.filter(v => /en[-_]US/i.test(v.lang));
    const enAll = voices.filter(v => /^en/i.test(v.lang));
    ttsVoice =
      enUS.find(v => /natural/i.test(v.name) && /aria|jenny|guy|davis/i.test(v.name)) ||
      enUS.find(v => /natural/i.test(v.name)) ||
      enUS.find(v => /premium|enhanced/i.test(v.name)) ||
      enUS.find(v => /microsoft/i.test(v.name) && /online/i.test(v.name)) ||
      enUS.find(v => /google/i.test(v.name)) ||
      enUS[0] || enAll[0] || voices[0];
  }
  pickVoice();
  if (speechSynthesis.onvoiceschanged !== undefined) speechSynthesis.onvoiceschanged = pickVoice;
  const btn = document.getElementById('tts-btn');
  if (btn) btn.innerHTML = SPEAKER_OFF;
}

function toggleTTS() {
  ttsEnabled = !ttsEnabled;
  const btn = document.getElementById('tts-btn');
  if (!btn) return;
  btn.innerHTML = ttsEnabled ? SPEAKER_ON : SPEAKER_OFF;
  btn.title     = ttsEnabled ? 'Disable voice responses' : 'Enable voice responses';
  btn.classList.toggle('active', ttsEnabled);
  if (!ttsEnabled) speechSynthesis.cancel();
}

function speak(text) {
  if (!ttsEnabled || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (ttsVoice) u.voice = ttsVoice;
  u.rate  = 0.93;
  u.pitch = 1.0;
  speechSynthesis.speak(u);
}

let voiceState    = 'idle'; // idle | listening | processing
let voiceRecog    = null;
let waveRaf       = null;
let wavePhase     = 0;
let feedbackTimer = null;

// ── Zone name → zone ID lookup ───────────────────────────────────────────────
// Sorted by phrase length (desc) so longer phrases match before shorter ones
const VOICE_ZONES = [
  ['main hall east', 'c'], ['main hall e',    'c'], ['hall east',      'c'], ['hall e',     'c'],
  ['main hall west', 'b'], ['main hall w',    'b'], ['main hall',      'b'], ['hall west',  'b'], ['hall w',    'b'],
  ['main upper',     'd'], ['upper hall',     'd'],
  ['studio north',   'e'], ['north studio',   'e'],
  ['studio east',    'k'], ['east studio',    'k'],
  ['office south',   'h'], ['south office',   'h'],
  ['office northeast','j'],['office ne',      'j'],
  ['office mid',     'i'], ['middle office',  'i'],
  ['tech room',      'm'], ['tech',           'm'],
  ['production',     'f'],
  ['workshop',       'g'],
  ['entrance',       'a'],
  ['annex',          'n'],
  ['lab',            'l'],
];

// ── Gradient name → gradient ID lookup ───────────────────────────────────────
const VOICE_GRADS = [
  ['accenture purple','accenture'], ['dark night', 'dark'],  ['blue deep',  'blue'],
  ['yellow warm',    'yellow'],     ['accenture',  'accenture'], ['yellow', 'yellow'],
  ['brand',          'brand'],      ['dark',       'dark'],   ['blue',   'blue'],
  ['purple',         'accenture'],  ['off',        'off'],
];

// ── Scene name lookup ─────────────────────────────────────────────────────────
const VOICE_SCENES = [
  ['breakout sessions','breakout'],['after hours','afterhours'],['afterhours','afterhours'],
  ['presentation',     'presentation'],['workshop','workshop'],['welcome','welcome'],
  ['breakout',         'breakout'],
];

// ── Company name lookup ───────────────────────────────────────────────────────
const VOICE_COMPANIES = [
  ['accenture','accenture'],['ikea','ikea'],['h&m','hm'],['hm','hm'],
];

// ── Main toggle ───────────────────────────────────────────────────────────────
function toggleVoice() {
  if (voiceState === 'idle') startListening();
  else stopListening(true);
}

function startListening() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { addChatMessage('Voice not supported — use Chrome or Edge', 'agent', 'error'); return; }

  voiceRecog = new SR();
  voiceRecog.lang = 'en-US';
  voiceRecog.interimResults = false;
  voiceRecog.maxAlternatives = 3;

  voiceRecog.onresult = (e) => {
    let result = null;
    let bestTranscript = '';
    for (let i = 0; i < e.results[0].length; i++) {
      const transcript = e.results[0][i].transcript.toLowerCase().replace(/[.,!?]/g, '').trim();
      if (!bestTranscript) bestTranscript = e.results[0][i].transcript.trim();
      result = parseVoiceCommand(transcript);
      if (result) break;
    }
    // Show what was heard as a user message
    if (bestTranscript) addChatMessage(bestTranscript, 'user');
    setVoiceState('processing');
    setTimeout(() => {
      if (result) {
        executeVoiceCommand(result);
      } else {
        const msg = "I didn't quite catch that. Try something like 'change main hall to dark night' or 'apply the workshop scene'.";
        addChatMessage(msg, 'agent', 'error');
        speak(msg);
      }
      setVoiceState('idle');
    }, 450);
  };

  voiceRecog.onerror = (e) => {
    setVoiceState('idle');
    if (e.error !== 'no-speech') addChatMessage('Error: ' + e.error, 'agent', 'error');
  };
  voiceRecog.onend = () => { if (voiceState === 'listening') setVoiceState('idle'); };

  voiceRecog.start();
  setVoiceState('listening');
}

function stopListening(cancelled) {
  if (voiceRecog) voiceRecog.stop();
  setVoiceState('idle');
  if (cancelled) addChatMessage('Cancelled', 'agent');
}

// ── Command parser ────────────────────────────────────────────────────────────
function parseVoiceCommand(t) {
  // 0. Lights off / on — keyword-based so natural phrasing always works
  //    ("turn off all the lights", "lights off", "kill the lights", etc.)
  const hasLight = t.includes('light');
  const hasOff   = t.includes(' off') || t.endsWith('off');
  const hasOn    = t.includes(' on')  || t.endsWith(' on');

  // Lights-on: "back on", "restore * light", "them * on", "light * on"
  const isLightsOn = t.includes('back on')
    || (t.includes('restore') && hasLight)
    || (t.includes('them') && hasOn)
    || (hasLight && hasOn && !hasOff);

  // Lights-off: "light * off", "kill * light"
  const isLightsOff = (hasLight && hasOff)
    || (t.includes('kill') && hasLight);

  // Check on before off so "back on" never triggers off
  if (isLightsOn)  return { type: 'lights-on' };
  if (isLightsOff) return { type: 'lights-off' };

  // 1. Company profile: "accenture profile", "activate ikea", etc.
  for (const [alias, id] of VOICE_COMPANIES) {
    if (t.includes(alias) && (t.includes('profile') || t.includes('activate') || t.includes('company'))) {
      return { type: 'company', id };
    }
  }
  // 2. Scene: "apply workshop", "switch to presentation", "after hours scene", etc.
  for (const [alias, id] of VOICE_SCENES) {
    if (t.includes(alias) && (t.includes('scene') || t.includes('apply') || t.includes('switch') || t.includes('activate') || t.includes('mode'))) {
      return { type: 'scene', id };
    }
  }
  // 3. Zone + gradient: "change main hall e to dark night"
  let foundZone = null, foundGrad = null;
  for (const [alias, id] of VOICE_ZONES) {
    if (t.includes(alias)) { foundZone = { alias, id }; break; }
  }
  for (const [alias, id] of VOICE_GRADS) {
    if (t.includes(alias)) { foundGrad = { alias, id }; break; }
  }
  if (foundZone && foundGrad) return { type: 'zone-grad', zone: foundZone, grad: foundGrad };
  // 4. All zones: "set everything to dark"
  if ((t.includes('all') || t.includes('every')) && foundGrad) {
    return { type: 'all-grad', grad: foundGrad };
  }
  // 5. Just a scene name with no keyword — low confidence, still try
  for (const [alias, id] of VOICE_SCENES) {
    if (t.includes(alias)) return { type: 'scene', id };
  }
  return null;
}

// ── Command executor ──────────────────────────────────────────────────────────
function executeVoiceCommand(cmd) {
  let msg = '';
  if (cmd.type === 'lights-off') {
    turnOffAllLights();
    msg = "I've turned off all the lights across the studio.";
    addChatMessage(msg, 'agent', 'success');
    speak(msg);
    return;
  }
  if (cmd.type === 'lights-on') {
    const restored = restoreAllLights();
    if (restored) {
      msg = "The lights are back on — all zones have been restored to their previous settings.";
      addChatMessage(msg, 'agent', 'success');
      speak(msg);
    }
    return;
  }
  if (cmd.type === 'zone-grad') {
    const zoneId = cmd.zone.id;
    const gradId = cmd.grad.id;
    if (!ZONES[zoneId]) {
      msg = "I couldn't find that zone — could you try again?";
      addChatMessage(msg, 'agent', 'error'); speak(msg); return;
    }
    selectZone(zoneId);
    onGradChange(gradId);
    const zoneName  = ZONES[zoneId].name;
    const gradLabel = GRADIENTS.find(g => g.id === gradId)?.label || gradId;
    msg = `Done — I've changed ${zoneName} to ${gradLabel}.`;
    addChatMessage(msg, 'agent', 'success');
    speak(msg);
  } else if (cmd.type === 'all-grad') {
    const gradId = cmd.grad.id;
    Object.keys(ZONES).forEach(zId => { ZONES[zId].grad = gradId; });
    renderAllZones(); renderAllScreens(); renderRightPanel(); clearSceneHighlight();
    const gradLabel = GRADIENTS.find(g => g.id === gradId)?.label || gradId;
    msg = `Got it — I've switched all zones to ${gradLabel}.`;
    addChatMessage(msg, 'agent', 'success');
    speak(msg);
  } else if (cmd.type === 'scene') {
    applyScene(cmd.id);
    const labels = { welcome:'Welcome', workshop:'Workshop', breakout:'Breakout Sessions', presentation:'Presentation', afterhours:'After Hours', accenture:'Demo 12 June' };
    msg = `I've applied the ${labels[cmd.id] || cmd.id} scene to the studio.`;
    addChatMessage(msg, 'agent', 'success');
    speak(msg);
  } else if (cmd.type === 'company') {
    applyCompany(cmd.id);
    const names = { ikea:'IKEA', hm:'H&M', accenture:'Accenture' };
    msg = `The ${names[cmd.id] || cmd.id} brand profile is now active across the studio.`;
    addChatMessage(msg, 'agent', 'success');
    speak(msg);
  }
}

// ── STUDIO AGENT ─────────────────────────────────────────────────────────────
// States: idle | await_brand | await_scene | active | mode2
let chatFlowState = 'idle';
let chatFlowData  = {};

// ── Typing indicator ────────────────────────────────────────────────────────
function showTyping() {
  hideTyping();
  var feed = document.getElementById('chat-messages');
  if (!feed) return;
  var el = document.createElement('div');
  el.id = 'chat-typing-indicator';
  el.className = 'chat-message agent chat-typing';
  el.innerHTML = '<div class="msg-sender">Agent</div><div class="msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
}
function hideTyping() { var el = document.getElementById('chat-typing-indicator'); if (el) el.remove(); }

function agentSay(text, delay, style) {
  showTyping();
  return new Promise(function(resolve) {
    setTimeout(function() {
      hideTyping();
      addChatMessage(text, 'agent', style || '');
      speak(text);
      resolve();
    }, delay || 520);
  });
}

// ── Scene card ────────────────────────────────────────────────────────────────
function addSceneCard(sceneId) {
  var feed = document.getElementById('chat-messages');
  if (!feed) return;
  var labels = { welcome:'Welcome', workshop:'Workshop', breakout:'Breakout Sessions', presentation:'Presentation', afterhours:'After Hours', accenture:'Demo 12 June' };
  var activeCount = Object.values(ZONES).filter(function(z){ return z.grad !== 'off'; }).length;
  var swatches    = GRADIENTS.slice(0,4).map(function(g){ return '<div class="asc-swatch" style="background:' + g.css + '"></div>'; }).join('');
  var msg = document.createElement('div');
  msg.className = 'chat-message agent';
  msg.innerHTML = '<div class="msg-sender">Agent</div>';
  var card = document.createElement('div');
  card.className = 'agent-scene-card';
  card.innerHTML =
    '<div class="asc-header"><div class="asc-title">' + (labels[sceneId]||sceneId) + '</div>' +
    '<div class="asc-sub">' + activeCount + ' zones active</div></div>' +
    '<div class="asc-swatches">' + swatches + '</div>' +
    '<div class="asc-actions">' +
      '<button class="asc-btn primary" onclick="chatConfirm()">Looks great ✓</button>' +
      '<button class="asc-btn" onclick="chatTryAnother()">Try another</button>' +
    '</div>';
  msg.appendChild(card);
  feed.appendChild(msg);
  feed.scrollTop = feed.scrollHeight;
}

function chatConfirm() {
  document.querySelectorAll('.asc-actions').forEach(function(el){ el.remove(); });
  chatFlowState = 'active';
  agentSay('All set — studio is live. Talk to me any time.', 320, 'success');
}

function chatTryAnother() {
  document.querySelectorAll('.asc-actions').forEach(function(el){ el.remove(); });
  chatFlowState = 'await_scene';
  agentSay('Which scene? Try: Welcome, Workshop, Presentation, Breakout, or After Hours.', 320);
}

// ── Brand detection ───────────────────────────────────────────────────────────
function detectBrand(t) {
  if (/\baccenture\b/.test(t)) return 'accenture';
  if (/\bikea\b/.test(t))      return 'ikea';
  if (/\bh\s*[&+]\s*m\b|\bhm\b/.test(t)) return 'hm';
  return null;
}

// ── Colour helpers ────────────────────────────────────────────────────────────
function _hexToRgb(hex) {
  hex = hex.replace('#',''); if (hex.length===3) hex=hex.split('').map(function(c){return c+c;}).join('');
  var n=parseInt(hex,16); return [(n>>16)&255,(n>>8)&255,n&255];
}
function _rgbToHex(r,g,b) { return '#'+[r,g,b].map(function(v){return Math.round(Math.max(0,Math.min(255,v))).toString(16).padStart(2,'0');}).join(''); }
function _lighten(hex,amt) { var c=_hexToRgb(hex); return _rgbToHex(c[0]+(255-c[0])*amt,c[1]+(255-c[1])*amt,c[2]+(255-c[2])*amt); }
function _darken(hex,amt)  { var c=_hexToRgb(hex); return _rgbToHex(c[0]*(1-amt),c[1]*(1-amt),c[2]*(1-amt)); }


// ── Conversation router ───────────────────────────────────────────────────────
function processChatFlow(t) {

  if (chatFlowState==='idle') {
    if (parseVoiceCommand(t)) return false;
    var brand=detectBrand(t);
    if (brand) {
      var names={ikea:'IKEA',hm:'H&M',accenture:'Accenture'};
      chatFlowState='await_scene';
      agentSay('Got it — loading '+names[brand]+' now…',500).then(function(){
        applyCompany(brand);
        setTimeout(function(){ agentSay(names[brand]+' is live.',650).then(function(){ addSceneCard(COMPANIES[brand].scene); }); },700);
      });
      return true;
    }
    chatFlowState='await_brand';
    agentSay("Who's the client? Say a brand name — IKEA, H&M or Accenture.",620);
    return true;
  }

  if (chatFlowState==='await_brand') {
    var brand=detectBrand(t);
    if (brand) {
      var names={ikea:'IKEA',hm:'H&M',accenture:'Accenture'};
      chatFlowState='await_scene';
      agentSay(names[brand]+' — on it…',480).then(function(){
        applyCompany(brand);
        setTimeout(function(){ agentSay(names[brand]+' is live.',650).then(function(){ addSceneCard(COMPANIES[brand].scene); }); },700);
      });
      return true;
    }
    if (/back|cancel|reset/.test(t)) { chatFlowState='idle'; agentSay("No problem. Just tell me when you're ready.",300); return true; }
    agentSay("I don't recognise that brand — try IKEA, H&M or Accenture.",400,'error');
    return true;
  }

  if (chatFlowState==='await_scene') {
    if (/great|good|perfect|yes|ok|love|done/.test(t)) { chatConfirm(); return true; }
    if (/another|change|different|no|switch/.test(t))  { chatTryAnother(); return true; }
    for (var i=0;i<VOICE_SCENES.length;i++) {
      if (t.includes(VOICE_SCENES[i][0])) {
        var sid=VOICE_SCENES[i][1];
        applyScene(sid);
        var sl={welcome:'Welcome',workshop:'Workshop',breakout:'Breakout Sessions',presentation:'Presentation',afterhours:'After Hours'};
        agentSay('Switched to '+(sl[sid]||sid)+'. How does this look?',420).then(function(){ addSceneCard(sid); });
        return true;
      }
    }
    return false;
  }

  if (chatFlowState==='active') {
    if (/new setup|start over|reset/.test(t)) {
      chatFlowState='idle';
      agentSay("Ready. Just tell me the brand — IKEA, H&M or Accenture.",380);
      return true;
    }
    return false;
  }

  return false;
}

function initAgent() {
  setTimeout(function(){ agentSay('Studio ready. Tell me who the client is, or tap "Start Studio Setup".', 700); }, 400);
}


// ── Chat helpers ──────────────────────────────────────────────────────────────
function addChatMessage(text, role, style) {
  const feed = document.getElementById('chat-messages');
  if (!feed) return;
  const msg    = document.createElement('div');
  msg.className = `chat-message ${role}`;
  const sender = document.createElement('div');
  sender.className = 'msg-sender';
  sender.textContent = role === 'user' ? 'You' : 'Agent';
  const bubble = document.createElement('div');
  bubble.className = `msg-bubble${style ? ' ' + style : ''}`;
  bubble.textContent = text;
  msg.appendChild(sender);
  msg.appendChild(bubble);
  feed.appendChild(msg);
  feed.scrollTop = feed.scrollHeight;
}

function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  addChatMessage(text, 'user');
  input.value = '';
  document.getElementById('chat-send').disabled = true;

  const t = text.toLowerCase().replace(/[.,!?]/g, '').trim();

  // Route through conversation flow first
  const handled = processChatFlow(t);
  if (!handled) {
    // Fallback: freeform voice commands
    setTimeout(function() {
      const result = parseVoiceCommand(t);
      if (result) {
        executeVoiceCommand(result);
      } else {
        // Context-aware fallback hint
        if (chatFlowState === 'idle') {
          agentSay("I can run direct commands like 'apply workshop scene' or 'turn lights off'. Or just tell me about your session and I'll set things up.", 400);
        } else if (chatFlowState === 'await_brand') {
          agentSay("I need a brand name — try 'IKEA', 'Accenture', or say 'new client' to build one from scratch.", 350, 'error');
        } else {
          agentSay("I didn't quite get that. Try a scene name, a zone colour, or pick one of the options above.", 350, 'error');
        }
      }
    }, 320);
  }
}

// ── UI state ──────────────────────────────────────────────────────────────────
function setVoiceState(state) {
  voiceState = state;
  const btn    = document.getElementById('voice-btn');
  const status = document.getElementById('voice-status');
  if (!btn) return;

  btn.classList.remove('listening', 'processing');
  cancelAnimationFrame(waveRaf);

  if (state === 'idle') {
    btn.innerHTML = MIC_SVG;
    btn.title = 'Press to speak';
    if (status) status.textContent = '';
    drawWave();
  } else if (state === 'listening') {
    btn.classList.add('listening');
    btn.innerHTML = STOP_SVG;
    btn.title = 'Stop listening';
    if (status) status.textContent = 'Listening…';
    drawWave();
  } else if (state === 'processing') {
    btn.classList.add('processing');
    btn.innerHTML = MIC_SVG;
    btn.title = 'Processing…';
    if (status) status.textContent = 'Processing…';
    drawWave();
  }
}

// ── showVoiceFeedback — kept for backwards compat, routes to chat ─────────────
function showVoiceFeedback(msg, isError) {
  addChatMessage(msg, 'agent', isError ? 'error' : 'success');
}

// ── Waveform canvas ───────────────────────────────────────────────────────────
function drawWave() {
  const canvas = document.getElementById('voice-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const isLight = document.documentElement.classList.contains('light');

  function frame() {
    ctx.clearRect(0, 0, W, H);
    wavePhase += voiceState === 'listening' ? 0.065 : voiceState === 'processing' ? 0.038 : 0.012;

    const lines = voiceState === 'listening'
      ? [
          { amp: 10, freq: 2.4, phOff: 0,    alpha: 0.85, width: 1.5 },
          { amp:  7, freq: 3.8, phOff: 0.6,  alpha: 0.50, width: 1.0 },
          { amp: 13, freq: 1.6, phOff: 1.2,  alpha: 0.30, width: 1.0 },
          { amp:  5, freq: 5.0, phOff: 1.8,  alpha: 0.20, width: 0.8 },
        ]
      : voiceState === 'processing'
      ? [
          { amp: 5 + Math.sin(wavePhase * 4) * 3, freq: 3.2, phOff: 0,   alpha: 0.70, width: 1.5 },
          { amp: 3 + Math.sin(wavePhase * 5) * 2, freq: 4.8, phOff: 0.8, alpha: 0.40, width: 1.0 },
          { amp: 4 + Math.cos(wavePhase * 3) * 2, freq: 2.0, phOff: 1.6, alpha: 0.25, width: 1.0 },
        ]
      : /* idle */ [
          { amp: 2.5, freq: 2.0, phOff: 0,   alpha: 0.30, width: 1.0 },
          { amp: 1.5, freq: 3.5, phOff: 0.8, alpha: 0.18, width: 0.8 },
          { amp: 2.0, freq: 1.2, phOff: 1.5, alpha: 0.12, width: 0.8 },
        ];

    lines.forEach(ln => {
      ctx.beginPath();
      const baseAlpha = isLight ? ln.alpha * 0.7 : ln.alpha;
      ctx.strokeStyle = `rgba(161,0,255,${baseAlpha})`;
      ctx.lineWidth = ln.width;
      for (let x = 0; x <= W; x++) {
        const y = H / 2 + Math.sin((x / W) * Math.PI * ln.freq + wavePhase + ln.phOff) * ln.amp;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    });

    waveRaf = requestAnimationFrame(frame);
  }
  frame();
}

function initVoice() {
  const btn = document.getElementById('voice-btn');
  if (btn) btn.innerHTML = MIC_SVG;
  // Allow Enter key in chat input
  const input = document.getElementById('chat-input');
  if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') sendChatMessage(); });
  drawWave();
}

// ── COLLAPSIBLE SECTIONS ──────────────────────────────────────────────────────

function toggleSection(sectionId) {
  const section = document.getElementById(sectionId);
  if (section) section.classList.toggle('section-collapsed');
}

function toggleChatPanel() {
  const app = document.getElementById('app');
  const collapsed = app.classList.toggle('chat-collapsed');
  const headerBtn = document.getElementById('chat-panel-toggle');
  if (headerBtn) headerBtn.title = collapsed ? 'Open agent panel' : 'Close agent panel';
  // Redraw waveform after transition so it fills the correct canvas width
  setTimeout(() => { cancelAnimationFrame(waveRaf); drawWave(); }, 280);
}

// ── BOOT ──────────────────────────────────────────────────────────────────────

document.body.classList.add('view-screens');
init();
checkPendingBrand();
initVoice();
initTTS();
initAgent();
