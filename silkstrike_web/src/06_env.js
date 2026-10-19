// =====================================================================
//  Umgebung: echte HDR-Himmel + Foto-PBR-Oberflächen (Poly Haven, CC0)
//  HDRIs werden einmalig auf die Sonnen-/Blickrichtung des Spiels gedreht
//  und als PMREM-Umgebung gecacht. Fehlen Dateien -> prozeduraler Himmel.
// =====================================================================
// shift: Drehung in Bildbreiten (Sonne/Skyline -> Spielrichtung), bg/env: Intensitäten,
// fog: Horizontfarbe linear (bereits mit bg multipliziert), blur: Hintergrundunschärfe
const ENV_HDRI = {
  // Alpenwiese mit Bergen, Sonne passend zum Tageslicht der Tempel-Arena
  day: { path: Assets.need('hdr', 'env/hdri/alps_field_2k.hdr'), shift: 0.0408, peak: 40, bg: 0.85, env: 0.5, blur: 0, fog: [0.52, 0.6, 0.7] },
  // goldene Stunde: Sonnenuntergang mit Wolken (reiner Himmel, die Stadt liefert die Skyline), Sonne auf GOLDEN_SUN gedreht
  dusk: { path: Assets.need('hdr', 'env/hdri/belfast_sunset_puresky_2k.hdr'), shift: -0.2586, peak: 18, bg: 0.5, env: 0.4, blur: 0, fog: [0.5, 0.38, 0.33] },
  // Stadt bei Nacht: Skyline hinter den Arenen (-z)
  night: { path: Assets.need('hdr', 'env/hdri/shanghai_bund_1k.hdr'), shift: -0.25, peak: 8, bg: 0.2, env: 0.16, blur: 0.02, fog: [0.03, 0.032, 0.055] },
  // dunkler, bedeckter Nachthimmel mit Stadtglühen
  stormNight: { path: Assets.need('hdr', 'env/hdri/kloppenheim_07_puresky_1k.hdr'), shift: -0.317, bg: 0.16, env: 0.3, blur: 0.02, fog: [0.035, 0.036, 0.042] },
};
const EnvHDR = {
  cache: {},
  // Spalten jeder Zeile zyklisch verschieben (dreht das Panorama um die Hochachse)
  rotate(t, shift) {
    const img = t.image, w = img && img.width, h = img && img.height, d = img && img.data;
    if (!d || !w || !h || !shift) return;
    const C = d.length / (w * h), k = ((Math.round(shift * w) % w) + w) % w;
    if (!k || C !== Math.floor(C)) return;
    const row = w * C, tmp = new d.constructor(row);
    for (let y = 0; y < h; y++) {
      const o = y * row; tmp.set(d.subarray(o, o + row));
      d.set(tmp.subarray((w - k) * C), o); d.set(tmp.subarray(0, (w - k) * C), o + k * C);
    }
    t.needsUpdate = true;
  },
  // Sonnen-/Lampen-Spitzen kappen: die Sonne liefert das Richtungslicht der Szene, sonst überstrahlt die IBL alles
  clampPeak(t, max) {
    const d = t.image && t.image.data;
    if (!d || !max) return;
    if (d instanceof Uint16Array) { const hm = THREE.DataUtils.toHalfFloat(max); for (let i = 0; i < d.length; i++) if (d[i] > hm && d[i] < 0x8000) d[i] = hm; }
    else if (d instanceof Float32Array) { for (let i = 0; i < d.length; i++) if (d[i] > max) d[i] = max; }
    t.needsUpdate = true;
  },
  get(tod) {
    const def = ENV_HDRI[tod];
    if (!def) return null;
    if (this.cache[tod]) return this.cache[tod];
    const t = Assets.hdr(def.path);
    if (!t) return null;
    try {
      if (!t.userData.envRotated) { this.rotate(t, def.shift); this.clampPeak(t, def.peak); t.userData.envRotated = true; }
      t.mapping = THREE.EquirectangularReflectionMapping;
      const env = pmrem.fromEquirectangular(t).texture; // einmal pro HDRI
      return (this.cache[tod] = { bg: t, env, def });
    } catch (e) { console.warn('HDRI', tod, e && e.message); return null; }
  },
  // auf die Szene anwenden; false -> prozeduraler Ersatz
  apply(scene, tod, fogDensity) {
    const H = this.get(tod);
    if (!H) return false;
    const d = H.def;
    scene.background = H.bg; scene.backgroundIntensity = d.bg; scene.backgroundBlurriness = d.blur;
    scene.environment = H.env; scene.environmentIntensity = d.env;
    scene.fog = new THREE.FogExp2(0xffffff, tod === 'day' ? Math.min(fogDensity, 0.0042) : fogDensity);
    scene.fog.color.setRGB(d.fog[0], d.fog[1], d.fog[2]); // linear, passt zum HDR-Horizont
    return true;
  },
};

