import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  SILKSTRIKE – Titelkulisse
//  Nächtliches Neo-Haven im Gewitterregen. Silkstrike hockt auf der
//  Brüstung eines Hochhauses, am Himmel dreht sich der blutrote Riss.
//  Langsame Kran-/Orbitkamera, Blitze, blinkende Antennenlichter.
// =====================================================================

final class TitleBackdropController: GameSceneController {

    let scene: SCNScene
    let cameraNode: SCNNode

    private let quality: QualityPreset
    private var hero: CharacterRig?
    private let heroFeet: SIMD3<Float>
    private let riftPosition: SIMD3<Float>
    private var time: Float = 0
    private var isTornDown = false

    // Blitz
    private let lightningNode: SCNNode
    private var lightningCooldown: Float = 5.5
    private var lightningAge: Float = -1
    private var thunderDelay: Float = -1

    // Blinkende Lichter
    private var beaconMaterials: [SCNMaterial] = []
    private var riftLight: SCNNode?

    init(quality: QualityPreset, darkSuit: Bool = false) {
        self.quality = quality
        self.scene = SCNScene()
        self.cameraNode = SCNNode()
        self.heroFeet = SIMD3<Float>(0, 1.05, -0.85)
        self.riftPosition = SIMD3<Float>(-28, 64, -175)
        self.lightningNode = SCNNode()

        buildEnvironment()
        buildRooftop()
        buildHero(darkSuit: darkSuit)
        buildLights()
        buildRift()
        buildCamera()
        updateCamera()
    }

    // MARK: - Aufbau

    private func buildEnvironment() {
        Render.applyEnvironment(to: scene,
                                timeOfDay: .stormNight,
                                quality: quality,
                                fogStart: 70,
                                fogEnd: 620,
                                fogColor: UIColor(red: 0.05, green: 0.045, blue: 0.08, alpha: 1))
        let skyline = CityBuilder.buildBackdrop(seed: 0x51_1C_57_12,
                                                quality: quality,
                                                timeOfDay: .stormNight,
                                                clearRadius: 42)
        scene.rootNode.addChildNode(skyline)
    }

