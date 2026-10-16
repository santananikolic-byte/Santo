import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Zwischensequenzen: Kulissen, Schauspieler, Kamerafahrten, Dialoge
// =====================================================================

final class CutsceneController: GameSceneController {

    let scene = SCNScene()
    let cameraNode = SCNNode()
    var onFinished: (() -> Void)?

    private let def: CutsceneDef
    private let settings: GameSettings
    private let hud: CutsceneHUD
    private let camera = SCNCamera()
    private let shake = CameraShake()

    private struct ActorMove {
        let from: SIMD3<Float>
        let to: SIMD3<Float>
        let duration: Float
        var elapsed: Float
    }

    private var actors: [String: CharacterRig] = [:]
    private var moves: [String: ActorMove] = [:]

    private var shotIndex = 0
    private var shotTime: Float = 0
    private var lineIndex = -1
    private var lineTime: Float = 0
    private var fired = Set<Int>()
    private var timeScale: Float = 1
    private var fadeIn: Float = 0
    private var fadeOut: Float = -1
    private var titleTimer: Float = 0
    private var flash: Double = 0
    private var finished = false

    init(def: CutsceneDef, settings: GameSettings, hud: CutsceneHUD) {
        self.def = def
        self.settings = settings
        self.hud = hud
        FX.quality = settings.quality
        FX.bloodEnabled = settings.bloodEnabled

        CutsceneStageBuilder.build(def.stage, timeOfDay: def.timeOfDay, quality: settings.quality, into: scene)

        Render.configureCamera(camera, quality: settings.quality, style: .cinematic)
        camera.zNear = 0.05
        camera.zFar = 2000
        cameraNode.camera = camera
        scene.rootNode.addChildNode(cameraNode)
        if def.timeOfDay == .stormNight && CutsceneStageBuilder.isOutdoor(def.stage) {
            cameraNode.addParticleSystem(FX.makeRain(intensity: 0.7))
        }

        for a in def.actors {
            let rig = CharacterRig(look: Roster.look(for: a.cast), quality: settings.quality)
            rig.node.simdPosition = a.position
            rig.node.simdEulerAngles = SIMD3<Float>(0, deg2rad(a.yawDegrees), 0)
            rig.play(a.clip)
            scene.rootNode.addChildNode(rig.node)
            actors[a.key] = rig
        }
        // Figuren, die erst später auftauchen, sind anfangs versteckt (wenn ein show-Event existiert)
        for shot in def.shots {
            for e in shot.events {
                if case .show(let key) = e.event, let rig = actors[key] {
                    rig.node.isHidden = true
                }
            }
        }

        hud.letterbox = true
        hud.fadeOpacity = 1
        hud.flashOpacity = 0
        hud.speaker = nil
        hud.line = nil
        hud.title = def.title
        titleTimer = def.title == nil ? 0 : 2.8
        if let first = def.shots.first {
            applyCamera(first.camera, k: 0)
        }
    }

    // MARK: GameSceneController

    func didAttach(to view: SCNView) {}

    func teardown() {
        AudioDirector.shared.stopSpeech()
        AudioDirector.shared.setSlowMotion(1)
        FX.cleanup(in: scene)
        cameraNode.removeAllParticleSystems()
        onFinished = nil
    }

    func skip() {
        guard !finished, fadeOut < 0 else { return }
        AudioDirector.shared.stopSpeech()
        fadeOut = 0
    }

    // MARK: Update

    func update(dt: Float) {
        guard !finished else { return }
        // Einblenden
        if fadeIn < 0.8 {
            fadeIn += dt
            let o = Double(Swift.max(0, 1 - fadeIn / 0.8))
            if fadeOut < 0 { hud.fadeOpacity = o }
        }
        if titleTimer > 0 {
            titleTimer -= dt
            if titleTimer <= 0 { hud.title = nil }
        }
        if flash > 0 {
            flash = Swift.max(0, flash - Double(dt) * 2.5)
            hud.flashOpacity = flash
        }
        // Ausblenden
        if fadeOut >= 0 {
            fadeOut += dt
            hud.fadeOpacity = Double(Swift.min(1, fadeOut / 0.6))
            if fadeOut >= 0.65 {
                finish()
                return
            }
        }

        let sdt = dt * timeScale
        for (_, rig) in actors { rig.update(dt: sdt) }
        updateMoves(dt: sdt)

        guard shotIndex < def.shots.count else {
            if fadeOut < 0 { fadeOut = 0 }
            return
        }
        let shot = def.shots[shotIndex]
        shotTime += sdt

        // Ereignisse
        for (i, e) in shot.events.enumerated() where !fired.contains(i) && e.time <= shotTime {
            fired.insert(i)
            fire(e.event)
        }
        // Dialogzeilen
        updateLines(shot, dt: sdt)
        // Kamera
        let k = shot.camera.easing.apply(shotTime / Swift.max(0.01, shot.duration))
        applyCamera(shot.camera, k: k, dt: dt)

        if shotTime >= shot.duration {
            nextShot()
        }
    }

