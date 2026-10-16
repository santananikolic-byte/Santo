import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Offene Welt: Schwingen, Wandlauf, Netz-Zip, Straßenkämpfe, Ziele
// =====================================================================

final class OpenWorldController: GameSceneController {

    let scene = SCNScene()
    var cameraNode: SCNNode { return cam.node }

    var onReachObjective: (() -> Void)?
    var onHeroDefeated: (() -> Void)?

    private enum HeroMove {
        case grounded
        case air
        case swing
        case wall
        case zip
    }

    private let context: WorldContext
    private let settings: GameSettings
    private let input: InputState
    private let hud: WorldHUD
    private let city: City
    private let cam: WorldCamera
    private let hero: CharacterRig
    private let thugs: ThugManager
    private let strand = WebStrand(color: UIColor(white: 0.95, alpha: 1), radius: 0.014)
    private let keyLight: SCNNode

    // Held
    private var pos = SIMD3<Float>(0, 0, 0)
    private var vel = SIMD3<Float>(0, 0, 0)
    private var facingYaw: Float = 0
    private var move: HeroMove = .grounded
    private var health: Float = 1
    private var anchor = SIMD3<Float>(0, 0, 0)
    private var ropeLength: Float = 20
    private var swingTime: Float = 0
    private var wallNormal = SIMD3<Float>(0, 0, 1)
    private var zipTarget = SIMD3<Float>(0, 0, 0)
    private var hitStop: Float = 0
    private var attackCooldown: Float = 0
    private var comboCount = 0
    private var comboTimer: Float = 0
    private var attackFlip = false
    private var lastHurt: Float = 10
    private var defeatedFired = false

    // Ziel
    private var objectiveNode: SCNNode?
    private var objectivePos: SIMD3<Float>?
    private var objectiveFired = false
    private var musicMood: MusicMood = .none

    // Sammelobjekte
    private var crystals: [(node: SCNNode, index: Int)] = []
    private var collected: Set<Int>
    private static let collectedKey = "silkstrike.collected.v1"

    private var toastTimer: Float = 0
    private var time: Float = 0

    init(context: WorldContext, settings: GameSettings, input: InputState, hud: WorldHUD) {
        self.context = context
        self.settings = settings
        self.input = input
        self.hud = hud
        let tod = context.chapter?.timeOfDay ?? context.timeOfDay
        FX.quality = settings.quality
        FX.bloodEnabled = settings.bloodEnabled

        city = CityBuilder.build(seed: 2077, quality: settings.quality, timeOfDay: tod)
        scene.rootNode.addChildNode(city.root)
        city.setBloodTowerActive(context.chapter?.objective == .bloodTower)

        Render.applyEnvironment(to: scene, timeOfDay: tod, quality: settings.quality, fogStart: 140, fogEnd: 950)
        let moon = UIColor(red: 0.62, green: 0.7, blue: 0.95, alpha: 1)
        let duskSun = UIColor(red: 1, green: 0.62, blue: 0.4, alpha: 1)
        keyLight = Render.makeKeyLight(direction: SIMD3<Float>(-0.45, -1, -0.35), color: tod == .dusk ? duskSun : moon,
                                       intensity: tod == .dusk ? 1100 : 650, quality: settings.quality, shadowExtent: 70)
        scene.rootNode.addChildNode(keyLight)
        scene.rootNode.addChildNode(Render.makeAmbient(color: UIColor(red: 0.35, green: 0.38, blue: 0.5, alpha: 1), intensity: 180))

        cam = WorldCamera(quality: settings.quality, settings: settings, timeOfDay: tod)
        scene.rootNode.addChildNode(cam.node)

        let look: FighterLook = context.heroDarkSuit ? Roster.heroDarkSuitLook : Roster.def(.silkstrike).look
        hero = CharacterRig(look: look, quality: settings.quality)
        scene.rootNode.addChildNode(hero.node)
        scene.rootNode.addChildNode(strand.node)
        strand.isHidden = true

        thugs = ThugManager(scene: scene, city: city, quality: settings.quality, bloodEnabled: settings.bloodEnabled)

        if let arr = UserDefaults.standard.array(forKey: OpenWorldController.collectedKey) as? [Int] {
            collected = Set(arr)
        } else {
            collected = []
        }
        buildCrystals()
        buildObjective()
        respawn()

        hud.objective = context.chapter?.objectiveText ?? "Freies Schwingen – sammle Blutsiegel und stoppe die Kultisten"
        hud.collectiblesTotal = city.collectiblePositions.count
        hud.collectibles = collected.count
        hud.toast = context.chapter.map { "KAPITEL \($0.number): \($0.title.uppercased())" }
        toastTimer = 3.5
        AudioDirector.shared.setMusic(.roam)
        musicMood = .roam
    }

