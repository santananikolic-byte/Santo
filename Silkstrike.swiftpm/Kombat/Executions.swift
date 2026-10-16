import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Exekutionen & Brutal-Schlag – geskriptete Kinosequenzen
// =====================================================================

struct CinematicCamera {
    var position: SIMD3<Float>
    var lookAt: SIMD3<Float>
    var fov: Float
}

/// Gemeinsamer Zeitstrahl: Ereignisse, Kameraschnitte, Tweens.
class KombatTimeline {
    struct Cue {
        let time: Float
        let action: () -> Void
    }
    struct CamShot {
        let start: Float
        let end: Float
        let from: CinematicCamera
        let to: CinematicCamera
    }
    struct Tween {
        let start: Float
        let end: Float
        let apply: (Float) -> Void
    }

    private(set) var t: Float = 0
    private var cues: [Cue] = []
    private var nextCue = 0
    private var shots: [CamShot] = []
    private var tweens: [Tween] = []
    private(set) var camera: CinematicCamera
    let attacker: CharacterRig
    let victim: CharacterRig
    let scene: SCNScene
    let floorY: Float
    let bloodEnabled: Bool
    let color: UIColor
    /// +1, wenn der Angreifer nach +X schaut.
    let facing: Float
    var strands: [WebStrand] = []

    var onShake: ((Float) -> Void)?
    var onFlash: ((UIColor) -> Void)?
    var onTimeScale: ((Float) -> Void)?
    var onSound: ((SoundEffect) -> Void)?

    init(attacker: CharacterRig, victim: CharacterRig, color: UIColor, scene: SCNScene, floorY: Float, bloodEnabled: Bool) {
        self.attacker = attacker
        self.victim = victim
        self.color = color
        self.scene = scene
        self.floorY = floorY
        self.bloodEnabled = bloodEnabled
        let ax = attacker.node.simdPosition.x
        let vx = victim.node.simdPosition.x
        facing = vx >= ax ? 1 : -1
        let mid = (attacker.node.simdPosition + victim.node.simdPosition) * 0.5
        camera = CinematicCamera(position: mid + SIMD3<Float>(0, 1.6, 6), lookAt: mid + SIMD3<Float>(0, 1, 0), fov: 45)
    }

    var victimPos: SIMD3<Float> { return victim.node.simdPosition }
    var attackerPos: SIMD3<Float> { return attacker.node.simdPosition }

    func cue(_ time: Float, _ action: @escaping () -> Void) {
        cues.append(Cue(time: time, action: action))
    }

    func shot(_ start: Float, _ end: Float, from: CinematicCamera, to: CinematicCamera) {
        shots.append(CamShot(start: start, end: end, from: from, to: to))
    }

    func tween(_ start: Float, _ end: Float, _ apply: @escaping (Float) -> Void) {
        tweens.append(Tween(start: start, end: end, apply: apply))
    }

    /// Kamera relativ zum Opfer: side = seitlicher Versatz (in Blickrichtung des Angreifers), z = Abstand zur Kamera.
    func cam(_ side: Float, _ height: Float, _ z: Float, lookHeight: Float, fov: Float, around: SIMD3<Float>? = nil) -> CinematicCamera {
        let c = around ?? victimPos
        return CinematicCamera(position: c + SIMD3<Float>(side * facing, height, z),
                               lookAt: c + SIMD3<Float>(0, lookHeight, 0), fov: fov)
    }

    func strand(from: SIMD3<Float>, to: SIMD3<Float>, color: UIColor, radius: Float = 0.02) -> WebStrand {
        let s = WebStrand(color: color, radius: radius)
        s.update(from: from, to: to)
        scene.rootNode.addChildNode(s.node)
        strands.append(s)
        return s
    }

    func blood(_ kind: EffectKind, at p: SIMD3<Float>, dir: SIMD3<Float> = SIMD3<Float>(0, 1, 0), scale: Float = 1) {
        FX.spawn(kind, at: p, in: scene, direction: dir, scale: scale)
    }

    func sortCues() {
        cues.sort { $0.time < $1.time }
        shots.sort { $0.start < $1.start }
    }

