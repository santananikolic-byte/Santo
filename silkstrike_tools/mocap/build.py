"""Build clips.json from CMU BVH sources.  python3 -I build.py OUT.json"""
import sys, json, os
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np
import lib, conv as C, bvh as B

ALPHA = np.radians(15)   # orthodox stance: (left foot - right foot) line rotated 15 deg from +Z toward +X
META = {}


def floor_off(tr):
    """per-trial floor correction (m, already scaled): lowest foot joints should sit ~3 cm above y=0."""
    T = lib.trial(tr); P = T['P']; I = T['b'].idx
    m = np.min(np.stack([P[1:, I[j], 1] for j in ('LeftToeBase', 'RightToeBase', 'LeftFoot', 'RightFoot')], 1), 1)
    off = (np.percentile(m, 5) - 0.03) * T['scale']
    return off if abs(off) > 0.02 else 0.0


def fix_floor(tr, p):
    p = p.copy(); p[:, 1] -= floor_off(tr); return p


def smooth_ends(q, p, k=3):
    return q, p


def strike(tr, part, pk, s=None, e=None, mirror=False, maxpost=90, pad=4, yaw_off=0.0):
    if s is None or e is None:
        s2, e2 = lib.strike_window(tr, part, pk, maxpost=maxpost, pad=pad)
        s = s if s is not None else s2
        e = e if e is not None else e2
    T = lib.trial(tr)
    y = lib.target_yaw(T, pk, part, s) + np.radians(yaw_off)
    q, p = lib.extract(tr, s, e, yaw=y, mirror_lr=mirror)
    p = fix_floor(tr, p)
    n = len(q)
    hit = round((pk - s) / (e - s), 3)
    return q, p, hit, dict(src=tr, frames=[s, e], peak=pk, mirror=mirror)


def strike_return(tr, part, pk, s, r, m, mirror=False, xf=4):
    """forward s..r (through the strike), then the wind-up m..s played in reverse to return to the start pose."""
    T = lib.trial(tr)
    y = lib.target_yaw(T, pk, part, s)
    q1, p1 = lib.extract(tr, s, r, yaw=y, mirror_lr=mirror)
    q2, p2 = lib.extract(tr, s, m, yaw=y, mirror_lr=mirror)
    q2 = q2[::-1]; p2 = p2[::-1]
    # root: shift reversed part to start at p1[-1] (x,z), shift fades out toward the end
    off = p1[-1] - p2[0]; off[1] = 0
    w = np.linspace(1, 0, len(p2))[:, None]
    w = w * w * (3 - 2 * w)
    p2 = p2 + w * off
    # crossfade xf frames
    qa = q1[:-xf] if xf else q1
    blend_q = []; blend_p = []
    for k in range(xf):
        t = (k + 1) / (xf + 1); t = t * t * (3 - 2 * t)
        blend_q.append(B.slerp(q1[len(q1) - xf + k], q2[k], t)); blend_p.append((1 - t) * p1[len(q1) - xf + k] + t * p2[k])
    q = np.concatenate([q1[:-xf], np.array(blend_q), q2[xf:]]) if xf else np.concatenate([q1, q2[1:]])
    p = np.concatenate([p1[:-xf], np.array(blend_p), p2[xf:]]) if xf else np.concatenate([p1, p2[1:]])
    q = lib.make_continuous(q)
    p = fix_floor(tr, p)
    hit = round((pk - s) / 4 / (len(q) - 1), 3)
    return q, p, hit, dict(src=tr, frames=[s, r], returnVia=[m, s], peak=pk, mirror=mirror)


def loop(tr, a, b, mirror=False, yawmode='stance', xfade=0.15, inplace=True, alpha=ALPHA, yaw=None, yaw_drift=True):
    if yaw is None:
        if yawmode == 'stance':
            yaw = lib.stance_yaw(tr, np.arange(a, b, 4), mirror, alpha)
        else:
            yaw = None
    q, p = lib.extract(tr, a, b, loop=True, yaw=yaw, mirror_lr=mirror, inplace=inplace, xfade=xfade, yaw_drift=yaw_drift)
    p = fix_floor(tr, p)
    return q, p, None, dict(src=tr, frames=[a, b], mirror=mirror)