    // MARK: GameSceneController

    func didAttach(to view: SCNView) {
        let h = Swift.max(1, view.bounds.height)
        cam.setViewAspect(Float(view.bounds.width / h))
    }

    func teardown() {
        AudioDirector.shared.stopSpeech()
        thugs.removeAll()
        cam.teardown()
        FX.cleanup(in: scene)
        scene.rootNode.childNodes.forEach { $0.removeAllActions() }
        onReachObjective = nil
        onHeroDefeated = nil
    }

    func respawn() {
        let spawn = city.landmarks[context.spawnAt] ?? city.landmarks[.heroApartment] ?? SIMD3<Float>(0, 40, 0)
        pos = spawn + SIMD3<Float>(0, 0.1, 0)
        vel = .zero
        move = .air
        health = 1
        defeatedFired = false
        strand.isHidden = true
        if let target = objectivePos {
            facingYaw = yawOfDirection(safeNormalize(flatten(target - pos)))
        }
        cam.snap(target: pos + SIMD3<Float>(0, 1.4, 0), yaw: facingYaw)
        hero.play(.idle, restart: true)
    }

    func update(dt rawDt: Float) {
        time += rawDt
        if hitStop > 0 {
            hitStop -= rawDt
            hero.update(dt: rawDt * 0.05)
            return
        }
        let dt = rawDt
        handleInput(dt: dt)
        simulate(dt: dt)
        updateCombat(dt: dt)
        updatePresentation(dt: dt)
        updateObjective()
        updateCrystals()
        updateHUD(dt: dt)
        city.update(dt: dt, cameraPosition: cam.position)
    }

    // MARK: Eingabe

    private func moveDirection() -> SIMD3<Float> {
        let fwd = cam.flatForward
        let right = simd_cross(fwd, SIMD3<Float>(0, 1, 0))
        let m = input.move
        return right * m.x + fwd * m.y
    }

    private func handleInput(dt: Float) {
        if input.consumePress(.jump) {
            switch move {
            case .grounded:
                vel.y = 13
                move = .air
                hero.play(.jump, restart: true)
                AudioDirector.shared.play(.whoosh, volume: 0.5)
            case .swing:
                releaseSwing(boost: true)
                vel.y += 7
                hero.play(.jump, restart: true)
            case .wall:
                vel = wallNormal * 12 + SIMD3<Float>(0, 11, 0)
                move = .air
                hero.play(.jump, restart: true)
                AudioDirector.shared.play(.whoosh, volume: 0.6)
            case .air, .zip:
                break
            }
        }
        if input.consumePress(.web) && move != .swing {
            startSwing()
        }
        if move == .swing && !input.isDown(.web) {
            releaseSwing(boost: true)
        }
        if input.consumePress(.zip) {
            startZip()
        }
        if input.consumePress(.attack) {
            heroAttack()
        }
        if input.consumePress(.interact), let target = objectivePos, simd_length(target - pos) < 14 {
            fireObjective()
        }
    }

    private func startSwing() {
        let aim = cam.flatForward + SIMD3<Float>(0, 0.2, 0)
        guard let a = city.findSwingAnchor(from: pos + SIMD3<Float>(0, 1.5, 0), velocity: vel, aim: aim) else {
            AudioDirector.shared.play(.uiBack, volume: 0.4)
            return
        }
        anchor = a
        ropeLength = Swift.max(8, simd_length(a - pos) * 0.92)
        move = .swing
        swingTime = 0
        strand.isHidden = false
        hero.play(.swing)
        AudioDirector.shared.play(.webShoot)
        Haptics.light()
        if vel.y < -4 { vel.y *= 0.6 }
    }

    private func releaseSwing(boost: Bool) {
        guard move == .swing else { return }
        move = .air
        strand.isHidden = true
        if boost {
            let hv = safeNormalize(flatten(vel), fallback: cam.flatForward)
            vel += hv * 4 + SIMD3<Float>(0, 5, 0)
        }
        AudioDirector.shared.play(.swingRelease, volume: 0.7)
        hero.play(vel.y > 0 ? .jump : .fall, restart: true)
    }