    /// Gibt true zurück, wenn `duration` erreicht ist.
    func advance(dt: Float, duration: Float) -> Bool {
        t += dt
        while nextCue < cues.count && cues[nextCue].time <= t {
            cues[nextCue].action()
            nextCue += 1
        }
        for tw in tweens where t >= tw.start {
            let span = Swift.max(0.0001, tw.end - tw.start)
            tw.apply(Easing.easeInOut.apply(Swift.min(1, (t - tw.start) / span)))
        }
        var active: CamShot? = nil
        for s in shots where t >= s.start { active = s }
        if let s = active {
            let k = Easing.easeInOut.apply(Swift.min(1, (t - s.start) / Swift.max(0.0001, s.end - s.start)))
            camera = CinematicCamera(position: lerp3(s.from.position, s.to.position, k),
                                     lookAt: lerp3(s.from.lookAt, s.to.lookAt, k),
                                     fov: lerpf(s.from.fov, s.to.fov, k))
        }
        attacker.update(dt: dt)
        victim.update(dt: dt)
        if t >= duration {
            for s in strands { s.node.removeFromParentNode() }
            strands.removeAll()
            // Zyklen (Closures halten die Timeline) auflösen
            cues.removeAll()
            tweens.removeAll()
            nextCue = 0
            return true
        }
        return false
    }
}

final class ExecutionSequence {
    let duration: Float
    private let tl: KombatTimeline
    var camera: CinematicCamera { return tl.camera }

    var onShake: ((Float) -> Void)? { didSet { tl.onShake = onShake } }
    var onFlash: ((UIColor) -> Void)? { didSet { tl.onFlash = onFlash } }
    var onTimeScale: ((Float) -> Void)? { didSet { tl.onTimeScale = onTimeScale } }
    var onSound: ((SoundEffect) -> Void)? { didSet { tl.onSound = onSound } }

    init(kind: ExecutionKind, attacker: CharacterRig, victim: CharacterRig, attackerColor: UIColor,
         scene: SCNScene, floorY: Float, bloodEnabled: Bool) {
        tl = KombatTimeline(attacker: attacker, victim: victim, color: attackerColor, scene: scene, floorY: floorY, bloodEnabled: bloodEnabled)
        switch kind {
        case .webDecapitate: duration = 6.5
        case .devour: duration = 6.5
        case .splitInHalf: duration = 6.0
        case .shadowSlice: duration = 6.0
        case .headCrush: duration = 6.5
        case .incinerate: duration = 7.0
        case .impaleBurst: duration = 6.5
        }
        // Aufstellung: Opfer taumelt, Angreifer davor
        let v = victim.node.simdPosition
        let f = tl.facing
        attacker.node.simdPosition = SIMD3<Float>(v.x - f * 1.6, floorY, v.z)
        attacker.node.simdEulerAngles = SIMD3<Float>(0, f > 0 ? Float.pi / 2 : -Float.pi / 2, 0)
        victim.node.simdEulerAngles = SIMD3<Float>(0, f > 0 ? -Float.pi / 2 : Float.pi / 2, 0)
        victim.play(.dizzy)
        attacker.play(.taunt, restart: true)
        build(kind)
        tl.sortCues()
    }

    func update(dt: Float) -> Bool {
        return tl.advance(dt: dt, duration: duration)
    }

