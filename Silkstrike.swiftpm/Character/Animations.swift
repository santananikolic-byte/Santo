import Foundation
import simd

// =====================================================================
//  SILKSTRIKE – Animationen
//  Gelenke, Posen und die komplette Clip-Bibliothek (alle AnimClip-Fälle).
//
//  Konventionen (Posen-Raum, Radiant):
//  - Rumpf-Gelenke (hips, spine, chest, neck, head):
//      x+ = nach vorne beugen (Kopf: nicken), y+ = Drehung zur EIGENEN linken Seite,
//      z+ = Neigung zur eigenen rechten Seite.
//  - Gliedmaßen (beide Seiten gespiegelt, gleiche Zahlen = symmetrische Bewegung):
//      x+ = Gliedende nach vorne schwingen (Arm/Bein heben, Ellbogen beugen),
//      Schienbein: x- = Knie beugen, Fuß: x+ = Zehen hoch, Hand: x+ = Handgelenk beugen,
//      z+ = abspreizen (vom Körper weg), y+ = nach außen drehen / horizontal nach außen schwingen.
//  - Rotationsreihenfolge je Gelenk: erst Roll (z), dann Pitch (x), dann Yaw (y) um die Elternachse.
//  - hipsOffset wird für eine 1,80-m-Figur angegeben und vom Rig mit der Körpergröße skaliert.
//  - Die Figur schaut lokal nach +Z, ihre linke Seite liegt bei +X.
//
//  Die Schlüsselposen wurden mit einem Vorwärtskinematik-Werkzeug erstellt und geprüft
//  (Füße auf dem Boden, Fäuste auf Kopfhöhe beim Schlag, Liegen auf dem Rücken usw.).
// =====================================================================

// MARK: - Gelenke

enum Joint: String, CaseIterable {
    case hips, spine, chest, neck, head
    case lUpperArm, lForearm, lHand, rUpperArm, rForearm, rHand
    case lThigh, lShin, lFoot, rThigh, rShin, rFoot

    /// +1 = linke Körperseite, -1 = rechte Körperseite, 0 = Körpermitte.
    var rigSide: Int {
        switch self {
        case .lUpperArm, .lForearm, .lHand, .lThigh, .lShin, .lFoot: return 1
        case .rUpperArm, .rForearm, .rHand, .rThigh, .rShin, .rFoot: return -1
        case .hips, .spine, .chest, .neck, .head: return 0
        }
    }

    /// Elterngelenk in der Hierarchie (nil = Hüfte hängt direkt am Wurzelknoten).
    var rigParent: Joint? {
        switch self {
        case .hips: return nil
        case .spine: return .hips
        case .chest: return .spine
        case .neck: return .chest
        case .head: return .neck
        case .lUpperArm, .rUpperArm: return .chest
        case .lForearm: return .lUpperArm
        case .rForearm: return .rUpperArm
        case .lHand: return .lForearm
        case .rHand: return .rForearm
        case .lThigh, .rThigh: return .hips
        case .lShin: return .lThigh
        case .rShin: return .rThigh
        case .lFoot: return .lShin
        case .rFoot: return .rShin
        }
    }

    /// Das gespiegelte Gelenk (links <-> rechts).
    var rigMirror: Joint {
        switch self {
        case .hips, .spine, .chest, .neck, .head: return self
        case .lUpperArm: return .rUpperArm
        case .lForearm: return .rForearm
        case .lHand: return .rHand
        case .rUpperArm: return .lUpperArm
        case .rForearm: return .lForearm
        case .rHand: return .lHand
        case .lThigh: return .rThigh
        case .lShin: return .rShin
        case .lFoot: return .rFoot
        case .rThigh: return .lThigh
        case .rShin: return .lShin
        case .rFoot: return .lFoot
        }
    }

    /// Wandelt eine Posen-Rotation in echte lokale Euler-Winkel des Gelenkknotens um.
    func rigRawEuler(_ e: SIMD3<Float>) -> SIMD3<Float> {
        switch rigSide {
        case 1: return SIMD3<Float>(-e.x, e.y, e.z)
        case -1: return SIMD3<Float>(-e.x, -e.y, -e.z)
        default: return e
        }
    }
}

// MARK: - Pose

/// Lokale Euler-Rotationen (Radiant) pro Gelenk + Versatz der Hüfte.
struct Pose {
    var rotations: [Joint: SIMD3<Float>]
    var hipsOffset: SIMD3<Float>

    init(_ rotations: [Joint: SIMD3<Float>] = [:], hipsOffset: SIMD3<Float> = .zero) {
        self.rotations = rotations
        self.hipsOffset = hipsOffset
    }

    /// Rotation eines Gelenks (fehlend = 0).
    subscript(_ j: Joint) -> SIMD3<Float> {
        get { return rotations[j] ?? SIMD3<Float>(0, 0, 0) }
        set { rotations[j] = newValue }
    }

    /// Lineare Mischung a -> b (t = 0 → a, t = 1 → b). Für weiche Übergänge t vorher glätten.
    static func blend(_ a: Pose, _ b: Pose, _ t: Float) -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            let va = a.rotations[j]
            let vb = b.rotations[j]
            if va == nil && vb == nil { continue }
            let x = va ?? SIMD3<Float>(0, 0, 0)
            let y = vb ?? SIMD3<Float>(0, 0, 0)
            out[j] = x + (y - x) * t
        }
        return Pose(out, hipsOffset: a.hipsOffset + (b.hipsOffset - a.hipsOffset) * t)
    }

    /// Wie blend, aber die Gier-Drehung (y) der Rumpfgelenke nimmt den kürzesten Weg (±π) –
    /// verhindert, dass nach einer vollen Drehung (z.B. Drehkick) beim Überblenden zurückgedreht wird.
    static func rigBlendShortest(_ a: Pose, _ b: Pose, _ t: Float) -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            let va = a.rotations[j]
            let vb = b.rotations[j]
            if va == nil && vb == nil { continue }
            let x = va ?? SIMD3<Float>(0, 0, 0)
            let y = vb ?? SIMD3<Float>(0, 0, 0)
            var d = y - x
            if j.rigSide == 0 {
                d.y = wrapAngle(d.y)
            }
            out[j] = x + d * t
        }
        return Pose(out, hipsOffset: a.hipsOffset + (b.hipsOffset - a.hipsOffset) * t)
    }

    /// Additiv: addiert die Rotationen und den Hüftversatz von `other`, skaliert mit weight.
    func rigAdding(_ other: Pose, weight: Float = 1) -> Pose {
        var out = self
        for (j, r) in other.rotations {
            out[j] = out[j] + r * weight
        }
        out.hipsOffset += other.hipsOffset * weight
        return out
    }

    /// Spiegelt die Pose (links <-> rechts).
    func mirrored() -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        for (j, r) in rotations {
            if j.rigSide == 0 {
                out[j] = SIMD3<Float>(r.x, -r.y, -r.z)
            } else {
                out[j.rigMirror] = r
            }
        }
        return Pose(out, hipsOffset: SIMD3<Float>(-hipsOffset.x, hipsOffset.y, hipsOffset.z))
    }

    /// Catmull-Rom-Spline durch p1 -> p2 (p0/p3 = Nachbarn) – für weiche Schleifen.
    static func rigCatmull(_ p0: Pose, _ p1: Pose, _ p2: Pose, _ p3: Pose, _ u: Float) -> Pose {
        let u2 = u * u
        let u3 = u2 * u
        let c0 = -0.5 * u3 + u2 - 0.5 * u
        let c1 = 1.5 * u3 - 2.5 * u2 + 1.0
        let c2 = -1.5 * u3 + 2.0 * u2 + 0.5 * u
        let c3 = 0.5 * u3 - 0.5 * u2
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            if p0.rotations[j] == nil && p1.rotations[j] == nil && p2.rotations[j] == nil && p3.rotations[j] == nil {
                continue
            }
            var acc = p0[j] * c0
            acc += p1[j] * c1
            acc += p2[j] * c2
            acc += p3[j] * c3
            out[j] = acc
        }
        var h = p0.hipsOffset * c0
        h += p1.hipsOffset * c1
        h += p2.hipsOffset * c2
        h += p3.hipsOffset * c3
        return Pose(out, hipsOffset: h)
    }
}

// MARK: - Keyframes & Clips

/// Wie ein Schlüsselbild ERREICHT wird (Kurve vom vorherigen Schlüssel zu diesem).
enum RigEase {
    case smooth     // Smoothstep
    case snap       // schneller Start, weiches Abbremsen (Schläge, Tritte)
    case accel      // langsamer Start, beschleunigt (Fallen)
    case linear

    func apply(_ u: Float) -> Float {
        let x = Swift.max(0, Swift.min(1, u))
        switch self {
        case .smooth: return x * x * (3 - 2 * x)
        case .snap:
            let k = 1 - x
            return 1 - k * k * k
        case .accel: return x * x
        case .linear: return x
        }
    }
}

struct RigKeyframe {
    let time: Float      // 0...1 (Anteil der Cliplänge)
    let pose: Pose
    let ease: RigEase
}

struct RigClip {
    let duration: Float          // Standardlänge in Sekunden (Schleifen: Länge eines Zyklus)
    let loops: Bool
    var breathing: Float         // Stärke der prozeduralen Atmung (0 = keine)
    private(set) var keys: [RigKeyframe] = []

    init(duration: Float, loops: Bool, breathing: Float = 1) {
        self.duration = duration
        self.loops = loops
        self.breathing = breathing
    }

    mutating func key(_ time: Float, _ ease: RigEase, pose: Pose) {
        keys.append(RigKeyframe(time: time, pose: pose, ease: ease))
    }

    mutating func key(_ time: Float, _ ease: RigEase, h: SIMD3<Float>, _ r: [Joint: SIMD3<Float>]) {
        keys.append(RigKeyframe(time: time, pose: Pose(r, hipsOffset: h), ease: ease))
    }

