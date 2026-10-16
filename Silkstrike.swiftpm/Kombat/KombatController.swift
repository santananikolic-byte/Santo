import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  1-gegen-1-Kampf: Runden, Kombos, Specials, Brutal-Schlag, Exekution
// =====================================================================

final class KProjectile {
    let visual: ProjectileVisual
    let owner: Int
    var x: Float
    let y: Float
    let vx: Float
    let damage: Float
    let low: Bool
    var life: Float = 2.2
    var alive = true

    init(visual: ProjectileVisual, owner: Int, x: Float, y: Float, vx: Float, damage: Float, low: Bool) {
        self.visual = visual
        self.owner = owner
        self.x = x
        self.y = y
        self.vx = vx
        self.damage = damage
        self.low = low
    }
}

final class KombatController: GameSceneController {

    let scene = SCNScene()
    let cameraNode = SCNNode()
    var onMatchEnd: ((KombatResult) -> Void)?

    private enum Phase {
        case intro
        case roundIntro
        case fight
        case brutal
        case roundOver
        case finishHim
        case executing
        case outro
        case done
    }

    private let setup: KombatSetup
    private let settings: GameSettings
    private let input: InputState
    private let hud: KombatHUD
    private let arena: ArenaSet
    private let fighters: [KFighter]
    private let ai: KombatAI
    private let camera = SCNCamera()
    private let shake = CameraShake()
    private var projectiles: [KProjectile] = []
    private var pullStrand: WebStrand?
    private var pullStrandTimer: Float = 0

    private var phase: Phase = .intro
    private var phaseTime: Float = 0
    private var round = 1
    private var timerAccum: Float = 0
    private var timeLeft: Int
    private var timeScale: Float = 1
    private var hitStop: Float = 0
    private var paused = false
    private var camPos = SIMD3<Float>(0, 1.6, 7)
    private var camLook = SIMD3<Float>(0, 1.1, 0)
    private var camFov: Float = 42
    private var lastJumpUp = false
    private var comboTextTimer: Float = 0
    private var bannerTimer: Float = 0
    private var flash: Double = 0
    private var execution: ExecutionSequence?
    private var brutal: BrutalSequence?
    private var brutalAttacker = 0
    private var roundWinner = -1
    private var matchWinner = -1
    private var executionPerformed = false
    private var playerExecuted = false
    private var totalTime: Float = 0
    private var endFired = false
    private var cueFlags = Set<String>()

    init(setup: KombatSetup, settings: GameSettings, input: InputState, hud: KombatHUD) {
        self.setup = setup
        self.settings = settings
        self.input = input
        self.hud = hud
        self.timeLeft = setup.roundSeconds
        FX.quality = settings.quality
        FX.bloodEnabled = settings.bloodEnabled

        arena = ArenaBuilder.build(setup.arena, quality: settings.quality, into: scene)
        let pDef = Roster.def(setup.player)
        let cDef = Roster.def(setup.cpu)
        let pLook = (setup.playerUsesDarkSuit && setup.player == .silkstrike) ? Roster.heroDarkSuitLook : pDef.look
        let p1 = KFighter(def: pDef, look: pLook, isPlayer: true, quality: settings.quality, x: -2.6)
        let p2 = KFighter(def: cDef, look: cDef.look, isPlayer: false, quality: settings.quality, x: 2.6)
        fighters = [p1, p2]
        ai = KombatAI(level: setup.aiLevel, boss: setup.cpu == .malrek || setup.cpu == .nachtseide)
        for f in fighters {
            scene.rootNode.addChildNode(f.rig.node)
            f.rig.play(.fightIdle)
        }

        Render.configureCamera(camera, quality: settings.quality, style: .kombat)
        camera.fieldOfView = 42
        camera.zNear = 0.05
        camera.zFar = 1500
        cameraNode.camera = camera
        scene.rootNode.addChildNode(cameraNode)
        if arena.hasRain {
            cameraNode.addParticleSystem(FX.makeRain(intensity: 0.8))
        }

        hud.p1Name = pDef.name.uppercased()
        hud.p2Name = cDef.name.uppercased()
        hud.special1Name = pDef.specials.first?.name ?? "Spezial 1"
        hud.special2Name = pDef.specials.count > 1 ? pDef.specials[1].name : "Spezial 2"
        hud.roundsToWin = setup.roundsToWin
        hud.p1Rounds = 0
        hud.p2Rounds = 0
        hud.p1Health = 1
        hud.p2Health = 1
        hud.p1HealthLag = 1
        hud.p2HealthLag = 1
        hud.p1Meter = 0
        hud.p2Meter = 0
        hud.timer = setup.roundSeconds
        hud.banner = nil
        hud.comboText = nil
        hud.matchOver = false
        hud.playerWon = false
        hud.showExecutePrompt = false
        hud.canBrutal = false
        hud.cinematic = true
        hud.controlsEnabled = false
        syncVisuals(dt: 0)
        camPos = SIMD3<Float>(-2.6, 1.4, 3.2)
        camLook = SIMD3<Float>(-2.6, 1.3, 0)
        applyCamera(dt: 0)
        AudioDirector.shared.setMusic(setup.cpu == .malrek ? .boss : arena.music)
    }

    // MARK: GameSceneController

    func didAttach(to view: SCNView) {}

    func teardown() {
        AudioDirector.shared.stopSpeech()
        AudioDirector.shared.setSlowMotion(1)
        FX.cleanup(in: scene)
        for p in projectiles { p.visual.node.removeFromParentNode() }
        projectiles.removeAll()
        cameraNode.removeAllParticleSystems()
        onMatchEnd = nil
    }

    func setPaused(_ p: Bool) {
        paused = p
        scene.isPaused = p
    }

    private var p1: KFighter { return fighters[0] }
    private var p2: KFighter { return fighters[1] }

    // MARK: Hauptschleife