    private func build(_ kind: ExecutionKind) {
        let tl = self.tl
        let a = tl.attacker
        let v = tl.victim
        let f = tl.facing
        let head: () -> SIMD3<Float> = { v.worldPosition(of: .head) }
        // Eröffnung (alle): langsamer Push-in auf den Angreifer
        tl.shot(0, 1.2, from: tl.cam(-2.4, 1.2, 4.5, lookHeight: 1.2, fov: 50, around: tl.attackerPos),
                to: tl.cam(-1.2, 1.5, 2.6, lookHeight: 1.5, fov: 38, around: tl.attackerPos))
        tl.cue(0.1) { tl.onSound?(.heartbeat) }

        switch kind {
        case .webDecapitate:
            tl.cue(1.2) {
                a.play(.webShoot, restart: true)
                tl.onSound?(.webShoot)
                _ = tl.strand(from: a.worldPosition(of: .rHand), to: head(), color: .white)
                _ = tl.strand(from: a.worldPosition(of: .lHand), to: head(), color: .white)
            }
            tl.shot(1.2, 2.6, from: tl.cam(0.6, 1.8, 2.2, lookHeight: 1.6, fov: 35), to: tl.cam(1.2, 1.4, 1.6, lookHeight: 1.6, fov: 30))
            tl.cue(1.25) { v.play(.hitHigh, restart: true) }
            tl.cue(2.6) { tl.onTimeScale?(0.3); a.play(.zip, restart: true); tl.onSound?(.webZip) }
            tl.cue(2.75) {
                for s in tl.strands { s.node.removeFromParentNode() }
                tl.strands.removeAll()
                _ = v.detach(.head, impulse: SIMD3<Float>(-f * 7, 4, 0.6), in: tl.scene, bloodEnabled: tl.bloodEnabled)
                tl.blood(.bloodBurst, at: head(), scale: 1.4)
                tl.blood(.bloodSpray, at: v.worldPosition(of: .neck), dir: SIMD3<Float>(0, 1, 0), scale: 1.6)
                tl.onShake?(0.8)
                tl.onFlash?(UIColor(red: 0.8, green: 0, blue: 0, alpha: 1))
                tl.onSound?(.gore)
                tl.onSound?(.boneCrack)
            }
            tl.shot(2.6, 4.0, from: tl.cam(2.5, 0.8, 3, lookHeight: 1.6, fov: 42), to: tl.cam(3.5, 2.2, 4.5, lookHeight: 1.0, fov: 48))
            tl.cue(3.4) { tl.onTimeScale?(1); v.play(.knockdown, restart: true) }
            tl.cue(3.6) { tl.blood(.bloodPool, at: tl.victimPos + SIMD3<Float>(0, 0.02, 0), scale: 1.5) }
            tl.cue(4.4) { a.play(.taunt, restart: true) }
            tl.shot(4.2, 6.5, from: tl.cam(-1.5, 0.6, 3.2, lookHeight: 1.5, fov: 40, around: tl.attackerPos),
                    to: tl.cam(-2.5, 0.4, 4.2, lookHeight: 1.7, fov: 46, around: tl.attackerPos))

        case .devour:
            var tendrils: [WebStrand] = []
            tl.cue(1.2) {
                a.play(.cast, restart: true)
                tl.onSound?(.roar)
                for k in 0..<5 {
                    let s = tl.strand(from: a.worldPosition(of: .chest), to: v.worldPosition(of: .chest) + SIMD3<Float>(0, Float(k) * 0.2 - 0.4, 0),
                                      color: UIColor(red: 0.05, green: 0, blue: 0.08, alpha: 1), radius: 0.05)
                    tendrils.append(s)
                }
            }
            tl.tween(1.3, 3.2) { k in v.setMaterialState(.shadow, amount: k) }
            tl.shot(1.2, 3.2, from: tl.cam(1.5, 1.2, 3.0, lookHeight: 1.2, fov: 40), to: tl.cam(0.6, 1.6, 1.8, lookHeight: 1.4, fov: 30))
            tl.cue(1.4) { v.play(.hitHigh, restart: true); tl.onShake?(0.3) }
            tl.cue(3.2) {
                tl.onTimeScale?(0.35)
                for s in tendrils { s.node.removeFromParentNode() }
                v.detachAll(impulseScale: 1.2, in: tl.scene, bloodEnabled: tl.bloodEnabled)
                tl.blood(.shadowBurst, at: tl.victimPos + SIMD3<Float>(0, 1.2, 0), scale: 2)
                tl.blood(.bloodBurst, at: tl.victimPos + SIMD3<Float>(0, 1.2, 0), scale: 1.6)
                tl.onFlash?(UIColor(red: 0.3, green: 0, blue: 0.4, alpha: 1))
                tl.onShake?(1)
                tl.onSound?(.gore)
                tl.onSound?(.explosion)
            }
            tl.shot(3.2, 4.8, from: tl.cam(3, 1.4, 4, lookHeight: 1, fov: 50), to: tl.cam(4, 3, 6, lookHeight: 0.4, fov: 55))
            tl.cue(4.4) { tl.onTimeScale?(1); a.play(.victory, restart: true) }
            tl.cue(4.6) { tl.blood(.bloodPool, at: tl.victimPos + SIMD3<Float>(0, 0.02, 0), scale: 1.8) }
            tl.shot(4.8, 6.5, from: tl.cam(-1.2, 0.5, 3, lookHeight: 1.6, fov: 38, around: tl.attackerPos),
                    to: tl.cam(-1.8, 0.3, 4, lookHeight: 1.8, fov: 44, around: tl.attackerPos))

        case .splitInHalf:
            tl.cue(1.2) {
                a.play(.cast, restart: true)
                tl.onSound?(.chain)
                _ = tl.strand(from: a.worldPosition(of: .rHand), to: v.worldPosition(of: .hips), color: UIColor(white: 0.6, alpha: 1), radius: 0.03)
            }
            tl.shot(1.2, 2.4, from: tl.cam(0, 1.0, 3.5, lookHeight: 1.0, fov: 40), to: tl.cam(0.4, 1.0, 2.4, lookHeight: 1.0, fov: 34))
            tl.cue(2.4) {
                tl.onTimeScale?(0.25)
                a.play(.dashStrike, restart: true)
                tl.onSound?(.slice)
                tl.onFlash?(.white)
                for s in tl.strands { s.node.removeFromParentNode() }
                tl.strands.removeAll()
                _ = v.detach(.upperBody, impulse: SIMD3<Float>(f * 1.5, 2.5, -0.6), in: tl.scene, bloodEnabled: tl.bloodEnabled)
                tl.blood(.bloodBurst, at: v.worldPosition(of: .hips), scale: 1.6)
                tl.blood(.bloodSpray, at: v.worldPosition(of: .hips), dir: SIMD3<Float>(0, 1, 0), scale: 1.8)
                tl.onShake?(0.8)
                tl.onSound?(.gore)
            }
            tl.shot(2.4, 4.0, from: tl.cam(2.2, 0.6, 2.4, lookHeight: 1.0, fov: 40), to: tl.cam(3.4, 1.8, 4.2, lookHeight: 0.6, fov: 48))
            tl.cue(3.4) { tl.onTimeScale?(1); v.play(.kneel, restart: true) }
            tl.cue(3.9) { tl.blood(.bloodPool, at: tl.victimPos + SIMD3<Float>(0, 0.02, 0), scale: 1.6); tl.onSound?(.bodyFall) }
            tl.cue(4.4) { a.play(.taunt, restart: true) }
            tl.shot(4.2, 6.0, from: tl.cam(-1.4, 0.7, 3.2, lookHeight: 1.5, fov: 40, around: tl.attackerPos),
                    to: tl.cam(-2.2, 0.5, 4.2, lookHeight: 1.7, fov: 46, around: tl.attackerPos))

        case .shadowSlice:
            tl.cue(1.1) {
                tl.blood(.shadowBurst, at: tl.attackerPos + SIMD3<Float>(0, 1, 0), scale: 1.3)
                tl.onSound?(.teleport)
                a.node.simdPosition = tl.victimPos + SIMD3<Float>(f * 1.3, 0, 0)
                a.node.simdEulerAngles = SIMD3<Float>(0, f > 0 ? -Float.pi / 2 : Float.pi / 2, 0)
                tl.blood(.shadowBurst, at: a.node.simdPosition + SIMD3<Float>(0, 1, 0), scale: 1.3)
            }
            tl.shot(1.1, 2.0, from: tl.cam(-1.0, 1.4, 3.2, lookHeight: 1.3, fov: 42), to: tl.cam(-0.5, 1.5, 2.6, lookHeight: 1.4, fov: 36))
            for (i, limb) in [Limb.rightArm, Limb.leftArm, Limb.head].enumerated() {
                let tt = 2.0 + Float(i) * 0.45
                tl.cue(tt) {
                    a.play(i % 2 == 0 ? .punch : .punch2, restart: true)
                    tl.onFlash?(UIColor(red: 0.6, green: 0.4, blue: 1, alpha: 1))
                    tl.onSound?(.slice)
                }
                tl.cue(tt + 0.08) {
                    if i == 2 { tl.onTimeScale?(0.25) }
                    let side: Float = limb == .leftArm ? 0.8 : (limb == .rightArm ? -0.8 : 0)
                    _ = v.detach(limb, impulse: SIMD3<Float>(-f * 2.5, 3.5, side), in: tl.scene, bloodEnabled: tl.bloodEnabled)
                    tl.blood(.bloodSpray, at: v.worldPosition(of: limb == .head ? .neck : .chest), dir: SIMD3<Float>(-f, 0.8, side), scale: 1.2)
                    tl.onShake?(0.5)
                    tl.onSound?(.gore)
                }
            }
            tl.shot(2.0, 3.6, from: tl.cam(2.0, 1.0, 2.6, lookHeight: 1.4, fov: 38), to: tl.cam(2.8, 1.6, 3.6, lookHeight: 1.2, fov: 44))
            tl.cue(3.8) { tl.onTimeScale?(1); v.play(.knockdown, restart: true); tl.onSound?(.bodyFall) }
            tl.cue(4.3) { tl.blood(.bloodPool, at: tl.victimPos + SIMD3<Float>(0, 0.02, 0), scale: 1.6); a.play(.crossArms, restart: true) }
            tl.shot(3.8, 6.0, from: tl.cam(-0.8, 0.6, 3.2, lookHeight: 1.6, fov: 40, around: tl.attackerPos),
                    to: tl.cam(-1.6, 0.4, 4.0, lookHeight: 1.7, fov: 44, around: tl.attackerPos))

        case .headCrush:
            tl.cue(1.1) { a.play(.grab, restart: true); tl.onSound?(.metalHit) }
            tl.tween(1.3, 2.3) { k in
                v.node.simdPosition = SIMD3<Float>(v.node.simdPosition.x, tl.floorY + 0.5 * k, v.node.simdPosition.z)
            }
            tl.shot(1.1, 2.6, from: tl.cam(1.6, 0.6, 2.8, lookHeight: 1.8, fov: 40), to: tl.cam(0.8, 1.4, 1.8, lookHeight: 2.0, fov: 30))
            tl.cue(1.4) { v.play(.hitHigh, restart: true) }
            tl.tween(2.3, 3.4) { k in
                let headNode = v.joint(.head)
                headNode.simdScale = SIMD3<Float>(1 + 0.25 * k, 1 - 0.6 * k, 1 + 0.25 * k)
            }
            tl.cue(2.6) { tl.onSound?(.boneCrack); tl.onShake?(0.3) }
            tl.cue(3.4) {
                tl.onTimeScale?(0.3)
                _ = v.detach(.head, impulse: SIMD3<Float>(0, -1, 0.4), in: tl.scene, bloodEnabled: tl.bloodEnabled)
                tl.blood(.bloodBurst, at: head(), scale: 1.8)
                tl.onFlash?(UIColor(red: 0.8, green: 0, blue: 0, alpha: 1))
                tl.onShake?(0.9)
                tl.onSound?(.gore)
            }
            tl.cue(4.1) {
                tl.onTimeScale?(1)
                a.play(.throwToss, restart: true)
                v.play(.knockdown, restart: true)
            }
            tl.tween(4.1, 4.7) { k in
                let p = v.node.simdPosition
                v.node.simdPosition = SIMD3<Float>(p.x + f * 0.08, tl.floorY + 0.5 * (1 - k), p.z)
            }
            tl.cue(4.8) { tl.onSound?(.bodyFall); tl.blood(.bloodPool, at: tl.victimPos + SIMD3<Float>(0, 0.02, 0), scale: 1.6) }
            tl.shot(3.4, 6.5, from: tl.cam(2.5, 1.2, 3.6, lookHeight: 1.4, fov: 44), to: tl.cam(-2.0, 0.6, 4.4, lookHeight: 1.6, fov: 46, around: tl.attackerPos))

        case .incinerate:
            tl.cue(1.1) { a.play(.cast, restart: true); tl.onSound?(.fire) }
            for k in 0..<6 {
                tl.cue(1.3 + Float(k) * 0.45) {
                    tl.blood(.fireBurst, at: tl.victimPos + SIMD3<Float>(0, 0.4 + Float(k % 3) * 0.5, 0), scale: 1.3)
                    tl.blood(.embers, at: tl.victimPos + SIMD3<Float>(0, 1, 0))
                    tl.onSound?(.fire)
                }
            }
            tl.cue(1.4) { v.play(.hitHigh, restart: true); tl.onShake?(0.3) }
            tl.cue(2.2) { v.play(.kneel, restart: true) }
            tl.tween(1.3, 4.0) { k in v.setMaterialState(.charred, amount: k) }
            tl.shot(1.1, 4.0, from: tl.cam(1.8, 0.8, 3.4, lookHeight: 1.0, fov: 44), to: tl.cam(0.6, 1.2, 2.0, lookHeight: 1.0, fov: 32))
            tl.cue(4.2) {
                tl.onTimeScale?(0.4)
                v.detachAll(impulseScale: 0.35, in: tl.scene, bloodEnabled: false)
                tl.blood(.ash, at: tl.victimPos + SIMD3<Float>(0, 0.8, 0), scale: 2)
                tl.blood(.smoke, at: tl.victimPos + SIMD3<Float>(0, 0.6, 0), scale: 1.5)
                tl.onFlash?(UIColor(red: 1, green: 0.5, blue: 0.1, alpha: 1))
                tl.onShake?(0.6)
                tl.onSound?(.explosion)
            }
            tl.shot(4.2, 5.4, from: tl.cam(2.6, 1.0, 3.6, lookHeight: 0.6, fov: 46), to: tl.cam(3.2, 2.2, 5.0, lookHeight: 0.3, fov: 52))
            tl.cue(5.2) { tl.onTimeScale?(1); a.play(.taunt, restart: true) }
            tl.shot(5.4, 7.0, from: tl.cam(-1.2, 0.7, 3.0, lookHeight: 1.6, fov: 40, around: tl.attackerPos),
                    to: tl.cam(-2.0, 0.5, 4.0, lookHeight: 1.8, fov: 46, around: tl.attackerPos))

        case .impaleBurst:
            tl.cue(1.1) { a.play(.cast, restart: true); tl.onSound?(.roar) }
            tl.cue(1.6) {
                tl.onSound?(.gore)
                tl.onShake?(0.6)
                tl.blood(.bloodSpray, at: tl.victimPos + SIMD3<Float>(0, 0.1, 0), dir: SIMD3<Float>(0, 1, 0), scale: 1.5)
                let spear = SCNNode(geometry: SCNCone(topRadius: 0, bottomRadius: 0.16, height: 2.8))
                spear.geometry?.firstMaterial = Render.pbr(UIColor(red: 0.45, green: 0, blue: 0.02, alpha: 1), roughness: 0.1, metalness: 0.3,
                                                           emission: UIColor(red: 0.8, green: 0, blue: 0.05, alpha: 1), emissionIntensity: 1.5)
                spear.simdPosition = tl.victimPos + SIMD3<Float>(0, 1.0, 0)
                tl.scene.rootNode.addChildNode(spear)
                spear.runAction(SCNAction.sequence([SCNAction.wait(duration: 4.5), SCNAction.fadeOut(duration: 0.5), SCNAction.removeFromParentNode()]))
                v.play(.hitHigh, restart: true)
            }
            tl.tween(1.6, 3.0) { k in
                let p = v.node.simdPosition
                v.node.simdPosition = SIMD3<Float>(p.x, tl.floorY + 1.4 * k, p.z)
            }
            tl.shot(1.1, 3.0, from: tl.cam(1.2, 0.3, 3.0, lookHeight: 1.4, fov: 46), to: tl.cam(1.0, 0.2, 3.4, lookHeight: 2.6, fov: 40))
            tl.cue(3.2) {
                tl.onTimeScale?(0.3)
                v.detachAll(impulseScale: 1.4, in: tl.scene, bloodEnabled: tl.bloodEnabled)
                tl.blood(.bloodBurst, at: tl.victimPos + SIMD3<Float>(0, 1.4, 0), scale: 2.2)
                tl.blood(.explosion, at: tl.victimPos + SIMD3<Float>(0, 1.4, 0), scale: 0.6, dir: SIMD3<Float>(0, 1, 0))
                tl.onFlash?(UIColor(red: 1, green: 0, blue: 0.05, alpha: 1))
                tl.onShake?(1)
                tl.onSound?(.explosion)
                tl.onSound?(.gore)
            }
            tl.shot(3.2, 4.8, from: tl.cam(3, 1.6, 4, lookHeight: 1.6, fov: 50), to: tl.cam(4, 3.2, 6, lookHeight: 0.6, fov: 56))
            tl.cue(4.4) { tl.onTimeScale?(1); a.play(.victory, restart: true) }
            tl.cue(4.6) { tl.blood(.bloodPool, at: SIMD3<Float>(tl.victimPos.x, tl.floorY + 0.02, tl.victimPos.z), scale: 2) }
            tl.shot(4.8, 6.5, from: tl.cam(-1.0, 0.3, 3.4, lookHeight: 1.9, fov: 40, around: tl.attackerPos),
                    to: tl.cam(-1.8, 0.2, 4.6, lookHeight: 2.1, fov: 46, around: tl.attackerPos))
        }
    }
}