    private func startZip() {
        let from = cam.position
        guard let hit = city.raycast(from: from, direction: cam.forward, maxDistance: 140) else { return }
        guard simd_length(hit - pos) > 4 else { return }
        if move == .swing { releaseSwing(boost: false) }
        zipTarget = hit
        move = .zip
        strand.isHidden = false
        hero.play(.zip, restart: true)
        AudioDirector.shared.play(.webZip)
        cam.kickFOV(8)
        Haptics.medium()
    }

    // MARK: Simulation

    private func simulate(dt: Float) {
        let dir = moveDirection()
        let gravity: Float = -24
        switch move {
        case .grounded:
            let m = simd_length(input.move)
            let speed: Float = m > 0.92 ? 15 : 9
            let desired = dir * speed
            vel.x = damp(vel.x, desired.x, lambda: 10, dt: dt)
            vel.z = damp(vel.z, desired.z, lambda: 10, dt: dt)
            vel.y = 0
            if m > 0.1 {
                facingYaw = dampAngle(facingYaw, yawOfDirection(dir), lambda: 12, dt: dt)
            }
        case .air:
            vel.y += gravity * dt
            vel += dir * 9 * dt
            let hs = horizontalLength(vel)
            if hs > 1 {
                facingYaw = dampAngle(facingYaw, atan2f(vel.x, vel.z), lambda: 4, dt: dt)
            }
        case .swing:
            swingTime += dt
            vel.y += gravity * dt
            let pump = dir * 13 + cam.flatForward * 4
            vel += pump * dt
            ropeLength = Swift.max(8, ropeLength - 1.5 * dt)
            if horizontalLength(vel) > 1 {
                facingYaw = dampAngle(facingYaw, atan2f(vel.x, vel.z), lambda: 6, dt: dt)
            }
        case .wall:
            let up: Float = input.move.y < -0.5 ? -4 : 11
            let lateral = dir - wallNormal * simd_dot(dir, wallNormal)
            vel = SIMD3<Float>(lateral.x * 6, up, lateral.z * 6) - wallNormal * 2
            facingYaw = yawOfDirection(-wallNormal)
        case .zip:
            let to = zipTarget - pos
            let d = simd_length(to)
            if d < 1.6 {
                arriveZip()
            } else {
                vel = to / d * 48
            }
        }
        // Tempolimit
        let sp = simd_length(vel)
        if sp > 58 { vel *= 58 / sp }

        // Integration in kleinen Schritten (verhindert Durchtunneln)
        let steps = Swift.max(1, Swift.min(8, Int(ceil(sp * dt / 0.45))))
        let h = dt / Float(steps)
        var landedHard = false
        let fallSpeed = vel.y
        var touchedGround = false
        var touchedWall = false
        var wallN = SIMD3<Float>(0, 0, 0)
        for _ in 0..<steps {
            pos += vel * h
            if move == .swing {
                let d = pos - anchor
                let len = simd_length(d)
                if len > ropeLength && len > 0.001 {
                    let radial = d / len
                    pos = anchor + radial * ropeLength
                    let vr = simd_dot(vel, radial)
                    if vr > 0 { vel -= radial * vr }
                }
            }
            let info = city.resolveCollision(position: &pos, velocity: &vel, radius: 0.45, height: 1.8)
            if info.hitGround { touchedGround = true }
            if info.hitWall {
                touchedWall = true
                wallN = info.wallNormal
            }
        }
        // Zustandswechsel nach Kollision
        switch move {
        case .air, .swing:
            if touchedGround && vel.y <= 0.1 {
                if move == .swing { releaseSwing(boost: false) }
                landedHard = fallSpeed < -18
                move = .grounded
                hero.play(landedHard ? .land : .idle, restart: true)
                if landedHard {
                    FX.spawn(.dust, at: pos, in: scene, scale: 1.2)
                    cam.addShake(0.35)
                    AudioDirector.shared.play(.land)
                    Haptics.medium()
                }
            } else if touchedWall {
                let into = simd_dot(safeNormalize(flatten(vel)), -wallN)
                let pushing = simd_dot(dir, -wallN) > 0.3
                if into > 0.3 || pushing {
                    if move == .swing { releaseSwing(boost: false) }
                    move = .wall
                    wallNormal = wallN
                    hero.play(.wallRun)
                }
            }
            if move == .swing && pos.y > anchor.y - 1.5 {
                releaseSwing(boost: true)
            }
        case .wall:
            // Noch an der Wand? Kurz in die Wand drücken und prüfen.
            var probe = pos - wallNormal * 0.25
            var pv = SIMD3<Float>(0, 0, 0)
            let info = city.resolveCollision(position: &probe, velocity: &pv, radius: 0.45, height: 1.8)
            if !info.hitWall || info.onRoof {
                // Dachkante erreicht → hochschwingen
                vel = -wallNormal * 5 + SIMD3<Float>(0, 8, 0)
                move = .air
                hero.play(.jump, restart: true)
            } else if touchedGround && input.move.y < -0.5 {
                move = .grounded
            }
        case .grounded:
            if !touchedGround {
                let below = city.surfaceHeight(at: pos)
                if pos.y - below > 0.35 {
                    move = .air
                    hero.play(.fall)
                }
            }
        case .zip:
            break
        }
        // Absturz aus der Welt verhindern
        if pos.y < -5 || !pos.x.isFinite || !pos.z.isFinite {
            respawn()
        }
    }

