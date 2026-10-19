// =====================================================================
//  Echte Requisiten (Poly Haven, CC0): Felsen, Statuen, Klimageräte,
//  Fässer, Kisten ... als InstancedMesh (1 Draw-Call pro Teilmesh).
//  Fehlt ein Modell, bleibt die prozedurale Kulisse unverändert.
// =====================================================================
const PROP_IDS = ['rock_face_01', 'rock_moss_set_01', 'shrub_02', 'lion_head', 'gothic_statue', 'exterior_aircon_unit', 'Barrel_01', 'wooden_crate_02',
  'modular_airduct_circular_01', 'modular_industrial_pipes_01', 'security_light', 'barrel_stove', 'old_tyre', 'stone_fire_pit', 'metal_trash_can', 'trashbag',
  'large_castle_door', 'street_lamp_01'];
const PROP = {};
for (const id of PROP_IDS) PROP[id] = Assets.need('model', 'models/' + id + '/' + id + '.gltf');
const propCache = new Map();

function propsHave(id) { return !!(PROP[id] && Assets.gltf(PROP[id])); }

// Quelle eines Modells (optional nur ein benannter Knoten): Teilmeshes mit Matrix,
// so verschoben, dass die Unterseite auf y=0 liegt und x/z mittig sind.
function propSrc(id, node) {
  const key = id + '|' + (node || '');
  if (propCache.has(key)) return propCache.get(key);
  const g = PROP[id] && Assets.gltf(PROP[id]);
  let src = null;
  if (g) {
    g.scene.updateMatrixWorld(true);
    const base = node ? g.scene.getObjectByName(node) : g.scene;
    if (base) {
      const inv = new THREE.Matrix4().copy(base.matrixWorld).invert(), parts = [], box = new THREE.Box3();
      base.traverse((o) => {
        if (!o.isMesh) return;
        const m = new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        box.union(o.geometry.boundingBox.clone().applyMatrix4(m));
        parts.push({ geo: o.geometry, mat: o.material, m });
      });
      if (parts.length) {
        const c = box.getCenter(new V3()), off = new THREE.Matrix4().makeTranslation(-c.x, -box.min.y, -c.z);
        parts.forEach((p) => p.m.premultiply(off));
        src = { parts, size: box.getSize(new V3()) };
      }
    }
  }
  propCache.set(key, src);
  return src;
}

// Platziert viele Kopien: list = [[x, y, z, ry, s, rx, rz], ...]; s = Zahl oder [sx, sy, sz]
const _pM = new THREE.Matrix4(), _pQ = new THREE.Quaternion(), _pE = new THREE.Euler(), _pP = new V3(), _pS = new V3(), _pT = new THREE.Matrix4();
function propPlace(parent, id, node, list, opt = {}) {
  const S = propSrc(id, node);
  if (!S || !list.length) return null;
  const out = [];
  for (const p of S.parts) {
    const im = new THREE.InstancedMesh(p.geo, p.mat, list.length);
    list.forEach(([x, y, z, ry = 0, s = 1, rx = 0, rz = 0], i) => {
      _pE.set(rx, ry, rz); _pQ.setFromEuler(_pE);
      if (Array.isArray(s)) _pS.set(s[0], s[1], s[2]); else _pS.set(s, s, s);
      _pT.compose(_pP.set(x, y, z), _pQ, _pS); _pM.multiplyMatrices(_pT, p.m); im.setMatrixAt(i, _pM);
    });
    im.castShadow = opt.shadow !== false; im.receiveShadow = true;
    im.computeBoundingSphere(); im.computeBoundingBox && im.computeBoundingBox();
    parent.add(im); out.push(im);
  }
  return out;
}
// Skalierung auf Zielhöhe (Meter)
function propH(id, node, h) { const S = propSrc(id, node); return S ? h / S.size.y : 1; }
// Leuchtende Teile (Glühbirnen/Glas) eines Modells zum Glühen bringen
function propGlow(id, test, color, inten) {
  const S = propSrc(id); if (!S) return;
  for (const p of S.parts) {
    const ms = Array.isArray(p.mat) ? p.mat : [p.mat];
    for (const m of ms) if (test.test(m.name || '') && m.emissive && !m.userData.glowSet) { m.emissive.set(color); m.emissiveIntensity = inten; m.userData.glowSet = true; }
  }
}

