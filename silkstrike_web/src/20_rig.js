// =====================================================================
//  Figuren: prozeduraler Körper, Animationen, Materialzustände, Zerstückelung
// =====================================================================
const BUILD = { lean: [0.92, 0.95], athletic: [1, 1], heavy: [1.25, 1.12], giant: [1.38, 1.2] };

function lookFor(cast) {
  if (cast === 'darksuit') return ROSTER.cast.heroDarkSuitLook;
  if (cast === 'lena') return ROSTER.cast.lenaLook;
  if (cast === 'morgrim') return ROSTER.cast.morgrimLook;
  if (cast === 'civilian') return ROSTER.cast.civilianLook;
  if (cast === 'cultist') return CULTIST_LOOK;
  const f = ROSTER.fighters[cast];
  return f ? f.look : ROSTER.fighters.silkstrike.look;
}
function castName(cast) {
  if (!cast) return '';
  if (cast === 'darksuit') return 'Silkstrike';
  if (cast === 'lena') return 'Dr. Lena Hart';
  if (cast === 'morgrim') return 'Morgrim';
  if (cast === 'civilian') return 'Passantin';
  const f = ROSTER.fighters[cast];
  return f ? f.name : cast;
}
const CULTIST_LOOK = { build: 'athletic', height: 1.8, skin: '#8c6b5c', primary: '#470508', secondary: '#0d0d10', glow: '#ff2a1a', metal: 0.1, rough: 0.75, mask: true, eyes: 'glow', acc: ['hood'] };

// One-Shot-Längen (Sekunden)
const CLIP_LEN = { punch: 0.32, punch2: 0.36, kick: 0.45, kick2: 0.5, uppercut: 0.5, sweep: 0.5, jumpKick: 0.5, hitHigh: 0.35, hitLow: 0.35,
  knockdown: 0.7, getUp: 0.6, grab: 0.4, throwToss: 0.6, cast: 0.45, dashStrike: 0.4, webShoot: 0.3, zip: 0.4, land: 0.25, jump: 0.35,
  victory: 1.6, taunt: 1.2, point: 1.0, kneel: 1.0, celebrate: 1.6, defeat: 1.4 };
const LOOPS = new Set(['idle', 'fightIdle', 'crouch', 'walkForward', 'walkBack', 'run', 'sprint', 'fall', 'swing', 'wallRun', 'perch', 'dive', 'block', 'lieDown', 'dizzy', 'talk', 'crossArms', 'lookAround']);
const JOINTS = ['hips', 'spine', 'chest', 'neck', 'head', 'lUpper', 'lFore', 'lHand', 'rUpper', 'rFore', 'rHand', 'lThigh', 'lShin', 'lFoot', 'rThigh', 'rShin', 'rFoot'];

