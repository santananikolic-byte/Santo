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
  json(path) { return this.data.get(path) || null; },
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
  async bin(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status + ' ' + url);
    const s = atob((await r.text()).trim()), n = s.length, u = new Uint8Array(n);
    for (let i = 0; i < n; i++) u[i] = s.charCodeAt(i);
    return u.buffer;
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
        // Modelle und HDRs liegen gepackt als Base64-Text vor (pack.py), Bilder als .jpg/.png
        if (it.kind === 'model') {
          const dir = url.slice(0, url.lastIndexOf('/') + 1);
          this.bin(url.replace(/\.(gltf|glb)$/, '.glb.txt')).then((buf) => gl.parse(buf, dir, (g) => { g.scene.traverse((o) => { if (o.isMesh) { o.castShadow = it.opts.shadow !== false; o.receiveShadow = true; } }); ok(g); }, fail)).catch(fail);
        } else if (it.kind === 'hdr') {
          this.bin(url + '.txt').then((buf) => {
            const d = hl.parse(buf);
            const t = new THREE.DataTexture(d.data, d.width, d.height, THREE.RGBAFormat, d.type);
            t.colorSpace = THREE.LinearSRGBColorSpace; t.minFilter = t.magFilter = THREE.LinearFilter; t.generateMipmaps = false; t.flipY = true;
            t.mapping = THREE.EquirectangularReflectionMapping; t.needsUpdate = true; ok(t);
          }).catch(fail);
        } else if (it.kind === 'json') {
          fetch(url).then((r) => { if (!r.ok) throw new Error(r.status + ' ' + url); return r.json(); }).then(ok).catch(fail);
        } else tl.load(url, (t) => { t.colorSpace = it.opts.srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace; t.anisotropy = aniso; t.wrapS = t.wrapT = THREE.RepeatWrapping; ok(t); }, undefined, fail);
      } catch (e) { fail(e); }
    });
    // max. 6 gleichzeitig
    let i = 0;
    const worker = async () => { while (i < this.list.length) await one(this.list[i++]); };
    return Promise.all(Array.from({ length: Math.min(6, total) }, worker));
  },
};