    func update(dt rawDt: Float) {
        guard !paused else { return }
        totalTime += rawDt
        updateOverlays(dt: rawDt)
        if hitStop > 0 {
            hitStop -= rawDt
            applyCamera(dt: rawDt)
            return
        }
        let dt = rawDt * timeScale
        phaseTime += dt
        switch phase {
        case .intro: updateIntro(dt: dt)
        case .roundIntro: updateRoundIntro(dt: dt)
        case .fight: updateFight(dt: dt)
        case .brutal: updateBrutal(dt: dt)
        case .roundOver: updateRoundOver(dt: dt)
        case .finishHim: updateFinishHim(dt: dt)
        case .executing: updateExecution(dt: dt)
        case .outro: updateOutro(dt: dt)
        case .done: break
        }
        if phase != .executing && phase != .brutal {
            syncVisuals(dt: dt)
            if phase != .intro && phase != .outro { fightCamera(dt: dt) }
        }
        applyCamera(dt: rawDt)
        updateHUD(dt: rawDt)
    }

    private func setPhase(_ p: Phase) {
        phase = p
        phaseTime = 0
        cueFlags.removeAll()
    }

    /// true genau einmal, wenn phaseTime die Marke überschreitet.
    private func once(_ key: String, at t: Float) -> Bool {
        if phaseTime >= t && !cueFlags.contains(key) {
            cueFlags.insert(key)
            return true
        }
        return false
    }

    private func setTimeScale(_ s: Float) {
        timeScale = s
        AudioDirector.shared.setSlowMotion(s)
    }

    // MARK: Phasen

    private func updateIntro(dt: Float) {
        if once("p1", at: 0.05) {
            AudioDirector.shared.speak(p1.def.introQuote, as: .fighter(p1.def.id))
            p1.rig.play(.taunt, restart: true)
        }
        if once("p2", at: 2.4) {
            AudioDirector.shared.speak(p2.def.introQuote, as: .fighter(p2.def.id))
            p2.rig.play(.taunt, restart: true)
        }
        let focus = phaseTime < 2.4 ? p1 : p2
        let local = phaseTime < 2.4 ? phaseTime / 2.4 : (phaseTime - 2.4) / 2.4
        let side: Float = focus === p1 ? -1 : 1
        let ang = lerpf(-0.5, 0.35, local) * side
        let target = SIMD3<Float>(focus.x, 1.3, 0)
        let radius: Float = lerpf(3.4, 2.6, local)
        camPos = target + SIMD3<Float>(sinf(ang) * radius, 0.1 + local * 0.3, cosf(ang) * radius)
        camLook = target + SIMD3<Float>(0, 0.1, 0)
        camFov = 36
        if input.consumePress(.skip) || phaseTime > 4.8 {
            AudioDirector.shared.stopSpeech()
            startRound()
        }
    }

    private func startRound() {
        p1.resetForRound(x: -2.6)
        p2.resetForRound(x: 2.6)
        p1.facing = 1
        p2.facing = -1
        timeLeft = setup.roundSeconds
        timerAccum = 0
        roundWinner = -1
        for p in projectiles { p.visual.node.removeFromParentNode() }
        projectiles.removeAll()
        hud.cinematic = false
        setTimeScale(1)
        setPhase(.roundIntro)
    }

    private func updateRoundIntro(dt: Float) {
        if once("round", at: 0.1) {
            let names = ["eins", "zwei", "drei", "vier", "fünf"]
            showBanner("RUNDE \(round)", style: .round, seconds: 1.3)
            AudioDirector.shared.announce("Runde \(names[Swift.min(round - 1, names.count - 1)])")
        }
        if once("fight", at: 1.5) {
            showBanner("KÄMPFT!", style: .fight, seconds: 0.9)
            AudioDirector.shared.announce("Kämpft!")
            Haptics.medium()
        }
        if phaseTime > 2.2 {
            hud.controlsEnabled = true
            setPhase(.fight)
        }
    }

    private func updateFight(dt: Float) {
        // Rundenzeit
        timerAccum += dt
        if timerAccum >= 1 {
            timerAccum -= 1
            timeLeft = Swift.max(0, timeLeft - 1)
        }
        let playerIntent = readPlayerIntent()
        let aiIntent = ai.think(dt: dt, me: p2, opp: p1, incomingProjectile: projectiles.contains { $0.owner == 0 && $0.alive })
        step(0, intent: playerIntent, dt: dt)
        step(1, intent: aiIntent, dt: dt)
        updateProjectiles(dt: dt)
        separate()
        updatePullStrand(dt: dt)

        // K.O. oder Zeit abgelaufen
        if p1.health <= 0 || p2.health <= 0 || timeLeft <= 0 {
            let winner: Int
            if p1.health <= 0 && p2.health <= 0 { winner = 0 }
            else if p1.health <= 0 { winner = 1 }
            else if p2.health <= 0 { winner = 0 }
            else { winner = p1.health / p1.maxHealth >= p2.health / p2.maxHealth ? 0 : 1 }
            endRound(winner: winner, timeout: timeLeft <= 0 && p1.health > 0 && p2.health > 0)
        }
    }

    private func endRound(winner: Int, timeout: Bool) {
        roundWinner = winner
        let w = fighters[winner]
        let l = fighters[1 - winner]
        w.roundsWon += 1
        hud.controlsEnabled = false
        hud.canBrutal = false
        l.health = Swift.max(0, l.health)
        setTimeScale(0.3)
        shake.add(0.6)
        flashScreen(.white)
        if !timeout {
            l.setState(.knockdown)
            l.rig.play(.knockdown, restart: true)
            l.vx = w.facing * 3
            AudioDirector.shared.play(.punchHeavy)
            AudioDirector.shared.play(.boneCrack)
        }
        if w.roundsWon >= setup.roundsToWin {
            matchWinner = winner
        }
        setPhase(.roundOver)
    }