    private func nextShot() {
        shotIndex += 1
        shotTime = 0
        lineIndex = -1
        lineTime = 0
        fired.removeAll()
        if shotIndex >= def.shots.count {
            hud.speaker = nil
            hud.line = nil
            if fadeOut < 0 { fadeOut = 0 }
        }
    }

    private func finish() {
        guard !finished else { return }
        finished = true
        hud.speaker = nil
        hud.line = nil
        hud.title = nil
        AudioDirector.shared.stopSpeech()
        AudioDirector.shared.setSlowMotion(1)
        let cb = onFinished
        onFinished = nil
        cb?()
    }

    private func updateLines(_ shot: Shot, dt: Float) {
        guard !shot.lines.isEmpty else { return }
        if lineIndex < 0 {
            lineIndex = 0
            lineTime = 0
            showLine(shot.lines[0])
            return
        }
        guard lineIndex < shot.lines.count else { return }
        lineTime += dt
        if lineTime >= shot.lines[lineIndex].duration {
            lineIndex += 1
            lineTime = 0
            if lineIndex < shot.lines.count {
                showLine(shot.lines[lineIndex])
            } else {
                hud.speaker = nil
                hud.line = nil
            }
        }
    }

    private func showLine(_ line: DialogLine) {
        hud.speaker = line.speaker.isEmpty ? nil : line.speaker.uppercased()
        hud.line = line.text
        AudioDirector.shared.stopSpeech()
        AudioDirector.shared.speak(line.text, as: line.voice)
    }

    private func applyCamera(_ c: CameraMove, k: Float, dt: Float = 0) {
        let s = shake.update(dt: dt)
        let pos = lerp3(c.from, c.to, k)
        let look = lerp3(c.lookFrom, c.lookTo, k)
        cameraNode.simdPosition = pos + s.offset
        cameraNode.simdLook(at: look, up: SIMD3<Float>(sinf(s.roll), cosf(s.roll), 0), localFront: SIMD3<Float>(0, 0, -1))
        camera.fieldOfView = CGFloat(lerpf(c.fovFrom, c.fovTo, k))
        if settings.quality == .ultra {
            camera.wantsDepthOfField = true
            let focus = c.focusDistance ?? simd_length(look - pos)
            camera.focusDistance = CGFloat(Swift.max(0.3, focus))
            camera.fStop = 2.2
        }
    }

    private func updateMoves(dt: Float) {
        guard !moves.isEmpty else { return }
        var done: [String] = []
        for (key, var m) in moves {
            m.elapsed += dt
            let k = Easing.easeInOut.apply(m.elapsed / Swift.max(0.01, m.duration))
            if let rig = actors[key] {
                rig.node.simdPosition = lerp3(m.from, m.to, k)
            }
            if m.elapsed >= m.duration { done.append(key) }
            moves[key] = m
        }
        for key in done {
            moves[key] = nil
            if let rig = actors[key], rig.currentClip == .walkForward || rig.currentClip == .run {
                rig.play(.idle, blend: 0.2)
            }
        }
    }