    /// Pose bei normierter Zeit (0...1). Schleifen: Catmull-Rom (zyklisch), sonst Ease pro Schlüssel.
    func sample(_ phase: Float) -> Pose {
        let n = keys.count
        if n == 0 { return Pose() }
        if n == 1 { return keys[0].pose }
        if loops {
            var t = phase.truncatingRemainder(dividingBy: 1)
            if t < 0 { t += 1 }
            if !t.isFinite { t = 0 }
            var i = n - 1
            for k in 0..<n {
                let next: Float = (k + 1 < n) ? keys[k + 1].time : 1.0 + keys[0].time
                if t >= keys[k].time && t < next {
                    i = k
                    break
                }
            }
            let t0 = keys[i].time
            let t1: Float = (i + 1 < n) ? keys[i + 1].time : 1.0 + keys[0].time
            var tt = t
            if tt < t0 { tt += 1 }
            let span = Swift.max(0.0001, t1 - t0)
            let u = Swift.max(0, Swift.min(1, (tt - t0) / span))
            let p0 = keys[(i - 1 + n) % n].pose
            let p1 = keys[i].pose
            let p2 = keys[(i + 1) % n].pose
            let p3 = keys[(i + 2) % n].pose
            return Pose.rigCatmull(p0, p1, p2, p3, u)
        }
        let t = Swift.max(0, Swift.min(1, phase.isFinite ? phase : 1))
        if t <= keys[0].time { return keys[0].pose }
        if t >= keys[n - 1].time { return keys[n - 1].pose }
        for k in 0..<(n - 1) {
            let a = keys[k]
            let b = keys[k + 1]
            if t >= a.time && t <= b.time {
                let span = Swift.max(0.0001, b.time - a.time)
                let u = b.ease.apply((t - a.time) / span)
                return Pose.blend(a.pose, b.pose, u)
            }
        }
        return keys[n - 1].pose
    }
}

// MARK: - Clip-Bibliothek

enum RigAnimLibrary {
    /// Ruhehaltung, auf die jede Pose addiert wird: Arme leicht abgespreizt, Ellbogen leicht gebeugt.
    static let restPose = Pose([
        .lUpperArm: SIMD3<Float>(0, 0, 0.1), .rUpperArm: SIMD3<Float>(0, 0, 0.1),
        .lForearm: SIMD3<Float>(0.15, 0, 0), .rForearm: SIMD3<Float>(0.15, 0, 0)
    ])

    private static var cache: [AnimClip: RigClip] = [:]

    /// Clip-Daten (einmal erzeugt, danach aus dem Cache).
    static func clip(_ c: AnimClip) -> RigClip {
        if let hit = cache[c] { return hit }
        let made = build(c)
        cache[c] = made
        return made
    }

    /// Standarddauer eines Clips in Sekunden.
    static func defaultDuration(_ c: AnimClip) -> Float {
        return clip(c).duration
    }

    /// true für Schleifen-Clips (idle, run, swing …).
    static func isLooping(_ c: AnimClip) -> Bool {
        return clip(c).loops
    }

    private static func v(_ x: Float, _ y: Float, _ z: Float) -> SIMD3<Float> {
        return SIMD3<Float>(x, y, z)
    }

