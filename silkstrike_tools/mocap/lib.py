"""Clip extraction: resample to 30 fps, heading removal, loops, normalisation."""
import sys
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np
import bvh as B, conv as C

H_REF = 1.0          # output root positions are normalised to a T-pose hip height of 1.0 m
_cache = {}


def trial(name):
    """full-trial data at source rate: q[F,22,4] (BVH world), hips pos (m), joint pos (m), R, bvh."""
    if name not in _cache:
        b = B.load(name)
        q, hp, P, R = C.compute(b, np.arange(b.nf))
        _cache[name] = dict(b=b, q=q, hp=hp, P=P, R=R, yaw=np.unwrap(C.heading_of(R[:, 0])),
                            scale=H_REF / C.stand_hip_height(b))
    return _cache[name]


def qyaw(a):
    return np.array([0, np.sin(a / 2), 0, np.cos(a / 2)])


def apply_yaw(q, yaw):
    """rotate world quats q[F,22,4] by -yaw[F] about +Y."""
    h = np.stack([qyaw(-y) for y in np.atleast_1d(yaw)])
    return B.qmul(h[:, None, :], q)


def rot_xz(v, yaw):
    c, s = np.cos(-yaw), np.sin(-yaw)
    x = c * v[..., 0] + s * v[..., 2]; z = -s * v[..., 0] + c * v[..., 2]
    return np.stack([x, v[..., 1], z], -1)


def make_continuous(q):
    """sign-continuity along time per bone."""
    q = q.copy()
    for f in range(1, len(q)):
        d = np.sum(q[f] * q[f - 1], -1)
        q[f][d < 0] *= -1
    return q


def mirror(q, p):
    """mirror across the character's sagittal plane (x -> -x) and swap left/right bones."""
    q = q * np.array([1, -1, -1, 1.0]); p = p * np.array([-1, 1, 1.0])
    idx = []
    for n in C.BONES:
        m = n.replace('Left', '#').replace('Right', 'Left').replace('#', 'Right')
        idx.append(C.BONES.index(m))
    return q[:, idx], p


def target_yaw(T, hit, part, start):
    """yaw of the vector from the hips (at clip start) to the striking end-effector at the hit frame."""
    I = T['b'].idx
    j = {'LH': 'LeftHand', 'RH': 'RightHand', 'LF': 'LeftFoot', 'RF': 'RightFoot',
         'LT': 'LeftToeBase', 'RT': 'RightToeBase'}[part]
    v = T['P'][hit, I[j]] - T['hp'][start]
    return np.arctan2(v[0], v[2])


def extract(name, a, b, loop=False, yaw=None, yaw_off=0.0, inplace=False, mirror_lr=False,
            xfade=0.15, step=4, yaw_drift=True, keep_y=True):
    """a,b: source frames (120 fps). loop: frame b is treated as the same pose as frame a
    (output contains a..b inclusive with the last frame == first frame).
    yaw: None -> hips yaw (frame a, or mean for loops); number (radians) -> explicit.
    returns q[n,22,4], p[n,3]"""
    T = trial(name)
    sc = T['scale']
    fr = np.arange(a, b + 1, step)
    yw = T['yaw']
    if yaw is None:
        y0 = yw[a] if not loop else np.mean(yw[a:b + 1])
    else:
        y0 = yaw
    y0 = y0 + yaw_off
    n = len(fr)
    if loop and yaw_drift:
        om = (yw[fr[-1]] - yw[fr[0]]) / (n - 1)
        ys = y0 + om * (np.arange(n) - (n - 1) / 2)
    else:
        om = 0.0
        ys = np.full(n, y0)
    K = int(round(xfade * 30)) if loop else 0
    # pre-roll frames for crossfade
    pre = np.arange(a - K * step, a, step)
    pre = pre[pre >= 0]
    K = len(pre)
    allf = np.concatenate([pre, fr])
    yall = np.concatenate([ys[0] - om * np.arange(K, 0, -1), ys])
    q = apply_yaw(T['q'][allf], yall)
    hp = T['hp'][allf] * sc
    d = np.diff(hp, axis=0)
    d = rot_xz(d, yall[1:])
    p = np.concatenate([np.zeros((1, 3)), np.cumsum(d, 0)])
    p[:, 1] = hp[:, 1]
    p[:, [0, 2]] -= p[K, [0, 2]]
    if loop:
        v = (p[-1] - p[K]) / (n - 1)
        v[1] = 0
        p = p - np.outer(np.arange(len(p)) - K, v)
        # crossfade tail -> pre-roll of the start
        L = n - 1
        for k in range(1, K + 1):
            i = L + k  # tail index (all-array: 0..K-1 pre-roll, K = frame a, K+L = frame b)
            j = i - L
            w = k / K
            w = w * w * (3 - 2 * w)
            q[i] = B.slerp(q[i], q[j], w)
            p[i] = (1 - w) * p[i] + w * p[j]
        q[-1] = q[K]; p[-1] = p[K]
    q = q[K:]; p = p[K:]
    if inplace and not loop:
        p[:, [0, 2]] = 0
    if inplace and loop:
        p[:, [0, 2]] -= p[:, [0, 2]].mean(0)
    if mirror_lr:
        q, p = mirror(q, p)
    q = make_continuous(q)
    return q, p