    private func fire(_ e: CutsceneEvent) {
        switch e {
        case .clip(let actor, let clip):
            actors[actor]?.play(clip, restart: true, blend: 0.18)
        case .moveTo(let actor, let position, let duration):
            guard let rig = actors[actor] else { return }
            let from = rig.node.simdPosition
            moves[actor] = ActorMove(from: from, to: position, duration: duration, elapsed: 0)
            let dir = position - from
            if horizontalLength(dir) > 0.1 {
                rig.node.simdEulerAngles = SIMD3<Float>(0, yawOfDirection(safeNormalize(flatten(dir))), 0)
                rig.play(horizontalLength(dir) / Swift.max(0.1, duration) > 3 ? .run : .walkForward)
            }
        case .face(let actor, let yaw):
            actors[actor]?.node.simdEulerAngles = SIMD3<Float>(0, deg2rad(yaw), 0)
        case .sound(let s):
            AudioDirector.shared.play(s)
        case .shake(let amount):
            shake.add(amount)
            if amount > 0.5 { Haptics.medium() }
        case .flash(let color):
            hud.flashColor = color
            flash = 0.8
            hud.flashOpacity = flash
        case .effect(let kind, let position):
            FX.spawn(kind, at: position, in: scene)
        case .setCast(let actor, let cast):
            actors[actor]?.setLook(Roster.look(for: cast))
        case .hide(let actor):
            actors[actor]?.node.isHidden = true
        case .show(let actor):
            actors[actor]?.node.isHidden = false
        case .music(let mood):
            AudioDirector.shared.setMusic(mood)
        case .slowMotion(let factor):
            timeScale = clampf(factor, 0.05, 2)
            AudioDirector.shared.setSlowMotion(timeScale)
        }
    }
}

// MARK: - Kulissen

enum CutsceneStageBuilder {

    static func isOutdoor(_ stage: CutsceneStage) -> Bool {
        switch stage {
        case .cityRooftop, .cityStreet: return true
        case .lab: return false
        case .arena(let id): return id != .subway
        }
    }

    static func build(_ stage: CutsceneStage, timeOfDay: TimeOfDay, quality: QualityPreset, into scene: SCNScene) {
        switch stage {
        case .arena(let id):
            _ = ArenaBuilder.build(id, quality: quality, into: scene)
        case .cityRooftop:
            buildRooftop(timeOfDay: timeOfDay, quality: quality, scene: scene)
        case .cityStreet:
            buildStreet(timeOfDay: timeOfDay, quality: quality, scene: scene)
        case .lab:
            buildLab(timeOfDay: timeOfDay, quality: quality, scene: scene)
        }
    }

    private static func standardLights(_ scene: SCNScene, timeOfDay: TimeOfDay, quality: QualityPreset) {
        let key = timeOfDay == .dusk ? UIColor(red: 1, green: 0.65, blue: 0.45, alpha: 1) : UIColor(red: 0.6, green: 0.7, blue: 1, alpha: 1)
        let k = Render.makeKeyLight(direction: SIMD3<Float>(-0.5, -1, -0.4), color: key, intensity: timeOfDay == .dusk ? 1000 : 600,
                                    quality: quality, shadowExtent: 14)
        scene.rootNode.addChildNode(k)
        let rim = Render.makeSpotLight(color: UIColor(red: 1, green: 0.25, blue: 0.3, alpha: 1), intensity: 1800, angle: 60, range: 40, castsShadow: false)
        rim.simdPosition = SIMD3<Float>(0, 6, -8)
        rim.simdLook(at: SIMD3<Float>(0, 1.2, 0))
        scene.rootNode.addChildNode(rim)
        scene.rootNode.addChildNode(Render.makeAmbient(color: UIColor(red: 0.3, green: 0.32, blue: 0.42, alpha: 1), intensity: 180))
    }