function propsForArena(id, root, anim, q) {
  const perf = q === 'performance';
  const thin = (l) => (perf ? l.filter((_, i) => i % 2 === 0) : l);
  const R = seeded(0x9e0b + id.length * 7);
  const MOSS = ['rock_moss_set_01_rock01', 'rock_moss_set_01_rock02', 'rock_moss_set_01_rock03', 'rock_moss_set_01_rock04', 'rock_moss_set_01_rock05', 'rock_moss_set_01_rock06'];
  const SHRUB = ['shrub_02_a', 'shrub_02_b', 'shrub_02_c', 'shrub_02_d'];
  const spread = (nodes, pts) => nodes.forEach((n, k) => { const l = pts.filter((_, i) => i % nodes.length === k); if (l.length) propPlace(root, ...n, l); });
  const embers = (x, y, z, r) => anim.push(() => { if (Math.random() < 0.45) FX.emberAt(new V3(x + rand(-r, r), y, z + rand(-r, r))); });
  if (id === 'templeGarden') {
    // Wächterlöwen auf den Statuensockeln (Sockeloberkante y=1.95)
    const lh = propH('lion_head', null, 2.3);
    propPlace(root, 'lion_head', null, [[-9.5, 1.95, -12, 0.18, lh], [9.5, 1.95, -12, -0.18, lh]]);
    // bemooste Findlinge im Garten
    const rocks = thin([[-13.2, 0, -8.2, 0.4, 0.9], [13.6, 0, -9.0, 2.1, 1.0], [-18.4, 0, -6.4, 1.3, 1.15], [18.8, 0, -5.2, 4.2, 1.1], [-7.6, 0, -20.5, 0.7, 0.8], [8.4, 0, -21.2, 2.6, 0.85],
      [-14.5, 0, -28.5, 3.3, 1.4], [15.2, 0, -29.5, 5.1, 1.35], [-6.3, 0, -38.5, 1.9, 1.1], [6.9, 0, -39.2, 0.2, 1.0], [-24, 0, -22, 2.4, 1.8], [25, 0, -24, 1.1, 1.9]]);
    spread(MOSS.map((n) => ['rock_moss_set_01', n]), rocks.map(([x, y, z, ry, s]) => [x, y - 0.12 * s, z, ry, s]));
    // Felswände als Kulisse links/rechts hinter dem Garten
    const cliffs = [[-44, -0.3, -36, 0.9, 3.4], [46, -0.3, -40, -0.8, 3.6], [-30, -0.4, -78, 0.2, 5.5], [33, -0.4, -84, -0.3, 5.8], [-70, -0.5, -60, 1.3, 6], [72, -0.5, -66, -1.4, 6.2]];
    propPlace(root, 'rock_face_01', null, perf ? cliffs.slice(0, 4) : cliffs, { shadow: false });
    // Sträucher um Felsen und Wege
    const sh = [];
    for (const [x, , z, , s] of rocks) for (let k = 0; k < 2; k++) sh.push([x + rand(-1.6, 1.6) * s, 0, z + rand(0.6, 1.6) * s, R() * TAU, 0.8 + R() * 0.4]);
    for (const sx of [-1, 1]) for (let k = 0; k < 6; k++) sh.push([sx * (4.2 + k * 2.6), 0, -15.4 + (k % 2) * 0.3, R() * TAU, 0.7 + R() * 0.3]);
    spread(SHRUB.map((n) => ['shrub_02', n]), thin(sh));
  } else if (id === 'rainRooftop') {
    const ac = propH('exterior_aircon_unit', null, 1.65);
    propPlace(root, 'exterior_aircon_unit', null, [[-15.6, 0, -9.55, 0, ac], [-14.0, 0, -9.55, 0, ac], [-7.5, 1.6, -7.1, 0.12, ac * 0.85], [7.2, 2.2, -7.8, -0.1, ac * 0.85], [16.5, 0, -6.4, -1.4, ac], [3.2, 0, -9.55, 0, ac]]);
    const barrel = propH('Barrel_01', null, 0.88);
    propPlace(root, 'Barrel_01', null, thin([[8.7, 0, -4.6, 0.3, barrel], [9.4, 0, -5.2, 1.2, barrel], [8.3, 0, -5.6, 2.0, barrel], [-10.0, 0, -4.8, 0.4, barrel], [-10.7, 0, -4.2, 2.4, barrel], [10.6, 0.3, -3.9, 0.4, barrel, Math.PI / 2, 0]]));
    propPlace(root, 'wooden_crate_02', null, thin([[-8.6, 0, -3.4, 1.62, 1.1], [-8.7, 0.48, -3.5, 1.5, 1.1], [-7.4, 0, -4.6, 0.2, 1.1], [11.6, 0, -3.0, 1.2, 1.1], [12.4, 0, -4.2, 0.3, 1.1]]));
    propPlace(root, 'old_tyre', null, [[9.9, 0.08, -3.2, 0, 1, Math.PI / 2, 0], [9.9, 0.25, -3.2, 0.4, 1, Math.PI / 2, 0], [-11.4, 0.08, -3.0, 0, 1, Math.PI / 2, 0]]);
    propPlace(root, 'trashbag', null, thin([[-9.6, 0, -2.6, 0.5, 1], [-7.0, 0, -3.3, 2.2, 0.9], [12.9, 0, -2.6, 1.4, 1]]));
    // Lüftungskanal entlang der Brüstung + Lüfter
    const d = 1.45, duct = [];
    for (let k = 0; k < 4; k++) duct.push([-5.6 + k * 2.06, 0.1, -9.65, Math.PI / 2, d]);
    propPlace(root, 'modular_airduct_circular_01', 'modular_airduct_circular_triple', duct);
    propPlace(root, 'modular_airduct_circular_01', 'modular_airduct_circular_fan', [[1.72, 0, -9.65, Math.PI / 2, d]]);
    // Rohre vom Wassertank in den Boden
    propPlace(root, 'modular_industrial_pipes_01', 'modular_industrial_pipes_01_pipe02', [[11.0, 0, -9.6, 0, [1.6, 1.6, 1.6]], [11.5, 0, -9.6, 0, [1.6, 1.3, 1.6]], [15.2, 0, -9.6, 0, [1.6, 1.6, 1.6]]]);
    // Strahler auf den Klimakästen
    propGlow('security_light', /bulb|glass/i, 0xfff0d0, 1.6);
    propPlace(root, 'security_light', null, [[-7.5, 0.7, -5.74, 0, 1.3], [7.0, 1.2, -6.24, 0, 1.3]], { shadow: false });
  } else if (id === 'foundry') {
    const barrel = propH('Barrel_01', null, 0.88);
    propPlace(root, 'Barrel_01', null, thin([[-13.5, 0, -6.2, 0.3, barrel], [-12.8, 0, -6.9, 1.2, barrel], [-14.2, 0, -7.0, 2.5, barrel], [13.2, 0, -6.5, 0.6, barrel], [14.0, 0, -5.8, 2.2, barrel], [9.5, 0.3, -5.0, 1.1, barrel, Math.PI / 2, 0]]));
    propPlace(root, 'barrel_stove', null, [[-16.5, 0, -4.2, 0.4, 1.1], [16.2, 0, -3.6, 2.0, 1.1]]);
    embers(-16.5, 0.95, -4.2, 0.25); embers(16.2, 0.95, -3.6, 0.25);
    propPlace(root, 'wooden_crate_02', null, thin([[-10.0, 0, -5.8, 0.1, 1.15], [-10.1, 0.5, -5.85, 0.25, 1.15], [11.5, 0, -4.6, 1.5, 1.15], [-18.5, 0, -6.8, 1.6, 1.2], [18.6, 0, -7.0, 0.1, 1.2]]));
    propPlace(root, 'old_tyre', null, [[12.0, 0.08, -3.3, 0, 1, Math.PI / 2, 0], [12.0, 0.25, -3.3, 0.7, 1, Math.PI / 2, 0], [-8.8, 0.3, -4.2, 0.9, 1, 0, 0]]);
    // senkrechte Rohre an den Hallenstützen
    const pp = [];
    for (let k = 0; k < 6; k++) { const x = -20 + k * 8; pp.push([x + 0.65, 0, -13.2, 0, [1.4, 3.4, 1.4]], [x + 0.65, 6.65, -13.2, 0, [1.4, 3.4, 1.4]]); }
    propPlace(root, 'modular_industrial_pipes_01', 'modular_industrial_pipes_01_pipe02', thin(pp));
    propGlow('security_light', /bulb|glass/i, 0xffd8a0, 1.6);
    propPlace(root, 'security_light', null, [[-12, 5.5, -12.74, 0, 1.4], [4, 5.5, -12.74, 0, 1.4]], { shadow: false });
  } else if (id === 'burningSquare') {
    propPlace(root, 'gothic_statue', null, [[-5.2, 0, -18.7, 0.25, propH('gothic_statue', null, 3.1)], [5.2, 0, -18.7, -0.25, propH('gothic_statue', null, 3.1)]]);
    propPlace(root, 'stone_fire_pit', null, [[-15.5, 0, -12.5, 0.3, 1.3], [6.0, 0, -15.0, 1.9, 1.2]]);
    embers(-15.5, 0.35, -12.5, 0.7); embers(6.0, 0.35, -15.0, 0.6);
    const barrel = propH('Barrel_01', null, 0.88);
    propPlace(root, 'Barrel_01', null, thin([[-12.5, 0, -4.2, 0.3, barrel], [-13.2, 0, -4.8, 1.3, barrel], [12.4, 0.3, -6.0, 0.9, barrel, Math.PI / 2, 0], [16.5, 0, -8.5, 2.2, barrel]]));
    propPlace(root, 'trashbag', null, thin([[-11.8, 0, -3.2, 0.4, 1], [13.6, 0, -3.0, 1.7, 1.1], [-8.0, 0, -9.0, 2.6, 1]]));
    propGlow('street_lamp_01', /bulb|glass/i, 0xffc070, 5);
    const sl = propH('street_lamp_01', null, 4.4);
    propPlace(root, 'street_lamp_01', null, [[-17.5, 0, -5.5, 0.4, sl], [17.5, 0, -6.5, -0.5, sl], [-9.5, 0, -16.5, 0.2, sl], [9.5, 0, -16.5, -0.2, sl]]);
  } else if (id === 'subway') {
    const tc = [];
    for (const x of [-12, 0, 12]) tc.push([x + 0.95, 0, -5.6, R() * TAU, 1.05]);
    tc.push([-17.0, 0, -12.6, 0.3, 1.05]);
    propPlace(root, 'metal_trash_can', null, tc);
    propPlace(root, 'trashbag', null, thin([[-11.3, 0, -4.7, 0.8, 1], [1.7, 0, -5.0, 2.1, 0.9], [-16.2, 0, -12.2, 1.4, 1.1], [13.6, 0, -4.9, 0.2, 1]]));
    propPlace(root, 'wooden_crate_02', null, [[-13.8, 0, -11.8, 0.1, 1.1], [-13.8, 0.48, -11.85, 0.2, 1.1]]);
    propGlow('security_light', /bulb|glass/i, 0xe8fff8, 1.6);
    propPlace(root, 'security_light', null, [[-15.0, 4.6, -13.24, 0, 1.4], [-8.0, 4.6, -13.24, 0, 1.4]], { shadow: false });
  } else if (id === 'bloodTower' || id === 'riftRealm') {
    const gs = propH('gothic_statue', null, id === 'bloodTower' ? 3.4 : 2.9);
    if (id === 'bloodTower') {
      propPlace(root, 'gothic_statue', null, thin([[-6, 0, -9.3, 0.1, gs], [6, 0, -9.3, -0.1, gs], [-12, 0, -9.3, 0.2, gs], [12, 0, -9.3, -0.2, gs]]));
      const lh = propH('lion_head', null, 1.1);
      propPlace(root, 'lion_head', null, [[-2.3, 1.5, -12.6, 0.15, lh], [2.3, 1.5, -12.6, -0.15, lh]]);
    } else {
      propPlace(root, 'gothic_statue', null, [[-9.5, 0, -6.8, 0.5, gs], [9.8, 0, -7.4, -0.4, gs]]);
      propPlace(root, 'large_castle_door', null, [[0, 0, -13.5, 0, propH('large_castle_door', null, 5.6)]]);
      // schwebende Felsbrocken im Riss
      const fl = [];
      for (let k = 0; k < (perf ? 5 : 10); k++) { const sx = k % 2 ? 1 : -1; fl.push([sx * (8 + R() * 22), 2 + R() * 14, -16 - R() * 34, R() * TAU, 0.8 + R() * 1.6, (R() - 0.5) * 0.9, (R() - 0.5) * 0.9]); }
      const flo = propPlace(root, 'rock_face_01', null, fl, { shadow: false });
      if (flo) { let t = 0; anim.push((dt) => { t += dt; for (const m of flo) m.position.y = Math.sin(t * 0.5) * 0.4; }); }
    }
  }
}

