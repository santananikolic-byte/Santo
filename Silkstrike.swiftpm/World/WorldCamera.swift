import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  SILKSTRIKE – Weltkamera
//  Third-Person-Orbit hinter/über dem Helden: Look-Eingabe (Empfindlichkeit,
//  Invertierung), automatisches Nachführen hinter die Flugrichtung,
//  Kollisionsvermeidung mit Gebäuden, FOV nach Tempo, Bewegungsunschärfe,
//  Speed-Lines, Trauma-Shake und Regen bei Sturmnacht.
// =====================================================================

final class WorldCamera {

    enum Mode {
        case ground
        case air
        case swing
        case dive
        case wall
        case zip
        case perch
        case combat
    }

    let node: SCNNode
    let camera: SCNCamera

    /// Yaw der Blickrichtung (atan2(x, z)), Pitch > 0 = Kamera oberhalb, schaut nach unten.
    private(set) var yaw: Float = 0
    private(set) var pitch: Float = 0.22
    /// Aktuelle Weltposition der Kamera (inkl. Shake).
    private(set) var position = SIMD3<Float>(0, 10, -6)
    /// Normierte Blickrichtung (ohne Shake).
    private(set) var forward = SIMD3<Float>(0, 0, 1)

    /// Horizontale Blickrichtung (normiert).
    var flatForward: SIMD3<Float> {
        return safeNormalize(flatten(forward), fallback: SIMD3<Float>(sinf(yaw), 0, cosf(yaw)))
    }

    var sensitivity: Float
    var invertY: Bool

    private let quality: QualityPreset
    private let shake = CameraShake()

    private var pivot = SIMD3<Float>(0, 0, 0)
    private var distance: Float = 5.5
    private var fov: Float = 60
    private var fovKick: Float = 0
    private var lookIdle: Float = 10
    private var dutch: Float = 0
    private var aspectFactor: Float = 0.6      // 0 = iPad 4:3, 1 = breites iPhone
    private var lastAppliedFov: Float = -1
    private var lastAppliedBlur: Float = -1

    // Speed-Lines (dünne Leuchtstreifen im Kameraraum)
    private let streakRoot = SCNNode()
    private var streaks: [SCNNode] = []
    private var streakZ: [Float] = []
    private var streakXY: [SIMD2<Float>] = []
    private var streakIntensity: Float = 0

    private var rainSystem: SCNParticleSystem?

    // MARK: - Init

    init(quality: QualityPreset, settings: GameSettings, timeOfDay: TimeOfDay) {
        self.quality = quality
        self.sensitivity = Swift.max(0.1, settings.cameraSensitivity)
        self.invertY = settings.invertCameraY

        let cam = SCNCamera()
        Render.configureCamera(cam, quality: quality, style: .gameplay)
        cam.projectionDirection = .vertical
        cam.zNear = 0.12
        cam.zFar = 2400
        cam.fieldOfView = 60
        self.camera = cam

        let n = SCNNode()
        n.name = "worldCamera"
        n.camera = cam
        self.node = n

        buildStreaks()

        if timeOfDay == .stormNight {
            let rain = FX.makeRain(intensity: 1.0)
            n.addParticleSystem(rain)
            rainSystem = rain
        }
    }

    // MARK: - Öffentliche Steuerung

    /// Bildseitenverhältnis (Breite / Höhe) – passt die FOV-Werte an breite iPhones an.
    func setViewAspect(_ aspect: Float) {
        guard aspect.isFinite, aspect > 0.2 else { return }
        let a = aspect >= 1 ? aspect : 1 / aspect
        aspectFactor = clampf((a - 1.33) / (2.17 - 1.33), 0, 1)
    }

    func addShake(_ trauma: Float) {
        guard trauma.isFinite, trauma > 0 else { return }
        shake.add(Swift.min(1, trauma))
    }

    /// Kurzer FOV-Stoß (positiv = weiter, negativ = Zoom-Punch).
    func kickFOV(_ degrees: Float) {
        guard degrees.isFinite else { return }
        fovKick = clampf(fovKick + degrees, -12, 14)
    }

    /// Kamera ohne Glättung hinter das Ziel setzen (Spawn, Respawn).
    func snap(target: SIMD3<Float>, yaw newYaw: Float) {
        yaw = newYaw.isFinite ? wrapAngle(newYaw) : 0
        pitch = 0.22
        pivot = target
        distance = 5.5
        lookIdle = 10
        fovKick = 0
        dutch = 0
        shake.reset()
        let dir = WorldCamera.direction(yaw: yaw, pitch: pitch)
        position = pivot - dir * distance
        forward = dir
        node.simdPosition = position
        node.simdLook(at: pivot + SIMD3<Float>(0, 0.3, 0), up: SIMD3<Float>(0, 1, 0), localFront: SIMD3<Float>(0, 0, -1))
    }