def local_pose_feats(name, step=4):
    """per 30fps frame features for loop search: heading-free quats + hips height."""
    T = trial(name)
    fr = np.arange(0, T['b'].nf, step)
    q = apply_yaw(T['q'][fr], T['yaw'][fr])
    return fr, q, T['hp'][fr, 1] * T['scale']


def pose_dist(qa, qb):
    d = np.abs(np.sum(qa * qb, -1))
    return np.sum(1 - np.clip(d, 0, 1), -1)


EFF = {'LH': ('LeftHand', 'LeftArm'), 'RH': ('RightHand', 'RightArm'), 'LF': ('LeftFoot', 'LeftUpLeg'),
       'RF': ('RightFoot', 'RightUpLeg'), 'LT': ('LeftToeBase', 'LeftUpLeg'), 'RT': ('RightToeBase', 'RightUpLeg')}


def strike_window(name, part, pk, vthr=0.6, back=0.08, maxpre=60, maxpost=90, pad=4):
    """source frames (s, e) around a strike peak: start when the end-effector (relative to hips) starts
    moving, end when it is back near its start position."""
    T = trial(name); I = T['b'].idx; P = T['P']
    eff = I[EFF[part][0]]
    rel = P[:, eff] - P[:, 0]
    v = np.linalg.norm(np.gradient(rel, axis=0), axis=1) * 120
    s = pk - 1
    while s > pk - 15 and v[s] < vthr: s -= 1
    while s > pk - maxpre and v[s] > vthr: s -= 1
    s = max(0, s - pad)
    e = pk + 6
    while e < min(T['b'].nf - 1, pk + maxpost):
        if np.linalg.norm(rel[e] - rel[s]) < back and v[e] < vthr: break
        e += 1
    return s, min(T['b'].nf - 1, e + pad)


def peak_of(name, part, s, e):
    T = trial(name); I = T['b'].idx; P = T['P']
    a, r = EFF[part]
    d = np.linalg.norm(P[s:e, I[a]] - P[s:e, I[r]], axis=1)
    if part[1] in 'FT':
        d = d + 0.5 * (P[s:e, I[a], 1])  # favour height for kicks
    return s + int(np.argmax(d))


def feet_yaw(name, frames):
    """yaw of the (left foot - right foot) line averaged over frames."""
    T = trial(name); I = T['b'].idx; P = T['P']
    v = (P[frames, I['LeftFoot']] - P[frames, I['RightFoot']]).mean(0)
    return np.arctan2(v[0], v[2])


def stance_yaw(name, frames, mirror_lr=False, alpha=np.radians(15)):
    """yaw for extract() such that the output (left foot - right foot) line points at angle alpha
    from +Z toward +X (orthodox stance: left foot forward)."""
    T = trial(name); I = T['b'].idx; P = T['P']
    v = (P[frames, I['LeftFoot']] - P[frames, I['RightFoot']]).mean(0)
    if mirror_lr:
        v = -v
        return alpha + np.arctan2(v[0], v[2])
    return np.arctan2(v[0], v[2]) - alpha


def out_feet_alpha(q, p):
    """measure the feet-line angle (deg) of an extracted clip on the canonical preview skeleton (frame 0)."""
    import preview
    J = preview.fk_frame(C.BONES, q[0], p[0])
    v = J['LeftFoot'] - J['RightFoot']
    return np.degrees(np.arctan2(v[0], v[2]))