    private func updateRoundOver(dt: Float) {
        let w = fighters[roundWinner]
        let l = fighters[1 - roundWinner]
        // Physik der Kämpfer weiterlaufen lassen (Fallen)
        simulateBody(l, dt: dt)
        if once("slow", at: 0.6) { setTimeScale(1) }
        if once("banner", at: 0.7) {
            if matchWinner >= 0 {
                // Gleich: VOLLENDE ES!
            } else {
                showBanner("\(w.def.name.uppercased()) GEWINNT DIE RUNDE", style: .info, seconds: 1.8)
                w.rig.play(.taunt, restart: true)
            }
        }
        if phaseTime > 2.6 {
            if matchWinner >= 0 {
                l.setState(.dizzy)
                l.y = 0
                l.vx = 0
                l.health = 1
                l.rig.resetBody()
                l.rig.play(.getUp, restart: true)
                w.setState(.idle)
                showBanner("VOLLENDE ES!", style: .finish, seconds: 2.2)
                AudioDirector.shared.announce("Vollende es!")
                AudioDirector.shared.setMusic(.tension)
                Haptics.heavy()
                if w.isPlayer {
                    hud.showExecutePrompt = true
                    hud.controlsEnabled = true
                }
                setPhase(.finishHim)
            } else {
                round += 1
                hud.p1Rounds = p1.roundsWon
                hud.p2Rounds = p2.roundsWon
                startRound()
            }
        }
    }

    private func updateFinishHim(dt: Float) {
        let w = fighters[matchWinner]
        let l = fighters[1 - matchWinner]
        if l.rig.currentClip != .dizzy && l.rig.clipFinished { l.rig.play(.dizzy) }
        hud.p1Rounds = p1.roundsWon
        hud.p2Rounds = p2.roundsWon
        let window: Float = 6
        let left = Swift.max(0, window - phaseTime)
        if w.isPlayer {
            if abs(hud.executeTimeLeft - left) > 0.05 { hud.executeTimeLeft = left }
            // Spieler darf sich noch bewegen
            let intent = readPlayerIntent()
            if abs(intent.moveX) > 0.2 {
                w.vx = intent.moveX * w.def.stats.walkSpeed
                w.rig.play(intent.moveX * w.facing > 0 ? .walkForward : .walkBack)
            } else {
                w.vx = 0
                if w.rig.currentClip != .fightIdle { w.rig.play(.fightIdle) }
            }
            w.x = clampf(w.x + w.vx * dt, -arena.halfWidth, arena.halfWidth)
            if input.consumePress(.execute) {
                startExecution(attacker: matchWinner)
                return
            }
            if left <= 0 {
                // Gnade: Gegner bricht zusammen
                hud.showExecutePrompt = false
                l.setState(.knockdown)
                l.rig.play(.knockdown, restart: true)
                AudioDirector.shared.play(.bodyFall)
                startOutro()
            }
        } else if phaseTime > 1.8 {
            startExecution(attacker: matchWinner)
        }
    }

    private func startExecution(attacker: Int) {
        let a = fighters[attacker]
        let v = fighters[1 - attacker]
        hud.showExecutePrompt = false
        hud.controlsEnabled = false
        hud.cinematic = true
        var kind = a.def.execution.kind
        if a.isPlayer && setup.playerUsesDarkSuit && a.def.id == .silkstrike { kind = .devour }
        let seq = ExecutionSequence(kind: kind, attacker: a.rig, victim: v.rig, attackerColor: a.def.look.glowColor,
                                    scene: scene, floorY: arena.floorY, bloodEnabled: settings.bloodEnabled)
        seq.onShake = { [weak self] t in self?.shake.add(t) }
        seq.onFlash = { [weak self] c in self?.flashScreen(c) }
        seq.onTimeScale = { [weak self] s in self?.setTimeScale(s) }
        seq.onSound = { s in AudioDirector.shared.play(s) }
        execution = seq
        a.setState(.cinematic)
        v.setState(.cinematic)
        if a.isPlayer { executionPerformed = true } else { playerExecuted = true }
        AudioDirector.shared.setMusic(.none)
        setPhase(.executing)
    }

    private func updateExecution(dt: Float) {
        guard let seq = execution else {
            startOutro()
            return
        }
        let finished = seq.update(dt: dt)
        let c = seq.camera
        camPos = c.position
        camLook = c.lookAt
        camFov = c.fov
        if finished {
            execution = nil
            setTimeScale(1)
            for f in fighters { f.x = f.rig.node.simdPosition.x }
            let a = fighters[matchWinner]
            showBanner(a.def.execution.name.uppercased(), style: .execution, seconds: 2.6)
            AudioDirector.shared.announce("Exekution!")
            Haptics.heavy()
            startOutro()
        }
    }

    private func startOutro() {
        hud.cinematic = true
        hud.controlsEnabled = false
        let w = fighters[matchWinner]
        w.setState(.victory)
        w.rig.play(.victory, restart: true)
        hud.matchOver = true
        hud.playerWon = w.isPlayer
        AudioDirector.shared.setMusic(w.isPlayer ? .victory : .sad)
        setPhase(.outro)
    }

    private func updateOutro(dt: Float) {
        let w = fighters[matchWinner]
        if once("banner", at: 2.4) {
            if w.isPlayer {
                showBanner("\(w.def.name.uppercased()) SIEGT", style: .victory, seconds: 3)
            } else {
                showBanner("NIEDERLAGE", style: .defeat, seconds: 3)
            }
            AudioDirector.shared.announce("\(w.def.name) siegt")
        }
        if once("quote", at: 3.6) {
            AudioDirector.shared.speak(w.def.winQuote, as: .fighter(w.def.id))
        }
        let ang = 0.4 + phaseTime * 0.12
        let target = SIMD3<Float>(w.x, 1.2, 0)
        camPos = target + SIMD3<Float>(sinf(ang) * 3.2 * -w.facing, 0.4, cosf(ang) * 3.2)
        camLook = target + SIMD3<Float>(0, 0.2, 0)
        camFov = 38
        w.rig.update(dt: 0)
        if phaseTime > 7.5 || (phaseTime > 3 && input.consumePress(.skip)) {
            finishMatch()
        }
    }