    func teardown() {
        node.removeAllParticleSystems()
        rainSystem = nil
        streakRoot.removeFromParentNode()
        streaks.removeAll()
    }

    // MARK: - Update

    /// - Parameters:
    ///   - look: Pixel-Delta aus `input.consumeLook()` (UIKit-Konvention: +y = Finger nach unten).
    ///   - target: Punkt, um den die Kamera kreist (Brusthöhe des Helden).
    func update(dt: Float,
                look: SIMD2<Float>,
                target: SIMD3<Float>,
                velocity: SIMD3<Float>,
                facingYaw: Float,
                mode: Mode,
                city: City) {
        guard dt > 0 else { return }
        let speed = simd_length(velocity)
        let hs = horizontalLength(velocity)

        // 1) Look-Eingabe
        let k: Float = 0.0042 * sensitivity
        if look.x != 0 || look.y != 0 {
            yaw = wrapAngle(yaw - look.x * k)
            pitch += look.y * k * 0.8 * (invertY ? -1 : 1)
            lookIdle = 0
        } else {
            lookIdle += dt
        }

        // 2) Automatisch hinter die Bewegung schwenken
        let defaultPitch = WorldCamera.defaultPitch(for: mode)
        if mode == .wall {
            if lookIdle > 0.6 {
                yaw = dampAngle(yaw, facingYaw, lambda: 3.0, dt: dt)
                pitch = damp(pitch, defaultPitch, lambda: 2.0, dt: dt)
            }
        } else if lookIdle > 1.5 {
            let ramp = clampf((lookIdle - 1.5) / 0.8, 0, 1)
            if hs > 3 {
                let velYaw = atan2f(velocity.x, velocity.z)
                var strength: Float = 1.5
                if mode == .swing || mode == .dive || mode == .zip { strength = 2.6 }
                let s = clampf((hs - 3) / 10, 0, 1) * ramp
                yaw = dampAngle(yaw, velYaw, lambda: strength * s, dt: dt)
            }
            pitch = damp(pitch, defaultPitch, lambda: 1.4 * ramp, dt: dt)
        }
        pitch = clampf(pitch, -0.6, 1.25)

        // 3) Abstand je nach Modus
        var baseDist: Float
        switch mode {
        case .ground: baseDist = 5.0 + clampf(hs / 16, 0, 1) * 1.0
        case .perch: baseDist = 5.6
        case .air: baseDist = 6.2
        case .swing: baseDist = 6.8 + clampf(speed / 40, 0, 1) * 2.2
        case .dive: baseDist = 6.0
        case .wall: baseDist = 6.4
        case .zip: baseDist = 7.0
        case .combat: baseDist = 6.8
        }

        // 4) Pivot folgt dem Ziel (Höhe etwas träger → weiche Landungen)
        if !(pivot.x.isFinite && pivot.y.isFinite && pivot.z.isFinite) { pivot = target }
        pivot.x = damp(pivot.x, target.x, lambda: 20, dt: dt)
        pivot.z = damp(pivot.z, target.z, lambda: 20, dt: dt)
        pivot.y = damp(pivot.y, target.y, lambda: 11, dt: dt)
        let lag = pivot - target
        let lagLen = simd_length(lag)
        if lagLen > 4 {
            pivot = target + lag * (4 / lagLen)
        }

        // 5) Richtung + Kollision mit Gebäuden
        let dir = WorldCamera.direction(yaw: yaw, pitch: pitch)
        var allowed = baseDist
        if let hit = city.raycast(from: pivot, direction: -dir, maxDistance: baseDist + 0.6) {
            allowed = Swift.max(0.9, simd_distance(hit, pivot) - 0.45)
        }
        if allowed < distance {
            distance = allowed                                   // sofort heranziehen
        } else {
            distance = damp(distance, allowed, lambda: 2.5, dt: dt)  // langsam wieder raus
        }
        var camPos = pivot - dir * distance
        if camPos.y < 0.35 { camPos.y = 0.35 }

        // 6) FOV nach Tempo (60 → 80 auf iPad, etwas enger auf breiten iPhones)
        let t = clampf((speed - 12) / 38, 0, 1)
        let baseFov = lerpf(60, 52, aspectFactor)
        let maxFov = lerpf(80, 72, aspectFactor)
        var targetFov = lerpf(baseFov, maxFov, t)
        if mode == .dive { targetFov += 3 }
        fov = damp(fov, targetFov, lambda: 3.2, dt: dt)
        fovKick = damp(fovKick, 0, lambda: 4.0, dt: dt)
        let finalFov = clampf(fov + fovKick, 35, 100)
        if Swift.abs(finalFov - lastAppliedFov) > 0.05 {
            camera.fieldOfView = CGFloat(finalFov)
            lastAppliedFov = finalFov
        }

        // 7) Bewegungsunschärfe bei hohem Tempo
        if quality != .performance {
            let blur = (clampf((speed - 26) / 30, 0, 1) * 0.5 * 50).rounded() / 50
            if blur != lastAppliedBlur {
                camera.motionBlurIntensity = CGFloat(blur)
                lastAppliedBlur = blur
            }
        }

        // 8) Shake + leichte Schräglage beim Schwingen
        let s = shake.update(dt: dt)
        camPos += s.offset
        let rightFlat = SIMD3<Float>(-dir.z, 0, dir.x)
        let lateral = simd_dot(velocity, safeNormalize(rightFlat, fallback: SIMD3<Float>(1, 0, 0)))
        let dutchTarget: Float = (mode == .swing) ? clampf(-lateral / 40, -1, 1) * 0.07 : 0
        dutch = damp(dutch, dutchTarget, lambda: 3, dt: dt)

        node.simdPosition = camPos
        node.simdLook(at: pivot + SIMD3<Float>(0, 0.3, 0), up: SIMD3<Float>(0, 1, 0), localFront: SIMD3<Float>(0, 0, -1))
        let roll = s.roll + dutch
        if roll != 0 {
            node.simdOrientation = node.simdOrientation * simd_quatf(angle: roll, axis: SIMD3<Float>(0, 0, 1))
        }
        position = camPos
        forward = dir

        // 9) Speed-Lines
        updateStreaks(dt: dt, speed: speed)
    }

