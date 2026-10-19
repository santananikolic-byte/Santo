"""usage: ana.py TRIAL [start end step] [--sheet out.png] [--fixed]
Prints a coarse timeline (body-local coordinates, m) and optionally a contact sheet."""
import sys
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np, bvh as B, conv as C, render

args = [a for a in sys.argv[1:] if not a.startswith('--')]
opts = [a for a in sys.argv[1:] if a.startswith('--')]
b = B.load(args[0])
s = int(args[1]) if len(args) > 1 else 0
e = int(args[2]) if len(args) > 2 else b.nf
st = int(args[3]) if len(args) > 3 else 12
frames = np.arange(s, min(e, b.nf), st)
R, P = B.fk(b, frames)
P = P * B.UNIT
I = b.idx
yaw = C.heading_of(R[:, 0])
if '--fixed' in opts:
    yaw = np.full_like(yaw, yaw[0])
hp = P[:, 0]
names = list(I.keys())
loc = np.zeros_like(P)
for f in range(len(frames)):
    M = B.roty(-yaw[f])
    loc[f] = (P[f] - hp[f] * np.array([1, 0, 1])) @ M.T
headend = np.einsum('fij,j->fi', R[:, I['Head']], b.ends[I['Head']]) * B.UNIT + P[:, I['Head']]
he = np.zeros_like(headend)
for f in range(len(frames)):
    he[f] = (headend[f] - hp[f] * np.array([1, 0, 1])) @ B.roty(-yaw[f]).T

g = lambda n: loc[:, I[n]]
print('trial', b.name, 'nf', b.nf, 'standHip %.3f' % C.stand_hip_height(b))
print(' frame  t     yaw  hipY | LH x    y    z  | RH x    y    z  | LF y   z  | RF y   z  | headY')
for k, f in enumerate(frames):
    lh, rh, lf, rf = g('LeftHand')[k], g('RightHand')[k], g('LeftToeBase')[k], g('RightToeBase')[k]
    print('%6d %5.2f %5.0f %5.2f | %5.2f %4.2f %5.2f | %5.2f %4.2f %5.2f | %4.2f %5.2f | %4.2f %5.2f | %4.2f' % (
        f, f / 120, np.degrees(yaw[k]), hp[k, 1], *lh, *rh, lf[1], lf[2], rf[1], rf[2], he[k, 1]))

for o in opts:
    if o.startswith('--sheet='):
        cells = []
        for k, f in enumerate(frames):
            J = {n: loc[k, I[n]] for n in names}
            J['HeadEnd'] = he[k]
            J['Hips'] = loc[k, 0]
            cells.append(('%d %.2fs' % (f, f / 120), J))
        render.sheet(cells, render.BVH_SEGS, o.split('=', 1)[1], cols=int(dict(x.split('=') for x in opts if x.startswith('--cols=')).get('--cols', 8)), cell=int(dict(x.split('=') for x in opts if x.startswith('--cell=')).get('--cell', 170)))