// Posen: {joint: [x,y,z]}, y = Hüft-Höhenversatz (m), rx = Körperneigung
// Konvention: Arm/Bein nach vorn = negative X-Rotation, Knie beugen = positive X-Rotation am Unterschenkel
function P(o) { return o; }
const S = Math.sin, C = Math.cos;
const POSES = {
  idle: (t) => P({ chest: [0.02 * S(t * 2), 0, 0], lUpper: [0.05, 0, 0.12], rUpper: [0.05, 0, -0.12], lFore: [-0.15, 0, 0], rFore: [-0.15, 0, 0], head: [0.03 * S(t * 1.3), 0.1 * S(t * 0.4), 0] }),
  fightIdle: (t) => { const b = S(t * 5) * 0.025; return P({ y: -0.06 + b, spine: [0.12, 0.35, 0], chest: [0.05, 0.15, 0], head: [-0.05, -0.45, 0], lUpper: [-0.9, 0, 0.35], lFore: [-1.6, 0, 0], rUpper: [-0.6, 0, -0.3], rFore: [-1.8, 0, 0], lThigh: [-0.35, 0, 0.12], lShin: [0.45, 0, 0], rThigh: [0.25, 0, -0.12], rShin: [0.35, 0, 0] }); },
  crouch: () => P({ y: -0.42, spine: [0.35, 0, 0], lThigh: [-1.3, 0, 0.15], rThigh: [-1.3, 0, -0.15], lShin: [2.0, 0, 0], rShin: [2.0, 0, 0], lFoot: [-0.6, 0, 0], rFoot: [-0.6, 0, 0], lUpper: [-0.9, 0, 0.3], rUpper: [-0.9, 0, -0.3], lFore: [-1.4, 0, 0], rFore: [-1.4, 0, 0] }),
  walkForward: (t) => { const w = S(t * 7); return P({ y: Math.abs(w) * 0.03 - 0.04, spine: [0.1, 0.3, 0], lThigh: [-0.5 * w - 0.2, 0, 0.1], rThigh: [0.5 * w - 0.2, 0, -0.1], lShin: [0.4 + 0.3 * Math.max(0, w), 0, 0], rShin: [0.4 + 0.3 * Math.max(0, -w), 0, 0], lUpper: [-0.9, 0, 0.35], lFore: [-1.6, 0, 0], rUpper: [-0.6, 0, -0.3], rFore: [-1.8, 0, 0], head: [0, -0.3, 0] }); },
  walkBack: (t) => POSES.walkForward(-t),
  run: (t) => { const w = S(t * 10), w2 = C(t * 10); return P({ y: Math.abs(w2) * 0.07 - 0.03, spine: [0.25, 0.12 * w, 0], chest: [0.05, -0.15 * w, 0], lThigh: [-1.0 * w - 0.15, 0, 0.05], rThigh: [1.0 * w - 0.15, 0, -0.05], lShin: [0.5 + 0.9 * Math.max(0, w), 0, 0], rShin: [0.5 + 0.9 * Math.max(0, -w), 0, 0], lUpper: [0.9 * w, 0, 0.12], rUpper: [-0.9 * w, 0, -0.12], lFore: [-1.3, 0, 0], rFore: [-1.3, 0, 0] }); },
  sprint: (t) => { const p = POSES.run(t * 1.3); p.spine = [0.45, p.spine[1], 0]; p.lUpper = [p.lUpper[0] + 0.5, 0, 0.6]; p.rUpper = [p.rUpper[0] + 0.5, 0, -0.6]; p.lFore = [-0.4, 0, 0]; p.rFore = [-0.4, 0, 0]; return p; },
  jump: (t, p) => P({ y: -0.1 * (1 - p), spine: [0.15, 0, 0], lThigh: [-1.1, 0, 0.1], lShin: [1.4, 0, 0], rThigh: [-0.3, 0, -0.1], rShin: [0.6, 0, 0], lUpper: [-2.6, 0, 0.3], rUpper: [-0.5, 0, -0.5], lFore: [-0.3, 0, 0], rFore: [-0.8, 0, 0] }),
  fall: (t) => P({ spine: [0.1, 0, 0], lThigh: [-0.7, 0, 0.15], lShin: [1.0, 0, 0], rThigh: [-0.2, 0, -0.15], rShin: [0.5, 0, 0], lUpper: [-0.3, 0, 1.2 + 0.1 * S(t * 6)], rUpper: [-0.3, 0, -1.2 - 0.1 * S(t * 6)], lFore: [-0.4, 0, 0], rFore: [-0.4, 0, 0] }),
  land: (t, p) => P({ y: -0.35 * (1 - p), spine: [0.5 * (1 - p), 0, 0], lThigh: [-1.2 * (1 - p), 0, 0.2], rThigh: [-1.2 * (1 - p), 0, -0.2], lShin: [1.8 * (1 - p), 0, 0], rShin: [1.8 * (1 - p), 0, 0], lUpper: [-0.4, 0, 0.8], rUpper: [-0.4, 0, -0.8] }),
  swing: (t) => P({ spine: [-0.1, 0, 0], rUpper: [-3.0, 0, -0.15], rFore: [-0.1, 0, 0], lUpper: [-0.4, 0, 0.9 + 0.1 * S(t * 3)], lFore: [-1.0, 0, 0], lThigh: [-1.3, 0, 0.1], lShin: [1.9, 0, 0], rThigh: [-0.5, 0, -0.1], rShin: [0.9, 0, 0], head: [-0.2, 0, 0] }),
  webShoot: (t, p) => P({ rUpper: [-1.55, 0, -0.1], rFore: [0, 0, 0], lUpper: [-0.5, 0, 0.4], lFore: [-1.2, 0, 0], spine: [0.05, -0.3, 0] }),
  zip: (t, p) => P({ spine: [0.3, 0, 0], rUpper: [-2.2, 0, -0.1], lUpper: [-2.2, 0, 0.1], lThigh: [-0.4, 0, 0.1], rThigh: [-0.2, 0, -0.1], lShin: [0.9, 0, 0], rShin: [0.6, 0, 0] }),
  wallRun: (t) => { const w = S(t * 9); return P({ spine: [-0.3, 0, 0], lThigh: [-1.4 - 0.5 * w, 0, 0.1], rThigh: [-1.4 + 0.5 * w, 0, -0.1], lShin: [1.4, 0, 0], rShin: [1.4, 0, 0], lUpper: [-2.4 + 0.6 * w, 0, 0.3], rUpper: [-2.4 - 0.6 * w, 0, -0.3] }); },
  perch: (t) => P({ y: -0.55, spine: [0.6, 0, 0], head: [-0.5, 0.2 * S(t * 0.5), 0], lThigh: [-1.9, 0, 0.35], rThigh: [-1.9, 0, -0.35], lShin: [2.5, 0, 0], rShin: [2.5, 0, 0], lUpper: [-0.6, 0, 0.5], rUpper: [-0.6, 0, -0.5], lFore: [-0.5, 0, 0], rFore: [-0.5, 0, 0] }),
  dive: (t) => P({ spine: [0.2, 0, 0], lUpper: [-0.1, 0, 1.4], rUpper: [-0.1, 0, -1.4], lThigh: [0.2, 0, 0.15 + 0.05 * S(t * 8)], rThigh: [0.2, 0, -0.15 - 0.05 * S(t * 8)], lShin: [0.3, 0, 0], rShin: [0.3, 0, 0], head: [-0.6, 0, 0] }),
  punch: (t, p) => { const k = p < 0.35 ? p / 0.35 : 1 - (p - 0.35) / 0.65; return P({ y: -0.06, spine: [0.15, -0.6 * k + 0.3, 0], chest: [0, -0.3 * k, 0], rUpper: [-0.6 - 0.95 * k, 0, -0.3 + 0.2 * k], rFore: [-1.8 + 1.75 * k, 0, 0], lUpper: [-0.9, 0, 0.35], lFore: [-1.6, 0, 0], lThigh: [-0.35, 0, 0.12], lShin: [0.45, 0, 0], rThigh: [0.25, 0, -0.12], rShin: [0.35, 0, 0] }); },
  punch2: (t, p) => { const k = p < 0.35 ? p / 0.35 : 1 - (p - 0.35) / 0.65; return P({ y: -0.06, spine: [0.15, 0.3 + 0.7 * k, 0], chest: [0, 0.3 * k, 0], lUpper: [-0.9 - 0.7 * k, 0, 0.35 - 0.2 * k], lFore: [-1.6 + 1.55 * k, 0, 0], rUpper: [-0.6, 0, -0.3], rFore: [-1.8, 0, 0], lThigh: [-0.45, 0, 0.12], lShin: [0.45, 0, 0], rThigh: [0.3, 0, -0.12], rShin: [0.3, 0, 0] }); },
  kick: (t, p) => { const k = p < 0.4 ? p / 0.4 : 1 - (p - 0.4) / 0.6; return P({ spine: [-0.2 * k, 0.4, -0.25 * k], rThigh: [-1.5 * k, 0, -0.2], rShin: [1.6 - 1.55 * k, 0, 0], lThigh: [0.1, 0, 0.1], lShin: [0.2, 0, 0], lUpper: [-0.9, 0, 0.6], rUpper: [-0.4, 0, -0.6], lFore: [-1.5, 0, 0], rFore: [-1.2, 0, 0] }); },
  kick2: (t, p) => { const k = p < 0.45 ? p / 0.45 : 1 - (p - 0.45) / 0.55; return P({ spine: [-0.3 * k, 0.4 + 1.1 * k, -0.35 * k], lThigh: [-0.5 * k, 0, 1.4 * k], lShin: [0.8 * (1 - k), 0, 0], rThigh: [0.15, 0, -0.1], rShin: [0.3, 0, 0], lUpper: [-0.3, 0, 0.9], rUpper: [-0.6, 0, -0.9] }); },
  uppercut: (t, p) => { const k = p < 0.3 ? -p / 0.3 : Math.min(1, (p - 0.3) / 0.25); return P({ y: k < 0 ? -0.3 * -k : 0.1 * k, spine: [0.4 - 0.6 * Math.max(0, k), -0.3, 0], rUpper: [-0.5 - 2.4 * Math.max(0, k), 0, -0.1], rFore: [-1.6 + 1.2 * Math.max(0, k), 0, 0], lUpper: [-0.9, 0, 0.35], lFore: [-1.6, 0, 0], lThigh: [-0.8 * (1 - Math.max(0, k)), 0, 0.1], rThigh: [-0.6 * (1 - Math.max(0, k)), 0, -0.1], lShin: [1.0, 0, 0], rShin: [0.9, 0, 0] }); },
  sweep: (t, p) => { const k = smooth(p / 0.5); return P({ y: -0.55, spine: [0.5, 1.2 * k - 0.6, 0], rThigh: [-1.2, 0, -0.9 - 0.4 * k], rShin: [0.1, 0, 0], lThigh: [-1.6, 0, 0.3], lShin: [2.2, 0, 0], lUpper: [-0.4, 0, 1.0], rUpper: [-0.5, 0, -0.9] }); },
  jumpKick: (t, p) => P({ spine: [-0.2, 0.5, 0], rThigh: [-1.4, 0, -0.2], rShin: [0.1, 0, 0], lThigh: [-0.9, 0, 0.1], lShin: [1.6, 0, 0], lUpper: [-0.6, 0, 1.0], rUpper: [-0.3, 0, -1.0] }),
  block: () => P({ y: -0.08, spine: [0.2, 0, 0], head: [0.25, 0, 0], lUpper: [-1.5, 0, -0.25], lFore: [-1.9, 0, 0], rUpper: [-1.5, 0, 0.25], rFore: [-1.9, 0, 0], lThigh: [-0.4, 0, 0.12], lShin: [0.55, 0, 0], rThigh: [0.2, 0, -0.12], rShin: [0.45, 0, 0] }),
  hitHigh: (t, p) => { const k = Math.sin(Math.PI * Math.min(1, p * 1.3)); return P({ spine: [-0.45 * k, 0.2 * k, 0], head: [-0.6 * k, 0.4 * k, 0], lUpper: [-0.3, 0, 0.9 * k], rUpper: [-0.3, 0, -0.9 * k], lThigh: [-0.2, 0, 0.1], rThigh: [0.25, 0, -0.1], lShin: [0.3, 0, 0], rShin: [0.4, 0, 0] }); },
  hitLow: (t, p) => { const k = Math.sin(Math.PI * Math.min(1, p * 1.3)); return P({ y: -0.15 * k, spine: [0.6 * k, 0, 0], head: [0.3 * k, 0, 0], lUpper: [-0.6, 0, 0.5], rUpper: [-0.6, 0, -0.5], lThigh: [-0.5 * k, 0, 0.1], lShin: [0.8 * k, 0, 0] }); },
  knockdown: (t, p) => { const k = smooth(p / 0.8); return P({ y: -0.78 * k, rx: -1.45 * k, spine: [-0.2 * k, 0, 0], head: [0.3 * k, 0, 0], lUpper: [-0.2, 0, 1.4 * k], rUpper: [-0.2, 0, -1.4 * k], lThigh: [-0.5 * (1 - k), 0, 0.2], rThigh: [-0.3 * k, 0, -0.2], lShin: [0.3, 0, 0], rShin: [0.8 * k, 0, 0] }); },
  lieDown: (t) => P({ y: -0.78, rx: -1.45, head: [0.3, 0.2 * S(t * 0.3), 0], lUpper: [-0.2, 0, 1.4], rUpper: [-0.2, 0, -1.4], rThigh: [-0.3, 0, -0.2], rShin: [0.8, 0, 0] }),
  getUp: (t, p) => { const k = 1 - smooth(p); return P({ y: -0.78 * k, rx: -1.45 * k, spine: [0.5 * (1 - k) * k * 4, 0, 0], lThigh: [-1.2 * k, 0, 0.2], rThigh: [-1.4 * k, 0, -0.2], lShin: [1.8 * k, 0, 0], rShin: [1.9 * k, 0, 0], lUpper: [-0.5, 0, 0.6], rUpper: [-0.5, 0, -0.6] }); },
  dizzy: (t) => P({ y: -0.05, rx: 0.1 * S(t * 2.3), spine: [0.25 + 0.1 * S(t * 3), 0.25 * S(t * 1.7), 0.15 * S(t * 2.1)], head: [0.3, 0.4 * S(t * 2.6), 0.25 * C(t * 1.9)], lUpper: [-0.1, 0, 0.25 + 0.1 * S(t * 2)], rUpper: [-0.1, 0, -0.25], lFore: [-0.3, 0, 0], rFore: [-0.3, 0, 0], lThigh: [-0.1, 0, 0.12], rThigh: [0.1, 0, -0.12], lShin: [0.3, 0, 0], rShin: [0.3, 0, 0] }),
  grab: (t, p) => P({ spine: [0.3, 0, 0], lUpper: [-1.5, 0, -0.1], rUpper: [-1.5, 0, 0.1], lFore: [-0.3, 0, 0], rFore: [-0.3, 0, 0], lThigh: [-0.4, 0, 0.1], lShin: [0.5, 0, 0] }),
  throwToss: (t, p) => { const k = smooth(p / 0.6); return P({ spine: [0.3 - 0.6 * k, 1.8 * k, 0], lUpper: [-1.5 - 1.0 * k, 0, 0.3 * k], rUpper: [-1.5 - 1.0 * k, 0, -0.3 * k], lThigh: [-0.4, 0, 0.1], rThigh: [0.3, 0, -0.1] }); },
  cast: (t, p) => { const k = smooth(p / 0.5); return P({ spine: [-0.1 * k, 0, 0], lUpper: [-1.6 * k, 0, 0.3], rUpper: [-1.6 * k, 0, -0.3], lFore: [-0.2, 0, 0], rFore: [-0.2, 0, 0], lThigh: [-0.4, 0, 0.15], lShin: [0.5, 0, 0], rThigh: [0.3, 0, -0.15] }); },
  dashStrike: (t, p) => P({ y: -0.12, spine: [0.5, -0.4, 0], rUpper: [-1.6, 0, -0.2], rFore: [-0.1, 0, 0], lUpper: [0.5, 0, 0.6], lThigh: [-1.0, 0, 0.1], lShin: [1.0, 0, 0], rThigh: [0.6, 0, -0.1], rShin: [0.4, 0, 0] }),
  victory: (t, p) => { const k = smooth(p / 0.4); return P({ spine: [-0.15 * k, 0, 0], head: [-0.25 * k, 0, 0], rUpper: [-3.0 * k, 0, -0.2], rFore: [-0.2, 0, 0], lUpper: [-0.3, 0, 0.5 * k], lFore: [-1.6 * k, 0, 0], lThigh: [-0.1, 0, 0.18], rThigh: [0.05, 0, -0.18] }); },
  celebrate: (t, p) => P({ y: 0.05 * Math.abs(S(t * 6)), lUpper: [-2.8, 0, 0.5], rUpper: [-2.8, 0, -0.5], lFore: [-0.3, 0, 0], rFore: [-0.3, 0, 0], head: [-0.3, 0, 0] }),
  taunt: (t, p) => P({ spine: [-0.1, 0.3 * S(t * 3), 0], head: [-0.2, 0.3 * S(t * 3), 0], rUpper: [-1.2, 0, -0.4], rFore: [-1.4 - 0.4 * S(t * 12), 0, 0], lUpper: [-0.2, 0, 0.4], lThigh: [-0.2, 0, 0.15], rThigh: [0.1, 0, -0.15] }),
  point: (t, p) => P({ rUpper: [-1.55, 0.2, -0.1], rFore: [0, 0, 0], lUpper: [0.05, 0, 0.15], head: [-0.05, -0.15, 0] }),
  kneel: (t, p) => { const k = smooth(p / 0.6); return P({ y: -0.48 * k, spine: [0.45 * k, 0, 0], head: [0.4 * k, 0, 0], lThigh: [-1.5 * k, 0, 0.12], lShin: [1.55 * k, 0, 0], rThigh: [0.2 * k, 0, -0.12], rShin: [2.0 * k, 0, 0], lUpper: [-0.5 * k, 0, 0.2], rUpper: [-0.2, 0, -0.25], lFore: [-0.8 * k, 0, 0] }); },
  talk: (t) => P({ rUpper: [-0.55 - 0.15 * S(t * 2.7), 0, -0.25], rFore: [-1.1 - 0.3 * S(t * 3.1), 0, 0], lUpper: [-0.2, 0, 0.15], lFore: [-0.5, 0, 0], head: [0.05 * S(t * 2), 0.12 * S(t * 1.3), 0] }),
  crossArms: (t) => P({ lUpper: [-0.6, 0, -0.35], lFore: [-1.9, 0.6, 0], rUpper: [-0.6, 0, 0.35], rFore: [-1.9, -0.6, 0], head: [-0.08, 0.06 * S(t * 0.7), 0], lThigh: [-0.05, 0, 0.18], rThigh: [0.05, 0, -0.18] }),
  lookAround: (t) => P({ head: [0, 0.7 * S(t * 0.9), 0], chest: [0, 0.2 * S(t * 0.9), 0], lUpper: [0.05, 0, 0.12], rUpper: [0.05, 0, -0.12], lFore: [-0.2, 0, 0], rFore: [-0.2, 0, 0] }),
  defeat: (t, p) => POSES.kneel(t, p),
};

