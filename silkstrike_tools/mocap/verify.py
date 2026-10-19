"""numeric checks on clips.json (independent of the build: uses only the JSON + canonical preview skeleton)"""
import sys, json
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np, preview
d = json.load(open(sys.argv[1]))
assert d['fps'] == 30 and len(d['bones']) == 22
nb = len(d['bones'])
def qdist(a, b):
    return 2 * np.degrees(np.arccos(np.clip(np.abs(np.sum(a * b, -1)), 0, 1)))
print('%-12s %4s %5s %5s | %7s | %-26s | %-22s | %s' % ('clip', 'n', 'dur', 'hit', 'maxNorm', 'loop seam (deg: last->1 vs med)', 'strike dir / dist', 'feet minY  hipsY  final p'))
for name, c in d['clips'].items():
    n = c['n']
    q = np.array(c['q']).reshape(n, nb, 4); p = np.array(c['p']).reshape(n, 3)
    assert len(c['q']) == n * nb * 4 and len(c['p']) == n * 3
    nerr = np.abs(np.linalg.norm(q, axis=-1) - 1).max()
    step = qdist(q[1:], q[:-1]).max(1)          # max bone rotation change per frame (deg)
    seam = ''
    if c['loop']:
        same = qdist(q[-1], q[0]).max()
        wrap = qdist(q[1], q[-1]).max()          # frame n-1 (== 0) -> 1 continues the loop
        seam = 'last==first %.2f, wrap %.1f med %.1f max %.1f' % (same, wrap, np.median(step), step.max())
        seam += '  dp %.3f' % np.linalg.norm(p[-1] - p[0])
    J = [preview.fk_frame(d['bones'], q[i], p[i]) for i in range(n)]
    feet = min(min(j[k][1] for k in ('LeftToeEnd', 'RightToeEnd', 'LeftFoot', 'RightFoot')) for j in J) - 0.0
    sd = ''
    if c['hit'] is not None:
        h = int(round(c['hit'] * (n - 1)))
        best = None
        for k in ('LeftHand', 'RightHand', 'LeftFoot', 'RightFoot'):
            v = J[h][k] - J[0]['Hips']
            dist = np.linalg.norm(J[h][k] - J[h]['Spine2' if 'Hand' in k else 'Hips'])
            if best is None or dist > best[2]:
                best = (k, v, dist)
        k, v, dist = best
        sd = '%s yaw %+.0f x %+.2f z %+.2f y %.2f' % (k, np.degrees(np.arctan2(v[0], v[2])), v[0], v[2], J[h][k][1])
    print('%-12s %4d %5.2f %5s | %.1e | %-26s | %-22s | %.2f  %.2f-%.2f  (%+.2f,%+.2f)' % (
        name, n, (n - 1) / 30, c['hit'], nerr, seam, sd, feet - 0.08 + 0.08, p[:, 1].min(), p[:, 1].max(), p[-1, 0], p[-1, 2]))
# left/right sanity: in fightIdle frame 0, left shoulder/hand should be at +x relative to right
J0 = preview.fk_frame(d['bones'], np.array(d['clips']['fightIdle']['q'][:nb * 4]).reshape(nb, 4), d['clips']['fightIdle']['p'][:3])
print('fightIdle f0: LeftArm x %.2f RightArm x %.2f | LeftFoot z %.2f RightFoot z %.2f | LeftHand y %.2f RightHand y %.2f head y %.2f' % (
    J0['LeftArm'][0], J0['RightArm'][0], J0['LeftFoot'][2], J0['RightFoot'][2], J0['LeftHand'][1], J0['RightHand'][1], J0['Head'][1]))