    private static func buildRooftop(timeOfDay: TimeOfDay, quality: QualityPreset, scene: SCNScene) {
        Render.applyEnvironment(to: scene, timeOfDay: timeOfDay, quality: quality, fogStart: 60, fogEnd: 600)
        scene.rootNode.addChildNode(CityBuilder.buildBackdrop(seed: 7, quality: quality, timeOfDay: timeOfDay, clearRadius: 30))
        var roof = MeshBuilder()
        roof.addBox(min: SIMD3<Float>(-12, -1, -12), max: SIMD3<Float>(12, 0, 12), uvScale: 0.2)
        let roofMat = Render.texturedPBR(diffuse: ProceduralTextures.concrete(), normal: ProceduralTextures.asphaltNormal(),
                                         roughness: timeOfDay == .stormNight ? 0.15 : 0.6, metalness: 0.1)
        scene.rootNode.addChildNode(roof.buildNode(material: roofMat, name: "roof", castsShadow: false))
        var props = MeshBuilder()
        props.addBox(min: SIMD3<Float>(-12, 0, -12), max: SIMD3<Float>(12, 1.1, -11.6), uvScale: 0.3)
        props.addBox(min: SIMD3<Float>(-12, 0, -12), max: SIMD3<Float>(-11.6, 1.1, 12), uvScale: 0.3)
        props.addBox(min: SIMD3<Float>(11.6, 0, -12), max: SIMD3<Float>(12, 1.1, 12), uvScale: 0.3)
        props.addBox(min: SIMD3<Float>(-6, 0, -8), max: SIMD3<Float>(-3.5, 1.5, -6), uvScale: 0.3)
        props.addBox(min: SIMD3<Float>(4, 0, -9), max: SIMD3<Float>(7.5, 2.2, -6.5), uvScale: 0.3)
        props.addCylinder(center: SIMD3<Float>(-8, 2.5, 5), radius: 2, height: 3.5, segments: 16)
        props.addCylinder(center: SIMD3<Float>(8, 0, 6), radius: 0.12, height: 12, segments: 6)
        scene.rootNode.addChildNode(props.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.4, metalness: 0.7), name: "props"))
        let blink = SCNNode(geometry: SCNSphere(radius: 0.25))
        blink.geometry?.firstMaterial = Render.emissive(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 6)
        blink.simdPosition = SIMD3<Float>(8, 12.2, 6)
        scene.rootNode.addChildNode(blink)
        let rift = FX.makeRiftSwirl(color: UIColor(red: 0.95, green: 0.05, blue: 0.12, alpha: 1))
        rift.simdPosition = SIMD3<Float>(0, 40, -90)
        rift.simdScale = SIMD3<Float>(repeating: 10)
        scene.rootNode.addChildNode(rift)
        standardLights(scene, timeOfDay: timeOfDay, quality: quality)
    }

    private static func buildStreet(timeOfDay: TimeOfDay, quality: QualityPreset, scene: SCNScene) {
        Render.applyEnvironment(to: scene, timeOfDay: timeOfDay, quality: quality, fogStart: 30, fogEnd: 300)
        var ground = MeshBuilder()
        ground.addBox(min: SIMD3<Float>(-60, -0.2, -60), max: SIMD3<Float>(60, 0, 60), uvScale: 0.125)
        scene.rootNode.addChildNode(ground.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.asphalt(), normal: ProceduralTextures.asphaltNormal(),
                                                                                  roughness: 0.25, metalness: 0.05), name: "street", castsShadow: false))
        var walls = MeshBuilder()
        for side: Float in [-1, 1] {
            for k in 0..<6 {
                let z = -50 + Float(k) * 18
                walls.addBox(min: SIMD3<Float>(side * 10 - (side > 0 ? 0 : 14), 0, z), max: SIMD3<Float>(side * 10 + (side > 0 ? 14 : 0), 40 + Float(k * 13 % 50), z + 16),
                             uvScale: 1 / ProceduralTextures.facadeTileMeters)
            }
        }
        let mat = Render.texturedPBR(diffuse: ProceduralTextures.facade(style: 1, lit: false), roughness: 0.7, metalness: 0.05,
                                     emission: ProceduralTextures.facade(style: 1, lit: true))
        scene.rootNode.addChildNode(walls.buildNode(material: mat, name: "walls"))
        standardLights(scene, timeOfDay: timeOfDay, quality: quality)
    }

    private static func buildLab(timeOfDay: TimeOfDay, quality: QualityPreset, scene: SCNScene) {
        Render.applyEnvironment(to: scene, timeOfDay: timeOfDay, quality: quality, fogStart: 80, fogEnd: 700)
        let skyline = CityBuilder.buildBackdrop(seed: 11, quality: quality, timeOfDay: timeOfDay, clearRadius: 40)
        skyline.simdPosition = SIMD3<Float>(0, -120, 0)
        scene.rootNode.addChildNode(skyline)
        let floorMat = Render.texturedPBR(diffuse: ProceduralTextures.tiles(), roughness: 0.2, metalness: 0.1)
        var floor = MeshBuilder()
        floor.addBox(min: SIMD3<Float>(-8, -0.2, -6), max: SIMD3<Float>(8, 0, 6), uvScale: 0.25)
        scene.rootNode.addChildNode(floor.buildNode(material: floorMat, name: "labFloor", castsShadow: false))
        let wallMat = Render.pbr(UIColor(white: 0.12, alpha: 1), roughness: 0.5, metalness: 0.4)
        var walls = MeshBuilder()
        walls.addBox(min: SIMD3<Float>(-8.2, 0, -6), max: SIMD3<Float>(-8, 4, 6), uvScale: 0.25)
        walls.addBox(min: SIMD3<Float>(8, 0, -6), max: SIMD3<Float>(8.2, 4, 6), uvScale: 0.25)
        walls.addBox(min: SIMD3<Float>(-8, 3.8, -6), max: SIMD3<Float>(8, 4, 6), uvScale: 0.25)
        // Fensterrahmen an der Rückwand (Blick auf die Skyline)
        for k in 0..<5 {
            let x = -8 + Float(k) * 4
            walls.addBox(min: SIMD3<Float>(x - 0.1, 0, -6.2), max: SIMD3<Float>(x + 0.1, 4, -6), uvScale: 0.25)
        }
        walls.addBox(min: SIMD3<Float>(-8, 0, -6.2), max: SIMD3<Float>(8, 0.8, -6), uvScale: 0.25)
        // Arbeitstisch
        walls.addBox(min: SIMD3<Float>(2.5, 0.9, -3.5), max: SIMD3<Float>(6.5, 1.0, -2), uvScale: 0.25)
        walls.addBox(min: SIMD3<Float>(2.6, 0, -3.4), max: SIMD3<Float>(2.8, 0.9, -2.1), uvScale: 0.25)
        walls.addBox(min: SIMD3<Float>(6.2, 0, -3.4), max: SIMD3<Float>(6.4, 0.9, -2.1), uvScale: 0.25)
        scene.rootNode.addChildNode(walls.buildNode(material: wallMat, name: "labWalls"))
        // Glasscheibe
        let glass = SCNNode(geometry: SCNPlane(width: 16, height: 3.2))
        let gm = Render.pbr(UIColor(red: 0.6, green: 0.75, blue: 0.9, alpha: 1), roughness: 0.02, metalness: 0.2)
        gm.transparency = 0.12
        gm.isDoubleSided = true
        glass.geometry?.firstMaterial = gm
        glass.simdPosition = SIMD3<Float>(0, 2.4, -6.1)
        scene.rootNode.addChildNode(glass)
        // Monitore
        var screens = MeshBuilder()
        for k in 0..<3 {
            let x = 3 + Float(k) * 1.2
            screens.addBox(min: SIMD3<Float>(x, 1.1, -3.3), max: SIMD3<Float>(x + 1.0, 1.75, -3.25), uvScale: 1)
        }
        scene.rootNode.addChildNode(screens.buildNode(material: Render.emissive(UIColor(red: 0.2, green: 0.8, blue: 1, alpha: 1), intensity: 2.5), name: "screens", castsShadow: false))
        // Probe: schwarze Seide im Glaszylinder
        let tube = SCNNode(geometry: SCNCylinder(radius: 0.35, height: 1.4))
        let tm = Render.pbr(UIColor(white: 0.9, alpha: 1), roughness: 0.02, metalness: 0)
        tm.transparency = 0.25
        tube.geometry?.firstMaterial = tm
        tube.simdPosition = SIMD3<Float>(-4.5, 0.7, -3)
        scene.rootNode.addChildNode(tube)
        let silk = SCNNode(geometry: SCNSphere(radius: 0.22))
        let sm = Render.pbr(UIColor(red: 0.03, green: 0, blue: 0.05, alpha: 1), roughness: 0.1, metalness: 0.4,
                            emission: UIColor(red: 0.5, green: 0.05, blue: 0.8, alpha: 1), emissionIntensity: 1.5)
        silk.geometry?.firstMaterial = sm
        silk.simdPosition = SIMD3<Float>(-4.5, 0.75, -3)
        silk.runAction(SCNAction.repeatForever(SCNAction.sequence([SCNAction.scale(to: 1.25, duration: 0.9), SCNAction.scale(to: 0.85, duration: 0.9)])))
        scene.rootNode.addChildNode(silk)
        let glow = Render.makePointLight(color: UIColor(red: 0.6, green: 0.1, blue: 1, alpha: 1), intensity: 600, range: 6)
        glow.simdPosition = SIMD3<Float>(-4.5, 1.2, -3)
        scene.rootNode.addChildNode(glow)
        for x: Float in [-4, 0, 4] {
            let l = Render.makePointLight(color: UIColor(red: 0.85, green: 0.92, blue: 1, alpha: 1), intensity: 700, range: 9)
            l.simdPosition = SIMD3<Float>(x, 3.6, 0)
            scene.rootNode.addChildNode(l)
        }
        standardLights(scene, timeOfDay: timeOfDay, quality: quality)
    }
}