    private func finishMatch() {
        guard !endFired else { return }
        endFired = true
        setPhase(.done)
        AudioDirector.shared.stopSpeech()
        let result = KombatResult(playerWon: matchWinner == 0,
                                  executionPerformed: executionPerformed,
                                  playerWasExecuted: playerExecuted,
                                  roundsWon: p1.roundsWon,
                                  roundsLost: p2.roundsWon,
                                  maxCombo: p1.maxCombo,
                                  totalDamageDealt: p1.damageDealt,
                                  seconds: totalTime)
        onMatchEnd?(result)
    }

    // MARK: Brutal-Schlag

    private func tryBrutal(_ index: Int) -> Bool {
        let a = fighters[index]
        let v = fighters[1 - index]
        guard a.meter >= 100, abs(v.x - a.x) < 2.4, !v.isDown, v.grounded else { return false }
        a.meter = 0
        brutalAttacker = index
        a.setState(.cinematic)
        v.setState(.cinematic)
        hud.cinematic = true
        hud.controlsEnabled = false
        showBanner(a.def.brutalName, style: .brutal, seconds: 1.6)
        let seq = BrutalSequence(attacker: a.rig, victim: v.rig, attackerColor: a.def.look.glowColor,
                                 scene: scene, floorY: arena.floorY, bloodEnabled: settings.bloodEnabled)
        seq.onShake = { [weak self] t in self?.shake.add(t) }
        seq.onFlash = { [weak self] c in self?.flashScreen(c) }
        seq.onTimeScale = { [weak self] s in self?.setTimeScale(s) }
        seq.onImpact = { [weak self] i in self?.brutalImpact(i) }
        brutal = seq
        setPhase(.brutal)
        return true
    }

    private func brutalImpact(_ i: Int) {
        let a = fighters[brutalAttacker]
        let v = fighters[1 - brutalAttacker]
        let parts: [Float] = [70, 80, 130]
        let dmg = parts[Swift.min(i, 2)] * a.def.stats.power / Swift.max(0.3, v.def.stats.defense)
        v.health = Swift.max(1, v.health - dmg)
        a.damageDealt += dmg
        a.comboDealt += 1
        a.maxCombo = Swift.max(a.maxCombo, a.comboDealt)
    }

    private func updateBrutal(dt: Float) {
        guard let seq = brutal else {
            setPhase(.fight)
            return
        }
        let finished = seq.update(dt: dt)
        let c = seq.camera
        camPos = c.position
        camLook = c.lookAt
        camFov = c.fov
        if finished {
            brutal = nil
            setTimeScale(1)
            let a = fighters[brutalAttacker]
            let v = fighters[1 - brutalAttacker]
            // Positionen aus den Rigs übernehmen
            a.x = a.rig.node.simdPosition.x
            v.x = v.rig.node.simdPosition.x
            a.setState(.idle)
            v.setState(.knockdown)
            v.rig.play(.lieDown)
            hud.cinematic = false
            hud.controlsEnabled = true
            setPhase(.fight)
        }
    }

    // MARK: Eingabe

    private func readPlayerIntent() -> KIntent {
        var i = KIntent()
        let m = input.move
        i.moveX = abs(m.x) > 0.25 ? m.x : 0
        i.crouch = m.y < -0.55
        let up = m.y > 0.6
        i.jump = up && !lastJumpUp
        lastJumpUp = up
        i.block = input.isDown(.block)
        i.punch = input.consumePress(.punch)
        i.kick = input.consumePress(.kick)
        i.special1 = input.consumePress(.special1)
        i.special2 = input.consumePress(.special2)
        i.brutal = input.consumePress(.brutal)
        return i
    }

    // MARK: Kämpfer-Logik

