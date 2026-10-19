"""Minimal BVH loader + vectorised FK + quaternion helpers (numpy only)."""
import numpy as np, re, os

UNIT = 0.0254 / 0.45  # CMU ASF length unit (1/0.45 inch) in meters
BVH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bvh')


class BVH:
    pass


def load(name):
    path = name if name.endswith('.bvh') else os.path.join(BVH_DIR, name + '.bvh')
    txt = open(path).read()
    head, motion = txt.split('MOTION', 1)
    toks = head.split()
    names, parents, offsets, chans, ends = [], [], [], [], {}
    stack = []
    i = 0
    cur = -1
    while i < len(toks):
        t = toks[i]
        if t in ('ROOT', 'JOINT'):
            names.append(toks[i + 1]); parents.append(stack[-1] if stack else -1)
            offsets.append(None); chans.append([]); cur = len(names) - 1
            i += 2
        elif t == 'End':
            # End Site { OFFSET x y z }
            j = toks.index('OFFSET', i)
            ends[stack[-1]] = np.array([float(v) for v in toks[j + 1:j + 4]])
            k = toks.index('}', j)
            i = k + 1
            cur = None
            continue
        elif t == '{':
            if cur is not None and cur >= 0:
                stack.append(cur)
            cur = None
            i += 1
        elif t == '}':
            stack.pop(); i += 1
        elif t == 'OFFSET':
            offsets[stack[-1]] = np.array([float(v) for v in toks[i + 1:i + 4]]); i += 4
        elif t == 'CHANNELS':
            n = int(toks[i + 1]); chans[stack[-1]] = toks[i + 2:i + 2 + n]; i += 2 + n
        else:
            i += 1
    lines = motion.strip().split('\n')
    nf = int(re.search(r'Frames:\s*(\d+)', lines[0]).group(1))
    ft = float(re.search(r'Frame Time:\s*([\d.eE+-]+)', lines[1]).group(1))
    data = np.array([[float(v) for v in l.split()] for l in lines[2:2 + nf]])
    b = BVH()
    b.names, b.parents, b.offsets, b.chans, b.ends = names, parents, np.array(offsets), chans, ends
    b.idx = {n: k for k, n in enumerate(names)}
    b.data, b.nf, b.fps = data, nf, round(1.0 / ft)
    b.name = os.path.basename(path)[:-4]
    return b


def axis_mat(axis, ang):
    c, s = np.cos(ang), np.sin(ang)
    n = len(ang)
    M = np.zeros((n, 3, 3)); o = np.ones(n); z = np.zeros(n)
    if axis == 'X':
        M[:] = np.stack([np.stack([o, z, z], -1), np.stack([z, c, -s], -1), np.stack([z, s, c], -1)], 1)
    elif axis == 'Y':
        M[:] = np.stack([np.stack([c, z, s], -1), np.stack([z, o, z], -1), np.stack([-s, z, c], -1)], 1)
    else:
        M[:] = np.stack([np.stack([c, -s, z], -1), np.stack([s, c, z], -1), np.stack([z, z, o], -1)], 1)
    return M


def fk(b, frames=None):
    """Returns world rotation matrices R[F,J,3,3] and world positions P[F,J,3] (BVH units)."""
    d = b.data if frames is None else b.data[frames]
    F, J = len(d), len(b.names)
    R = np.zeros((F, J, 3, 3)); P = np.zeros((F, J, 3))
    col = 0
    for j in range(J):
        L = np.tile(np.eye(3), (F, 1, 1)); pos = np.zeros((F, 3))
        for c in b.chans[j]:
            v = d[:, col]; col += 1
            if c.endswith('position'):
                pos[:, 'XYZ'.index(c[0])] = v
            else:
                L = L @ axis_mat(c[0], np.radians(v))
        p = b.parents[j]
        if p < 0:
            R[:, j] = L; P[:, j] = b.offsets[j] + pos
        else:
            R[:, j] = R[:, p] @ L
            P[:, j] = P[:, p] + np.einsum('fij,j->fi', R[:, p], b.offsets[j])
    return R, P


def rest_positions(b):
    J = len(b.names); P = np.zeros((J, 3))
    for j in range(J):
        p = b.parents[j]
        P[j] = b.offsets[j] + (P[p] if p >= 0 else 0)
    return P


# ---------------- quaternion helpers (x,y,z,w) ----------------
def mat2quat(M):
    M = np.asarray(M); sh = M.shape[:-2]; M = M.reshape(-1, 3, 3)
    q = np.zeros((len(M), 4))
    tr = M[:, 0, 0] + M[:, 1, 1] + M[:, 2, 2]
    for k in range(len(M)):
        m = M[k]; t = tr[k]
        if t > 0:
            s = np.sqrt(t + 1.0) * 2
            q[k] = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
        elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
            q[k] = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
        elif m[1, 1] > m[2, 2]:
            s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
            q[k] = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
        else:
            s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
            q[k] = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    return q.reshape(sh + (4,))


def quat2mat(q):
    q = np.asarray(q); sh = q.shape[:-1]; q = q.reshape(-1, 4)
    x, y, z, w = q.T
    M = np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], 1)
    return M.reshape(sh + (3, 3))


def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0); bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], -1)


def qinv(a):
    return a * np.array([-1, -1, -1, 1.0])


def qrot(q, v):
    return np.einsum('...ij,...j->...i', quat2mat(q), v)


def slerp(a, b, t):
    a = np.asarray(a, float); b = np.asarray(b, float).copy()
    d = np.sum(a * b, -1, keepdims=True)
    b = np.where(d < 0, -b, b); d = np.abs(d)
    t = np.asarray(t, float)
    if t.ndim < a.ndim:
        t = t.reshape(t.shape + (1,) * (a.ndim - t.ndim))
    th = np.arccos(np.clip(d, -1, 1)); s = np.sin(th)
    small = s < 1e-6
    wa = np.where(small, 1 - t, np.sin((1 - t) * th) / np.where(small, 1, s))
    wb = np.where(small, t, np.sin(t * th) / np.where(small, 1, s))
    r = wa * a + wb * b
    return r / np.linalg.norm(r, axis=-1, keepdims=True)


def swing(u, v):
    """Minimal rotation matrix turning unit direction u onto v."""
    u = u / np.linalg.norm(u); v = v / np.linalg.norm(v)
    c = np.cross(u, v); d = np.dot(u, v)
    if np.linalg.norm(c) < 1e-9:
        if d > 0: return np.eye(3)
        a = np.cross(u, [1, 0, 0]) if abs(u[0]) < 0.9 else np.cross(u, [0, 1, 0])
        a /= np.linalg.norm(a)
        return 2 * np.outer(a, a) - np.eye(3)
    K = np.array([[0, -c[2], c[1]], [c[2], 0, -c[0]], [-c[1], c[0], 0]])
    return np.eye(3) + K + K @ K * (1 / (1 + d))


def roty(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
