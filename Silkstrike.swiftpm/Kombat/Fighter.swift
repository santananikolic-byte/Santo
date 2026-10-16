import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Kämpfer: Zustände, Moves mit Frame-Daten, Eingabe-Absicht
// =====================================================================

enum KHitLevel {
    case high
    case mid
    case low
    case overhead
    case unblockable
}

struct KMoveDef {
    let name: String
    let clip: AnimClip
    let startup: Float
    let active: Float
    let recovery: Float
    let damage: Float
    let reach: Float
    let level: KHitLevel
    let knockdown: Bool
    let launch: Bool
    let lunge: Float

    var total: Float { return startup + active + recovery }
}

enum KMoves {
    static let jab = KMoveDef(name: "jab", clip: .punch, startup: 0.07, active: 0.06, recovery: 0.17,
                              damage: 45, reach: 1.3, level: .high, knockdown: false, launch: false, lunge: 1.0)
    static let cross = KMoveDef(name: "cross", clip: .punch2, startup: 0.08, active: 0.07, recovery: 0.2,
                                damage: 55, reach: 1.35, level: .mid, knockdown: false, launch: false, lunge: 1.4)
    static let chainKick = KMoveDef(name: "chainKick", clip: .kick2, startup: 0.12, active: 0.08, recovery: 0.32,
                                    damage: 90, reach: 1.7, level: .mid, knockdown: true, launch: false, lunge: 1.8)
    static let kick = KMoveDef(name: "kick", clip: .kick, startup: 0.12, active: 0.07, recovery: 0.26,
                               damage: 70, reach: 1.65, level: .mid, knockdown: false, launch: false, lunge: 0.8)
    static let roundhouse = KMoveDef(name: "roundhouse", clip: .kick2, startup: 0.14, active: 0.08, recovery: 0.32,
                                     damage: 85, reach: 1.75, level: .high, knockdown: true, launch: false, lunge: 1.0)
    static let kickPunch = KMoveDef(name: "kickPunch", clip: .uppercut, startup: 0.1, active: 0.08, recovery: 0.34,
                                    damage: 80, reach: 1.3, level: .mid, knockdown: false, launch: true, lunge: 1.6)
    static let uppercut = KMoveDef(name: "uppercut", clip: .uppercut, startup: 0.1, active: 0.09, recovery: 0.38,
                                   damage: 95, reach: 1.3, level: .mid, knockdown: false, launch: true, lunge: 0.6)
    static let sweep = KMoveDef(name: "sweep", clip: .sweep, startup: 0.12, active: 0.08, recovery: 0.36,
                                damage: 70, reach: 1.7, level: .low, knockdown: true, launch: false, lunge: 0.4)
    static let jumpKick = KMoveDef(name: "jumpKick", clip: .jumpKick, startup: 0.06, active: 0.25, recovery: 0.1,
                                   damage: 75, reach: 1.5, level: .overhead, knockdown: false, launch: false, lunge: 0)
    static let jumpPunch = KMoveDef(name: "jumpPunch", clip: .punch, startup: 0.05, active: 0.2, recovery: 0.1,
                                    damage: 55, reach: 1.3, level: .overhead, knockdown: false, launch: false, lunge: 0)
    static let throwMove = KMoveDef(name: "throw", clip: .grab, startup: 0.08, active: 0.06, recovery: 0.5,
                                    damage: 110, reach: 1.25, level: .unblockable, knockdown: true, launch: false, lunge: 0.4)

    /// Kombo-Ketten: (vorheriger Move, Taste P=true/K=false) → nächster Move
    static func chain(after name: String, punch: Bool) -> KMoveDef? {
        switch (name, punch) {
        case ("jab", true): return cross
        case ("cross", false): return chainKick
        case ("kick", false): return roundhouse
        case ("kick", true): return kickPunch
        default: return nil
        }
    }
}

/// Was ein Kämpfer in diesem Frame tun will (Spieler oder KI).
struct KIntent {
    var moveX: Float = 0        // Welt-X, -1...1
    var crouch = false
    var jump = false
    var block = false
    var punch = false
    var kick = false
    var special1 = false
    var special2 = false
    var brutal = false
}

enum KState: Equatable {
    case idle
    case walk
    case crouch
    case air
    case attack
    case block
    case hitstun
    case blockstun
    case knockdown
    case getUp
    case special
    case dizzy
    case cinematic
    case victory
}

final class KFighter {
    let def: FighterDef
    let rig: CharacterRig
    let isPlayer: Bool

    var x: Float
    var y: Float = 0
    var vx: Float = 0
    var vy: Float = 0
    var facing: Float = 1
    let maxHealth: Float
    var health: Float
    var healthLag: Float
    var meter: Float = 0               // 0...100
    var state: KState = .idle
    var stateTime: Float = 0
    var move: KMoveDef?
    var moveHit = false
    var moveConnected = false          // getroffen oder geblockt (für Ketten)
    var stun: Float = 0
    var juggled = false
    var blockLow = false
    var invuln: Float = 0
    var cooldowns: [Float] = [0, 0]
    var specialIndex = 0
    var specialDone = false
    var specialStep = 0
    var counterTimer: Float = 0
    var comboTaken = 0
    var comboDealt = 0
    var maxCombo = 0
    var damageDealt: Float = 0
    var roundsWon = 0

    init(def: FighterDef, look: FighterLook, isPlayer: Bool, quality: QualityPreset, x: Float) {
        self.def = def
        self.isPlayer = isPlayer
        self.rig = CharacterRig(look: look, quality: quality)
        self.x = x
        self.maxHealth = def.stats.maxHealth
        self.health = def.stats.maxHealth
        self.healthLag = def.stats.maxHealth
        self.facing = x < 0 ? 1 : -1
    }

    var grounded: Bool { return y <= 0.001 }
    var canAct: Bool {
        switch state {
        case .idle, .walk, .crouch, .block: return true
        default: return false
        }
    }
    var isDown: Bool { return state == .knockdown || state == .getUp }

    func setState(_ s: KState) {
        state = s
        stateTime = 0
    }

    func resetForRound(x newX: Float) {
        x = newX
        y = 0
        vx = 0
        vy = 0
        health = maxHealth
        healthLag = maxHealth
        state = .idle
        stateTime = 0
        move = nil
        stun = 0
        juggled = false
        invuln = 0
        counterTimer = 0
        comboTaken = 0
        comboDealt = 0
        cooldowns = [0, 0]
        rig.resetBody()
        rig.node.isHidden = false
        rig.play(.fightIdle, restart: true)
    }
}