def segment(tr, a, b, yaw=None, mirror=False, yaw_end=None):
    """plain segment; yaw None -> hips yaw at a. yaw_end: optional second yaw reached at the end (smoothstep)."""
    T = lib.trial(tr)
    if yaw is None:
        yaw = T['yaw'][a]
    q, p = lib.extract(tr, a, b, yaw=yaw, mirror_lr=mirror)
    if yaw_end is not None:
        n = len(q)
        t = np.linspace(0, 1, n); t = t * t * (3 - 2 * t)
        dy = (yaw_end - yaw) * t
        h = np.stack([lib.qyaw(-d) for d in dy])
        q = B.qmul(h[:, None, :], q)
        # rotate root path about the first frame
        p0 = p.copy()
        for i in range(n):
            v = p0[i] - p0[0]
            c, s_ = np.cos(-dy[i]), np.sin(-dy[i])
            p[i, 0] = c * v[0] + s_ * v[2]; p[i, 2] = -s_ * v[0] + c * v[2]
        q = lib.make_continuous(q)
    p = fix_floor(tr, p)
    return q, p, None, dict(src=tr, frames=[a, b], mirror=mirror)


def reverse(c):
    q, p, hit, m = c
    m = dict(m); m['reversed'] = True
    return q[::-1].copy(), p[::-1].copy(), hit, m


def synth_block(idle, tr, f, mirror=False):
    """held high guard: cover pose (single source frame) + the fight-idle's per-bone world-rotation deltas."""
    qi, pi_, _, _ = idle
    yaw = lib.stance_yaw(tr, np.arange(f - 8, f + 9, 4), mirror)
    qc, pc = lib.extract(tr, f, f, yaw=yaw, mirror_lr=mirror)
    pc = fix_floor(tr, pc)
    d = B.qmul(qi, B.qinv(qi[0])[None])          # world delta of each bone vs frame 0
    q = B.qmul(d, qc[0][None])
    p = pc[0][None] + (pi_ - pi_[0])
    q = lib.make_continuous(q / np.linalg.norm(q, axis=-1, keepdims=True))
    return q, p, None, dict(src=tr, frames=[f, f], synthesized='cover pose %s f%d + fightIdle motion' % (tr, f))


def redirect_upper(c, target=np.pi):
    """rotate the upper-body motion (world deltas vs frame 0) about +Y so that the head's main horizontal
    displacement points toward yaw 'target' (pi = straight back, -Z). Hips/legs/root untouched."""
    import preview
    q, p, hit, meta = c
    J = [preview.fk_frame(C.BONES, q[i], p[i]) for i in range(len(q))]
    H = np.array([j['Head'] - j['Hips'] for j in J])
    d = H - H[0]
    k = int(np.argmax(np.linalg.norm(d[:, [0, 2]], axis=1)))
    phi = target - np.arctan2(d[k, 0], d[k, 2])
    Y = lib.qyaw(phi)
    up = [C.BONES.index(b) for b in C.BONES if not (b == 'Hips' or 'Leg' in b or 'Foot' in b or 'Toe' in b)]
    q = q.copy()
    for b in up:
        D = B.qmul(q[:, b], B.qinv(q[0, b])[None])
        D = B.qmul(B.qmul(Y[None], D), B.qinv(Y)[None])
        q[:, b] = B.qmul(D, q[0, b][None])
    meta = dict(meta); meta['upperBodyRedirectDeg'] = round(float(np.degrees(phi)), 1)
    return lib.make_continuous(q), p, hit, meta


def head_axis_yaw(tr, f):
    T = lib.trial(tr); P = T['P']; I = T['b'].idx
    v = P[f, 0] - P[f, I['Head']]
    return np.arctan2(v[0], v[2])