    private func arriveZip() {
        strand.isHidden = true
        let top = city.surfaceHeight(at: zipTarget + SIMD3<Float>(0, 3, 0))
        if abs(top - zipTarget.y) < 2.5 {
            pos.y = top
            vel = .zero
            move = .grounded
            hero.play(.land, restart: true)
        } else {
            let d = safeNormalize(flatten(zipTarget - pos), fallback: cam.flatForward)
            vel = d * 16 + SIMD3<Float>(0, 11, 0)
            move = .air
            hero.play(.jump, restart: true)
        }
        AudioDirector.shared.play(.land, volume: 0.5)
    }

    // MARK: Kampf

    private func heroAttack() {
        guard attackCooldown <= 0 else { return }
        attackCooldown = 0.28
        if let t = thugs.nearest(to: pos, maxDistance: 7) {
            let to = t.pos - pos
            let d = horizontalLength(to)
            let dir = safeNormalize(flatten(to))
            facingYaw = yawOfDirection(dir)
            if d > 1.4 { pos += dir * Swift.min(d - 1.2, 4) }
            comboCount += 1
            comboTimer = 1.6
            let heavy = comboCount % 4 == 0
            attackFlip.toggle()
            hero.play(heavy ? .uppercut : (attackFlip ? .punch : .kick), restart: true)
            let downed = thugs.hit(t, damage: heavy ? 55 : 32, direction: dir, heavy: heavy)
            hitStop = heavy || downed ? 0.09 : 0.05
            cam.addShake(heavy ? 0.4 : 0.2)
            AudioDirector.shared.play(heavy ? .punchHeavy : (attackFlip ? .punchLight : .kick))
            if heavy { AudioDirector.shared.play(.boneCrack, volume: 0.7) }
            if heavy { Haptics.heavy() } else { Haptics.light() }
        } else if let t = thugs.nearest(to: pos, maxDistance: 22) {
            // Netzschlag auf Distanz
            let dir = safeNormalize(t.pos - pos)
            hero.play(.webShoot, restart: true)
            strand.isHidden = false
            strand.update(from: hero.worldPosition(of: .rHand), to: t.pos + SIMD3<Float>(0, 1.2, 0))
            webFlash = 0.15
            FX.spawn(.webHit, at: t.pos + SIMD3<Float>(0, 1.2, 0), in: scene)
            _ = thugs.hit(t, damage: 20, direction: -dir, heavy: false)
            AudioDirector.shared.play(.webShoot)
            comboCount += 1
            comboTimer = 1.6
        } else {
            hero.play(attackFlip ? .punch : .kick, restart: true)
            attackFlip.toggle()
            AudioDirector.shared.play(.whoosh, volume: 0.5)
        }
    }

    private var webFlash: Float = 0

    private func updateCombat(dt: Float) {
        attackCooldown -= dt
        comboTimer -= dt
        if comboTimer <= 0 { comboCount = 0 }
        lastHurt += dt
        let blocking = move == .swing || move == .zip
        let dmg = thugs.update(dt: dt, heroPos: pos, heroBlocking: blocking)
        if dmg > 0 {
            health -= dmg
            lastHurt = 0
            hero.flashHit(color: UIColor(red: 1, green: 0.2, blue: 0.2, alpha: 1))
            cam.addShake(0.3)
            AudioDirector.shared.play(.punchHeavy)
            Haptics.heavy()
            FX.spawn(.bloodSpray, at: pos + SIMD3<Float>(0, 1.4, 0), in: scene, scale: 0.5)
        } else if lastHurt > 4 {
            health = Swift.min(1, health + dt * 0.05)
        }
        if health <= 0 && !defeatedFired {
            defeatedFired = true
            health = 0
            hero.play(.knockdown, restart: true)
            onHeroDefeated?()
        }
    }

