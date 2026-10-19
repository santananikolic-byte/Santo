"""cgspeed CMU skeleton -> Mixamo bone world-delta quaternions (q = W_frame * inv(W_canonical))."""
import sys
sys.path.insert(0, '/tmp/claude-0/-home-user-Santo/aeab05ac-6a70-5e30-a731-db44ed40f269/scratchpad/mocap')
import numpy as np
import bvh as B

BONES = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
         "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
         "RightShoulder", "RightArm", "RightForeArm", "RightHand",
         "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
         "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]

# mixamo bone -> (cgspeed joint(s) whose world rotation drives it)
SRC = {"Hips": "Hips", "Spine": "LowerBack", "Spine1": "Spine", "Spine2": "Spine1",
       "Neck": ("Neck", "Neck1"), "Head": "Head",
       "LeftShoulder": "LeftShoulder", "LeftArm": "LeftArm", "LeftForeArm": "LeftForeArm", "LeftHand": "LeftFingerBase",
       "RightShoulder": "RightShoulder", "RightArm": "RightArm", "RightForeArm": "RightForeArm", "RightHand": "RightFingerBase",
       "LeftUpLeg": "LeftUpLeg", "LeftLeg": "LeftLeg", "LeftFoot": "LeftFoot", "LeftToeBase": "LeftToeBase",
       "RightUpLeg": "RightUpLeg", "RightLeg": "RightLeg", "RightFoot": "RightFoot", "RightToeBase": "RightToeBase"}

X, Y, Z = np.eye(3)
CANON_DIR = {"Hips": None, "Spine": Y, "Spine1": Y, "Spine2": Y, "Neck": Y, "Neck1": Y, "Head": Y,
             "LeftShoulder": X, "LeftArm": X, "LeftForeArm": X, "LeftHand": X,
             "RightShoulder": -X, "RightArm": -X, "RightForeArm": -X, "RightHand": -X,
             "LeftUpLeg": -Y, "LeftLeg": -Y, "LeftFoot": Z, "LeftToeBase": Z,
             "RightUpLeg": -Y, "RightLeg": -Y, "RightFoot": Z, "RightToeBase": Z}


def rest_dir(b, joint):
    """direction joint -> (main) child joint in the BVH rest pose (rest rotations are identity)."""
    I = b.idx
    child = {"LowerBack": ["Spine"], "Spine": ["Spine1"], "Spine1": ["Neck", "Neck1"], "Neck": ["Neck1"],
             "Neck1": ["Head"], "LeftShoulder": ["LeftArm"], "LeftArm": ["LeftForeArm"],
             "LeftForeArm": ["LeftHand"], "LeftFingerBase": ["LeftHandIndex1"],
             "RightShoulder": ["RightArm"], "RightArm": ["RightForeArm"], "RightForeArm": ["RightHand"],
             "RightFingerBase": ["RightHandIndex1"],
             "LeftUpLeg": ["LeftLeg"], "LeftLeg": ["LeftFoot"], "LeftFoot": ["LeftToeBase"],
             "RightUpLeg": ["RightLeg"], "RightLeg": ["RightFoot"], "RightFoot": ["RightToeBase"]}
    if joint in ("Head", "LeftToeBase", "RightToeBase"):
        return b.ends[I[joint]]
    return sum(b.offsets[I[c]] for c in child[joint])


def canonical(b):
    """W_canonical (3x3) per cgspeed joint used (rest world rotation = identity, pre-multiplied by swing)."""
    out = {}
    for mb, src in SRC.items():
        for s in (src if isinstance(src, tuple) else (src,)):
            cd = CANON_DIR[mb if s != "Neck1" else "Neck1"]
            out[s] = np.eye(3) if cd is None else B.swing(rest_dir(b, s), cd)
    return out


def bone_lengths(b):
    """lengths (m) for the canonical preview skeleton (Mixamo topology)."""
    U = B.UNIT; o = lambda n: b.offsets[b.idx[n]]
    L = {}
    L['hipL'] = o('LeftUpLeg') * U; L['hipR'] = o('RightUpLeg') * U
    L['Spine'] = np.linalg.norm(o('Spine')) * U
    L['Spine1'] = np.linalg.norm(o('Spine1')) * U
    L['Neck'] = (np.linalg.norm(o('Neck1')) + np.linalg.norm(o('Head'))) * U
    L['Head'] = np.linalg.norm(b.ends[b.idx['Head']]) * U
    for s in 'Left', 'Right':
        L[s + 'Shoulder'] = np.linalg.norm(o(s + 'Arm')) * U
        L[s + 'Arm'] = np.linalg.norm(o(s + 'ForeArm')) * U
        L[s + 'ForeArm'] = np.linalg.norm(o(s + 'Hand')) * U
        L[s + 'Hand'] = (np.linalg.norm(o(s + 'HandIndex1')) + np.linalg.norm(b.ends[b.idx[s + 'HandIndex1']])) * U
        L[s + 'UpLeg'] = np.linalg.norm(o(s + 'Leg')) * U
        L[s + 'Leg'] = np.linalg.norm(o(s + 'Foot')) * U
        L[s + 'Foot'] = np.linalg.norm(o(s + 'ToeBase')) * U
        L[s + 'ToeBase'] = np.linalg.norm(b.ends[b.idx[s + 'ToeBase']]) * U
    return L


def stand_hip_height(b):
    """hip (root) height of the subject standing straight, ankle->sole included (m)."""
    L = bone_lengths(b)
    ft = b.offsets[b.idx['LeftToeBase']]
    ankle = -ft[1] * B.UNIT  # toe-base is roughly on the floor; ankle height above it
    return (-L['hipL'][1] + L['LeftUpLeg'] + L['LeftLeg']) + ankle


def heading_of(R_hips):
    f = R_hips[..., :, 2]  # hips forward axis (+Z in rest)
    return np.arctan2(f[..., 0], f[..., 2])


def compute(b, frames):
    """world-delta quats q[F,22,4] (BVH world frame, no heading fix), hips pos (m) [F,3], joint pos (m)."""
    R, P = B.fk(b, frames)
    C = canonical(b)
    F = len(frames)
    q = np.zeros((F, len(BONES), 4))
    for k, mb in enumerate(BONES):
        src = SRC[mb]
        if isinstance(src, tuple):
            qa = B.mat2quat(R[:, b.idx[src[0]]] @ C[src[0]].T)
            qb = B.mat2quat(R[:, b.idx[src[1]]] @ C[src[1]].T)
            q[:, k] = B.slerp(qa, qb, 0.5)
        else:
            q[:, k] = B.mat2quat(R[:, b.idx[src]] @ C[src].T)
    return q, P[:, 0] * B.UNIT, P * B.UNIT, R