    private func step(_ index: Int, intent: KIntent, dt: Float) {
        let f = fighters[index]
        let o = fighters[1 - index]
        f.stateTime += dt
        f.invuln -= dt
        f.counterTimer -= dt
        for k in 0..<f.cooldowns.count { f.cooldowns[k] -= dt }
        if f.isPlayer {
            let r0 = f.cooldowns[0] <= 0
            let r1 = f.cooldowns.count > 1 ? f.cooldowns[1] <= 0 : false
            if hud.special1Ready != r0 { hud.special1Ready = r0 }
            if hud.special2Ready != r1 { hud.special2Ready = r1 }
        }
        // Schadens-Lag-Balken
        f.healthLag = f.healthLag > f.health ? Swift.max(f.health, f.healthLag - f.maxHealth * 0.35 * dt) : f.health

        switch f.state {
        case .idle, .walk, .crouch, .block:
            if f.comboTaken > 0 { f.comboTaken = 0 }
            f.facing = o.x >= f.x ? 1 : -1
            if intent.brutal && tryBrutal(index) { return }
            if intent.jump {
                f.setState(.air)
                f.vy = f.def.stats.jumpVelocity
                f.vx = intent.moveX * 3.6
                f.move = nil
                f.rig.play(.jump, restart: true)
                AudioDirector.shared.play(.whoosh, volume: 0.4)
            } else if intent.special1 && f.cooldowns[0] <= 0 {
                startSpecial(f, index: 0)
            } else if intent.special2 && f.cooldowns.count > 1 && f.cooldowns[1] <= 0 {
                startSpecial(f, index: 1)
            } else if intent.punch {
                if intent.block && abs(o.x - f.x) < 1.5 {
                    startMove(f, KMoves.throwMove)
                } else {
                    startMove(f, intent.crouch ? KMoves.uppercut : KMoves.jab)
                }
            } else if intent.kick {
                startMove(f, intent.crouch ? KMoves.sweep : KMoves.kick)
            } else if intent.block {
                if f.state != .block { f.setState(.block) }
                f.blockLow = intent.crouch
                f.vx = 0
            } else if intent.crouch {
                if f.state != .crouch { f.setState(.crouch) }
                f.vx = 0
            } else if abs(intent.moveX) > 0.1 {
                if f.state != .walk { f.setState(.walk) }
                let back = intent.moveX * f.facing < 0
                f.vx = intent.moveX * f.def.stats.walkSpeed * (back ? 0.8 : 1)
            } else {
                if f.state != .idle { f.setState(.idle) }
                f.vx = 0
            }
        case .air:
            f.vy -= 22 * dt
            if f.move == nil && (intent.kick || intent.punch) {
                let m = intent.kick ? KMoves.jumpKick : KMoves.jumpPunch
                f.move = m
                f.moveHit = false
                f.stateTime = 0
                f.rig.play(m.clip, duration: m.total, restart: true)
                AudioDirector.shared.play(.whoosh, volume: 0.5)
            }
            if let m = f.move, !f.moveHit, f.stateTime >= m.startup, f.stateTime < m.startup + m.active {
                tryHit(index, move: m)
            }
            if f.y <= 0 && f.vy <= 0 {
                f.y = 0
                f.vy = 0
                f.move = nil
                f.setState(.idle)
                f.rig.play(.land, restart: true)
                FX.spawn(.dust, at: SIMD3<Float>(f.x, 0.02, 0), in: scene, scale: 0.5)
            }
        case .attack:
            guard let m = f.move else {
                f.setState(.idle)
                break
            }
            let t = f.stateTime
            if t < m.startup + m.active {
                f.vx = f.facing * m.lunge
            } else {
                f.vx *= 0.8
            }
            if !f.moveHit && t >= m.startup && t < m.startup + m.active {
                tryHit(index, move: m)
            }
            // Kombo-Ketten
            if f.moveConnected && t >= m.startup && t < m.total - 0.03 && (intent.punch || intent.kick) {
                if let next = KMoves.chain(after: m.name, punch: intent.punch) {
                    startMove(f, next)
                    return
                }
            }
            if t >= m.total {
                f.move = nil
                f.setState(.idle)
            }
        case .special:
            updateSpecial(index, dt: dt)
        case .hitstun, .blockstun:
            f.stun -= dt
            if f.juggled || !f.grounded {
                f.vy -= 22 * dt
                if f.y <= 0 && f.vy <= 0 {
                    f.y = 0
                    f.vy = 0
                    f.juggled = false
                    f.setState(.knockdown)
                    f.rig.play(.knockdown, restart: true)
                    FX.spawn(.dust, at: SIMD3<Float>(f.x, 0.02, 0), in: scene, scale: 0.8)
                    AudioDirector.shared.play(.bodyFall)
                    shake.add(0.25)
                }
            } else if f.stun <= 0 {
                f.setState(.idle)
            }
            f.vx *= Swift.max(0, 1 - 5 * dt)
        case .knockdown:
            f.vx *= Swift.max(0, 1 - 6 * dt)
            if f.stateTime > 0.5 && f.rig.currentClip != .lieDown && f.rig.clipFinished { f.rig.play(.lieDown) }
            if f.stateTime > 1.0 {
                f.setState(.getUp)
                f.invuln = 0.7
                f.rig.play(.getUp, restart: true)
            }
        case .getUp:
            if f.stateTime > 0.6 { f.setState(.idle) }
        case .dizzy, .cinematic, .victory:
            break
        }
        simulateBody(f, dt: dt)
    }

    private func simulateBody(_ f: KFighter, dt: Float) {
        if f.state == .air || f.juggled || f.y > 0 {
            if f.state != .air && f.state != .hitstun && f.state != .blockstun {
                f.vy -= 22 * dt
            }
            f.y = Swift.max(0, f.y + f.vy * dt)
        }
        f.x = clampf(f.x + f.vx * dt, -arena.halfWidth, arena.halfWidth)
    }

    private func separate() {
        let minD: Float = 0.75
        let dx = p2.x - p1.x
        if abs(dx) < minD && abs(p1.y - p2.y) < 1.2 {
            let push = (minD - abs(dx)) * 0.5
            let s: Float = dx >= 0 ? 1 : -1
            p1.x = clampf(p1.x - s * push, -arena.halfWidth, arena.halfWidth)
            p2.x = clampf(p2.x + s * push, -arena.halfWidth, arena.halfWidth)
        }
    }

    private func startMove(_ f: KFighter, _ m: KMoveDef) {
        f.setState(.attack)
        f.move = m
        f.moveHit = false
        f.moveConnected = false
        f.rig.play(m.clip, duration: m.total, restart: true)
        AudioDirector.shared.play(.whoosh, volume: 0.45, pitch: Float.random(in: 0.9...1.15))
    }

    private func tryHit(_ index: Int, move m: KMoveDef) {
        let a = fighters[index]
        let d = fighters[1 - index]
        let dx = d.x - a.x
        guard abs(dx) <= m.reach + 0.3 else { return }
        if abs(dx) > 0.25 && (dx > 0 ? 1 : -1) != a.facing { return }
        if d.invuln > 0 || d.isDown || d.state == .cinematic || d.state == .dizzy { return }
        if m.level == .low && d.y > 0.4 { return }
        if d.y - a.y > 1.6 { return }
        if m.level == .high && d.state == .crouch { return }
        if m.level == .unblockable && (!d.grounded || d.state == .attack) { return }
        a.moveHit = true
        a.moveConnected = true
        // Konter-Haltung
        if d.counterTimer > 0 && m.level != .unblockable {
            d.counterTimer = 0
            showCombo(d, text: "KONTER!")
            applyHit(attacker: 1 - index, damage: 90, knockdown: true, launch: false, level: .unblockable)
            d.rig.play(.uppercut, restart: true)
            return
        }
        applyHit(attacker: index, damage: m.damage, knockdown: m.knockdown, launch: m.launch, level: m.level)
        if m.name == "throw" && d.state == .knockdown {
            // Wurf: Gegner landet hinter dem Angreifer
            d.x = clampf(a.x - a.facing * 1.2, -arena.halfWidth, arena.halfWidth)
            a.rig.play(.throwToss, restart: true)
            FX.spawn(.dust, at: SIMD3<Float>(d.x, 0.05, 0), in: scene, scale: 1.2)
        }
    }