    // MARK: Darstellung

    private func updatePresentation(dt: Float) {
        hero.node.simdPosition = pos
        if move == .swing {
            let up = safeNormalize(anchor - pos, fallback: SIMD3<Float>(0, 1, 0))
            let tilt = simd_quatf(from: SIMD3<Float>(0, 1, 0), to: simd_normalize(SIMD3<Float>(0, 1, 0) * 0.35 + up * 0.65))
            hero.node.simdOrientation = tilt * yawQuat(facingYaw)
            strand.update(from: hero.worldPosition(of: .rHand), to: anchor)
        } else if move == .zip {
            hero.node.simdOrientation = yawQuat(yawOfDirection(safeNormalize(flatten(zipTarget - pos), fallback: SIMD3<Float>(0, 0, 1))))
            strand.update(from: hero.worldPosition(of: .rHand), to: zipTarget)
        } else {
            hero.node.simdOrientation = yawQuat(facingYaw)
        }
        if webFlash > 0 {
            webFlash -= dt
            if webFlash <= 0 && move != .swing && move != .zip { strand.isHidden = true }
        }
        // Animationen nach Zustand
        let hs = horizontalLength(vel)
        switch move {
        case .grounded:
            if !isOneShotPlaying() {
                let want: AnimClip = hs < 0.6 ? (thugs.nearest(to: pos, maxDistance: 8) != nil ? .fightIdle : .idle) : (hs < 11 ? .run : .sprint)
                if hero.currentClip != want { hero.play(want, blend: 0.15) }
            }
        case .air:
            if !isOneShotPlaying() {
                let want: AnimClip = vel.y < -16 ? .dive : .fall
                if hero.currentClip != want { hero.play(want, blend: 0.2) }
            }
        case .swing:
            if hero.currentClip != .swing { hero.play(.swing) }
        case .wall:
            if hero.currentClip != .wallRun { hero.play(.wallRun) }
        case .zip:
            break
        }
        hero.update(dt: dt)

        // Kamera
        let mode: WorldCamera.Mode
        switch move {
        case .grounded: mode = thugs.nearest(to: pos, maxDistance: 10) != nil ? .combat : .ground
        case .air: mode = vel.y < -16 ? .dive : .air
        case .swing: mode = .swing
        case .wall: mode = .wall
        case .zip: mode = .zip
        }
        let look = input.consumeLook()
        cam.update(dt: dt, look: look, target: pos + SIMD3<Float>(0, 1.4, 0), velocity: vel,
                   facingYaw: facingYaw, mode: mode, city: city)
        keyLight.simdPosition = pos + SIMD3<Float>(20, 60, 15)
    }

    private func isOneShotPlaying() -> Bool {
        let c = hero.currentClip
        let oneShots: [AnimClip] = [.jump, .land, .punch, .kick, .uppercut, .webShoot, .zip, .hitHigh, .knockdown]
        return oneShots.contains(c) && !hero.clipFinished
    }

    // MARK: Ziel & Sammelobjekte

    private func buildObjective() {
        guard let ch = context.chapter, let p = city.landmarks[ch.objective] else { return }
        let node = SCNNode()
        let rift = FX.makeRiftSwirl(color: UIColor(red: 0.95, green: 0.05, blue: 0.12, alpha: 1))
        rift.simdScale = SIMD3<Float>(repeating: 1.8)
        rift.simdPosition = SIMD3<Float>(0, 2.6, 0)
        node.addChildNode(rift)
        let beam = SCNCylinder(radius: 0.8, height: 400)
        let m = Render.emissive(UIColor(red: 1, green: 0.05, blue: 0.1, alpha: 1), intensity: 3)
        m.blendMode = .add
        m.writesToDepthBuffer = false
        m.transparency = 0.35
        beam.firstMaterial = m
        let beamNode = SCNNode(geometry: beam)
        beamNode.simdPosition = SIMD3<Float>(0, 200, 0)
        beamNode.castsShadow = false
        node.addChildNode(beamNode)
        node.simdPosition = p
        scene.rootNode.addChildNode(node)
        objectiveNode = node
        objectivePos = p
    }

    private func fireObjective() {
        guard !objectiveFired else { return }
        objectiveFired = true
        AudioDirector.shared.play(.riftHum)
        Haptics.success()
        onReachObjective?()
    }

