import Foundation
import UIKit
import SceneKit
import QuartzCore
import simd

// =====================================================================
//  SILKSTRIKE – CharacterRig
//  Prozedurale, stilisiert-realistische Figur aus SceneKit-Grundkörpern:
//  Gelenkhierarchie, PBR-Materialien aus FighterLook, Accessoires mit
//  Sekundärbewegung (Umhang, Schal, Kittel, Ranken), Materialzustände
//  (verkohlt / gefroren / Schatten), Treffer-Blitz und Zerstückelung.
//
//  Hierarchie: node (Wurzel an den Füßen, Blick +Z) → hips → spine → chest → neck → head,
//  chest → Oberarme → Unterarme → Hände, hips → Oberschenkel → Schienbeine → Füße.
//  Jedes Gelenk dreht um seinen Gelenkpunkt; die Geometrie hängt als Kind darunter.
// =====================================================================

enum Limb {
    case head, leftArm, rightArm, leftLeg, rightLeg, upperBody
}

enum RigMaterialState {
    case normal, charred, frozen, shadow
}

final class CharacterRig {

    // MARK: - Öffentliche API

    /// Wurzel an den Füßen; die Figur schaut lokal nach +Z.
    let node: SCNNode
    private(set) var look: FighterLook
    /// Körpergröße in Metern.
    let height: Float
    private(set) var currentClip: AnimClip = .idle
    /// Wird additiv auf die Clip-Pose gelegt (z.B. Lehnen beim Schwingen). hipsOffset in Metern (1,80-m-Figur).
    var proceduralOverride: Pose?

    /// 0...1 – bei One-Shots der Fortschritt, bei Schleifen die Phase im Zyklus.
    var clipProgress: Float {
        let d = Swift.max(0.0001, clipDuration)
        if clipData.loops {
            let p = (clipTime / d).truncatingRemainder(dividingBy: 1)
            return p.isFinite ? Swift.max(0, p) : 0
        }
        return Swift.min(1, Swift.max(0, clipTime / d))
    }

    /// true, sobald ein One-Shot-Clip durchgelaufen ist (hält dann das letzte Bild). Schleifen: immer false.
    var clipFinished: Bool {
        return !clipData.loops && clipTime >= clipDuration
    }

    var isDismembered: Bool {
        return !detachedLimbs.isEmpty || pelvisDetached
    }

    // MARK: - Interne Typen

    private struct Dims {
        var s: Float = 1        // Körpergröße / 1,80 m
        var ws: Float = 1       // Schulter-/Brustbreite
        var hw: Float = 1       // Hüftbreite
        var ts: Float = 1       // Dicke der Gliedmaßen
        var td: Float = 1       // Rumpftiefe
        var head: Float = 1     // Kopfgröße
        var belly: Float = 1
        var armSpread: Float = 0  // zusätzliche Abspreizung der Arme (breite Figuren)
    }

    private enum MatRole {
        case body       // reagiert auf Blitz und Materialzustände
        case glow       // leuchtende Details (Augen, Linien)
    }

    private final class MatEntry {
        let mat: SCNMaterial
        let role: MatRole
        let diffuse: UIColor
        let rough: Float
        let metal: Float
        let emission: UIColor
        let emissionIntensity: Float

        init(mat: SCNMaterial, role: MatRole, diffuse: UIColor, rough: Float, metal: Float,
             emission: UIColor, emissionIntensity: Float) {
            self.mat = mat
            self.role = role
            self.diffuse = diffuse
            self.rough = rough
            self.metal = metal
            self.emission = emission
            self.emissionIntensity = emissionIntensity
        }
    }

    private struct Palette {
        let suit: SCNMaterial
        let panel: SCNMaterial
        let skin: SCNMaterial
        let glove: SCNMaterial
        let boot: SCNMaterial
        let dark: SCNMaterial
        let glow: SCNMaterial
        let lens: SCNMaterial
        let metal: SCNMaterial
        let gold: SCNMaterial
        let hair: SCNMaterial
        let web: SCNMaterial
        let cyber: SCNMaterial
        let cloth: SCNMaterial
        let coat: SCNMaterial
        let blade: SCNMaterial
        let horn: SCNMaterial
        let eyeWhite: SCNMaterial
        let lips: SCNMaterial
        let headMat: SCNMaterial
        let superSuit: Bool     // Heldenanzug-Details (Seitenpaneele, Knieschoner, Stulpen)
    }

    /// Kette aus Segmenten, die per Schwerkraft + Fahrtwind + Flattern nachschwingt (Umhang, Schal, Kittel).
    private final class SwayChain {
        let anchor: SCNNode
        let segments: [SCNNode]
        let ref: SCNNode
        let side: Float          // -1: hinter dem Körper halten, +1: davor, 0: frei
        let minOffset: Float
        let stiffness: Float
        let drag: Float
        let flutter: Float
        let phase: Float
        var lastPos: SIMD3<Float>?
        var vel = SIMD3<Float>(0, 0, 0)

        init(anchor: SCNNode, segments: [SCNNode], ref: SCNNode, side: Float, minOffset: Float,
             stiffness: Float, drag: Float, flutter: Float, phase: Float) {
            self.anchor = anchor
            self.segments = segments
            self.ref = ref
            self.side = side
            self.minOffset = minOffset
            self.stiffness = stiffness
            self.drag = drag
            self.flutter = flutter
            self.phase = phase
        }

        func reset() {
            lastPos = nil
            vel = SIMD3<Float>(0, 0, 0)
        }

        func step(dt: Float, time: Float) {
            guard dt > 0 else { return }
            let p = anchor.simdWorldPosition
            if let lp = lastPos {
                let raw = (p - lp) / dt
                if raw.x.isFinite && raw.y.isFinite && raw.z.isFinite && simd_length(raw) < 80 {
                    vel = damp3(vel, raw, lambda: 12, dt: dt)
                }
            }
            lastPos = p
            let speed = simd_length(vel)
            let refQ = ref.simdWorldOrientation
            let refInv = refQ.inverse
            let gravity = SIMD3<Float>(0, -9.8, 0)
            for i in 0..<segments.count {
                let seg = segments[i]
                guard let parent = seg.parent else { continue }
                let fi = Float(i)
                let t = time * (5.5 + fi * 0.45) + phase + fi * 0.75
                let fl = flutter * (0.3 + Swift.min(speed, 14) / 14)
                var wind = -vel * drag
                wind += SIMD3<Float>(sinf(t), 0.4 * cosf(t * 1.37), sinf(t * 0.71 + 1.3)) * (fl * 3.0)
                var dirW = safeNormalize(gravity + wind, fallback: SIMD3<Float>(0, -1, 0))
                if side != 0 {
                    var dr = refInv.act(dirW)
                    if side < 0 {
                        dr.z = Swift.min(dr.z, -minOffset)
                    } else {
                        dr.z = Swift.max(dr.z, minOffset)
                    }
                    dr.y = Swift.min(dr.y, 0.3)
                    dirW = refQ.act(safeNormalize(dr, fallback: SIMD3<Float>(0, -1, 0)))
                }
                let local = parent.simdWorldOrientation.inverse.act(dirW)
                let target = CharacterRig.rotation(from: SIMD3<Float>(0, -1, 0), to: local)
                let k = 1 - expf(-stiffness * Swift.max(0.35, 1 - fi * 0.09) * dt)
                seg.simdOrientation = simd_slerp(seg.simdOrientation, target, Swift.max(0, Swift.min(1, k)))
            }
        }
    }

    /// Wellenförmig bewegte Ranke (schwarze Tentakel).
    private final class Tendril {
        let segments: [SCNNode]
        let base: [SIMD3<Float>]
        let phase: Float
        let freq: Float
        let amp: Float

        init(segments: [SCNNode], base: [SIMD3<Float>], phase: Float, freq: Float, amp: Float) {
            self.segments = segments
            self.base = base
            self.phase = phase
            self.freq = freq
            self.amp = amp
        }

        func step(time: Float) {
            for i in 0..<segments.count {
                let fi = Float(i)
                let w = time * freq + phase + fi * 0.85
                let b = i < base.count ? base[i] : SIMD3<Float>(0, 0, 0)
                let e = b + SIMD3<Float>(sinf(w) * amp, 0, cosf(w * 0.83 + fi) * amp * 0.8)
                segments[i].simdOrientation = CharacterRig.quatYXZ(e)
            }
        }
    }

    // MARK: - Zustand

    private let quality: QualityPreset
    private var dims = Dims()
    private var joints: [Joint: SCNNode] = [:]
    private var restPositions: [Joint: SIMD3<Float>] = [:]
    private var visRoots: [Joint: SCNNode] = [:]

    // Animation
    private var clipData: RigClip = RigAnimLibrary.clip(.idle)
    private var clipDuration: Float = 3
    private var clipTime: Float = 0
    private var fromPose = Pose()
    private var blendTime: Float = 0
    private var blendDuration: Float = 0
    private var lastBasePose = Pose()
    private var animTime: Float = 0
    private var hasUpdated = false

    // Sekundärbewegung / Accessoires
    private var swayChains: [SwayChain] = []
    private var tendrils: [Tendril] = []
    private var flameLights: [SCNLight] = []
    private var flameLightBase: CGFloat = 0

    // Materialien
    private var matEntries: [MatEntry] = []
    private var matState: RigMaterialState = .normal
    private var matAmount: Float = 0
    private var crackHeat: Float = 0
    private var flashAmount: Float = 0
    private var flashColor: UIColor = .white
    private var rimInstalled = false

    // Zerstückelung
    private var detachedLimbs: Set<Limb> = []
    private var stumpNodes: [SCNNode] = []
    private var ownDebris: [SCNNode] = []
    private static var liveDebris: [SCNNode] = []
    private static let maxLiveDebris = 20

    // Gemeinsame Bildressourcen
    private static var weaveCache: UIImage?
    private static var crackCache: UIImage?

    private static let charColor = UIColor(red: 0.035, green: 0.03, blue: 0.028, alpha: 1)
    private static let iceColor = UIColor(red: 0.72, green: 0.88, blue: 1.0, alpha: 1)
    private static let iceGlow = UIColor(red: 0.25, green: 0.75, blue: 1.0, alpha: 1)
    private static let shadowColor = UIColor(red: 0.012, green: 0.01, blue: 0.018, alpha: 1)
    private static let shadowGlow = UIColor(red: 0.55, green: 0.12, blue: 1.0, alpha: 1)

    private static let rimShaderSource = """
    #pragma arguments
    float rigRimAmount;
    float rigRimHue;
    #pragma body
    float rigRimTerm = 1.0 - saturate(dot(normalize(_surface.view), normalize(_surface.normal)));
    float3 rigRimColor = mix(float3(0.55, 0.12, 1.0), float3(0.45, 0.85, 1.0), rigRimHue);
    _surface.emission.rgb += rigRimColor * (rigRimTerm * rigRimTerm * rigRimTerm) * rigRimAmount;
    """

    // MARK: - Init

    init(look: FighterLook, quality: QualityPreset) {
        self.look = look
        self.quality = quality
        var h = look.height
        if !h.isFinite { h = 1.8 }
        self.height = Swift.max(1.4, Swift.min(2.7, h))
        self.node = SCNNode()
        node.name = "rig.root"
        dims = CharacterRig.makeDims(look: look, height: height)
        buildSkeleton()
        buildVisuals()
        clipData = RigAnimLibrary.clip(.idle)
        clipDuration = clipData.duration
        let first = clipData.sample(0)
        lastBasePose = first
        fromPose = first
        applyPose(first)
    }

    // MARK: - Gelenke

    func joint(_ j: Joint) -> SCNNode {
        return joints[j] ?? node
    }

    /// Weltposition eines Gelenks. Kopf = Kopfmitte, Hände = Faustmitte, Füße = Fußmitte, sonst Gelenkpunkt.
    func worldPosition(of j: Joint) -> SIMD3<Float> {
        guard let n = joints[j] else { return node.simdWorldPosition }
        let s = dims.s
        switch j {
        case .head:
            return n.simdConvertPosition(headCenterLocal, to: nil)
        case .lHand, .rHand:
            return n.simdConvertPosition(SIMD3<Float>(0, -0.065 * s, 0), to: nil)
        case .lFoot, .rFoot:
            return n.simdConvertPosition(SIMD3<Float>(0, -0.045 * s, 0.06 * s), to: nil)
        default:
            return n.simdWorldPosition
        }
    }

    // MARK: - Animation

    /// Spielt einen Clip. Schleifen laufen endlos, One-Shots einmal (duration skaliert sie) und halten das letzte Bild.
    /// Derselbe Clip ohne restart ändert nur die Länge (z.B. Lauftempo). blend = Überblendzeit in Sekunden.
    func play(_ clip: AnimClip, duration: Float? = nil, restart: Bool = false, blend: Float = 0.08) {
        let data = RigAnimLibrary.clip(clip)
        var dur = data.duration
        if let d = duration, d.isFinite, d > 0.01 {
            dur = d
        }
        if clip == currentClip && !restart {
            if data.loops {
                let phase = clipTime / Swift.max(0.0001, clipDuration)
                clipDuration = dur
                clipTime = phase * dur
            } else if duration != nil {
                let progress = clipTime / Swift.max(0.0001, clipDuration)
                clipDuration = dur
                clipTime = progress * dur
            }
            return
        }
        fromPose = lastBasePose
        blendTime = 0
        var b = blend
        if !b.isFinite || b < 0 { b = 0 }
        blendDuration = hasUpdated ? b : 0
        currentClip = clip
        clipData = data
        clipDuration = dur
        clipTime = 0
        evaluateAndApply()
    }

    /// Pro Frame aufrufen (dt bereits zeitskaliert für Zeitlupe/Hit-Stop).
    func update(dt: Float) {
        var d = dt
        if !d.isFinite || d < 0 { d = 0 }
        d = Swift.min(d, 0.1)
        animTime += d
        clipTime += d
        blendTime += d
        evaluateAndApply()
        if d > 0 {
            for c in swayChains { c.step(dt: d, time: animTime) }
        }
        for t in tendrils { t.step(time: animTime) }
        updateFlames()
        updateMaterialTimers(d)
        hasUpdated = true
    }

