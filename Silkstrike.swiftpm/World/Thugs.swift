import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Karnath-Kultisten: Straßenschläger-Gruppen in der offenen Welt
// =====================================================================

final class ThugManager {

    enum ThugState {
        case approach
        case windup
        case strike
        case stagger
        case down
    }

    final class Thug {
        let rig: CharacterRig
        var pos: SIMD3<Float>
        var vel = SIMD3<Float>(0, 0, 0)
        var yaw: Float = 0
        var health: Float = 100
        var state: ThugState = .approach
        var timer: Float = 0
        var downTime: Float = 0
        var attackCooldown: Float

        init(rig: CharacterRig, pos: SIMD3<Float>, cooldown: Float) {
            self.rig = rig
            self.pos = pos
            self.attackCooldown = cooldown
        }

        var alive: Bool { return state != .down }
    }

    private(set) var thugs: [Thug] = []
    private let scene: SCNScene
    private let city: City
    private let quality: QualityPreset
    private let bloodEnabled: Bool
    private var respawnTimer: Float = 3
    private var usedSpawns = Set<Int>()

    static let cultistLook = FighterLook(
        build: .athletic, height: 1.8,
        skinColor: UIColor(red: 0.55, green: 0.42, blue: 0.36, alpha: 1),
        primaryColor: UIColor(red: 0.28, green: 0.03, blue: 0.05, alpha: 1),
        secondaryColor: UIColor(red: 0.05, green: 0.05, blue: 0.06, alpha: 1),
        glowColor: UIColor(red: 1, green: 0.15, blue: 0.1, alpha: 1),
        metalness: 0.1, roughness: 0.75, hasMask: true, eyeStyle: .glow,
        hairColor: nil, accessories: [.hood])

    init(scene: SCNScene, city: City, quality: QualityPreset, bloodEnabled: Bool) {
        self.scene = scene
        self.city = city
        self.quality = quality
        self.bloodEnabled = bloodEnabled
    }

    var aliveCount: Int { return thugs.filter { $0.alive }.count }

    /// Nächster lebender Schläger in Reichweite.
    func nearest(to p: SIMD3<Float>, maxDistance: Float) -> Thug? {
        var best: Thug? = nil
        var bestD = maxDistance
        for t in thugs where t.alive {
            let d = simd_length(t.pos - p)
            if d < bestD {
                bestD = d
                best = t
            }
        }
        return best
    }

    /// Treffer durch den Helden. Gibt true zurück, wenn der Schläger dabei zu Boden geht.
    @discardableResult
    func hit(_ t: Thug, damage: Float, direction: SIMD3<Float>, heavy: Bool) -> Bool {
        guard t.alive else { return false }
        t.health -= damage
        t.rig.flashHit()
        let dir = safeNormalize(flatten(direction))
        t.vel = dir * (heavy ? 9 : 4) + SIMD3<Float>(0, heavy ? 5 : 0, 0)
        let chest = t.pos + SIMD3<Float>(0, 1.3, 0)
        FX.spawn(.hitFlash, at: chest, in: scene, scale: heavy ? 1.2 : 0.8)
        FX.spawn(.bloodSpray, at: chest, in: scene, direction: dir + SIMD3<Float>(0, 0.4, 0), scale: heavy ? 1.0 : 0.6)
        if t.health <= 0 {
            t.state = .down
            t.downTime = 0
            t.rig.play(.knockdown, restart: true)
            if bloodEnabled {
                FX.spawn(.bloodPool, at: SIMD3<Float>(t.pos.x, t.pos.y + 0.02, t.pos.z), in: scene)
            }
            AudioDirector.shared.play(.bodyFall)
            return true
        }
        t.state = .stagger
        t.timer = heavy ? 0.7 : 0.4
        t.rig.play(.hitHigh, restart: true)
        return false
    }

