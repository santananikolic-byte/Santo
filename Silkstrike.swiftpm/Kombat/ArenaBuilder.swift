import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Kampfarenen – gekämpft wird auf der X-Achse bei z = 0,
//  die Kamera steht bei +Z, die Kulisse liegt bei negativem z.
// =====================================================================

struct ArenaSet {
    let root: SCNNode
    let floorY: Float
    let halfWidth: Float
    let cameraDistance: Float
    let music: MusicMood
    let hasRain: Bool
    let accentColor: UIColor
}

enum ArenaBuilder {

    static func build(_ id: ArenaID, quality: QualityPreset, into scene: SCNScene) -> ArenaSet {
        let root = SCNNode()
        root.name = "Arena-\(id.rawValue)"
        scene.rootNode.addChildNode(root)
        scene.physicsWorld.gravity = SCNVector3(0, -14, 0)
        let halfWidth: Float = 8

        // Physik: Boden + unsichtbare Wände für Trümmer
        let floorBody = SCNNode(geometry: SCNBox(width: 60, height: 1, length: 30, chamferRadius: 0))
        floorBody.simdPosition = SIMD3<Float>(0, -0.5, 0)
        floorBody.opacity = 0
        floorBody.physicsBody = SCNPhysicsBody(type: .static, shape: nil)
        floorBody.physicsBody?.friction = 0.9
        root.addChildNode(floorBody)
        for side: Float in [-1, 1] {
            let wall = SCNNode(geometry: SCNBox(width: 1, height: 12, length: 30, chamferRadius: 0))
            wall.simdPosition = SIMD3<Float>(side * (halfWidth + 2.5), 6, 0)
            wall.opacity = 0
            wall.physicsBody = SCNPhysicsBody(type: .static, shape: nil)
            root.addChildNode(wall)
        }
        let back = SCNNode(geometry: SCNBox(width: 60, height: 12, length: 1, chamferRadius: 0))
        back.simdPosition = SIMD3<Float>(0, 6, -4)
        back.opacity = 0
        back.physicsBody = SCNPhysicsBody(type: .static, shape: nil)
        root.addChildNode(back)

        switch id {
        case .rainRooftop:
            return buildRooftop(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        case .subway:
            return buildSubway(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        case .foundry:
            return buildFoundry(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        case .burningSquare:
            return buildSquare(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        case .riftRealm:
            return buildRift(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        case .bloodTower:
            return buildThrone(root: root, scene: scene, quality: quality, halfWidth: halfWidth)
        }
    }

    // MARK: Helfer

    private static func floorSlab(_ root: SCNNode, material: SCNMaterial, width: Float = 40, depth: Float = 24) {
        var b = MeshBuilder()
        b.addBox(min: SIMD3<Float>(-width / 2, -0.4, -depth / 2 - 6), max: SIMD3<Float>(width / 2, 0, depth / 2 - 4), uvScale: 0.25)
        root.addChildNode(b.buildNode(material: material, name: "floor", castsShadow: false))
    }

    private static func lights(_ root: SCNNode, quality: QualityPreset, key: UIColor, keyIntensity: Float,
                               rim: UIColor, rimIntensity: Float, ambient: UIColor, ambientIntensity: Float) {
        let k = Render.makeKeyLight(direction: SIMD3<Float>(-0.35, -1, -0.55), color: key, intensity: keyIntensity,
                                    quality: quality, shadowExtent: 14)
        root.addChildNode(k)
        // Gegenlicht für Silhouetten
        let r1 = Render.makeSpotLight(color: rim, intensity: rimIntensity, angle: 55, range: 40, castsShadow: false)
        r1.simdPosition = SIMD3<Float>(-7, 6, -9)
        r1.simdLook(at: SIMD3<Float>(0, 1, 0))
        root.addChildNode(r1)
        let r2 = Render.makeSpotLight(color: rim, intensity: rimIntensity, angle: 55, range: 40, castsShadow: false)
        r2.simdPosition = SIMD3<Float>(7, 6, -9)
        r2.simdLook(at: SIMD3<Float>(0, 1, 0))
        root.addChildNode(r2)
        root.addChildNode(Render.makeAmbient(color: ambient, intensity: ambientIntensity))
    }

    private static func flicker(_ node: SCNNode, base: CGFloat) {
        guard let l = node.light else { return }
        let seq = SCNAction.repeatForever(SCNAction.sequence([
            SCNAction.customAction(duration: 0.12) { n, _ in n.light?.intensity = base * CGFloat.random(in: 0.55...1.15) },
            SCNAction.wait(duration: 0.05, withRange: 0.2)
        ]))
        l.intensity = base
        node.runAction(seq)
    }

    // MARK: Dach im Regen

    private static func buildRooftop(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .stormNight, quality: quality, fogStart: 30, fogEnd: 380)
        let wet = Render.texturedPBR(diffuse: ProceduralTextures.concrete(), normal: ProceduralTextures.asphaltNormal(),
                                     roughness: 0.12, metalness: 0.15, tileScale: 1)
        floorSlab(root, material: wet)
        let skyline = CityBuilder.buildBackdrop(seed: 0xAC1D, quality: quality, timeOfDay: .stormNight, clearRadius: 25)
        root.addChildNode(skyline)
        var m = MeshBuilder()
        // Brüstung, Lüftungsanlagen, Wassertank
        m.addBox(min: SIMD3<Float>(-20, 0, -10.5), max: SIMD3<Float>(20, 1.1, -10), uvScale: 0.3)
        m.addBox(min: SIMD3<Float>(-9, 0, -8), max: SIMD3<Float>(-6, 1.6, -6), uvScale: 0.3)
        m.addBox(min: SIMD3<Float>(5, 0, -9), max: SIMD3<Float>(9, 2.2, -6.5), uvScale: 0.3)
        m.addCylinder(center: SIMD3<Float>(13, 2.5, -8), radius: 2.4, height: 4, segments: 16)
        for k in 0..<4 {
            let x: Float = k % 2 == 0 ? 11.4 : 14.6
            let z: Float = k < 2 ? -9.6 : -6.4
            m.addBox(min: SIMD3<Float>(x - 0.15, 0, z - 0.15), max: SIMD3<Float>(x + 0.15, 2.5, z + 0.15), uvScale: 0.3)
        }
        root.addChildNode(m.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.35, metalness: 0.7), name: "props"))
        // Leuchtschrift NEO-HAVEN
        var sign = MeshBuilder()
        let letters: Float = 9
        for k in 0..<Int(letters) {
            let x = -8 + Float(k) * 2
            sign.addBox(min: SIMD3<Float>(x, 5, -11), max: SIMD3<Float>(x + 1.4, 7.4, -10.8), uvScale: 1)
        }
        let neon = Render.emissive(UIColor(red: 1, green: 0.08, blue: 0.35, alpha: 1), intensity: 3.2)
        root.addChildNode(sign.buildNode(material: neon, name: "neonSign", castsShadow: false))
        var frame = MeshBuilder()
        frame.addBox(min: SIMD3<Float>(-8.5, 0, -11.2), max: SIMD3<Float>(-8.2, 5, -10.9), uvScale: 0.3)
        frame.addBox(min: SIMD3<Float>(9.2, 0, -11.2), max: SIMD3<Float>(9.5, 5, -10.9), uvScale: 0.3)
        root.addChildNode(frame.buildNode(material: Render.pbr(UIColor(white: 0.2, alpha: 1), roughness: 0.4, metalness: 0.8)))
        let neonLight = Render.makePointLight(color: UIColor(red: 1, green: 0.1, blue: 0.4, alpha: 1), intensity: 900, range: 22)
        neonLight.simdPosition = SIMD3<Float>(0, 6, -9)
        root.addChildNode(neonLight)
        flicker(neonLight, base: 900)
        lights(root, quality: quality, key: UIColor(red: 0.6, green: 0.7, blue: 1, alpha: 1), keyIntensity: 700,
               rim: UIColor(red: 0.5, green: 0.75, blue: 1, alpha: 1), rimIntensity: 2200,
               ambient: UIColor(red: 0.25, green: 0.3, blue: 0.45, alpha: 1), ambientIntensity: 160)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 7.0, music: .combat,
                        hasRain: true, accentColor: UIColor(red: 1, green: 0.1, blue: 0.4, alpha: 1))
    }

    // MARK: U-Bahn

    private static func buildSubway(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .night, quality: quality, fogStart: 12, fogEnd: 70,
                                fogColor: UIColor(red: 0.02, green: 0.03, blue: 0.03, alpha: 1))
        scene.background.contents = UIColor.black
        let tiles = Render.texturedPBR(diffuse: ProceduralTextures.tiles(), roughness: 0.3, metalness: 0, tileScale: 1)
        floorSlab(root, material: tiles)
        var walls = MeshBuilder()
        walls.addBox(min: SIMD3<Float>(-30, 0, -14), max: SIMD3<Float>(30, 8, -13.5), uvScale: 0.25)
        walls.addBox(min: SIMD3<Float>(-30, 7.5, -14), max: SIMD3<Float>(30, 8, 4), uvScale: 0.25)
        for k in 0..<7 {
            let x = -18 + Float(k) * 6
            walls.addBox(min: SIMD3<Float>(x - 0.4, 0, -6), max: SIMD3<Float>(x + 0.4, 7.5, -5.2), uvScale: 0.25)
        }
        root.addChildNode(walls.buildNode(material: tiles, name: "walls"))
        // Gleisbett + Zugwrack
        var track = MeshBuilder()
        track.addBox(min: SIMD3<Float>(-30, -1.2, -12.5), max: SIMD3<Float>(30, -1.0, -7), uvScale: 0.3)
        for r: Float in [-11, -8.5] {
            track.addBox(min: SIMD3<Float>(-30, -1.0, r - 0.08), max: SIMD3<Float>(30, -0.85, r + 0.08), uvScale: 0.3)
        }
        root.addChildNode(track.buildNode(material: Render.pbr(UIColor(white: 0.3, alpha: 1), roughness: 0.3, metalness: 0.9), name: "tracks"))
        var train = MeshBuilder()
        train.addBox(min: SIMD3<Float>(-4, -0.9, -12.3), max: SIMD3<Float>(16, 3.2, -7.4), uvScale: 0.2)
        root.addChildNode(train.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.4, metalness: 0.8), name: "train"))
        var windows = MeshBuilder()
        for k in 0..<5 {
            let x = -2.5 + Float(k) * 3.6
            windows.addBox(min: SIMD3<Float>(x, 1.2, -7.38), max: SIMD3<Float>(x + 2.2, 2.4, -7.3), uvScale: 1)
        }
        root.addChildNode(windows.buildNode(material: Render.emissive(UIColor(red: 0.7, green: 0.9, blue: 1, alpha: 1), intensity: 1.4), name: "trainWindows", castsShadow: false))
        // Neonröhren
        var tubes = MeshBuilder()
        for k in 0..<5 {
            let x = -14 + Float(k) * 7
            tubes.addBox(min: SIMD3<Float>(x - 1.2, 7.3, -3.1), max: SIMD3<Float>(x + 1.2, 7.42, -2.9), uvScale: 1)
            let l = Render.makePointLight(color: UIColor(red: 0.75, green: 0.95, blue: 0.9, alpha: 1), intensity: 700, range: 14)
            l.simdPosition = SIMD3<Float>(x, 7, -3)
            root.addChildNode(l)
            if k == 1 || k == 3 { flicker(l, base: 700) }
        }
        root.addChildNode(tubes.buildNode(material: Render.emissive(UIColor(red: 0.8, green: 1, blue: 0.95, alpha: 1), intensity: 5), name: "tubes", castsShadow: false))
        lights(root, quality: quality, key: UIColor(red: 0.7, green: 0.9, blue: 0.85, alpha: 1), keyIntensity: 300,
               rim: UIColor(red: 0.2, green: 0.9, blue: 0.7, alpha: 1), rimIntensity: 1800,
               ambient: UIColor(red: 0.2, green: 0.25, blue: 0.25, alpha: 1), ambientIntensity: 120)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 6.6, music: .combat,
                        hasRain: false, accentColor: UIColor(red: 0.3, green: 1, blue: 0.8, alpha: 1))
    }

    // MARK: Gießerei

    private static func buildFoundry(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .stormNight, quality: quality, fogStart: 15, fogEnd: 90,
                                fogColor: UIColor(red: 0.12, green: 0.05, blue: 0.02, alpha: 1))
        let metal = Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.55, metalness: 0.8, tileScale: 1)
        floorSlab(root, material: metal)
        let molten = Render.emissive(UIColor(red: 1, green: 0.42, blue: 0.08, alpha: 1), intensity: 4)
        var pools = MeshBuilder()
        pools.addBox(min: SIMD3<Float>(-24, -0.3, -12), max: SIMD3<Float>(24, 0.05, -8), uvScale: 0.2)
        root.addChildNode(pools.buildNode(material: molten, name: "molten", castsShadow: false))
        var structure = MeshBuilder()
        for k in 0..<6 {
            let x = -20 + Float(k) * 8
            structure.addBox(min: SIMD3<Float>(x - 0.5, 0, -14), max: SIMD3<Float>(x + 0.5, 14, -13), uvScale: 0.3)
            structure.addCylinder(center: SIMD3<Float>(x + 3, 0, -16), radius: 2.2, height: 4 + Float(k % 3) * 2, segments: 14)
        }
        structure.addBox(min: SIMD3<Float>(-24, 13, -14), max: SIMD3<Float>(24, 14, 2), uvScale: 0.2)
        root.addChildNode(structure.buildNode(material: metal, name: "structure"))
        // Ketten
        var chains = MeshBuilder()
        for k in 0..<8 {
            let x = -14 + Float(k) * 4
            chains.addCylinder(center: SIMD3<Float>(x, 6 + Float(k % 3), -5), radius: 0.05, height: 8, segments: 5)
        }
        root.addChildNode(chains.buildNode(material: Render.pbr(UIColor(white: 0.25, alpha: 1), roughness: 0.4, metalness: 0.9), name: "chains"))
        for k in 0..<3 {
            let l = Render.makePointLight(color: UIColor(red: 1, green: 0.45, blue: 0.12, alpha: 1), intensity: 1800, range: 22)
            l.simdPosition = SIMD3<Float>(-12 + Float(k) * 12, 1.2, -9)
            root.addChildNode(l)
            flicker(l, base: 1800)
        }
        let embers = FX.makeEmbersAmbient()
        let emberNode = SCNNode()
        emberNode.simdPosition = SIMD3<Float>(0, 0, -6)
        emberNode.addParticleSystem(embers)
        root.addChildNode(emberNode)
        lights(root, quality: quality, key: UIColor(red: 1, green: 0.7, blue: 0.5, alpha: 1), keyIntensity: 450,
               rim: UIColor(red: 1, green: 0.5, blue: 0.15, alpha: 1), rimIntensity: 2600,
               ambient: UIColor(red: 0.35, green: 0.2, blue: 0.12, alpha: 1), ambientIntensity: 130)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 7.0, music: .combat,
                        hasRain: false, accentColor: UIColor(red: 1, green: 0.5, blue: 0.1, alpha: 1))
    }

    // MARK: Brennender Domplatz

    private static func buildSquare(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .night, quality: quality, fogStart: 25, fogEnd: 160,
                                fogColor: UIColor(red: 0.15, green: 0.06, blue: 0.03, alpha: 1))
        let cobble = Render.texturedPBR(diffuse: ProceduralTextures.brick(), normal: ProceduralTextures.asphaltNormal(),
                                        roughness: 0.6, metalness: 0, tileScale: 1)
        cobble.diffuse.contentsTransform = SCNMatrix4MakeScale(2, 2, 1)
        floorSlab(root, material: cobble)
        let stone = Render.pbr(UIColor(red: 0.33, green: 0.31, blue: 0.3, alpha: 1), roughness: 0.85, metalness: 0)
        var dom = MeshBuilder()
        dom.addBox(min: SIMD3<Float>(-14, 0, -26), max: SIMD3<Float>(14, 24, -20), uvScale: 0.2)
        for side: Float in [-1, 1] {
            dom.addBox(min: SIMD3<Float>(side * 11 - 4, 0, -27), max: SIMD3<Float>(side * 11 + 4, 46, -19), uvScale: 0.2)
            dom.addCone(center: SIMD3<Float>(side * 11, 46, -23), radius: 5, height: 22, segments: 4)
        }
        root.addChildNode(dom.buildNode(material: stone, name: "dom"))
        let rose = SCNNode(geometry: SCNCylinder(radius: 4, height: 0.2))
        rose.geometry?.firstMaterial = Render.emissive(UIColor(red: 1, green: 0.5, blue: 0.2, alpha: 1), intensity: 3)
        rose.simdEulerAngles = SIMD3<Float>(Float.pi / 2, 0, 0)
        rose.simdPosition = SIMD3<Float>(0, 15, -19.85)
        root.addChildNode(rose)
        // Brennende Trümmer
        var debris = MeshBuilder()
        let spots: [SIMD3<Float>] = [SIMD3<Float>(-10, 0, -7), SIMD3<Float>(9, 0, -8), SIMD3<Float>(-3, 0, -12), SIMD3<Float>(14, 0, -4)]
        for p in spots {
            debris.addBox(min: p + SIMD3<Float>(-1.5, 0, -1), max: p + SIMD3<Float>(1.5, 0.8, 1), uvScale: 0.4)
            let fire = SCNNode()
            fire.simdPosition = p + SIMD3<Float>(0, 0.8, 0)
            fire.addParticleSystem(FX.makeEmbersAmbient())
            root.addChildNode(fire)
            let l = Render.makePointLight(color: UIColor(red: 1, green: 0.45, blue: 0.1, alpha: 1), intensity: 1600, range: 16)
            l.simdPosition = p + SIMD3<Float>(0, 1.5, 0)
            root.addChildNode(l)
            flicker(l, base: 1600)
        }
        root.addChildNode(debris.buildNode(material: Render.pbr(UIColor(white: 0.06, alpha: 1), roughness: 0.9, metalness: 0,
                                                                emission: UIColor(red: 0.6, green: 0.15, blue: 0.02, alpha: 1), emissionIntensity: 1), name: "debris"))
        lights(root, quality: quality, key: UIColor(red: 1, green: 0.6, blue: 0.35, alpha: 1), keyIntensity: 500,
               rim: UIColor(red: 1, green: 0.4, blue: 0.1, alpha: 1), rimIntensity: 2400,
               ambient: UIColor(red: 0.3, green: 0.15, blue: 0.1, alpha: 1), ambientIntensity: 140)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 7.2, music: .combat,
                        hasRain: false, accentColor: UIColor(red: 1, green: 0.45, blue: 0.1, alpha: 1))
    }

    // MARK: Riss-Dimension

    private static func buildRift(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .stormNight, quality: quality, fogStart: 20, fogEnd: 220,
                                fogColor: UIColor(red: 0.12, green: 0.02, blue: 0.1, alpha: 1))
        scene.background.contents = UIColor(red: 0.06, green: 0.0, blue: 0.05, alpha: 1)
        let rock = Render.texturedPBR(diffuse: ProceduralTextures.concrete(), normal: ProceduralTextures.asphaltNormal(),
                                      roughness: 0.7, metalness: 0.1, tileScale: 1)
        rock.diffuse.contents = UIColor(red: 0.12, green: 0.08, blue: 0.12, alpha: 1)
        var island = MeshBuilder()
        island.addBox(min: SIMD3<Float>(-14, -0.4, -9), max: SIMD3<Float>(14, 0, 4), uvScale: 0.2)
        island.addBox(min: SIMD3<Float>(-11, -4, -8), max: SIMD3<Float>(11, -0.4, 3), uvScale: 0.2)
        island.addBox(min: SIMD3<Float>(-7, -8, -6), max: SIMD3<Float>(7, -4, 1), uvScale: 0.2)
        root.addChildNode(island.buildNode(material: rock, name: "island"))
        // Leuchtende Risse im Boden
        var cracks = MeshBuilder()
        for k in 0..<9 {
            let x = -12 + Float(k) * 3
            cracks.addBox(min: SIMD3<Float>(x, 0.0, -3 + Float(k % 3)), max: SIMD3<Float>(x + 2.4, 0.02, -2.85 + Float(k % 3)), uvScale: 1)
        }
        root.addChildNode(cracks.buildNode(material: Render.emissive(UIColor(red: 0.9, green: 0.1, blue: 0.6, alpha: 1), intensity: 4), name: "cracks", castsShadow: false))
        // Schwebende Felsen
        var floating = MeshBuilder()
        var rng = SeededRandom(seed: 0x21F7)
        for _ in 0..<(quality == .performance ? 10 : 22) {
            let c = SIMD3<Float>(rng.float(-60, 60), rng.float(-5, 30), rng.float(-80, -18))
            let s = rng.float(1.5, 6)
            floating.addBox(min: c - SIMD3<Float>(s, s * 0.5, s), max: c + SIMD3<Float>(s, s * 0.5, s), uvScale: 0.2)
            floating.addBox(min: c - SIMD3<Float>(s * 0.6, s * 1.2, s * 0.6), max: c + SIMD3<Float>(s * 0.6, -s * 0.5, s * 0.6), uvScale: 0.2)
        }
        let floatNode = floating.buildNode(material: rock, name: "floating", castsShadow: false)
        floatNode.runAction(SCNAction.repeatForever(SCNAction.sequence([
            SCNAction.moveBy(x: 0, y: 1.2, z: 0, duration: 4),
            SCNAction.moveBy(x: 0, y: -1.2, z: 0, duration: 4)
        ])))
        root.addChildNode(floatNode)
        let swirl = FX.makeRiftSwirl(color: UIColor(red: 0.85, green: 0.1, blue: 0.7, alpha: 1))
        swirl.simdPosition = SIMD3<Float>(0, 22, -60)
        swirl.simdScale = SIMD3<Float>(repeating: 12)
        root.addChildNode(swirl)
        let ash = SCNNode()
        ash.simdPosition = SIMD3<Float>(0, 4, -4)
        ash.addParticleSystem(FX.makeAshAmbient())
        root.addChildNode(ash)
        lights(root, quality: quality, key: UIColor(red: 0.8, green: 0.5, blue: 1, alpha: 1), keyIntensity: 550,
               rim: UIColor(red: 1, green: 0.2, blue: 0.8, alpha: 1), rimIntensity: 2800,
               ambient: UIColor(red: 0.3, green: 0.15, blue: 0.3, alpha: 1), ambientIntensity: 150)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 7.0, music: .boss,
                        hasRain: false, accentColor: UIColor(red: 0.9, green: 0.15, blue: 0.75, alpha: 1))
    }

    // MARK: Thron des Blutturms

    private static func buildThrone(root: SCNNode, scene: SCNScene, quality: QualityPreset, halfWidth: Float) -> ArenaSet {
        Render.applyEnvironment(to: scene, timeOfDay: .stormNight, quality: quality, fogStart: 30, fogEnd: 300,
                                fogColor: UIColor(red: 0.1, green: 0.01, blue: 0.02, alpha: 1))
        let obsidian = Render.texturedPBR(diffuse: ProceduralTextures.tiles(), roughness: 0.08, metalness: 0.4, tileScale: 1)
        obsidian.diffuse.contents = UIColor(red: 0.04, green: 0.02, blue: 0.03, alpha: 1)
        floorSlab(root, material: obsidian)
        var channels = MeshBuilder()
        for k in 0..<8 {
            let x = -14 + Float(k) * 4
            channels.addBox(min: SIMD3<Float>(x - 0.12, 0.0, -14), max: SIMD3<Float>(x + 0.12, 0.02, 3), uvScale: 1)
        }
        channels.addBox(min: SIMD3<Float>(-20, 0.0, -1.2), max: SIMD3<Float>(20, 0.02, -0.95), uvScale: 1)
        root.addChildNode(channels.buildNode(material: Render.emissive(UIColor(red: 0.9, green: 0.02, blue: 0.05, alpha: 1), intensity: 3), name: "bloodChannels", castsShadow: false))
        let iron = Render.pbr(UIColor(red: 0.07, green: 0.05, blue: 0.05, alpha: 1), roughness: 0.35, metalness: 0.85)
        var hall = MeshBuilder()
        for k in 0..<6 {
            let x = -15 + Float(k) * 6
            hall.addBox(min: SIMD3<Float>(x - 0.9, 0, -10), max: SIMD3<Float>(x + 0.9, 16, -8.2), uvScale: 0.2)
            hall.addCone(center: SIMD3<Float>(x, 16, -9.1), radius: 1.3, height: 3, segments: 4)
        }
        // Thron
        hall.addBox(min: SIMD3<Float>(-3, 0, -16), max: SIMD3<Float>(3, 1.5, -12), uvScale: 0.3)
        hall.addBox(min: SIMD3<Float>(-1.8, 1.5, -15.8), max: SIMD3<Float>(1.8, 3, -13.6), uvScale: 0.3)
        hall.addBox(min: SIMD3<Float>(-2, 1.5, -16), max: SIMD3<Float>(2, 9, -15.4), uvScale: 0.3)
        for k in 0..<5 {
            let x = -1.6 + Float(k) * 0.8
            hall.addCone(center: SIMD3<Float>(x, 9, -15.7), radius: 0.3, height: 2.5 + Float(k % 2), segments: 4)
        }
        root.addChildNode(hall.buildNode(material: iron, name: "hall"))
        let skyline = CityBuilder.buildBackdrop(seed: 0xB100D, quality: quality, timeOfDay: .stormNight, clearRadius: 60)
        skyline.simdPosition = SIMD3<Float>(0, -220, 0)
        root.addChildNode(skyline)
        let swirl = FX.makeRiftSwirl(color: UIColor(red: 1, green: 0.03, blue: 0.08, alpha: 1))
        swirl.simdPosition = SIMD3<Float>(0, 35, -70)
        swirl.simdScale = SIMD3<Float>(repeating: 14)
        root.addChildNode(swirl)
        for x: Float in [-9, 9] {
            let l = Render.makePointLight(color: UIColor(red: 1, green: 0.08, blue: 0.08, alpha: 1), intensity: 2000, range: 24)
            l.simdPosition = SIMD3<Float>(x, 5, -7)
            root.addChildNode(l)
            flicker(l, base: 2000)
        }
        lights(root, quality: quality, key: UIColor(red: 1, green: 0.55, blue: 0.5, alpha: 1), keyIntensity: 500,
               rim: UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), rimIntensity: 3000,
               ambient: UIColor(red: 0.3, green: 0.1, blue: 0.1, alpha: 1), ambientIntensity: 140)
        return ArenaSet(root: root, floorY: 0, halfWidth: halfWidth, cameraDistance: 7.4, music: .boss,
                        hasRain: true, accentColor: UIColor(red: 1, green: 0.05, blue: 0.1, alpha: 1))
    }
}