    // MARK: - Intern

    private static func direction(yaw: Float, pitch: Float) -> SIMD3<Float> {
        let cp = cosf(pitch)
        return SIMD3<Float>(sinf(yaw) * cp, -sinf(pitch), cosf(yaw) * cp)
    }

    private static func defaultPitch(for mode: Mode) -> Float {
        switch mode {
        case .ground: return 0.22
        case .perch: return 0.3
        case .air: return 0.18
        case .swing: return 0.1
        case .dive: return 0.55
        case .wall: return -0.15
        case .zip: return 0.12
        case .combat: return 0.32
        }
    }

    private func buildStreaks() {
        let box = SCNBox(width: 0.012, height: 0.012, length: 1.8, chamferRadius: 0)
        let m = SCNMaterial()
        m.lightingModel = .constant
        m.diffuse.contents = UIColor.black
        m.emission.contents = UIColor(white: 0.92, alpha: 1)
        m.blendMode = .add
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = false
        box.firstMaterial = m

        let count = quality == .performance ? 12 : 22
        for _ in 0..<count {
            let s = SCNNode(geometry: box)
            s.castsShadow = false
            s.renderingOrder = 3000
            let xy = WorldCamera.randomStreakXY()
            let z = randf(-18, -2)
            s.simdPosition = SIMD3<Float>(xy.x, xy.y, z)
            streakRoot.addChildNode(s)
            streaks.append(s)
            streakZ.append(z)
            streakXY.append(xy)
        }
        streakRoot.isHidden = true
        streakRoot.opacity = 0
        node.addChildNode(streakRoot)
    }

    private static func randomStreakXY() -> SIMD2<Float> {
        let a = randf(0, Float.pi * 2)
        let r = randf(1.4, 3.2)
        return SIMD2<Float>(cosf(a) * r, sinf(a) * r * 0.62)
    }

    private func updateStreaks(dt: Float, speed: Float) {
        let target = clampf((speed - 24) / 24, 0, 1)
        streakIntensity = damp(streakIntensity, target, lambda: 5, dt: dt)
        if streakIntensity < 0.02 {
            if !streakRoot.isHidden { streakRoot.isHidden = true }
            return
        }
        if streakRoot.isHidden { streakRoot.isHidden = false }
        streakRoot.opacity = CGFloat(streakIntensity * 0.55)
        let advance = (12 + speed * 0.9) * dt
        for i in 0..<streaks.count {
            var z = streakZ[i] + advance
            if z > -1 {
                z = randf(-18, -12)
                streakXY[i] = WorldCamera.randomStreakXY()
            }
            streakZ[i] = z
            let xy = streakXY[i]
            streaks[i].simdPosition = SIMD3<Float>(xy.x, xy.y, z)
        }
    }
}