extension KombatTimeline {
    func blood(_ kind: EffectKind, at p: SIMD3<Float>, scale: Float, dir: SIMD3<Float>) {
        FX.spawn(kind, at: p, in: scene, direction: dir, scale: scale)
    }
}

// MARK: - Brutal-Schlag

final class BrutalSequence {
    let duration: Float = 3.4
    private let tl: KombatTimeline
    var camera: CinematicCamera { return tl.camera }

    var onShake: ((Float) -> Void)? { didSet { tl.onShake = onShake } }
    var onFlash: ((UIColor) -> Void)? { didSet { tl.onFlash = onFlash } }
    var onTimeScale: ((Float) -> Void)? { didSet { tl.onTimeScale = onTimeScale } }
    var onImpact: ((Int) -> Void)?

    init(attacker: CharacterRig, victim: CharacterRig, attackerColor: UIColor, scene: SCNScene, floorY: Float, bloodEnabled: Bool) {
        tl = KombatTimeline(attacker: attacker, victim: victim, color: attackerColor, scene: scene, floorY: floorY, bloodEnabled: bloodEnabled)
        let v = victim.node.simdPosition
        let f = tl.facing
        attacker.node.simdPosition = SIMD3<Float>(v.x - f * 1.25, floorY, v.z)
        build()
        tl.sortCues()
    }