    /// Wendet einen Treffer an (berücksichtigt Block).
    private func applyHit(attacker index: Int, damage base: Float, knockdown: Bool, launch: Bool, level: KHitLevel) {
        let a = fighters[index]
        let d = fighters[1 - index]
        let hitPos = SIMD3<Float>(d.x - a.facing * 0.15, d.y + (level == .low ? 0.4 : 1.35), 0)
        let blocking = d.state == .block || d.state == .blockstun
        var blocked = false
        if blocking {
            switch level {
            case .high, .mid: blocked = true
            case .low: blocked = d.blockLow
            case .overhead: blocked = !d.blockLow
            case .unblockable: blocked = false
            }
        }
        if blocked {
            let chip = base * 0.12 * a.def.stats.power / Swift.max(0.3, d.def.stats.defense)
            d.health = Swift.max(1, d.health - chip)
            d.setState(.blockstun)
            d.stun = 0.16 + base / 900
            d.vx = a.facing * 3.2
            d.rig.flashHit(color: UIColor(red: 0.6, green: 0.8, blue: 1, alpha: 1))
            FX.spawn(.sparks, at: hitPos, in: scene, direction: SIMD3<Float>(-a.facing, 0.3, 0.5), scale: 0.7)
            AudioDirector.shared.play(.block)
            a.meter = Swift.min(100, a.meter + 2)
            d.meter = Swift.min(100, d.meter + 4)
            hitStop = 0.04
            if a.isPlayer || d.isPlayer { Haptics.light() }
            return
        }
        d.comboTaken += 1
        a.comboDealt = d.comboTaken
        a.maxCombo = Swift.max(a.maxCombo, a.comboDealt)
        let scale = Swift.max(0.4, 1 - 0.08 * Float(d.comboTaken - 1))
        let dmg = base * a.def.stats.power / Swift.max(0.3, d.def.stats.defense) * scale
        d.health = Swift.max(0, d.health - dmg)
        a.damageDealt += dmg
        a.meter = Swift.min(100, a.meter + dmg * 0.07)
        d.meter = Swift.min(100, d.meter + dmg * 0.05)
        d.move = nil
        d.rig.flashHit()
        if launch || (!d.grounded && d.state != .knockdown) {
            d.setState(.hitstun)
            d.juggled = true
            d.vy = launch ? 8.5 : Swift.max(d.vy, 5)
            d.y = Swift.max(d.y, 0.05)
            d.vx = a.facing * 1.6
            d.rig.play(.hitHigh, restart: true)
        } else if knockdown {
            d.setState(.hitstun)
            d.juggled = true
            d.vy = 4.5
            d.y = 0.05
            d.vx = a.facing * 4.5
            d.rig.play(.knockdown, restart: true)
        } else {
            d.setState(.hitstun)
            d.stun = 0.3 + base / 450
            d.vx = a.facing * 2.6
            d.rig.play(level == .low ? .hitLow : .hitHigh, restart: true)
        }
        // Saft: Blut, Blitz, Hitstop, Kamera, Sound
        let heavy = base >= 80
        FX.spawn(.hitFlash, at: hitPos, in: scene, scale: heavy ? 1.3 : 0.8)
        FX.spawn(.bloodSpray, at: hitPos, in: scene, direction: SIMD3<Float>(a.facing, 0.5, 0.3), scale: heavy ? 1.1 : 0.7)
        if heavy && settings.bloodEnabled && Float.random(in: 0...1) < 0.5 {
            FX.spawn(.bloodPool, at: SIMD3<Float>(d.x, 0.02, Float.random(in: -0.4...0.4)), in: scene, scale: 0.6)
        }
        hitStop = heavy ? 0.11 : 0.06
        shake.add(heavy ? 0.45 : 0.22)
        AudioDirector.shared.play(heavy ? .punchHeavy : .punchLight)
        if heavy { AudioDirector.shared.play(.boneCrack, volume: 0.6) }
        if a.isPlayer || d.isPlayer {
            if heavy { Haptics.heavy() } else { Haptics.medium() }
        }
        if d.comboTaken >= 2 {
            let words = ["", "", "", "BRUTAL!", "GNADENLOS!", "BLUTRAUSCH!", "UNAUFHALTSAM!", "VERNICHTEND!"]
            let w = d.comboTaken < words.count ? words[d.comboTaken] : "LEGENDÄR!"
            showCombo(a, text: "\(d.comboTaken) TREFFER" + (w.isEmpty ? "" : "  \(w)"))
        }
    }

    private func showCombo(_ f: KFighter, text: String) {
        guard f.isPlayer else { return }
        hud.comboText = text
        comboTextTimer = 1.4
    }

    // MARK: Specials

    private func startSpecial(_ f: KFighter, index: Int) {
        guard index < f.def.specials.count else { return }
        let s = f.def.specials[index]
        f.cooldowns[index] = s.cooldown
        f.setState(.special)
        f.specialIndex = index
        f.specialDone = false
        f.specialStep = 0
        f.vx = 0
        switch s.kind {
        case .dashStrike: f.rig.play(.dashStrike, duration: 0.6, restart: true)
        case .grabSlam: f.rig.play(.grab, duration: 0.5, restart: true)
        case .counter:
            f.rig.play(.block, restart: true)
            f.counterTimer = 0.7
        default: f.rig.play(.cast, duration: 0.45, restart: true)
        }
        AudioDirector.shared.play(s.sound)
        if f.isPlayer { Haptics.light() }
    }

