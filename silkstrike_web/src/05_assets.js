// =====================================================================
//  Assets: echte Modelle, HDR-Himmel und Foto-Texturen (Dateien in assets/)
//  Registrieren auf Top-Level mit Assets.need(...), beim Start wird alles
//  vorgeladen; Szenen holen sich die Daten danach synchron.
//  Fehlt eine Datei, liefern die Getter null -> prozeduraler Ersatz.
// =====================================================================
const Assets = {
  base: 'assets/',
  list: [], data: new Map(), loaded: 0,
  need(kind, path, opts = {}) { if (!this.list.find((x) => x.path === path)) this.list.push({ kind, path, opts }); return path; },
  // Modell als Klon (eigene Transformation, geteilte Geometrie/Materialien)
  model(path) { const g = this.data.get(path); return g ? g.scene.clone(true) : null; },
  gltf(path) { return this.data.get(path) || null; },
  hdr(path) { return this.data.get(path) || null; },
  // Textur (geteilt); repeat setzt man am besten über tex.clone() pro Material
  tex(path) { return this.data.get(path) || null; },
  // PBR-Material aus einem Texturset: {map, normal, rough, arm, repeat:[x,y], color, metal}
  pbrSet(o) {
    const m = new THREE.MeshStandardMaterial({ color: o.color || 0xffffff, roughness: o.roughness ?? 1, metalness: o.metal ?? 0 });
    const rep = (t) => { if (!t) return null; const c = t.clone(); c.wrapS = c.wrapT = THREE.RepeatWrapping; if (o.repeat) c.repeat.set(o.repeat[0], o.repeat[1]); c.needsUpdate = true; return c; };
    if (o.map) m.map = rep(this.tex(o.map));
    if (o.normal) { m.normalMap = rep(this.tex(o.normal)); if (o.normalScale) m.normalScale.set(o.normalScale, o.normalScale); }
    if (o.rough) m.roughnessMap = rep(this.tex(o.rough));
    if (o.arm) { const t = rep(this.tex(o.arm)); m.aoMap = t; m.roughnessMap = t; m.metalnessMap = t; }
    if (o.map && !m.map) return null;
    return m;
  },
  preload(onProgress) {
    const total = this.list.length;
    if (!total) return Promise.resolve();
    const gl = new GLTFLoader(), tl = new THREE.TextureLoader(), hl = new RGBELoader();
    const aniso = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    const one = (it) => new Promise((res) => {
      const url = this.base + it.path;
      const ok = (v) => { this.data.set(it.path, v); this.loaded++; onProgress && onProgress(this.loaded / total); res(); };
      const fail = (e) => { console.warn('asset fehlt', it.path, e && e.message); this.loaded++; onProgress && onProgress(this.loaded / total); res(); };
      try {
        if (it.kind === 'model') gl.load(url, (g) => { g.scene.traverse((o) => { if (o.isMesh) { o.castShadow = it.opts.shadow !== false; o.receiveShadow = true; } }); ok(g); }, undefined, fail);
        else if (it.kind === 'hdr') hl.load(url, (t) => { t.mapping = THREE.EquirectangularReflectionMapping; ok(t); }, undefined, fail);
        else tl.load(url, (t) => { t.colorSpace = it.opts.srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace; t.anisotropy = aniso; t.wrapS = t.wrapT = THREE.RepeatWrapping; ok(t); }, undefined, fail);
      } catch (e) { fail(e); }
    });
    // max. 6 gleichzeitig
    let i = 0;
    const worker = async () => { while (i < this.list.length) await one(this.list[i++]); };
    return Promise.all(Array.from({ length: Math.min(6, total) }, worker));
  },
};