    private func buildRooftop() {
        let root = SCNNode()
        root.name = "titleRooftop"
        scene.rootNode.addChildNode(root)

        let wetConcrete = Render.pbr(UIColor(red: 0.16, green: 0.16, blue: 0.18, alpha: 1), roughness: 0.32, metalness: 0.05)
        let darkConcrete = Render.pbr(UIColor(red: 0.09, green: 0.09, blue: 0.11, alpha: 1), roughness: 0.8, metalness: 0.0)
        let metal = Render.pbr(UIColor(red: 0.22, green: 0.23, blue: 0.26, alpha: 1), roughness: 0.45, metalness: 0.85)
        let rust = Render.pbr(UIColor(red: 0.24, green: 0.13, blue: 0.09, alpha: 1), roughness: 0.7, metalness: 0.5)
        let puddle = Render.pbr(UIColor(red: 0.02, green: 0.02, blue: 0.03, alpha: 1), roughness: 0.04, metalness: 0.6)

        // Dachplatte (Oberkante y = 0) und Fassade, die 60 m in die Tiefe fällt
        addBox(to: root, size: SIMD3<Float>(28, 1, 24), center: SIMD3<Float>(0, -0.5, 11), material: wetConcrete)
        addBox(to: root, size: SIMD3<Float>(28, 60, 24), center: SIMD3<Float>(0, -31, 11), material: darkConcrete)

        // Brüstung an der Vorderkante (zur Stadt hin) + Seitenbrüstungen
        addBox(to: root, size: SIMD3<Float>(28, 1.05, 0.5), center: SIMD3<Float>(0, 0.525, -0.85), material: darkConcrete)
        addBox(to: root, size: SIMD3<Float>(0.5, 1.05, 24), center: SIMD3<Float>(-13.75, 0.525, 11), material: darkConcrete)
        addBox(to: root, size: SIMD3<Float>(0.5, 1.05, 24), center: SIMD3<Float>(13.75, 0.525, 11), material: darkConcrete)
        // Abdeckblech auf der Brüstung
        addBox(to: root, size: SIMD3<Float>(28.2, 0.06, 0.62), center: SIMD3<Float>(0, 1.08, -0.85), material: metal)

        // Wassertank auf Stelzen
        let tank = SCNNode(geometry: SCNCylinder(radius: 2.1, height: 3.6))
        tank.geometry?.firstMaterial = rust
        tank.simdPosition = SIMD3<Float>(-8.5, 4.6, 13)
        root.addChildNode(tank)
        let roofCone = SCNNode(geometry: SCNCone(topRadius: 0.1, bottomRadius: 2.3, height: 1.0))
        roofCone.geometry?.firstMaterial = rust
        roofCone.simdPosition = SIMD3<Float>(-8.5, 6.9, 13)
        root.addChildNode(roofCone)
        let legOffsets: [SIMD2<Float>] = [SIMD2<Float>(-1.4, -1.4), SIMD2<Float>(1.4, -1.4), SIMD2<Float>(-1.4, 1.4), SIMD2<Float>(1.4, 1.4)]
        for o in legOffsets {
            addBox(to: root, size: SIMD3<Float>(0.18, 2.8, 0.18), center: SIMD3<Float>(-8.5 + o.x, 1.4, 13 + o.y), material: metal)
        }

        // Klimageräte
        addBox(to: root, size: SIMD3<Float>(2.4, 1.3, 1.6), center: SIMD3<Float>(-6.5, 0.65, 6.5), material: metal)
        addBox(to: root, size: SIMD3<Float>(2.4, 1.3, 1.6), center: SIMD3<Float>(-6.5, 0.65, 8.6), material: metal)
        addBox(to: root, size: SIMD3<Float>(1.8, 1.0, 1.8), center: SIMD3<Float>(7.5, 0.5, 9.5), material: metal)
        let fan = SCNNode(geometry: SCNCylinder(radius: 0.7, height: 0.08))
        fan.geometry?.firstMaterial = darkConcrete
        fan.simdPosition = SIMD3<Float>(7.5, 1.04, 9.5)
        root.addChildNode(fan)
        fan.runAction(SCNAction.repeatForever(SCNAction.rotateBy(x: 0, y: CGFloat.pi * 2, z: 0, duration: 1.6)))

        // Treppenhaus-Aufbau mit Tür und Notlicht
        addBox(to: root, size: SIMD3<Float>(4.5, 3.2, 3.5), center: SIMD3<Float>(-1.5, 1.6, 17.5), material: darkConcrete)
        let doorLight = Render.pbr(UIColor(red: 0.3, green: 0.05, blue: 0.04, alpha: 1), roughness: 0.4, metalness: 0,
                                   emission: UIColor(red: 1.0, green: 0.18, blue: 0.12, alpha: 1), emissionIntensity: 2.2)
        addBox(to: root, size: SIMD3<Float>(0.6, 0.18, 0.12), center: SIMD3<Float>(-1.5, 2.75, 15.7), material: doorLight)

        // Antennenmast mit roter Warnleuchte
        addBox(to: root, size: SIMD3<Float>(0.16, 11, 0.16), center: SIMD3<Float>(9.5, 5.5, 16), material: metal)
        addBox(to: root, size: SIMD3<Float>(2.2, 0.08, 0.08), center: SIMD3<Float>(9.5, 8.5, 16), material: metal)
        let beacon = Render.pbr(UIColor(red: 0.4, green: 0.02, blue: 0.02, alpha: 1), roughness: 0.3, metalness: 0,
                                emission: UIColor(red: 1.0, green: 0.05, blue: 0.05, alpha: 1), emissionIntensity: 4)
        let beaconNode = SCNNode(geometry: SCNSphere(radius: 0.16))
        beaconNode.geometry?.firstMaterial = beacon
        beaconNode.simdPosition = SIMD3<Float>(9.5, 11.1, 16)
        root.addChildNode(beaconNode)
        beaconMaterials.append(beacon)

        // Pfützen (spiegeln Riss und Neon)
        let puddleSpots: [SIMD4<Float>] = [
            SIMD4<Float>(1.8, 0, 3.2, 2.6),
            SIMD4<Float>(-2.8, 0, 6.0, 1.8),
            SIMD4<Float>(3.5, 0, 8.5, 3.2),
            SIMD4<Float>(-0.6, 0, 11.0, 2.2)
        ]
        for spot in puddleSpots {
            let plane = SCNPlane(width: CGFloat(spot.w), height: CGFloat(spot.w * 0.62))
            plane.cornerRadius = CGFloat(spot.w * 0.3)
            let node = SCNNode(geometry: plane)
            node.geometry?.firstMaterial = puddle
            node.simdPosition = SIMD3<Float>(spot.x, 0.012, spot.z)
            node.simdEulerAngles = SIMD3<Float>(-Float.pi / 2, 0, randf(-0.6, 0.6))
            root.addChildNode(node)
        }

        // Leuchtende Neon-Leiste an der Brüstungsunterkante (Silhouette gegen den Abgrund)
        let neon = Render.pbr(UIColor(red: 0.25, green: 0.0, blue: 0.03, alpha: 1), roughness: 0.5, metalness: 0,
                              emission: UIColor(red: 0.9, green: 0.04, blue: 0.12, alpha: 1), emissionIntensity: 1.6)
        addBox(to: root, size: SIMD3<Float>(28, 0.07, 0.05), center: SIMD3<Float>(0, -0.25, -1.12), material: neon)
    }