    private func updateSpecial(_ index: Int, dt: Float) {
        let f = fighters[index]
        let o = fighters[1 - index]
        let s = f.def.specials[f.specialIndex]
        let t = f.stateTime
        let dist = abs(o.x - f.x)
        func finish(at end: Float) {
            if t >= end {
                f.rig.node.isHidden = false
                f.setState(.idle)
            }
        }
        switch s.kind {
        case .projectile:
            if f.specialStep == 0 && t >= 0.18 {
                f.specialStep = 1
                spawnProjectile(owner: index, def: s, low: false)
            }
            finish(at: 0.5)
        case .groundWave:
            if f.specialStep == 0 && t >= 0.2 {
                f.specialStep = 1
                spawnProjectile(owner: index, def: s, low: true)
                shake.add(0.2)
            }
            finish(at: 0.55)
        case .dashStrike:
            if t >= 0.12 && t < 0.42 {
                f.vx = f.facing * 14
                if !f.specialDone && dist < 1.4 && (o.x - f.x) * f.facing > -0.2 {
                    f.specialDone = true
                    f.vx = 0
                    applyHit(attacker: index, damage: s.damage, knockdown: true, launch: false, level: .mid)
                }
            } else {
                f.vx *= 0.7
            }
            finish(at: 0.65)
        case .teleportStrike:
            if f.specialStep == 0 && t >= 0.15 {
                f.specialStep = 1
                FX.spawn(.shadowBurst, at: SIMD3<Float>(f.x, 1, 0), in: scene, color: s.color)
                f.rig.node.isHidden = true
            }
            if f.specialStep == 1 && t >= 0.35 {
                f.specialStep = 2
                let side: Float = f.x < o.x ? 1 : -1
                f.x = clampf(o.x + side * 1.0, -arena.halfWidth, arena.halfWidth)
                f.facing = o.x >= f.x ? 1 : -1
                f.rig.node.isHidden = false
                FX.spawn(.shadowBurst, at: SIMD3<Float>(f.x, 1, 0), in: scene, color: s.color)
                AudioDirector.shared.play(.teleport)
                f.rig.play(.uppercut, duration: 0.35, restart: true)
            }
            if f.specialStep == 2 && t >= 0.42 && !f.specialDone {
                f.specialDone = true
                if abs(o.x - f.x) < 1.7 && !o.isDown && o.state != .cinematic {
                    applyHit(attacker: index, damage: s.damage, knockdown: false, launch: true, level: .overhead)
                }
            }
            finish(at: 0.8)
        case .grabSlam:
            if !f.specialDone && t >= 0.15 {
                f.specialDone = true
                if dist < Swift.min(s.range, 2.2) && o.grounded && !o.isDown && o.state != .cinematic {
                    o.x = clampf(f.x + f.facing * 0.9, -arena.halfWidth, arena.halfWidth)
                    f.rig.play(.throwToss, duration: 0.5, restart: true)
                    applyHit(attacker: index, damage: s.damage, knockdown: true, launch: false, level: .unblockable)
                    FX.spawn(.dust, at: SIMD3<Float>(o.x, 0.05, 0), in: scene, scale: 1.5)
                    shake.add(0.6)
                    AudioDirector.shared.play(.bodyFall)
                }
            }
            finish(at: 0.85)
        case .pullIn:
            if f.specialStep == 0 && t >= 0.15 {
                f.specialStep = 1
                let handPos = f.rig.worldPosition(of: .rHand)
                let strand = pullStrand ?? WebStrand(color: s.color, radius: 0.02)
                if strand.node.parent == nil { scene.rootNode.addChildNode(strand.node) }
                pullStrand = strand
                if dist < s.range && !o.isDown && o.state != .cinematic {
                    strand.isHidden = false
                    strand.update(from: handPos, to: o.rig.worldPosition(of: .chest))
                    pullStrandTimer = 0.35
                    if o.state == .block {
                        FX.spawn(.sparks, at: SIMD3<Float>(o.x, 1.2, 0), in: scene)
                        AudioDirector.shared.play(.block)
                    } else {
                        o.x = clampf(f.x + f.facing * 1.1, -arena.halfWidth, arena.halfWidth)
                        applyHit(attacker: index, damage: s.damage, knockdown: false, launch: false, level: .mid)
                        o.stun = 0.75
                    }
                } else {
                    strand.isHidden = false
                    strand.update(from: handPos, to: handPos + SIMD3<Float>(f.facing * s.range, 0.2, 0))
                    pullStrandTimer = 0.2
                }
            }
            finish(at: 0.55)
        case .counter:
            finish(at: 0.75)
        }
    }

    private func updatePullStrand(dt: Float) {
        guard let s = pullStrand, pullStrandTimer > 0 else { return }
        pullStrandTimer -= dt
        if pullStrandTimer <= 0 { s.isHidden = true }
    }

    private func spawnProjectile(owner: Int, def s: SpecialMoveDef, low: Bool) {
        let f = fighters[owner]
        let visual = ProjectileVisual(color: s.color, radius: low ? 0.35 : 0.22, style: s.kind)
        let y: Float = low ? 0.2 : 1.3
        let p = KProjectile(visual: visual, owner: owner, x: f.x + f.facing * 0.8, y: y, vx: f.facing * (low ? 10 : 13),
                            damage: s.damage, low: low)
        visual.node.simdPosition = SIMD3<Float>(p.x, y, 0)
        scene.rootNode.addChildNode(visual.node)
        projectiles.append(p)
    }

    private func updateProjectiles(dt: Float) {
        for p in projectiles where p.alive {
            p.x += p.vx * dt
            p.life -= dt
            p.visual.node.simdPosition = SIMD3<Float>(p.x, p.y, 0)
            let target = fighters[1 - p.owner]
            if abs(target.x - p.x) < 0.55 && !target.isDown && target.state != .cinematic && target.invuln <= 0 {
                let airborneDodge = p.low ? target.y > 0.3 : target.y > 1.6
                if !airborneDodge {
                    p.alive = false
                    let a = fighters[p.owner]
                    let savedFacing = a.facing
                    a.facing = p.vx >= 0 ? 1 : -1
                    applyHit(attacker: p.owner, damage: p.damage, knockdown: p.low, launch: false, level: p.low ? .low : .mid)
                    a.facing = savedFacing
                    FX.spawn(.explosion, at: SIMD3<Float>(p.x, p.y, 0), in: scene, scale: 0.4)
                }
            }
            if abs(p.x) > arena.halfWidth + 4 || p.life <= 0 { p.alive = false }
        }
        // Zusammenstoß zweier Geschosse
        let live = projectiles.filter { $0.alive }
        if live.count >= 2 {
            for i in 0..<live.count {
                for j in (i + 1)..<live.count where live[i].owner != live[j].owner && abs(live[i].x - live[j].x) < 0.6 {
                    live[i].alive = false
                    live[j].alive = false
                    FX.spawn(.explosion, at: SIMD3<Float>((live[i].x + live[j].x) * 0.5, 1.2, 0), in: scene, scale: 0.6)
                    AudioDirector.shared.play(.explosion, volume: 0.7)
                    shake.add(0.3)
                }
            }
        }
        for p in projectiles where !p.alive { p.visual.node.removeFromParentNode() }
        projectiles.removeAll { !$0.alive }
    }