    // MARK: Gemeinsame Posen (von mehreren Clips genutzt)
    private static let pCePump = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.05, 0, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, 0, 0), .lUpperArm: v(2.4, 0, 0.6),
        .lForearm: v(1.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.4, 0, 0.6),
        .rForearm: v(1.2, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.05, 0.25, 0.14),
        .lShin: v(-0.645, 0, 0), .lFoot: v(0.591, 0, -0.154), .rThigh: v(0, 0.3, 0.14),
        .rShin: v(-0.614, 0, 0), .rFoot: v(0.618, 0, -0.126)
    ], hipsOffset: v(0, -0.08, 0))
    private static let pCeUp = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.15, 0, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.35, 0, 0), .lUpperArm: v(2.75, 0, 0.5),
        .lForearm: v(0.25, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.75, 0, 0.5),
        .rForearm: v(0.25, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.05, 0.25, 0.14),
        .lShin: v(-0.258, 0, 0), .lFoot: v(0.204, 0, -0.154), .rThigh: v(0, 0.3, 0.14),
        .rShin: v(-0.268, 0, 0), .rFoot: v(0.273, 0, -0.126)
    ], hipsOffset: v(0, -0.02, 0))
    private static let pDsHit = Pose([
        .hips: v(0.1, 0.4, 0), .spine: v(0.2, 0.15, 0), .chest: v(0.05, 0.3, 0),
        .neck: v(-0.15, -0.2, 0), .head: v(-0.15, -0.3, 0), .lUpperArm: v(-0.8, 0.1, 0.35),
        .lForearm: v(0.5, 0, 0), .rUpperArm: v(1.8, 0.5, 0.05), .rForearm: v(0.05, 0, 0),
        .rHand: v(-0.2, 0, 0), .lThigh: v(1.05, 0, 0.06), .lShin: v(-0.452, 0, 0),
        .lFoot: v(-0.498, 0, -0.035), .rThigh: v(-0.75, 0.2, 0.08), .rShin: v(-0.15, 0, 0),
        .rFoot: v(-0.4, 0, 0)
    ], hipsOffset: v(0, -0.22, 0.2))
    private static let pGrPull = Pose([
        .hips: v(0.1, -0.15, 0), .spine: v(0.12, 0.05, 0), .chest: v(0.1, 0.05, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(-0.15, 0.05, 0), .lUpperArm: v(1.05, -0.4, 0.12),
        .lForearm: v(1.3, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(1.05, -0.45, 0.15),
        .rForearm: v(1.35, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
        .lShin: v(-0.997, 0, 0), .lFoot: v(0.341, 0, -0.077), .rThigh: v(-0.32, 0.4, 0.1),
        .rShin: v(-0.175, 0, 0), .rFoot: v(0.591, 0, -0.13)
    ], hipsOffset: v(0, -0.11, 0.06))
    private static let pGuard = Pose([
        .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
        .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
        .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
        .lShin: v(-0.595, 0, 0), .lFoot: v(-0.109, 0, -0.061), .rThigh: v(-0.32, 0.4, 0.1),
        .rShin: v(-0.218, 0, 0), .rFoot: v(0.587, 0, -0.113)
    ], hipsOffset: v(0, -0.1, 0))
    private static let pHh = Pose([
        .hips: v(-0.02, -0.25, 0), .spine: v(-0.15, 0, 0.05), .chest: v(-0.3, -0.1, 0.05),
        .neck: v(-0.3, 0.1, 0), .head: v(-0.4, 0.35, 0.15), .lUpperArm: v(0.3, 0.1, 0.55),
        .lForearm: v(0.7, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(0.2, 0.1, 0.5),
        .rForearm: v(0.8, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.588, 0.3, 0.06),
        .lShin: v(-0.221, 0, 0), .lFoot: v(-0.387, 0, -0.043), .rThigh: v(-0.173, 0.4, 0.1),
        .rShin: v(-0.569, 0, 0), .rFoot: v(0.724, 0, -0.091)
    ], hipsOffset: v(0, -0.1, -0.07))
    private static let pJkExt = Pose([
        .hips: v(-0.1, 0.25, 0), .spine: v(-0.15, 0, 0), .chest: v(-0.1, -0.15, 0),
        .neck: v(0.1, 0, 0), .head: v(0.15, -0.1, 0), .lUpperArm: v(-0.3, 0.2, 0.75),
        .lForearm: v(0.6, 0, 0), .rUpperArm: v(0.6, -0.4, 0.4), .rForearm: v(1.6, 0, 0),
        .lThigh: v(1, 0.1, 0.1), .lShin: v(-2, 0, 0), .lFoot: v(-0.4, 0, 0),
        .rThigh: v(1.5, -0.1, 0.05), .rShin: v(-0.05, 0, 0), .rFoot: v(0.3, 0, 0)
    ], hipsOffset: v(0, 0.05, 0))
    private static let pJtuck = Pose([
        .hips: v(0.1, 0, 0), .spine: v(0.12, 0, 0), .chest: v(0.05, 0, 0),
        .neck: v(-0.05, 0, 0), .head: v(-0.15, 0, 0), .lUpperArm: v(0.9, 0.1, 0.65),
        .lForearm: v(1.2, 0, 0), .rUpperArm: v(0.8, 0.1, 0.7), .rForearm: v(1.3, 0, 0),
        .lThigh: v(1.2, 0.1, 0.12), .lShin: v(-1.7, 0, 0), .lFoot: v(-0.3, 0, 0),
        .rThigh: v(0.95, 0.1, 0.12), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.3, 0, 0)
    ], hipsOffset: v(0, 0.05, 0))
    private static let pLieKd = Pose([
        .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0.02, 0.05, 0),
        .neck: v(0.05, 0.1, 0), .head: v(-0.15, 0.55, 0.05), .lUpperArm: v(0.35, 0, 0.75),
        .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
        .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
        .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
        .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
    ], hipsOffset: v(0, -0.8, -0.5))
    private static let pLookl = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.15, 0), .chest: v(-0.04, 0.25, -0.01),
        .neck: v(0, 0.25, 0), .head: v(-0.05, 0.4, 0), .lUpperArm: v(0.04, 0.05, 0.1),
        .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(-0.02, -0.03, 0.09),
        .rForearm: v(0.18, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0, 0.07),
        .lShin: v(-0.23, 0, 0), .lFoot: v(0.21, 0, -0.085), .rThigh: v(0.003, 0.3, 0.06),
        .rShin: v(-0.231, 0, 0), .rFoot: v(0.233, 0, -0.046)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pLookr = Pose([
        .hips: v(0, 0, -0.02), .spine: v(-0.02, -0.15, 0), .chest: v(-0.04, -0.25, 0.01),
        .neck: v(0, -0.25, 0), .head: v(-0.08, -0.4, 0), .lUpperArm: v(0, 0.05, 0.12),
        .lForearm: v(0.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.03, -0.03, 0.08),
        .rForearm: v(0.12, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.105, 0.3, 0.07),
        .lShin: v(-0.331, 0, 0), .lFoot: v(0.232, 0, -0.051), .rThigh: v(0.055, 0, 0.06),
        .rShin: v(-0.372, 0, 0), .rFoot: v(0.316, 0, -0.08)
    ], hipsOffset: v(-0.008, -0.018, 0))
    private static let pStand = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.04, 0.02, -0.01),
        .neck: v(0.02, 0, 0), .head: v(0.03, -0.04, 0.01), .lUpperArm: v(0.04, 0.05, 0.1),
        .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(-0.02, -0.03, 0.09),
        .rForearm: v(0.18, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0.12, 0.07),
        .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
        .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pTa1 = Pose([
        .hips: v(0, -0.3, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.12, 0.2, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, -0.1, 0.1), .lUpperArm: v(1.1, -0.1, 0.1),
        .lForearm: v(0.45, 0, 0), .lHand: v(-0.7, 0, 0), .rUpperArm: v(0.1, 0.2, 0.55),
        .rForearm: v(1.8, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.742, 0.3, 0.06),
        .lShin: v(-0.598, 0, 0), .lFoot: v(-0.145, 0, -0.044), .rThigh: v(-0.262, 0.4, 0.1),
        .rShin: v(-0.439, 0, 0), .rFoot: v(0.703, 0, -0.097)
    ], hipsOffset: v(0, -0.11, -0.02))
    private static let pTa2 = Pose([
        .hips: v(0, -0.3, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.12, 0.2, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, -0.1, 0.1), .lUpperArm: v(1.1, -0.1, 0.1),
        .lForearm: v(1, 0, 0), .lHand: v(0.7, 0, 0), .rUpperArm: v(0.1, 0.2, 0.55),
        .rForearm: v(1.8, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.742, 0.3, 0.06),
        .lShin: v(-0.598, 0, 0), .lFoot: v(-0.145, 0, -0.044), .rThigh: v(-0.262, 0.4, 0.1),
        .rShin: v(-0.439, 0, 0), .rFoot: v(0.703, 0, -0.097)
    ], hipsOffset: v(0, -0.11, -0.02))
    private static let pThSlam = Pose([
        .hips: v(0.2, 1.15, 0), .spine: v(0.55, 0.25, 0), .chest: v(0.3, 0.3, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(-0.3, -0.2, 0), .lUpperArm: v(1, -0.2, 0.25),
        .lForearm: v(0.3, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(1, -0.2, 0.25),
        .rForearm: v(0.3, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.9, -0.4, 0.1),
        .lShin: v(-1.691, 0, 0), .lFoot: v(0.978, 0, 0.002), .rThigh: v(0.2, 0, 0.15),
        .rShin: v(-1.233, 0, 0), .rFoot: v(1.233, 0, -0.15)
    ], hipsOffset: v(0, -0.28, 0.05))
    private static let pViUp = Pose([
        .spine: v(-0.08, 0, 0), .chest: v(-0.15, 0.1, 0), .neck: v(-0.15, 0, 0),
        .head: v(-0.3, -0.1, 0), .lUpperArm: v(0.15, 0, 0.3), .lForearm: v(0.7, 0, 0),
        .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.95, 0, 0.18), .rForearm: v(0.12, 0, 0),
        .lThigh: v(0.05, 0.25, 0.16), .lShin: v(-0.36, 0, 0), .lFoot: v(0.309, 0, -0.16),
        .rThigh: v(0, 0.3, 0.14), .rShin: v(-0.332, 0, 0), .rFoot: v(0.332, 0, -0.14)
    ], hipsOffset: v(0, -0.03, 0))
    private static let pWsShot = Pose([
        .hips: v(0, 0, 0.015), .spine: v(0, 0.1, 0), .chest: v(-0.05, 0.3, 0),
        .neck: v(0.02, 0, 0), .head: v(-0.1, -0.3, 0), .lUpperArm: v(0.3, 0, 0.3),
        .lForearm: v(0.9, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.85, 0.25, 0.05),
        .rForearm: v(0.05, 0, 0), .rHand: v(-0.75, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
        .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
        .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pZip1 = Pose([
        .hips: v(0.25, 0, 0), .spine: v(0.1, 0, 0), .chest: v(-0.05, 0, 0),
        .neck: v(-0.2, 0, 0), .head: v(-0.3, 0, 0), .lUpperArm: v(2.5, -0.1, 0.15),
        .lForearm: v(0.2, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(2.6, -0.1, 0.12),
        .rForearm: v(0.15, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(-0.25, 0, 0.05),
        .lShin: v(-0.4, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(-0.1, 0, 0.05),
        .rShin: v(-0.2, 0, 0), .rFoot: v(-0.6, 0, 0)
    ], hipsOffset: v(0, 0, 0))

    // MARK: Clip-Erzeugung (exhaustiv über alle AnimClip-Fälle)
    private static func build(_ clip: AnimClip) -> RigClip {
        switch clip {
        case .idle: return makeIdle()
        case .fightIdle: return makeFightIdle()
        case .crouch: return makeCrouch()
        case .walkForward: return makeWalkForward()
        case .walkBack: return makeWalkBack()
        case .run: return makeRun()
        case .sprint: return makeSprint()
        case .jump: return makeJump()
        case .fall: return makeFall()
        case .land: return makeLand()
        case .swing: return makeSwing()
        case .webShoot: return makeWebShoot()
        case .zip: return makeZip()
        case .wallRun: return makeWallRun()
        case .perch: return makePerch()
        case .dive: return makeDive()
        case .punch: return makePunch()
        case .punch2: return makePunch2()
        case .kick: return makeKick()
        case .kick2: return makeKick2()
        case .uppercut: return makeUppercut()
        case .sweep: return makeSweep()
        case .jumpKick: return makeJumpKick()
        case .block: return makeBlock()
        case .hitHigh: return makeHitHigh()
        case .hitLow: return makeHitLow()
        case .knockdown: return makeKnockdown()
        case .lieDown: return makeLieDown()
        case .getUp: return makeGetUp()
        case .dizzy: return makeDizzy()
        case .grab: return makeGrab()
        case .throwToss: return makeThrowToss()
        case .cast: return makeCast()
        case .dashStrike: return makeDashStrike()
        case .victory: return makeVictory()
        case .defeat: return makeDefeat()
        case .taunt: return makeTaunt()
        case .talk: return makeTalk()
        case .point: return makePoint()
        case .crossArms: return makeCrossArms()
        case .lookAround: return makeLookAround()
        case .kneel: return makeKneel()
        case .celebrate: return makeCelebrate()
        }
    }

    private static func makeIdle() -> RigClip {
        var c = RigClip(duration: 3, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.5, .smooth, h: v(-0.008, -0.018, 0), [
            .hips: v(0, 0, -0.02), .spine: v(-0.02, 0.02, 0), .chest: v(-0.035, -0.02, 0.012),
            .neck: v(0.02, 0, 0), .head: v(0.01, 0.06, -0.01), .lUpperArm: v(0, 0.05, 0.12),
            .lForearm: v(0.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.03, -0.03, 0.08),
            .rForearm: v(0.12, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.084, 0.12, 0.07),
            .lShin: v(-0.334, 0, 0), .lFoot: v(0.252, 0, -0.05), .rThigh: v(0.043, 0.15, 0.06),
            .rShin: v(-0.347, 0, 0), .rFoot: v(0.301, 0, -0.08)
        ])
        return c
    }

    private static func makeFightIdle() -> RigClip {
        var c = RigClip(duration: 0.9, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.5, .smooth, h: v(0, -0.13, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.11, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.8, -0.4, 0.22),
            .lForearm: v(1.9, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.62, -0.7, 0.28),
            .rForearm: v(2.1, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.865, 0.3, 0.06),
            .lShin: v(-0.792, 0, 0), .lFoot: v(-0.027, 0, -0.056), .rThigh: v(-0.17, 0.4, 0.1),
            .rShin: v(-0.551, 0, 0), .rFoot: v(0.768, 0, -0.117)
        ])
        return c
    }

    private static func makeCrouch() -> RigClip {
        var c = RigClip(duration: 1.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.42, 0.02), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.15, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.25, 0.3, 0.18), .lShin: v(-2.117, 0, 0), .lFoot: v(1.042, 0, -0.146),
            .rThigh: v(0.75, 0.4, 0.22), .rShin: v(-1.983, 0, 0), .rFoot: v(1.397, 0, -0.262)
        ])
        c.key(0.5, .smooth, h: v(0, -0.44, 0.02), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.18, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.277, 0.3, 0.18), .lShin: v(-2.172, 0, 0), .lFoot: v(1.07, 0, -0.142),
            .rThigh: v(0.755, 0.4, 0.22), .rShin: v(-2.032, 0, 0), .rFoot: v(1.441, 0, -0.262)
        ])
        return c
    }

    private static func makeWalkForward() -> RigClip {
        var c = RigClip(duration: 1, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.085, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.62, 0.3, 0.06),
            .lShin: v(-0.876, 0, 0), .lFoot: v(0.303, 0, -0.065), .rThigh: v(-0.28, 0.4, 0.1),
            .rShin: v(-0.214, 0, 0), .rFoot: v(0.542, 0, -0.114)
        ])
        c.key(0.25, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.45, 0.3, 0.06),
            .lShin: v(-0.126, 0, 0), .lFoot: v(-0.277, 0, -0.07), .rThigh: v(0.15, 0.4, 0.1),
            .rShin: v(-0.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.4, 0.3, 0.06),
            .lShin: v(-0.869, 0, 0), .lFoot: v(0.516, 0, -0.071), .rThigh: v(-0.42, 0.4, 0.1),
            .rFoot: v(0.469, 0, -0.109)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.9, 0, 0), .lFoot: v(0.4, 0, 0), .rThigh: v(-0.2, 0.4, 0.1),
            .rShin: v(-0.153, 0, 0), .rFoot: v(0.401, 0, -0.116)
        ])
        return c
    }

    private static func makeWalkBack() -> RigClip {
        var c = RigClip(duration: 1.1, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.085, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.62, 0.3, 0.06),
            .lShin: v(-0.876, 0, 0), .lFoot: v(0.303, 0, -0.065), .rThigh: v(-0.28, 0.4, 0.1),
            .rShin: v(-0.214, 0, 0), .rFoot: v(0.542, 0, -0.114)
        ])
        c.key(0.25, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.9, 0, 0), .lFoot: v(0.4, 0, 0), .rThigh: v(-0.2, 0.4, 0.1),
            .rShin: v(-0.153, 0, 0), .rFoot: v(0.401, 0, -0.116)
        ])
        c.key(0.5, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.4, 0.3, 0.06),
            .lShin: v(-0.869, 0, 0), .lFoot: v(0.516, 0, -0.071), .rThigh: v(-0.42, 0.4, 0.1),
            .rFoot: v(0.469, 0, -0.109)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.45, 0.3, 0.06),
            .lShin: v(-0.126, 0, 0), .lFoot: v(-0.277, 0, -0.07), .rThigh: v(0.15, 0.4, 0.1),
            .rShin: v(-0.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        return c
    }

    private static func makeRun() -> RigClip {
        var c = RigClip(duration: 0.68, loops: true, breathing: 0.6)
        c.key(0, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0.048, 0.14, 0), .spine: v(0.16, 0.04, 0), .chest: v(0.064, -0.24, 0),
            .neck: v(-0.096, 0.06, 0), .head: v(-0.08, 0.08, 0), .lUpperArm: v(0.9, -0.25, 0.12),
            .lForearm: v(1.55, 0, 0), .lHand: v(0.15, 0, 0), .rUpperArm: v(-0.7, 0.1, 0.15),
            .rForearm: v(1.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(-0.55, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.65, 0.05, 0.03),
            .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.048, 0, 0), .spine: v(0.16, 0, 0), .chest: v(0.064, 0, 0),
            .neck: v(-0.096, 0, 0), .head: v(-0.08, 0, 0), .lUpperArm: v(0.1, -0.1, 0.14),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0, 0, 0.14),
            .rForearm: v(1.4, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.55, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.703, 0, 0), .rFoot: v(0.631, 0, -0.032)
        ])
        c.key(0.5, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0.048, -0.14, 0), .spine: v(0.16, -0.04, 0), .chest: v(0.064, 0.24, 0),
            .neck: v(-0.096, -0.06, 0), .head: v(-0.08, -0.08, 0), .lUpperArm: v(-0.7, 0.1, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.9, -0.25, 0.12),
            .rForearm: v(1.55, 0, 0), .rHand: v(0.15, 0, 0), .lThigh: v(0.65, 0.05, 0.03),
            .lFoot: v(0.25, 0, 0), .rThigh: v(-0.55, 0.05, 0.03), .rShin: v(-1, 0, 0),
            .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.048, 0, 0), .spine: v(0.16, 0, 0), .chest: v(0.064, 0, 0),
            .neck: v(-0.096, 0, 0), .head: v(-0.08, 0, 0), .lUpperArm: v(0, 0, 0.14),
            .lForearm: v(1.4, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.1, -0.1, 0.14),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.703, 0, 0), .lFoot: v(0.631, 0, -0.032), .rThigh: v(0.55, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeSprint() -> RigClip {
        var c = RigClip(duration: 0.5, loops: true, breathing: 0.5)
        c.key(0, .smooth, h: v(0, -0.06, 0), [
            .hips: v(0.096, 0.14, 0), .spine: v(0.32, 0.04, 0), .chest: v(0.128, -0.24, 0),
            .neck: v(-0.192, 0.06, 0), .head: v(-0.16, 0.08, 0), .lUpperArm: v(1.17, -0.25, 0.12),
            .lForearm: v(1.55, 0, 0), .lHand: v(0.15, 0, 0), .rUpperArm: v(-0.91, 0.1, 0.15),
            .rForearm: v(1.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(-0.688, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.812, 0.05, 0.03),
            .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.12, 0), [
            .hips: v(0.096, 0, 0), .spine: v(0.32, 0, 0), .chest: v(0.128, 0, 0),
            .neck: v(-0.192, 0, 0), .head: v(-0.16, 0, 0), .lUpperArm: v(0.1, -0.1, 0.14),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0, 0, 0.14),
            .rForearm: v(1.4, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.688, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.808, 0, 0), .rFoot: v(0.784, 0, -0.035)
        ])
        c.key(0.5, .smooth, h: v(0, -0.06, 0), [
            .hips: v(0.096, -0.14, 0), .spine: v(0.32, -0.04, 0), .chest: v(0.128, 0.24, 0),
            .neck: v(-0.192, -0.06, 0), .head: v(-0.16, -0.08, 0), .lUpperArm: v(-0.91, 0.1, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.17, -0.25, 0.12),
            .rForearm: v(1.55, 0, 0), .rHand: v(0.15, 0, 0), .lThigh: v(0.812, 0.05, 0.03),
            .lFoot: v(0.25, 0, 0), .rThigh: v(-0.688, 0.05, 0.03), .rShin: v(-1, 0, 0),
            .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.12, 0), [
            .hips: v(0.096, 0, 0), .spine: v(0.32, 0, 0), .chest: v(0.128, 0, 0),
            .neck: v(-0.192, 0, 0), .head: v(-0.16, 0, 0), .lUpperArm: v(0, 0, 0.14),
            .lForearm: v(1.4, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.1, -0.1, 0.14),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.808, 0, 0), .lFoot: v(0.784, 0, -0.035), .rThigh: v(0.688, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeJump() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.3, .smooth, h: v(0, -0.26, 0.02), [
            .hips: v(0.15, -0.2, 0), .spine: v(0.25, 0.05, 0), .chest: v(0.12, 0.08, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, 0.05, 0), .lUpperArm: v(-0.5, 0, 0.25),
            .lForearm: v(0.6, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(-0.6, 0, 0.25),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.341, 0.2, 0.08),
            .lShin: v(-1.359, 0, 0), .lFoot: v(0.162, 0, -0.059), .rThigh: v(0.111, 0.25, 0.1),
            .rShin: v(-1.193, 0, 0), .rFoot: v(1.228, 0, -0.137)
        ])
        c.key(0.55, .snap, h: v(0, 0.08, 0), [
            .spine: v(-0.05, 0, 0), .chest: v(-0.12, 0, 0), .neck: v(-0.05, 0, 0),
            .head: v(-0.15, 0, 0), .lUpperArm: v(2.2, 0, 0.35), .lForearm: v(0.4, 0, 0),
            .rUpperArm: v(2, 0, 0.35), .rForearm: v(0.5, 0, 0), .lThigh: v(0.05, 0.1, 0.05),
            .lShin: v(-0.08, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(-0.1, 0.1, 0.05),
            .rShin: v(-0.2, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(1, .smooth, pose: pJtuck)
        return c
    }

    private static func makeFall() -> RigClip {
        var c = RigClip(duration: 0.9, loops: true, breathing: 0.3)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.12, 0.05, 0), .spine: v(-0.1, 0, 0.03), .chest: v(-0.08, 0.05, 0),
            .neck: v(0.05, 0, 0), .head: v(0.25, 0, 0), .lUpperArm: v(0.9, 0.2, 1.15),
            .lForearm: v(0.7, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(0.6, 0.2, 1.25),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.55, 0.1, 0.12),
            .lShin: v(-0.9, 0, 0), .lFoot: v(-0.3, 0, 0), .rThigh: v(0.15, 0.1, 0.1),
            .rShin: v(-0.45, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.08, -0.05, 0), .spine: v(-0.12, 0, -0.03), .chest: v(-0.08, 0.05, 0),
            .neck: v(0.05, 0, 0), .head: v(0.25, 0, 0), .lUpperArm: v(0.65, 0.2, 1.3),
            .lForearm: v(0.7, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(0.85, 0.2, 1.1),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.2, 0.1, 0.1),
            .lShin: v(-0.5, 0, 0), .lFoot: v(-0.3, 0, 0), .rThigh: v(0.6, 0.1, 0.12),
            .rShin: v(-1, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        return c
    }

    private static func makeLand() -> RigClip {
        var c = RigClip(duration: 0.25, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pJtuck)
        c.key(0.35, .snap, h: v(0, -0.34, 0.02), [
            .hips: v(0.15, -0.2, 0), .spine: v(0.35, 0.05, 0), .chest: v(0.12, 0.08, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.25, 0, 0), .lUpperArm: v(0.3, 0, 0.6),
            .lForearm: v(0.6, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.3, 0, 0.6),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.533, 0.2, 0.08),
            .lShin: v(-1.605, 0, 0), .lFoot: v(0.216, 0, -0.044), .rThigh: v(0.156, 0.25, 0.1),
            .rShin: v(-1.434, 0, 0), .rFoot: v(1.423, 0, -0.137)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeSwing() -> RigClip {
        var c = RigClip(duration: 1.6, loops: true, breathing: 0.4)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(0.05, 0.1, 0), .spine: v(0.1, 0.05, -0.08), .chest: v(0, 0.1, -0.1),
            .neck: v(-0.1, -0.1, 0), .head: v(-0.15, -0.15, 0.05), .lUpperArm: v(0.4, 0.1, 0.95),
            .lForearm: v(0.9, 0, 0), .lHand: v(-0.1, 0, 0), .rUpperArm: v(2.95, 0, 0.12),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(1.1, 0, 0.1),
            .lShin: v(-1.7, 0, 0), .lFoot: v(-0.4, 0, 0), .rThigh: v(0.8, 0, 0.08),
            .rShin: v(-1.4, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.12, 0.05, 0), .spine: v(-0.05, 0.05, -0.06), .chest: v(0, 0.1, -0.1),
            .neck: v(-0.1, -0.1, 0), .head: v(-0.05, -0.1, 0.04), .lUpperArm: v(0.2, 0.1, 1.1),
            .lForearm: v(0.5, 0, 0), .lHand: v(-0.1, 0, 0), .rUpperArm: v(2.95, 0, 0.12),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.45, 0, 0.08),
            .lShin: v(-0.6, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(0.2, 0, 0.06),
            .rShin: v(-0.35, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        return c
    }

    private static func makeWebShoot() -> RigClip {
        var c = RigClip(duration: 0.3, loops: false, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(0, -0.15, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, 0.1, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.6, 0.1, 0.25),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.5, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(0.35, .snap, pose: pWsShot)
        c.key(1, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.1, 0), .chest: v(-0.05, 0.3, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.1, -0.3, 0), .lUpperArm: v(0.3, 0, 0.3),
            .lForearm: v(0.9, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.7, 0.2, 0.08),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.4, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makeZip() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 0.3)
        c.key(0, .smooth, pose: pWsShot)
        c.key(0.3, .snap, pose: pZip1)
        c.key(0.75, .smooth, pose: pZip1)
        c.key(1, .smooth, h: v(0, 0, 0), [
            .hips: v(0.05, 0, 0), .spine: v(0.1, 0, 0), .chest: v(-0.05, 0, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.3, 0, 0), .lUpperArm: v(2.2, -0.1, 0.2),
            .lForearm: v(0.6, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(2.3, -0.1, 0.2),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(1, 0, 0.1),
            .lShin: v(-1.4, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.8, 0, 0.1),
            .rShin: v(-1.2, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeWallRun() -> RigClip {
        var c = RigClip(duration: 0.5, loops: true, breathing: 0.5)
        c.key(0, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.126, 0.14, 0), .spine: v(0.42, 0.04, 0), .chest: v(0.168, -0.24, 0),
            .neck: v(-0.252, 0.06, 0), .head: v(-0.21, 0.08, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(-0.66, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.78, 0.05, 0.03),
            .rShin: v(-0.931, 0, 0), .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.16, 0), [
            .hips: v(0.126, 0, 0), .spine: v(0.42, 0, 0), .chest: v(0.168, 0, 0),
            .neck: v(-0.252, 0, 0), .head: v(-0.21, 0, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.66, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.909, 0, 0), .rFoot: v(0.915, 0, -0.036)
        ])
        c.key(0.5, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.126, -0.14, 0), .spine: v(0.42, -0.04, 0), .chest: v(0.168, 0.24, 0),
            .neck: v(-0.252, -0.06, 0), .head: v(-0.21, -0.08, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.78, 0.05, 0.03),
            .lShin: v(-0.931, 0, 0), .lFoot: v(0.25, 0, 0), .rThigh: v(-0.66, 0.05, 0.03),
            .rShin: v(-1, 0, 0), .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.16, 0), [
            .hips: v(0.126, 0, 0), .spine: v(0.42, 0, 0), .chest: v(0.168, 0, 0),
            .neck: v(-0.252, 0, 0), .head: v(-0.21, 0, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.909, 0, 0), .lFoot: v(0.915, 0, -0.036), .rThigh: v(0.66, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makePerch() -> RigClip {
        var c = RigClip(duration: 3.6, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.55, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.2, 0.08, 0),
            .neck: v(-0.3, 0, 0), .head: v(-0.65, -0.05, 0), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.65, 0.2, 0.42), .lShin: v(-2.46, 0, 0),
            .lFoot: v(1.063, 0, -0.141), .rThigh: v(1.55, 0.25, 0.5), .rShin: v(-2.457, 0, 0),
            .rFoot: v(1.127, 0, -0.213)
        ])
        c.key(0.35, .smooth, h: v(0, -0.54, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.17, 0.12, 0),
            .neck: v(-0.3, 0.08, 0), .head: v(-0.62, 0.25, 0.04), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.635, 0.2, 0.42), .lShin: v(-2.436, 0, 0),
            .lFoot: v(1.052, 0, -0.147), .rThigh: v(1.54, 0.25, 0.5), .rShin: v(-2.433, 0, 0),
            .rFoot: v(1.113, 0, -0.217)
        ])
        c.key(0.7, .smooth, h: v(0, -0.56, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.21, 0.04, 0),
            .neck: v(-0.3, -0.08, 0), .head: v(-0.67, -0.3, -0.03), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.665, 0.2, 0.42), .lShin: v(-2.485, 0, 0),
            .lFoot: v(1.073, 0, -0.135), .rThigh: v(1.56, 0.25, 0.5), .rShin: v(-2.481, 0, 0),
            .rFoot: v(1.142, 0, -0.208)
        ])
        return c
    }

    private static func makeDive() -> RigClip {
        var c = RigClip(duration: 0.7, loops: true, breathing: 0.3)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(1.42, 0, 0), .spine: v(-0.05, 0, 0), .chest: v(-0.08, 0, 0),
            .neck: v(-0.35, 0, 0), .head: v(-0.55, 0, 0), .lUpperArm: v(-0.35, 0, 0.32),
            .lForearm: v(0.2, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.3, 0, 0.3),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(-0.06, 0, 0.03),
            .lShin: v(-0.12, 0, 0), .lFoot: v(-0.7, 0, 0), .rThigh: v(0.05, 0, 0.02),
            .rShin: v(-0.2, 0, 0), .rFoot: v(-0.7, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(1.38, 0.03, 0.04), .spine: v(-0.05, 0, 0), .chest: v(-0.08, 0, 0),
            .neck: v(-0.35, 0, 0), .head: v(-0.55, 0, 0), .lUpperArm: v(-0.28, 0, 0.36),
            .lForearm: v(0.2, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.36, 0, 0.28),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.06, 0, 0.03),
            .lShin: v(-0.25, 0, 0), .lFoot: v(-0.7, 0, 0), .rThigh: v(-0.05, 0, 0.02),
            .rShin: v(-0.1, 0, 0), .rFoot: v(-0.7, 0, 0)
        ])
        return c
    }

    private static func makePunch() -> RigClip {
        var c = RigClip(duration: 0.32, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.2, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -0.5, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.1, 0, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.5, -0.6, 0.3),
            .rForearm: v(2.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.737, 0.3, 0.06),
            .lShin: v(-0.616, 0, 0), .lFoot: v(-0.075, 0, -0.061), .rThigh: v(-0.271, 0.4, 0.1),
            .rShin: v(-0.262, 0, 0), .rFoot: v(0.581, 0, -0.114)
        ])
        c.key(0.45, .snap, h: v(0, -0.115, 0.07), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.18, 0), .chest: v(0.12, 0.28, 0),
            .neck: v(-0.08, -0.2, 0), .head: v(0, -0.25, 0), .lUpperArm: v(0.6, -0.6, 0.2),
            .lForearm: v(2.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.9, 0.15, 0.05),
            .rForearm: v(0.06, 0, 0), .rHand: v(-0.1, 0, 0), .lThigh: v(0.86, 0, 0.06),
            .lShin: v(-0.793, 0, 0), .lFoot: v(0.013, 0, -0.043), .rThigh: v(-0.119, -0.05, 0.08),
            .rShin: v(-0.664, 0, 0), .rFoot: v(0.864, 0, -0.074)
        ])
        c.key(0.62, .smooth, h: v(0, -0.115, 0.07), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.18, 0), .chest: v(0.12, 0.25, 0),
            .neck: v(-0.08, -0.2, 0), .head: v(0, -0.25, 0), .lUpperArm: v(0.6, -0.6, 0.2),
            .lForearm: v(2.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.9, 0.15, 0.05),
            .rForearm: v(0.2, 0, 0), .rHand: v(-0.1, 0, 0), .lThigh: v(0.86, 0, 0.06),
            .lShin: v(-0.793, 0, 0), .lFoot: v(0.013, 0, -0.043), .rThigh: v(-0.119, -0.05, 0.08),
            .rShin: v(-0.664, 0, 0), .rFoot: v(0.864, 0, -0.074)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makePunch2() -> RigClip {
        var c = RigClip(duration: 0.36, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -0.2, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.3, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.5, -0.1, 0.6),
            .lForearm: v(1.9, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.773, 0.3, 0.06),
            .lShin: v(-0.592, 0, 0), .lFoot: v(-0.135, 0, -0.06), .rThigh: v(-0.338, 0.4, 0.1),
            .rShin: v(-0.242, 0, 0), .rFoot: v(0.628, 0, -0.112)
        ])
        c.key(0.48, .snap, h: v(0, -0.12, 0.03), [
            .hips: v(0.06, -0.5, 0), .spine: v(0.06, -0.15, 0), .chest: v(0.1, -0.2, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.45, 0), .lUpperArm: v(0.25, -0.25, 1.5),
            .lForearm: v(1.7, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28), .rForearm: v(2.15, 0, 0),
            .rHand: v(0.1, 0, 0), .lThigh: v(0.824, 0.3, 0.06), .lShin: v(-0.823, 0, 0),
            .lFoot: v(0.054, 0, -0.061), .rThigh: v(-0.255, 0.4, 0.1), .rShin: v(-0.337, 0, 0),
            .rFoot: v(0.649, 0, -0.119)
        ])
        c.key(0.64, .smooth, h: v(0, -0.12, 0.03), [
            .hips: v(0.06, -0.5, 0), .spine: v(0.06, -0.15, 0), .chest: v(0.1, -0.25, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.45, 0), .lUpperArm: v(0.25, -0.35, 1.45),
            .lForearm: v(1.7, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28), .rForearm: v(2.15, 0, 0),
            .rHand: v(0.1, 0, 0), .lThigh: v(0.824, 0.3, 0.06), .lShin: v(-0.823, 0, 0),
            .lFoot: v(0.054, 0, -0.061), .rThigh: v(-0.255, 0.4, 0.1), .rShin: v(-0.337, 0, 0),
            .rFoot: v(0.649, 0, -0.119)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKick() -> RigClip {
        var c = RigClip(duration: 0.45, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.25, .smooth, h: v(0, -0.06, 0.02), [
            .hips: v(0.05, 0.45, -0.15), .spine: v(0, -0.1, -0.2), .chest: v(0.05, -0.25, -0.1),
            .neck: v(0, -0.05, 0), .head: v(0.05, -0.1, 0.1), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.2, 0, 0.45), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.29, -0.35, 0.05), .lFoot: v(-0.292, 0, 0.11), .rThigh: v(1.45, 0, 0.55),
            .rShin: v(-2.1, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(0.48, .snap, h: v(0, -0.04, 0.03), [
            .hips: v(0.05, 1.15, -0.4), .spine: v(0, -0.25, -0.2), .chest: v(0.05, -0.45, -0.15),
            .neck: v(0, -0.2, 0.1), .head: v(0.05, -0.25, 0.2), .lUpperArm: v(0.8, -0.3, 0.45),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(-0.5, 0, 0.7), .rForearm: v(0.6, 0, 0),
            .lThigh: v(0.186, -0.75, 0.05), .lFoot: v(-0.423, 0, 0.279), .rThigh: v(1.5, 0, 1.3),
            .rShin: v(-0.1, 0, 0), .rFoot: v(-0.65, 0, 0)
        ])
        c.key(0.68, .smooth, h: v(0, -0.06, 0.02), [
            .hips: v(0.05, 0.8, 0), .spine: v(0, -0.1, -0.2), .chest: v(0.05, -0.25, -0.1),
            .neck: v(0, -0.05, 0), .head: v(0.05, -0.1, 0.1), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.2, 0, 0.45), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.553, -0.35, 0.05), .lShin: v(-0.147, 0, 0), .lFoot: v(-0.36, 0, -0.027),
            .rThigh: v(1.45, 0, 0.55), .rShin: v(-1.7, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKick2() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.32, .accel, h: v(0, -0.1, 0), [
            .hips: v(0.15, -2, 0), .spine: v(0.2, -0.1, 0), .chest: v(0.1, -0.1, 0),
            .neck: v(0, 0.4, 0), .head: v(-0.05, 0.6, 0), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.6, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(0.12, -0.2, 0.05), .lShin: v(-0.661, 0, 0), .lFoot: v(0.689, 0, -0.02),
            .rThigh: v(0.9, 0.1, 0.1), .rShin: v(-1.8, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.55, .snap, h: v(0, -0.08, 0), [
            .hips: v(0.5, -3.05, 0), .spine: v(0.35, 0, 0), .chest: v(0.05, -0.1, 0),
            .neck: v(-0.3, 0.45, 0), .head: v(-0.35, 0.7, 0), .lUpperArm: v(0.7, -0.4, 0.35),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.3, -0.2, 0.5), .rForearm: v(1.6, 0, 0),
            .lThigh: v(0.359, -0.1, 0.05), .lShin: v(-0.488, 0, 0), .lFoot: v(0.627, 0, -0.002),
            .rThigh: v(-1.3, 0, 0.1), .rShin: v(-0.1, 0, 0), .rFoot: v(0.5, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.2, -3.9, 0), .spine: v(0.2, -0.1, 0), .chest: v(0.1, -0.1, 0),
            .neck: v(0, 0.2, 0), .head: v(0, 0.3, 0), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.6, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(0.642, -0.2, 0.05), .lShin: v(-1.08, 0, 0), .lFoot: v(0.634, 0, -0.006),
            .rThigh: v(0.5, 0.1, 0.1), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -6.663, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.595, 0, 0), .lFoot: v(-0.109, 0, -0.061), .rThigh: v(-0.32, 0.4, 0.1),
            .rShin: v(-0.218, 0, 0), .rFoot: v(0.587, 0, -0.113)
        ])
        return c
    }

    private static func makeUppercut() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.3, .smooth, h: v(0, -0.28, 0.02), [
            .hips: v(0.15, -0.55, 0), .spine: v(0.3, 0, 0.05), .chest: v(0.15, -0.25, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, 0.25, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.15, -0.2, 0.25),
            .rForearm: v(1.7, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.335, 0.3, 0.06),
            .lShin: v(-1.47, 0, 0), .lFoot: v(0.275, 0, -0.066), .rThigh: v(0.218, 0.4, 0.1),
            .rShin: v(-1.27, 0, 0), .rFoot: v(1.189, 0, -0.158)
        ])
        c.key(0.52, .snap, h: v(0, -0.08, 0.08), [
            .hips: v(-0.02, 0.2, 0), .spine: v(-0.12, 0.15, 0), .chest: v(-0.15, 0.3, 0),
            .neck: v(-0.05, -0.2, 0), .head: v(-0.15, -0.25, 0), .lUpperArm: v(0.6, -0.5, 0.3),
            .lForearm: v(2.2, 0, 0), .rUpperArm: v(2.55, -0.25, 0.1), .rForearm: v(1.05, 0, 0),
            .lThigh: v(0.657, 0.1, 0.06), .lShin: v(-0.639, 0, 0), .lFoot: v(-0.038, 0, -0.045),
            .rThigh: v(-0.372, 0.05, 0.08), .rShin: v(-0.354, 0, 0), .rFoot: v(0.707, 0, -0.074)
        ])
        c.key(0.72, .smooth, h: v(0, -0.08, 0.08), [
            .hips: v(-0.02, 0.2, 0), .spine: v(-0.12, 0.15, 0), .chest: v(-0.1, 0.28, 0),
            .neck: v(-0.05, -0.2, 0), .head: v(-0.15, -0.25, 0), .lUpperArm: v(0.6, -0.5, 0.3),
            .lForearm: v(2.2, 0, 0), .rUpperArm: v(2.55, -0.25, 0.1), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.657, 0.1, 0.06), .lShin: v(-0.639, 0, 0), .lFoot: v(-0.038, 0, -0.045),
            .rThigh: v(-0.372, 0.05, 0.08), .rShin: v(-0.354, 0, 0), .rFoot: v(0.707, 0, -0.074)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeSweep() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.25, .snap, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, -0.4, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, 0.1, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.2, 0.2, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.55, 0.2, 0.35), .lShin: v(-2.327, 0, 0),
            .lFoot: v(0.99, 0, -0.137), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.6, .snap, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, 1.15, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, -0.5, 0),
            .neck: v(-0.15, -0.2, 0), .head: v(-0.2, -0.45, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.931, -0.2, 0.3), .lShin: v(-2.258, 0, 0),
            .lFoot: v(0.592, 0, 0.081), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, 1.4, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, -0.5, 0),
            .neck: v(-0.15, -0.2, 0), .head: v(-0.2, -0.45, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.94, -0.2, 0.3), .lShin: v(-2.276, 0, 0),
            .lFoot: v(0.601, 0, 0.084), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeJumpKick() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pJtuck)
        c.key(0.3, .smooth, h: v(0, 0.05, 0), [
            .hips: v(0, 0.1, 0), .spine: v(-0.15, 0, 0), .chest: v(-0.1, -0.15, 0),
            .neck: v(0.1, 0, 0), .head: v(0.15, -0.1, 0), .lUpperArm: v(-0.3, 0.2, 0.75),
            .lForearm: v(0.6, 0, 0), .rUpperArm: v(0.6, -0.4, 0.4), .rForearm: v(1.6, 0, 0),
            .lThigh: v(1, 0.1, 0.1), .lShin: v(-2, 0, 0), .lFoot: v(-0.4, 0, 0),
            .rThigh: v(1.3, 0, 0.05), .rShin: v(-1.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        c.key(0.5, .snap, pose: pJkExt)
        c.key(0.75, .smooth, pose: pJkExt)
        c.key(1, .smooth, pose: pJtuck)
        return c
    }

    private static func makeBlock() -> RigClip {
        var c = RigClip(duration: 1.2, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.11, -0.02), [
            .hips: v(0.05, -0.3, 0), .spine: v(0.1, 0.1, 0), .chest: v(0.15, 0.2, 0),
            .neck: v(0.05, 0, 0), .head: v(0.22, 0, 0), .lUpperArm: v(1.3, -1.1, 0.15),
            .lForearm: v(1.75, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(1.3, -1.05, 0.15),
            .rForearm: v(1.75, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(0.791, 0.3, 0.06),
            .lShin: v(-0.595, 0, 0), .lFoot: v(-0.15, 0, -0.059), .rThigh: v(-0.195, 0.4, 0.1),
            .rShin: v(-0.475, 0, 0), .rFoot: v(0.717, 0, -0.117)
        ])
        c.key(0.5, .smooth, h: v(0, -0.125, -0.02), [
            .hips: v(0.05, -0.3, 0), .spine: v(0.1, 0.1, 0), .chest: v(0.17, 0.2, 0),
            .neck: v(0.05, 0, 0), .head: v(0.22, 0, 0), .lUpperArm: v(1.3, -1.1, 0.15),
            .lForearm: v(1.75, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(1.3, -1.05, 0.15),
            .rForearm: v(1.75, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(0.852, 0.3, 0.06),
            .lShin: v(-0.698, 0, 0), .lFoot: v(-0.107, 0, -0.056), .rThigh: v(-0.143, 0.4, 0.1),
            .rShin: v(-0.594, 0, 0), .rFoot: v(0.785, 0, -0.118)
        ])
        return c
    }

    private static func makeHitHigh() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .snap, pose: pHh)
        c.key(0.55, .smooth, h: v(0, -0.09, -0.04), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.08, 0.1, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.1, 0.15, 0.05), .lUpperArm: v(0.6, -0.2, 0.3),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.65, 0.3, 0.06),
            .lShin: v(-0.314, 0, 0), .lFoot: v(-0.289, 0, -0.064), .rThigh: v(-0.203, 0.4, 0.1),
            .rShin: v(-0.376, 0, 0), .rFoot: v(0.627, 0, -0.116)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeHitLow() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .snap, h: v(0, -0.14, -0.06), [
            .hips: v(0.1, -0.3, 0), .spine: v(0.4, 0, 0), .chest: v(0.3, 0.05, 0),
            .neck: v(0.1, 0, 0), .head: v(0.05, 0.05, 0), .lUpperArm: v(0.55, -0.55, 0.12),
            .lForearm: v(1.45, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.5, -0.6, 0.12),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.936, 0.3, 0.06),
            .lShin: v(-0.656, 0, 0), .lFoot: v(-0.187, 0, -0.069), .rThigh: v(0.057, 0.4, 0.1),
            .rShin: v(-0.84, 0, 0), .rFoot: v(0.876, 0, -0.139)
        ])
        c.key(0.55, .smooth, h: v(0, -0.1, -0.03), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.15, 0.1, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.05, 0.05, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.727, 0.3, 0.06),
            .lShin: v(-0.48, 0, 0), .lFoot: v(-0.201, 0, -0.061), .rThigh: v(-0.19, 0.4, 0.1),
            .rShin: v(-0.429, 0, 0), .rFoot: v(0.666, 0, -0.117)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKnockdown() -> RigClip {
        var c = RigClip(duration: 0.7, loops: false, breathing: 0)
        c.key(0, .smooth, pose: pHh)
        c.key(0.3, .accel, h: v(0, -0.3, -0.25), [
            .hips: v(-0.65, -0.1, 0), .spine: v(-0.1, 0, 0), .chest: v(-0.15, 0, 0),
            .neck: v(0.2, 0, 0), .head: v(0.3, 0.1, 0), .lUpperArm: v(1.5, 0.1, 0.6),
            .lForearm: v(0.5, 0, 0), .rUpperArm: v(1.7, 0.1, 0.5), .rForearm: v(0.4, 0, 0),
            .lThigh: v(0.75, 0.1, 0.1), .lShin: v(-0.6, 0, 0), .lFoot: v(-0.2, 0, 0),
            .rThigh: v(0.45, 0.1, 0.1), .rShin: v(-0.3, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.62, .accel, h: v(0, -0.79, -0.5), [
            .hips: v(-1.571, 0, 0.03), .spine: v(0.08, 0, 0), .chest: v(0.12, 0, 0),
            .neck: v(0.25, 0, 0), .head: v(0.2, 0.1, 0), .lUpperArm: v(1, 0, 1),
            .lForearm: v(0.4, 0, 0), .rUpperArm: v(0.8, 0, 0.9), .rForearm: v(0.35, 0, 0),
            .lThigh: v(0.6, 0.1, 0.12), .lShin: v(-0.35, 0, 0), .lFoot: v(-0.3, 0, 0),
            .rThigh: v(0.45, -0.1, 0.06), .rShin: v(-0.2, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(0.8, .snap, h: v(0, -0.75, -0.5), [
            .hips: v(-1.48, 0, 0.03), .spine: v(0.08, 0, 0), .chest: v(0.05, 0.03, 0),
            .neck: v(0.25, 0, 0), .head: v(-0.05, 0.3, 0.03), .lUpperArm: v(0.5, 0, 0.85),
            .lForearm: v(0.4, 0, 0), .rUpperArm: v(0.2, 0, 0.6), .rForearm: v(0.35, 0, 0),
            .lThigh: v(0.3, 0.1, 0.12), .lShin: v(-0.35, 0, 0), .lFoot: v(-0.3, 0, 0),
            .rThigh: v(0.15, -0.1, 0.05), .rShin: v(-0.2, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(1, .smooth, pose: pLieKd)
        return c
    }

    private static func makeLieDown() -> RigClip {
        var c = RigClip(duration: 4, loops: true, breathing: 0.25)
        c.key(0, .smooth, h: v(0, -0.8, -0.48), [
            .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0.02, 0.05, 0),
            .neck: v(0.05, 0.1, 0), .head: v(-0.15, 0.55, 0.05), .lUpperArm: v(0.35, 0, 0.75),
            .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
            .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
            .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
            .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, -0.8, -0.48), [
            .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0, 0.05, 0),
            .neck: v(0.05, 0.1, 0), .head: v(-0.13, 0.57, 0.05), .lUpperArm: v(0.35, 0, 0.75),
            .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
            .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
            .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
            .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
        ])
        return c
    }

    private static func makeGetUp() -> RigClip {
        var c = RigClip(duration: 0.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pLieKd)
        c.key(0.32, .smooth, h: v(0, -0.66, -0.32), [
            .hips: v(-0.85, 0, 0), .spine: v(0.55, 0, 0), .chest: v(0.25, 0, 0),
            .neck: v(0.1, 0, 0), .head: v(0.1, 0, 0), .lUpperArm: v(-0.5, 0, 0.35),
            .lForearm: v(0.3, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(-0.55, 0, 0.35),
            .rForearm: v(0.3, 0, 0), .rHand: v(-0.8, 0, 0), .lThigh: v(1.55, 0.1, 0.2),
            .lShin: v(-2.1, 0, 0), .lFoot: v(0.2, 0, 0), .rThigh: v(1.35, 0.1, 0.15),
            .rShin: v(-1.9, 0, 0), .rFoot: v(0.2, 0, 0)
        ])
        c.key(0.65, .smooth, h: v(0, -0.36, -0.08), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.15, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.25, 0.3, 0.18), .lShin: v(-0.216, 0, 0), .lFoot: v(-0.859, 0, -0.146),
            .rThigh: v(0.75, 0.4, 0.22), .rShin: v(-1.825, 0, 0), .rFoot: v(1.239, 0, -0.262)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeDizzy() -> RigClip {
        var c = RigClip(duration: 1.9, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0.03, -0.06, 0), [
            .hips: v(0.02, 0.1, 0.07), .spine: v(0.12, 0.05, 0.06), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.15, 0.1, 0.08), .head: v(0.35, 0.2, 0.22), .lUpperArm: v(0.15, 0, 0.25),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.35, 0, 0.12),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.561, 0, 0), .lFoot: v(0.419, 0, -0.191), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.592, 0, 0), .rFoot: v(0.576, 0, -0.035)
        ])
        c.key(0.25, .smooth, h: v(0, -0.09, 0.02), [
            .hips: v(0.06, -0.05, 0), .spine: v(0.18, 0, 0), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.2, 0, 0), .head: v(0.5, 0, 0), .lUpperArm: v(0.3, 0, 0.18),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.25, 0, 0.2),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.737, 0, 0), .lFoot: v(0.646, 0, -0.128), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.65, 0, 0), .rFoot: v(0.659, 0, -0.112)
        ])
        c.key(0.5, .smooth, h: v(-0.03, -0.06, 0), [
            .hips: v(0.02, -0.1, -0.07), .spine: v(0.12, -0.05, -0.06), .chest: v(0.12, -0.05, -0.05),
            .neck: v(0.15, -0.1, -0.08), .head: v(0.35, -0.2, -0.22), .lUpperArm: v(0.35, 0, 0.12),
            .lForearm: v(0.55, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.15, 0, 0.25),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.05, 0.2, 0.1),
            .lShin: v(-0.592, 0, 0), .lFoot: v(0.576, 0, -0.035), .rThigh: v(0.15, 0.15, 0.12),
            .rShin: v(-0.561, 0, 0), .rFoot: v(0.419, 0, -0.191)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, -0.02), [
            .hips: v(0.06, -0.05, 0), .spine: v(0.06, 0, 0), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.2, 0, 0), .head: v(0.15, 0, 0), .lUpperArm: v(0.3, 0, 0.18),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.25, 0, 0.2),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.548, 0, 0), .lFoot: v(0.457, 0, -0.128), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.466, 0, 0), .rFoot: v(0.474, 0, -0.112)
        ])
        return c
    }

    private static func makeGrab() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.45, .snap, h: v(0, -0.13, 0.12), [
            .hips: v(0.1, -0.15, 0), .spine: v(0.25, 0.05, 0), .chest: v(0.1, 0.05, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.15, 0.05, 0), .lUpperArm: v(1.45, -0.15, 0.12),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(1.45, -0.2, 0.15),
            .rForearm: v(0.4, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-1.122, 0, 0), .lFoot: v(0.466, 0, -0.077), .rThigh: v(-0.32, 0.4, 0.1),
            .rShin: v(-0.259, 0, 0), .rFoot: v(0.675, 0, -0.13)
        ])
        c.key(0.7, .smooth, pose: pGrPull)
        c.key(1, .smooth, pose: pGrPull)
        return c
    }

    private static func makeThrowToss() -> RigClip {
        var c = RigClip(duration: 0.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGrPull)
        c.key(0.35, .smooth, h: v(0, -0.08, 0.02), [
            .hips: v(0, 0.6, 0), .spine: v(-0.2, 0.2, 0), .chest: v(-0.15, 0.35, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, -0.3, 0), .lUpperArm: v(2.2, -0.2, 0.4),
            .lForearm: v(0.7, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(2.3, -0.2, 0.4),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.4, -0.2, 0.08),
            .lShin: v(-0.88, 0, 0), .lFoot: v(0.479, 0, -0.074), .rThigh: v(-0.2, 0, 0.1),
            .rShin: v(-0.386, 0, 0), .rFoot: v(0.587, 0, -0.098)
        ])
        c.key(0.6, .snap, pose: pThSlam)
        c.key(0.75, .smooth, pose: pThSlam)
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeCast() -> RigClip {
        var c = RigClip(duration: 0.45, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.35, .smooth, h: v(0, -0.12, -0.02), [
            .hips: v(0.08, -0.7, 0), .spine: v(0.08, -0.1, 0), .chest: v(0.05, -0.35, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.85, 0), .lUpperArm: v(0.3, -0.85, 0.15),
            .lForearm: v(2, 0, 0), .lHand: v(-0.4, 0, 0), .rUpperArm: v(-0.45, 0.2, 0.3),
            .rForearm: v(1.9, 0, 0), .rHand: v(-0.4, 0, 0), .lThigh: v(0.812, 0.3, 0.06),
            .lShin: v(-0.747, 0, 0), .lFoot: v(0.009, 0, -0.068), .rThigh: v(0.008, 0.4, 0.1),
            .rShin: v(-0.637, 0, 0), .rFoot: v(0.703, 0, -0.131)
        ])
        c.key(0.58, .snap, h: v(0, -0.155, 0.1), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.1, 0), .chest: v(0.06, 0.15, 0),
            .neck: v(0, -0.05, 0), .head: v(0, -0.18, 0), .lUpperArm: v(1.55, -0.35, 0.05),
            .lForearm: v(0.12, 0, 0), .lHand: v(-1, 0, 0), .rUpperArm: v(1.55, 0.05, 0.05),
            .rForearm: v(0.12, 0, 0), .rHand: v(-1, 0, 0), .lThigh: v(0.987, 0.2, 0.06),
            .lShin: v(-1.092, 0, 0), .lFoot: v(0.182, 0, -0.053), .rThigh: v(-0.276, 0.2, 0.1),
            .rShin: v(-0.568, 0, 0), .rFoot: v(0.925, 0, -0.11)
        ])
        c.key(0.78, .smooth, h: v(0, -0.155, 0.1), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.1, 0), .chest: v(0.06, 0.15, 0),
            .neck: v(0, -0.05, 0), .head: v(0, -0.18, 0), .lUpperArm: v(1.55, -0.35, 0.05),
            .lForearm: v(0.3, 0, 0), .lHand: v(-1, 0, 0), .rUpperArm: v(1.55, 0.05, 0.05),
            .rForearm: v(0.3, 0, 0), .rHand: v(-1, 0, 0), .lThigh: v(0.987, 0.2, 0.06),
            .lShin: v(-1.092, 0, 0), .lFoot: v(0.182, 0, -0.053), .rThigh: v(-0.276, 0.2, 0.1),
            .rShin: v(-0.568, 0, 0), .rFoot: v(0.925, 0, -0.11)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeDashStrike() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .smooth, h: v(0, -0.2, 0.05), [
            .hips: v(0.15, -0.1, 0), .spine: v(0.4, 0.05, 0), .chest: v(0.15, 0.05, 0),
            .neck: v(-0.3, 0, 0), .head: v(-0.35, 0, 0), .lUpperArm: v(-0.9, 0.1, 0.3),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.1, 0.3),
            .rForearm: v(0.4, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.95, 0.1, 0.06),
            .lShin: v(-1.418, 0, 0), .lFoot: v(0.615, 0, -0.057), .rThigh: v(-0.55, 0.1, 0.06),
            .rShin: v(-0.7, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.5, .snap, pose: pDsHit)
        c.key(0.72, .smooth, pose: pDsHit)
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeVictory() -> RigClip {
        var c = RigClip(duration: 1.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.18, .snap, pose: pViUp)
        c.key(0.4, .smooth, h: v(0, -0.05, 0), [
            .spine: v(-0.08, 0, 0), .chest: v(-0.1, 0.1, 0), .neck: v(-0.15, 0, 0),
            .head: v(-0.3, -0.1, 0), .lUpperArm: v(0.15, 0, 0.3), .lForearm: v(0.7, 0, 0),
            .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.95, 0, 0.18), .rForearm: v(0.55, 0, 0),
            .lThigh: v(0.05, 0.25, 0.16), .lShin: v(-0.495, 0, 0), .lFoot: v(0.444, 0, -0.16),
            .rThigh: v(0, 0.3, 0.14), .rShin: v(-0.46, 0, 0), .rFoot: v(0.46, 0, -0.14)
        ])
        c.key(0.55, .snap, pose: pViUp)
        c.key(1, .smooth, pose: pViUp)
        return c
    }

    private static func makeDefeat() -> RigClip {
        var c = RigClip(duration: 1.4, loops: false, breathing: 0.5)
        c.key(0, .smooth, pose: pHh)
        c.key(0.35, .accel, h: v(0, -0.44, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.35, 0, 0.04), .chest: v(0.25, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.5, 0.1, 0.08), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        c.key(0.45, .snap, h: v(0, -0.43, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.35, 0, 0.04), .chest: v(0.25, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.5, 0.1, 0.08), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.45, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.5, 0, 0.05), .chest: v(0.3, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.6, 0.15, 0.12), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        return c
    }

    private static func makeTaunt() -> RigClip {
        var c = RigClip(duration: 1.2, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.2, .smooth, pose: pTa1)
        c.key(0.35, .smooth, pose: pTa2)
        c.key(0.5, .smooth, pose: pTa1)
        c.key(0.65, .smooth, pose: pTa2)
        c.key(0.8, .smooth, pose: pTa1)
        c.key(1, .smooth, pose: pTa1)
        return c
    }

    private static func makeTalk() -> RigClip {
        var c = RigClip(duration: 2.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.04, 0.08, 0),
            .neck: v(0.02, 0, 0), .head: v(0.06, -0.08, 0.02), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.45, -0.1, 0.18),
            .rForearm: v(1.35, 0, 0), .rHand: v(-0.35, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(0.33, .smooth, h: v(-0.008, -0.018, 0), [
            .hips: v(0, 0, -0.02), .spine: v(-0.02, 0.02, 0), .chest: v(-0.035, -0.02, 0.012),
            .neck: v(0.02, 0, 0), .head: v(-0.04, 0.06, -0.02), .lUpperArm: v(0.4, -0.15, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(-0.4, 0, 0), .rUpperArm: v(0.35, -0.2, 0.22),
            .rForearm: v(1.1, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.084, 0.12, 0.07),
            .lShin: v(-0.334, 0, 0), .lFoot: v(0.252, 0, -0.05), .rThigh: v(0.043, 0.15, 0.06),
            .rShin: v(-0.347, 0, 0), .rFoot: v(0.301, 0, -0.08)
        ])
        c.key(0.66, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.03, -0.08, 0),
            .neck: v(0.02, 0, 0), .head: v(0.1, 0.1, 0), .lUpperArm: v(0.5, -0.1, 0.2),
            .lForearm: v(1.45, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(0.1, 0, 0.12),
            .rForearm: v(0.5, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makePoint() -> RigClip {
        var c = RigClip(duration: 1, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.3, .snap, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.05, 0), .chest: v(-0.05, 0.22, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, -0.2, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.55, 0.1, 0.05),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(1, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.05, 0), .chest: v(-0.05, 0.22, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, -0.2, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.5, 0.1, 0.05),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makeCrossArms() -> RigClip {
        var c = RigClip(duration: 3.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0.02, -0.015, 0), [
            .hips: v(0, 0.05, -0.04), .spine: v(-0.03, 0, 0), .chest: v(-0.06, 0, 0),
            .head: v(0.02, -0.05, 0.02), .lUpperArm: v(0.25, -1.3, 0.12), .lForearm: v(1.4, 0, 0),
            .rUpperArm: v(0.32, -1.35, 0.12), .rForearm: v(1.35, 0, 0), .lThigh: v(0.109, 0.15, 0.1),
            .lShin: v(-0.362, 0, 0), .lFoot: v(0.259, 0, -0.06), .rThigh: v(-0.04, 0.12, 0.04),
            .rShin: v(-0.194, 0, 0), .rFoot: v(0.23, 0, -0.08)
        ])
        c.key(0.5, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0, 0.05, -0.04), .spine: v(-0.03, 0, 0), .chest: v(-0.04, 0.03, 0),
            .head: v(0.05, 0.12, 0), .lUpperArm: v(0.25, -1.3, 0.12), .lForearm: v(1.4, 0, 0),
            .rUpperArm: v(0.32, -1.35, 0.12), .rForearm: v(1.35, 0, 0), .lThigh: v(0.128, 0.15, 0.1),
            .lShin: v(-0.39, 0, 0), .lFoot: v(0.268, 0, -0.06), .rThigh: v(0.024, 0.12, 0.04),
            .rShin: v(-0.328, 0, 0), .rFoot: v(0.299, 0, -0.08)
        ])
        return c
    }

    private static func makeLookAround() -> RigClip {
        var c = RigClip(duration: 5, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.25, .smooth, pose: pLookl)
        c.key(0.45, .smooth, pose: pLookl)
        c.key(0.6, .smooth, pose: pStand)
        c.key(0.75, .smooth, pose: pLookr)
        c.key(0.9, .smooth, pose: pLookr)
        return c
    }

    private static func makeKneel() -> RigClip {
        var c = RigClip(duration: 1, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.5, .smooth, h: v(0, -0.42, -0.05), [
            .hips: v(0, 0.1, 0), .spine: v(0.12, 0, 0), .chest: v(0.1, 0, 0),
            .neck: v(0.15, 0, 0), .head: v(0.3, 0, 0), .lUpperArm: v(0.55, -0.2, 0.25),
            .lForearm: v(1.1, 0, 0), .rUpperArm: v(0.15, 0, 0.12), .rForearm: v(0.3, 0, 0),
            .lThigh: v(1.5, 0.15, 0.08), .lShin: v(-1.966, 0, 0), .lFoot: v(0.466, 0, -0.006),
            .rThigh: v(-0.08, 0.1, 0.06), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.9, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.425, -0.05), [
            .hips: v(0, 0.1, 0), .spine: v(0.12, 0, 0), .chest: v(0.1, 0, 0),
            .neck: v(0.15, 0, 0), .head: v(0.35, 0, 0), .lUpperArm: v(0.55, -0.2, 0.25),
            .lForearm: v(1.1, 0, 0), .rUpperArm: v(0.15, 0, 0.12), .rForearm: v(0.3, 0, 0),
            .lThigh: v(1.5, 0.15, 0.08), .lShin: v(-1.966, 0, 0), .lFoot: v(0.466, 0, -0.006),
            .rThigh: v(-0.08, 0.1, 0.06), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.9, 0, 0)
        ])
        return c
    }

    private static func makeCelebrate() -> RigClip {
        var c = RigClip(duration: 1.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.15, .snap, pose: pCeUp)
        c.key(0.3, .smooth, pose: pCePump)
        c.key(0.45, .snap, pose: pCeUp)
        c.key(0.6, .smooth, pose: pCePump)
        c.key(0.75, .snap, pose: pCeUp)
        c.key(1, .smooth, pose: pCeUp)
        return c
    }
}