    private func buildHero(darkSuit: Bool) {
        let look: FighterLook = darkSuit ? Roster.heroDarkSuitLook : Roster.def(.silkstrike).look
        let rig = CharacterRig(look: look, quality: quality)
        rig.node.simdPosition = heroFeet
        rig.node.simdEulerAngles = SIMD3<Float>(0, Float.pi + 0.35, 0)   // blickt über die Stadt zum Riss
        rig.play(.perch)
        scene.rootNode.addChildNode(rig.node)
        hero = rig
    }

    private func buildLights() {
        let root = scene.rootNode

        // Kühles Mondlicht von schräg oben hinten
        let moonDir = safeNormalize(SIMD3<Float>(0.35, -0.75, -0.55))
        let moon = Render.makeKeyLight(direction: moonDir,
                                       color: UIColor(red: 0.55, green: 0.65, blue: 1.0, alpha: 1),
                                       intensity: 520,
                                       quality: quality,
                                       shadowExtent: 26)
        root.addChildNode(moon)

        root.addChildNode(Render.makeAmbient(color: UIColor(red: 0.18, green: 0.2, blue: 0.32, alpha: 1), intensity: 140))

        let chest = heroFeet + SIMD3<Float>(0, 0.8, 0)

        // Blutroter Kantenlicht-Spot aus Richtung des Risses
        let rim = Render.makeSpotLight(color: UIColor(red: 1.0, green: 0.12, blue: 0.16, alpha: 1),
                                       intensity: 2600, angle: 42, range: 16, castsShadow: false)
        rim.simdPosition = heroFeet + SIMD3<Float>(-2.2, 3.4, -5.2)
        rim.simdLook(at: chest)
        root.addChildNode(rim)
        riftLight = rim

        // Kaltes Gegenlicht von hinten
        let back = Render.makeSpotLight(color: UIColor(red: 0.45, green: 0.75, blue: 1.0, alpha: 1),
                                        intensity: 1500, angle: 38, range: 14, castsShadow: quality != .performance)
        back.simdPosition = heroFeet + SIMD3<Float>(2.6, 4.2, 4.4)
        back.simdLook(at: chest)
        root.addChildNode(back)

        // Warmer Schein vom Treppenhaus-Notlicht
        let warm = Render.makePointLight(color: UIColor(red: 1.0, green: 0.3, blue: 0.2, alpha: 1), intensity: 320, range: 9)
        warm.simdPosition = SIMD3<Float>(-1.5, 2.6, 15.0)
        root.addChildNode(warm)

        // Blitz (eigenes Richtungslicht, standardmäßig aus)
        let flash = SCNLight()
        flash.type = .directional
        flash.color = UIColor(red: 0.78, green: 0.84, blue: 1.0, alpha: 1)
        flash.intensity = 0
        flash.castsShadow = false
        lightningNode.light = flash
        lightningNode.simdPosition = SIMD3<Float>(0, 50, -40)
        lightningNode.simdLook(at: SIMD3<Float>(0, 0, 0))
        root.addChildNode(lightningNode)
    }

    private func buildRift() {
        let rift = FX.makeRiftSwirl(color: UIColor(red: 0.95, green: 0.06, blue: 0.14, alpha: 1))
        rift.simdPosition = riftPosition
        rift.simdScale = SIMD3<Float>(repeating: 7.5)
        scene.rootNode.addChildNode(rift)
    }

    private func buildCamera() {
        let cam = SCNCamera()
        Render.configureCamera(cam, quality: quality, style: .cinematic)
        cam.fieldOfView = 40
        cam.zNear = 0.05
        cam.zFar = 1600
        if quality == .ultra {
            cam.wantsDepthOfField = true
            cam.fStop = 2.4
            cam.focusDistance = 5
        }
        cameraNode.camera = cam
        cameraNode.name = "titleCamera"
        scene.rootNode.addChildNode(cameraNode)

        let rain = FX.makeRain(intensity: quality == .performance ? 0.6 : 1.0)
        cameraNode.addParticleSystem(rain)
    }