    private func updateObjective() {
        guard let p = objectivePos else { return }
        let d = simd_length(p - pos)
        if d < 4 { fireObjective() }
        let mood: MusicMood = d < 120 ? .tension : .roam
        if mood != musicMood {
            musicMood = mood
            AudioDirector.shared.setMusic(mood)
        }
    }

    private func buildCrystals() {
        let geo = SCNPyramid(width: 0.6, height: 0.7, length: 0.6)
        let mat = Render.pbr(UIColor(red: 0.5, green: 0, blue: 0.05, alpha: 1), roughness: 0.15, metalness: 0.3,
                             emission: UIColor(red: 1, green: 0.05, blue: 0.15, alpha: 1), emissionIntensity: 2.5)
        geo.firstMaterial = mat
        for (i, p) in city.collectiblePositions.enumerated() where !collected.contains(i) {
            let n = SCNNode()
            let top = SCNNode(geometry: geo)
            let bottom = SCNNode(geometry: geo)
            bottom.simdEulerAngles = SIMD3<Float>(Float.pi, 0, 0)
            n.addChildNode(top)
            n.addChildNode(bottom)
            n.simdPosition = p
            n.runAction(SCNAction.repeatForever(SCNAction.rotateBy(x: 0, y: CGFloat.pi * 2, z: 0, duration: 2.5)))
            scene.rootNode.addChildNode(n)
            crystals.append((node: n, index: i))
        }
    }

    private func updateCrystals() {
        var picked: [Int] = []
        for (k, c) in crystals.enumerated() where simd_length(c.node.simdPosition - (pos + SIMD3<Float>(0, 1, 0))) < 2.6 {
            picked.append(k)
        }
        guard !picked.isEmpty else { return }
        for k in picked.reversed() {
            let c = crystals[k]
            collected.insert(c.index)
            FX.spawn(.shadowBurst, at: c.node.simdPosition, in: scene, color: UIColor(red: 1, green: 0.1, blue: 0.2, alpha: 1))
            c.node.removeFromParentNode()
            crystals.remove(at: k)
        }
        UserDefaults.standard.set(Array(collected), forKey: OpenWorldController.collectedKey)
        AudioDirector.shared.play(.uiConfirm)
        Haptics.success()
        hud.collectibles = collected.count
        hud.toast = "Blutsiegel \(collected.count)/\(city.collectiblePositions.count)"
        toastTimer = 2.2
    }

    // MARK: HUD

    private func updateHUD(dt: Float) {
        if toastTimer > 0 {
            toastTimer -= dt
            if toastTimer <= 0 && hud.toast != nil { hud.toast = nil }
        }
        let h = (health * 100).rounded() / 100
        if hud.health != h { hud.health = h }
        let kmh = Int(simd_length(vel) * 3.6)
        if hud.speedKmh != kmh { hud.speedKmh = kmh }
        let swinging = move == .swing
        if hud.isSwinging != swinging { hud.isSwinging = swinging }
        if hud.combo != comboCount { hud.combo = comboCount }
        let alive = thugs.aliveCount
        if hud.thugsRemaining != alive { hud.thugsRemaining = alive }
        let s = city.size
        let mm = SIMD2<Float>(clampf(pos.x / s + 0.5, 0, 1), clampf(pos.z / s + 0.5, 0, 1))
        if simd_length(mm - hud.minimapHero) > 0.004 { hud.minimapHero = mm }
        let heading = (facingYaw * 20).rounded() / 20
        if hud.minimapHeroHeading != heading { hud.minimapHeroHeading = heading }
        if let p = objectivePos {
            let d = (simd_length(p - pos)).rounded()
            if hud.objectiveDistance != d { hud.objectiveDistance = d }
            let camYaw = yawOfDirection(cam.flatForward)
            let toYaw = yawOfDirection(safeNormalize(flatten(p - pos)))
            let ang = (wrapAngle(camYaw - toYaw) * 30).rounded() / 30
            if hud.objectiveArrowAngle != ang { hud.objectiveArrowAngle = ang }
            let mo = SIMD2<Float>(clampf(p.x / s + 0.5, 0, 1), clampf(p.z / s + 0.5, 0, 1))
            if hud.minimapObjective != mo { hud.minimapObjective = mo }
            let prompt: String? = d < 14 ? "RISS BETRETEN" : nil
            if hud.interactPrompt != prompt { hud.interactPrompt = prompt }
        } else {
            if hud.objectiveDistance != nil { hud.objectiveDistance = nil }
            if hud.minimapObjective != nil { hud.minimapObjective = nil }
        }
    }
}
