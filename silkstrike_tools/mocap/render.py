"""PIL stick-figure contact sheets. Front view: camera in front of the character (character faces +Z
toward the viewer), so character-left (+X) appears on the image RIGHT. Side view: looking from the
character's right side toward -X... (+Z to the image RIGHT)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BLUE = (40, 90, 230); RED = (220, 40, 40); GRAY = (60, 60, 60); GREEN = (20, 150, 60)

BVH_SEGS = [("Hips", "LeftUpLeg", BLUE), ("LeftUpLeg", "LeftLeg", BLUE), ("LeftLeg", "LeftFoot", BLUE), ("LeftFoot", "LeftToeBase", BLUE),
            ("Hips", "RightUpLeg", RED), ("RightUpLeg", "RightLeg", RED), ("RightLeg", "RightFoot", RED), ("RightFoot", "RightToeBase", RED),
            ("Hips", "Spine", GRAY), ("Spine", "Spine1", GRAY), ("Spine1", "Neck1", GRAY), ("Neck1", "Head", GRAY), ("Head", "HeadEnd", GRAY),
            ("Spine1", "LeftArm", BLUE), ("LeftArm", "LeftForeArm", BLUE), ("LeftForeArm", "LeftHand", BLUE), ("LeftHand", "LeftHandIndex1", GREEN),
            ("Spine1", "RightArm", RED), ("RightArm", "RightForeArm", RED), ("RightForeArm", "RightHand", RED), ("RightHand", "RightHandIndex1", GREEN)]


def sheet(cells, segs, out, cols=6, cell=170, span=2.2, views=('front', 'side'), floor=True):
    """cells: list of (label, {name: xyz (m, character frame: +Y up, faces +Z, left=+X)})."""
    nv = len(views)
    rows = (len(cells) + cols - 1) // cols
    W, H = cols * cell * nv, rows * (cell + 14)
    img = Image.new('RGB', (W, H), (250, 250, 247))
    d = ImageDraw.Draw(img)
    for i, (label, J) in enumerate(cells):
        cx0 = (i % cols) * cell * nv; cy0 = (i // cols) * (cell + 14)
        ref = J.get('Hips', np.zeros(3))
        for v, view in enumerate(views):
            ox = cx0 + v * cell; oy = cy0 + 14
            d.rectangle([ox, oy, ox + cell - 1, oy + cell - 1], outline=(200, 200, 200))
            sc = cell / span

            def pr(p):
                if view == 'front':
                    h = p[0] - ref[0]          # +X (char left) -> image right
                elif view == 'side':
                    h = p[2] - ref[2]          # +Z (forward) -> image right
                else:  # top: +X (char left) -> image right, +Z (forward) -> image up
                    return (ox + cell / 2 + (p[0] - ref[0]) * sc, oy + cell / 2 - (p[2] - ref[2]) * sc)
                return (ox + cell / 2 + h * sc, oy + cell - 8 - p[1] * sc)
            if floor and view != 'top':
                d.line([ox, oy + cell - 8, ox + cell, oy + cell - 8], fill=(170, 170, 170))
            for a, b, c in segs:
                if a in J and b in J:
                    d.line([pr(J[a]), pr(J[b])], fill=c, width=3)
            if 'Head' in J:
                x, y = pr(J['HeadEnd'] if 'HeadEnd' in J else J['Head'])
                d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=GRAY, width=2)
            d.text((ox + 3, oy + 2), view[0], fill=(120, 120, 120))
        d.text((cx0 + 3, cy0 + 1), label, fill=(0, 0, 0))
    img.save(out)
    return out