class Rig {
  constructor(cast, quality) {
    this.cast = cast;
    this.look = lookFor(cast);
    this.quality = quality || Settings.data.quality;
    this.root = new THREE.Group();
    this.j = {};
    this.mats = [];
    this.clip = 'idle'; this.clipT = 0; this.clipDur = 1; this.prevPose = null; this.blendT = 1; this.blendDur = 0.1;
    this.flash = 0; this.flashColor = new THREE.Color(1, 1, 1);
    this.detached = []; this.stumps = []; this.dismembered = false;
    this.sway = []; this.override = null;
    this.matState = { kind: 'normal', amount: 0 };
    this.build();
    this.play('idle');
  }
  mat(color, rough, metal, emissive = null, ei = 0) {
    const m = new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness: rough, metalness: metal });
    if (emissive) { m.emissive = new THREE.Color(emissive); m.emissiveIntensity = ei; }
    m.userData.base = { color: m.color.clone(), rough, metal, emissive: m.emissive.clone(), ei: m.emissiveIntensity };
    this.mats.push(m);
    return m;
  }
  build() {
    const L = this.look;
    const [bw, bh] = BUILD[L.build] || BUILD.athletic;
    const s = L.height / 1.8;
    this.scale = s;
    this.height = L.height;
    const seg = this.quality === 'performance' ? 8 : (this.quality === 'ultra' ? 18 : 12);
    const suit = this.mat(L.primary, L.rough, L.metal);
    const trim = this.mat(L.secondary, Math.min(1, L.rough + 0.1), L.metal);
    const skin = this.mat(L.skin, 0.55, 0);
    const glow = this.mat('#050505', 0.4, 0, L.glow, 2.2);
    this.suitMat = suit; this.trimMat = trim; this.glowMat = glow;
    const isHuman = L.eyes === 'human';
    const headMat = (L.mask || !isHuman) ? suit : skin;
    const cap = (r, len, m) => { const g = new THREE.CapsuleGeometry(r, len, 4, seg); const me = new THREE.Mesh(g, m); me.position.y = -len / 2 - r * 0.2; me.castShadow = true; me.userData.body = true; return me; };
    const grp = (name, parent, x, y, z) => { const g = new THREE.Group(); g.position.set(x, y, z); parent.add(g); this.j[name] = g; g.userData.rest = g.position.clone(); g.userData.parent = parent; return g; };
    const R = this.root;
    const hips = grp('hips', R, 0, 0.98 * s, 0);
    const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.15 * s * bw, seg, seg), trim); pelvis.scale.set(1.25, 0.75, 0.85); hips.add(pelvis); pelvis.castShadow = true; pelvis.userData.body = true;
    const spine = grp('spine', hips, 0, 0.08 * s, 0);
    const abd = new THREE.Mesh(new THREE.CapsuleGeometry(0.135 * s * bw, 0.12 * s, 4, seg), suit); abd.position.y = 0.1 * s; abd.scale.set(1.15, 1, 0.8); spine.add(abd); abd.castShadow = true; abd.userData.body = true;
    const chest = grp('chest', spine, 0, 0.22 * s, 0);
    const torso = new THREE.Mesh(new THREE.SphereGeometry(0.215 * s * bw, seg, seg), suit); torso.scale.set(1.22, 1.08, 0.78); torso.position.y = 0.1 * s; chest.add(torso); torso.castShadow = true; torso.userData.body = true;
    const neck = grp('neck', chest, 0, 0.28 * s, 0);
    const neckM = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * s * bw, 0.06 * s * bw, 0.1 * s, seg), headMat); neckM.position.y = 0.03 * s; neck.add(neckM); neckM.userData.body = true;
    const head = grp('head', neck, 0, 0.1 * s, 0);
    const skull = new THREE.Mesh(new THREE.SphereGeometry(0.115 * s, seg + 4, seg + 4), headMat); skull.scale.set(0.9, 1.08, 0.98); skull.position.y = 0.09 * s; head.add(skull); skull.castShadow = true; skull.userData.body = true;
    // Augen
    if (L.eyes === 'lenses') {
      const lensMat = this.mat('#ffffff', 0.2, 0, L.glow, 1.3);
      for (const sx of [-1, 1]) { const e = new THREE.Mesh(new THREE.SphereGeometry(0.038 * s, 12, 8), lensMat); e.scale.set(1.2, 0.75, 0.35); e.position.set(sx * 0.042 * s, 0.11 * s, 0.098 * s); e.rotation.z = sx * 0.5; head.add(e); e.userData.face = true; }
    } else if (L.eyes === 'glow') {
      for (const sx of [-1, 1]) { const e = new THREE.Mesh(new THREE.SphereGeometry(0.014 * s, 8, 6), glow); e.position.set(sx * 0.038 * s, 0.11 * s, 0.1 * s); head.add(e); e.userData.face = true; }
    } else if (L.eyes === 'visor') {
      const v = new THREE.Mesh(new THREE.BoxGeometry(0.17 * s, 0.03 * s, 0.05 * s), glow); v.position.set(0, 0.11 * s, 0.09 * s); head.add(v); v.userData.face = true;
    } else {
      const eyeM = this.mat('#1a1410', 0.3, 0);
      for (const sx of [-1, 1]) { const e = new THREE.Mesh(new THREE.SphereGeometry(0.012 * s, 8, 6), eyeM); e.position.set(sx * 0.038 * s, 0.11 * s, 0.1 * s); head.add(e); e.userData.face = true; }
      if (L.hair) { const hairM = this.mat(L.hair, 0.8, 0); const hair = new THREE.Mesh(new THREE.SphereGeometry(0.122 * s, seg, seg, 0, TAU, 0, Math.PI * 0.55), hairM); hair.position.y = 0.1 * s; hair.rotation.x = -0.25; head.add(hair); hair.userData.face = true; }
    }
    // Arme
    const armR = 0.062 * s * bw;
    const lineMat = this.mat('#15161a', 0.4, 0.3, L.glow, 0.45);
    for (const side of ['l', 'r']) {
      const sx = side === 'l' ? 1 : -1;
      const up = grp(side + 'Upper', chest, sx * 0.21 * s * bw, 0.19 * s, 0);
      const shoulder = new THREE.Mesh(new THREE.SphereGeometry(armR * 1.35, seg, seg), trim); up.add(shoulder); shoulder.userData.body = true;
      up.add(cap(armR, 0.22 * s, suit));
      const fore = grp(side + 'Fore', up, 0, -0.3 * s, 0);
      fore.add(cap(armR * 0.88, 0.2 * s, side === 'r' && L.acc.includes('cyberArm') ? this.mat('#9aa3ad', 0.25, 0.9) : trim));
      const hand = grp(side + 'Hand', fore, 0, -0.27 * s, 0);
      const handM = new THREE.Mesh(new THREE.SphereGeometry(armR * 0.95, seg, seg), L.mask ? trim : skin); handM.scale.set(0.9, 1.2, 0.7); handM.position.y = -0.04 * s; hand.add(handM); handM.userData.body = true;
      if (L.acc.includes('chainBlades')) { const bl = new THREE.Mesh(new THREE.BoxGeometry(0.02 * s, 0.32 * s, 0.07 * s), this.mat('#b8bec6', 0.15, 1)); bl.position.set(sx * 0.05 * s, -0.12 * s, -0.02); fore.add(bl); }
      if (L.acc.includes('shoulderPads')) { const pad = new THREE.Mesh(new THREE.SphereGeometry(armR * 2.1, seg, seg, 0, TAU, 0, Math.PI / 2), this.mat(L.secondary, 0.35, 0.8)); pad.position.y = 0.02; up.add(pad); }
      if (L.acc.includes('spikes')) { const sp = new THREE.Mesh(new THREE.ConeGeometry(0.03 * s, 0.14 * s, 5), this.mat('#1b1b1f', 0.3, 0.8)); sp.position.y = 0.07 * s; up.add(sp); }
      if (L.acc.includes('webLines')) { for (const yy of [-0.08, -0.2]) { const ring = new THREE.Mesh(new THREE.TorusGeometry(armR * 1.02, 0.005 * s, 4, seg), lineMat); ring.rotation.x = Math.PI / 2; ring.position.y = yy * s; up.add(ring); ring.userData.body = true; } }
    }
    // Beine
    const legR = 0.084 * s * bw;
    for (const side of ['l', 'r']) {
      const sx = side === 'l' ? 1 : -1;
      const th = grp(side + 'Thigh', hips, sx * 0.1 * s * bw, -0.04 * s, 0);
      th.add(cap(legR, 0.34 * s * bh, suit));
      const sh = grp(side + 'Shin', th, 0, -0.45 * s * bh, 0);
      sh.add(cap(legR * 0.8, 0.33 * s * bh, trim));
      const ft = grp(side + 'Foot', sh, 0, -0.44 * s * bh, 0);
      const foot = new THREE.Mesh(new THREE.BoxGeometry(0.09 * s, 0.06 * s, 0.22 * s), trim); foot.position.set(0, -0.03 * s, 0.05 * s); ft.add(foot); foot.castShadow = true; foot.userData.body = true;
    }
    // Zubehör
    const A = L.acc;
    if (A.includes('webLines')) {
      const emb = new THREE.Mesh(new THREE.CircleGeometry(0.05 * s, 6), glow); emb.position.set(0, 0.13 * s, 0.15 * s * bw); chest.add(emb);
    }
    if (A.includes('horns')) for (const sx of [-1, 1]) { const h = new THREE.Mesh(new THREE.ConeGeometry(0.025 * s, 0.16 * s, 6), this.mat('#1a0d08', 0.4, 0.2)); h.position.set(sx * 0.07 * s, 0.2 * s, 0); h.rotation.z = -sx * 0.5; head.add(h); }
    if (A.includes('crown')) { const cr = new THREE.Mesh(new THREE.CylinderGeometry(0.11 * s, 0.1 * s, 0.07 * s, 8, 1, true), this.mat('#16120f', 0.3, 0.9)); cr.position.y = 0.2 * s; head.add(cr); for (let k = 0; k < 6; k++) { const sp = new THREE.Mesh(new THREE.ConeGeometry(0.015 * s, 0.09 * s, 4), cr.material); const a = k / 6 * TAU; sp.position.set(Math.sin(a) * 0.1 * s, 0.27 * s, Math.cos(a) * 0.1 * s); head.add(sp); } }
    if (A.includes('hood')) { const hd = new THREE.Mesh(new THREE.SphereGeometry(0.135 * s, seg, seg, 0, TAU, 0, Math.PI * 0.6), trim); hd.position.y = 0.09 * s; hd.rotation.x = -0.35; head.add(hd); }
    if (A.includes('katana')) { const k = new THREE.Mesh(new THREE.BoxGeometry(0.03 * s, 0.85 * s, 0.015 * s), this.mat('#d6dbe2', 0.12, 1)); k.position.set(0, 0.05, -0.16 * s); k.rotation.z = 0.7; chest.add(k); }
    if (A.includes('cape') || A.includes('scarf') || A.includes('labCoat')) {
      const isCoat = A.includes('labCoat');
      const len = (isCoat ? 0.55 : (A.includes('cape') ? 1.0 : 0.6)) * s;
      const wdt = (isCoat ? 0.38 : (A.includes('cape') ? 0.5 : 0.12)) * s * bw;
      const segs = 4;
      let parent = A.includes('scarf') && !A.includes('cape') ? neck : chest;
      const m = isCoat ? this.mat('#e8ecef', 0.8, 0) : this.mat(A.includes('cape') ? '#5a0a10' : L.secondary, 0.8, 0);
      m.side = THREE.DoubleSide;
      let y0 = isCoat ? -0.08 * s : 0.25 * s;
      const chain = [];
      for (let k = 0; k < segs; k++) {
        const g = new THREE.Group();
        g.position.set(0, k === 0 ? y0 : -len / segs, k === 0 ? -0.13 * s * bw : 0);
        const pl = new THREE.Mesh(new THREE.PlaneGeometry(wdt, len / segs), m);
        pl.position.y = -len / segs / 2; pl.castShadow = true;
        g.add(pl); parent.add(g); parent = g; chain.push(g);
      }
      this.sway.push(chain);
    }
    if (A.includes('tendrils')) {
      const tm = this.mat('#050407', 0.15, 0.3, L.glow, 0.4);
      for (let k = 0; k < 4; k++) {
        const t = new THREE.Mesh(new THREE.CylinderGeometry(0.004 * s, 0.018 * s, 0.6 * s, 5), tm);
        const g = new THREE.Group(); g.position.set((k - 1.5) * 0.06 * s, 0.15 * s, -0.12 * s); t.position.y = 0.3 * s; g.add(t); chest.add(g);
        g.userData.phase = k * 1.7; this.sway.push([g]);
        g.userData.tendril = true;
      }
    }
    if (A.includes('flameAura')) this.flame = true;
    this.root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  }
  play(clip, dur = null, restart = false, blend = 0.1) {
    if (!POSES[clip]) clip = 'idle';
    if (clip === this.clip && !restart) return;
    this.prevPose = this.currentPose || null;
    this.blendT = 0; this.blendDur = blend;
    this.clip = clip; this.clipT = 0;
    this.clipDur = LOOPS.has(clip) ? 1 : (dur || CLIP_LEN[clip] || 0.5);
  }
  get finished() { return !LOOPS.has(this.clip) && this.clipT >= this.clipDur; }
  get progress() { return LOOPS.has(this.clip) ? 0 : clamp(this.clipT / this.clipDur, 0, 1); }
  update(dt) {
    this.clipT += dt;
    const p = LOOPS.has(this.clip) ? 0 : clamp(this.clipT / this.clipDur, 0, 1);
    let pose = POSES[this.clip](this.clipT, p);
    if (this.override) pose = this.addPose(pose, this.override);
    if (this.prevPose && this.blendT < this.blendDur) {
      this.blendT += dt;
      pose = this.blendPose(this.prevPose, pose, smooth(this.blendT / Math.max(0.001, this.blendDur)));
    }
    this.currentPose = pose;
    this.apply(pose);
    // Stoff/Ranken
    const t = Game.time;
    for (const chain of this.sway) {
      chain.forEach((g, i) => {
        if (g.userData.tendril) { g.rotation.set(-0.6 + 0.4 * Math.sin(t * 2 + g.userData.phase), 0, 0.5 * Math.sin(t * 1.6 + g.userData.phase)); }
        else g.rotation.x = 0.12 + 0.08 * Math.sin(t * 3 + i) + (i === 0 ? 0.15 : 0.05);
      });
    }
    if (this.flash > 0) {
      this.flash = Math.max(0, this.flash - dt * 7);
      for (const m of this.mats) { m.emissive.copy(m.userData.base.emissive).lerp(this.flashColor, this.flash); m.emissiveIntensity = Math.max(m.userData.base.ei, this.flash * 2); }
    }
    if (this.flame && Math.random() < dt * 30 && !this.root.visible === false) {
      const hp = this.worldPos(Math.random() < 0.5 ? 'lHand' : 'rHand');
      FX.emberAt(hp);
    }
    this.updateDebris(dt);
  }
  addPose(a, b) {
    const o = Object.assign({}, a);
    for (const k in b) { if (Array.isArray(b[k])) { const x = a[k] || [0, 0, 0]; o[k] = [x[0] + b[k][0], x[1] + b[k][1], x[2] + b[k][2]]; } else o[k] = (a[k] || 0) + b[k]; }
    return o;
  }
  blendPose(a, b, t) {
    const o = {};
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      const x = a[k], y = b[k];
      if (Array.isArray(x) || Array.isArray(y)) { const xa = x || [0, 0, 0], ya = y || [0, 0, 0]; o[k] = [lerp(xa[0], ya[0], t), lerp(xa[1], ya[1], t), lerp(xa[2], ya[2], t)]; }
      else o[k] = lerp(x || 0, y || 0, t);
    }
    return o;
  }
  apply(pose) {
    for (const n of JOINTS) { const g = this.j[n]; if (!g || g.userData.detached) continue; const r = pose[n]; if (r) g.rotation.set(r[0], r[1], r[2]); else g.rotation.set(0, 0, 0); }
    const h = this.j.hips;
    h.position.y = h.userData.rest.y + (pose.y || 0) * this.scale;
    h.rotation.x = (pose.rx || 0) + (pose.hips ? pose.hips[0] : 0);
  }
  flashHit(color = 0xffffff) { this.flash = 1; this.flashColor.set(color); }
  worldPos(n, out = new V3()) { const g = this.j[n]; if (!g) return this.root.getWorldPosition(out); return g.getWorldPosition(out); }
  setMaterialState(kind, amount) {
    this.matState = { kind, amount };
    const target = kind === 'charred' ? new THREE.Color(0.03, 0.02, 0.02) : kind === 'shadow' ? new THREE.Color(0.01, 0.0, 0.02) : kind === 'frozen' ? new THREE.Color(0.55, 0.75, 0.95) : null;
    for (const m of this.mats) {
      const b = m.userData.base;
      if (!target || amount <= 0) { m.color.copy(b.color); m.roughness = b.rough; m.emissive.copy(b.emissive); m.emissiveIntensity = b.ei; continue; }
      m.color.copy(b.color).lerp(target, amount);
      if (kind === 'charred') { m.roughness = lerp(b.rough, 1, amount); m.emissive.set(0xff4a10); m.emissiveIntensity = 0.6 * amount * (0.5 + 0.5 * Math.random()); }
      if (kind === 'shadow') { m.roughness = 0.1; m.emissive.set(0x6a1aff); m.emissiveIntensity = 0.5 * amount; }
      if (kind === 'frozen') { m.roughness = 0.15; m.emissive.set(0x4ad0ff); m.emissiveIntensity = 0.5 * amount; }
    }
  }
  setLook(cast) {
    const parent = this.root.parent;
    const pos = this.root.position.clone(), rot = this.root.rotation.clone(), clip = this.clip;
    this.root.clear();
    this.cast = cast; this.look = lookFor(cast); this.j = {}; this.mats = []; this.sway = []; this.flame = false;
    this.build();
    this.root.position.copy(pos); this.root.rotation.copy(rot);
    this.play(clip, null, true, 0);
    if (parent) FX.burst('shadowBurst', this.worldPos('chest'), 1.2);
  }
  detach(limb, impulse, bloodOn = Settings.data.blood) {
    const map = { head: 'neck', leftArm: 'lUpper', rightArm: 'rUpper', leftLeg: 'lThigh', rightLeg: 'rThigh', upperBody: 'spine' };
    const g = this.j[map[limb]];
    const scene = this.root.parent;
    if (!g || g.userData.detached || !scene) return null;
    let sc = scene; while (sc.parent) sc = sc.parent;
    const stumpPos = g.getWorldPosition(new V3());
    g.userData.detached = true;
    g.userData.oldParent = g.parent;
    g.userData.oldPos = g.position.clone(); g.userData.oldRot = g.rotation.clone();
    sc.attach(g);
    const piece = { obj: g, v: impulse.clone(), w: new V3(rand(-8, 8), rand(-8, 8), rand(-8, 8)), life: 12, floor: this.floorY || 0 };
    this.detached.push(piece);
    this.dismembered = true;
    // Stumpf
    const stump = new THREE.Mesh(new THREE.SphereGeometry(0.06 * this.scale, 10, 8), pbr('#3a0004', 0.3, 0, '#2a0000', 0.4));
    g.userData.oldParent.add(stump);
    stump.position.copy(g.userData.oldPos);
    this.stumps.push(stump);
    if (bloodOn) {
      FX.burst('bloodSpray', stumpPos, 1.4, new V3(0, 1, 0));
      FX.pool(new V3(stumpPos.x, (this.floorY || 0) + 0.02, stumpPos.z), 1.0);
    } else FX.burst('sparks', stumpPos, 1.0);
    return piece;
  }
  detachAll(scale = 1, bloodOn = Settings.data.blood) {
    const c = this.worldPos('chest');
    for (const limb of ['head', 'leftArm', 'rightArm', 'leftLeg', 'rightLeg']) {
      const p = this.worldPos(limb === 'head' ? 'head' : limb === 'leftArm' ? 'lUpper' : limb === 'rightArm' ? 'rUpper' : limb === 'leftLeg' ? 'lThigh' : 'rThigh');
      const dir = p.clone().sub(c).normalize().multiplyScalar(4 * scale).add(new V3(0, 3 * scale, 0));
      this.detach(limb, dir, bloodOn);
    }
    const tor = this.detach('upperBody', new V3(rand(-1, 1), 2.5 * scale, rand(-1, 1)), bloodOn);
    if (bloodOn) { FX.burst('bloodBurst', c, 2 * scale); FX.pool(new V3(c.x, (this.floorY || 0) + 0.02, c.z), 1.6); }
    return tor;
  }
  updateDebris(dt) {
    for (let i = this.detached.length - 1; i >= 0; i--) {
      const d = this.detached[i];
      d.life -= dt;
      d.v.y -= 14 * dt;
      d.obj.position.addScaledVector(d.v, dt);
      d.obj.rotation.x += d.w.x * dt; d.obj.rotation.y += d.w.y * dt; d.obj.rotation.z += d.w.z * dt;
      if (d.obj.position.y < d.floor + 0.08) {
        d.obj.position.y = d.floor + 0.08;
        d.v.y = Math.abs(d.v.y) * 0.25; d.v.x *= 0.6; d.v.z *= 0.6; d.w.multiplyScalar(0.6);
        if (Math.abs(d.v.y) < 0.4) d.v.y = 0;
      }
      if (d.life <= 0) { d.obj.parent && d.obj.parent.remove(d.obj); this.detached.splice(i, 1); }
    }
  }
  resetBody() {
    for (const d of this.detached) {
      const g = d.obj;
      if (g.userData.oldParent) { g.userData.oldParent.add(g); g.position.copy(g.userData.oldPos); g.rotation.copy(g.userData.oldRot); }
      g.userData.detached = false;
    }
    for (const n in this.j) { const g = this.j[n]; if (g.userData.detached && g.userData.oldParent) { g.userData.oldParent.add(g); g.position.copy(g.userData.oldPos); } g.userData.detached = false; }
    this.detached = [];
    this.stumps.forEach((s) => s.parent && s.parent.remove(s));
    this.stumps = [];
    this.dismembered = false;
    this.root.visible = true;
    this.setMaterialState('normal', 0);
  }
}