    // MARK: Darstellung

    private func syncVisuals(dt: Float) {
        for f in fighters where f.state != .cinematic {
            f.rig.node.simdPosition = SIMD3<Float>(f.x, arena.floorY + f.y, 0)
            f.rig.node.simdEulerAngles = SIMD3<Float>(0, f.facing > 0 ? Float.pi / 2 : -Float.pi / 2, 0)
            animate(f)
            f.rig.update(dt: dt)
        }
    }

    private func animate(_ f: KFighter) {
        let c = f.rig.currentClip
        switch f.state {
        case .idle:
            let busyClips: [AnimClip] = [.punch, .punch2, .kick, .kick2, .uppercut, .sweep, .land, .getUp, .cast, .grab, .throwToss, .dashStrike, .taunt]
            let busy = busyClips.contains(c) && !f.rig.clipFinished
            if !busy && c != .fightIdle { f.rig.play(.fightIdle, blend: 0.12) }
        case .walk:
            let want: AnimClip = f.vx * f.facing >= 0 ? .walkForward : .walkBack
            if c != want { f.rig.play(want, blend: 0.1) }
        case .crouch:
            if c != .crouch { f.rig.play(.crouch, blend: 0.08) }
        case .block:
            if c != .block { f.rig.play(.block, blend: 0.06) }
        case .air:
            if f.move == nil && f.vy < 0 && c != .fall && (c != .jump || f.rig.clipFinished) { f.rig.play(.fall, blend: 0.15) }
        case .dizzy:
            if c != .dizzy && (c != .getUp || f.rig.clipFinished) { f.rig.play(.dizzy) }
        default:
            break
        }
    }

    private func fightCamera(dt: Float) {
        let mid = (p1.x + p2.x) * 0.5
        let span = abs(p1.x - p2.x)
        let maxY = Swift.max(p1.y, p2.y)
        let targetPos = SIMD3<Float>(mid, 1.55 + span * 0.04 + maxY * 0.3, arena.cameraDistance + Swift.max(0, span - 3) * 0.5)
        let targetLook = SIMD3<Float>(mid, 1.1 + maxY * 0.35, 0)
        camPos = damp3(camPos, targetPos, lambda: 6, dt: dt)
        camLook = damp3(camLook, targetLook, lambda: 7, dt: dt)
        camFov = damp(camFov, 42, lambda: 4, dt: dt)
    }

    private func applyCamera(dt: Float) {
        let s = shake.update(dt: dt)
        cameraNode.simdPosition = camPos + s.offset
        cameraNode.simdLook(at: camLook + s.offset * 0.5, up: SIMD3<Float>(sinf(s.roll), cosf(s.roll), 0), localFront: SIMD3<Float>(0, 0, -1))
        let fov = CGFloat(camFov)
        if abs(camera.fieldOfView - fov) > 0.05 { camera.fieldOfView = fov }
    }

    private func flashScreen(_ c: UIColor) {
        hud.flashColor = c
        flash = 0.75
        hud.flashOpacity = flash
    }

    private func showBanner(_ text: String, style: BannerStyle, seconds: Float) {
        hud.bannerStyle = style
        hud.banner = text
        bannerTimer = seconds
    }

    private func updateOverlays(dt: Float) {
        if flash > 0 {
            flash = Swift.max(0, flash - Double(dt) * 3.5)
            hud.flashOpacity = flash
        }
        if bannerTimer > 0 {
            bannerTimer -= dt
            if bannerTimer <= 0 { hud.banner = nil }
        }
        if comboTextTimer > 0 {
            comboTextTimer -= dt
            if comboTextTimer <= 0 { hud.comboText = nil }
        }
    }

    private func updateHUD(dt: Float) {
        let h1 = clampf(p1.health / p1.maxHealth, 0, 1)
        let h2 = clampf(p2.health / p2.maxHealth, 0, 1)
        let l1 = clampf(p1.healthLag / p1.maxHealth, 0, 1)
        let l2 = clampf(p2.healthLag / p2.maxHealth, 0, 1)
        if abs(hud.p1Health - h1) > 0.001 { hud.p1Health = h1 }
        if abs(hud.p2Health - h2) > 0.001 { hud.p2Health = h2 }
        if abs(hud.p1HealthLag - l1) > 0.002 { hud.p1HealthLag = l1 }
        if abs(hud.p2HealthLag - l2) > 0.002 { hud.p2HealthLag = l2 }
        let m1 = p1.meter / 100
        let m2 = p2.meter / 100
        if abs(hud.p1Meter - m1) > 0.005 { hud.p1Meter = m1 }
        if abs(hud.p2Meter - m2) > 0.005 { hud.p2Meter = m2 }
        let can = phase == .fight && p1.meter >= 100
        if hud.canBrutal != can { hud.canBrutal = can }
        if hud.timer != timeLeft { hud.timer = timeLeft }
        if hud.p1Rounds != p1.roundsWon && phase != .roundOver { hud.p1Rounds = p1.roundsWon }
        if hud.p2Rounds != p2.roundsWon && phase != .roundOver { hud.p2Rounds = p2.roundsWon }
    }
}
