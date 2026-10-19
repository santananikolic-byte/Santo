#!/usr/bin/env python3
# Packs assets/ into dist/assets/ using only file types the artifact host serves:
#  .gltf+.bin -> one GLB (textures stay external .jpg) -> base64 '.glb.txt'
#  .glb with embedded images -> images extracted to files -> base64 '.glb.txt'
#  .hdr -> base64 '.hdr.txt'; .jpg/.png copied as is.
import os, json, struct, base64, shutil
here = os.path.dirname(os.path.abspath(__file__))
src, dst = os.path.join(here, 'assets'), os.path.join(here, 'dist', 'assets')

def glb_bytes(js, binbuf):
    j = json.dumps(js, separators=(',', ':')).encode()
    j += b' ' * (-len(j) % 4)
    binbuf += b'\0' * (-len(binbuf) % 4)
    total = 12 + 8 + len(j) + 8 + len(binbuf)
    return struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(j), 0x4E4F534A) + j + struct.pack('<II', len(binbuf), 0x004E4942) + binbuf

def read_glb(path):
    b = open(path, 'rb').read()
    jl = struct.unpack('<I', b[12:16])[0]
    js = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl = struct.unpack('<I', b[off:off + 4])[0]
    return js, b[off + 8:off + 8 + bl]

def write_txt(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w').write(base64.b64encode(data).decode())

def main():
    if os.path.exists(dst): shutil.rmtree(dst)
    for d, _, fs in os.walk(src):
        rel = os.path.relpath(d, src)
        od = os.path.join(dst, rel)
        for f in fs:
            p = os.path.join(d, f); ext = f.rsplit('.', 1)[-1].lower()
            if ext in ('jpg', 'jpeg', 'png'):
                os.makedirs(od, exist_ok=True); shutil.copy(p, os.path.join(od, f))
            elif ext == 'hdr':
                write_txt(os.path.join(od, f + '.txt'), open(p, 'rb').read())
            elif ext == 'gltf':
                js = json.load(open(p))
                assert len(js['buffers']) == 1, p
                binbuf = open(os.path.join(d, js['buffers'][0]['uri']), 'rb').read()
                del js['buffers'][0]['uri']; js['buffers'][0]['byteLength'] = len(binbuf)
                write_txt(os.path.join(od, f[:-5] + '.glb.txt'), glb_bytes(js, binbuf))
            elif ext == 'glb':
                js, binbuf = read_glb(p)
                base = f[:-4]
                for i, im in enumerate(js.get('images', [])):
                    if 'bufferView' not in im: continue
                    bv = js['bufferViews'][im['bufferView']]
                    data = binbuf[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
                    e = 'png' if im.get('mimeType') == 'image/png' else 'jpg'
                    name = '%s_img%d.%s' % (base, i, e)
                    os.makedirs(od, exist_ok=True); open(os.path.join(od, name), 'wb').write(data)
                    js['images'][i] = {'uri': name}
                write_txt(os.path.join(od, base + '.glb.txt'), glb_bytes(js, binbuf))
    shutil.copy(os.path.join(here, 'silkstrike.html'), os.path.join(here, 'dist', 'silkstrike.html'))
    shutil.copy(os.path.join(here, 'index.html'), os.path.join(here, 'dist', 'index.html'))
    n = sum(len(fs) for _, _, fs in os.walk(dst)); size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(dst) for f in fs)
    print('packed', n, 'files', round(size / 1e6, 1), 'MB')

if __name__ == '__main__':
    main()