// ---------------------------------------------------------------- Foto-PBR-Sets (1k, Diffuse/Normal/Rough)
// size = Kantenlänge eines Textur-Kachels in Metern (aus Poly-Haven-Metadaten)
const PHOTO_SETS = {};
for (const [key, id, size, maps] of [
  ['asphalt', 'asphalt_02', 3.0, 'dnr'], ['concrete', 'concrete_floor_worn_001', 3.0, 'dnr'], ['pavement', 'concrete_pavement', 1.8, 'dnr'],
  ['tiles', 'large_grey_tiles', 3.0, 'dnr'], ['plate', 'metal_plate', 0.5, 'dnr'], ['cobble', 'cobblestone_square', 1.0, 'dnr'],
  ['rock', 'rock_boulder_dry', 1.8, 'dnr'], ['slab', 'slab_tiles', 2.37, 'dnr'], ['flagstone', 'stone_tiles_02', 2.0, 'dnr'],
  ['grass', 'leafy_grass', 2.0, 'dn'], ['wallDetail', 'concrete_wall_008', 2.71, 'n'],
]) {
  const p = 'env/tex/' + id;
  PHOTO_SETS[key] = {
    size,
    map: maps.includes('d') ? Assets.need('tex', p + '_diff.jpg', { srgb: true }) : null,
    normal: maps.includes('n') ? Assets.need('tex', p + '_nor.jpg') : null,
    rough: maps.includes('r') ? Assets.need('tex', p + '_rough.jpg') : null,
  };
}
const PhotoMatCache = new Map();
// Foto-Material; uvMeters = Meter pro UV-Einheit der Geometrie (Zahl oder [x, y]).
// o: color, roughness (Faktor auf die Rough-Map), metal, normalScale, envIntensity. null -> prozeduraler Ersatz
function photoMat(key, uvMeters, o = {}) {
  const S = PHOTO_SETS[key];
  if (!S || !S.map) return null;
  const um = Array.isArray(uvMeters) ? uvMeters : [uvMeters, uvMeters];
  const rx = um[0] / S.size, ry = um[1] / S.size;
  const ck = key + '|' + rx.toFixed(3) + '|' + ry.toFixed(3) + '|' + JSON.stringify(o);
  if (PhotoMatCache.has(ck)) return PhotoMatCache.get(ck);
  const m = Assets.pbrSet({ map: S.map, normal: S.normal, rough: S.rough, repeat: [rx, ry], normalScale: o.normalScale ?? 1, color: o.color, roughness: o.roughness ?? (S.rough ? 1 : 0.9), metal: o.metal ?? 0 });
  if (!m) return null;
  if (o.envIntensity != null) m.envMapIntensity = o.envIntensity;
  PhotoMatCache.set(ck, m);
  return m;
}
// feines Foto-Relief (Normal-Map mit eigener Kachelung) auf ein bestehendes Material legen, z. B. Fassaden
function photoDetail(mat, key, uvMeters, normalScale = 0.5) {
  const S = PHOTO_SETS[key], t = S && S.normal && Assets.tex(S.normal);
  if (!t || !mat) return mat;
  const n = t.clone(); n.wrapS = n.wrapT = THREE.RepeatWrapping; n.repeat.set(uvMeters / S.size, uvMeters / S.size); n.needsUpdate = true;
  mat.normalMap = n; mat.normalScale.set(normalScale, normalScale); mat.needsUpdate = true;
  return mat;
}