    private func sampleClip() -> Pose {
        let d = Swift.max(0.0001, clipDuration)
        if clipData.loops {
            return clipData.sample(clipTime / d)
        }
        return clipData.sample(Swift.min(1, clipTime / d))
    }

    private func evaluateAndApply() {
        var base = sampleClip()
        if blendDuration > 0.0001 && blendTime < blendDuration {
            let u = Swift.max(0, Swift.min(1, blendTime / blendDuration))
            let sm = u * u * (3 - 2 * u)
            base = Pose.rigBlendShortest(fromPose, base, sm)
        }
        lastBasePose = base
        var outPose = base
        // Atmung (prozedural, additiv)
        let br = clipData.breathing
        if br > 0.001 {
            let w = sinf(animTime * 2 * Float.pi / 3.4) * br
            outPose[.chest] = outPose[.chest] + SIMD3<Float>(-0.018 * w, 0, 0)
            outPose[.spine] = outPose[.spine] + SIMD3<Float>(0.006 * w, 0, 0)
            outPose[.neck] = outPose[.neck] + SIMD3<Float>(0.012 * w, 0, 0)
            outPose[.lUpperArm] = outPose[.lUpperArm] + SIMD3<Float>(0, 0, 0.012 * w)
            outPose[.rUpperArm] = outPose[.rUpperArm] + SIMD3<Float>(0, 0, 0.012 * w)
        }
        if let o = proceduralOverride {
            outPose = outPose.rigAdding(o)
        }
        applyPose(outPose)
    }

    private func applyPose(_ pose: Pose) {
        let rest = RigAnimLibrary.restPose
        let spread = dims.armSpread
        for j in Joint.allCases {
            guard let n = joints[j] else { continue }
            var r = rest[j] + pose[j]
            if spread != 0 && (j == .lUpperArm || j == .rUpperArm) {
                r.z += spread
            }
            let e = j.rigRawEuler(r)
            if !(e.x.isFinite && e.y.isFinite && e.z.isFinite) { continue }
            n.simdOrientation = CharacterRig.quatYXZ(e)
        }
        if let hn = joints[.hips], let hp = restPositions[.hips] {
            let off = pose.hipsOffset * dims.s
            if off.x.isFinite && off.y.isFinite && off.z.isFinite {
                hn.simdPosition = hp + off
            }
        }
    }

    // MARK: - Treffer-Blitz & Materialzustände

    /// Kurzer emissiver Blitz (klingt in ~0,12 s ab).
    func flashHit(color: UIColor = .white) {
        flashColor = color
        flashAmount = 1
        refreshMaterials()
    }

    /// amount 0...1 blendet vom normalen Aussehen zum Zustand.
    func setMaterialState(_ s: RigMaterialState, amount: Float) {
        var a = amount.isFinite ? amount : 0
        a = Swift.max(0, Swift.min(1, a))
        if s == .charred {
            if matState != .charred {
                crackHeat = 1
            } else if a > matAmount + 0.05 {
                crackHeat = Swift.max(crackHeat, 0.85)
            }
        }
        matState = s
        matAmount = (s == .normal) ? 0 : a
        if (s == .frozen || s == .shadow) && a > 0 {
            installRimShader()
        }
        refreshMaterials()
    }

    /// Neues Aussehen (z.B. Anzug wird schwarz): baut Geometrie, Materialien und Accessoires neu auf.
    func setLook(_ newLook: FighterLook) {
        look = newLook
        dims = CharacterRig.makeDims(look: newLook, height: height)
        buildVisuals()
        applyPose(lastBasePose)
    }

    private func updateMaterialTimers(_ dt: Float) {
        var dirty = false
        if flashAmount > 0 {
            flashAmount = Swift.max(0, flashAmount - dt / 0.12)
            dirty = true
        }
        if matState == .charred && matAmount > 0 && crackHeat > 0.14 {
            crackHeat = Swift.max(0.14, crackHeat - dt * 0.22)
            dirty = true
        }
        if dirty {
            refreshMaterials()
        }
    }

    private func installRimShader() {
        if rimInstalled { return }
        rimInstalled = true
        for e in matEntries where e.role == .body {
            e.mat.shaderModifiers = [.surface: CharacterRig.rimShaderSource]
            e.mat.setValue(NSNumber(value: Float(0)), forKey: "rigRimAmount")
            e.mat.setValue(NSNumber(value: Float(0)), forKey: "rigRimHue")
        }
    }