def build():
    clips = {}
    # ---------------- boxing core (subject 15, southpaw section mirrored -> orthodox, left lead) ----------------
    clips['fightIdle'] = loop('15_13', 1396, 1516, mirror=True)
    clips['punch'] = strike('15_13', 'RH', 3714, mirror=True)            # lead (left after mirroring) jab
    clips['punch2'] = strike('15_13', 'LH', 6224, mirror=True)           # rear (right after mirroring) cross
    T13 = lib.trial('13_17'); I13 = T13['b'].idx
    up_pk = 1300 + int(np.argmax(T13['P'][1300:1345, I13['RightHand'], 1]))
    clips['uppercut'] = strike('13_17', 'RH', up_pk, s=1258, e=1372)      # rear right uppercut (orthodox)
    # footwork (subject 17): forward = lead-foot step + rear-foot drag; back = same cycle reversed
    clips['walkForward'] = loop('17_10', 1944, 2084)
    clips['walkBack'] = reverse(clips['walkForward'])
    # kicks
    clips['kick'] = strike('144_05', 'RF', 360, e=470)              # rear-leg front kick, returns to stance
    clips['kick2'] = strike_return('135_07', 'RF', 120, 52, 152, 92)      # rear-leg roundhouse, return = rewound chamber
    clips['sweep'] = strike('144_05', 'RF', 1441, maxpost=130)            # low front kick
    clips['jumpKick'] = strike('75_16', 'RF', lib.peak_of('75_16', 'RF', 225, 262), s=196, e=300)
    # reactions
    T = lib.trial('13_17')
    clips['hitHigh'] = redirect_upper(segment('13_17', 4198, 4282, yaw=lib.stance_yaw('13_17', np.arange(4190, 4200), False)))
    clips['knockdown'] = segment('90_18', 66, 170)
    kd_yaw = lib.trial('90_18')['yaw'][66]
    clips['lieDown'] = loop('90_18', 200, 380, yaw=kd_yaw, xfade=0.3, inplace=False, yaw_drift=False)
    # getUp: align lying axis with the knockdown's end, end facing +Z
    gy0 = head_axis_yaw('140_09', 150) - (head_axis_yaw('90_18', 300) - kd_yaw)
    gy1 = lib.trial('140_09')['yaw'][575]
    gy1 = gy0 + ((gy1 - gy0 + np.pi) % (2 * np.pi) - np.pi)
    clips['getUp'] = segment('140_09', 150, 580, yaw=gy0, yaw_end=gy1)
    # misc
    clips['victory'] = segment('79_69', 105, 300)
    clips['taunt'] = segment('79_94', 236, 460)
    clips['block'] = synth_block(clips['fightIdle'], '13_18', 794)
    clips['dizzy'] = loop('137_15', 264, 536, yawmode='hips', xfade=0.25)
    clips['idle'] = loop('77_02', 76, 276, yawmode='hips', xfade=0.25)
    clips['run'] = loop('16_35', 28, 124, yawmode='hips', xfade=0.1)
    # Zwischensequenzen / Spezialangriffe
    clips['talk'] = loop('18_08', 600, 840, yawmode='hips', xfade=0.25)
    clips['lookAround'] = loop('77_01', 240, 600, yawmode='hips', xfade=0.3)
    clips['kneel'] = segment('23_03', 60, 200)
    clips['defeat'] = segment('79_71', 200, 368)
    q, p_, _, m = segment('120_03', 270, 430)
    clips['cast'] = (q, p_, round((400 - 270) / (430 - 270), 3), m)
    clips['crouch'] = synth_block(clips['fightIdle'], '136_09', 480)
    clips['jump'] = segment('16_01', 70, 150)
    clips['land'] = segment('16_01', 160, 240)
    return clips


def pack(clips):
    out = {"fps": 30, "bones": C.BONES, "clips": {}}
    for name, (q, p, hit, meta) in clips.items():
        q = q / np.linalg.norm(q, axis=-1, keepdims=True)
        loopf = name in ('fightIdle', 'walkForward', 'walkBack', 'lieDown', 'block', 'dizzy', 'idle', 'run', 'talk', 'lookAround', 'crouch')
        out["clips"][name] = {"loop": loopf, "hit": hit, "n": int(len(q)),
                              "q": [float(round(v, 4)) for v in q.reshape(-1)],
                              "p": [float(round(v, 4)) for v in p.reshape(-1)]}
        META[name] = meta
    return out


if __name__ == '__main__':
    out = pack(build())
    path = sys.argv[1]
    s = json.dumps(out, separators=(',', ':'))
    s = s.replace('.0,', ',').replace('.0]', ']')
    open(path, 'w').write(s)
    print('wrote', path, '%.2f MB' % (len(s) / 1e6))
    json.dump(META, open(path + '.meta.json', 'w'), indent=1, default=str)
    for k, c in out['clips'].items():
        print('%-12s n %3d (%.2fs) loop %-5s hit %s  %s' % (k, c['n'], (c['n'] - 1) / 30, c['loop'], c['hit'], META[k]))
