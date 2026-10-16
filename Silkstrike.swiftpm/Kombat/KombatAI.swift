import Foundation
import simd

// =====================================================================
//  CPU-Gegner: Reaktionszeit, Blocken, Kombos, Specials – nach aiLevel
// =====================================================================

final class KombatAI {

    private enum Plan {
        case punch
        case kick
        case crouchPunch
        case crouchKick
        case special(Int)
        case jumpIn
        case throwIt
        case brutal
    }

    private let level: Float
    private let aggressive: Bool
    private var decisionTimer: Float = 0.6
    private var blockHold: Float = 0
    private var blockLowHold = false
    private var walkDir: Float = 0
    private var walkHold: Float = 0
    private var queue: [(delay: Float, plan: Plan)] = []
    private var queueTimer: Float = 0
    private var crouchHold: Float = 0

    init(level: Float, boss: Bool) {
        self.level = clampf(level, 0.2, 1.25)
        self.aggressive = boss
    }

    private var reaction: Float { return lerpf(0.5, 0.11, clampf(level, 0, 1.2) / 1.2) }
    private var blockChance: Float { return clampf(0.12 + 0.62 * level, 0, 0.88) }

    func think(dt: Float, me: KFighter, opp: KFighter, incomingProjectile: Bool) -> KIntent {
        var intent = KIntent()
        let dx = opp.x - me.x
        let dist = abs(dx)
        let toward: Float = dx >= 0 ? 1 : -1

        blockHold -= dt
        walkHold -= dt
        crouchHold -= dt
        decisionTimer -= dt

        // Geplante Tastendrücke abarbeiten
        if !queue.isEmpty {
            queueTimer -= dt
            if queueTimer <= 0 {
                let item = queue.removeFirst()
                apply(item.plan, to: &intent, toward: toward)
                queueTimer = queue.first?.delay ?? 0
            }
        }

        if decisionTimer <= 0 && queue.isEmpty {
            decisionTimer = reaction * Float.random(in: 0.8...1.3)
            decide(me: me, opp: opp, dist: dist, toward: toward, incomingProjectile: incomingProjectile)
        }

        if blockHold > 0 {
            intent.block = true
            intent.crouch = blockLowHold
        } else if walkHold > 0 && queue.isEmpty {
            intent.moveX = walkDir
        }
        if crouchHold > 0 { intent.crouch = true }
        return intent
    }

    private func apply(_ plan: Plan, to intent: inout KIntent, toward: Float) {
        switch plan {
        case .punch: intent.punch = true
        case .kick: intent.kick = true
        case .crouchPunch:
            intent.crouch = true
            intent.punch = true
        case .crouchKick:
            intent.crouch = true
            intent.kick = true
        case .special(let i):
            if i == 0 { intent.special1 = true } else { intent.special2 = true }
        case .jumpIn:
            intent.jump = true
            intent.moveX = toward
        case .throwIt:
            intent.block = true
            intent.punch = true
        case .brutal:
            intent.brutal = true
        }
    }

    private func enqueue(_ plans: [Plan]) {
        let gap = lerpf(0.24, 0.11, clampf(level, 0, 1.2) / 1.2)
        var built: [(delay: Float, plan: Plan)] = []
        for (i, p) in plans.enumerated() {
            built.append((delay: i == 0 ? Float(0) : gap, plan: p))
        }
        queue = built
        queueTimer = 0
    }

    private func decide(me: KFighter, opp: KFighter, dist: Float, toward: Float, incomingProjectile: Bool) {
        let r = Float.random(in: 0...1)
        // Verteidigung zuerst
        if (opp.state == .attack || opp.state == .special) && dist < 2.6 {
            if r < blockChance {
                blockHold = 0.45
                blockLowHold = opp.move?.level == .low
                return
            }
        }
        if incomingProjectile && r < blockChance {
            if Float.random(in: 0...1) < 0.4 * level {
                enqueue([.jumpIn])
            } else {
                blockHold = 0.5
                blockLowHold = false
            }
            return
        }
        if opp.state == .air && dist < 2.6 && r < 0.75 * level {
            enqueue([.crouchPunch])
            return
        }
        // Angriff
        let cd0 = me.cooldowns.count > 0 ? me.cooldowns[0] : 1
        let cd1 = me.cooldowns.count > 1 ? me.cooldowns[1] : 1
        if me.meter >= 100 && dist < 2.0 && r < 0.65 * level {
            enqueue([.brutal])
            return
        }
        let specialRange0 = me.def.specials.count > 0 ? me.def.specials[0].range : 0
        let specialRange1 = me.def.specials.count > 1 ? me.def.specials[1].range : 0
        if dist > 3.2 {
            let roll = Float.random(in: 0...1)
            if cd0 <= 0 && dist < specialRange0 && roll < 0.3 + 0.25 * level {
                enqueue([.special(0)])
            } else if cd1 <= 0 && dist < specialRange1 && roll < 0.25 + 0.2 * level {
                enqueue([.special(1)])
            } else if roll < 0.12 + (aggressive ? 0.1 : 0) {
                enqueue([.jumpIn, .kick])
            } else {
                walkDir = toward
                walkHold = 0.4
            }
            return
        }
        if dist > 1.5 {
            let roll = Float.random(in: 0...1)
            if roll < 0.55 + (aggressive ? 0.2 : 0) {
                walkDir = toward
                walkHold = 0.3
            } else if roll < 0.7 && cd1 <= 0 && dist < specialRange1 {
                enqueue([.special(1)])
            } else if roll < 0.82 {
                walkDir = -toward
                walkHold = 0.25
            } else {
                enqueue([.kick])
            }
            return
        }
        // Nahkampf
        let roll = Float.random(in: 0...1)
        let skill = clampf(level, 0, 1.2)
        if opp.state == .block && roll < 0.35 * skill {
            enqueue([.throwIt])
        } else if roll < 0.28 + 0.2 * skill {
            enqueue([.punch, .punch, .kick])
        } else if roll < 0.45 + 0.15 * skill {
            enqueue([.kick, .kick])
        } else if roll < 0.58 {
            enqueue([.crouchKick])
        } else if roll < 0.68 {
            enqueue([.crouchPunch])
        } else if roll < 0.76 && cd0 <= 0 && specialRange0 > 0 {
            enqueue([.special(0)])
        } else if roll < 0.88 {
            blockHold = 0.35
            blockLowHold = Float.random(in: 0...1) < 0.4
        } else {
            walkDir = -toward
            walkHold = 0.3
        }
    }
}