    private func addBox(to parent: SCNNode, size: SIMD3<Float>, center: SIMD3<Float>, material: SCNMaterial) {
        let box = SCNBox(width: CGFloat(size.x), height: CGFloat(size.y), length: CGFloat(size.z), chamferRadius: 0)
        box.firstMaterial = material
        let node = SCNNode(geometry: box)
        node.simdPosition = center
        parent.addChildNode(node)
    }

    // MARK: - GameSceneController

    func update(dt: Float) {
        guard !isTornDown else { return }
        time += dt
        hero?.update(dt: dt)
        updateCamera()
        updateLightning(dt: dt)
        updateBeacons()
    }

    func didAttach(to view: SCNView) {
        view.pointOfView = cameraNode
    }

    func teardown() {
        guard !isTornDown else { return }
        isTornDown = true
        cameraNode.removeAllParticleSystems()
        FX.cleanup(in: scene)
        scene.rootNode.enumerateChildNodes { node, _ in
            node.removeAllActions()
        }
        hero = nil
    }

    // MARK: - Kamera: langsame Kranfahrt + Orbit

    private func updateCamera() {
        let chest = heroFeet + SIMD3<Float>(0, 0.85, 0)

        // Orbit zwischen Über-die-Schulter (Riss sichtbar) und Dreiviertel-Front
        let yaw: Float = Float.pi * 0.5 + sinf(time * 0.045) * 1.15
        let radius: Float = 5.0 + sinf(time * 0.07 + 1.0) * 0.8
        let height: Float = 0.35 + (sinf(time * 0.06) * 0.5 + 0.5) * 1.2
        let orbitPos = chest + SIMD3<Float>(sinf(yaw) * radius, height, cosf(yaw) * radius)

        // Eröffnung: Kran senkt sich in den ersten Sekunden von hoch oben herab
        let intro = smoothRampf(0, 7, time)
        let craneStart = chest + SIMD3<Float>(6, 14, 12)
        let pos = lerp3(craneStart, orbitPos, intro)

        // Blick knapp über den Helden in den Himmel Richtung Riss
        let toRift = safeNormalize(riftPosition - chest)
        let target = chest + SIMD3<Float>(0, 0.55, 0) + toRift * 1.4

        cameraNode.simdPosition = pos
        cameraNode.simdLook(at: target)

        // Leichtes Handkamera-Schwanken
        let sway = SIMD3<Float>(sinf(time * 0.9) * 0.004, sinf(time * 0.63) * 0.006, sinf(time * 0.37) * 0.01)
        cameraNode.simdEulerAngles = cameraNode.simdEulerAngles + sway

        if quality == .ultra, let cam = cameraNode.camera {
            cam.focusDistance = CGFloat(simd_length(chest - pos))
        }
    }

    // MARK: - Blitze & Donner

    private func updateLightning(dt: Float) {
        guard let light = lightningNode.light else { return }

        if lightningAge >= 0 {
            lightningAge += dt
            // Doppelter Blitz: zwei kurze Spitzen
            let a = lightningAge
            var level: Float = 0
            if a < 0.08 {
                level = 1
            } else if a < 0.16 {
                level = 0.15
            } else if a < 0.3 {
                level = 0.85
            } else if a < 0.7 {
                level = 0.85 * (1 - (a - 0.3) / 0.4)
            } else {
                level = 0
                lightningAge = -1
            }
            light.intensity = CGFloat(level * 2400)
        } else {
            lightningCooldown -= dt
            if lightningCooldown <= 0 {
                lightningCooldown = randf(7, 15)
                lightningAge = 0
                lightningNode.simdPosition = SIMD3<Float>(randf(-60, 60), 50, randf(-80, -30))
                lightningNode.simdLook(at: SIMD3<Float>(0, 0, 0))
                thunderDelay = randf(0.5, 1.4)
            }
        }

        if thunderDelay >= 0 {
            thunderDelay -= dt
            if thunderDelay < 0 {
                AudioDirector.shared.play(.thunder, volume: 0.35, pitch: randf(0.85, 1.05))
            }
        }

        // Riss-Licht pulsiert langsam
        if let rim = riftLight?.light {
            let pulse: Float = 0.85 + 0.15 * sinf(time * 1.3) + (lightningAge >= 0 ? 0.25 : 0)
            rim.intensity = CGFloat(2600 * pulse)
        }
    }

    private func updateBeacons() {
        let phase = time.truncatingRemainder(dividingBy: 1.4)
        let on: Bool = phase < 0.18
        let value: CGFloat = on ? 4.0 : 0.15
        for m in beaconMaterials where m.emission.intensity != value {
            m.emission.intensity = value
        }
    }
}