    private func refreshMaterials() {
        let a = matAmount
        let flash = flashAmount
        let cracks: UIImage? = (matState == .charred && a > 0.001) ? CharacterRig.crackTexture() : nil
        for e in matEntries {
            var diffuse = e.diffuse
            var rough = e.rough
            var metal = e.metal
            var emis: Any = e.emission
            var eInt = e.emissionIntensity
            var rim: Float = 0
            var rimHue: Float = 0
            if a > 0.001 {
                switch matState {
                case .normal:
                    break
                case .charred:
                    diffuse = e.diffuse.blended(with: CharacterRig.charColor, t: CGFloat(a))
                    if e.role == .body {
                        rough = lerpf(e.rough, 1, a)
                        metal = lerpf(e.metal, 0.02, a)
                        let heat = crackHeat * a
                        if heat > 0.01, let c = cracks {
                            emis = c
                            eInt = 2.6 * heat
                        }
                    } else {
                        eInt = e.emissionIntensity * (1 - a)
                    }
                case .frozen:
                    if e.role == .body {
                        diffuse = e.diffuse.blended(with: CharacterRig.iceColor, t: CGFloat(a * 0.85))
                        rough = lerpf(e.rough, 0.15, a)
                        metal = lerpf(e.metal, 0.12, a)
                        emis = CharacterRig.iceGlow
                        eInt = 0.3 * a
                        rim = 1.2 * a
                        rimHue = 1
                    }
                case .shadow:
                    if e.role == .body {
                        diffuse = e.diffuse.blended(with: CharacterRig.shadowColor, t: CGFloat(a))
                        rough = lerpf(e.rough, 0.1, a)
                        metal = lerpf(e.metal, 0.35, a)
                        emis = CharacterRig.shadowGlow
                        eInt = 0.12 * a
                        rim = 1.8 * a
                        rimHue = 0
                    } else {
                        emis = e.emission.blended(with: CharacterRig.shadowGlow, t: CGFloat(a))
                    }
                }
            }
            if flash > 0.001 && e.role == .body {
                emis = flashColor
                eInt = Swift.max(eInt, 3.0 * flash)
            }
            e.mat.diffuse.contents = diffuse
            e.mat.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, rough)))
            e.mat.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metal)))
            e.mat.emission.contents = emis
            e.mat.emission.intensity = CGFloat(eInt)
            if rimInstalled && e.role == .body {
                e.mat.setValue(NSNumber(value: rim), forKey: "rigRimAmount")
                e.mat.setValue(NSNumber(value: rimHue), forKey: "rigRimHue")
            }
        }
    }

    private func updateFlames() {
        if flameLights.isEmpty { return }
        let t = animTime
        let f1: Float = 0.14 * sinf(t * 17.0)
        let f2: Float = 0.08 * sinf(t * 31.0 + 1.3)
        let f: Float = 0.78 + f1 + f2
        let hidden = isDismembered && detachedLimbs.contains(.upperBody)
        for l in flameLights {
            l.intensity = hidden ? 0 : flameLightBase * CGFloat(f)
        }
    }

    // MARK: - Proportionen & Skelett

    private static func makeDims(look: FighterLook, height: Float) -> Dims {
        var d = Dims()
        d.s = height / 1.8
        switch look.build {
        case .lean:
            d.ws = 0.93; d.hw = 0.95; d.ts = 0.86; d.td = 0.92; d.head = 1.0; d.belly = 0.95; d.armSpread = 0
        case .athletic:
            d.ws = 1.0; d.hw = 1.0; d.ts = 1.0; d.td = 1.0; d.head = 1.0; d.belly = 1.0; d.armSpread = 0
        case .heavy:
            d.ws = 1.18; d.hw = 1.12; d.ts = 1.32; d.td = 1.2; d.head = 0.96; d.belly = 1.15; d.armSpread = 0.14
        case .giant:
            d.ws = 1.26; d.hw = 1.15; d.ts = 1.4; d.td = 1.22; d.head = 0.9; d.belly = 1.05; d.armSpread = 0.16
        }
        return d
    }

    /// Gelenkpositionen relativ zum Elterngelenk (Referenz 1,80 m, skaliert).
    private func layoutPositions() -> [Joint: SIMD3<Float>] {
        let d = dims
        let s = d.s
        let shoulderX = 0.205 * s * d.ws
        let hipX = 0.092 * s * d.hw
        var p: [Joint: SIMD3<Float>] = [:]
        p[.hips] = SIMD3<Float>(0, 0.954 * s, 0)
        p[.spine] = SIMD3<Float>(0, 0.10 * s, 0)
        p[.chest] = SIMD3<Float>(0, 0.21 * s, 0)
        p[.neck] = SIMD3<Float>(0, 0.225 * s, -0.01 * s)
        p[.head] = SIMD3<Float>(0, 0.085 * s, 0.01 * s)
        p[.lUpperArm] = SIMD3<Float>(shoulderX, 0.195 * s, -0.01 * s)
        p[.rUpperArm] = SIMD3<Float>(-shoulderX, 0.195 * s, -0.01 * s)
        p[.lForearm] = SIMD3<Float>(0, -0.29 * s, 0)
        p[.rForearm] = SIMD3<Float>(0, -0.29 * s, 0)
        p[.lHand] = SIMD3<Float>(0, -0.26 * s, 0)
        p[.rHand] = SIMD3<Float>(0, -0.26 * s, 0)
        p[.lThigh] = SIMD3<Float>(hipX, -0.06 * s, 0)
        p[.rThigh] = SIMD3<Float>(-hipX, -0.06 * s, 0)
        p[.lShin] = SIMD3<Float>(0, -0.405 * s, 0)
        p[.rShin] = SIMD3<Float>(0, -0.405 * s, 0)
        p[.lFoot] = SIMD3<Float>(0, -0.408 * s, 0)
        p[.rFoot] = SIMD3<Float>(0, -0.408 * s, 0)
        return p
    }

    private func buildSkeleton() {
        restPositions = layoutPositions()
        for j in Joint.allCases {
            let n = SCNNode()
            n.name = "rig." + j.rawValue
            n.simdPosition = restPositions[j] ?? SIMD3<Float>(0, 0, 0)
            if let p = j.rigParent, let pn = joints[p] {
                pn.addChildNode(n)
            } else {
                node.addChildNode(n)
            }
            joints[j] = n
        }
    }

    /// Kopfmitte im Kopfgelenk-Raum.
    private var headCenterLocal: SIMD3<Float> {
        let k: Float = dims.s * dims.head
        return SIMD3<Float>(0, 0.105, 0.005) * k
    }

    private var headRadius: Float {
        return 0.105 * dims.s * dims.head
    }

    private var headScale: SIMD3<Float> {
        return SIMD3<Float>(0.86 + (dims.ws - 1) * 0.15, 1.06, 1.0)
    }

    /// Brustkorb-Ellipsoid (Chest-Raum) – gemeinsam für Geometrie und Netzlinien.
    private var chestSurface: WebSurface {
        let d = dims
        return WebSurface(c: pv(0, 0.085, -0.005), r: 0.165 * d.s, k: SIMD3<Float>(1.1 * d.ws, 0.98, 0.7 * d.td))
    }

    /// Rücken/Seitenpaneel-Ellipsoid (Chest-Raum).
    private var latsSurface: WebSurface {
        let d = dims
        return WebSurface(c: pv(0, 0.06, -0.03 * d.td), r: 0.165 * d.s, k: SIMD3<Float>(1.135 * d.ws, 0.92, 0.6 * d.td))
    }

    // MARK: - Mathe-Helfer

    /// Euler (Posen-Raum bereits in Rohwinkel umgerechnet) → Quaternion, Reihenfolge Roll → Pitch → Yaw.
    private static func quatYXZ(_ e: SIMD3<Float>) -> simd_quatf {
        let qx = simd_quatf(angle: e.x, axis: SIMD3<Float>(1, 0, 0))
        let qy = simd_quatf(angle: e.y, axis: SIMD3<Float>(0, 1, 0))
        let qz = simd_quatf(angle: e.z, axis: SIMD3<Float>(0, 0, 1))
        return qy * qx * qz
    }

    /// Kürzeste Drehung, die Richtung a auf Richtung b abbildet (robust bei (anti)parallelen Vektoren).
    private static func rotation(from a: SIMD3<Float>, to b: SIMD3<Float>) -> simd_quatf {
        let identity = simd_quatf(angle: 0, axis: SIMD3<Float>(0, 1, 0))
        let la = simd_length(a)
        let lb = simd_length(b)
        if !(la > 1e-6) || !(lb > 1e-6) || !la.isFinite || !lb.isFinite { return identity }
        let u = a / la
        let v = b / lb
        let d = simd_dot(u, v)
        if d > 0.99999 { return identity }
        if d < -0.99999 {
            var axis = simd_cross(u, SIMD3<Float>(1, 0, 0))
            if simd_length(axis) < 1e-4 { axis = simd_cross(u, SIMD3<Float>(0, 0, 1)) }
            return simd_quatf(angle: Float.pi, axis: simd_normalize(axis))
        }
        return simd_quatf(from: u, to: v)
    }

    // MARK: - Materialien

    private func registerMaterial(_ color: UIColor, rough: Float, metal: Float, emission: UIColor? = nil,
                                  emissionIntensity: Float = 1, role: MatRole = .body, doubleSided: Bool = false,
                                  normalMap: UIImage? = nil, normalTile: Float = 6) -> SCNMaterial {
        let r = Swift.max(0.02, Swift.min(1, rough))
        let mt = Swift.max(0, Swift.min(1, metal))
        let mat = Render.pbr(color, roughness: r, metalness: mt, emission: emission, emissionIntensity: emissionIntensity)
        mat.isDoubleSided = doubleSided
        if let n = normalMap {
            mat.normal.contents = n
            mat.normal.intensity = 0.6
            mat.normal.wrapS = .repeat
            mat.normal.wrapT = .repeat
            mat.normal.contentsTransform = SCNMatrix4MakeScale(normalTile, normalTile, 1)
        }
        let entry = MatEntry(mat: mat, role: role, diffuse: color, rough: r, metal: mt,
                             emission: emission ?? UIColor.black,
                             emissionIntensity: emission == nil ? 0 : emissionIntensity)
        matEntries.append(entry)
        return mat
    }

    private func makePalette() -> Palette {
        let L = look
        let rough = Swift.max(0.05, Swift.min(1, L.roughness.isFinite ? L.roughness : 0.5))
        let metal = Swift.max(0, Swift.min(1, L.metalness.isFinite ? L.metalness : 0))
        let weave: UIImage? = quality == .performance ? nil : CharacterRig.weaveNormal()
        let superSuit = L.hasMask || L.eyeStyle != .human

        let suit = registerMaterial(L.primaryColor, rough: rough, metal: metal, normalMap: weave)
        let panel = registerMaterial(L.secondaryColor, rough: Swift.max(0.08, rough * 0.7), metal: Swift.min(1, metal + 0.15))
        let skin = registerMaterial(L.skinColor, rough: 0.5, metal: 0)
        let dark = registerMaterial(UIColor(white: 0.045, alpha: 1), rough: 0.45, metal: 0.35)
        let glow = registerMaterial(L.glowColor.withBrightness(0.35), rough: 0.35, metal: 0,
                                    emission: L.glowColor, emissionIntensity: 2.6, role: .glow)
        let lensEmission = UIColor.white.blended(with: L.glowColor, t: 0.12)
        let lens = registerMaterial(UIColor(white: 0.95, alpha: 1), rough: 0.18, metal: 0,
                                    emission: lensEmission, emissionIntensity: 1.5, role: .glow)
        let metalMat = registerMaterial(UIColor(white: 0.6, alpha: 1), rough: 0.28, metal: 1)
        let gold = registerMaterial(UIColor(red: 0.93, green: 0.72, blue: 0.32, alpha: 1), rough: 0.22, metal: 1)
        let hairColor = L.hairColor ?? UIColor(red: 0.12, green: 0.08, blue: 0.05, alpha: 1)
        let hair = registerMaterial(hairColor, rough: 0.72, metal: 0)
        let webEmission = UIColor(red: 0.62, green: 0.66, blue: 0.76, alpha: 1).blended(with: L.glowColor, t: 0.25)
        let web = registerMaterial(UIColor(red: 0.1, green: 0.1, blue: 0.12, alpha: 1), rough: 0.32, metal: 0.8,
                                   emission: webEmission, emissionIntensity: 0.55, role: .glow, doubleSided: true)
        let cyber = registerMaterial(UIColor(red: 0.22, green: 0.23, blue: 0.26, alpha: 1), rough: 0.3, metal: 1)
        let cloth = registerMaterial(L.secondaryColor, rough: 0.82, metal: 0, doubleSided: true)
        let coat = registerMaterial(UIColor(red: 0.9, green: 0.92, blue: 0.94, alpha: 1), rough: 0.78, metal: 0, doubleSided: true)
        let blade = registerMaterial(UIColor(red: 0.86, green: 0.88, blue: 0.92, alpha: 1), rough: 0.12, metal: 1)
        let hornColor = L.secondaryColor.blended(with: UIColor(red: 0.12, green: 0.1, blue: 0.09, alpha: 1), t: 0.55)
        let horn = registerMaterial(hornColor, rough: 0.42, metal: 0.2)
        let eyeWhite = registerMaterial(UIColor(white: 0.9, alpha: 1), rough: 0.2, metal: 0)
        let lipColor = L.skinColor.blended(with: UIColor(red: 0.55, green: 0.2, blue: 0.2, alpha: 1), t: 0.35)
        let lips = registerMaterial(lipColor, rough: 0.45, metal: 0)

        return Palette(suit: suit, panel: panel, skin: skin,
                       glove: superSuit ? panel : skin,
                       boot: superSuit ? panel : dark,
                       dark: dark, glow: glow, lens: lens, metal: metalMat, gold: gold, hair: hair, web: web,
                       cyber: cyber, cloth: cloth, coat: coat, blade: blade, horn: horn, eyeWhite: eyeWhite, lips: lips,
                       headMat: L.hasMask ? suit : skin, superSuit: superSuit)
    }

    /// Feines Rautengewebe als Normal-Map für den Anzug (einmal erzeugt).
    private static func weaveNormal() -> UIImage? {
        if let w = weaveCache { return w }
        let size = 128
        var bytes = [UInt8](repeating: 255, count: size * size * 4)
        func heightAt(_ x: Int, _ y: Int) -> Float {
            let fx = Float((x + size) % size) / Float(size)
            let fy = Float((y + size) % size) / Float(size)
            let u = fx * 2 * Float.pi * 8
            let v = fy * 2 * Float.pi * 8
            let a = abs(sinf((u + v) * 0.5))
            let b = abs(sinf((u - v) * 0.5))
            return a * b
        }
        let strength: Float = 2.2
        for y in 0..<size {
            for x in 0..<size {
                let dx = heightAt(x + 1, y) - heightAt(x - 1, y)
                let dy = heightAt(x, y + 1) - heightAt(x, y - 1)
                let n = simd_normalize(SIMD3<Float>(-dx * strength, -dy * strength, 1))
                let i = (y * size + x) * 4
                bytes[i] = UInt8(Swift.max(0, Swift.min(255, (n.x * 0.5 + 0.5) * 255)))
                bytes[i + 1] = UInt8(Swift.max(0, Swift.min(255, (n.y * 0.5 + 0.5) * 255)))
                bytes[i + 2] = UInt8(Swift.max(0, Swift.min(255, (n.z * 0.5 + 0.5) * 255)))
                bytes[i + 3] = 255
            }
        }
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let info = CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue)
        guard let provider = CGDataProvider(data: Data(bytes) as CFData),
              let cg = CGImage(width: size, height: size, bitsPerComponent: 8, bitsPerPixel: 32,
                               bytesPerRow: size * 4, space: colorSpace, bitmapInfo: info,
                               provider: provider, decode: nil, shouldInterpolate: true,
                               intent: .defaultIntent) else {
            return nil
        }
        let img = UIImage(cgImage: cg)
        weaveCache = img
        return img
    }

    /// Glühende Risse (Emissionstextur für "verkohlt").
    private static func crackTexture() -> UIImage? {
        if let c = crackCache { return c }
        let side: CGFloat = 256
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: side, height: side), format: format)
        var rng = SeededRandom(seed: 0xC4A2_17)
        var paths: [[CGPoint]] = []
        for _ in 0..<22 {
            var p = CGPoint(x: CGFloat(rng.float(0, 256)), y: CGFloat(rng.float(0, 256)))
            var ang = rng.float(0, Float.pi * 2)
            var pts: [CGPoint] = [p]
            let steps = rng.int(5, 12)
            for _ in 0..<steps {
                ang += rng.float(-0.8, 0.8)
                let len = CGFloat(rng.float(8, 22))
                p = CGPoint(x: p.x + CGFloat(cosf(ang)) * len, y: p.y + CGFloat(sinf(ang)) * len)
                pts.append(p)
                if rng.chance(0.18) {
                    let bAng = ang + rng.float(-1.4, 1.4)
                    let bLen = CGFloat(rng.float(10, 26))
                    paths.append([p, CGPoint(x: p.x + CGFloat(cosf(bAng)) * bLen, y: p.y + CGFloat(sinf(bAng)) * bLen)])
                }
            }
            paths.append(pts)
        }
        let img = renderer.image { ctx in
            let cg = ctx.cgContext
            cg.setFillColor(UIColor.black.cgColor)
            cg.fill(CGRect(x: 0, y: 0, width: side, height: side))
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            // weicher Glutschein
            cg.setStrokeColor(UIColor(red: 0.7, green: 0.12, blue: 0.0, alpha: 0.45).cgColor)
            cg.setLineWidth(7)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
            // heller Kern
            cg.setStrokeColor(UIColor(red: 1.0, green: 0.55, blue: 0.12, alpha: 1).cgColor)
            cg.setLineWidth(2.2)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
            cg.setStrokeColor(UIColor(red: 1.0, green: 0.9, blue: 0.6, alpha: 0.9).cgColor)
            cg.setLineWidth(0.8)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
        }
        crackCache = img
        return img
    }

    // MARK: - Geometrie-Helfer

    private var segSphere: Int {
        switch quality {
        case .ultra: return 40
        case .balanced: return 28
        case .performance: return 18
        }
    }

    private var segRadial: Int {
        switch quality {
        case .ultra: return 36
        case .balanced: return 24
        case .performance: return 14
        }
    }

    private var segCap: Int {
        switch quality {
        case .ultra: return 14
        case .balanced: return 9
        case .performance: return 5
        }
    }

    private var particleScale: Float {
        switch quality {
        case .ultra: return 1
        case .balanced: return 0.7
        case .performance: return 0.4
        }
    }

    /// Referenzmaße (1,80 m) → skaliert.
    private func pv(_ x: Float, _ y: Float, _ z: Float) -> SIMD3<Float> {
        return SIMD3<Float>(x, y, z) * dims.s
    }

    /// Container für die Geometrie eines Gelenks (wird bei setLook komplett ersetzt).
    private func container(_ j: Joint) -> SCNNode {
        if let c = visRoots[j] { return c }
        let c = SCNNode()
        c.name = "rig.vis"
        joint(j).addChildNode(c)
        visRoots[j] = c
        return c
    }

    @discardableResult
    private func ellipsoid(_ parent: SCNNode, _ c: SIMD3<Float>, _ r: Float, _ scale: SIMD3<Float>, _ m: SCNMaterial,
                           shadow: Bool = true, detail: Float = 1) -> SCNNode {
        let g = SCNSphere(radius: CGFloat(Swift.max(0.0005, r)))
        g.segmentCount = Swift.max(10, Int(Float(segSphere) * detail))
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        n.simdScale = scale
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func capsule(_ parent: SCNNode, _ a: SIMD3<Float>, _ b: SIMD3<Float>, _ r: Float, _ m: SCNMaterial,
                         shadow: Bool = true, detail: Float = 1) -> SCNNode {
        let d = b - a
        let len = simd_length(d)
        let rr = Swift.max(0.0005, r)
        let g = SCNCapsule(capRadius: CGFloat(rr), height: CGFloat(len + 2 * rr))
        g.radialSegmentCount = Swift.max(6, Int(Float(segRadial) * detail))
        g.capSegmentCount = Swift.max(3, Int(Float(segCap) * detail))
        g.heightSegmentCount = 1
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = (a + b) * 0.5
        n.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: d)
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func box(_ parent: SCNNode, _ c: SIMD3<Float>, _ size: SIMD3<Float>, chamfer: Float, _ m: SCNMaterial,
                     orient: simd_quatf? = nil, shadow: Bool = true) -> SCNNode {
        let smallest = Swift.min(size.x, Swift.min(size.y, size.z))
        let ch = Swift.max(0, Swift.min(chamfer, smallest * 0.49))
        let g = SCNBox(width: CGFloat(size.x), height: CGFloat(size.y), length: CGFloat(size.z), chamferRadius: CGFloat(ch))
        g.chamferSegmentCount = quality == .performance ? 2 : 4
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func cylinder(_ parent: SCNNode, _ c: SIMD3<Float>, r: Float, h: Float, _ m: SCNMaterial,
                          orient: simd_quatf? = nil, scale: SIMD3<Float>? = nil, shadow: Bool = true) -> SCNNode {
        let g = SCNCylinder(radius: CGFloat(Swift.max(0.0005, r)), height: CGFloat(Swift.max(0.0005, h)))
        g.radialSegmentCount = segRadial
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        if let sc = scale { n.simdScale = sc }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    /// Kegel, dessen Grundfläche bei `base` liegt und der entlang `dir` um h wächst.
    @discardableResult
    private func cone(_ parent: SCNNode, base: SIMD3<Float>, dir: SIMD3<Float>, r0: Float, r1: Float, h: Float,
                      _ m: SCNMaterial, shadow: Bool = true) -> SCNNode {
        let g = SCNCone(topRadius: CGFloat(Swift.max(0, r1)), bottomRadius: CGFloat(Swift.max(0.0005, r0)),
                        height: CGFloat(Swift.max(0.0005, h)))
        g.radialSegmentCount = Swift.max(8, segRadial / 2)
        g.materials = [m]
        let n = SCNNode(geometry: g)
        let dn = safeNormalize(dir, fallback: SIMD3<Float>(0, 1, 0))
        n.simdPosition = base + dn * (h * 0.5)
        n.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: dn)
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func torus(_ parent: SCNNode, _ c: SIMD3<Float>, ring: Float, pipe: Float, _ m: SCNMaterial,
                       orient: simd_quatf? = nil, scale: SIMD3<Float>? = nil, shadow: Bool = false) -> SCNNode {
        let g = SCNTorus(ringRadius: CGFloat(Swift.max(0.001, ring)), pipeRadius: CGFloat(Swift.max(0.0005, pipe)))
        g.ringSegmentCount = Swift.max(12, segRadial)
        g.pipeSegmentCount = quality == .performance ? 6 : 10
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        if let sc = scale { n.simdScale = sc }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    // MARK: - Linienmuster (Netzlinien als ein Mesh pro Gelenk)

    private struct WebSurface {
        let c: SIMD3<Float>     // Mittelpunkt
        let r: Float            // Radius
        let k: SIMD3<Float>     // Skalierung je Achse
    }

    private struct LimbEll {
        let c: SIMD3<Float>     // Mittelpunkt
        let e: SIMD3<Float>     // Halbachsen
    }

    /// Querschnitt einer Gliedmaße entlang -Y: Kapseln (yOben, yUnten, Radius) + Ellipsoide (Muskeln).
    private struct LimbShape {
        var caps: [SIMD3<Float>] = []
        var ells: [LimbEll] = []
    }

    private static func surfacePoint(_ e: WebSurface, _ u: SIMD3<Float>, off: Float) -> (p: SIMD3<Float>, n: SIMD3<Float>) {
        let un = safeNormalize(u)
        let p = e.c + SIMD3<Float>(un.x * e.k.x, un.y * e.k.y, un.z * e.k.z) * e.r
        let n = safeNormalize(SIMD3<Float>(un.x / e.k.x, un.y / e.k.y, un.z / e.k.z))
        return (p + n * off, n)
    }

    /// Flaches Band von a nach b, das auf der Oberfläche (Normale na/nb) liegt; Vorderseite zeigt nach außen.
    private static func ribbon(_ mb: inout MeshBuilder, _ a: SIMD3<Float>, _ na: SIMD3<Float>,
                               _ b: SIMD3<Float>, _ nb: SIMD3<Float>, width: Float) {
        let dir = b - a
        if simd_length_squared(dir) < 1e-10 { return }
        let n = safeNormalize(na + nb, fallback: na)
        let sideRaw = simd_cross(dir, n)
        let l = simd_length(sideRaw)
        if l < 1e-8 || !l.isFinite { return }
        let side = sideRaw / l * (width * 0.5)
        mb.addQuad(a - side, a + side, b + side, b - side, uvScale: 1)
    }

    /// Netz aus Speichen und (leicht durchhängenden) Ringen um einen Pol auf einem Ellipsoid.
    private func webPattern(_ mb: inout MeshBuilder, on e: WebSurface, pole: SIMD3<Float>, radials: Int, phase: Float,
                            theta0: Float, theta1: Float, rings: [Float], width: Float, off: Float) {
        let axisA = safeNormalize(pole)
        var refAxis = SIMD3<Float>(0, 1, 0)
        if abs(simd_dot(refAxis, axisA)) > 0.9 { refAxis = SIMD3<Float>(1, 0, 0) }
        let b1 = safeNormalize(simd_cross(axisA, refAxis))
        let b2 = simd_cross(axisA, b1)
        func dirAt(_ th: Float, _ ph: Float) -> SIMD3<Float> {
            let radial = b1 * cosf(ph) + b2 * sinf(ph)
            return axisA * cosf(th) + radial * sinf(th)
        }
        let spokes = Swift.max(3, radials)
        let steps = quality == .ultra ? 12 : 8
        for k in 0..<spokes {
            let ph = phase + Float(k) / Float(spokes) * 2 * Float.pi
            var prev = CharacterRig.surfacePoint(e, dirAt(theta0, ph), off: off)
            for i in 1...steps {
                let th = theta0 + (theta1 - theta0) * Float(i) / Float(steps)
                let cur = CharacterRig.surfacePoint(e, dirAt(th, ph), off: off)
                CharacterRig.ribbon(&mb, prev.p, prev.n, cur.p, cur.n, width: width)
                prev = cur
            }
        }
        let perSpoke = quality == .ultra ? 5 : 3
        let ringSteps = spokes * perSpoke
        for th in rings {
            var prev = CharacterRig.surfacePoint(e, dirAt(th, phase), off: off)
            for i in 1...ringSteps {
                let f = Float(i) / Float(ringSteps)
                let ph = phase + f * 2 * Float.pi
                let local = Float(i % perSpoke) / Float(perSpoke)
                let sag = 1 - 0.1 * sinf(local * Float.pi)
                let cur = CharacterRig.surfacePoint(e, dirAt(th * sag, ph), off: off)
                CharacterRig.ribbon(&mb, prev.p, prev.n, cur.p, cur.n, width: width)
                prev = cur
            }
        }
    }

    /// Abstand der Gliedmaßen-Oberfläche von der Y-Achse bei Höhe y in Richtung a (x = sin a, z = cos a).
    private static func limbRadius(_ shape: LimbShape, y: Float, a: Float) -> Float {
        var best: Float = 0
        for cp in shape.caps {
            let top = Swift.max(cp.x, cp.y)
            let bot = Swift.min(cp.x, cp.y)
            let r = cp.z
            var rr: Float = 0
            if y <= top && y >= bot {
                rr = r
            } else if y > top && y - top < r {
                let d = y - top
                rr = (r * r - d * d).squareRoot()
            } else if y < bot && bot - y < r {
                let d = bot - y
                rr = (r * r - d * d).squareRoot()
            }
            best = Swift.max(best, rr)
        }
        let sa = sinf(a)
        let ca = cosf(a)
        for el in shape.ells {
            let dy = (y - el.c.y) / el.e.y
            let kk = 1 - dy * dy
            if kk <= 0 { continue }
            let k = kk.squareRoot()
            let ex = el.e.x * k
            let ez = el.e.z * k
            let ex2 = ex * ex
            let ez2 = ez * ez
            let qa = (sa * sa) / ex2 + (ca * ca) / ez2
            let qb = -2 * ((sa * el.c.x) / ex2 + (ca * el.c.z) / ez2)
            let qc = (el.c.x * el.c.x) / ex2 + (el.c.z * el.c.z) / ez2 - 1
            let disc = qb * qb - 4 * qa * qc
            if disc < 0 || qa <= 0 { continue }
            let t = (-qb + disc.squareRoot()) / (2 * qa)
            if t > best { best = t }
        }
        return best
    }

    /// Längslinien + Ringe auf einer Gliedmaße.
    private func webOnLimb(_ mb: inout MeshBuilder, _ shape: LimbShape, yTop: Float, yBot: Float, lines: Int,
                           rings: [Float], width: Float, off: Float, phase: Float) {
        let steps = quality == .ultra ? 14 : 9
        for k in 0..<lines {
            let a = phase + Float(k) / Float(Swift.max(1, lines)) * 2 * Float.pi
            let n = SIMD3<Float>(sinf(a), 0, cosf(a))
            var prevP: SIMD3<Float>? = nil
            for i in 0...steps {
                let y = yTop + (yBot - yTop) * Float(i) / Float(steps)
                let r = CharacterRig.limbRadius(shape, y: y, a: a)
                if r <= 0.0001 {
                    prevP = nil
                    continue
                }
                let p = SIMD3<Float>(n.x * (r + off), y, n.z * (r + off))
                if let pp = prevP {
                    CharacterRig.ribbon(&mb, pp, n, p, n, width: width)
                }
                prevP = p
            }
        }
        let ringSteps = quality == .ultra ? 28 : 18
        for y in rings {
            var prev: SIMD3<Float>? = nil
            var prevN = SIMD3<Float>(0, 0, 1)
            for i in 0...ringSteps {
                let a = Float(i) / Float(ringSteps) * 2 * Float.pi
                let n = SIMD3<Float>(sinf(a), 0, cosf(a))
                let r = CharacterRig.limbRadius(shape, y: y, a: a)
                if r <= 0.0001 {
                    prev = nil
                    continue
                }
                let p = SIMD3<Float>(n.x * (r + off), y, n.z * (r + off))
                if let pp = prev {
                    CharacterRig.ribbon(&mb, pp, prevN, p, n, width: width)
                }
                prev = p
                prevN = n
            }
        }
    }

    /// Flaches Emblem (Raute mit Schwingen), auf die Oberfläche projiziert.
    private func emblem(_ mb: inout MeshBuilder, on e: WebSurface, at u: SIMD3<Float>, size: Float, off: Float) {
        let center = CharacterRig.surfacePoint(e, u, off: 0)
        let n = center.n
        var up = SIMD3<Float>(0, 1, 0) - n * simd_dot(SIMD3<Float>(0, 1, 0), n)
        up = safeNormalize(up, fallback: SIMD3<Float>(0, 1, 0))
        let right = safeNormalize(simd_cross(up, n), fallback: SIMD3<Float>(1, 0, 0))
        func project(_ x: Float, _ y: Float) -> SIMD3<Float> {
            let sx: Float = x * size
            let sy: Float = y * size
            let ox: SIMD3<Float> = right * sx
            let oy: SIMD3<Float> = up * sy
            let flat: SIMD3<Float> = center.p + ox + oy
            let rel: SIMD3<Float> = flat - e.c
            let u: SIMD3<Float> = rel / e.k
            return CharacterRig.surfacePoint(e, u, off: off).p
        }
        func tri(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>) {
            let nn = simd_cross(b - a, c - a)
            if simd_dot(nn, n) >= 0 {
                mb.addTriangle(a, b, c, uvScale: 1)
            } else {
                mb.addTriangle(a, c, b, uvScale: 1)
            }
        }
        // zentrale Klinge (lange Raute)
        let top = project(0, 0.075)
        let rgt = project(0.026, 0.004)
        let bot = project(0, -0.09)
        let lft = project(-0.026, 0.004)
        tri(top, lft, bot)
        tri(top, bot, rgt)
        // Schwingen
        for sd in [Float(1), Float(-1)] {
            let a = project(0.022 * sd, 0.022)
            let b = project(0.082 * sd, 0.05)
            let c = project(0.034 * sd, -0.018)
            tri(a, b, c)
            let d = project(0.03 * sd, -0.03)
            let f = project(0.062 * sd, -0.012)
            let g = project(0.026 * sd, -0.06)
            tri(d, f, g)
        }
    }

    // MARK: - Körper

    private func buildVisuals() {
        for (_, v) in visRoots { v.removeFromParentNode() }
        visRoots.removeAll()
        matEntries.removeAll()
        swayChains.removeAll()
        tendrils.removeAll()
        flameLights.removeAll()
        rimInstalled = false
        restPositions = layoutPositions()
        for j in Joint.allCases where j != .hips {
            joints[j]?.simdPosition = restPositions[j] ?? SIMD3<Float>(0, 0, 0)
        }
        let m = makePalette()
        buildTorso(m)
        buildHead(m)
        buildArm(m, left: true)
        buildArm(m, left: false)
        buildLeg(m, left: true)
        buildLeg(m, left: false)
        buildAccessories(m)
        if matState == .frozen || matState == .shadow {
            if matAmount > 0 { installRimShader() }
        }
        refreshMaterials()
    }

    private func buildTorso(_ m: Palette) {
        let d = dims
        let s = d.s
        let hp = container(.hips)
        let sp = container(.spine)
        let ch = container(.chest)
        let coat = look.accessories.contains(.labCoat)

        // Becken + Gesäß
        ellipsoid(hp, pv(0, -0.02, -0.005), 0.13 * s, SIMD3<Float>(1.22 * d.hw, 0.72, 0.86 * d.td), m.suit)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(hp, pv(0.06 * sd * d.hw, -0.06, -0.045 * d.td), 0.085 * s, SIMD3<Float>(1, 1.05, 0.9 * d.td), m.suit)
        }
        // Gürtel mit Schnalle
        if !coat {
            cylinder(hp, pv(0, 0.035, 0), r: 1, h: 0.045 * s, m.dark,
                     scale: SIMD3<Float>(0.137 * s * d.hw, 1, 0.098 * s * d.td))
            box(hp, pv(0, 0.035, 0.098 * d.td + 0.003), SIMD3<Float>(0.05, 0.034, 0.012) * s, chamfer: 0.004 * s,
                m.superSuit ? m.glow : m.metal, shadow: false)
        }
        // Bauch
        let abW = 0.95 + (d.ws - 1) * 0.8
        ellipsoid(sp, pv(0, 0.04, 0.008), 0.12 * s, SIMD3<Float>(abW, 1.2, 0.8 * d.td * d.belly), m.suit)
        // Brustkorb, Brustmuskeln, Rücken (Seitenpaneele), Nacken
        let chestS = chestSurface
        ellipsoid(ch, chestS.c, chestS.r, chestS.k, m.suit)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(ch, pv(0.068 * sd * d.ws, 0.11, 0.055 * d.td), 0.08 * s, SIMD3<Float>(1.05 * d.ws, 0.72, 0.55 * d.td), m.suit)
        }
        if m.superSuit {
            let latsS = latsSurface
            ellipsoid(ch, latsS.c, latsS.r, latsS.k, m.panel)
        }
        let trapR = 0.062 * s * (1 + (d.ts - 1) * 0.5)
        capsule(ch, pv(-0.11 * d.ws, 0.17, -0.035 * d.td), pv(0.11 * d.ws, 0.17, -0.035 * d.td), trapR, m.suit)
    }

    private func buildHead(_ m: Palette) {
        let d = dims
        let s = d.s
        let hj = container(.head)
        let nj = container(.neck)
        let hasHood = look.accessories.contains(.hood)

        let neckR = 0.05 * s * (1 + (d.ts - 1) * 0.75)
        capsule(nj, pv(0, -0.02, 0), pv(0, 0.1, 0.012), neckR, look.hasMask ? m.suit : m.skin)

        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let hk = s * d.head
        ellipsoid(hj, c, r, hs, m.headMat)
        // Kiefer / Kinn
        ellipsoid(hj, SIMD3<Float>(0, 0.05, 0.03) * hk, 0.068 * hk, SIMD3<Float>(1.0 + (d.ws - 1) * 0.5, 0.78, 0.95), m.headMat)

        let surf = WebSurface(c: c, r: r, k: hs)
        switch look.eyeStyle {
        case .lenses:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.36 * sd, 0.13, 0.92), off: 0)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: 0.42 * sd, axis: SIMD3<Float>(0, 0, 1))
                let rimNode = ellipsoid(hj, sp.p - sp.n * (0.002 * s), 1, SIMD3<Float>(0.035, 0.023, 0.008) * hk, m.dark, shadow: false, detail: 0.6)
                rimNode.simdOrientation = q
                let lensNode = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.029, 0.0185, 0.0078) * hk, m.lens, shadow: false, detail: 0.6)
                lensNode.simdOrientation = q
                // Tropfenform: zweiter Lappen innen-unten
                let off = q.act(SIMD3<Float>(-0.013 * sd, -0.007, 0) * hk)
                let rim2 = ellipsoid(hj, sp.p + off - sp.n * (0.002 * s), 1, SIMD3<Float>(0.024, 0.018, 0.0082) * hk, m.dark, shadow: false, detail: 0.5)
                rim2.simdOrientation = q
                let lobe = ellipsoid(hj, sp.p + off, 1, SIMD3<Float>(0.019, 0.0135, 0.0079) * hk, m.lens, shadow: false, detail: 0.5)
                lobe.simdOrientation = q
            }
        case .glow:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.34 * sd, 0.11, 0.93), off: 0)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: 0.25 * sd, axis: SIMD3<Float>(0, 0, 1))
                let socket = ellipsoid(hj, sp.p - sp.n * (0.003 * s), 1, SIMD3<Float>(0.022, 0.012, 0.007) * hk, m.dark, shadow: false, detail: 0.5)
                socket.simdOrientation = q
                let eye = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.014, 0.0075, 0.006) * hk, m.glow, shadow: false, detail: 0.5)
                eye.simdOrientation = q
            }
        case .visor:
            ellipsoid(hj, c + SIMD3<Float>(0, 0.012 * hk, 0.27 * r), 1,
                      SIMD3<Float>(0.95 * r * hs.x, 0.16 * r, 0.81 * r), m.glow, shadow: false)
        case .human:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.33 * sd, 0.1, 0.94), off: -0.002 * s)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n)
                let white = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.0135, 0.0085, 0.006) * hk, m.eyeWhite, shadow: false, detail: 0.5)
                white.simdOrientation = q
                ellipsoid(hj, sp.p + sp.n * (0.0045 * s), 0.0058 * hk, SIMD3<Float>(1, 1, 0.6), m.dark, shadow: false, detail: 0.4)
            }
        }

        // Gesicht (ohne Maske)
        if !look.hasMask {
            let browMat = look.hairColor != nil ? m.hair : m.dark
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.33 * sd, 0.27, 0.9), off: 0.002 * s)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: -0.12 * sd, axis: SIMD3<Float>(0, 0, 1))
                box(hj, sp.p, SIMD3<Float>(0.032, 0.006, 0.008) * hk, chamfer: 0.002 * s, browMat, orient: q, shadow: false)
                // Ohren
                ellipsoid(hj, c + SIMD3<Float>(sd * (r * hs.x - 0.004 * s), -0.005 * s, -0.008 * s), 1,
                          SIMD3<Float>(0.01, 0.027, 0.018) * hk, m.skin, detail: 0.5)
            }
            let nose = CharacterRig.surfacePoint(surf, SIMD3<Float>(0, -0.05, 1), off: 0)
            ellipsoid(hj, nose.p + nose.n * (0.006 * s), 1, SIMD3<Float>(0.011, 0.021, 0.015) * hk, m.skin, shadow: false, detail: 0.5)
            let mouth = CharacterRig.surfacePoint(surf, SIMD3<Float>(0, -0.42, 0.9), off: 0.001 * s)
            let mq = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: mouth.n)
            box(hj, mouth.p, SIMD3<Float>(0.032, 0.0045, 0.008) * hk, chamfer: 0.002 * s, m.lips, orient: mq, shadow: false)
            if look.hairColor != nil && !hasHood {
                ellipsoid(hj, c + SIMD3<Float>(0, 0.25 * r, -0.12 * r), r,
                          SIMD3<Float>(hs.x * 1.07, hs.y * 0.84, hs.z * 1.06), m.hair)
            }
        }
    }

    // Gliedmaßen-Formen (gemeinsam für Geometrie und Netzlinien)

    private func upperArmShape(_ sd: Float, _ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(-0.02 * s, -0.27 * s, 0.048 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0.012 * sd * s, -0.03 * s, 0), e: SIMD3<Float>(0.066, 0.0739, 0.066) * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.12 * s, 0.016 * k), e: SIMD3<Float>(0.044, 0.088, 0.044) * k))
        return sh
    }

    private func forearmShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.13 * s, 0.043 * k))
        sh.caps.append(SIMD3<Float>(-0.1 * s, -0.248 * s, 0.034 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.065 * s, 0.004 * s), e: SIMD3<Float>(0.047, 0.0893, 0.0447) * k))
        return sh
    }

    private func thighShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.39 * s, 0.072 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.14 * s, 0.02 * k), e: SIMD3<Float>(0.0646, 0.1428, 0.0612) * k))
        return sh
    }

    private func shinShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.40 * s, 0.05 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.12 * s, -0.022 * k), e: SIMD3<Float>(0.055, 0.1155, 0.0578) * k))
        return sh
    }

    private func armThickness(left: Bool) -> Float {
        let cyber = !left && look.accessories.contains(.cyberArm)
        return dims.s * dims.ts * (cyber ? 1.08 : 1)
    }

    private func buildArm(_ m: Palette, left: Bool) {
        let s = dims.s
        let sd: Float = left ? 1 : -1
        let cyber = !left && look.accessories.contains(.cyberArm)
        let coat = look.accessories.contains(.labCoat)
        let ua = container(left ? .lUpperArm : .rUpperArm)
        let fa = container(left ? .lForearm : .rForearm)
        let hd = container(left ? .lHand : .rHand)
        let armMat = cyber ? m.cyber : m.suit
        let shoulderMat = cyber ? m.cyber : (m.superSuit ? m.panel : m.suit)
        let k = armThickness(left: left)

        let uaShape = upperArmShape(sd, k)
        for cp in uaShape.caps {
            capsule(ua, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, armMat)
        }
        if uaShape.ells.count >= 2 {
            ellipsoid(ua, uaShape.ells[0].c, 1, uaShape.ells[0].e, shoulderMat)
            ellipsoid(ua, uaShape.ells[1].c, 1, uaShape.ells[1].e, armMat)
        }
        let faShape = forearmShape(k)
        for cp in faShape.caps {
            capsule(fa, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, armMat)
        }
        for el in faShape.ells {
            ellipsoid(fa, el.c, 1, el.e, armMat)
        }
        if m.superSuit && !cyber && !coat {
            capsule(fa, pv(0, -0.125, 0), pv(0, -0.252, 0), 0.034 * k + 0.0045 * s, m.glove)
        }
        let fistMat = cyber ? m.cyber : m.glove
        buildFist(hd, sd: sd, mat: fistMat, k: s * (1 + (dims.ts - 1) * 0.6))
    }

    private func buildFist(_ hd: SCNNode, sd: Float, mat: SCNMaterial, k: Float) {
        // Faust: schmal in X, Daumen vorne (+Z), Knöchel unten
        box(hd, SIMD3<Float>(0, -0.05, 0.006) * k, SIMD3<Float>(0.05, 0.09, 0.088) * k, chamfer: 0.018 * k, mat)
        box(hd, SIMD3<Float>(-0.012 * sd, -0.088, 0.008) * k, SIMD3<Float>(0.044, 0.042, 0.084) * k, chamfer: 0.016 * k, mat)
        capsule(hd, SIMD3<Float>(-0.006 * sd, -0.028, 0.044) * k, SIMD3<Float>(-0.02 * sd, -0.07, 0.05) * k, 0.012 * k, mat,
                shadow: false, detail: 0.6)
    }

    private func buildLeg(_ m: Palette, left: Bool) {
        let s = dims.s
        let k = s * dims.ts
        let th = container(left ? .lThigh : .rThigh)
        let sh = container(left ? .lShin : .rShin)
        let ft = container(left ? .lFoot : .rFoot)

        let tShape = thighShape(k)
        for cp in tShape.caps {
            capsule(th, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, m.suit)
        }
        for el in tShape.ells {
            ellipsoid(th, el.c, 1, el.e, m.suit)
        }
        let sShape = shinShape(k)
        for cp in sShape.caps {
            capsule(sh, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, m.suit)
        }
        for el in sShape.ells {
            ellipsoid(sh, el.c, 1, el.e, m.suit)
        }
        if m.superSuit {
            // Knieschoner
            ellipsoid(sh, SIMD3<Float>(0, -0.005 * s, 0.042 * k), 0.034 * k, SIMD3<Float>(1, 1.05, 0.7), m.panel, detail: 0.6)
        }
        // Stiefelschaft
        capsule(sh, pv(0, -0.21, 0), pv(0, -0.405, 0), 0.056 * k, m.boot)
        // Fuß + Sohle
        let fk = s * (1 + (dims.ts - 1) * 0.5)
        box(ft, pv(0, -0.041, 0.05), SIMD3<Float>(0.095 * fk, 0.08 * s, 0.25 * s), chamfer: 0.03 * s, m.boot)
        box(ft, pv(0, -0.072, 0.05), SIMD3<Float>(0.1 * fk, 0.018 * s, 0.258 * s), chamfer: 0.006 * s, m.dark, shadow: false)
    }

    // MARK: - Accessoires

    private func buildAccessories(_ m: Palette) {
        var done = Set<Accessory>()
        for a in look.accessories {
            if done.contains(a) { continue }
            done.insert(a)
            switch a {
            case .webLines: buildWebLines(m)
            case .chainBlades: buildChainBlades(m)
            case .katana: buildKatana(m)
            case .scarf: buildScarf(m)
            case .shoulderPads: buildShoulderPads(m)
            case .cyberArm: buildCyberDetails(m)
            case .horns: buildHorns(m)
            case .crown: buildCrown(m)
            case .cape: buildCape(m)
            case .flameAura: buildFlameAura(m)
            case .tendrils: buildTendrils(m)
            case .spikes: buildSpikes(m)
            case .labCoat: buildLabCoat(m)
            case .hood: buildHood(m)
            }
        }
    }

    private func addMeshNode(_ mb: MeshBuilder, to j: Joint, material: SCNMaterial) {
        if mb.isEmpty { return }
        let n = SCNNode(geometry: mb.build(material: material))
        n.name = "rig.web"
        n.castsShadow = false
        container(j).addChildNode(n)
    }

    /// Dunkel-silbern leuchtende Netzlinien auf Maske, Brust, Rücken, Bauch und Gliedmaßen + Brustemblem.
    private func buildWebLines(_ m: Palette) {
        let d = dims
        let s = d.s
        let width = 0.0034 * s
        let off = 0.0022 * s
        let ultra = quality == .ultra
        let lines = ultra ? 6 : 4

        // Brust vorne + Emblem
        var chestMB = MeshBuilder()
        let chestSurf = chestSurface
        webPattern(&chestMB, on: chestSurf, pole: SIMD3<Float>(0, 0.25, 1), radials: ultra ? 10 : 8, phase: Float.pi / 8,
                   theta0: 0.16, theta1: 1.35, rings: [0.34, 0.66, 0.98, 1.28], width: width, off: off)
        // Rücken (auf den Seitenpaneelen, falls vorhanden)
        let backSurf: WebSurface
        if m.superSuit {
            backSurf = latsSurface
        } else {
            backSurf = chestSurf
        }
        webPattern(&chestMB, on: backSurf, pole: SIMD3<Float>(0, 0.25, -1), radials: 8, phase: Float.pi / 8,
                   theta0: 0.12, theta1: 1.2, rings: [0.42, 0.8, 1.12], width: width, off: off)
        addMeshNode(chestMB, to: .chest, material: m.web)

        var emblemMB = MeshBuilder()
        emblem(&emblemMB, on: chestSurf, at: SIMD3<Float>(0, 0.25, 1), size: s * d.ws, off: 0.0035 * s)
        emblem(&emblemMB, on: backSurf, at: SIMD3<Float>(0, 0.3, -1), size: s * d.ws * 0.6, off: 0.0035 * s)
        addMeshNode(emblemMB, to: .chest, material: m.glow)

        // Bauch: Ringe + Meridiane
        var absMB = MeshBuilder()
        let abW = 0.95 + (d.ws - 1) * 0.8
        let absSurf = WebSurface(c: pv(0, 0.04, 0.008), r: 0.12 * s, k: SIMD3<Float>(abW, 1.2, 0.8 * d.td * d.belly))
        webPattern(&absMB, on: absSurf, pole: SIMD3<Float>(0, 1, 0), radials: 8, phase: Float.pi / 8,
                   theta0: 0.95, theta1: 2.2, rings: [1.3, 1.62, 1.95], width: width, off: off)
        addMeshNode(absMB, to: .spine, material: m.web)

        // Maske
        if look.hasMask {
            var headMB = MeshBuilder()
            let headSurf = WebSurface(c: headCenterLocal, r: headRadius, k: headScale)
            webPattern(&headMB, on: headSurf, pole: SIMD3<Float>(0, 0.05, 1), radials: ultra ? 12 : 10, phase: Float.pi / 12,
                       theta0: 0.12, theta1: 2.5, rings: [0.42, 0.8, 1.2, 1.62, 2.05], width: width * 0.85, off: off * 0.8)
            addMeshNode(headMB, to: .head, material: m.web)
        }

        // Gliedmaßen
        let ringCountUA: [Float] = ultra ? [-0.22, -0.26] : [-0.24]
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            if !left && look.accessories.contains(.cyberArm) { continue }
            let k = armThickness(left: left)
            var uaMB = MeshBuilder()
            webOnLimb(&uaMB, upperArmShape(sd, k), yTop: -0.01 * s, yBot: -0.285 * s, lines: lines,
                      rings: ringCountUA.map { $0 * s }, width: width, off: off, phase: 0.3)
            addMeshNode(uaMB, to: left ? .lUpperArm : .rUpperArm, material: m.web)
            var faMB = MeshBuilder()
            webOnLimb(&faMB, forearmShape(k), yTop: -0.005 * s, yBot: -0.2 * s, lines: lines,
                      rings: [-0.035 * s, -0.1 * s], width: width, off: off, phase: 0.3)
            addMeshNode(faMB, to: left ? .lForearm : .rForearm, material: m.web)
        }
        let legK = s * d.ts
        for left in [true, false] {
            var thMB = MeshBuilder()
            webOnLimb(&thMB, thighShape(legK), yTop: -0.02 * s, yBot: -0.38 * s, lines: lines + 2,
                      rings: ultra ? [-0.08 * s, -0.2 * s, -0.32 * s] : [-0.12 * s, -0.3 * s],
                      width: width, off: off, phase: 0.2)
            addMeshNode(thMB, to: left ? .lThigh : .rThigh, material: m.web)
            var shMB = MeshBuilder()
            webOnLimb(&shMB, shinShape(legK), yTop: -0.03 * s, yBot: -0.2 * s, lines: lines + 2,
                      rings: [-0.08 * s, -0.17 * s], width: width, off: off, phase: 0.2)
            addMeshNode(shMB, to: left ? .lShin : .rShin, material: m.web)
        }
    }

    /// Kettenklingen: Klinge an der Unterarm-Außenseite, gewickelte Kette und eine schwingende Kettenschleppe.
    private func buildChainBlades(_ m: Palette) {
        let s = dims.s
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let fa = container(left ? .lForearm : .rForearm)
            let k = armThickness(left: left)
            let bx = sd * (0.043 * k + 0.012 * s)
            // Klinge (Spitze zeigt Richtung Ellbogen und darüber hinaus)
            box(fa, SIMD3<Float>(bx, -0.08 * s, -0.008 * s), SIMD3<Float>(0.006 * s, 0.3 * s, 0.038 * s), chamfer: 0.002 * s, m.blade)
            let tip = SCNPyramid(width: CGFloat(0.006 * s), height: CGFloat(0.075 * s), length: CGFloat(0.038 * s))
            tip.materials = [m.blade]
            let tipNode = SCNNode(geometry: tip)
            tipNode.simdPosition = SIMD3<Float>(bx, 0.07 * s, -0.008 * s)
            tipNode.castsShadow = false
            fa.addChildNode(tipNode)
            // leuchtende Schneide
            box(fa, SIMD3<Float>(bx, -0.07 * s, -0.008 * s - 0.019 * s), SIMD3<Float>(0.0068 * s, 0.3 * s, 0.003 * s),
                chamfer: 0, m.glow, shadow: false)
            // gewickelte Kette
            let links = quality == .performance ? 6 : 10
            for i in 0..<links {
                let a = Float(i) * (2 * Float.pi / 4.5)
                let y = -0.05 * s - Float(i) * 0.017 * s
                let rad = (y > -0.13 * s ? 0.045 * k : 0.037 * k) + 0.004 * s
                let n = SIMD3<Float>(sinf(a), 0, cosf(a))
                let pos = SIMD3<Float>(n.x * rad, y, n.z * rad)
                let q: simd_quatf
                if i % 2 == 0 {
                    q = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: n)
                } else {
                    let tangent = SIMD3<Float>(cosf(a), -0.25, -sinf(a))
                    q = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: simd_cross(n, tangent))
                }
                torus(fa, pos, ring: 0.0105 * s, pipe: 0.0028 * s, m.metal, orient: q)
            }
            // schwingende Kettenschleppe am Handgelenk
            let anchor = SCNNode()
            anchor.simdPosition = SIMD3<Float>(sd * 0.04 * k, -0.235 * s, -0.01 * s)
            fa.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            let count = quality == .performance ? 4 : 6
            let segLen = 0.03 * s
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let q = (i % 2 == 0) ? simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(1, 0, 0))
                                     : simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(0, 0, 1))
                torus(seg, SIMD3<Float>(0, -segLen * 0.5, 0), ring: 0.011 * s, pipe: 0.0028 * s, m.metal,
                      orient: q, scale: SIMD3<Float>(1, 1, 1.35))
                segs.append(seg)
                parent = seg
            }
            cone(parent, base: SIMD3<Float>(0, -segLen, 0), dir: SIMD3<Float>(0, -1, 0), r0: 0.012 * s, r1: 0, h: 0.05 * s, m.blade, shadow: false)
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(left ? .lForearm : .rForearm),
                                        side: 0, minOffset: 0, stiffness: 14, drag: 0.25, flutter: 0.12, phase: sd * 2.1))
        }
    }

    /// Katana schräg auf dem Rücken, Griff über der rechten Schulter.
    private func buildKatana(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let holder = SCNNode()
        holder.simdPosition = pv(0, 0.05, -(0.125 * d.td + 0.032))
        holder.simdOrientation = simd_quatf(angle: 0.45, axis: SIMD3<Float>(0, 0, 1))
        ch.addChildNode(holder)
        let sheath = cylinder(holder, pv(0, -0.04, 0), r: 0.02 * s, h: 0.68 * s, m.dark, scale: SIMD3<Float>(1, 1, 0.62))
        sheath.name = "rig.katana"
        cylinder(holder, pv(0, -0.38, 0), r: 0.021 * s, h: 0.03 * s, m.gold, scale: SIMD3<Float>(1, 1, 0.62))
        cylinder(holder, pv(0, 0.305, 0), r: 0.042 * s, h: 0.01 * s, m.gold)
        cylinder(holder, pv(0, 0.42, 0), r: 0.016 * s, h: 0.22 * s, m.cloth)
        if quality != .performance {
            for i in 0..<6 {
                let y = 0.33 + Float(i) * 0.034
                torus(holder, pv(0, y, 0), ring: 0.0165 * s, pipe: 0.0035 * s, m.panel,
                      orient: simd_quatf(angle: 0.5, axis: SIMD3<Float>(1, 0, 0)))
            }
        }
        cylinder(holder, pv(0, 0.535, 0), r: 0.018 * s, h: 0.014 * s, m.gold)
    }

    /// Schal um den Hals mit zwei flatternden Enden.
    private func buildScarf(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let nt = 1 + (d.ts - 1) * 0.75
        torus(ch, pv(0, 0.215, -0.005), ring: 0.064 * s * nt, pipe: 0.024 * s, m.cloth,
              scale: SIMD3<Float>(1.05, 0.85, 1.0), shadow: true)
        let count = quality == .ultra ? 7 : (quality == .balanced ? 5 : 4)
        let segLen = 0.52 * s / Float(count)
        for sd in [Float(1), Float(-1)] {
            let anchor = SCNNode()
            anchor.simdPosition = pv(0.032 * sd, 0.2, -0.075 * nt)
            ch.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let w = (0.075 - 0.012 * Float(i) / Float(count)) * s
                box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.08, 0.012 * s), chamfer: 0.004 * s, m.cloth)
                segs.append(seg)
                parent = seg
            }
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.chest), side: -1, minOffset: 0.08,
                                        stiffness: 7, drag: 0.8, flutter: 0.6, phase: sd * 1.7))
        }
    }

    /// Mehrlagige Schulterpanzer.
    private func buildShoulderPads(_ m: Palette) {
        let s = dims.s
        let armor = registerMaterial(look.secondaryColor, rough: 0.3, metal: 0.85)
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let ua = container(left ? .lUpperArm : .rUpperArm)
            let k = s * dims.ts
            let q1 = simd_quatf(angle: -0.35 * sd, axis: SIMD3<Float>(0, 0, 1))
            let p1 = ellipsoid(ua, SIMD3<Float>(0.025 * sd, 0.008, 0) * k, 0.095 * k, SIMD3<Float>(1.0, 0.55, 1.08), armor)
            p1.simdOrientation = q1
            torus(ua, SIMD3<Float>(0.025 * sd, 0.0, 0) * k, ring: 0.093 * k, pipe: 0.006 * k, m.gold,
                  orient: q1, scale: SIMD3<Float>(1, 1, 1.08), shadow: false)
            let q2 = simd_quatf(angle: -0.6 * sd, axis: SIMD3<Float>(0, 0, 1))
            let p2 = ellipsoid(ua, SIMD3<Float>(0.052 * sd, -0.045, 0) * k, 0.082 * k, SIMD3<Float>(1.0, 0.5, 1.02), armor)
            p2.simdOrientation = q2
            // Nieten
            for i in 0..<3 {
                let a = (Float(i) - 1) * 0.6
                let pos = SIMD3<Float>(0.03 * sd + sinf(a) * 0.0, 0.055, cosf(a) * 0.07) * k
                ellipsoid(ua, pos, 0.008 * k, SIMD3<Float>(1, 1, 1), m.gold, shadow: false, detail: 0.3)
            }
        }
    }

    /// Cyber-Arm (rechts): leuchtende Nähte, Kolben, Gelenkring.
    private func buildCyberDetails(_ m: Palette) {
        let s = dims.s
        let k = armThickness(left: false)
        let ua = container(.rUpperArm)
        let fa = container(.rForearm)
        let hd = container(.rHand)
        let pipe = 0.0035 * s
        torus(ua, pv(0, -0.2, 0), ring: 0.051 * k, pipe: pipe, m.glow)
        torus(ua, pv(0, -0.25, 0), ring: 0.05 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.015, 0), ring: 0.046 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.15, 0), ring: 0.04 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.245, 0), ring: 0.037 * k, pipe: pipe, m.glow)
        for sd in [Float(1), Float(-1)] {
            capsule(ua, SIMD3<Float>(sd * 0.049 * k, -0.08 * s, 0), SIMD3<Float>(sd * 0.049 * k, -0.23 * s, 0), 0.0025 * s,
                    m.glow, shadow: false, detail: 0.4)
            capsule(fa, SIMD3<Float>(sd * 0.041 * k, -0.03 * s, 0), SIMD3<Float>(sd * 0.036 * k, -0.135 * s, 0), 0.0025 * s,
                    m.glow, shadow: false, detail: 0.4)
        }
        // Kolben an der Unterarm-Rückseite
        capsule(fa, SIMD3<Float>(0, -0.03 * s, -0.048 * k), SIMD3<Float>(0, -0.2 * s, -0.04 * k), 0.007 * s, m.metal, detail: 0.5)
        capsule(fa, SIMD3<Float>(0.012 * s, -0.04 * s, -0.046 * k), SIMD3<Float>(0.012 * s, -0.12 * s, -0.042 * k), 0.005 * s, m.metal, detail: 0.5)
        // Knöchel-Leuchtpunkte
        let fk = s * (1 + (dims.ts - 1) * 0.6)
        for i in 0..<4 {
            let z = (-0.025 + Float(i) * 0.017) * fk
            ellipsoid(hd, SIMD3<Float>(0.006 * fk, -0.108 * fk, z + 0.008 * fk), 0.0055 * fk, SIMD3<Float>(1, 1, 1), m.glow,
                      shadow: false, detail: 0.3)
        }
        // Gelenkring am Rumpf
        let ch = container(.chest)
        let shoulder = restPositions[.rUpperArm] ?? pv(-0.205, 0.195, -0.01)
        torus(ch, shoulder, ring: 0.058 * k, pipe: 0.008 * s, m.metal,
              orient: simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(0, 0, 1)), shadow: true)
    }

    /// Gebogene Hörner aus Kegelsegmenten.
    private func buildHorns(_ m: Palette) {
        let s = dims.s
        let hk = s * dims.head
        let hj = container(.head)
        let surf = WebSurface(c: headCenterLocal, r: headRadius, k: headScale)
        for sd in [Float(1), Float(-1)] {
            let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.42 * sd, 0.62, 0.35), off: -0.004 * s)
            let root = SCNNode()
            root.simdPosition = sp.p
            root.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0),
                                                         to: safeNormalize(sp.n + SIMD3<Float>(0.35 * sd, 0.6, -0.2)))
            hj.addChildNode(root)
            var parent = root
            var radius = 0.03 * hk
            for i in 0..<3 {
                let h = (0.075 - 0.01 * Float(i)) * hk
                let r1 = radius * 0.64
                cone(parent, base: SIMD3<Float>(0, 0, 0), dir: SIMD3<Float>(0, 1, 0), r0: radius, r1: r1, h: h, m.horn)
                let next = SCNNode()
                next.simdPosition = SIMD3<Float>(0, h * 0.96, 0)
                next.simdOrientation = simd_quatf(angle: -0.5, axis: SIMD3<Float>(1, 0, 0)) * simd_quatf(angle: 0.12 * sd, axis: SIMD3<Float>(0, 0, 1))
                parent.addChildNode(next)
                parent = next
                radius = r1
            }
            cone(parent, base: SIMD3<Float>(0, 0, 0), dir: SIMD3<Float>(0, 1, 0), r0: radius, r1: 0.0005, h: 0.05 * hk, m.horn, shadow: false)
        }
    }

    /// Krone: Reif mit Zacken und leuchtenden Steinen.
    private func buildCrown(_ m: Palette) {
        let s = dims.s
        let hj = container(.head)
        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let lift: Float = 0.42
        let f = (1 - (lift / hs.y) * (lift / hs.y)).squareRoot()
        let semiX = r * hs.x * f * 1.01
        let semiZ = r * hs.z * f * 1.01
        let y = c.y + lift * r
        let band = SCNTube(innerRadius: CGFloat(semiX * 0.98), outerRadius: CGFloat(semiX * 0.98 + 0.008 * s), height: CGFloat(0.034 * s))
        band.radialSegmentCount = segRadial
        band.materials = [m.gold]
        let bandNode = SCNNode(geometry: band)
        bandNode.simdPosition = SIMD3<Float>(c.x, y, c.z)
        bandNode.simdScale = SIMD3<Float>(1, 1, semiZ / Swift.max(0.001, semiX))
        hj.addChildNode(bandNode)
        let spikes = 9
        for i in 0..<spikes {
            let a = (Float(i) / Float(spikes - 1) - 0.5) * 2 * 2.6
            let px = sinf(a) * (semiX + 0.004 * s)
            let pz = cosf(a) * (semiZ + 0.004 * s)
            let center = i == spikes / 2
            let h: Float = (center ? 0.075 : (0.04 + 0.012 * cosf(a))) * s
            let base = SIMD3<Float>(c.x + px, y + 0.012 * s, c.z + pz)
            let outward = safeNormalize(SIMD3<Float>(px, 0, pz))
            cone(hj, base: base, dir: safeNormalize(SIMD3<Float>(0, 1, 0) + outward * 0.18), r0: 0.011 * s, r1: 0.0008 * s, h: h, m.gold, shadow: false)
            if i % 2 == 0 {
                ellipsoid(hj, SIMD3<Float>(c.x + sinf(a) * (semiX + 0.009 * s), y, c.z + cosf(a) * (semiZ + 0.009 * s)),
                          (center ? 0.011 : 0.007) * s, SIMD3<Float>(1, 1, 0.7), m.glow, shadow: false, detail: 0.4)
            }
        }
    }

    /// Umhang aus Segmenten, die nachschwingen.
    private func buildCape(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        // Schulterspange
        capsule(ch, pv(-0.15 * d.ws, 0.172, -0.11 * d.td), pv(0.15 * d.ws, 0.172, -0.11 * d.td), 0.02 * s, m.gold, detail: 0.6)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(ch, pv(0.16 * sd * d.ws, 0.172, -0.1 * d.td), 0.03 * s, SIMD3<Float>(1, 1, 0.6), m.gold, detail: 0.5)
        }
        let anchor = SCNNode()
        anchor.simdPosition = pv(0, 0.168, -(0.135 * d.td + 0.006))
        ch.addChildNode(anchor)
        let count = quality == .ultra ? 9 : (quality == .balanced ? 6 : 4)
        let total = 1.12 * s
        let segLen = total / Float(count)
        var segs: [SCNNode] = []
        var parent = anchor
        for i in 0..<count {
            let seg = SCNNode()
            seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
            parent.addChildNode(seg)
            let t = count > 1 ? Float(i) / Float(count - 1) : 0
            let w = (0.4 + 0.22 * t) * s * d.ws
            box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.06, 0.012 * s), chamfer: 0.004 * s, m.cloth)
            segs.append(seg)
            parent = seg
        }
        swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.chest), side: -1, minOffset: 0.1,
                                    stiffness: 9, drag: 0.55, flutter: 0.35, phase: 0.4))
    }

    private func makeFlameSystem(rate: Float, size: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.loops = true
        p.birthRate = CGFloat(rate * particleScale)
        p.particleLifeSpan = 0.5
        p.particleLifeSpanVariation = 0.2
        p.particleVelocity = 0.35
        p.particleVelocityVariation = 0.25
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 25
        p.acceleration = SCNVector3(x: 0, y: 1.6, z: 0)
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleAngularVelocityVariation = 90
        p.particleImage = ProceduralTextures.radialGlow(color: .white)
        p.blendMode = .additive
        p.emitterShape = SCNSphere(radius: CGFloat(size * 0.45))
        p.birthLocation = .volume
        p.particleIntensity = 1.8
        let sizeAnim = CAKeyframeAnimation()
        sizeAnim.values = [NSNumber(value: size * 0.55), NSNumber(value: size), NSNumber(value: size * 0.25)]
        sizeAnim.keyTimes = [NSNumber(value: Float(0)), NSNumber(value: Float(0.35)), NSNumber(value: Float(1))]
        sizeAnim.duration = 1
        let colorAnim = CAKeyframeAnimation()
        colorAnim.values = [UIColor(red: 1.0, green: 0.92, blue: 0.6, alpha: 1),
                            UIColor(red: 1.0, green: 0.5, blue: 0.1, alpha: 0.9),
                            UIColor(red: 0.75, green: 0.12, blue: 0.02, alpha: 0.5),
                            UIColor(red: 0.2, green: 0.02, blue: 0.0, alpha: 0)]
        colorAnim.keyTimes = [NSNumber(value: Float(0)), NSNumber(value: Float(0.25)), NSNumber(value: Float(0.6)), NSNumber(value: Float(1))]
        colorAnim.duration = 1
        p.particleColor = .white
        p.propertyControllers = [.size: SCNParticlePropertyController(animation: sizeAnim),
                                 .color: SCNParticlePropertyController(animation: colorAnim)]
        return p
    }

    /// Flammen an Händen und Schultern (eigene, dauerhafte Partikelsysteme) + flackerndes Licht.
    private func buildFlameAura(_ m: Palette) {
        let d = dims
        let s = d.s
        for j in [Joint.lHand, Joint.rHand] {
            let emitter = SCNNode()
            emitter.simdPosition = pv(0, -0.065, 0)
            container(j).addChildNode(emitter)
            emitter.addParticleSystem(makeFlameSystem(rate: 70, size: 0.11 * s))
        }
        let ch = container(.chest)
        for sd in [Float(1), Float(-1)] {
            let emitter = SCNNode()
            emitter.simdPosition = pv(0.19 * sd * d.ws, 0.2, -0.03)
            ch.addChildNode(emitter)
            emitter.addParticleSystem(makeFlameSystem(rate: 34, size: 0.13 * s))
        }
        if quality != .performance {
            let light = SCNLight()
            light.type = .omni
            light.color = UIColor(red: 1.0, green: 0.48, blue: 0.16, alpha: 1)
            light.intensity = 300
            light.attenuationStartDistance = 0.1
            light.attenuationEndDistance = CGFloat(3.2 * s)
            light.castsShadow = false
            let ln = SCNNode()
            ln.light = light
            ln.simdPosition = pv(0, 0.12, 0.22)
            ch.addChildNode(ln)
            flameLights.append(light)
            flameLightBase = 300
        }
    }

    /// Schwarze, sich windende Ranken aus dem Rücken.
    private func buildTendrils(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let tendrilMat = registerMaterial(UIColor(red: 0.018, green: 0.016, blue: 0.026, alpha: 1), rough: 0.18, metal: 0.3)
        let anchors: [(SIMD3<Float>, SIMD3<Float>)] = [
            (SIMD3<Float>(0.09, 0.14, -0.11), SIMD3<Float>(0.6, 0.55, -0.6)),
            (SIMD3<Float>(-0.09, 0.14, -0.11), SIMD3<Float>(-0.6, 0.55, -0.6)),
            (SIMD3<Float>(0.07, 0.02, -0.11), SIMD3<Float>(0.8, -0.1, -0.6)),
            (SIMD3<Float>(-0.07, 0.02, -0.11), SIMD3<Float>(-0.8, -0.1, -0.6)),
            (SIMD3<Float>(0.03, 0.2, -0.1), SIMD3<Float>(0.25, 0.9, -0.45)),
            (SIMD3<Float>(-0.03, 0.2, -0.1), SIMD3<Float>(-0.25, 0.9, -0.45))
        ]
        let count = quality == .ultra ? 6 : (quality == .balanced ? 4 : 3)
        let segCount = quality == .ultra ? 8 : (quality == .balanced ? 6 : 5)
        let segLen = 0.11 * s
        for i in 0..<Swift.min(count, anchors.count) {
            let a = anchors[i]
            let root = SCNNode()
            root.simdPosition = SIMD3<Float>(a.0.x * d.ws, a.0.y, a.0.z * d.td) * s
            root.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: a.1)
            ch.addChildNode(root)
            var parent = root
            var segs: [SCNNode] = []
            var base: [SIMD3<Float>] = []
            for kIdx in 0..<segCount {
                let seg = SCNNode()
                seg.simdPosition = kIdx == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, segLen, 0)
                parent.addChildNode(seg)
                let t = Float(kIdx) / Float(segCount)
                let r0 = (0.024 - 0.017 * t) * s
                capsule(seg, SIMD3<Float>(0, 0, 0), SIMD3<Float>(0, segLen, 0), r0, tendrilMat, shadow: kIdx < 3, detail: 0.55)
                segs.append(seg)
                base.append(SIMD3<Float>(0.16 + 0.06 * t, 0, (i % 2 == 0 ? 0.05 : -0.05)))
                parent = seg
            }
            ellipsoid(parent, SIMD3<Float>(0, segLen, 0), 0.009 * s, SIMD3<Float>(1, 1.6, 1), m.glow, shadow: false, detail: 0.4)
            tendrils.append(Tendril(segments: segs, base: base, phase: Float(i) * 1.3,
                                    freq: 2.2 + 0.35 * Float(i % 3), amp: 0.24))
        }
    }

    /// Stacheln auf Schultern, Rücken und Unterarmen.
    private func buildSpikes(_ m: Palette) {
        let d = dims
        let s = d.s
        let spikeMat = registerMaterial(UIColor(white: 0.13, alpha: 1), rough: 0.35, metal: 0.9)
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let ua = container(left ? .lUpperArm : .rUpperArm)
            let k = s * d.ts
            for i in 0..<3 {
                let fi = Float(i)
                let base = SIMD3<Float>(sd * 0.055, 0.02 - 0.028 * fi, (fi - 1) * 0.03) * k
                cone(ua, base: base, dir: safeNormalize(SIMD3<Float>(sd, 0.75, (fi - 1) * 0.3)), r0: 0.016 * k, r1: 0.0008 * s,
                     h: (0.075 - 0.012 * fi) * s, spikeMat)
            }
            let fa = container(left ? .lForearm : .rForearm)
            let fk = armThickness(left: left)
            for i in 0..<2 {
                let y = (-0.08 - 0.07 * Float(i)) * s
                cone(fa, base: SIMD3<Float>(sd * 0.04 * fk, y, -0.01 * s), dir: safeNormalize(SIMD3<Float>(sd * 0.8, 0.55, -0.2)),
                     r0: 0.011 * s, r1: 0.0006 * s, h: 0.045 * s, spikeMat, shadow: false)
            }
        }
        let ch = container(.chest)
        for i in 0..<4 {
            let fi = Float(i)
            let y = 0.17 - fi * 0.055
            cone(ch, base: pv(0, y, -0.12 * d.td), dir: safeNormalize(SIMD3<Float>(0, 0.35, -1)), r0: 0.016 * s, r1: 0.0008 * s,
                 h: (0.07 - 0.01 * fi) * s, spikeMat)
        }
    }

    /// Offener Laborkittel mit Ärmeln, Revers und schwingenden Schößen.
    private func buildLabCoat(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let sp = container(.spine)
        let hp = container(.hips)
        ellipsoid(ch, pv(0, 0.075, -0.024), 0.172 * s, SIMD3<Float>(1.14 * d.ws, 1.0, 0.72 * d.td), m.coat)
        ellipsoid(sp, pv(0, 0.04, -0.02), 0.128 * s, SIMD3<Float>(1.02 * d.ws, 1.22, 0.82 * d.td * d.belly), m.coat)
        ellipsoid(hp, pv(0, -0.015, -0.02), 0.138 * s, SIMD3<Float>(1.22 * d.hw, 0.74, 0.88 * d.td), m.coat)
        // Revers
        for sd in [Float(1), Float(-1)] {
            let q = simd_quatf(angle: 0.35 * sd, axis: SIMD3<Float>(0, 0, 1)) * simd_quatf(angle: -0.25, axis: SIMD3<Float>(1, 0, 0))
            box(ch, pv(0.062 * sd * d.ws, 0.15, 0.1 * d.td), SIMD3<Float>(0.05, 0.13, 0.008) * s, chamfer: 0.003 * s, m.coat, orient: q)
        }
        // Ärmel
        for left in [true, false] {
            let k = armThickness(left: left)
            capsule(container(left ? .lUpperArm : .rUpperArm), pv(0, -0.005, 0), pv(0, -0.27, 0), 0.058 * k, m.coat)
            capsule(container(left ? .lForearm : .rForearm), pv(0, 0, 0), pv(0, -0.19, 0), 0.052 * k, m.coat)
        }
        // Schöße (schwingen beim Laufen)
        let count = quality == .performance ? 2 : 3
        let segLen = 0.52 * s / Float(count)
        let panels: [(SIMD3<Float>, Float, Float)] = [
            (pv(0, 0, -0.118 * d.td), 0.3 * d.hw, -1),
            (pv(0.085 * d.hw, 0, 0.1 * d.td), 0.13 * d.hw, 1),
            (pv(-0.085 * d.hw, 0, 0.1 * d.td), 0.13 * d.hw, 1)
        ]
        for (idx, panel) in panels.enumerated() {
            let anchor = SCNNode()
            anchor.simdPosition = panel.0
            hp.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let w = (panel.1 + 0.02 * Float(i)) * s
                box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.06, 0.01 * s), chamfer: 0.003 * s, m.coat)
                segs.append(seg)
                parent = seg
            }
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.hips), side: panel.2,
                                        minOffset: panel.2 < 0 ? 0.08 : 0.05, stiffness: 10, drag: 0.4, flutter: 0.18,
                                        phase: Float(idx) * 1.1))
        }
    }

    /// Kapuze (nach hinten versetzt, Gesicht bleibt frei) + Überwurf auf den Schultern.
    private func buildHood(_ m: Palette) {
        let d = dims
        let s = d.s
        let hj = container(.head)
        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let hoodMat = registerMaterial(look.primaryColor.withBrightness(0.6), rough: 0.85, metal: 0)
        ellipsoid(hj, c + SIMD3<Float>(0, 0.29 * r, -0.62 * r), r * 1.25, SIMD3<Float>(hs.x * 1.1, 1.0, 1.08), hoodMat)
        cone(hj, base: c + SIMD3<Float>(0, 1.05 * r, -0.95 * r), dir: safeNormalize(SIMD3<Float>(0, 0.45, -1)),
             r0: 0.05 * s, r1: 0.004 * s, h: 0.08 * s, hoodMat)
        let ch = container(.chest)
        let nt = 1 + (d.ts - 1) * 0.75
        let mantle = SCNCone(topRadius: CGFloat(0.075 * s * nt), bottomRadius: CGFloat(0.2 * s * d.ws), height: CGFloat(0.13 * s))
        mantle.radialSegmentCount = segRadial
        mantle.materials = [hoodMat]
        let mn = SCNNode(geometry: mantle)
        mn.simdPosition = pv(0, 0.215, -0.02)
        mn.simdScale = SIMD3<Float>(1, 1, 0.75 * d.td)
        ch.addChildNode(mn)
    }

    // MARK: - Zerstückelung

    private var pelvisDetached = false

    private static var stumpMatBlood: SCNMaterial?
    private static var stumpMatDry: SCNMaterial?
    private static var boneMat: SCNMaterial?

    private static func stumpMaterial(blood: Bool) -> SCNMaterial {
        if blood {
            if let m = stumpMatBlood { return m }
            let m = Render.pbr(UIColor(red: 0.3, green: 0.012, blue: 0.022, alpha: 1), roughness: 0.3, metalness: 0,
                               emission: UIColor(red: 0.22, green: 0.0, blue: 0.015, alpha: 1), emissionIntensity: 0.3)
            stumpMatBlood = m
            return m
        }
        if let m = stumpMatDry { return m }
        let m = Render.pbr(UIColor(red: 0.05, green: 0.045, blue: 0.045, alpha: 1), roughness: 0.9, metalness: 0,
                           emission: UIColor(red: 0.6, green: 0.15, blue: 0.02, alpha: 1), emissionIntensity: 0.35)
        stumpMatDry = m
        return m
    }

    private static func boneMaterial() -> SCNMaterial {
        if let m = boneMat { return m }
        let m = Render.pbr(UIColor(red: 0.86, green: 0.82, blue: 0.74, alpha: 1), roughness: 0.55, metalness: 0)
        boneMat = m
        return m
    }

    private func rootJoint(of limb: Limb) -> Joint {
        switch limb {
        case .head: return .neck
        case .leftArm: return .lUpperArm
        case .rightArm: return .rUpperArm
        case .leftLeg: return .lThigh
        case .rightLeg: return .rThigh
        case .upperBody: return .spine
        }
    }

    /// true, wenn das Gelenk oder eines seiner Elterngelenke ausgeblendet ist.
    private func isEffectivelyHidden(_ j: Joint) -> Bool {
        var cur: Joint? = j
        while let c = cur {
            if joints[c]?.isHidden == true { return true }
            cur = c.rigParent
        }
        return false
    }

    /// Endpunkte (Welt) und Radius der vereinfachten Kollisionsform eines abgetrennten Teils.
    private func limbSegment(_ limb: Limb) -> (start: SIMD3<Float>, end: SIMD3<Float>, radius: Float, mass: Float) {
        let d = dims
        let s = d.s
        switch limb {
        case .head:
            let a = joint(.neck).simdWorldPosition
            let b = joint(.head).simdConvertPosition(SIMD3<Float>(0, 0.21 * s * d.head, 0.005 * s), to: nil)
            return (a, b, 0.1 * s * d.head, 4.5 * s)
        case .leftArm, .rightArm:
            let left = limb == .leftArm
            let a = joint(left ? .lUpperArm : .rUpperArm).simdWorldPosition
            let b = joint(left ? .lHand : .rHand).simdConvertPosition(SIMD3<Float>(0, -0.1 * s, 0), to: nil)
            return (a, b, 0.052 * s * d.ts, 4.0 * s * d.ts)
        case .leftLeg, .rightLeg:
            let left = limb == .leftLeg
            let a = joint(left ? .lThigh : .rThigh).simdWorldPosition
            let b = joint(left ? .lFoot : .rFoot).simdConvertPosition(SIMD3<Float>(0, -0.04 * s, 0.06 * s), to: nil)
            return (a, b, 0.072 * s * d.ts, 10 * s * d.ts)
        case .upperBody:
            let a = joint(.spine).simdWorldPosition
            let b = joint(.neck).simdConvertPosition(SIMD3<Float>(0, 0.12 * s, 0), to: nil)
            return (a, b, 0.17 * s * d.ws, 32 * s * d.ts)
        }
    }

    /// Schnittfläche (rot-schwarze Scheibe + Knochen), optional mit kurzem Blutstrahl.
    @discardableResult
    private func addCutCap(to parent: SCNNode, at pos: SIMD3<Float>, orient: simd_quatf?, radius: Float, sign: Float,
                           bloodEnabled: Bool, gush: Bool, bone: Bool, scene: SCNScene?) -> SCNNode {
        let cap = SCNNode()
        cap.name = "rig.stump"
        cap.simdPosition = pos
        if let q = orient { cap.simdOrientation = q }
        parent.addChildNode(cap)
        let disc = SCNCylinder(radius: CGFloat(radius), height: CGFloat(radius * 0.22))
        disc.radialSegmentCount = 20
        disc.materials = [CharacterRig.stumpMaterial(blood: bloodEnabled)]
        let dn = SCNNode(geometry: disc)
        dn.simdPosition = SIMD3<Float>(0, sign * radius * 0.04, 0)
        dn.castsShadow = false
        cap.addChildNode(dn)
        if bone {
            let b = SCNCylinder(radius: CGFloat(radius * 0.26), height: CGFloat(radius * 0.3))
            b.radialSegmentCount = 12
            b.materials = [CharacterRig.boneMaterial()]
            let bn = SCNNode(geometry: b)
            bn.simdPosition = SIMD3<Float>(0, sign * radius * 0.07, 0)
            bn.castsShadow = false
            cap.addChildNode(bn)
        }
        if gush && bloodEnabled {
            let p = SCNParticleSystem()
            p.loops = false
            p.emissionDuration = 1.4
            p.birthRate = CGFloat(110 * particleScale)
            p.particleLifeSpan = 0.75
            p.particleLifeSpanVariation = 0.3
            p.particleVelocity = CGFloat(1.7 * dims.s)
            p.particleVelocityVariation = 0.9
            p.emittingDirection = SCNVector3(x: 0, y: sign, z: 0)
            p.spreadingAngle = 22
            p.isAffectedByGravity = true
            p.particleSize = CGFloat(0.02 * dims.s)
            p.particleSizeVariation = CGFloat(0.012 * dims.s)
            p.particleColor = UIColor(red: 0.4, green: 0.0, blue: 0.02, alpha: 1)
            p.particleImage = ProceduralTextures.softDisc()
            p.blendMode = .alpha
            cap.addParticleSystem(p)
        }
        return cap
    }

    private func registerDebris(_ n: SCNNode) {
        ownDebris.append(n)
        CharacterRig.liveDebris = CharacterRig.liveDebris.filter { $0.parent != nil }
        CharacterRig.liveDebris.append(n)
        while CharacterRig.liveDebris.count > CharacterRig.maxLiveDebris {
            let old = CharacterRig.liveDebris.removeFirst()
            old.removeAllActions()
            old.removeFromParentNode()
        }
        n.runAction(SCNAction.sequence([SCNAction.wait(duration: 11),
                                        SCNAction.fadeOut(duration: 1.0),
                                        SCNAction.removeFromParentNode()]))
    }

    /// Klont den Teilbaum `jn` als freies Physik-Trümmerteil in die Szene.
    private func spawnDebris(from jn: SCNNode, start: SIMD3<Float>, end: SIMD3<Float>, radius: Float, mass: Float,
                             sphere: Bool, stripChildJoints: Bool, impulse: SIMD3<Float>, capSign: Float,
                             scene: SCNScene, bloodEnabled: Bool) -> SCNNode {
        let axisRaw = end - start
        var len = simd_length(axisRaw)
        if !len.isFinite || len < 0.01 { len = 0.01 }
        var center = (start + end) * 0.5
        if !(center.x.isFinite && center.y.isFinite && center.z.isFinite) { center = jn.simdWorldPosition }

        let wrapper = SCNNode()
        wrapper.name = "rig.debris"
        scene.rootNode.addChildNode(wrapper)
        var m = simd_float4x4(CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: axisRaw))
        m.columns.3 = SIMD4<Float>(center.x, center.y, center.z, 1)
        wrapper.simdWorldTransform = m

        let visual = jn.clone()
        visual.isHidden = false
        if stripChildJoints {
            for child in visual.childNodes {
                let nm = child.name ?? ""
                if nm.hasPrefix("rig.") && nm != "rig.vis" {
                    child.removeFromParentNode()
                }
            }
        }
        visual.enumerateHierarchy { n, _ in
            n.removeAllParticleSystems()
            n.light = nil
        }
        wrapper.addChildNode(visual)
        visual.simdWorldTransform = jn.simdWorldTransform
        // Schnittfläche am abgetrennten Teil
        addCutCap(to: visual, at: SIMD3<Float>(0, 0, 0), orient: nil, radius: radius * 0.9, sign: capSign,
                  bloodEnabled: bloodEnabled, gush: false, bone: !sphere, scene: nil)

        // Vereinfachte Kollisionsform (Kugel / Kapsel), NICHT aus der Geometrie
        let shapeGeometry: SCNGeometry
        if sphere {
            shapeGeometry = SCNSphere(radius: CGFloat(Swift.max(0.03, len * 0.5)))
        } else {
            shapeGeometry = SCNCapsule(capRadius: CGFloat(radius), height: CGFloat(len + 2 * radius))
        }
        let body = SCNPhysicsBody(type: .dynamic, shape: SCNPhysicsShape(geometry: shapeGeometry, options: nil))
        body.mass = CGFloat(Swift.max(0.5, mass))
        body.friction = 0.9
        body.restitution = 0.12
        body.damping = 0.08
        body.angularDamping = 0.35
        body.continuousCollisionDetectionThreshold = CGFloat(radius * 0.5)
        wrapper.physicsBody = body

        var v = impulse
        if !(v.x.isFinite && v.y.isFinite && v.z.isFinite) { v = SIMD3<Float>(0, 3, 0) }
        let vl = simd_length(v)
        if vl > 22 { v = v * (22 / vl) }
        body.velocity = SCNVector3(x: v.x, y: v.y, z: v.z)
        let spinAxis = randUnit3()
        let spin = randf(4, 11)
        body.angularVelocity = SCNVector4(x: spinAxis.x, y: spinAxis.y, z: spinAxis.z, w: spin)

        registerDebris(wrapper)
        return wrapper
    }

    /// Trennt ein Körperteil ab: Klon mit Physik in die Szene, Original ausblenden, Stumpf + Blut.
    /// impulse ≈ Abfluggeschwindigkeit in m/s (wird auf 22 m/s begrenzt).
    @discardableResult
    func detach(_ limb: Limb, impulse: SIMD3<Float>, in scene: SCNScene, bloodEnabled: Bool) -> SCNNode? {
        if detachedLimbs.contains(limb) || pelvisDetached { return nil }
        let rj = rootJoint(of: limb)
        guard let jn = joints[rj], !isEffectivelyHidden(rj) else { return nil }
        detachedLimbs.insert(limb)

        let seg = limbSegment(limb)
        let isLimb = limb != .head && limb != .upperBody
        // Teil zeigt bei Gliedmaßen entlang -Y vom Gelenk weg, bei Kopf/Oberkörper entlang +Y
        let partSign: Float = isLimb ? -1 : 1
        let cutWorld = jn.simdWorldPosition
        let cutOrientation = jn.simdWorldOrientation

        let piece = spawnDebris(from: jn, start: seg.start, end: seg.end, radius: seg.radius, mass: seg.mass,
                                sphere: limb == .head, stripChildJoints: false, impulse: impulse, capSign: -partSign,
                                scene: scene, bloodEnabled: bloodEnabled)
        jn.isHidden = true

        // Stumpf am Körper
        if let parentJoint = rj.rigParent, let pn = joints[parentJoint] {
            let capRadius: Float
            switch limb {
            case .head: capRadius = 0.05 * dims.s * (1 + (dims.ts - 1) * 0.75)
            case .upperBody: capRadius = 0.13 * dims.s * dims.ws
            default: capRadius = seg.radius
            }
            let cap = addCutCap(to: pn, at: restPositions[rj] ?? jn.simdPosition, orient: jn.simdOrientation,
                                radius: capRadius, sign: partSign, bloodEnabled: bloodEnabled, gush: true,
                                bone: limb != .upperBody, scene: scene)
            stumpNodes.append(cap)
        }

        // Blut / Ersatzeffekt
        let out = safeNormalize(cutOrientation.act(SIMD3<Float>(0, partSign, 0)) + SIMD3<Float>(0, 0.6, 0),
                                fallback: SIMD3<Float>(0, 1, 0))
        if bloodEnabled {
            FX.spawn(.bloodSpray, at: cutWorld, in: scene, direction: out, scale: limb == .upperBody ? 1.5 : 1.1)
            FX.spawn(.bloodSpray, at: cutWorld, in: scene, direction: safeNormalize(-out + SIMD3<Float>(0, 0.8, 0)), scale: 0.6)
            let ground = SIMD3<Float>(cutWorld.x, node.simdWorldPosition.y + 0.01, cutWorld.z)
            FX.spawn(.bloodPool, at: ground, in: scene, scale: limb == .upperBody ? 1.6 : 1.0)
        } else {
            FX.spawn(.smoke, at: cutWorld, in: scene, direction: out, scale: 0.6)
            FX.spawn(.sparks, at: cutWorld, in: scene, direction: out, scale: 0.8)
        }
        return piece
    }

    /// Zerplatzt in Einzelteile (Kopf, Arme, Beine, Oberkörper, Becken).
    func detachAll(impulseScale: Float, in scene: SCNScene, bloodEnabled: Bool) {
        var k = impulseScale.isFinite ? impulseScale : 1
        k = Swift.max(0, Swift.min(k, 4))
        let center = joint(.spine).simdWorldPosition
        let order: [Limb] = [.head, .leftArm, .rightArm, .leftLeg, .rightLeg]
        for limb in order {
            let p = joint(rootJoint(of: limb)).simdWorldPosition
            var dir = safeNormalize(p - center, fallback: randUnit3())
            dir.y = abs(dir.y) + 0.55
            dir = safeNormalize(dir + randUnit3() * 0.25, fallback: SIMD3<Float>(0, 1, 0))
            detach(limb, impulse: dir * (4.5 * k), in: scene, bloodEnabled: bloodEnabled)
        }
        let torsoDir = safeNormalize(randUnit3() * 0.5 + SIMD3<Float>(0, 1, 0), fallback: SIMD3<Float>(0, 1, 0))
        detach(.upperBody, impulse: torsoDir * (3.2 * k), in: scene, bloodEnabled: bloodEnabled)

        // Becken als letztes Stück
        if !pelvisDetached, let hips = joints[.hips], !hips.isHidden {
            pelvisDetached = true
            let s = dims.s
            let a = hips.simdConvertPosition(SIMD3<Float>(0, 0.06 * s, 0), to: nil)
            let b = hips.simdConvertPosition(SIMD3<Float>(0, -0.1 * s, 0), to: nil)
            let pDir = safeNormalize(randUnit3() * 0.4 + SIMD3<Float>(0, 1, 0), fallback: SIMD3<Float>(0, 1, 0))
            _ = spawnDebris(from: hips, start: a, end: b, radius: 0.14 * s * dims.hw, mass: 14 * s,
                            sphere: false, stripChildJoints: true, impulse: pDir * (2.5 * k), capSign: 1,
                            scene: scene, bloodEnabled: bloodEnabled)
            hips.isHidden = true
        }
        if bloodEnabled {
            FX.spawn(.bloodBurst, at: center, in: scene, scale: 1.6)
            FX.spawn(.bloodPool, at: SIMD3<Float>(center.x, node.simdWorldPosition.y + 0.01, center.z), in: scene, scale: 2.0)
        } else {
            FX.spawn(.smoke, at: center, in: scene, scale: 1.4)
        }
    }

    /// Neue Runde: alles wieder anfügen/einblenden, Trümmer entfernen, Material normal.
    func resetBody() {
        for (_, n) in joints { n.isHidden = false }
        for n in stumpNodes { n.removeFromParentNode() }
        stumpNodes.removeAll()
        for n in ownDebris {
            n.removeAllActions()
            n.removeFromParentNode()
        }
        ownDebris.removeAll()
        CharacterRig.liveDebris = CharacterRig.liveDebris.filter { $0.parent != nil }
        detachedLimbs.removeAll()
        pelvisDetached = false
        flashAmount = 0
        matState = .normal
        matAmount = 0
        crackHeat = 0
        node.isHidden = false
        node.opacity = 1
        for c in swayChains { c.reset() }
        refreshMaterials()
    }
}