    /// Aktualisiert alle Schläger. Gibt den Schaden zurück, den der Held in diesem Frame erleidet (0...1).
    func update(dt: Float, heroPos: SIMD3<Float>, heroBlocking: Bool) -> Float {
        var damageToHero: Float = 0
        respawnTimer -= dt
        if respawnTimer <= 0 {
            respawnTimer = 6
            spawnGroupIfNeeded(near: heroPos)
        }
        for t in thugs {
            t.timer -= dt
            t.attackCooldown -= dt
            let toHero = heroPos - t.pos
            let dist = horizontalLength(toHero)
            let dir = safeNormalize(flatten(toHero))
            switch t.state {
            case .approach:
                if dist < 40 && abs(toHero.y) < 4 {
                    t.yaw = dampAngle(t.yaw, atan2f(dir.x, dir.z), lambda: 8, dt: dt)
                    if dist > 1.6 {
                        t.vel.x = dir.x * 4.2
                        t.vel.z = dir.z * 4.2
                        if t.rig.currentClip != .run { t.rig.play(.run) }
                    } else {
                        t.vel.x = 0
                        t.vel.z = 0
                        if t.rig.currentClip != .fightIdle { t.rig.play(.fightIdle) }
                        if t.attackCooldown <= 0 {
                            t.state = .windup
                            t.timer = 0.45
                            t.rig.play(.taunt, duration: 0.45, restart: true)
                            t.rig.flashHit(color: UIColor(red: 1, green: 0.2, blue: 0.1, alpha: 1))
                        }
                    }
                } else {
                    t.vel.x = 0
                    t.vel.z = 0
                    if t.rig.currentClip != .lookAround { t.rig.play(.lookAround) }
                }
            case .windup:
                t.vel.x = 0
                t.vel.z = 0
                if t.timer <= 0 {
                    t.state = .strike
                    t.timer = 0.3
                    t.rig.play(.punch, restart: true)
                    AudioDirector.shared.play(.whoosh, volume: 0.6)
                    if dist < 2.2 && abs(toHero.y) < 2 {
                        damageToHero += heroBlocking ? 0.02 : 0.08
                    }
                }
            case .strike:
                if t.timer <= 0 {
                    t.state = .approach
                    t.attackCooldown = randf(1.2, 2.4)
                }
            case .stagger:
                if t.timer <= 0 {
                    t.state = .approach
                }
            case .down:
                t.downTime += dt
                if t.downTime > 0.8 && t.rig.currentClip != .lieDown {
                    t.rig.play(.lieDown)
                }
            }
            // Bewegung + Kollision
            t.vel.y -= 24 * dt
            t.vel.x *= t.state == .stagger || t.state == .down ? Swift.max(0, 1 - 4 * dt) : 1
            t.vel.z *= t.state == .stagger || t.state == .down ? Swift.max(0, 1 - 4 * dt) : 1
            var p = t.pos + t.vel * dt
            var v = t.vel
            _ = city.resolveCollision(position: &p, velocity: &v, radius: 0.4, height: 1.8)
            t.pos = p
            t.vel = v
            t.rig.node.simdPosition = t.pos
            t.rig.node.simdEulerAngles = SIMD3<Float>(0, t.yaw, 0)
            t.rig.update(dt: dt)
        }
        // Liegende nach einiger Zeit entfernen
        let expired = thugs.filter { $0.state == .down && $0.downTime > 10 }
        for t in expired {
            t.rig.node.runAction(SCNAction.sequence([.fadeOut(duration: 0.6), .removeFromParentNode()]))
        }
        if !expired.isEmpty {
            thugs.removeAll { $0.state == .down && $0.downTime > 10 }
        }
        return damageToHero
    }

    func removeAll() {
        for t in thugs { t.rig.node.removeFromParentNode() }
        thugs.removeAll()
    }

    private func spawnGroupIfNeeded(near hero: SIMD3<Float>) {
        guard aliveCount < (quality == .performance ? 4 : 7) else { return }
        var bestIndex = -1
        var bestD: Float = 150
        for (i, p) in city.thugSpawnPoints.enumerated() where !usedSpawns.contains(i) {
            let d = simd_length(p - hero)
            if d > 25 && d < bestD {
                bestD = d
                bestIndex = i
            }
        }
        guard bestIndex >= 0 else {
            if usedSpawns.count >= city.thugSpawnPoints.count { usedSpawns.removeAll() }
            return
        }
        usedSpawns.insert(bestIndex)
        let center = city.thugSpawnPoints[bestIndex]
        let count = Int.random(in: 3...4)
        for k in 0..<count {
            let ang = Float(k) / Float(count) * Float.pi * 2
            let p = center + SIMD3<Float>(cosf(ang) * 2.5, 0, sinf(ang) * 2.5)
            let rig = CharacterRig(look: ThugManager.cultistLook, quality: quality)
            rig.node.simdPosition = p
            rig.play(.lookAround)
            scene.rootNode.addChildNode(rig.node)
            thugs.append(Thug(rig: rig, pos: p, cooldown: randf(0.5, 2.0)))
        }
    }
}