// Freie Stadt: Mülltonnen an Laternen, Klimageräte auf Dächern, Fässer/Kisten im Hafen.
// In 300-m-Kacheln instanziert, damit Frustum-Culling greift.
function propsForCity(city, tops, half, quality) {
  if (quality === 'performance') return;
  const R = seeded(0x51ee7), rich = quality === 'ultra';
  const tiles = new Map();
  const add = (k, p) => { const t = Math.floor((p[0] + half) / 300) + ',' + Math.floor((p[2] + half) / 300), key = k + '|' + t; if (!tiles.has(key)) tiles.set(key, []); tiles.get(key).push(p); };
  // Mülltonnen + Müllsäcke an Laternenmasten (Gehweg c±8.5)
  for (let k = 0; k <= CITY.blocks; k++) {
    const c = -half + k * CITY.pitch;
    for (let t = -half + 20; t < half; t += 50) for (const sd of [-1, 1]) {
      if (R() > (rich ? 0.3 : 0.15)) continue;
      const along = R() < 0.5, o = sd * 8.9, d = (R() < 0.5 ? 1 : -1) * 1.1;
      const p = along ? [c + o, 0.15, t + d] : [t + d, 0.15, c + o];
      add('can', [p[0], p[1], p[2], R() * TAU, 1]);
      if (R() < 0.5) add('bag', [p[0] + rand(-0.6, 0.6), 0.15, p[2] + rand(-0.6, 0.6), R() * TAU, 0.9 + R() * 0.3]);
    }
  }
  // Klimageräte auf niedrigen Dächern (dort schwingt/läuft man am häufigsten)
  const ac = propH('exterior_aircon_unit', null, 1.7);
  let nAc = 0;
  for (const tp of tops) {
    if (tp.y > 60 || R() > 0.35 || nAc > (rich ? 80 : 40)) continue;
    const n = 1 + Math.floor(R() * 2), ry = Math.floor(R() * 4) * Math.PI / 2; nAc += n;
    for (let i = 0; i < n; i++) add('ac', [tp.x + Math.cos(ry) * (i * 1.6 - 1.6) + rand(-2, 2), tp.y + 0.05, tp.z - Math.sin(ry) * (i * 1.6 - 1.6) + rand(-2, 2), ry, ac]);
  }
  const lm = city.landmarks;
  const barrel = propH('Barrel_01', null, 0.88);
  const L = lm.harborCrane;
  if (L) {
    for (let i = 0; i < 12; i++) { const a = Math.PI + R() * Math.PI, r = 7 + R() * 9; add('barrel', [L.x + Math.cos(a) * r, 0.02, L.z - 6 + Math.sin(a) * r, R() * TAU, barrel]); }
    for (let i = 0; i < 8; i++) { const a = Math.PI + R() * Math.PI, r = 7 + R() * 9; add('crate', [L.x + Math.cos(a) * r, 0.02, L.z - 6 + Math.sin(a) * r, R() * TAU, 1.2]); }
  }
  const kinds = { can: ['metal_trash_can', null], bag: ['trashbag', null], ac: ['exterior_aircon_unit', null], barrel: ['Barrel_01', null], crate: ['wooden_crate_02', null] };
  for (const [key, list] of tiles) {
    const [k] = key.split('|');
    const meshes = propPlace(city.root, kinds[k][0], kinds[k][1], list, { shadow: k === 'ac' });
    if (meshes) for (const m of meshes) m.receiveShadow = k !== 'ac';
  }
}