    func update(dt: Float) -> Bool {
        return tl.advance(dt: dt, duration: duration)
    }

    private func build() {
        let tl = self.tl
        let a = tl.attacker
        let v = tl.victim
        let clips: [AnimClip] = [.punch, .kick2, .uppercut]
        let sounds: [SoundEffect] = [.punchHeavy, .boneCrack, .boneCrack]
        tl.shot(0, 0.5, from: tl.cam(-1.2, 1.4, 2.6, lookHeight: 1.4, fov: 40, around: tl.attackerPos),
                to: tl.cam(-0.6, 1.5, 1.8, lookHeight: 1.5, fov: 30, around: tl.attackerPos))
        tl.cue(0.0) {
            tl.onTimeScale?(0.4)
            tl.onFlash?(tl.color)
            AudioDirector.shared.play(.whoosh)
        }
        for i in 0..<3 {
            let t0 = 0.5 + Float(i) * 0.8
            tl.cue(t0) { a.play(clips[i], restart: true) }
            tl.cue(t0 + 0.22) { [weak self] in
                tl.onFlash?(.white)
                tl.onShake?(i == 2 ? 1 : 0.55)
                v.play(i == 2 ? .knockdown : .hitHigh, restart: true)
                v.setMaterialState(.frozen, amount: 0.65)
                AudioDirector.shared.play(sounds[i])
                AudioDirector.shared.play(.gore, volume: 0.7)
                tl.blood(.bloodSpray, at: v.worldPosition(of: i == 1 ? .hips : .head), dir: SIMD3<Float>(tl.facing, 0.6, 0), scale: 1.1)
                Haptics.heavy()
                self?.onImpact?(i)
            }
            tl.cue(t0 + 0.55) { v.setMaterialState(.normal, amount: 0) }
            let side: Float = i % 2 == 0 ? 1 : -1
            tl.shot(t0, t0 + 0.8, from: tl.cam(side * 1.0, 1.3, 1.6, lookHeight: i == 1 ? 0.9 : 1.6, fov: 28),
                    to: tl.cam(side * 1.4, 1.2, 2.0, lookHeight: i == 1 ? 0.9 : 1.5, fov: 34))
        }
        tl.cue(2.9) { tl.onTimeScale?(1) }
        tl.shot(2.9, 3.4, from: tl.cam(0, 1.6, 5, lookHeight: 1.0, fov: 45), to: tl.cam(0, 1.6, 6, lookHeight: 1.0, fov: 48))
    }
}
