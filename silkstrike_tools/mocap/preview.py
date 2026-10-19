"""FK of clips.json on a canonical T-pose skeleton (Mixamo-like proportions, hip height 1.0 m)
usage: preview.py clips.json outdir [clip ...] [--n=6]"""
import sys, json, os
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np
import render

# canonical T-pose: child offsets (m) relative to parent joint, in character space (+Y up, faces +Z, left = +X)
SK = [("Hips", None, (0, 0, 0)), ("Spine", "Hips", (0, 0.10, 0)), ("Spine1", "Spine", (0, 0.12, 0)),
      ("Spine2", "Spine1", (0, 0.13, 0)), ("Neck", "Spine2", (0, 0.16, 0)), ("Head", "Neck", (0, 0.10, 0)),
      ("HeadEnd", "Head", (0, 0.20, 0)),
      ("LeftShoulder", "Spine2", (0.05, 0.11, 0)), ("LeftArm", "LeftShoulder", (0.12, 0, 0)),
      ("LeftForeArm", "LeftArm", (0.27, 0, 0)), ("LeftHand", "LeftForeArm", (0.26, 0, 0)), ("LeftHandEnd", "LeftHand", (0.17, 0, 0)),
      ("RightShoulder", "Spine2", (-0.05, 0.11, 0)), ("RightArm", "RightShoulder", (-0.12, 0, 0)),
      ("RightForeArm", "RightArm", (-0.27, 0, 0)), ("RightHand", "RightForeArm", (-0.26, 0, 0)), ("RightHandEnd", "RightHand", (-0.17, 0, 0)),
      ("LeftUpLeg", "Hips", (0.09, -0.05, 0)), ("LeftLeg", "LeftUpLeg", (0, -0.44, 0)), ("LeftFoot", "LeftLeg", (0, -0.43, 0)),
      ("LeftToeBase", "LeftFoot", (0, 0, 0.13)), ("LeftToeEnd", "LeftToeBase", (0, 0, 0.07)),
      ("RightUpLeg", "Hips", (-0.09, -0.05, 0)), ("RightLeg", "RightUpLeg", (0, -0.44, 0)), ("RightFoot", "RightLeg", (0, -0.43, 0)),
      ("RightToeBase", "RightFoot", (0, 0, 0.13)), ("RightToeEnd", "RightToeBase", (0, 0, 0.07))]
ANKLE = 0.08  # ankle height above the sole in the canonical pose (hip height = 0.05+0.44+0.43+0.08 = 1.0)

B, G, R_, K = render.BLUE, render.GREEN, render.RED, render.GRAY
SEGS = [("Hips", "Spine", K), ("Spine", "Spine1", K), ("Spine1", "Spine2", K), ("Spine2", "Neck", K), ("Neck", "Head", K), ("Head", "HeadEnd", K),
        ("Spine2", "LeftShoulder", B), ("LeftShoulder", "LeftArm", B), ("LeftArm", "LeftForeArm", B), ("LeftForeArm", "LeftHand", B), ("LeftHand", "LeftHandEnd", G),
        ("Spine2", "RightShoulder", R_), ("RightShoulder", "RightArm", R_), ("RightArm", "RightForeArm", R_), ("RightForeArm", "RightHand", R_), ("RightHand", "RightHandEnd", G),
        ("Hips", "LeftUpLeg", B), ("LeftUpLeg", "LeftLeg", B), ("LeftLeg", "LeftFoot", B), ("LeftFoot", "LeftToeBase", B), ("LeftToeBase", "LeftToeEnd", B),
        ("Hips", "RightUpLeg", R_), ("RightUpLeg", "RightLeg", R_), ("RightLeg", "RightFoot", R_), ("RightFoot", "RightToeBase", R_), ("RightToeBase", "RightToeEnd", R_)]


def quat2mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def fk_frame(bones, qf, pf):
    rot = {b: quat2mat(qf[k]) for k, b in enumerate(bones)}
    J = {}
    for name, par, off in SK:
        if par is None:
            J[name] = np.array(pf, float)
        else:
            J[name] = J[par] + rot[par] @ np.array(off, float)
    return J


def clip_frames(data, name):
    c = data['clips'][name]; bones = data['bones']; nb = len(bones)
    q = np.array(c['q']).reshape(c['n'], nb, 4); p = np.array(c['p']).reshape(c['n'], 3)
    return q, p


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opts = dict(a[2:].split('=') for a in sys.argv[1:] if a.startswith('--'))
    data = json.load(open(args[0])); out = args[1]; os.makedirs(out, exist_ok=True)
    names = args[2:] or list(data['clips'])
    nshow = int(opts.get('n', 6))
    for name in names:
        c = data['clips'][name]
        q, p = clip_frames(data, name)
        n = c['n']
        idx = sorted(set(np.linspace(0, n - 1, nshow).round().astype(int)))
        if c.get('hit') is not None:
            h = int(round(c['hit'] * (n - 1)))
            idx = sorted(set(idx) | {h})
        cells = []
        for i in idx:
            J = fk_frame(data['bones'], q[i], p[i])
            lab = '%s f%d/%d%s' % (name, i, n - 1, ' HIT' if c.get('hit') is not None and i == int(round(c['hit'] * (n - 1))) else '')
            cells.append((lab, J))
        render.sheet(cells, SEGS, os.path.join(out, name + '.png'), cols=min(len(cells), 4), cell=230, span=2.2,
                     views=('front', 'side', 'top'))
        print(name, 'n', n, 'frames', idx)
