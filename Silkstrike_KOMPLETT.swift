// SILKSTRIKE – Blutturnier
// Komplettes Spiel in EINER Datei für Swift Playgrounds / Xcode.
// Anleitung: siehe SILKSTRIKE_ANLEITUNG.md
// Automatisch erzeugt aus Silkstrike.swiftpm – nicht von Hand bearbeiten.

import AVFoundation
import Combine
import CoreGraphics
import Foundation
import GameController
import QuartzCore
import SceneKit
import SwiftUI
import UIKit
import simd

// =====================================================================
// MARK: - Core/GameLoop.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Spielschleife
//  CADisplayLink (Main-RunLoop, .common-Modus) mit variabler Bildrate
//  (ProMotion bis 120 Hz). dt = echte Sekunden, auf max. 1/20 s begrenzt.
//
//  Hinweis iPhone: Für mehr als 60 Hz auf ProMotion-iPhones braucht die App
//  den Info.plist-Schlüssel CADisableMinimumFrameDurationOnPhone = YES.
//  iPads mit ProMotion laufen ohne diesen Schlüssel mit 120 Hz.
// =====================================================================

/// Schwache Zwischenstelle: CADisplayLink hält sein Ziel STARK fest.
/// So entsteht kein Retain-Zyklus GameLoop ↔ DisplayLink.
private final class GameLoopDisplayProxy: NSObject {
    weak var owner: GameLoop?

    init(owner: GameLoop) {
        self.owner = owner
        super.init()
    }

    @objc func displayLinkFired(_ link: CADisplayLink) {
        if let owner = owner {
            owner.handleDisplayLink(link)
        } else {
            link.invalidate()
        }
    }
}

final class GameLoop: NSObject {

    /// Wird jeden Frame aufgerufen. dt in Sekunden, begrenzt auf 0.001 ... 1/20.
    var onUpdate: ((Float) -> Void)?

    /// Gewünschte Höchst-Bildrate (performance: 120, balanced: 60/120 je Gerät, ultra: 60).
    /// Siehe `GameLoop.recommendedMaxFPS(for:)`. Änderungen wirken sofort.
    var preferredMaxFPS: Int = 60 {
        didSet {
            let clamped = Swift.max(24, Swift.min(240, preferredMaxFPS))
            if clamped != preferredMaxFPS { preferredMaxFPS = clamped }
            refreshFrameRateRange()
        }
    }

    /// Bei Überhitzung (thermalState .serious/.critical) oder Stromsparmodus die Bildrate drosseln.
    var adaptsToThermalState: Bool = true {
        didSet { refreshFrameRateRange() }
    }

    /// Pausiert die Schleife ohne sie abzubauen (z.B. App im Hintergrund).
    var isPaused: Bool = false {
        didSet {
            displayLink?.isPaused = isPaused
            if !isPaused { lastTimestamp = 0 }
        }
    }

    /// Größtes dt, das an onUpdate geht (verhindert Physik-Explosionen nach Hängern).
    let maxDeltaTime: Float = 1.0 / 20.0

    private(set) var isRunning: Bool = false
    /// Geglättete, tatsächlich gemessene Bildrate (für die FPS-Anzeige).
    private(set) var measuredFPS: Float = 60
    /// Ungeglättete Dauer des letzten Frames in Sekunden.
    private(set) var lastRawDelta: Float = 1.0 / 60.0
    /// Tatsächlich angeforderte Höchst-Bildrate (nach thermischer Drosselung).
    private(set) var effectiveMaxFPS: Int = 60
    /// Anzahl der Frames seit start().
    private(set) var frameCount: UInt64 = 0
    /// Summe aller (begrenzten) dt seit start().
    private(set) var elapsedTime: Double = 0

    private var displayLink: CADisplayLink?
    private var proxy: GameLoopDisplayProxy?
    private var lastTimestamp: CFTimeInterval = 0
    private var smoothedFrameTime: Double = 1.0 / 60.0
    private var thermalCheckTimer: Double = 0
    private var isDispatching = false

    override init() {
        super.init()
    }

    deinit {
        displayLink?.invalidate()
    }

    /// Empfohlene Höchst-Bildrate für eine Qualitätsstufe.
    static func recommendedMaxFPS(for quality: QualityPreset) -> Int {
        switch quality {
        case .performance:
            return 120
        case .balanced:
            let memoryGB = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824.0
            return memoryGB >= 7.5 ? 120 : 60
        case .ultra:
            return 60
        }
    }

    /// Bequem: preferredMaxFPS passend zur Qualitätsstufe setzen.
    func configure(for quality: QualityPreset) {
        preferredMaxFPS = GameLoop.recommendedMaxFPS(for: quality)
    }

    func start() {
        if displayLink != nil {
            isRunning = true
            return
        }
        let p = GameLoopDisplayProxy(owner: self)
        let link = CADisplayLink(target: p, selector: #selector(GameLoopDisplayProxy.displayLinkFired(_:)))
        proxy = p
        displayLink = link
        lastTimestamp = 0
        thermalCheckTimer = 2.0
        frameCount = 0
        elapsedTime = 0
        effectiveMaxFPS = computeEffectiveMaxFPS()
        applyFrameRateRange(to: link)
        link.isPaused = isPaused
        link.add(to: RunLoop.main, forMode: RunLoop.Mode.common)
        isRunning = true
    }

    func stop() {
        displayLink?.invalidate()
        displayLink = nil
        proxy = nil
        lastTimestamp = 0
        isRunning = false
    }

    // MARK: - Intern

    fileprivate func handleDisplayLink(_ link: CADisplayLink) {
        let now = link.timestamp
        var raw: Double
        if lastTimestamp <= 0 {
            raw = link.duration > 0 ? link.duration : 1.0 / 60.0
        } else {
            raw = now - lastTimestamp
        }
        lastTimestamp = now
        if !raw.isFinite || raw < 0 { raw = 0 }

        // FPS-Messung (große Lücken wie Rückkehr aus dem Hintergrund ignorieren)
        if raw > 0.0005 && raw < 0.25 {
            smoothedFrameTime += (raw - smoothedFrameTime) * 0.08
            if smoothedFrameTime > 0.0001 {
                measuredFPS = Float(1.0 / smoothedFrameTime)
            }
        }
        lastRawDelta = Float(raw)
        frameCount &+= 1

        // Thermik / Stromsparmodus alle 2 Sekunden prüfen
        thermalCheckTimer -= Swift.min(raw, 0.25)
        if thermalCheckTimer <= 0 {
            thermalCheckTimer = 2.0
            let eff = computeEffectiveMaxFPS()
            if eff != effectiveMaxFPS {
                effectiveMaxFPS = eff
                applyFrameRateRange(to: link)
            }
        }

        let dtD = Swift.min(Swift.max(raw, 0.001), Double(maxDeltaTime))
        elapsedTime += dtD

        // Kein Wiedereintritt (falls onUpdate z.B. einen modalen Vorgang auslöst)
        guard !isDispatching else { return }
        isDispatching = true
        onUpdate?(Float(dtD))
        isDispatching = false
    }

    private func computeEffectiveMaxFPS() -> Int {
        var cap = Swift.max(24, preferredMaxFPS)
        if adaptsToThermalState {
            let info = ProcessInfo.processInfo
            let state = info.thermalState
            if state == .critical {
                cap = Swift.min(cap, 30)
            } else if state == .serious {
                cap = Swift.min(cap, 60)
            }
            if info.isLowPowerModeEnabled {
                cap = Swift.min(cap, 60)
            }
        }
        return cap
    }

    private func refreshFrameRateRange() {
        guard let link = displayLink else { return }
        let eff = computeEffectiveMaxFPS()
        effectiveMaxFPS = eff
        applyFrameRateRange(to: link)
    }

    private func applyFrameRateRange(to link: CADisplayLink) {
        let maxF = Float(effectiveMaxFPS)
        // Bei 120 Hz darf das System bis 80 Hz absenken; darunter feste Rate (keine Ruckel-Sprünge).
        let minF: Float = effectiveMaxFPS >= 100 ? 80 : maxF
        link.preferredFrameRateRange = CAFrameRateRange(minimum: minF, maximum: maxF, preferred: maxF)
    }
}

// =====================================================================
// MARK: - Core/Input.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Eingabe
//  Touch-Steuerung (UI), Gamecontroller (MFi / Xbox / PlayStation) und
//  Hardware-Tastatur schreiben alle in denselben InputState.
//  Die Szenen-Controller lesen nur ihre eigenen Aktionen.
//
//  Belegung Gamecontroller (Xbox-Namen, PlayStation in Klammern):
//    Linker Stick / Steuerkreuz → move        Rechter Stick → Kamera (addLook)
//    A (✕)  : Springen   | Tritt
//    X (□)  : Angriff    | Schlag
//    Y (△)  : Aktion     | Spezial 1
//    B (○)  : Netzsprint | Spezial 2  (+ Überspringen)
//    RT (R2): Netz (halten = schwingen) | Block (halten)
//    LT (L2): Netzsprint | Brutal-Schlag
//    RB (R1): Netz       | Exekution
//    LB (L1): Aktion     | Exekution
//    Menü ≡ (Options): Pause      Ansicht ⧉ (Share/Create): Überspringen
//
//  Tastatur: WASD bewegen, Pfeiltasten Kamera, Leertaste springen,
//    Shift Netz/Block, J Angriff/Schlag, K Tritt, L Block/Netz, Q Netzsprint,
//    E Aktion/Exekution, U Spezial 1, I Spezial 2, O Brutal, F Exekution,
//    Esc Pause, Enter Überspringen.
// =====================================================================

// MARK: - Aktionen

enum GameButton: String, CaseIterable, Hashable {
    case jump, web, zip, attack, interact          // offene Welt
    case punch, kick, block, special1, special2, brutal, execute   // Kombat
    case pause, skip

    /// Deutscher Name für Buttons / Hilfetexte.
    var germanLabel: String {
        switch self {
        case .jump: return "Springen"
        case .web: return "Netz"
        case .zip: return "Netzsprint"
        case .attack: return "Angriff"
        case .interact: return "Aktion"
        case .punch: return "Schlag"
        case .kick: return "Tritt"
        case .block: return "Block"
        case .special1: return "Spezial 1"
        case .special2: return "Spezial 2"
        case .brutal: return "Brutal-Schlag"
        case .execute: return "Exekution"
        case .pause: return "Pause"
        case .skip: return "Überspringen"
        }
    }

    /// Kurzer Hinweis auf die Controller-Taste (Xbox-Beschriftung).
    var padHint: String {
        switch self {
        case .jump: return "A"
        case .web: return "RT"
        case .zip: return "LT"
        case .attack: return "X"
        case .interact: return "Y"
        case .punch: return "X"
        case .kick: return "A"
        case .block: return "RT"
        case .special1: return "Y"
        case .special2: return "B"
        case .brutal: return "LT"
        case .execute: return "RB"
        case .pause: return "≡"
        case .skip: return "B"
        }
    }

    /// Kurzer Hinweis auf die Tastatur-Taste.
    var keyHint: String {
        switch self {
        case .jump: return "Leertaste"
        case .web: return "Shift"
        case .zip: return "Q"
        case .attack: return "J"
        case .interact: return "E"
        case .punch: return "J"
        case .kick: return "K"
        case .block: return "L"
        case .special1: return "U"
        case .special2: return "I"
        case .brutal: return "O"
        case .execute: return "F"
        case .pause: return "Esc"
        case .skip: return "Enter"
        }
    }
}

// MARK: - Eingabezustand

/// Gemeinsamer Eingabezustand. Alles läuft auf dem Main-Thread.
///
/// - `move`: virtueller Joystick / linker Stick, x = rechts, y = vorwärts, Länge <= 1.
/// - Look-Delta in Bildschirm-Pixeln, UIKit-Konvention: +x = Finger nach rechts, +y = Finger nach unten.
///   Der rechte Stick liefert dieselbe Konvention (Stick nach oben = negatives y).
/// - Tasten: `isDown` = gehalten, `consumePress` = genau einmal pro Druck (Flanke),
///   `pressBuffered` = Eingabepuffer für Kombos. Nicht abgeholte Drücke verfallen nach `pressExpiry` Sekunden.
final class InputState {

    /// Woher ein Tastendruck kommt (Touch-UI oder Gerät = Controller/Tastatur).
    enum Source {
        case touch
        case device
    }

    /// Bewegung: x = rechts, y = vorwärts. Wird automatisch auf Länge <= 1 begrenzt, NaN → 0.
    var move: SIMD2<Float> = SIMD2<Float>(0, 0) {
        didSet {
            if !move.x.isFinite || !move.y.isFinite {
                move = SIMD2<Float>(0, 0)
                return
            }
            let len2 = move.x * move.x + move.y * move.y
            if len2 > 1 {
                move = move / len2.squareRoot()
            }
        }
    }

    /// Länge von move (0...1).
    var moveMagnitude: Float {
        return (move.x * move.x + move.y * move.y).squareRoot()
    }

    /// Nicht abgeholte Tastendrücke verfallen nach so vielen Sekunden (verhindert "alte" Aktionen).
    var pressExpiry: Double = 0.6

    /// true, sobald Controller/Tastatur benutzt werden; false nach dem nächsten Touch-Druck.
    /// Die UI kann damit die Touch-Buttons ausblenden.
    var controllerActive: Bool = false

    /// Zeitpunkt (CACurrentMediaTime) der letzten Eingabe irgendeiner Art.
    private(set) var lastInputTime: Double = 0

    private var touchHeld = Set<GameButton>()
    private var deviceHeld = Set<GameButton>()
    private var downSince: [GameButton: Double] = [:]
    private var pendingPresses: [GameButton: [Double]] = [:]
    private var pendingReleases: [GameButton: Double] = [:]
    private var lastTouchPressCall: [GameButton: Double] = [:]

    private var lookAccum = SIMD2<Float>(0, 0)
    private var lookWindowStart: Double = 0
    private let maxLookAccum: Float = 6000
    private let maxQueuedPresses = 3

    init() {}

    // MARK: Kamera

    /// Look-Delta hinzufügen (Pixel; rechte Bildschirmhälfte ziehen oder rechter Stick).
    func addLook(_ delta: SIMD2<Float>) {
        guard delta.x.isFinite, delta.y.isFinite else { return }
        let now = CACurrentMediaTime()
        // Wird nichts abgeholt (z.B. Kombat), nicht endlos ansammeln → kein Kamerasprung später.
        if now - lookWindowStart > 0.3 {
            lookAccum = SIMD2<Float>(0, 0)
            lookWindowStart = now
        }
        lookAccum += delta
        lookAccum.x = clampf(lookAccum.x, -maxLookAccum, maxLookAccum)
        lookAccum.y = clampf(lookAccum.y, -maxLookAccum, maxLookAccum)
        if delta.x != 0 || delta.y != 0 { lastInputTime = now }
    }

    /// Liefert das gesammelte Look-Delta seit dem letzten Aufruf und setzt es zurück.
    func consumeLook() -> SIMD2<Float> {
        let v = lookAccum
        lookAccum = SIMD2<Float>(0, 0)
        lookWindowStart = CACurrentMediaTime()
        return v
    }

    // MARK: Tasten (Touch-API)

    /// Touch-Button gedrückt. Mehrfachaufrufe ohne release() erzeugen keine Dauerfeuer-Flanken;
    /// ein erneuter Aufruf nach > 0,3 s Pause zählt aber als neuer Tipp (für UIs ohne release()).
    func press(_ b: GameButton) {
        let now = CACurrentMediaTime()
        controllerActive = false
        if touchHeld.contains(b) {
            let last = lastTouchPressCall[b] ?? 0
            lastTouchPressCall[b] = now
            if now - last > 0.3 {
                registerPress(b, at: now)
            }
            return
        }
        lastTouchPressCall[b] = now
        setHeld(b, down: true, source: .touch, now: now)
    }

    /// Touch-Button losgelassen.
    func release(_ b: GameButton) {
        lastTouchPressCall[b] = nil
        guard touchHeld.contains(b) else { return }
        setHeld(b, down: false, source: .touch, now: CACurrentMediaTime())
    }

    /// Wird die Aktion gerade gehalten (Touch ODER Gerät)?
    func isDown(_ b: GameButton) -> Bool {
        return touchHeld.contains(b) || deviceHeld.contains(b)
    }

    /// Wie lange die Aktion schon gehalten wird (0, wenn nicht gehalten).
    func heldDuration(_ b: GameButton) -> Double {
        guard isDown(b), let t = downSince[b] else { return 0 }
        return Swift.max(0, CACurrentMediaTime() - t)
    }

    /// Alle aktuell gehaltenen Aktionen.
    var heldButtons: Set<GameButton> {
        return touchHeld.union(deviceHeld)
    }

    /// true genau einmal pro Druck (Flanke). Mehrere schnelle Tipps werden nacheinander geliefert.
    func consumePress(_ b: GameButton) -> Bool {
        guard var list = pendingPresses[b], !list.isEmpty else { return false }
        let cutoff = CACurrentMediaTime() - pressExpiry
        list.removeAll(where: { $0 < cutoff })
        if list.isEmpty {
            pendingPresses[b] = nil
            return false
        }
        list.removeFirst()
        pendingPresses[b] = list.isEmpty ? nil : list
        return true
    }

    /// Eingabepuffer: wurde die Aktion in den letzten `seconds` Sekunden gedrückt und noch nicht abgeholt?
    /// Wenn ja, wird dieser Druck (und ältere) verbraucht und true geliefert.
    func pressBuffered(_ b: GameButton, within seconds: Double) -> Bool {
        guard let list = pendingPresses[b], !list.isEmpty else { return false }
        let cutoff = CACurrentMediaTime() - Swift.max(0, seconds)
        guard let idx = list.firstIndex(where: { $0 >= cutoff }) else { return false }
        let rest = Array(list[(idx + 1)...])
        pendingPresses[b] = rest.isEmpty ? nil : rest
        return true
    }

    /// Wie pressBuffered, verbraucht aber nichts.
    func peekPress(_ b: GameButton, within seconds: Double) -> Bool {
        guard let list = pendingPresses[b], let newest = list.last else { return false }
        return newest >= CACurrentMediaTime() - Swift.max(0, seconds)
    }

    /// true genau einmal, nachdem die Aktion losgelassen wurde (z.B. Netz loslassen, Aufladeangriff).
    func consumeRelease(_ b: GameButton) -> Bool {
        guard let t = pendingReleases[b] else { return false }
        pendingReleases[b] = nil
        return CACurrentMediaTime() - t <= pressExpiry
    }

    /// Verwirft nur die noch nicht abgeholten Drücke/Loslassen (gehaltene Tasten bleiben gehalten).
    func clearPendingPresses() {
        pendingPresses.removeAll()
        pendingReleases.removeAll()
    }

    /// Alles zurücksetzen (beim Szenenwechsel aufrufen). Physisch noch gehaltene Controller-Tasten
    /// zählen erst nach erneutem Drücken wieder.
    func reset() {
        move = SIMD2<Float>(0, 0)
        lookAccum = SIMD2<Float>(0, 0)
        lookWindowStart = CACurrentMediaTime()
        touchHeld.removeAll()
        deviceHeld.removeAll()
        downSince.removeAll()
        pendingPresses.removeAll()
        pendingReleases.removeAll()
        lastTouchPressCall.removeAll()
    }

    // MARK: Quellen-API (Controller, eigene virtuelle Steuerungen)

    /// Setzt den Haltezustand einer Aktion für eine Quelle. Erzeugt Druck-/Loslass-Flanken,
    /// wenn sich der Gesamtzustand (Touch ODER Gerät) ändert.
    func setHeld(_ b: GameButton, down: Bool, source: Source, now: Double) {
        let wasDown = isDown(b)
        switch source {
        case .touch:
            if down { touchHeld.insert(b) } else { touchHeld.remove(b) }
        case .device:
            if down { deviceHeld.insert(b) } else { deviceHeld.remove(b) }
        }
        let nowDown = isDown(b)
        if nowDown && !wasDown {
            downSince[b] = now
            registerPress(b, at: now)
        } else if !nowDown && wasDown {
            downSince[b] = nil
            pendingReleases[b] = now
        }
        lastInputTime = now
    }

    private func registerPress(_ b: GameButton, at t: Double) {
        var list = pendingPresses[b] ?? []
        list.append(t)
        if list.count > maxQueuedPresses {
            list.removeFirst(list.count - maxQueuedPresses)
        }
        pendingPresses[b] = list
        lastInputTime = t
    }
}

// MARK: - Gamecontroller & Tastatur

/// Verbindet MFi-/Xbox-/PlayStation-Controller und Hardware-Tastaturen mit dem InputState.
/// `poll()` jeden Frame VOR dem Szenen-Update aufrufen.
final class ControllerBridge {
    let input: InputState

    /// Rechter Stick voll ausgelenkt ≈ so viele Pixel Drag pro Sekunde.
    var lookPixelsPerSecond: Float = 900
    /// Radiale Totzone der Sticks (0...0.9).
    var stickDeadzone: Float = 0.16
    /// Hardware-Tastatur (iPad mit Tastatur / Mac) mit abfragen.
    var keyboardEnabled: Bool = true

    /// Wird aufgerufen, wenn ein Controller verbunden (true) oder getrennt (false) wird.
    var onConnectionChanged: ((Bool) -> Void)?

    private(set) var isConnected: Bool = false
    private(set) var controllerName: String? = nil

    private weak var controller: GCController?
    private var observers: [NSObjectProtocol] = []
    private var prevDown = Set<GameButton>()
    private var ownsMove = false
    private var started = false
    private var lastPollTime: Double = 0
    private var rescanTimer: Float = 0

    init(input: InputState) {
        self.input = input
    }

    deinit {
        let nc = NotificationCenter.default
        for token in observers {
            nc.removeObserver(token)
        }
    }

    func start() {
        guard !started else { return }
        started = true
        let nc = NotificationCenter.default
        let names: [Notification.Name] = [
            .GCControllerDidConnect,
            .GCControllerDidDisconnect,
            .GCControllerDidBecomeCurrent,
            .GCControllerDidStopBeingCurrent
        ]
        for name in names {
            let token = nc.addObserver(forName: name, object: nil, queue: OperationQueue.main) { [weak self] _ in
                self?.refreshController()
            }
            observers.append(token)
        }
        refreshController()
        lastPollTime = CACurrentMediaTime()
    }

    func stop() {
        let nc = NotificationCenter.default
        for token in observers {
            nc.removeObserver(token)
        }
        observers.removeAll()
        started = false
        releaseEverything()
    }

    /// Jeden Frame aufrufen: Sticks → input.move / addLook, Tasten → Halten/Loslassen.
    func poll() {
        let now = CACurrentMediaTime()
        var dt = Float(now - lastPollTime)
        lastPollTime = now
        if !dt.isFinite || dt <= 0 { dt = 1.0 / 60.0 }
        dt = Swift.min(dt, 1.0 / 20.0)

        // Falls eine Verbindungs-Benachrichtigung verpasst wurde: gelegentlich neu suchen.
        if controller == nil || controller?.extendedGamepad == nil {
            rescanTimer -= dt
            if rescanTimer <= 0 {
                rescanTimer = 1.0
                refreshController()
            }
        }

        var down = Set<GameButton>()
        var moveVec = SIMD2<Float>(0, 0)
        var lookRate = SIMD2<Float>(0, 0)   // -1...1 je Achse, Bildschirm-Konvention (+y = nach unten)

        if let pad = controller?.extendedGamepad {
            readGamepad(pad, down: &down, move: &moveVec, look: &lookRate)
        }
        if keyboardEnabled, let kb = GCKeyboard.coalesced?.keyboardInput {
            readKeyboard(kb, down: &down, move: &moveVec, look: &lookRate)
        }

        // Tasten: nur echte Flanken weitergeben.
        if down != prevDown {
            let released = prevDown.subtracting(down)
            let pressed = down.subtracting(prevDown)
            for b in released {
                input.setHeld(b, down: false, source: .device, now: now)
            }
            for b in pressed {
                input.setHeld(b, down: true, source: .device, now: now)
            }
            prevDown = down
            if !pressed.isEmpty { input.controllerActive = true }
        }

        // Bewegung: nur überschreiben, solange das Gerät wirklich steuert (Touch-Joystick bleibt sonst unberührt).
        if simd_length_squared(moveVec) > 0.0001 {
            input.move = moveVec
            ownsMove = true
            input.controllerActive = true
        } else if ownsMove {
            input.move = SIMD2<Float>(0, 0)
            ownsMove = false
        }

        // Kamera
        if simd_length_squared(lookRate) > 0 {
            input.addLook(lookRate * (lookPixelsPerSecond * dt))
            input.controllerActive = true
        }
    }

    // MARK: Intern

    private func refreshController() {
        var chosen: GCController? = nil
        if let current = GCController.current, current.extendedGamepad != nil {
            chosen = current
        } else {
            chosen = GCController.controllers().first(where: { $0.extendedGamepad != nil })
        }
        let changed = chosen !== controller
        controller = chosen
        if changed, let c = chosen {
            c.playerIndex = .index1
        }
        controllerName = chosen?.vendorName
        let connected = (chosen != nil)
        if connected != isConnected {
            isConnected = connected
            if !connected { releaseEverything() }
            onConnectionChanged?(connected)
        }
    }

    private func releaseEverything() {
        let now = CACurrentMediaTime()
        for b in prevDown {
            input.setHeld(b, down: false, source: .device, now: now)
        }
        prevDown.removeAll()
        if ownsMove {
            input.move = SIMD2<Float>(0, 0)
            ownsMove = false
        }
    }

    /// Radiale Totzone mit Neuskalierung → weiche Kontrolle ab dem ersten Millimeter.
    private func shapedStick(_ raw: SIMD2<Float>) -> SIMD2<Float> {
        guard raw.x.isFinite, raw.y.isFinite else { return SIMD2<Float>(0, 0) }
        let dz = clampf(stickDeadzone, 0, 0.9)
        let len = simd_length(raw)
        if len <= dz || len < 1e-5 { return SIMD2<Float>(0, 0) }
        let scaled = clampf((len - dz) / (1 - dz), 0, 1)
        return raw * (scaled / len)
    }

    private func readGamepad(_ pad: GCExtendedGamepad,
                             down: inout Set<GameButton>,
                             move: inout SIMD2<Float>,
                             look: inout SIMD2<Float>) {
        // Bewegung: Stick hat Vorrang, sonst Steuerkreuz (beliebt bei Kampfspielen).
        let ls = shapedStick(SIMD2<Float>(pad.leftThumbstick.xAxis.value, pad.leftThumbstick.yAxis.value))
        let dp = SIMD2<Float>(pad.dpad.xAxis.value, pad.dpad.yAxis.value)
        if simd_length_squared(ls) > 0 {
            move = ls
        } else if simd_length_squared(dp) > 0.25 {
            move = safeNormalize2(dp, fallback: SIMD2<Float>(0, 0))
        }

        // Kamera: Ansprechkurve für feines Zielen, voller Ausschlag = schnell.
        let rs = shapedStick(SIMD2<Float>(pad.rightThumbstick.xAxis.value, pad.rightThumbstick.yAxis.value))
        let mag = simd_length(rs)
        if mag > 0 {
            let curved = powf(mag, 1.7)
            let dir = rs / mag
            look += SIMD2<Float>(dir.x, -dir.y) * curved
        }

        // Tasten (eine physische Taste löst die Welt- UND die Kombat-Aktion aus;
        // jede Szene liest nur ihre eigenen Aktionen).
        if pad.buttonA.isPressed { down.insert(.jump); down.insert(.kick) }
        if pad.buttonX.isPressed { down.insert(.attack); down.insert(.punch) }
        if pad.buttonY.isPressed { down.insert(.interact); down.insert(.special1) }
        if pad.buttonB.isPressed { down.insert(.zip); down.insert(.special2); down.insert(.skip) }
        if pad.rightTrigger.isPressed { down.insert(.web); down.insert(.block) }
        if pad.leftTrigger.isPressed { down.insert(.zip); down.insert(.brutal) }
        if pad.rightShoulder.isPressed { down.insert(.web); down.insert(.execute) }
        if pad.leftShoulder.isPressed { down.insert(.interact); down.insert(.execute) }
        if pad.buttonMenu.isPressed { down.insert(.pause) }
        if let options = pad.buttonOptions, options.isPressed { down.insert(.skip) }
    }

    private func readKeyboard(_ kb: GCKeyboardInput,
                              down: inout Set<GameButton>,
                              move: inout SIMD2<Float>,
                              look: inout SIMD2<Float>) {
        func key(_ code: GCKeyCode) -> Bool {
            return kb.button(forKeyCode: code)?.isPressed ?? false
        }

        var k = SIMD2<Float>(0, 0)
        if key(.keyW) { k.y += 1 }
        if key(.keyS) { k.y -= 1 }
        if key(.keyD) { k.x += 1 }
        if key(.keyA) { k.x -= 1 }
        if simd_length_squared(k) > 0 && simd_length_squared(move) == 0 {
            move = safeNormalize2(k, fallback: SIMD2<Float>(0, 0))
        }

        var l = SIMD2<Float>(0, 0)
        if key(.rightArrow) { l.x += 1 }
        if key(.leftArrow) { l.x -= 1 }
        if key(.upArrow) { l.y -= 1 }      // nach oben schauen = wie Finger nach oben ziehen
        if key(.downArrow) { l.y += 1 }
        if simd_length_squared(l) > 0 {
            look += safeNormalize2(l, fallback: SIMD2<Float>(0, 0)) * 0.75
        }

        if key(.spacebar) { down.insert(.jump) }
        if key(.leftShift) { down.insert(.web); down.insert(.block) }
        if key(.keyJ) { down.insert(.attack); down.insert(.punch) }
        if key(.keyK) { down.insert(.kick) }
        if key(.keyL) { down.insert(.block); down.insert(.web) }
        if key(.keyQ) { down.insert(.zip) }
        if key(.keyE) { down.insert(.interact); down.insert(.execute) }
        if key(.keyU) { down.insert(.special1) }
        if key(.keyI) { down.insert(.special2) }
        if key(.keyO) { down.insert(.brutal) }
        if key(.keyF) { down.insert(.execute) }
        if key(.escape) { down.insert(.pause) }
        if key(.returnOrEnter) { down.insert(.skip) }
    }
}

// =====================================================================
// MARK: - Core/MathUtils.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Mathe-Werkzeuge
//  Der EINZIGE Ort für diese globalen Funktionsnamen (siehe SPEC).
//
//  Konventionen im ganzen Spiel:
//  - Y zeigt nach oben, Figuren schauen lokal nach +Z.
//  - Yaw = Drehung um +Y (simdEulerAngles.y), alle Winkel in Radiant.
//  - Richtung aus Yaw: (sin yaw, 0, cos yaw)  ·  Yaw aus Richtung: atan2(x, z)
// =====================================================================

// MARK: - Skalare

/// Begrenzt v auf [lo, hi]. NaN wird zu lo.
func clampf(_ v: Float, _ lo: Float, _ hi: Float) -> Float {
    if v.isNaN { return lo }
    return Swift.min(Swift.max(v, lo), hi)
}

/// Lineare Interpolation (t wird NICHT begrenzt).
func lerpf(_ a: Float, _ b: Float, _ t: Float) -> Float {
    return a + (b - a) * t
}

/// Lineare Interpolation für Vektoren (t wird NICHT begrenzt).
func lerp3(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ t: Float) -> SIMD3<Float> {
    return a + (b - a) * t
}

/// Interner Faktor für bildratenunabhängiges Glätten: 1 - e^(-λ·dt), immer in [0, 1].
private func silkMathDampAlpha(_ lambda: Float, _ dt: Float) -> Float {
    let l = Swift.max(0, lambda)
    let d = Swift.max(0, dt)
    let a = 1 - expf(-l * d)
    if !a.isFinite { return 1 }
    return Swift.min(Swift.max(a, 0), 1)
}

/// Exponentielles Glätten, unabhängig von der Bildrate.
/// lambda ≈ Reaktionsgeschwindigkeit in 1/s (4 = weich, 10 = zügig, 25 = fast sofort).
func damp(_ current: Float, _ target: Float, lambda: Float, dt: Float) -> Float {
    return lerpf(current, target, silkMathDampAlpha(lambda, dt))
}

/// Exponentielles Glätten für Vektoren (Kamera, Positionen).
func damp3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, lambda: Float, dt: Float) -> SIMD3<Float> {
    return lerp3(current, target, silkMathDampAlpha(lambda, dt))
}

/// Wie damp, aber für Winkel: nimmt immer den kürzeren Weg über ±π. Ergebnis in (-π, π].
func dampAngle(_ current: Float, _ target: Float, lambda: Float, dt: Float) -> Float {
    let delta = wrapAngle(target - current)
    return wrapAngle(current + delta * silkMathDampAlpha(lambda, dt))
}

/// Normalisiert einen Winkel auf (-π, π].
func wrapAngle(_ a: Float) -> Float {
    guard a.isFinite else { return 0 }
    let twoPi = Float.pi * 2
    var r = (a + Float.pi).truncatingRemainder(dividingBy: twoPi)
    if r <= 0 { r += twoPi }
    return r - Float.pi
}

func deg2rad(_ d: Float) -> Float {
    return d * Float.pi / 180
}

func rad2deg(_ r: Float) -> Float {
    return r * 180 / Float.pi
}

/// Umkehrung von lerpf: liefert t, sodass lerpf(a, b, t) == v (nicht begrenzt). a == b → 0.
func inverseLerpf(_ a: Float, _ b: Float, _ v: Float) -> Float {
    let d = b - a
    if Swift.abs(d) < 1e-12 { return 0 }
    return (v - a) / d
}

/// Bildet v von [inLo, inHi] auf [outLo, outHi] ab und begrenzt das Ergebnis auf diesen Bereich.
func remapClampedf(_ v: Float, _ inLo: Float, _ inHi: Float, _ outLo: Float, _ outHi: Float) -> Float {
    let t = clampf(inverseLerpf(inLo, inHi, v), 0, 1)
    return lerpf(outLo, outHi, t)
}

/// Weiche S-Kurve (Hermite) zwischen edge0 und edge1, Ergebnis 0...1.
func smoothRampf(_ edge0: Float, _ edge1: Float, _ x: Float) -> Float {
    let t = clampf(inverseLerpf(edge0, edge1, x), 0, 1)
    return t * t * (3 - 2 * t)
}

/// Bewegt current höchstens um maxDelta in Richtung target (kein Überschießen).
func moveTowardf(_ current: Float, _ target: Float, maxDelta: Float) -> Float {
    let diff = target - current
    let step = Swift.max(0, maxDelta)
    if Swift.abs(diff) <= step { return target }
    return current + (diff > 0 ? step : -step)
}

/// Kritisch gedämpfte Feder (wie Unitys SmoothDamp). velocity wird mitgeführt.
/// smoothTime ≈ Zeit in Sekunden, um das Ziel ungefähr zu erreichen.
func smoothDampf(_ current: Float, _ target: Float, velocity: inout Float, smoothTime: Float, dt: Float) -> Float {
    guard dt > 0 else { return current }
    let st = Swift.max(0.0001, smoothTime)
    let omega = 2 / st
    let x = omega * dt
    let expo = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    let change = current - target
    let temp = (velocity + omega * change) * dt
    velocity = (velocity - omega * temp) * expo
    var output = target + (change + temp) * expo
    // Nicht über das Ziel hinausschießen
    if (target - current > 0) == (output > target) {
        output = target
        velocity = 0
    }
    if !output.isFinite || !velocity.isFinite {
        velocity = 0
        return target
    }
    return output
}

/// Federnder Pop-Effekt für UI/Kamera: 0 → 1 mit leichtem Überschwingen.
func easeOutBackf(_ t: Float) -> Float {
    let x = clampf(t, 0, 1)
    let c1: Float = 1.70158
    let c3: Float = c1 + 1
    let u = x - 1
    return 1 + c3 * u * u * u + c1 * u * u
}

/// Pulsiert zwischen 0 und 1 (z.B. leuchtende Details). frequency in Hz.
func pulse01(_ time: Float, frequency: Float) -> Float {
    return 0.5 + 0.5 * sinf(time * frequency * Float.pi * 2)
}

// MARK: - Vektoren

/// Länge in der XZ-Ebene (ignoriert Y).
func horizontalLength(_ v: SIMD3<Float>) -> Float {
    return (v.x * v.x + v.z * v.z).squareRoot()
}

/// Projiziert auf die Bodenebene (y = 0).
func flatten(_ v: SIMD3<Float>) -> SIMD3<Float> {
    return SIMD3<Float>(v.x, 0, v.z)
}

/// Normalisiert sicher; bei (fast) Nullvektor oder NaN wird fallback zurückgegeben.
func safeNormalize(_ v: SIMD3<Float>, fallback: SIMD3<Float> = SIMD3<Float>(0, 0, 1)) -> SIMD3<Float> {
    let len2 = simd_length_squared(v)
    if len2 > 1e-12 && len2.isFinite {
        return v / len2.squareRoot()
    }
    return fallback
}

/// 2D-Variante von safeNormalize (z.B. für Stick-Eingaben).
func safeNormalize2(_ v: SIMD2<Float>, fallback: SIMD2<Float> = SIMD2<Float>(0, 1)) -> SIMD2<Float> {
    let len2 = simd_length_squared(v)
    if len2 > 1e-12 && len2.isFinite {
        return v / len2.squareRoot()
    }
    return fallback
}

/// Bewegt einen Punkt höchstens um maxDelta Meter in Richtung target.
func moveToward3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, maxDelta: Float) -> SIMD3<Float> {
    let delta = target - current
    let dist = simd_length(delta)
    let step = Swift.max(0, maxDelta)
    if dist <= step || dist < 1e-6 || !dist.isFinite { return target }
    return current + delta * (step / dist)
}

/// Kritisch gedämpfte Feder für Vektoren (Kamera-Follow ohne Ruckeln).
func smoothDamp3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, velocity: inout SIMD3<Float>, smoothTime: Float, dt: Float) -> SIMD3<Float> {
    guard dt > 0 else { return current }
    let st = Swift.max(0.0001, smoothTime)
    let omega = 2 / st
    let x = omega * dt
    let expo = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    let change = current - target
    let temp = (velocity + change * omega) * dt
    velocity = (velocity - temp * omega) * expo
    var output = target + (change + temp) * expo
    // Überschießen verhindern
    if simd_dot(target - current, output - target) > 0 {
        output = target
        velocity = SIMD3<Float>(0, 0, 0)
    }
    if !(output.x.isFinite && output.y.isFinite && output.z.isFinite) {
        velocity = SIMD3<Float>(0, 0, 0)
        return target
    }
    return output
}

/// Yaw (Drehung um +Y), mit dem eine nach +Z schauende Figur in Richtung dir blickt.
func yawOfDirection(_ dir: SIMD3<Float>) -> Float {
    if Swift.abs(dir.x) < 1e-9 && Swift.abs(dir.z) < 1e-9 { return 0 }
    return atan2f(dir.x, dir.z)
}

/// Horizontale Blickrichtung zu einem Yaw (Gegenstück zu yawOfDirection).
func directionFromYaw(_ yaw: Float) -> SIMD3<Float> {
    return SIMD3<Float>(sinf(yaw), 0, cosf(yaw))
}

/// Dreht v um die Y-Achse (gleiche Richtung wie simdEulerAngles.y).
func rotateY3(_ v: SIMD3<Float>, _ angle: Float) -> SIMD3<Float> {
    let c = cosf(angle)
    let s = sinf(angle)
    return SIMD3<Float>(v.x * c + v.z * s, v.y, -v.x * s + v.z * c)
}

/// Quaternion für eine reine Yaw-Drehung (für simdOrientation).
func yawQuat(_ yaw: Float) -> simd_quatf {
    return simd_quatf(angle: yaw, axis: SIMD3<Float>(0, 1, 0))
}

/// Nächster Punkt auf der Strecke a–b zu p.
func closestPointOnSegment3(_ p: SIMD3<Float>, _ a: SIMD3<Float>, _ b: SIMD3<Float>) -> SIMD3<Float> {
    let ab = b - a
    let len2 = simd_length_squared(ab)
    if len2 < 1e-12 { return a }
    let t = clampf(simd_dot(p - a, ab) / len2, 0, 1)
    return a + ab * t
}

// MARK: - Zufall (System-Zufall, nicht deterministisch)

/// Gleichverteilte Zufallszahl in [lo, hi). Bei hi <= lo wird lo geliefert.
func randf(_ lo: Float, _ hi: Float) -> Float {
    if !lo.isFinite || !hi.isFinite { return lo.isFinite ? lo : 0 }
    if hi <= lo { return lo }
    return Float.random(in: lo..<hi)
}

/// Gleichverteilter Einheitsvektor auf der Kugel.
func randUnit3() -> SIMD3<Float> {
    let z = Float.random(in: -1...1)
    let phi = Float.random(in: 0..<(Float.pi * 2))
    let r = Swift.max(0, 1 - z * z).squareRoot()
    return SIMD3<Float>(r * cosf(phi), r * sinf(phi), z)
}

/// true mit Wahrscheinlichkeit p (0...1).
func randChance(_ p: Float) -> Bool {
    return Float.random(in: 0..<1) < p
}

/// Zufälliges Vorzeichen: -1 oder +1.
func randSignf() -> Float {
    return Bool.random() ? 1 : -1
}

/// Zufälliger Punkt auf einer Kreisscheibe in der XZ-Ebene (gleichmäßig verteilt, y = 0).
func randOnDiscXZ(_ radius: Float) -> SIMD3<Float> {
    let r = Swift.max(0, radius) * Float.random(in: 0...1).squareRoot()
    let a = Float.random(in: 0..<(Float.pi * 2))
    return SIMD3<Float>(r * cosf(a), 0, r * sinf(a))
}

// MARK: - Deterministischer Zufall

/// Deterministischer Zufallsgenerator (SplitMix64): gleiche Seed → gleiche Stadt / gleiche Texturen.
/// Ist auch ein RandomNumberGenerator, also nutzbar mit
/// `Int.random(in: 0...3, using: &rng)` oder `array.shuffled(using: &rng)`.
struct SeededRandom: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed ^ 0x2545_F491_4F6C_DD1D
        _ = silkNextRaw()
    }

    mutating func next() -> UInt64 {
        return silkNextRaw()
    }

    /// SplitMix64-Schritt (eindeutiger Name, damit es keine Überladungs-Mehrdeutigkeit
    /// mit den generischen next()-Varianten von RandomNumberGenerator gibt).
    private mutating func silkNextRaw() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    /// Gleichverteilt in [lo, hi).
    mutating func float(_ lo: Float, _ hi: Float) -> Float {
        let u = Float(silkNextRaw() >> 40) * (1.0 / 16_777_216.0)   // 24 Bit → [0, 1)
        return lo + (hi - lo) * u
    }

    /// Ganzzahl im HALBOFFENEN Bereich lo ..< hi (hi exklusiv – sicher für Array-Indizes:
    /// `items[rng.int(0, items.count)]`). Bei hi <= lo wird lo geliefert.
    /// Für inklusive Bereiche: `Int.random(in: a...b, using: &rng)`.
    mutating func int(_ lo: Int, _ hi: Int) -> Int {
        guard hi > lo else { return lo }
        let span = UInt64(bitPattern: Int64(hi &- lo))
        return lo &+ Int(truncatingIfNeeded: silkNextRaw() % span)
    }

    /// true mit Wahrscheinlichkeit p (0...1).
    mutating func chance(_ p: Float) -> Bool {
        return float(0, 1) < p
    }

    /// -1 oder +1.
    mutating func signf() -> Float {
        return (silkNextRaw() & 1) == 0 ? -1 : 1
    }

    /// Zufälliges Element oder nil bei leerem Array.
    mutating func pick<T>(_ items: [T]) -> T? {
        if items.isEmpty { return nil }
        return items[int(0, items.count)]
    }

    /// Gleichverteilter Einheitsvektor (deterministisch).
    mutating func unit3() -> SIMD3<Float> {
        let z = float(-1, 1)
        let phi = float(0, Float.pi * 2)
        let r = Swift.max(0, 1 - z * z).squareRoot()
        return SIMD3<Float>(r * cosf(phi), r * sinf(phi), z)
    }
}

// MARK: - Farben

extension UIColor {
    /// RGBA-Komponenten in jedem Farbraum (Graustufen, sRGB, erweitert). Nur intern.
    private func silkMathRGBA() -> (r: CGFloat, g: CGFloat, b: CGFloat, a: CGFloat) {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 1
        if getRed(&r, green: &g, blue: &b, alpha: &a) {
            return (r, g, b, a)
        }
        var w: CGFloat = 0
        if getWhite(&w, alpha: &a) {
            return (w, w, w, a)
        }
        if let comps = cgColor.components, comps.count >= 3 {
            let alpha: CGFloat = comps.count >= 4 ? comps[3] : 1
            return (comps[0], comps[1], comps[2], alpha)
        }
        return (0, 0, 0, 1)
    }

    /// Mischt mit einer anderen Farbe. t = 0 → self, t = 1 → other.
    func blended(with other: UIColor, t: CGFloat) -> UIColor {
        let k = Swift.max(0, Swift.min(1, t))
        let c0 = silkMathRGBA()
        let c1 = other.silkMathRGBA()
        return UIColor(red: c0.r + (c1.r - c0.r) * k,
                       green: c0.g + (c1.g - c0.g) * k,
                       blue: c0.b + (c1.b - c0.b) * k,
                       alpha: c0.a + (c1.a - c0.a) * k)
    }

    /// Helligkeit multiplizieren (0.5 = halb so hell, 1.5 = heller).
    /// Wird die Farbe dabei "zu hell", wandert sie Richtung Weiß (gut für Leuchteffekte).
    func withBrightness(_ factor: CGFloat) -> UIColor {
        let f = Swift.max(0, factor)
        var h: CGFloat = 0
        var s: CGFloat = 0
        var br: CGFloat = 0
        var a: CGFloat = 1
        if getHue(&h, saturation: &s, brightness: &br, alpha: &a) {
            var nb = br * f
            var ns = s
            if nb > 1 {
                ns = s / nb
                nb = 1
            }
            return UIColor(hue: h,
                           saturation: Swift.max(0, Swift.min(1, ns)),
                           brightness: Swift.max(0, Swift.min(1, nb)),
                           alpha: a)
        }
        let c = silkMathRGBA()
        return UIColor(red: Swift.min(1, c.r * f),
                       green: Swift.min(1, c.g * f),
                       blue: Swift.min(1, c.b * f),
                       alpha: c.a)
    }

    /// Farbe aus Hex-Wert, z.B. `UIColor.hex(0xC8102E)`.
    static func hex(_ rgb: UInt32, alpha: CGFloat = 1) -> UIColor {
        let r = CGFloat((rgb >> 16) & 0xFF) / 255
        let g = CGFloat((rgb >> 8) & 0xFF) / 255
        let b = CGFloat(rgb & 0xFF) / 255
        return UIColor(red: r, green: g, blue: b, alpha: alpha)
    }
}

// =====================================================================
// MARK: - Core/SceneContracts.swift
// =====================================================================

// =====================================================================
//  Verträge zwischen GameManager (UI) und den Szenen-Controllern
//  (Offene Welt, Kombat, Cutscene) + HUD-Modelle für SwiftUI.
//
//  Regel: Alles läuft auf dem Main-Thread (CADisplayLink-Spielschleife).
//  HUD-Werte nur zuweisen, wenn sie sich wirklich ändern.
// =====================================================================

/// Jede 3D-Szene, die der SceneViewHost anzeigen kann.
protocol GameSceneController: AnyObject {
    var scene: SCNScene { get }
    var cameraNode: SCNNode { get }
    /// Wird jeden Frame vom GameLoop aufgerufen. dt = echte Sekunden (bereits auf max. 1/20 begrenzt).
    func update(dt: Float)
    /// Wird einmal aufgerufen, nachdem die SCNView konfiguriert und die Szene gesetzt wurde.
    func didAttach(to view: SCNView)
    /// Aufräumen (Sounds stoppen, Referenzen lösen). Danach wird der Controller verworfen.
    func teardown()
}

// MARK: - Offene Welt

struct WorldContext {
    var chapter: ChapterDef?          // nil = Freies Schwingen
    var spawnAt: LandmarkID = .heroApartment
    var timeOfDay: TimeOfDay = .night
    var heroDarkSuit: Bool = false
}

// MARK: - Kombat

struct KombatSetup {
    var player: FighterID
    var playerUsesDarkSuit: Bool = false
    var cpu: FighterID
    var arena: ArenaID
    var aiLevel: Float = 0.6          // 0...1.2, schon mit Difficulty multipliziert
    var roundsToWin: Int = 2
    var roundSeconds: Int = 90
    var isStory: Bool = false
}

struct KombatResult {
    let playerWon: Bool
    let executionPerformed: Bool      // Spieler hat eine Exekution ausgeführt
    let playerWasExecuted: Bool       // CPU hat den Spieler exekutiert
    let roundsWon: Int
    let roundsLost: Int
    let maxCombo: Int
    let totalDamageDealt: Float
    let seconds: Float
}

// MARK: - HUD-Modelle (von Controllern beschrieben, von SwiftUI angezeigt)

enum BannerStyle: Equatable {
    case round        // "RUNDE 1"
    case fight        // "KÄMPFT!"
    case finish       // "VOLLENDE ES!"
    case execution    // "EXEKUTION"
    case brutal       // Name des Brutal-Schlags
    case victory      // "SILKSTRIKE SIEGT"
    case defeat       // "NIEDERLAGE"
    case info         // neutrale Meldung
}

final class KombatHUD: ObservableObject {
    @Published var p1Name: String = ""
    @Published var p2Name: String = ""
    @Published var p1Health: Float = 1      // 0...1
    @Published var p2Health: Float = 1
    @Published var p1HealthLag: Float = 1   // verzögerter roter Balken
    @Published var p2HealthLag: Float = 1
    @Published var p1Meter: Float = 0       // 0...1 (1 = Brutal-Schlag bereit)
    @Published var p2Meter: Float = 0
    @Published var p1Rounds: Int = 0
    @Published var p2Rounds: Int = 0
    @Published var roundsToWin: Int = 2
    @Published var timer: Int = 90
    @Published var banner: String? = nil
    @Published var bannerStyle: BannerStyle = .info
    @Published var comboText: String? = nil
    @Published var special1Name: String = ""
    @Published var special2Name: String = ""
    @Published var special1Ready: Bool = true
    @Published var special2Ready: Bool = true
    @Published var canBrutal: Bool = false
    @Published var showExecutePrompt: Bool = false
    @Published var executeTimeLeft: Float = 0
    @Published var cinematic: Bool = false   // Letterbox + Steuerung ausblenden
    @Published var flashOpacity: Double = 0
    @Published var flashColor: UIColor = .white
    @Published var controlsEnabled: Bool = false
    @Published var matchOver: Bool = false
    @Published var playerWon: Bool = false
}

final class WorldHUD: ObservableObject {
    @Published var objective: String = ""
    @Published var objectiveDistance: Float? = nil     // Meter, nil = kein Ziel
    @Published var objectiveArrowAngle: Float = 0      // Radiant relativ zur Kamerablickrichtung (0 = geradeaus, + = rechts)
    @Published var health: Float = 1                   // 0...1
    @Published var speedKmh: Int = 0
    @Published var collectibles: Int = 0
    @Published var collectiblesTotal: Int = 0
    @Published var interactPrompt: String? = nil       // z.B. "Riss betreten"
    @Published var toast: String? = nil
    @Published var isSwinging: Bool = false
    @Published var combo: Int = 0
    @Published var thugsRemaining: Int = 0
    @Published var minimapHero: SIMD2<Float> = .zero   // normiert 0...1 auf Stadtfläche
    @Published var minimapHeroHeading: Float = 0       // Radiant
    @Published var minimapObjective: SIMD2<Float>? = nil
}

final class CutsceneHUD: ObservableObject {
    @Published var title: String? = nil
    @Published var speaker: String? = nil
    @Published var line: String? = nil
    @Published var letterbox: Bool = true
    @Published var fadeOpacity: Double = 1   // 1 = schwarz, 0 = sichtbar
    @Published var flashOpacity: Double = 0
    @Published var flashColor: UIColor = .white
}

// =====================================================================
// MARK: - Core/SharedTypes.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – gemeinsame Datentypen
//  Alle Module (Welt, Kombat, Cutscenes, UI) sprechen über diese Typen.
// =====================================================================

// MARK: - Bildschirme & Modi

enum GameScreen: Equatable {
    case title
    case chapterSelect
    case fighterSelect
    case settings
    case openWorld
    case cutscene
    case kombat
    case results
    case credits
}

enum GameMode: Equatable {
    case story
    case versus
    case freeRoam
}

// MARK: - Einstellungen

enum QualityPreset: String, CaseIterable, Codable, Identifiable {
    case performance
    case balanced
    case ultra

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .performance: return "Leistung (120 FPS)"
        case .balanced: return "Ausgewogen"
        case .ultra: return "Ultra (native Auflösung, alle Effekte)"
        }
    }

    /// Wählt beim ersten Start automatisch eine passende Stufe für das Gerät.
    static func recommendedForDevice() -> QualityPreset {
        let memoryGB = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824.0
        if memoryGB >= 7.5 { return .ultra }
        if memoryGB >= 5.5 { return .balanced }
        return .performance
    }
}

enum Difficulty: String, CaseIterable, Codable, Identifiable {
    case easy
    case normal
    case hard
    case brutal

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .easy: return "Leicht"
        case .normal: return "Normal"
        case .hard: return "Schwer"
        case .brutal: return "Brutal"
        }
    }

    /// Multiplikator für die KI-Stärke (wird mit ChapterDef.aiLevel kombiniert).
    var aiMultiplier: Float {
        switch self {
        case .easy: return 0.55
        case .normal: return 0.8
        case .hard: return 1.0
        case .brutal: return 1.2
        }
    }
}

struct GameSettings: Codable, Equatable {
    var quality: QualityPreset = QualityPreset.recommendedForDevice()
    var difficulty: Difficulty = .normal
    var bloodEnabled: Bool = true
    var voicesEnabled: Bool = true
    var musicEnabled: Bool = true
    var sfxVolume: Float = 0.9
    var musicVolume: Float = 0.45
    var invertCameraY: Bool = false
    var cameraSensitivity: Float = 1.0
    var showFPS: Bool = false

    private static let storageKey = "silkstrike.settings.v1"

    static func load() -> GameSettings {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let decoded = try? JSONDecoder().decode(GameSettings.self, from: data) else {
            return GameSettings()
        }
        return decoded
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: GameSettings.storageKey)
        }
    }
}

// MARK: - Kämpfer

enum FighterID: String, CaseIterable, Codable, Identifiable {
    case silkstrike   // Held: Kai Ronan
    case nachtseide   // dunkles Spiegelbild aus Schwarzseide
    case vex          // Kettenklingen-Söldner
    case saya         // Schatten-Kunoichi Saya Kurogane
    case brutus       // Cyborg-Schläger Brutus Hale
    case inferna      // Feuerhexe
    case malrek       // Kaiser Malrek, Herrscher des Blutturniers (Endboss)

    var id: String { rawValue }
}

/// Wer in Cutscenes auftreten kann (Kämpfer + Nebenfiguren).
enum CastMember: Hashable {
    case fighter(FighterID)
    case heroDarkSuit   // Kai im Schwarzseide-Anzug
    case lena           // Dr. Lena Hart, Wissenschaftlerin, Kais Mentorin
    case morgrim        // Herold des Blutturniers
    case civilian       // Passant/Geisel
}

enum BodyBuild: String, Codable {
    case lean
    case athletic
    case heavy
    case giant
}

enum EyeStyle: String, Codable {
    case lenses   // große weiße Maskenlinsen
    case glow     // leuchtende Augen
    case visor    // durchgehendes Visier
    case human    // normales Gesicht
}

enum Accessory: String, Codable {
    case webLines       // Netzlinien auf dem Anzug
    case chainBlades    // Kettenklingen an den Unterarmen
    case katana         // Schwert auf dem Rücken
    case scarf          // wehender Schal
    case shoulderPads   // Schulterpanzer
    case cyberArm       // metallischer Arm
    case horns          // Hörner
    case crown          // Krone
    case cape           // Umhang
    case flameAura      // Flammen um den Körper
    case tendrils       // schwarze Ranken
    case spikes         // Stacheln auf Schultern/Rücken
    case labCoat        // Laborkittel
    case hood           // Kapuze
}

struct FighterLook {
    var build: BodyBuild
    var height: Float               // Meter, ca. 1.65 – 2.4
    var skinColor: UIColor
    var primaryColor: UIColor       // Hauptfarbe Anzug/Kleidung
    var secondaryColor: UIColor     // Akzentfarbe Anzug
    var glowColor: UIColor          // leuchtende Details (Augen, Linien)
    var metalness: Float            // 0...1
    var roughness: Float            // 0...1
    var hasMask: Bool
    var eyeStyle: EyeStyle
    var hairColor: UIColor?
    var accessories: [Accessory]
}

struct FighterStats {
    var maxHealth: Float            // 1000 = Standard
    var walkSpeed: Float            // m/s, ca. 2.0 – 3.5
    var power: Float                // Schadensmultiplikator, 1.0 = Standard
    var defense: Float              // eingehender Schaden wird durch defense geteilt, 1.0 = Standard
    var jumpVelocity: Float         // m/s, ca. 7 – 10
}

enum SpecialKind: String, Codable {
    case projectile      // Geschoss fliegt auf den Gegner zu
    case dashStrike      // schneller Sturmangriff
    case teleportStrike  // verschwindet, taucht hinter dem Gegner auf
    case grabSlam        // Griff + Wurf auf den Boden (nicht blockbar)
    case groundWave      // Bodenwelle (muss übersprungen werden)
    case pullIn          // zieht den Gegner heran (Netz / Kette)
    case counter         // Konter-Haltung
}

struct SpecialMoveDef {
    let name: String
    let kind: SpecialKind
    let damage: Float               // Grundschaden (Gesundheit 1000)
    let cooldown: Float             // Sekunden
    let range: Float                // Meter
    let color: UIColor              // Effektfarbe
    let sound: SoundEffect
}

enum ExecutionKind: String, Codable {
    case webDecapitate   // Silkstrike: Netz-Abriss – Kopf wird weggerissen
    case devour          // Nachtseide: Ranken verschlingen, Körper zerfällt
    case splitInHalf     // Vex: Kettenschnitt – in zwei Hälften
    case shadowSlice     // Saya: Schattenklinge – Kopf und Arme fliegen
    case headCrush       // Brutus: Hydraulikpresse – Kopf zerquetscht
    case incinerate      // Inferna: Aschegericht – verbrennt zu Asche
    case impaleBurst     // Malrek: Kaiserurteil – Blutspeer, Körper zerplatzt
}

struct ExecutionDef {
    let name: String
    let kind: ExecutionKind
    let description: String
}

struct FighterDef: Identifiable {
    let id: FighterID
    let name: String                // "Silkstrike"
    let realName: String            // "Kai Ronan"
    let title: String               // "Der Netzläufer von Neo-Haven"
    let bio: String
    let look: FighterLook
    let stats: FighterStats
    let specials: [SpecialMoveDef]  // genau 2
    let execution: ExecutionDef
    let brutalName: String          // Name des Brutal-Schlags (Kino-Superangriff)
    let introQuote: String
    let winQuote: String
    let voicePitch: Float           // AVSpeech pitchMultiplier 0.5 ... 2.0
    let voiceRate: Float            // 0.0 ... 1.0 (AVSpeechUtterance rate)
}

// MARK: - Arenen, Orte, Tageszeit

enum ArenaID: String, CaseIterable, Codable, Identifiable {
    case rainRooftop     // Dach im Regen, Hafenviertel
    case subway          // verlassene U-Bahn-Station
    case foundry         // Gießerei mit flüssigem Metall
    case burningSquare   // brennender Domplatz
    case riftRealm       // Riss-Dimension, schwebende Felsen
    case bloodTower      // Thronsaal auf dem Blutturm

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .rainRooftop: return "Dach im Regen"
        case .subway: return "Station Kanalstraße"
        case .foundry: return "Hale-Gießerei"
        case .burningSquare: return "Brennender Domplatz"
        case .riftRealm: return "Im Riss"
        case .bloodTower: return "Thron des Blutturms"
        }
    }
}

enum LandmarkID: String, CaseIterable, Codable {
    case heroApartment   // Startpunkt
    case harborCrane     // Hafenkran (Kapitel 1)
    case subwayEntrance  // U-Bahn-Eingang (Kapitel 2)
    case foundry         // Gießerei (Kapitel 3)
    case cathedral       // Dom (Kapitel 4)
    case riftCore        // Rissherz über dem Park (Kapitel 5)
    case bloodTower      // Blutturm im Zentrum (Finale)
    case labTower        // Lenas Labor (Hochhaus)
}

enum TimeOfDay: String, Codable {
    case dusk
    case night
    case stormNight
}

// MARK: - Animation (vom Character-Modul umgesetzt)

enum AnimClip: String, CaseIterable {
    // Grundhaltungen
    case idle, fightIdle, crouch
    // Bewegung
    case walkForward, walkBack, run, sprint, jump, fall, land
    // Schwingen / Traversal
    case swing, webShoot, zip, wallRun, perch, dive
    // Kampf
    case punch, punch2, kick, kick2, uppercut, sweep, jumpKick
    case block, hitHigh, hitLow, knockdown, lieDown, getUp, dizzy
    case grab, throwToss, cast, dashStrike
    // Erzählung / Ende
    case victory, defeat, taunt, talk, point, crossArms, lookAround, kneel, celebrate
}

// MARK: - Effekte & Sound (Grafik- bzw. Audio-Modul setzt sie um)

enum EffectKind: String, CaseIterable {
    case bloodSpray       // gerichteter Blutstrahl
    case bloodBurst       // Blutexplosion in alle Richtungen
    case bloodPool        // Blutlache am Boden (wächst)
    case sparks           // Funken (Block, Metall)
    case hitFlash         // heller Treffer-Blitz
    case fireBurst        // Feuerstoß
    case embers           // aufsteigende Glut
    case iceShatter       // Eissplitter
    case smoke            // Rauch
    case dust             // Staub bei Landung
    case shadowBurst      // schwarz-violette Explosion
    case webHit           // Netz trifft (weiße Fäden)
    case riftPortal       // pulsierendes Rissportal
    case explosion        // große Explosion
    case electric         // Blitze/Strom
    case ash              // Asche-Partikel
}

enum SoundEffect: String, CaseIterable {
    case punchLight, punchHeavy, kick, block, whoosh
    case webShoot, webZip, land, bodyFall, boneCrack, gore, slice
    case fire, ice, electric, explosion, teleport, chain, roar
    case uiSelect, uiConfirm, uiBack
    case heartbeat, thunder, riftHum, crowd, metalHit, swingRelease
}

enum MusicMood: String {
    case none
    case menu
    case roam
    case tension
    case combat
    case boss
    case sad
    case victory
}

// MARK: - Story & Cutscenes (Daten in Data/Story.swift)

enum Easing {
    case linear
    case easeIn
    case easeOut
    case easeInOut

    func apply(_ t: Float) -> Float {
        let x = max(0, min(1, t))
        switch self {
        case .linear: return x
        case .easeIn: return x * x * x
        case .easeOut: return 1 - pow(1 - x, 3)
        case .easeInOut: return x < 0.5 ? 4 * x * x * x : 1 - pow(-2 * x + 2, 3) / 2
        }
    }
}

struct DialogLine {
    let speaker: String          // angezeigter Name
    let voice: CastMember?       // bestimmt Stimmlage, nil = Erzähler
    let text: String
    let duration: Float          // Sekunden, die der Untertitel stehen bleibt
}

struct CameraMove {
    var from: SIMD3<Float>
    var to: SIMD3<Float>
    var lookFrom: SIMD3<Float>
    var lookTo: SIMD3<Float>
    var fovFrom: Float = 50
    var fovTo: Float = 50
    var easing: Easing = .easeInOut
    var focusDistance: Float? = nil   // Tiefenschärfe (nur Ultra)
}

enum CutsceneEvent {
    case clip(actor: String, AnimClip)
    case moveTo(actor: String, position: SIMD3<Float>, duration: Float)
    case face(actor: String, yawDegrees: Float)
    case sound(SoundEffect)
    case shake(Float)                       // 0...1
    case flash(UIColor)
    case effect(EffectKind, position: SIMD3<Float>)
    case setCast(actor: String, CastMember) // z.B. Anzug wird schwarz
    case hide(actor: String)
    case show(actor: String)
    case music(MusicMood)
    case slowMotion(Float)                  // 1 = normal, 0.3 = Zeitlupe
}

struct TimedEvent {
    let time: Float                         // Sekunden ab Shot-Beginn
    let event: CutsceneEvent
}

struct Shot {
    let duration: Float
    let camera: CameraMove
    var lines: [DialogLine] = []            // nacheinander abgespielt
    var events: [TimedEvent] = []
}

struct CutsceneActor {
    let key: String                         // eindeutiger Name in der Szene, z.B. "kai"
    let cast: CastMember
    let position: SIMD3<Float>
    let yawDegrees: Float                   // 0 = schaut nach +Z
    let clip: AnimClip
}

enum CutsceneStage {
    case cityRooftop        // Dach mit Skyline
    case cityStreet         // Straße zwischen Hochhäusern
    case lab                // Lenas Labor
    case arena(ArenaID)     // Kampfarena als Kulisse
}

struct CutsceneDef {
    let id: String
    let title: String?                      // großer Titel am Anfang (z.B. "KAPITEL 1")
    let stage: CutsceneStage
    let timeOfDay: TimeOfDay
    let music: MusicMood
    let actors: [CutsceneActor]
    let shots: [Shot]
}

struct ChapterDef: Identifiable {
    let number: Int                         // 0 = Prolog
    let title: String
    let subtitle: String
    let introCutscene: String               // Cutscene-ID
    let objectiveText: String               // "Schwing zum Hafenkran"
    let objective: LandmarkID
    let opponent: FighterID
    let arena: ArenaID
    let heroDarkSuit: Bool                  // Kai trägt Schwarzseide
    let preFightCutscene: String?           // vor dem Kampf (am Ziel)
    let outroCutscene: String               // nach dem Sieg
    let aiLevel: Float                      // 0.3 ... 1.0
    let timeOfDay: TimeOfDay

    var id: Int { number }
}

// =====================================================================
// MARK: - Graphics/Effects.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Effekte
//  Partikel (Blut, Funken, Feuer, Rauch, Eis, Blitze …), Blutlachen,
//  Netzfäden, Kamerawackeln, Geschoss-Optik und Rissportale.
//
//  Alle Partikelbilder werden HIER prozedural erzeugt (keine Assets).
//  HDR-Regeln: Blut = dunkles, glänzendes Rot (Alpha-Blend), Feuer /
//  Funken / Glühen / Strom / Riss = additiv mit particleIntensity > 1
//  (damit Bloom greift), Rauch / Staub / Asche = Alpha-Blend.
// =====================================================================

// MARK: - Deterministischer Zufall für die Sprite-Erzeugung

fileprivate struct FXSpriteRNG {
    private var state: UInt64

    init(_ seed: UInt64) {
        state = seed &* 0x9E3779B97F4A7C15 &+ 0x632BE59BD9B4E019
    }

    mutating func next() -> CGFloat {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        let bits = (state >> 40) & 0xFFFFFF
        return CGFloat(bits) / CGFloat(0xFFFFFF)
    }

    mutating func range(_ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
        return lo + (hi - lo) * next()
    }
}

// MARK: - Sprite-Bank (prozedurale Partikelbilder, gecacht)

fileprivate enum FXSpriteBank {
    static var cache: [String: UIImage] = [:]

    // ---------- Farb-Helfer ----------

    static func components(_ c: UIColor) -> (r: CGFloat, g: CGFloat, b: CGFloat, a: CGFloat) {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 1
        if c.getRed(&r, green: &g, blue: &b, alpha: &a) {
            return (FXSpriteBank.clamp01(r), FXSpriteBank.clamp01(g), FXSpriteBank.clamp01(b), FXSpriteBank.clamp01(a))
        }
        var w: CGFloat = 0
        if c.getWhite(&w, alpha: &a) {
            let ww = FXSpriteBank.clamp01(w)
            return (ww, ww, ww, FXSpriteBank.clamp01(a))
        }
        return (1, 1, 1, 1)
    }

    static func clamp01(_ v: CGFloat) -> CGFloat {
        if !v.isFinite { return 0 }
        return Swift.min(1, Swift.max(0, v))
    }

    static func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> UIColor {
        return UIColor(red: r, green: g, blue: b, alpha: a)
    }

    static func white(_ a: CGFloat) -> UIColor {
        return UIColor(red: 1, green: 1, blue: 1, alpha: a)
    }

    static func key(_ c: UIColor) -> String {
        let k = FXSpriteBank.components(c)
        return "\(Int(k.r * 255))_\(Int(k.g * 255))_\(Int(k.b * 255))"
    }

    static func mix(_ a: UIColor, _ b: UIColor, _ t: CGFloat) -> UIColor {
        let k = FXSpriteBank.clamp01(t)
        let c0 = FXSpriteBank.components(a)
        let c1 = FXSpriteBank.components(b)
        return UIColor(red: c0.r + (c1.r - c0.r) * k,
                       green: c0.g + (c1.g - c0.g) * k,
                       blue: c0.b + (c1.b - c0.b) * k,
                       alpha: c0.a + (c1.a - c0.a) * k)
    }

    /// RGB mit k multiplizieren, Alpha setzen.
    static func scaled(_ c: UIColor, _ k: CGFloat, alpha: CGFloat) -> UIColor {
        let v = FXSpriteBank.components(c)
        return UIColor(red: FXSpriteBank.clamp01(v.r * k),
                       green: FXSpriteBank.clamp01(v.g * k),
                       blue: FXSpriteBank.clamp01(v.b * k),
                       alpha: FXSpriteBank.clamp01(alpha))
    }

    static func luminance(_ c: UIColor) -> CGFloat {
        let v = FXSpriteBank.components(c)
        return 0.2126 * v.r + 0.7152 * v.g + 0.0722 * v.b
    }

    /// Feuerfarben (rot/orange/gelb) → klassische Flammenpalette verwenden.
    static func isWarm(_ c: UIColor) -> Bool {
        let v = FXSpriteBank.components(c)
        return v.r > 0.55 && v.r > v.b * 1.4 && v.g <= v.r
    }

    // ---------- Zeichen-Helfer ----------

    static func renderer(_ size: CGFloat) -> UIGraphicsImageRenderer {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        return UIGraphicsImageRenderer(size: CGSize(width: size, height: size), format: format)
    }

    static func radial(_ cg: CGContext, _ center: CGPoint, _ radius: CGFloat, _ colors: [UIColor], _ locations: [CGFloat]) {
        guard radius > 0, colors.count >= 2, colors.count == locations.count else { return }
        let cgColors: [CGColor] = colors.map { $0.cgColor }
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                        colors: cgColors as CFArray,
                                        locations: locations) else { return }
        cg.drawRadialGradient(gradient, startCenter: center, startRadius: 0,
                              endCenter: center, endRadius: radius, options: [])
    }

    // ---------- Basis-Sprites (weiß, werden per particleColor eingefärbt) ----------

    /// Weiches Glühen (Feuer-Kern, Treffer, Halos).
    static var glow: UIImage {
        if let c = cache["glow"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(1), FXSpriteBank.white(0.62), FXSpriteBank.white(0.2),
                                 FXSpriteBank.white(0.05), FXSpriteBank.white(0)],
                                [0, 0.16, 0.42, 0.72, 1])
        }
        cache["glow"] = img
        return img
    }

    /// Kleiner, harter Leuchtpunkt (Funken, Glut, Regen – wird per stretchFactor gestreckt).
    static var spark: UIImage {
        if let c = cache["spark"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let s: CGFloat = 64
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(1), FXSpriteBank.white(1), FXSpriteBank.white(0.35), FXSpriteBank.white(0)],
                                [0, 0.18, 0.45, 1])
        }
        cache["spark"] = img
        return img
    }

    /// Wolkige Rauchpuste.
    static var smoke: UIImage {
        if let c = cache["smoke"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(11)
            FXSpriteBank.radial(cg, CGPoint(x: s / 2, y: s / 2), s * 0.42,
                                [FXSpriteBank.white(0.35), FXSpriteBank.white(0.15), FXSpriteBank.white(0)],
                                [0, 0.5, 1])
            for _ in 0..<16 {
                let r = s * rng.range(0.12, 0.22)
                let maxOff = Swift.max(0, s * 0.47 - r)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = rng.range(0, maxOff * 0.75)
                let p = CGPoint(x: s / 2 + cos(a) * d, y: s / 2 + sin(a) * d)
                FXSpriteBank.radial(cg, p, r,
                                    [FXSpriteBank.white(0.24), FXSpriteBank.white(0.12), FXSpriteBank.white(0)],
                                    [0, 0.5, 1])
            }
        }
        cache["smoke"] = img
        return img
    }

    /// Flammenzunge: heller Kern + unruhige Ränder.
    static var fire: UIImage {
        if let c = cache["fire"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(29)
            for _ in 0..<12 {
                let r = s * rng.range(0.1, 0.2)
                let maxOff = Swift.max(0, s * 0.46 - r)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = rng.range(0, maxOff * 0.7)
                let p = CGPoint(x: s / 2 + cos(a) * d, y: s / 2 + sin(a) * d)
                FXSpriteBank.radial(cg, p, r,
                                    [FXSpriteBank.white(0.4), FXSpriteBank.white(0.18), FXSpriteBank.white(0)],
                                    [0, 0.45, 1])
            }
            FXSpriteBank.radial(cg, CGPoint(x: s / 2, y: s / 2), s * 0.3,
                                [FXSpriteBank.white(0.95), FXSpriteBank.white(0.45), FXSpriteBank.white(0)],
                                [0, 0.4, 1])
        }
        cache["fire"] = img
        return img
    }

    /// Bluttropfen mit eingebackenem dunklem Rot + kleinem Glanzlicht (particleColor = weiß).
    static var bloodDrop: UIImage {
        if let c = cache["bloodDrop"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let c = CGPoint(x: s / 2, y: s / 2)
            FXSpriteBank.radial(cg, c, s * 0.44,
                                [FXSpriteBank.rgb(0.40, 0.018, 0.026, 1),
                                 FXSpriteBank.rgb(0.30, 0.010, 0.018, 1),
                                 FXSpriteBank.rgb(0.17, 0.004, 0.010, 0.92),
                                 FXSpriteBank.rgb(0.10, 0.0, 0.004, 0)],
                                [0, 0.55, 0.82, 1])
            FXSpriteBank.radial(cg, CGPoint(x: s * 0.41, y: s * 0.38), s * 0.11,
                                [FXSpriteBank.rgb(1.0, 0.72, 0.70, 0.7), FXSpriteBank.rgb(0.7, 0.2, 0.2, 0)],
                                [0, 1])
        }
        cache["bloodDrop"] = img
        return img
    }

    /// Wie bloodDrop, aber graustufig (für eingefärbtes Blut, z.B. schwarzes Ranken-Blut).
    static var grayDrop: UIImage {
        if let c = cache["grayDrop"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let c = CGPoint(x: s / 2, y: s / 2)
            FXSpriteBank.radial(cg, c, s * 0.44,
                                [FXSpriteBank.white(1), FXSpriteBank.rgb(0.75, 0.75, 0.75, 1),
                                 FXSpriteBank.rgb(0.45, 0.45, 0.45, 0.92), FXSpriteBank.rgb(0.3, 0.3, 0.3, 0)],
                                [0, 0.55, 0.82, 1])
            FXSpriteBank.radial(cg, CGPoint(x: s * 0.41, y: s * 0.38), s * 0.11,
                                [FXSpriteBank.white(0.8), FXSpriteBank.white(0)],
                                [0, 1])
        }
        cache["grayDrop"] = img
        return img
    }

    /// Eissplitter mit heller Kante.
    static var shard: UIImage {
        if let c = cache["shard"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let path = CGMutablePath()
            path.move(to: CGPoint(x: s * 0.50, y: s * 0.04))
            path.addLine(to: CGPoint(x: s * 0.70, y: s * 0.40))
            path.addLine(to: CGPoint(x: s * 0.58, y: s * 0.96))
            path.addLine(to: CGPoint(x: s * 0.33, y: s * 0.56))
            path.closeSubpath()
            cg.addPath(path)
            cg.setFillColor(FXSpriteBank.white(0.55).cgColor)
            cg.fillPath()
            let facet = CGMutablePath()
            facet.move(to: CGPoint(x: s * 0.50, y: s * 0.04))
            facet.addLine(to: CGPoint(x: s * 0.70, y: s * 0.40))
            facet.addLine(to: CGPoint(x: s * 0.52, y: s * 0.52))
            facet.closeSubpath()
            cg.addPath(facet)
            cg.setFillColor(FXSpriteBank.white(0.85).cgColor)
            cg.fillPath()
            cg.addPath(path)
            cg.setStrokeColor(FXSpriteBank.white(1).cgColor)
            cg.setLineWidth(1.5)
            cg.setLineJoin(.round)
            cg.strokePath()
        }
        cache["shard"] = img
        return img
    }

    /// Gezackter Blitz mit Seitenarm und Glühen.
    static var bolt: UIImage {
        if let c = cache["bolt"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(5)
            var main: [CGPoint] = []
            var x = s * 0.5
            for i in 0...11 {
                let y = s * 0.05 + CGFloat(i) / 11 * s * 0.9
                main.append(CGPoint(x: x, y: y))
                x = Swift.min(Swift.max(x + rng.range(-s * 0.1, s * 0.1), s * 0.18), s * 0.82)
            }
            var branch: [CGPoint] = []
            if main.count > 5 {
                var bp = main[4]
                branch.append(bp)
                for _ in 0..<5 {
                    bp = CGPoint(x: Swift.min(Swift.max(bp.x + rng.range(s * 0.02, s * 0.08), s * 0.1), s * 0.9),
                                 y: Swift.min(bp.y + rng.range(s * 0.04, s * 0.08), s * 0.94))
                    branch.append(bp)
                }
            }
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            // Glühen
            cg.setShadow(offset: .zero, blur: 7, color: FXSpriteBank.white(0.9).cgColor)
            cg.setStrokeColor(FXSpriteBank.white(0.75).cgColor)
            cg.setLineWidth(3.2)
            cg.addLines(between: main)
            cg.strokePath()
            if branch.count > 1 {
                cg.setLineWidth(2.0)
                cg.addLines(between: branch)
                cg.strokePath()
            }
            // heißer Kern
            cg.setShadow(offset: .zero, blur: 0, color: nil)
            cg.setStrokeColor(FXSpriteBank.white(1).cgColor)
            cg.setLineWidth(1.3)
            cg.addLines(between: main)
            cg.strokePath()
            if branch.count > 1 {
                cg.setLineWidth(0.9)
                cg.addLines(between: branch)
                cg.strokePath()
            }
        }
        cache["bolt"] = img
        return img
    }

    /// Ring (Schockwelle).
    static var ring: UIImage {
        if let c = cache["ring"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(0), FXSpriteBank.white(0), FXSpriteBank.white(0.95),
                                 FXSpriteBank.white(0.3), FXSpriteBank.white(0)],
                                [0, 0.6, 0.8, 0.88, 1])
        }
        cache["ring"] = img
        return img
    }

    /// Netz-Spinnennetz (Netz trifft).
    static var web: UIImage {
        if let c = cache["web"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            let c = CGPoint(x: s / 2, y: s / 2)
            var rng = FXSpriteRNG(91)
            let spokes = 9
            var angles: [CGFloat] = []
            for i in 0..<spokes {
                angles.append(CGFloat(i) / CGFloat(spokes) * CGFloat.pi * 2 + rng.range(-0.15, 0.15))
            }
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            cg.setShadow(offset: .zero, blur: 2, color: FXSpriteBank.white(0.8).cgColor)
            cg.setStrokeColor(FXSpriteBank.white(0.95).cgColor)
            cg.setLineWidth(1.7)
            for a in angles {
                cg.move(to: c)
                cg.addLine(to: CGPoint(x: c.x + cos(a) * s * 0.47, y: c.y + sin(a) * s * 0.47))
            }
            cg.strokePath()
            cg.setLineWidth(1.15)
            for ringIndex in 1...4 {
                let rr = s * 0.47 * CGFloat(ringIndex) / 4.6
                for (i, a) in angles.enumerated() {
                    let rj = rr * rng.range(0.88, 1.04)
                    let p = CGPoint(x: c.x + cos(a) * rj, y: c.y + sin(a) * rj)
                    if i == 0 { cg.move(to: p) } else { cg.addLine(to: p) }
                }
                cg.closePath()
            }
            cg.strokePath()
            // Außen weich ausblenden
            cg.setShadow(offset: .zero, blur: 0, color: nil)
            cg.setBlendMode(.destinationIn)
            FXSpriteBank.radial(cg, c, s * 0.5,
                                [FXSpriteBank.white(1), FXSpriteBank.white(1), FXSpriteBank.white(0)],
                                [0, 0.62, 1])
            cg.setBlendMode(.normal)
        }
        cache["web"] = img
        return img
    }

    /// Unregelmäßige Ascheflocke / Splitter.
    static var flake: UIImage {
        if let c = cache["flake"] { return c }
        let img = FXSpriteBank.renderer(32).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 32
            var rng = FXSpriteRNG(23)
            let path = CGMutablePath()
            let n = 7
            for i in 0..<n {
                let a = CGFloat(i) / CGFloat(n) * CGFloat.pi * 2
                let r = s * rng.range(0.2, 0.46)
                let p = CGPoint(x: s / 2 + cos(a) * r, y: s / 2 + sin(a) * r)
                if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
            cg.addPath(path)
            cg.setFillColor(FXSpriteBank.white(0.9).cgColor)
            cg.fillPath()
        }
        cache["flake"] = img
        return img
    }

    /// Schwarze Leere im Rissportal (Alpha-Blend).
    static var voidDisc: UIImage {
        if let c = cache["voidDisc"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.rgb(0, 0, 0, 0.97), FXSpriteBank.rgb(0, 0, 0, 0.9),
                                 FXSpriteBank.rgb(0, 0, 0, 0.45), FXSpriteBank.rgb(0, 0, 0, 0)],
                                [0, 0.45, 0.72, 1])
        }
        cache["voidDisc"] = img
        return img
    }

    // ---------- Eingefärbte Sprites ----------

    /// Färbt ein weißes Sprite ein (Alpha bleibt). Für additive Billboards/Halos.
    static func tinted(_ base: UIImage, baseKey: String, color: UIColor) -> UIImage {
        let k = baseKey + "#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let size = Swift.max(1, base.size.width)
        let v = FXSpriteBank.components(color)
        let opaque = UIColor(red: v.r, green: v.g, blue: v.b, alpha: 1)
        let img = FXSpriteBank.renderer(size).image { ctx in
            let rect = CGRect(x: 0, y: 0, width: size, height: size)
            base.draw(in: rect)
            ctx.cgContext.setBlendMode(.sourceIn)
            ctx.cgContext.setFillColor(opaque.cgColor)
            ctx.cgContext.fill(rect)
        }
        cache[k] = img
        return img
    }

    /// Blutlachen-Textur: Hauptlache + Ausläufer + Spritzer, Mitte dunkler (dickeres Blut).
    static func splat(_ color: UIColor) -> UIImage {
        let k = "splat#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let v = FXSpriteBank.components(color)
        let img = FXSpriteBank.renderer(256).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 256
            let c = CGPoint(x: s / 2, y: s / 2)
            var rng = FXSpriteRNG(4242)
            cg.setFillColor(FXSpriteBank.rgb(v.r, v.g, v.b, 1).cgColor)
            // Hauptkörper
            for _ in 0..<10 {
                let r = s * rng.range(0.11, 0.19)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0, 0.11)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
            }
            // Ausläufer mit "Hals"
            for _ in 0..<8 {
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0.2, 0.31)
                let r = s * rng.range(0.035, 0.075)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
                let d2 = d * 0.62
                let r2 = r * 0.8
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d2 - r2, y: c.y + sin(a) * d2 - r2, width: r2 * 2, height: r2 * 2))
            }
            // Spritzer
            for _ in 0..<22 {
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0.32, 0.45)
                let r = s * rng.range(0.005, 0.02)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
            }
            // dunklere, dickere Mitte – nur auf bereits gefüllte Pixel
            cg.setBlendMode(.sourceAtop)
            FXSpriteBank.radial(cg, c, s * 0.34,
                                [FXSpriteBank.rgb(v.r * 0.5, v.g * 0.4, v.b * 0.5, 0.85),
                                 FXSpriteBank.rgb(v.r * 0.7, v.g * 0.6, v.b * 0.7, 0.4),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.55, 1])
            cg.setBlendMode(.normal)
        }
        cache[k] = img
        return img
    }

    /// Spiralarme für das Rissportal (eingebacken in der Portalfarbe, additiv).
    static func swirl(_ color: UIColor) -> UIImage {
        let k = "swirl#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let v = FXSpriteBank.components(color)
        let hot = FXSpriteBank.components(FXSpriteBank.mix(color, .white, 0.6))
        let img = FXSpriteBank.renderer(256).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 256
            let c = CGPoint(x: s / 2, y: s / 2)
            let arms = 5
            for arm in 0..<arms {
                let offset = CGFloat(arm) / CGFloat(arms) * CGFloat.pi * 2
                for k in 0..<80 {
                    let t = CGFloat(k) / 80
                    let ang = offset + t * CGFloat.pi * 2.4
                    let rad = s * 0.43 * (1 - t * 0.88)
                    let p = CGPoint(x: c.x + cos(ang) * rad, y: c.y + sin(ang) * rad)
                    let dotR = s * (0.018 + 0.035 * (1 - t))
                    let alpha = 0.06 + 0.22 * t
                    FXSpriteBank.radial(cg, p, dotR,
                                        [FXSpriteBank.rgb(v.r, v.g, v.b, alpha), FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                        [0, 1])
                }
            }
            // Randglühen
            FXSpriteBank.radial(cg, c, s * 0.5,
                                [FXSpriteBank.rgb(v.r, v.g, v.b, 0), FXSpriteBank.rgb(v.r, v.g, v.b, 0),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0.55), FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.72, 0.86, 1])
            // heißer Kern
            FXSpriteBank.radial(cg, c, s * 0.16,
                                [FXSpriteBank.rgb(hot.r, hot.g, hot.b, 0.9), FXSpriteBank.rgb(v.r, v.g, v.b, 0.4),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.45, 1])
        }
        cache[k] = img
        return img
    }
}

// MARK: - FX

enum FX {
    /// Einmal vom Spiel gesetzt; skaliert Partikelanzahlen (Leistung 0.4x, Ausgewogen 0.7x, Ultra 1x).
    static var quality: QualityPreset = .balanced {
        didSet { FX.prewarm() }
    }
    /// false: Blut wird zu dunklem Staub/Funken, keine Lachen.
    static var bloodEnabled: Bool = true

    /// Name aller kurzlebigen FX-Knoten (direkte Kinder von scene.rootNode) – für cleanup(in:).
    static let transientNodeName = "silkFX.transient"

    private static var livePools: [SCNNode] = []
    private static var liveLights: [SCNNode] = []
    private static var spriteMaterialCache: [String: SCNMaterial] = [:]
    private static var poolMaterialCache: [String: SCNMaterial] = [:]
    private static let maxLivePools = 24

    private static let bloodPoolColor = UIColor(red: 0.30, green: 0.012, blue: 0.02, alpha: 1)
    private static let bloodMistColor = UIColor(red: 0.22, green: 0.006, blue: 0.012, alpha: 0.6)
    private static let defaultRiftColor = UIColor(red: 0.62, green: 0.16, blue: 1.0, alpha: 1)

    // MARK: Öffentliche API

    /// Erzeugt alle Partikelbilder vorab (verhindert Ruckler beim ersten Treffer). Optional.
    static func prewarm() {
        _ = FXSpriteBank.glow
        _ = FXSpriteBank.spark
        _ = FXSpriteBank.smoke
        _ = FXSpriteBank.fire
        _ = FXSpriteBank.bloodDrop
        _ = FXSpriteBank.grayDrop
        _ = FXSpriteBank.shard
        _ = FXSpriteBank.bolt
        _ = FXSpriteBank.ring
        _ = FXSpriteBank.web
        _ = FXSpriteBank.flake
        _ = FXSpriteBank.voidDisc
        _ = FXSpriteBank.splat(FX.bloodPoolColor)
    }

    static func spawn(_ kind: EffectKind, at position: SIMD3<Float>, in scene: SCNScene,
                      direction: SIMD3<Float> = SIMD3<Float>(0, 1, 0), scale: Float = 1, color: UIColor? = nil) {
        guard FX.isFinite3(position) else { return }
        let dir = FX.safeDirection(direction)
        var s = scale
        if !s.isFinite || s <= 0 { s = 1 }
        s = Swift.min(Swift.max(s, 0.05), 8)

        switch kind {
        case .bloodSpray:
            if bloodEnabled {
                spawnBloodSpray(position, dir, s, color, scene)
            } else {
                spawnBloodless(position, dir, s, scene)
            }
        case .bloodBurst:
            if bloodEnabled {
                spawnBloodBurst(position, s, color, scene)
            } else {
                spawnBloodless(position, dir, s * 1.3, scene)
            }
        case .bloodPool:
            if bloodEnabled {
                spawnBloodPool(position, s, color, scene)
            }
        case .sparks:
            spawnSparks(position, dir, s, color, scene)
        case .hitFlash:
            spawnHitFlash(position, s, color, scene)
        case .fireBurst:
            spawnFireBurst(position, dir, s, color, scene)
        case .embers:
            spawnEmbers(position, dir, s, color, scene)
        case .iceShatter:
            spawnIceShatter(position, s, color, scene)
        case .smoke:
            spawnSmoke(position, dir, s, color, scene)
        case .dust:
            spawnDust(position, s, color, scene)
        case .shadowBurst:
            spawnShadowBurst(position, s, color, scene)
        case .webHit:
            spawnWebHit(position, dir, s, color, scene)
        case .riftPortal:
            spawnRiftPortal(position, s, color, scene)
        case .explosion:
            spawnExplosion(position, s, color, scene)
        case .electric:
            spawnElectric(position, s, color, scene)
        case .ash:
            spawnAsh(position, s, color, scene)
        }
    }

    /// Regen: an den Kamera-Knoten hängen (folgt der Kamera). intensity 0…2 (1 = kräftiger Regen).
    static func makeRain(intensity: Float) -> SCNParticleSystem {
        var k = intensity.isFinite ? intensity : 1
        k = Swift.min(Swift.max(k, 0), 2)
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(1400 * k * countScale)
        p.emitterShape = SCNBox(width: 24, height: 20, length: 24, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0.08, y: -1, z: 0.03)
        p.spreadingAngle = 3
        p.particleVelocity = 16
        p.particleVelocityVariation = 4
        p.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        p.particleLifeSpan = 1.1
        p.particleLifeSpanVariation = 0.3
        p.particleSize = 0.018
        p.particleSizeVariation = 0.006
        p.stretchFactor = 0.045
        p.particleColor = UIColor(red: 0.72, green: 0.78, blue: 0.88, alpha: 0.32)
        p.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.15, w: 0.1)
        p.warmupDuration = 1.2
        FX.addCurve(p, .opacity, [0, 1, 1, 0], [0, 0.08, 0.85, 1])

        // feiner Sprühnebel, wo Tropfen "aufschlagen" (nur ab Ausgewogen)
        if quality != .performance && k > 0.05 {
            let mist = SCNParticleSystem()
            mist.particleImage = FXSpriteBank.smoke
            mist.blendMode = .alpha
            mist.sortingMode = .none
            mist.isLightingEnabled = false
            mist.isLocal = false
            mist.loops = false
            mist.emissionDuration = 0.05
            mist.birthRate = 20
            mist.birthDirection = .random
            mist.spreadingAngle = 180
            mist.particleVelocity = 0.4
            mist.particleVelocityVariation = 0.2
            mist.dampingFactor = 1.5
            mist.particleLifeSpan = 0.6
            mist.particleLifeSpanVariation = 0.2
            mist.particleSize = 1
            mist.particleAngleVariation = 180
            mist.particleColor = UIColor(red: 0.8, green: 0.84, blue: 0.9, alpha: 0.07)
            FX.addCurve(mist, .size, [0.1, 0.38], [0, 1])
            FX.addCurve(mist, .opacity, [0, 1, 0], [0, 0.2, 1])
            p.systemSpawnedOnDying = mist
        }
        return p
    }

    /// Schwebende Glut (Gießerei, brennender Domplatz). Emitter: 26 x 3 x 26 m um den Knoten.
    static func makeEmbersAmbient() -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(45 * countScale + 6)
        p.emitterShape = SCNBox(width: 26, height: 3, length: 26, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 35
        p.particleVelocity = 0.7
        p.particleVelocityVariation = 0.45
        p.acceleration = SCNVector3(x: 0.18, y: 0.1, z: 0.06)
        p.dampingFactor = 0.15
        p.particleLifeSpan = 6
        p.particleLifeSpanVariation = 2
        p.particleSize = 0.032
        p.particleSizeVariation = 0.016
        p.particleColor = UIColor(red: 1.0, green: 0.5, blue: 0.14, alpha: 1)
        p.particleColorVariation = SCNVector4(x: 0.03, y: 0.1, z: 0.25, w: 0)
        p.particleIntensity = 2.6
        p.particleIntensityVariation = 1.4
        p.warmupDuration = 5
        FX.addCurve(p, .opacity, [0, 1, 0.5, 1, 0.35, 0], [0, 0.08, 0.3, 0.55, 0.8, 1])
        return p
    }

    /// Fallende Asche (brennende Stadt, Riss). Emitter: 30 x 10 x 30 m um den Knoten (Knoten ca. 5 m hoch setzen).
    static func makeAshAmbient() -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.flake
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(60 * countScale + 8)
        p.emitterShape = SCNBox(width: 30, height: 10, length: 30, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: -1, z: 0)
        p.spreadingAngle = 30
        p.particleVelocity = 0.35
        p.particleVelocityVariation = 0.2
        p.acceleration = SCNVector3(x: 0.12, y: -0.05, z: 0.04)
        p.particleLifeSpan = 9
        p.particleLifeSpanVariation = 3
        p.particleSize = 0.035
        p.particleSizeVariation = 0.02
        p.particleAngleVariation = 180
        p.particleAngularVelocity = 0
        p.particleAngularVelocityVariation = 90
        p.particleColor = UIColor(red: 0.30, green: 0.28, blue: 0.27, alpha: 0.85)
        p.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.4, w: 0.1)
        p.warmupDuration = 6
        FX.addCurve(p, .opacity, [0, 1, 1, 0], [0, 0.1, 0.85, 1])
        return p
    }

    /// Schleifendes, animiertes Rissportal (Ringe + Strudel + eingesaugte Partikel + pulsierendes Licht).
    /// Wurzel = Portalmitte, Radius ca. 1.3 m (Knoten ca. 1.6 m über dem Boden platzieren, simdScale zum Vergrößern).
    static func makeRiftSwirl(color: UIColor) -> SCNNode {
        let radius: Float = 1.3
        let lowDetail = quality == .performance
        let root = SCNNode()
        root.name = "fx.riftSwirl"
        root.castsShadow = false

        // Billboard (dreht sich nur um Y) – die Scheibe schaut immer zur Kamera.
        let face = SCNNode()
        let billboard = SCNBillboardConstraint()
        billboard.freeAxes = .Y
        face.constraints = [billboard]
        root.addChildNode(face)

        let pulse = SCNNode()
        face.addChildNode(pulse)
        let up = SCNAction.scale(to: 1.06, duration: 0.9)
        up.timingMode = .easeInEaseOut
        let down = SCNAction.scale(to: 0.95, duration: 0.9)
        down.timingMode = .easeInEaseOut
        pulse.runAction(.repeatForever(.sequence([up, down])))

        // Halo
        let haloImage = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: color)
        let halo = SCNPlane(width: CGFloat(radius * 3.6), height: CGFloat(radius * 3.6))
        halo.materials = [FX.spriteMaterial(haloImage, key: "glow#" + FXSpriteBank.key(color), boost: 1.0)]
        let haloNode = SCNNode(geometry: halo)
        haloNode.castsShadow = false
        haloNode.renderingOrder = 39
        haloNode.simdPosition = SIMD3<Float>(0, 0, -0.02)
        pulse.addChildNode(haloNode)

        // Schwarze Leere
        let voidPlane = SCNPlane(width: CGFloat(radius * 2.1), height: CGFloat(radius * 2.1))
        voidPlane.materials = [FX.spriteMaterial(FXSpriteBank.voidDisc, key: "voidDisc", boost: 1, additive: false)]
        let voidNode = SCNNode(geometry: voidPlane)
        voidNode.castsShadow = false
        voidNode.renderingOrder = 40
        pulse.addChildNode(voidNode)

        // Zwei gegenläufige Strudel
        let swirlImage = FXSpriteBank.swirl(color)
        let swirlMaterial = FX.spriteMaterial(swirlImage, key: "swirl#" + FXSpriteBank.key(color), boost: 1.8)
        for i in 0..<2 {
            let size = radius * (i == 0 ? 2.3 : 1.75)
            let plane = SCNPlane(width: CGFloat(size), height: CGFloat(size))
            plane.materials = [swirlMaterial]
            let swirlNode = SCNNode(geometry: plane)
            swirlNode.castsShadow = false
            swirlNode.renderingOrder = 41 + i
            swirlNode.simdPosition = SIMD3<Float>(0, 0, 0.01 * Float(i + 1))
            let turn: CGFloat = i == 0 ? -1 : 1
            swirlNode.runAction(.repeatForever(.rotateBy(x: 0, y: 0, z: turn * CGFloat.pi * 2, duration: i == 0 ? 5.0 : 3.2)))
            pulse.addChildNode(swirlNode)
        }

        // Rahmenring (liegt in der Scheibenebene)
        let ringMaterial = FX.glowLineMaterial(color, boost: 2.2)
        let frame = SCNTorus(ringRadius: CGFloat(radius * 1.02), pipeRadius: 0.035)
        frame.ringSegmentCount = lowDetail ? 40 : 72
        frame.pipeSegmentCount = 8
        frame.materials = [ringMaterial]
        let frameNode = SCNNode(geometry: frame)
        frameNode.castsShadow = false
        frameNode.simdEulerAngles = SIMD3<Float>(Float.pi / 2, 0, 0)
        pulse.addChildNode(frameNode)

        // Kreisende 3D-Ringe (Gyroskop)
        let ringSpecs: [(r: Float, tiltX: Float, tiltZ: Float, axis: SIMD3<Float>, duration: Double)] = [
            (1.18, 1.25, 0.3, SIMD3<Float>(0, 1, 0), 3.4),
            (1.32, 0.4, 1.1, SIMD3<Float>(1, 0, 0.3), 4.6),
            (1.45, -0.9, -0.5, SIMD3<Float>(0.2, 1, -0.6), 6.0)
        ]
        let ringCount = lowDetail ? 2 : 3
        for i in 0..<ringCount {
            let spec = ringSpecs[i]
            let torus = SCNTorus(ringRadius: CGFloat(radius * spec.r), pipeRadius: 0.016)
            torus.ringSegmentCount = lowDetail ? 40 : 72
            torus.pipeSegmentCount = 6
            torus.materials = [ringMaterial]
            let ringNode = SCNNode(geometry: torus)
            ringNode.castsShadow = false
            ringNode.simdEulerAngles = SIMD3<Float>(spec.tiltX, 0, spec.tiltZ)
            let gimbal = SCNNode()
            gimbal.addChildNode(ringNode)
            let a = FX.safeDirection(spec.axis)
            let full = CGFloat.pi * 2
            let spin = SCNAction.rotateBy(x: full * CGFloat(a.x), y: full * CGFloat(a.y), z: full * CGFloat(a.z),
                                          duration: spec.duration)
            gimbal.runAction(.repeatForever(spin))
            root.addChildNode(gimbal)
        }

        // Eingesaugte Partikel
        let suck = SCNParticleSystem()
        suck.particleImage = FXSpriteBank.spark
        suck.blendMode = .additive
        suck.sortingMode = .none
        suck.isLightingEnabled = false
        suck.isLocal = false
        suck.loops = true
        suck.emissionDuration = 1
        suck.birthRate = CGFloat(70 * countScale + 10)
        suck.emitterShape = SCNSphere(radius: CGFloat(radius * 1.55))
        suck.birthLocation = .surface
        suck.birthDirection = .surfaceNormal
        suck.particleVelocity = -2.2      // negativ = nach innen
        suck.particleVelocityVariation = 0.3
        suck.particleLifeSpan = 0.85
        suck.particleLifeSpanVariation = 0.1
        suck.particleSize = 0.035
        suck.particleSizeVariation = 0.015
        suck.stretchFactor = 0.06
        suck.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        suck.particleIntensity = 2.2
        FX.addCurve(suck, .opacity, [0, 1, 1, 0], [0, 0.25, 0.8, 1])
        root.addParticleSystem(suck)

        // Schwebende Funken am Rand
        if !lowDetail {
            let motes = SCNParticleSystem()
            motes.particleImage = FXSpriteBank.glow
            motes.blendMode = .additive
            motes.sortingMode = .none
            motes.isLightingEnabled = false
            motes.isLocal = false
            motes.loops = true
            motes.emissionDuration = 1
            motes.birthRate = CGFloat(18 * countScale + 4)
            motes.emitterShape = SCNSphere(radius: CGFloat(radius * 1.1))
            motes.birthLocation = .volume
            motes.birthDirection = .random
            motes.spreadingAngle = 180
            motes.particleVelocity = 0.25
            motes.particleVelocityVariation = 0.15
            motes.particleLifeSpan = 1.6
            motes.particleLifeSpanVariation = 0.5
            motes.particleSize = 0.09
            motes.particleSizeVariation = 0.05
            motes.particleColor = color
            motes.particleIntensity = 1.6
            FX.addCurve(motes, .opacity, [0, 0.8, 0], [0, 0.4, 1])
            root.addParticleSystem(motes)
        }

        // Pulsierendes Licht
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = 820
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = 9
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let lightNode = SCNNode()
        lightNode.light = light
        lightNode.simdPosition = SIMD3<Float>(0, 0, 0.4)
        let period: Double = 1.8
        let pulseLight = SCNAction.customAction(duration: period) { node, elapsed in
            let phase = Double(elapsed) / period * Double.pi * 2
            node.light?.intensity = CGFloat(820 + 380 * sin(phase))
        }
        lightNode.runAction(.repeatForever(pulseLight))
        root.addChildNode(lightNode)

        return root
    }

    /// Bewegungsspur für Fäuste/Füße/Geschosse (Partikel bleiben im Weltraum zurück).
    static func makeTrail(color: UIColor) -> SCNParticleSystem {
        return FX.trailSystem(color: color, size: 0.09, dark: FXSpriteBank.luminance(color) < 0.12)
    }

    /// Entfernt alle kurzlebigen FX-Knoten (Treffer, Blutlachen, Lichtblitze …) aus der Szene.
    static func cleanup(in scene: SCNScene) {
        let children = scene.rootNode.childNodes
        for child in children where child.name == transientNodeName {
            child.removeAllActions()
            child.removeAllParticleSystems()
            child.removeFromParentNode()
        }
        livePools.removeAll(where: { $0.parent == nil })
        liveLights.removeAll(where: { $0.parent == nil })
    }

    // MARK: - Gemeinsame Helfer (fileprivate: auch für ProjectileVisual)

    fileprivate static var countScale: Float {
        switch quality {
        case .performance: return 0.4
        case .balanced: return 0.7
        case .ultra: return 1.0
        }
    }

    private static var maxFlashLights: Int {
        switch quality {
        case .performance: return 1
        case .balanced: return 2
        case .ultra: return 4
        }
    }

    /// Partikelanzahl nach Qualität und Effektgröße.
    private static func count(_ base: Float, _ s: Float) -> Float {
        let sizeFactor = Swift.min(2.5, Swift.max(0.5, s))
        return Swift.max(1, (base * countScale * sizeFactor).rounded())
    }

    private static func cg(_ v: Float) -> CGFloat {
        return CGFloat(v)
    }

    private static func vec(_ v: SIMD3<Float>) -> SCNVector3 {
        return SCNVector3(x: v.x, y: v.y, z: v.z)
    }

    private static func isFinite3(_ v: SIMD3<Float>) -> Bool {
        return v.x.isFinite && v.y.isFinite && v.z.isFinite
    }

    fileprivate static func safeDirection(_ v: SIMD3<Float>) -> SIMD3<Float> {
        guard FX.isFinite3(v) else { return SIMD3<Float>(0, 1, 0) }
        let l = simd_length(v)
        if !l.isFinite || l < 1e-5 { return SIMD3<Float>(0, 1, 0) }
        return v / l
    }

    /// Kurzer, nicht schleifender Partikelstoß: count Partikel innerhalb von duration Sekunden.
    private static func makeBurst(_ image: UIImage, additive: Bool, count: Float, over duration: Float = 0.05) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = image
        p.blendMode = additive ? .additive : .alpha
        p.sortingMode = additive ? .none : .projectedDepth
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isAffectedByPhysicsFields = false
        p.isLocal = false
        p.loops = false
        p.orientationMode = .billboardScreenAligned
        p.particleColor = .white
        let d = Swift.max(0.02, duration)
        p.emissionDuration = CGFloat(d)
        p.birthRate = CGFloat(Swift.max(1, count) / d)
        return p
    }

    /// Kugelförmiger Stoß in alle Richtungen.
    private static func makeOmni(_ p: SCNParticleSystem, radius: Float) {
        p.emitterShape = SCNSphere(radius: CGFloat(Swift.max(0.005, radius)))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
    }

    /// Wert-Kurve über die Lebenszeit (opacity / size …).
    /// Bei .size immer particleSize = 1 setzen – dann stimmen absolute UND relative Deutung überein.
    fileprivate static func addCurve(_ p: SCNParticleSystem, _ property: SCNParticleSystem.ParticleProperty,
                                     _ values: [Float], _ times: [Float]) {
        guard values.count >= 2, values.count == times.count else { return }
        let anim = CAKeyframeAnimation()
        anim.values = values.map { NSNumber(value: $0) }
        anim.keyTimes = times.map { NSNumber(value: $0) }
        anim.duration = 1
        var dict = p.propertyControllers ?? [:]
        dict[property] = SCNParticlePropertyController(animation: anim)
        p.propertyControllers = dict
    }

    /// Farbverlauf über die Lebenszeit (particleColor bleibt weiß).
    fileprivate static func addColorCurve(_ p: SCNParticleSystem, _ colors: [UIColor], _ times: [Float]) {
        guard colors.count >= 2, colors.count == times.count else { return }
        let anim = CAKeyframeAnimation()
        anim.values = colors
        anim.keyTimes = times.map { NSNumber(value: $0) }
        anim.duration = 1
        var dict = p.propertyControllers ?? [:]
        dict[.color] = SCNParticlePropertyController(animation: anim)
        p.propertyControllers = dict
        p.particleColor = .white
    }

    fileprivate static func fireColors(_ tint: UIColor?) -> [UIColor] {
        if let t = tint, !FXSpriteBank.isWarm(t) {
            return [FXSpriteBank.mix(t, .white, 0.7).withAlphaComponent(1),
                    FXSpriteBank.scaled(t, 1, alpha: 0.95),
                    FXSpriteBank.scaled(t, 0.55, alpha: 0.6),
                    FXSpriteBank.scaled(t, 0.15, alpha: 0)]
        }
        return [UIColor(red: 1.0, green: 0.93, blue: 0.70, alpha: 1.0),
                UIColor(red: 1.0, green: 0.56, blue: 0.14, alpha: 0.95),
                UIColor(red: 0.75, green: 0.16, blue: 0.03, alpha: 0.6),
                UIColor(red: 0.18, green: 0.03, blue: 0.01, alpha: 0.0)]
    }

    private static func sparkColors(_ tint: UIColor?) -> [UIColor] {
        if let t = tint {
            return [FXSpriteBank.mix(t, .white, 0.75).withAlphaComponent(1),
                    FXSpriteBank.scaled(t, 1, alpha: 1),
                    FXSpriteBank.scaled(t, 0.6, alpha: 0.8),
                    FXSpriteBank.scaled(t, 0.3, alpha: 0)]
        }
        return [UIColor(red: 1.0, green: 0.96, blue: 0.82, alpha: 1),
                UIColor(red: 1.0, green: 0.72, blue: 0.28, alpha: 1),
                UIColor(red: 1.0, green: 0.36, blue: 0.06, alpha: 0.8),
                UIColor(red: 0.55, green: 0.08, blue: 0.0, alpha: 0)]
    }

    /// Hängt Systeme an einen kurzlebigen Knoten und entfernt ihn, wenn alle Partikel tot sind.
    @discardableResult
    private static func emit(_ systems: [SCNParticleSystem], at position: SIMD3<Float>, in scene: SCNScene) -> SCNNode {
        let node = SCNNode()
        node.name = transientNodeName
        node.simdPosition = position
        node.castsShadow = false
        var longest: Double = 0.1
        for p in systems {
            node.addParticleSystem(p)
            let life = Double(p.emissionDuration + p.emissionDurationVariation + p.particleLifeSpan + p.particleLifeSpanVariation)
            longest = Swift.max(longest, life)
        }
        scene.rootNode.addChildNode(node)
        node.runAction(.sequence([.wait(duration: longest + 0.2), .removeFromParentNode()]))
        return node
    }

    /// Material für Billboard-Sprites (additiv mit HDR-Boost oder Alpha).
    fileprivate static func spriteMaterial(_ image: UIImage, key: String, boost: Float, additive: Bool = true) -> SCNMaterial {
        let k = key + "|" + String(Int(boost * 100)) + (additive ? "a" : "n")
        if let m = spriteMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .constant
        m.diffuse.contents = image
        if additive {
            m.blendMode = .add
            if boost > 1 {
                m.emission.contents = image
                m.emission.intensity = CGFloat(boost - 1)
            }
        } else {
            m.blendMode = .alpha
        }
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = true
        spriteMaterialCache[k] = m
        return m
    }

    /// Leuchtende Linie/Ring (additiv, unbeleuchtet, HDR-hell).
    fileprivate static func glowLineMaterial(_ color: UIColor, boost: Float) -> SCNMaterial {
        let k = "line#" + FXSpriteBank.key(color) + "|" + String(Int(boost * 100))
        if let m = spriteMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .constant
        m.diffuse.contents = color
        if boost > 1 {
            m.emission.contents = color
            m.emission.intensity = CGFloat(boost - 1)
        }
        m.blendMode = .add
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = false
        spriteMaterialCache[k] = m
        return m
    }

    /// Einzelnes Billboard, das wächst und ausblendet (Blitz-Kern, Schockwelle).
    private static func spawnSprite(_ image: UIImage, key: String, at position: SIMD3<Float>, in scene: SCNScene,
                                    size: Float, from startScale: Float, to endScale: Float,
                                    duration: Double, boost: Float) {
        let plane = SCNPlane(width: cg(size), height: cg(size))
        plane.materials = [spriteMaterial(image, key: key, boost: boost)]
        let node = SCNNode(geometry: plane)
        node.name = transientNodeName
        node.castsShadow = false
        node.renderingOrder = 60
        node.simdPosition = position
        node.simdScale = SIMD3<Float>(repeating: Swift.max(0.001, startScale))
        node.constraints = [SCNBillboardConstraint()]
        scene.rootNode.addChildNode(node)
        let grow = SCNAction.scale(to: cg(endScale), duration: duration)
        grow.timingMode = .easeOut
        let fade = SCNAction.fadeOut(duration: duration)
        fade.timingMode = .easeIn
        node.runAction(.sequence([.group([grow, fade]), .removeFromParentNode()]))
    }

    /// Sehr kurzes Punktlicht (Anzahl gleichzeitiger FX-Lichter ist nach Qualität begrenzt).
    private static func flashLight(at position: SIMD3<Float>, in scene: SCNScene, color: UIColor,
                                   intensity: Float, range: Float, duration: Double, flicker: Bool = false) {
        liveLights.removeAll(where: { $0.parent == nil })
        if liveLights.count >= maxFlashLights { return }
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = CGFloat(intensity)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.5, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let node = SCNNode()
        node.light = light
        node.name = transientNodeName
        node.simdPosition = position
        scene.rootNode.addChildNode(node)
        liveLights.append(node)
        let peak = CGFloat(intensity)
        let total = Swift.max(0.02, duration)
        let fade = SCNAction.customAction(duration: total) { n, elapsed in
            let t = Swift.min(1, Swift.max(0, Double(elapsed) / total))
            var k = (1 - t) * (1 - t)
            if flicker {
                k *= 0.3 + 0.7 * abs(sin(t * 53.0))
            }
            n.light?.intensity = peak * CGFloat(k)
        }
        node.runAction(.sequence([fade, .removeFromParentNode()]))
    }

    // MARK: - Blut

    private static func spawnBloodSpray(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dropImage = tint == nil ? FXSpriteBank.bloodDrop : FXSpriteBank.grayDrop
        let dropColor = tint ?? UIColor.white

        // Tropfen (gestreckt, fallen mit Schwerkraft)
        let drops = makeBurst(dropImage, additive: false, count: count(70, s), over: 0.1)
        drops.particleColor = dropColor
        drops.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        drops.emitterShape = SCNSphere(radius: cg(0.035 * s))
        drops.birthLocation = .volume
        drops.birthDirection = .constant
        drops.emittingDirection = vec(dir)
        drops.spreadingAngle = 22
        drops.particleVelocity = cg(5.8 * vs)
        drops.particleVelocityVariation = cg(3.0 * vs)
        drops.acceleration = SCNVector3(x: 0, y: -10.5, z: 0)
        drops.dampingFactor = 0.25
        drops.particleLifeSpan = 0.9
        drops.particleLifeSpanVariation = 0.35
        drops.particleSize = cg(0.03 * s)
        drops.particleSizeVariation = cg(0.018 * s)
        drops.stretchFactor = 0.04
        addCurve(drops, .opacity, [1, 1, 0], [0, 0.82, 1])

        // dicke Batzen
        let globs = makeBurst(dropImage, additive: false, count: count(12, s), over: 0.12)
        globs.particleColor = dropColor
        globs.birthDirection = .constant
        globs.emittingDirection = vec(dir)
        globs.spreadingAngle = 14
        globs.particleVelocity = cg(3.6 * vs)
        globs.particleVelocityVariation = cg(1.4 * vs)
        globs.acceleration = SCNVector3(x: 0, y: -11, z: 0)
        globs.particleLifeSpan = 1.0
        globs.particleLifeSpanVariation = 0.3
        globs.particleSize = cg(0.07 * s)
        globs.particleSizeVariation = cg(0.03 * s)
        globs.particleAngleVariation = 180
        globs.stretchFactor = 0.015
        addCurve(globs, .opacity, [1, 1, 0], [0, 0.85, 1])

        // feiner Nebel
        let mist = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.08)
        mist.particleColor = tint.map { $0.withAlphaComponent(0.55) } ?? bloodMistColor
        mist.birthDirection = .constant
        mist.emittingDirection = vec(dir)
        mist.spreadingAngle = 40
        mist.particleVelocity = cg(1.6 * vs)
        mist.particleVelocityVariation = 0.7
        mist.dampingFactor = 2.2
        mist.particleLifeSpan = 0.55
        mist.particleLifeSpanVariation = 0.15
        mist.particleSize = 1
        mist.particleAngleVariation = 180
        addCurve(mist, .size, [0.14 * s, 0.5 * s], [0, 1])
        addCurve(mist, .opacity, [0, 0.7, 0], [0, 0.12, 1])

        emit([drops, globs, mist], at: p, in: scene)
    }

    private static func spawnBloodBurst(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dropImage = tint == nil ? FXSpriteBank.bloodDrop : FXSpriteBank.grayDrop
        let dropColor = tint ?? UIColor.white

        let drops = makeBurst(dropImage, additive: false, count: count(150, s), over: 0.08)
        makeOmni(drops, radius: 0.12 * s)
        drops.particleColor = dropColor
        drops.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        drops.particleVelocity = cg(4.8 * vs)
        drops.particleVelocityVariation = cg(2.6 * vs)
        drops.acceleration = SCNVector3(x: 0, y: -10.5, z: 0)
        drops.dampingFactor = 0.3
        drops.particleLifeSpan = 1.0
        drops.particleLifeSpanVariation = 0.35
        drops.particleSize = cg(0.032 * s)
        drops.particleSizeVariation = cg(0.02 * s)
        drops.stretchFactor = 0.035
        addCurve(drops, .opacity, [1, 1, 0], [0, 0.82, 1])

        let globs = makeBurst(dropImage, additive: false, count: count(26, s), over: 0.1)
        makeOmni(globs, radius: 0.1 * s)
        globs.particleColor = dropColor
        globs.particleVelocity = cg(3.2 * vs)
        globs.particleVelocityVariation = cg(1.6 * vs)
        globs.acceleration = SCNVector3(x: 0, y: -11, z: 0)
        globs.particleLifeSpan = 1.1
        globs.particleLifeSpanVariation = 0.3
        globs.particleSize = cg(0.075 * s)
        globs.particleSizeVariation = cg(0.035 * s)
        globs.particleAngleVariation = 180
        globs.stretchFactor = 0.012
        addCurve(globs, .opacity, [1, 1, 0], [0, 0.85, 1])

        let mist = makeBurst(FXSpriteBank.smoke, additive: false, count: count(22, s), over: 0.1)
        makeOmni(mist, radius: 0.15 * s)
        mist.particleColor = tint.map { $0.withAlphaComponent(0.6) } ?? bloodMistColor
        mist.particleVelocity = cg(1.8 * vs)
        mist.particleVelocityVariation = 0.8
        mist.dampingFactor = 2.4
        mist.particleLifeSpan = 0.7
        mist.particleLifeSpanVariation = 0.2
        mist.particleSize = 1
        mist.particleAngleVariation = 180
        mist.particleAngularVelocityVariation = 60
        addCurve(mist, .size, [0.2 * s, 0.8 * s], [0, 1])
        addCurve(mist, .opacity, [0, 0.75, 0], [0, 0.1, 1])

        emit([drops, globs, mist], at: p, in: scene)
    }

    /// Blutlache: flaches, glänzendes Decal; wächst ~1.5 s, verblasst nach 20 s, max. 24 gleichzeitig.
    private static func spawnBloodPool(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        livePools.removeAll(where: { $0.parent == nil })
        while livePools.count >= maxLivePools {
            let oldest = livePools.removeFirst()
            oldest.removeAllActions()
            oldest.runAction(.sequence([.fadeOut(duration: 0.5), .removeFromParentNode()]))
        }
        let w = 1.1 * s * Float.random(in: 0.8...1.2)
        let h = 1.1 * s * Float.random(in: 0.8...1.2)
        let plane = SCNPlane(width: cg(w), height: cg(h))
        plane.materials = [poolMaterial(tint ?? bloodPoolColor)]
        let node = SCNNode(geometry: plane)
        node.name = transientNodeName
        node.castsShadow = false
        node.renderingOrder = 10
        // leicht gestaffelte Höhe gegen Z-Fighting überlappender Lachen
        let lift: Float = 0.006 + Float(livePools.count % 12) * 0.0008
        node.simdPosition = SIMD3<Float>(p.x, p.y + lift, p.z)
        let flat = simd_quatf(angle: -Float.pi / 2, axis: SIMD3<Float>(1, 0, 0))
        let spin = simd_quatf(angle: Float.random(in: 0..<(Float.pi * 2)), axis: SIMD3<Float>(0, 1, 0))
        node.simdOrientation = spin * flat
        node.simdScale = SIMD3<Float>(repeating: 0.12)
        scene.rootNode.addChildNode(node)
        livePools.append(node)
        let grow = SCNAction.scale(to: 1, duration: 1.5)
        grow.timingMode = .easeOut
        node.runAction(.sequence([grow, .wait(duration: 18.5), .fadeOut(duration: 2.0), .removeFromParentNode()]))
    }

    private static func poolMaterial(_ color: UIColor) -> SCNMaterial {
        let k = FXSpriteBank.key(color)
        if let m = poolMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = FXSpriteBank.splat(color)
        m.roughness.contents = NSNumber(value: 0.12)
        m.metalness.contents = NSNumber(value: 0.0)
        m.blendMode = .alpha
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = false
        poolMaterialCache[k] = m
        return m
    }

    /// Blut deaktiviert: dunkler Staub + graue Funken.
    private static func spawnBloodless(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dust = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.08)
        dust.particleColor = UIColor(red: 0.2, green: 0.2, blue: 0.22, alpha: 0.75)
        dust.birthDirection = .constant
        dust.emittingDirection = vec(dir)
        dust.spreadingAngle = 50
        dust.particleVelocity = cg(1.4 * vs)
        dust.particleVelocityVariation = 0.6
        dust.dampingFactor = 2.0
        dust.particleLifeSpan = 0.7
        dust.particleLifeSpanVariation = 0.2
        dust.particleSize = 1
        dust.particleAngleVariation = 180
        addCurve(dust, .size, [0.18 * s, 0.55 * s], [0, 1])
        addCurve(dust, .opacity, [0, 0.8, 0], [0, 0.15, 1])

        let sp = makeBurst(FXSpriteBank.spark, additive: true, count: count(22, s), over: 0.05)
        sp.birthDirection = .constant
        sp.emittingDirection = vec(dir)
        sp.spreadingAngle = 45
        sp.particleVelocity = cg(5.5 * vs)
        sp.particleVelocityVariation = cg(2.5 * vs)
        sp.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sp.particleLifeSpan = 0.32
        sp.particleLifeSpanVariation = 0.12
        sp.particleSize = cg(0.016 * s)
        sp.stretchFactor = 0.05
        sp.particleColor = UIColor(red: 0.85, green: 0.85, blue: 0.9, alpha: 1)
        sp.particleIntensity = 1.4
        addCurve(sp, .opacity, [1, 0], [0, 1])

        emit([dust, sp], at: p, in: scene)
    }

    // MARK: - Funken & Treffer

    private static func spawnSparks(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let sp = makeBurst(FXSpriteBank.spark, additive: true, count: count(48, s), over: 0.05)
        sp.birthDirection = .constant
        sp.emittingDirection = vec(dir)
        sp.spreadingAngle = 55
        sp.particleVelocity = cg(6.5 * vs)
        sp.particleVelocityVariation = cg(3.5 * vs)
        sp.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sp.dampingFactor = 0.6
        sp.particleLifeSpan = 0.42
        sp.particleLifeSpanVariation = 0.22
        sp.particleSize = cg(0.02 * s)
        sp.particleSizeVariation = cg(0.008 * s)
        sp.stretchFactor = 0.06
        sp.particleIntensity = 3.2
        sp.particleIntensityVariation = 1.5
        addColorCurve(sp, sparkColors(tint), [0, 0.25, 0.6, 1])

        let core = makeBurst(FXSpriteBank.glow, additive: true, count: 2, over: 0.04)
        core.particleVelocity = 0
        core.particleLifeSpan = 0.09
        core.particleSize = cg(0.35 * s)
        core.particleColor = tint ?? UIColor(red: 1.0, green: 0.85, blue: 0.55, alpha: 1)
        core.particleIntensity = 2.5
        addCurve(core, .opacity, [1, 0], [0, 1])

        emit([sp, core], at: p, in: scene)
    }

    private static func spawnHitFlash(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 1.0, green: 0.92, blue: 0.78, alpha: 1)
        let ck = FXSpriteBank.key(c)
        flashLight(at: p, in: scene, color: c, intensity: 2600 * Swift.min(2, s), range: 4.5 * s, duration: 0.13)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: c), key: "glow#" + ck,
                    at: p, in: scene, size: 1.1 * s, from: 0.45, to: 1.15, duration: 0.12, boost: 2.5)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.ring, baseKey: "ring", color: c), key: "ring#" + ck,
                    at: p, in: scene, size: 1.0 * s, from: 0.25, to: 1.7, duration: 0.2, boost: 1.6)

        let streaks = makeBurst(FXSpriteBank.spark, additive: true, count: count(12, s), over: 0.03)
        makeOmni(streaks, radius: 0.03 * s)
        streaks.particleVelocity = cg(9 * vs)
        streaks.particleVelocityVariation = cg(3 * vs)
        streaks.particleLifeSpan = 0.08
        streaks.particleLifeSpanVariation = 0.03
        streaks.particleSize = cg(0.03 * s)
        streaks.stretchFactor = 0.035
        streaks.particleColor = FXSpriteBank.mix(c, .white, 0.4)
        streaks.particleIntensity = 4
        addCurve(streaks, .opacity, [1, 0], [0, 1])
        emit([streaks], at: p, in: scene)
    }

    // MARK: - Feuer, Glut, Explosion

    private static func spawnFireBurst(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()

        let fire = makeBurst(FXSpriteBank.fire, additive: true, count: count(90, s), over: 0.12)
        fire.emitterShape = SCNSphere(radius: cg(0.12 * s))
        fire.birthLocation = .volume
        fire.birthDirection = .constant
        fire.emittingDirection = vec(dir)
        fire.spreadingAngle = 40
        fire.particleVelocity = cg(3.0 * vs)
        fire.particleVelocityVariation = cg(1.6 * vs)
        fire.acceleration = SCNVector3(x: 0, y: 2.2, z: 0)
        fire.dampingFactor = 1.6
        fire.particleLifeSpan = 0.75
        fire.particleLifeSpanVariation = 0.25
        fire.particleSize = 1
        fire.particleAngleVariation = 180
        fire.particleAngularVelocityVariation = 120
        fire.particleIntensity = 2.6
        fire.particleIntensityVariation = 0.8
        addCurve(fire, .size, [0.18 * s, 0.32 * s, 0.5 * s], [0, 0.3, 1])
        addColorCurve(fire, fireColors(tint), [0, 0.2, 0.55, 1])

        let embers = makeBurst(FXSpriteBank.spark, additive: true, count: count(26, s), over: 0.1)
        embers.birthDirection = .constant
        embers.emittingDirection = vec(dir)
        embers.spreadingAngle = 60
        embers.particleVelocity = cg(4 * vs)
        embers.particleVelocityVariation = cg(2 * vs)
        embers.acceleration = SCNVector3(x: 0, y: 0.6, z: 0)
        embers.dampingFactor = 0.8
        embers.particleLifeSpan = 1.3
        embers.particleLifeSpanVariation = 0.5
        embers.particleSize = cg(0.018 * s)
        embers.particleSizeVariation = cg(0.008 * s)
        embers.stretchFactor = 0.02
        embers.particleIntensity = 3.5
        addColorCurve(embers, sparkColors(tint == nil || FXSpriteBank.isWarm(tint ?? .orange) ? nil : tint), [0, 0.2, 0.6, 1])

        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.15)
        smoke.birthDirection = .constant
        smoke.emittingDirection = vec(dir)
        smoke.spreadingAngle = 35
        smoke.particleVelocity = cg(1.2 * vs)
        smoke.particleVelocityVariation = 0.5
        smoke.acceleration = SCNVector3(x: 0, y: 0.9, z: 0)
        smoke.dampingFactor = 0.8
        smoke.particleLifeSpan = 2.0
        smoke.particleLifeSpanVariation = 0.5
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 30
        smoke.particleColor = UIColor(red: 0.12, green: 0.11, blue: 0.11, alpha: 1)
        addCurve(smoke, .size, [0.4 * s, 1.3 * s], [0, 1])
        addCurve(smoke, .opacity, [0, 0, 0.45, 0], [0, 0.15, 0.35, 1])

        let lightColor = (tint == nil || FXSpriteBank.isWarm(tint ?? .orange))
            ? UIColor(red: 1.0, green: 0.55, blue: 0.2, alpha: 1)
            : (tint ?? UIColor.orange)
        flashLight(at: p, in: scene, color: lightColor, intensity: 3200 * Swift.min(2, s), range: 6 * s, duration: 0.35)
        emit([fire, embers, smoke], at: p, in: scene)
    }

    private static func spawnEmbers(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let e = makeBurst(FXSpriteBank.spark, additive: true, count: count(40, s), over: 0.15)
        e.emitterShape = SCNSphere(radius: cg(0.15 * s))
        e.birthLocation = .volume
        e.birthDirection = .constant
        e.emittingDirection = vec(dir)
        e.spreadingAngle = 60
        e.particleVelocity = cg(1.5 * vs)
        e.particleVelocityVariation = cg(1.0 * vs)
        e.acceleration = SCNVector3(x: 0.2, y: 0.8, z: 0.1)
        e.dampingFactor = 0.4
        e.particleLifeSpan = 1.6
        e.particleLifeSpanVariation = 0.6
        e.particleSize = cg(0.025 * s)
        e.particleSizeVariation = cg(0.012 * s)
        e.particleColor = tint ?? UIColor(red: 1.0, green: 0.5, blue: 0.14, alpha: 1)
        e.particleColorVariation = SCNVector4(x: 0.03, y: 0.1, z: 0.25, w: 0)
        e.particleIntensity = 3
        e.particleIntensityVariation = 1.2
        addCurve(e, .opacity, [0, 1, 0.5, 1, 0], [0, 0.1, 0.4, 0.65, 1])
        emit([e], at: p, in: scene)
    }

    private static func spawnExplosion(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let lightColor = (tint == nil || FXSpriteBank.isWarm(tint ?? .orange))
            ? UIColor(red: 1.0, green: 0.6, blue: 0.3, alpha: 1)
            : (tint ?? UIColor.orange)
        flashLight(at: p, in: scene, color: lightColor, intensity: 6500 * Swift.min(2, s), range: 14 * s, duration: 0.45)

        let flashColor = FXSpriteBank.mix(lightColor, .white, 0.5)
        let fk = FXSpriteBank.key(flashColor)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: flashColor), key: "glow#" + fk,
                    at: p, in: scene, size: 3.0 * s, from: 0.5, to: 1.2, duration: 0.25, boost: 2.5)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.ring, baseKey: "ring", color: flashColor), key: "ring#" + fk,
                    at: p, in: scene, size: 1.0 * s, from: 0.5, to: 7.0, duration: 0.38, boost: 1.4)

        let fireball = makeBurst(FXSpriteBank.fire, additive: true, count: count(110, s), over: 0.08)
        makeOmni(fireball, radius: 0.3 * s)
        fireball.particleVelocity = cg(6 * vs)
        fireball.particleVelocityVariation = cg(3 * vs)
        fireball.acceleration = SCNVector3(x: 0, y: 1.5, z: 0)
        fireball.dampingFactor = 3.2
        fireball.particleLifeSpan = 0.9
        fireball.particleLifeSpanVariation = 0.3
        fireball.particleSize = 1
        fireball.particleAngleVariation = 180
        fireball.particleAngularVelocityVariation = 90
        fireball.particleIntensity = 3
        fireball.particleIntensityVariation = 1
        addCurve(fireball, .size, [0.5 * s, 1.2 * s, 1.6 * s], [0, 0.35, 1])
        addColorCurve(fireball, fireColors(tint), [0, 0.18, 0.5, 1])

        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(36, s), over: 0.2)
        smoke.emitterShape = SCNSphere(radius: cg(0.4 * s))
        smoke.birthLocation = .volume
        smoke.birthDirection = .constant
        smoke.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        smoke.spreadingAngle = 80
        smoke.particleVelocity = cg(2.5 * vs)
        smoke.particleVelocityVariation = cg(1.2 * vs)
        smoke.acceleration = SCNVector3(x: 0, y: 1.1, z: 0)
        smoke.dampingFactor = 1.2
        smoke.particleLifeSpan = 3.2
        smoke.particleLifeSpanVariation = 0.8
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 25
        smoke.particleColor = UIColor(red: 0.07, green: 0.065, blue: 0.06, alpha: 1)
        addCurve(smoke, .size, [0.7 * s, 2.2 * s, 3.0 * s], [0, 0.4, 1])
        addCurve(smoke, .opacity, [0, 0.7, 0.5, 0], [0, 0.12, 0.5, 1])

        let sparks = makeBurst(FXSpriteBank.spark, additive: true, count: count(90, s), over: 0.06)
        makeOmni(sparks, radius: 0.2 * s)
        sparks.particleVelocity = cg(11 * vs)
        sparks.particleVelocityVariation = cg(5 * vs)
        sparks.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sparks.dampingFactor = 0.4
        sparks.particleLifeSpan = 1.0
        sparks.particleLifeSpanVariation = 0.4
        sparks.particleSize = cg(0.025 * s)
        sparks.particleSizeVariation = cg(0.01 * s)
        sparks.stretchFactor = 0.05
        sparks.particleIntensity = 4
        addColorCurve(sparks, sparkColors(nil), [0, 0.2, 0.6, 1])

        let debris = makeBurst(FXSpriteBank.flake, additive: false, count: count(30, s), over: 0.05)
        debris.emitterShape = SCNSphere(radius: cg(0.25 * s))
        debris.birthLocation = .volume
        debris.birthDirection = .constant
        debris.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        debris.spreadingAngle = 75
        debris.particleVelocity = cg(7 * vs)
        debris.particleVelocityVariation = cg(3 * vs)
        debris.acceleration = SCNVector3(x: 0, y: -14, z: 0)
        debris.particleLifeSpan = 1.6
        debris.particleLifeSpanVariation = 0.4
        debris.particleSize = cg(0.06 * s)
        debris.particleSizeVariation = cg(0.03 * s)
        debris.particleAngleVariation = 180
        debris.particleAngularVelocityVariation = 720
        debris.particleColor = UIColor(red: 0.05, green: 0.045, blue: 0.04, alpha: 1)
        addCurve(debris, .opacity, [1, 1, 0], [0, 0.85, 1])

        emit([fireball, smoke, sparks, debris], at: p, in: scene)
    }

    // MARK: - Eis, Rauch, Staub, Schatten, Netz, Strom, Asche

    private static func spawnIceShatter(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let iceColor = tint ?? UIColor(red: 0.72, green: 0.9, blue: 1.0, alpha: 1)

        let shards = makeBurst(FXSpriteBank.shard, additive: false, count: count(40, s), over: 0.05)
        makeOmni(shards, radius: 0.15 * s)
        shards.particleVelocity = cg(5 * vs)
        shards.particleVelocityVariation = cg(2.5 * vs)
        shards.acceleration = SCNVector3(x: 0, y: -12, z: 0)
        shards.dampingFactor = 0.3
        shards.particleLifeSpan = 0.9
        shards.particleLifeSpanVariation = 0.3
        shards.particleSize = cg(0.075 * s)
        shards.particleSizeVariation = cg(0.04 * s)
        shards.particleAngleVariation = 180
        shards.particleAngularVelocityVariation = 540
        shards.particleColor = iceColor
        shards.particleColorVariation = SCNVector4(x: 0, y: 0.15, z: 0.15, w: 0)
        addCurve(shards, .opacity, [1, 1, 0], [0, 0.75, 1])

        let glints = makeBurst(FXSpriteBank.spark, additive: true, count: count(24, s), over: 0.05)
        makeOmni(glints, radius: 0.15 * s)
        glints.particleVelocity = cg(4 * vs)
        glints.particleVelocityVariation = cg(2 * vs)
        glints.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        glints.particleLifeSpan = 0.5
        glints.particleLifeSpanVariation = 0.2
        glints.particleSize = cg(0.02 * s)
        glints.particleColor = FXSpriteBank.mix(iceColor, .white, 0.6)
        glints.particleIntensity = 3
        addCurve(glints, .opacity, [1, 0.3, 1, 0], [0, 0.3, 0.6, 1])

        let mist = makeBurst(FXSpriteBank.glow, additive: true, count: count(10, s), over: 0.06)
        makeOmni(mist, radius: 0.1 * s)
        mist.particleVelocity = cg(1 * vs)
        mist.particleVelocityVariation = 0.4
        mist.dampingFactor = 1.5
        mist.particleLifeSpan = 0.7
        mist.particleLifeSpanVariation = 0.2
        mist.particleSize = 1
        mist.particleColor = iceColor.withAlphaComponent(0.35)
        mist.particleIntensity = 0.8
        addCurve(mist, .size, [0.35 * s, 0.9 * s], [0, 1])
        addCurve(mist, .opacity, [0.8, 0], [0, 1])

        flashLight(at: p, in: scene, color: iceColor, intensity: 1500 * Swift.min(2, s), range: 4 * s, duration: 0.2)
        emit([shards, glints, mist], at: p, in: scene)
    }

    private static func spawnSmoke(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(18, s), over: 0.2)
        smoke.emitterShape = SCNSphere(radius: cg(0.15 * s))
        smoke.birthLocation = .volume
        smoke.birthDirection = .constant
        smoke.emittingDirection = vec(dir)
        smoke.spreadingAngle = 40
        smoke.particleVelocity = cg(0.8 * vs)
        smoke.particleVelocityVariation = cg(0.4 * vs)
        smoke.acceleration = SCNVector3(x: 0, y: 0.4, z: 0)
        smoke.dampingFactor = 0.8
        smoke.particleLifeSpan = 2.2
        smoke.particleLifeSpanVariation = 0.6
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 30
        smoke.particleColor = tint ?? UIColor(red: 0.18, green: 0.18, blue: 0.2, alpha: 1)
        addCurve(smoke, .size, [0.5 * s, 1.4 * s], [0, 1])
        addCurve(smoke, .opacity, [0, 0.55, 0], [0, 0.18, 1])
        emit([smoke], at: p, in: scene)
    }

    private static func spawnDust(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let ring = makeBurst(FXSpriteBank.smoke, additive: false, count: count(26, s), over: 0.06)
        ring.emitterShape = SCNTube(innerRadius: cg(0.22 * s), outerRadius: cg(0.24 * s), height: cg(0.06 * s))
        ring.birthLocation = .surface
        ring.birthDirection = .surfaceNormal
        ring.particleVelocity = cg(2.4 * vs)
        ring.particleVelocityVariation = cg(1.0 * vs)
        ring.acceleration = SCNVector3(x: 0, y: 0.25, z: 0)
        ring.dampingFactor = 2.6
        ring.particleLifeSpan = 1.3
        ring.particleLifeSpanVariation = 0.4
        ring.particleSize = 1
        ring.particleAngleVariation = 180
        ring.particleAngularVelocityVariation = 40
        ring.particleColor = tint ?? UIColor(red: 0.27, green: 0.25, blue: 0.23, alpha: 0.55)
        addCurve(ring, .size, [0.3 * s, 1.05 * s], [0, 1])
        addCurve(ring, .opacity, [0, 1, 0], [0, 0.12, 1])

        let pebbles = makeBurst(FXSpriteBank.flake, additive: false, count: count(10, s), over: 0.04)
        pebbles.birthDirection = .constant
        pebbles.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        pebbles.spreadingAngle = 55
        pebbles.particleVelocity = cg(3 * vs)
        pebbles.particleVelocityVariation = cg(1.2 * vs)
        pebbles.acceleration = SCNVector3(x: 0, y: -12, z: 0)
        pebbles.particleLifeSpan = 0.7
        pebbles.particleLifeSpanVariation = 0.2
        pebbles.particleSize = cg(0.03 * s)
        pebbles.particleSizeVariation = cg(0.015 * s)
        pebbles.particleAngleVariation = 180
        pebbles.particleAngularVelocityVariation = 400
        pebbles.particleColor = UIColor(red: 0.16, green: 0.15, blue: 0.14, alpha: 1)
        addCurve(pebbles, .opacity, [1, 1, 0], [0, 0.8, 1])

        emit([ring, pebbles], at: p, in: scene)
    }

    private static func spawnShadowBurst(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let glowColor = tint ?? UIColor(red: 0.55, green: 0.12, blue: 1.0, alpha: 1)

        let dark = makeBurst(FXSpriteBank.smoke, additive: false, count: count(36, s), over: 0.06)
        makeOmni(dark, radius: 0.15 * s)
        dark.particleVelocity = cg(3.2 * vs)
        dark.particleVelocityVariation = cg(1.6 * vs)
        dark.dampingFactor = 2.4
        dark.particleLifeSpan = 1.0
        dark.particleLifeSpanVariation = 0.3
        dark.particleSize = 1
        dark.particleAngleVariation = 180
        dark.particleAngularVelocityVariation = 90
        dark.particleColor = UIColor(red: 0.03, green: 0.0, blue: 0.05, alpha: 0.85)
        addCurve(dark, .size, [0.3 * s, 1.1 * s], [0, 1])
        addCurve(dark, .opacity, [1, 0.8, 0], [0, 0.4, 1])

        let wisps = makeBurst(FXSpriteBank.glow, additive: true, count: count(40, s), over: 0.06)
        makeOmni(wisps, radius: 0.1 * s)
        wisps.particleVelocity = cg(4.5 * vs)
        wisps.particleVelocityVariation = cg(2 * vs)
        wisps.dampingFactor = 1.5
        wisps.particleLifeSpan = 0.6
        wisps.particleLifeSpanVariation = 0.2
        wisps.particleSize = cg(0.12 * s)
        wisps.particleSizeVariation = cg(0.05 * s)
        wisps.stretchFactor = 0.08
        wisps.particleColor = glowColor
        wisps.particleIntensity = 2.4
        addCurve(wisps, .opacity, [1, 0], [0, 1])

        let core = makeBurst(FXSpriteBank.glow, additive: true, count: 3, over: 0.04)
        core.particleVelocity = 0
        core.particleLifeSpan = 0.18
        core.particleSize = cg(0.9 * s)
        core.particleColor = glowColor
        core.particleIntensity = 2
        addCurve(core, .opacity, [1, 0], [0, 1])

        flashLight(at: p, in: scene, color: glowColor, intensity: 2400 * Swift.min(2, s), range: 6 * s, duration: 0.3)
        emit([dark, wisps, core], at: p, in: scene)
    }

    private static func spawnWebHit(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 0.95, green: 0.97, blue: 1.0, alpha: 1)

        let splat = makeBurst(FXSpriteBank.web, additive: false, count: 2, over: 0.04)
        splat.sortingMode = .none
        splat.particleVelocity = 0
        splat.particleLifeSpan = 0.45
        splat.particleSize = 1
        splat.particleAngleVariation = 180
        splat.particleColor = c
        addCurve(splat, .size, [0.25 * s, 0.85 * s, 0.9 * s], [0, 0.25, 1])
        addCurve(splat, .opacity, [1, 1, 0], [0, 0.6, 1])

        let strands = makeBurst(FXSpriteBank.spark, additive: true, count: count(22, s), over: 0.04)
        strands.birthDirection = .constant
        strands.emittingDirection = vec(dir)
        strands.spreadingAngle = 70
        strands.particleVelocity = cg(5 * vs)
        strands.particleVelocityVariation = cg(2 * vs)
        strands.dampingFactor = 3
        strands.particleLifeSpan = 0.3
        strands.particleLifeSpanVariation = 0.1
        strands.particleSize = cg(0.015 * s)
        strands.stretchFactor = 0.12
        strands.particleColor = c
        strands.particleIntensity = 1.4
        addCurve(strands, .opacity, [1, 0], [0, 1])

        let puff = makeBurst(FXSpriteBank.glow, additive: false, count: count(6, s), over: 0.04)
        puff.birthDirection = .constant
        puff.emittingDirection = vec(dir)
        puff.spreadingAngle = 60
        puff.particleVelocity = cg(0.8 * vs)
        puff.dampingFactor = 2
        puff.particleLifeSpan = 0.35
        puff.particleSize = 1
        puff.particleColor = c.withAlphaComponent(0.35)
        addCurve(puff, .size, [0.2 * s, 0.5 * s], [0, 1])
        addCurve(puff, .opacity, [1, 0], [0, 1])

        emit([splat, strands, puff], at: p, in: scene)
    }

    private static func spawnRiftPortal(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let c = tint ?? defaultRiftColor
        let portal = makeRiftSwirl(color: c)
        portal.name = transientNodeName
        portal.simdPosition = p
        portal.simdScale = SIMD3<Float>(repeating: 0.01)
        scene.rootNode.addChildNode(portal)
        let open = SCNAction.scale(to: cg(s), duration: 0.35)
        open.timingMode = .easeOut
        let close = SCNAction.scale(to: 0.01, duration: 0.4)
        close.timingMode = .easeIn
        portal.runAction(.sequence([open, .wait(duration: 1.9), close, .removeFromParentNode()]))

        // Öffnungs-Stoß
        let vs = s.squareRoot()
        let wisps = makeBurst(FXSpriteBank.glow, additive: true, count: count(30, s), over: 0.08)
        makeOmni(wisps, radius: 0.3 * s)
        wisps.particleVelocity = cg(3.5 * vs)
        wisps.particleVelocityVariation = cg(1.5 * vs)
        wisps.dampingFactor = 2
        wisps.particleLifeSpan = 0.6
        wisps.particleLifeSpanVariation = 0.2
        wisps.particleSize = cg(0.14 * s)
        wisps.stretchFactor = 0.06
        wisps.particleColor = c
        wisps.particleIntensity = 2.2
        addCurve(wisps, .opacity, [1, 0], [0, 1])
        emit([wisps], at: p, in: scene)
    }

    private static func spawnElectric(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 0.55, green: 0.8, blue: 1.0, alpha: 1)

        // flackernde Blitze über ~0.35 s
        let bolts = makeBurst(FXSpriteBank.bolt, additive: true, count: count(16, s), over: 0.35)
        bolts.emitterShape = SCNSphere(radius: cg(0.35 * s))
        bolts.birthLocation = .volume
        bolts.particleVelocity = 0
        bolts.particleLifeSpan = 0.09
        bolts.particleLifeSpanVariation = 0.05
        bolts.particleSize = cg(0.45 * s)
        bolts.particleSizeVariation = cg(0.2 * s)
        bolts.particleAngleVariation = 180
        bolts.particleColor = FXSpriteBank.mix(c, .white, 0.25)
        bolts.particleIntensity = 3.5
        bolts.particleIntensityVariation = 1.5

        let sparks = makeBurst(FXSpriteBank.spark, additive: true, count: count(30, s), over: 0.3)
        makeOmni(sparks, radius: 0.25 * s)
        sparks.particleVelocity = cg(5 * vs)
        sparks.particleVelocityVariation = cg(2.5 * vs)
        sparks.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        sparks.particleLifeSpan = 0.3
        sparks.particleLifeSpanVariation = 0.15
        sparks.particleSize = cg(0.016 * s)
        sparks.stretchFactor = 0.05
        sparks.particleColor = FXSpriteBank.mix(c, .white, 0.5)
        sparks.particleIntensity = 3
        addCurve(sparks, .opacity, [1, 0], [0, 1])

        let haze = makeBurst(FXSpriteBank.glow, additive: true, count: 3, over: 0.05)
        haze.particleVelocity = 0
        haze.particleLifeSpan = 0.4
        haze.particleSize = cg(1.0 * s)
        haze.particleColor = c
        haze.particleIntensity = 1.2
        addCurve(haze, .opacity, [0.8, 0.3, 0.7, 0], [0, 0.3, 0.55, 1])

        flashLight(at: p, in: scene, color: c, intensity: 2200 * Swift.min(2, s), range: 5 * s, duration: 0.4, flicker: true)
        emit([bolts, sparks, haze], at: p, in: scene)
    }

    private static func spawnAsh(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let flakes = makeBurst(FXSpriteBank.flake, additive: false, count: count(90, s), over: 0.25)
        flakes.emitterShape = SCNSphere(radius: cg(0.35 * s))
        flakes.birthLocation = .volume
        flakes.birthDirection = .constant
        flakes.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        flakes.spreadingAngle = 70
        flakes.particleVelocity = cg(1.2 * vs)
        flakes.particleVelocityVariation = cg(0.8 * vs)
        flakes.acceleration = SCNVector3(x: 0.1, y: -0.7, z: 0.05)
        flakes.dampingFactor = 0.9
        flakes.particleLifeSpan = 3.0
        flakes.particleLifeSpanVariation = 1.0
        flakes.particleSize = cg(0.045 * s)
        flakes.particleSizeVariation = cg(0.025 * s)
        flakes.particleAngleVariation = 180
        flakes.particleAngularVelocityVariation = 200
        flakes.particleColor = tint ?? UIColor(red: 0.16, green: 0.15, blue: 0.15, alpha: 0.95)
        flakes.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        addCurve(flakes, .opacity, [0, 1, 1, 0], [0, 0.05, 0.7, 1])

        let glowing = makeBurst(FXSpriteBank.spark, additive: true, count: count(24, s), over: 0.25)
        glowing.emitterShape = SCNSphere(radius: cg(0.3 * s))
        glowing.birthLocation = .volume
        glowing.birthDirection = .constant
        glowing.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        glowing.spreadingAngle = 50
        glowing.particleVelocity = cg(1.5 * vs)
        glowing.particleVelocityVariation = 0.6
        glowing.acceleration = SCNVector3(x: 0, y: 0.4, z: 0)
        glowing.dampingFactor = 0.6
        glowing.particleLifeSpan = 1.5
        glowing.particleLifeSpanVariation = 0.6
        glowing.particleSize = cg(0.02 * s)
        glowing.particleColor = UIColor(red: 1.0, green: 0.45, blue: 0.1, alpha: 1)
        glowing.particleIntensity = 3
        addCurve(glowing, .opacity, [1, 0.6, 1, 0], [0, 0.3, 0.6, 1])

        let cloud = makeBurst(FXSpriteBank.smoke, additive: false, count: count(8, s), over: 0.2)
        cloud.emitterShape = SCNSphere(radius: cg(0.3 * s))
        cloud.birthLocation = .volume
        cloud.birthDirection = .constant
        cloud.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        cloud.spreadingAngle = 60
        cloud.particleVelocity = cg(0.6 * vs)
        cloud.dampingFactor = 0.8
        cloud.particleLifeSpan = 2.5
        cloud.particleLifeSpanVariation = 0.5
        cloud.particleSize = 1
        cloud.particleAngleVariation = 180
        cloud.particleColor = UIColor(red: 0.1, green: 0.1, blue: 0.1, alpha: 1)
        addCurve(cloud, .size, [0.5 * s, 1.6 * s], [0, 1])
        addCurve(cloud, .opacity, [0, 0.4, 0], [0, 0.2, 1])

        emit([flakes, glowing, cloud], at: p, in: scene)
    }

    // MARK: - Schleifende Systeme für Geschosse

    fileprivate static func trailSystem(color: UIColor, size: Float, dark: Bool) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = dark ? FXSpriteBank.smoke : FXSpriteBank.glow
        p.blendMode = dark ? .alpha : .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(160 * countScale + 20)
        p.particleVelocity = 0
        p.particleLifeSpan = 0.22
        p.particleLifeSpanVariation = 0.05
        p.particleSize = 1
        p.particleColor = dark ? UIColor(red: 0.04, green: 0.0, blue: 0.06, alpha: 0.8) : color
        p.particleIntensity = dark ? 1 : 1.8
        let sz = Swift.max(0.01, size)
        FX.addCurve(p, .size, [sz, sz * 0.25], [0, 1])
        FX.addCurve(p, .opacity, [0.75, 0], [0, 1])
        return p
    }

    fileprivate static func flameLicks(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.fire
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(70 * countScale + 15)
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.55))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
        p.particleVelocity = CGFloat(r * 1.5)
        p.particleVelocityVariation = CGFloat(r)
        p.acceleration = SCNVector3(x: 0, y: 1.5, z: 0)
        p.particleLifeSpan = 0.32
        p.particleLifeSpanVariation = 0.1
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleAngularVelocityVariation = 180
        p.particleIntensity = 2.4
        FX.addCurve(p, .size, [r * 1.3, r * 0.5], [0, 1])
        FX.addColorCurve(p, FX.fireColors(color), [0, 0.25, 0.6, 1])
        return p
    }

    fileprivate static func darkWisps(radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.smoke
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(50 * countScale + 10)
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.5))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
        p.particleVelocity = 0.3
        p.particleVelocityVariation = 0.15
        p.particleLifeSpan = 0.45
        p.particleLifeSpanVariation = 0.1
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleColor = UIColor(red: 0.03, green: 0.0, blue: 0.05, alpha: 0.7)
        FX.addCurve(p, .size, [r * 1.2, r * 2.2], [0, 1])
        FX.addCurve(p, .opacity, [0.8, 0], [0, 1])
        return p
    }

    fileprivate static func risingSparks(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(90 * countScale + 15)
        p.emitterShape = SCNCylinder(radius: CGFloat(r * 1.1), height: 0.02)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 20
        p.particleVelocity = 2.5
        p.particleVelocityVariation = 1
        p.particleLifeSpan = 0.45
        p.particleLifeSpanVariation = 0.15
        p.particleSize = CGFloat(r * 0.18)
        p.particleSizeVariation = CGFloat(r * 0.08)
        p.stretchFactor = 0.04
        p.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        p.particleIntensity = 2.4
        FX.addCurve(p, .opacity, [1, 0.8, 0], [0, 0.5, 1])
        return p
    }

    fileprivate static func groundDustTrail(radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.smoke
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(25 * countScale + 5)
        p.emitterShape = SCNCylinder(radius: CGFloat(r), height: 0.05)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 40
        p.particleVelocity = 0.6
        p.particleVelocityVariation = 0.3
        p.dampingFactor = 1.2
        p.particleLifeSpan = 0.9
        p.particleLifeSpanVariation = 0.3
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleColor = UIColor(red: 0.25, green: 0.23, blue: 0.21, alpha: 0.6)
        FX.addCurve(p, .size, [r * 0.8, r * 1.8], [0, 1])
        FX.addCurve(p, .opacity, [0, 0.6, 0], [0, 0.2, 1])
        return p
    }

    fileprivate static func crackle(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.bolt
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = true
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = 18
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.6))
        p.birthLocation = .volume
        p.particleVelocity = 0
        p.particleLifeSpan = 0.07
        p.particleLifeSpanVariation = 0.03
        p.particleSize = CGFloat(r * 2.2)
        p.particleSizeVariation = CGFloat(r * 0.8)
        p.particleAngleVariation = 180
        p.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        p.particleIntensity = 3
        return p
    }
}

// MARK: - WebStrand

/// Dünne leuchtende Linie zwischen zwei Weltpunkten (Netz, Ketten, Ranken).
/// node an scene.rootNode (oder einen unskalierten Knoten) hängen und jeden Frame update(from:to:) aufrufen.
final class WebStrand {
    let node: SCNNode
    private let coreNode: SCNNode
    private let glowNode: SCNNode

    init(color: UIColor = .white, radius: Float = 0.012) {
        let r: Float = (radius.isFinite && radius > 0.0005) ? radius : 0.012
        let root = SCNNode()
        root.name = "fx.webStrand"
        root.castsShadow = false

        // Kern: Einheitszylinder (Höhe 1, entlang +Y) – Länge über simdScale.y
        let core = SCNCylinder(radius: CGFloat(r), height: 1)
        core.radialSegmentCount = 8
        core.heightSegmentCount = 1
        let coreMaterial = SCNMaterial()
        coreMaterial.lightingModel = .constant
        coreMaterial.diffuse.contents = color
        coreMaterial.emission.contents = color
        coreMaterial.emission.intensity = 0.6
        core.materials = [coreMaterial]
        let coreN = SCNNode(geometry: core)
        coreN.castsShadow = false
        root.addChildNode(coreN)

        // weicher Schimmer (additiv, breiter)
        let glow = SCNCylinder(radius: CGFloat(r * 3.2), height: 1)
        glow.radialSegmentCount = 8
        glow.heightSegmentCount = 1
        let glowMaterial = SCNMaterial()
        glowMaterial.lightingModel = .constant
        glowMaterial.diffuse.contents = FXSpriteBank.scaled(color, 0.22, alpha: 1)
        glowMaterial.blendMode = .add
        glowMaterial.writesToDepthBuffer = false
        glowMaterial.readsFromDepthBuffer = true
        glow.materials = [glowMaterial]
        let glowN = SCNNode(geometry: glow)
        glowN.castsShadow = false
        glowN.renderingOrder = 30
        glowN.isHidden = FX.quality == .performance
        root.addChildNode(glowN)

        root.simdScale = SIMD3<Float>(1, 0.0001, 1)
        node = root
        coreNode = coreN
        glowNode = glowN
    }

    /// Weltpositionen der beiden Enden.
    func update(from: SIMD3<Float>, to: SIMD3<Float>) {
        guard from.x.isFinite, from.y.isFinite, from.z.isFinite,
              to.x.isFinite, to.y.isFinite, to.z.isFinite else { return }
        let d = to - from
        let len = simd_length(d)
        node.simdWorldPosition = (from + to) * 0.5
        if len > 1e-5 {
            node.simdWorldOrientation = WebStrand.rotationFromUp(to: d / len)
        }
        node.simdScale = SIMD3<Float>(1, Swift.max(len, 0.0001), 1)
    }

    var isHidden: Bool {
        get { return node.isHidden }
        set { node.isHidden = newValue }
    }

    /// Quaternion, das +Y auf dir dreht (stabil auch bei exakt entgegengesetzter Richtung).
    static func rotationFromUp(to dir: SIMD3<Float>) -> simd_quatf {
        let up = SIMD3<Float>(0, 1, 0)
        let dp = simd_dot(up, dir)
        if dp > 0.99999 {
            return simd_quatf(angle: 0, axis: SIMD3<Float>(1, 0, 0))
        }
        if dp < -0.99999 {
            return simd_quatf(angle: Float.pi, axis: SIMD3<Float>(1, 0, 0))
        }
        return simd_quatf(from: up, to: dir)
    }
}

// MARK: - CameraShake

/// Trauma-basiertes Kamerawackeln: Amplitude = trauma², glattes Rauschen aus Sinus-Summen, Abbau ~1.2/s.
final class CameraShake {
    private(set) var trauma: Float = 0
    var maxTranslation: Float = 0.28      // Meter bei trauma = 1
    var maxRoll: Float = 0.07             // Radiant bei trauma = 1
    var decayPerSecond: Float = 1.2
    var frequency: Float = 24
    private var time: Float = 0

    init() {}

    func add(_ trauma: Float) {
        guard trauma.isFinite else { return }
        self.trauma = Swift.min(1, Swift.max(0, self.trauma + trauma))
    }

    func update(dt: Float) -> (offset: SIMD3<Float>, roll: Float) {
        let step: Float = (dt.isFinite && dt > 0) ? Swift.min(dt, 0.1) : 0
        time += step
        if time > 10_000 { time = 0 }
        trauma = Swift.max(0, trauma - decayPerSecond * step)
        let amp = trauma * trauma
        if amp < 0.0001 {
            return (offset: SIMD3<Float>(0, 0, 0), roll: 0)
        }
        let t = time * frequency
        let x = CameraShake.smoothNoise(t, seed: 1.3)
        let y = CameraShake.smoothNoise(t, seed: 7.9)
        let z = CameraShake.smoothNoise(t, seed: 3.7)
        let r = CameraShake.smoothNoise(t, seed: 5.1)
        let offset = SIMD3<Float>(x, y, z * 0.5) * (maxTranslation * amp)
        return (offset: offset, roll: r * maxRoll * amp)
    }

    func reset() {
        trauma = 0
        time = 0
    }

    /// Perlin-artiges, glattes Rauschen in etwa [-1, 1].
    private static func smoothNoise(_ t: Float, seed: Float) -> Float {
        let a = sin(t * 1.0 + seed * 12.9898)
        let b = sin(t * 2.17 + seed * 78.233) * 0.5
        let c = sin(t * 4.73 + seed * 37.719) * 0.25
        let d = sin(t * 0.61 + seed * 4.1) * 0.35
        return (a + b + c + d) / 2.1
    }
}

// MARK: - ProjectileVisual

/// Leuchtendes Geschoss (Orb / Feuerball / Netzkopf / Bodenwelle). Nur Optik – Bewegung macht der Controller.
/// Orientierungsunabhängig; bei .groundWave liegt der Ursprung auf Bodenhöhe.
final class ProjectileVisual {
    let node: SCNNode
    let style: SpecialKind

    init(color: UIColor, radius: Float, style: SpecialKind) {
        let r: Float = (radius.isFinite && radius > 0.02) ? Swift.min(radius, 3) : 0.2
        let root = SCNNode()
        root.name = "fx.projectile"
        root.castsShadow = false
        let dark = FXSpriteBank.luminance(color) < 0.12
        let glowColor: UIColor = dark ? UIColor(red: 0.5, green: 0.14, blue: 0.9, alpha: 1) : color

        switch style {
        case .projectile, .dashStrike, .teleportStrike, .counter:
            ProjectileVisual.buildOrb(on: root, color: color, glow: glowColor, radius: r, dark: dark)
        case .grabSlam:
            ProjectileVisual.buildOrb(on: root, color: color, glow: glowColor, radius: r, dark: dark)
            root.addParticleSystem(FX.crackle(color: glowColor, radius: r))
        case .pullIn:
            ProjectileVisual.buildHead(on: root, color: color, glow: glowColor, radius: r, dark: dark)
        case .groundWave:
            ProjectileVisual.buildWave(on: root, color: color, glow: glowColor, radius: r)
        }

        if FX.quality != .performance {
            let light = SCNLight()
            light.type = .omni
            light.color = glowColor
            light.intensity = dark ? 350 : 650
            light.attenuationStartDistance = 0
            light.attenuationEndDistance = CGFloat(Swift.max(3, r * 14))
            light.attenuationFalloffExponent = 2
            light.castsShadow = false
            let lightNode = SCNNode()
            lightNode.light = light
            if style == .groundWave {
                lightNode.simdPosition = SIMD3<Float>(0, r * 0.8, 0)
            }
            root.addChildNode(lightNode)
        }

        self.node = root
        self.style = style
    }

    private static func coreMaterial(_ color: UIColor, dark: Bool, boost: CGFloat) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .constant
        if dark {
            m.diffuse.contents = UIColor(red: 0.02, green: 0.0, blue: 0.04, alpha: 1)
        } else {
            let hot = FXSpriteBank.mix(color, .white, 0.7)
            m.diffuse.contents = hot
            m.emission.contents = hot
            m.emission.intensity = boost
        }
        return m
    }

    private static func addHalo(to parent: SCNNode, color: UIColor, size: Float, boost: Float) -> SCNNode {
        let image = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: color)
        let plane = SCNPlane(width: CGFloat(size), height: CGFloat(size))
        plane.materials = [FX.spriteMaterial(image, key: "glow#" + FXSpriteBank.key(color), boost: boost)]
        let halo = SCNNode(geometry: plane)
        halo.constraints = [SCNBillboardConstraint()]
        halo.castsShadow = false
        halo.renderingOrder = 55
        parent.addChildNode(halo)
        return halo
    }

    private static func buildOrb(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float, dark: Bool) {
        let segments = FX.quality == .performance ? 16 : 32
        let core = SCNSphere(radius: CGFloat(r * 0.5))
        core.segmentCount = segments
        core.materials = [ProjectileVisual.coreMaterial(color, dark: dark, boost: 1.6)]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        root.addChildNode(coreNode)

        let halo = ProjectileVisual.addHalo(to: root, color: glow, size: r * 4.4, boost: 1.8)
        let a1 = SCNAction.scale(to: 1.12, duration: 0.12)
        let a2 = SCNAction.scale(to: 0.92, duration: 0.14)
        halo.runAction(.repeatForever(.sequence([a1, a2])))

        // Energieringe
        let ringMaterial = FX.glowLineMaterial(glow, boost: 2.0)
        for i in 0..<2 {
            let torus = SCNTorus(ringRadius: CGFloat(r * (0.8 + 0.15 * Float(i))), pipeRadius: CGFloat(r * 0.045))
            torus.ringSegmentCount = FX.quality == .performance ? 24 : 48
            torus.pipeSegmentCount = 6
            torus.materials = [ringMaterial]
            let ring = SCNNode(geometry: torus)
            ring.castsShadow = false
            ring.simdEulerAngles = i == 0 ? SIMD3<Float>(1.1, 0, 0.4) : SIMD3<Float>(-0.6, 0, 1.2)
            let gimbal = SCNNode()
            gimbal.addChildNode(ring)
            let turn: CGFloat = i == 0 ? 1 : -1
            let spin = SCNAction.rotateBy(x: 0, y: CGFloat.pi * 2 * turn, z: 0, duration: i == 0 ? 0.45 : 0.6)
            gimbal.runAction(.repeatForever(spin))
            root.addChildNode(gimbal)
        }

        root.addParticleSystem(FX.trailSystem(color: glow, size: r * 1.3, dark: dark))
        if dark {
            root.addParticleSystem(FX.darkWisps(radius: r))
        } else if FXSpriteBank.isWarm(color) {
            root.addParticleSystem(FX.flameLicks(color: color, radius: r))
        }
    }

    private static func buildHead(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float, dark: Bool) {
        let material = ProjectileVisual.coreMaterial(color, dark: dark, boost: 1.2)
        let spinner = SCNNode()
        root.addChildNode(spinner)

        let core = SCNSphere(radius: CGFloat(r * 0.42))
        core.segmentCount = FX.quality == .performance ? 16 : 24
        core.materials = [material]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        spinner.addChildNode(coreNode)

        // sechs Stacheln (Kettenkopf / Netzkugel)
        let dirs: [SIMD3<Float>] = [
            SIMD3<Float>(1, 0, 0), SIMD3<Float>(-1, 0, 0),
            SIMD3<Float>(0, 1, 0), SIMD3<Float>(0, -1, 0),
            SIMD3<Float>(0, 0, 1), SIMD3<Float>(0, 0, -1)
        ]
        let spikeHeight = r * 0.75
        let cone = SCNCone(topRadius: 0, bottomRadius: CGFloat(r * 0.16), height: CGFloat(spikeHeight))
        cone.radialSegmentCount = 10
        cone.materials = [material]
        for d in dirs {
            let spike = SCNNode(geometry: cone)
            spike.castsShadow = false
            spike.simdOrientation = WebStrand.rotationFromUp(to: d)
            spike.simdPosition = d * (r * 0.42 + spikeHeight * 0.5)
            spinner.addChildNode(spike)
        }
        let spin = SCNAction.rotateBy(x: CGFloat.pi * 2, y: CGFloat.pi * 1.4, z: 0, duration: 0.5)
        spinner.runAction(.repeatForever(spin))

        _ = ProjectileVisual.addHalo(to: root, color: glow, size: r * 3.2, boost: 1.4)
        root.addParticleSystem(FX.trailSystem(color: glow, size: r * 0.9, dark: dark))
    }

    private static func buildWave(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float) {
        // leuchtende Kuppel (untere Hälfte steckt im Boden)
        let dome = SCNSphere(radius: CGFloat(r))
        dome.segmentCount = FX.quality == .performance ? 16 : 28
        let domeMaterial = SCNMaterial()
        domeMaterial.lightingModel = .constant
        let soft = FXSpriteBank.scaled(glow, 0.45, alpha: 1)
        domeMaterial.diffuse.contents = soft
        domeMaterial.emission.contents = soft
        domeMaterial.emission.intensity = 0.8
        domeMaterial.blendMode = .add
        domeMaterial.writesToDepthBuffer = false
        domeMaterial.readsFromDepthBuffer = true
        dome.materials = [domeMaterial]
        let domeNode = SCNNode(geometry: dome)
        domeNode.castsShadow = false
        domeNode.renderingOrder = 50
        domeNode.simdScale = SIMD3<Float>(1.3, 0.6, 1.3)
        root.addChildNode(domeNode)
        let grow = SCNAction.scale(by: 1.08, duration: 0.15)
        grow.timingMode = .easeInEaseOut
        domeNode.runAction(.repeatForever(.sequence([grow, grow.reversed()])))

        // heißer Kern
        let core = SCNSphere(radius: CGFloat(r * 0.45))
        core.segmentCount = 16
        core.materials = [ProjectileVisual.coreMaterial(color, dark: false, boost: 1.4)]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        coreNode.simdScale = SIMD3<Float>(1.4, 0.6, 1.4)
        root.addChildNode(coreNode)

        // Bodenglühen (flach)
        let image = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: glow)
        let plane = SCNPlane(width: CGFloat(r * 5), height: CGFloat(r * 5))
        plane.materials = [FX.spriteMaterial(image, key: "glow#" + FXSpriteBank.key(glow), boost: 1.5)]
        let groundGlow = SCNNode(geometry: plane)
        groundGlow.castsShadow = false
        groundGlow.renderingOrder = 45
        groundGlow.simdEulerAngles = SIMD3<Float>(-Float.pi / 2, 0, 0)
        groundGlow.simdPosition = SIMD3<Float>(0, 0.02, 0)
        root.addChildNode(groundGlow)

        root.addParticleSystem(FX.risingSparks(color: glow, radius: r))
        root.addParticleSystem(FX.groundDustTrail(radius: r))
        if FXSpriteBank.isWarm(color) {
            root.addParticleSystem(FX.flameLicks(color: color, radius: r))
        }
    }
}

// =====================================================================
// MARK: - Graphics/MeshBuilder.swift
// =====================================================================

// =====================================================================
//  MeshBuilder – sammelt viele Boxen / Quads / Zylinder in EINER
//  SCNGeometry (ein Draw-Call pro Material und Chunk).
//
//  Konventionen:
//  - Vorderseiten sind gegen den Uhrzeigersinn (CCW) gewunden (SceneKit-Standard).
//  - UVs in Welteinheiten: 1 Textur-Kachel = 1 / uvScale Meter.
//    (Fassaden: uvScale 0.1 → Kachel 10 m = 4 Stockwerke à 2,5 m x 4 Fensterachsen.)
//  - Seitenflächen von Boxen: u läuft horizontal von der linken Kante, v vertikal von unten.
//    Die Kachelzahl wird auf ganze Kacheln gerundet (Fenster werden an Ecken/Dachkante nicht
//    abgeschnitten) und pro Fläche um ein zufälliges Viertel versetzt (Fenstermuster
//    wiederholen sich nicht von Gebäude zu Gebäude).
//  - Ober-/Unterseiten: Welt-XZ-Projektion (nahtlose Dächer / Straßen).
//  - Texturkoordinate v = 0 ist der obere Bildrand (SceneKit / UIKit-Konvention).
// =====================================================================

struct MeshBuilder {
    private var positions: [SCNVector3] = []
    private var normals: [SCNVector3] = []
    private var uvs: [CGPoint] = []
    private var indices: [UInt32] = []

    /// Rundet die Kachelanzahl auf Seitenflächen auf ganze Kacheln (ab 0.75 Kacheln).
    var snapsTilesToFaces: Bool = true
    /// Versetzt jede Seitenfläche um ein zufälliges Viertel einer Kachel (deterministisch aus der Position).
    var variesFaceOffsets: Bool = true

    init() {}

    /// Optional: Speicher für ungefähr so viele Boxen vorab reservieren.
    init(reserveBoxes: Int) {
        let quads = Swift.max(0, reserveBoxes) * 6
        positions.reserveCapacity(quads * 4)
        normals.reserveCapacity(quads * 4)
        uvs.reserveCapacity(quads * 4)
        indices.reserveCapacity(quads * 6)
    }

    var isEmpty: Bool { return indices.isEmpty }
    var vertexCount: Int { return positions.count }
    var triangleCount: Int { return indices.count / 3 }

    mutating func removeAll() {
        positions.removeAll(keepingCapacity: true)
        normals.removeAll(keepingCapacity: true)
        uvs.removeAll(keepingCapacity: true)
        indices.removeAll(keepingCapacity: true)
    }

    // MARK: - Public shapes

    /// Achsenparallele Box. Ohne Unterseite (Gebäude stehen auf dem Boden), außer includeBottom.
    mutating func addBox(min lo: SIMD3<Float>, max hi: SIMD3<Float>, uvScale: Float = 0.1, includeBottom: Bool = false) {
        let a = simd_min(lo, hi)
        let b = simd_max(lo, hi)
        let d = b - a
        let up = MeshBuilder.axisY
        // +X (rechts = -Z)
        pushFace(origin: SIMD3<Float>(b.x, a.y, b.z), right: MeshBuilder.axisNegZ, up: up,
                 width: d.z, height: d.y, uvScale: uvScale, horizontal: false, salt: 11)
        // -X (rechts = +Z)
        pushFace(origin: SIMD3<Float>(a.x, a.y, a.z), right: MeshBuilder.axisZ, up: up,
                 width: d.z, height: d.y, uvScale: uvScale, horizontal: false, salt: 23)
        // +Z (rechts = +X)
        pushFace(origin: SIMD3<Float>(a.x, a.y, b.z), right: MeshBuilder.axisX, up: up,
                 width: d.x, height: d.y, uvScale: uvScale, horizontal: false, salt: 37)
        // -Z (rechts = -X)
        pushFace(origin: SIMD3<Float>(b.x, a.y, a.z), right: MeshBuilder.axisNegX, up: up,
                 width: d.x, height: d.y, uvScale: uvScale, horizontal: false, salt: 41)
        // Oberseite (Normal +Y)
        pushFace(origin: SIMD3<Float>(a.x, b.y, b.z), right: MeshBuilder.axisX, up: MeshBuilder.axisNegZ,
                 width: d.x, height: d.z, uvScale: uvScale, horizontal: true, salt: 53)
        if includeBottom {
            // Unterseite (Normal -Y)
            pushFace(origin: SIMD3<Float>(a.x, a.y, a.z), right: MeshBuilder.axisX, up: MeshBuilder.axisZ,
                     width: d.x, height: d.z, uvScale: uvScale, horizontal: true, salt: 67)
        }
    }

    /// Beliebiges (planares) Viereck. a→b→c→d gegen den Uhrzeigersinn von der Vorderseite gesehen.
    /// UVs: waagerechte Flächen → Welt-XZ, senkrechte Flächen → (horizontale Weltachse, Höhe).
    mutating func addQuad(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>, _ d: SIMD3<Float>, uvScale: Float = 0.1) {
        var n = simd_cross(b - a, c - a)
        if simd_length_squared(n) < 1e-12 { n = simd_cross(c - a, d - a) }
        if simd_length_squared(n) < 1e-12 { return }
        n = simd_normalize(n)
        let t0 = MeshBuilder.planarUV(a, normal: n, scale: uvScale)
        let t1 = MeshBuilder.planarUV(b, normal: n, scale: uvScale)
        let t2 = MeshBuilder.planarUV(c, normal: n, scale: uvScale)
        let t3 = MeshBuilder.planarUV(d, normal: n, scale: uvScale)
        pushQuad(a, b, c, d, normal: n, t0, t1, t2, t3)
    }

    /// Dreieck a→b→c gegen den Uhrzeigersinn von der Vorderseite gesehen.
    mutating func addTriangle(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>, uvScale: Float = 0.1) {
        let raw = simd_cross(b - a, c - a)
        if simd_length_squared(raw) < 1e-12 { return }
        let n = simd_normalize(raw)
        let base = UInt32(positions.count)
        let ta = MeshBuilder.planarUV(a, normal: n, scale: uvScale)
        let tb = MeshBuilder.planarUV(b, normal: n, scale: uvScale)
        let tc = MeshBuilder.planarUV(c, normal: n, scale: uvScale)
        pushVertex(a, n, ta)
        pushVertex(b, n, tb)
        pushVertex(c, n, tc)
        indices.append(base)
        indices.append(base + 1)
        indices.append(base + 2)
    }

    /// Senkrechter Zylinder. `center` = Mittelpunkt der GRUNDFLÄCHE, wächst nach +Y um `height`.
    /// Glatte Normalen, Deckel oben (optional unten).
    mutating func addCylinder(center: SIMD3<Float>, radius: Float, height: Float, segments: Int = 12,
                              uvScale: Float = 0.1, capTop: Bool = true, capBottom: Bool = false) {
        guard radius > 0.0001, height > 0.0001 else { return }
        let segs = Swift.max(3, Swift.min(128, segments))
        let circumference = 2 * Float.pi * radius
        var tilesU = circumference * uvScale
        if snapsTilesToFaces && tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
        let vBottom = height * uvScale
        let base = UInt32(positions.count)

        // Mantel: (segs + 1) Spalten (UV-Naht), je 2 Vertices (unten, oben)
        for i in 0...segs {
            let f = Float(i) / Float(segs)
            let ang = f * 2 * Float.pi
            let s = sin(ang)
            let c = cos(ang)
            let n = SIMD3<Float>(s, 0, c)
            let bottom = center + SIMD3<Float>(s * radius, 0, c * radius)
            let top = bottom + SIMD3<Float>(0, height, 0)
            pushVertex(bottom, n, SIMD2<Float>(f * tilesU, vBottom))
            pushVertex(top, n, SIMD2<Float>(f * tilesU, 0))
        }
        for i in 0..<segs {
            let b0 = base + UInt32(i * 2)
            let t0 = b0 + 1
            let b1 = b0 + 2
            let t1 = b0 + 3
            // (b0, b1, t1), (b0, t1, t0) – CCW von außen
            indices.append(b0); indices.append(b1); indices.append(t1)
            indices.append(b0); indices.append(t1); indices.append(t0)
        }

        if capTop {
            let topY = center.y + height
            let up = MeshBuilder.axisY
            let cIndex = UInt32(positions.count)
            let cTop = SIMD3<Float>(center.x, topY, center.z)
            pushVertex(cTop, up, SIMD2<Float>(cTop.x * uvScale, cTop.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, topY, center.z + cos(ang) * radius)
                pushVertex(p, up, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 1 + UInt32(i))
                indices.append(cIndex + 2 + UInt32(i))
            }
        }
        if capBottom {
            let down = SIMD3<Float>(0, -1, 0)
            let cIndex = UInt32(positions.count)
            pushVertex(center, down, SIMD2<Float>(center.x * uvScale, center.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, center.y, center.z + cos(ang) * radius)
                pushVertex(p, down, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 2 + UInt32(i))
                indices.append(cIndex + 1 + UInt32(i))
            }
        }
    }

    /// Kegel (Baumkronen, Turmspitzen). `center` = Mittelpunkt der Grundfläche, Spitze bei center + (0, height, 0).
    mutating func addCone(center: SIMD3<Float>, radius: Float, height: Float, segments: Int = 12,
                          uvScale: Float = 0.1, capBottom: Bool = false) {
        guard radius > 0.0001, height > 0.0001 else { return }
        let segs = Swift.max(3, Swift.min(128, segments))
        let apex = center + SIMD3<Float>(0, height, 0)
        let slant = sqrt(radius * radius + height * height)
        var tilesU = 2 * Float.pi * radius * uvScale
        if snapsTilesToFaces && tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
        let vBottom = slant * uvScale
        for i in 0..<segs {
            let f0 = Float(i) / Float(segs)
            let f1 = Float(i + 1) / Float(segs)
            let a0 = f0 * 2 * Float.pi
            let a1 = f1 * 2 * Float.pi
            let am = (a0 + a1) * 0.5
            let n0 = simd_normalize(SIMD3<Float>(sin(a0) * height, radius, cos(a0) * height))
            let n1 = simd_normalize(SIMD3<Float>(sin(a1) * height, radius, cos(a1) * height))
            let nm = simd_normalize(SIMD3<Float>(sin(am) * height, radius, cos(am) * height))
            let p0 = center + SIMD3<Float>(sin(a0) * radius, 0, cos(a0) * radius)
            let p1 = center + SIMD3<Float>(sin(a1) * radius, 0, cos(a1) * radius)
            let base = UInt32(positions.count)
            pushVertex(p0, n0, SIMD2<Float>(f0 * tilesU, vBottom))
            pushVertex(p1, n1, SIMD2<Float>(f1 * tilesU, vBottom))
            pushVertex(apex, nm, SIMD2<Float>((f0 + f1) * 0.5 * tilesU, 0))
            indices.append(base); indices.append(base + 1); indices.append(base + 2)
        }
        if capBottom {
            let down = SIMD3<Float>(0, -1, 0)
            let cIndex = UInt32(positions.count)
            pushVertex(center, down, SIMD2<Float>(center.x * uvScale, center.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, center.y, center.z + cos(ang) * radius)
                pushVertex(p, down, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 2 + UInt32(i))
                indices.append(cIndex + 1 + UInt32(i))
            }
        }
    }

    /// Hängt einen anderen Builder an (z. B. Chunks zusammenführen).
    mutating func append(_ other: MeshBuilder) {
        if other.isEmpty { return }
        let offset = UInt32(positions.count)
        positions.append(contentsOf: other.positions)
        normals.append(contentsOf: other.normals)
        uvs.append(contentsOf: other.uvs)
        indices.reserveCapacity(indices.count + other.indices.count)
        for i in other.indices { indices.append(i + offset) }
    }

    // MARK: - Build

    func build(material: SCNMaterial) -> SCNGeometry {
        guard !indices.isEmpty, !positions.isEmpty else {
            let empty = SCNGeometry()
            empty.materials = [material]
            return empty
        }
        let vertexSource = SCNGeometrySource(vertices: positions)
        let normalSource = SCNGeometrySource(normals: normals)
        let uvSource = SCNGeometrySource(textureCoordinates: uvs)
        let element: SCNGeometryElement
        if positions.count <= 65_535 {
            let small: [UInt16] = indices.map { UInt16(truncatingIfNeeded: $0) }
            element = SCNGeometryElement(indices: small, primitiveType: .triangles)
        } else {
            element = SCNGeometryElement(indices: indices, primitiveType: .triangles)
        }
        let geometry = SCNGeometry(sources: [vertexSource, normalSource, uvSource], elements: [element])
        geometry.materials = [material]
        return geometry
    }

    /// Bequemlichkeit: fertiger Node mit der Geometrie.
    func buildNode(material: SCNMaterial, name: String? = nil, castsShadow: Bool = true) -> SCNNode {
        let node = SCNNode(geometry: build(material: material))
        node.name = name
        node.castsShadow = castsShadow
        return node
    }

    // MARK: - Internals

    private static let axisX = SIMD3<Float>(1, 0, 0)
    private static let axisNegX = SIMD3<Float>(-1, 0, 0)
    private static let axisY = SIMD3<Float>(0, 1, 0)
    private static let axisZ = SIMD3<Float>(0, 0, 1)
    private static let axisNegZ = SIMD3<Float>(0, 0, -1)

    private mutating func pushVertex(_ p: SIMD3<Float>, _ n: SIMD3<Float>, _ uv: SIMD2<Float>) {
        positions.append(SCNVector3(x: p.x, y: p.y, z: p.z))
        normals.append(SCNVector3(x: n.x, y: n.y, z: n.z))
        uvs.append(CGPoint(x: CGFloat(uv.x), y: CGFloat(uv.y)))
    }

    /// p0..p3 gegen den Uhrzeigersinn von vorne gesehen.
    private mutating func pushQuad(_ p0: SIMD3<Float>, _ p1: SIMD3<Float>, _ p2: SIMD3<Float>, _ p3: SIMD3<Float>,
                                   normal n: SIMD3<Float>,
                                   _ t0: SIMD2<Float>, _ t1: SIMD2<Float>, _ t2: SIMD2<Float>, _ t3: SIMD2<Float>) {
        let base = UInt32(positions.count)
        pushVertex(p0, n, t0)
        pushVertex(p1, n, t1)
        pushVertex(p2, n, t2)
        pushVertex(p3, n, t3)
        indices.append(base); indices.append(base + 1); indices.append(base + 2)
        indices.append(base); indices.append(base + 2); indices.append(base + 3)
    }

    /// Rechteck: origin = unten links (von außen gesehen), right/up = Einheitsachsen,
    /// Außennormale = cross(right, up).
    private mutating func pushFace(origin o: SIMD3<Float>, right r: SIMD3<Float>, up u: SIMD3<Float>,
                                   width w: Float, height h: Float, uvScale s: Float,
                                   horizontal: Bool, salt: UInt64) {
        guard w > 0.0001, h > 0.0001 else { return }
        let n = simd_normalize(simd_cross(r, u))
        let p0 = o
        let p1 = o + r * w
        let p2 = o + r * w + u * h
        let p3 = o + u * h
        if horizontal {
            pushQuad(p0, p1, p2, p3, normal: n,
                     SIMD2<Float>(p0.x * s, p0.z * s), SIMD2<Float>(p1.x * s, p1.z * s),
                     SIMD2<Float>(p2.x * s, p2.z * s), SIMD2<Float>(p3.x * s, p3.z * s))
            return
        }
        var tilesU = w * s
        var tilesV = h * s
        if snapsTilesToFaces {
            if tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
            if tilesV >= 0.75 { tilesV = Swift.max(1, tilesV.rounded()) }
        }
        var offU: Float = 0
        var offV: Float = 0
        if variesFaceOffsets {
            let hsh = MeshBuilder.hashPoint(o, salt: salt)
            offU = Float(hsh & 3) * 0.25
            offV = Float((hsh >> 2) & 3) * 0.25
        }
        // v = 0 oben im Bild → unten an der Fläche liegt v = tilesV (ganze Kachel-Grenze)
        pushQuad(p0, p1, p2, p3, normal: n,
                 SIMD2<Float>(offU, offV + tilesV),
                 SIMD2<Float>(offU + tilesU, offV + tilesV),
                 SIMD2<Float>(offU + tilesU, offV),
                 SIMD2<Float>(offU, offV))
    }

    private static func planarUV(_ p: SIMD3<Float>, normal n: SIMD3<Float>, scale s: Float) -> SIMD2<Float> {
        if abs(n.y) > 0.7 {
            return SIMD2<Float>(p.x * s, p.z * s)
        }
        let rightRaw = simd_cross(axisY, n)
        let len = simd_length(rightRaw)
        let right = len > 1e-5 ? rightRaw / len : axisX
        return SIMD2<Float>(simd_dot(p, right) * s, -p.y * s)
    }

    /// Deterministischer Hash einer Position (ohne Überlauf-Traps).
    private static func hashPoint(_ p: SIMD3<Float>, salt: UInt64) -> UInt64 {
        var h: UInt64 = 0xcbf2_9ce4_8422_2325 ^ salt
        let parts: [UInt32] = [p.x.bitPattern, p.y.bitPattern, p.z.bitPattern]
        for part in parts {
            h ^= UInt64(part)
            h = h &* 0x0000_0100_0000_01b3
            h ^= h >> 29
        }
        // splitmix64 finalizer
        h = (h ^ (h >> 30)) &* 0xbf58_476d_1ce4_e5b9
        h = (h ^ (h >> 27)) &* 0x94d0_49bb_1331_11eb
        h = h ^ (h >> 31)
        return h
    }
}

// =====================================================================
// MARK: - Graphics/Render.swift
// =====================================================================

// =====================================================================
//  Render – Grundlage der Darstellung:
//  SCNView-Konfiguration (native Auflösung, MSAA, FPS), Kamera-Look
//  (HDR, Bloom, SSAO, Motion Blur, Filmlook), PBR-Materialien,
//  prozeduraler Himmel (Cube-Map) + IBL + Nebel, Lichter.
// =====================================================================

enum CameraStyle {
    case gameplay
    case kombat
    case cinematic
}

enum Render {

    // MARK: - View

    /// Native Auflösung (Ultra/Ausgewogen = volle Panel-Auflösung), MSAA, Bildrate, schwarzer Hintergrund.
    static func configure(view: SCNView, quality: QualityPreset) {
        let native = UIScreen.main.nativeScale
        switch quality {
        case .ultra, .balanced:
            view.contentScaleFactor = native
            view.antialiasingMode = .multisampling4X
        case .performance:
            // 120-FPS-Modus: auf 3x-Displays leicht reduziert, sonst nativ
            view.contentScaleFactor = Swift.min(native, 2.0)
            view.antialiasingMode = .multisampling2X
        }
        let maxFPS = Swift.max(30, UIScreen.main.maximumFramesPerSecond)
        view.preferredFramesPerSecond = quality == .performance ? maxFPS : Swift.min(60, maxFPS)
        view.rendersContinuously = true
        view.isJitteringEnabled = false
        view.backgroundColor = .black
        view.allowsCameraControl = false
        view.autoenablesDefaultLighting = false
        view.showsStatistics = false
        view.isPlaying = true
    }

    // MARK: - Kamera

    /// HDR, Bloom, SSAO, Motion Blur und Farbgebung (leicht entsättigtes Teal/Orange, Vignette).
    /// fieldOfView wird NICHT verändert (setzt der jeweilige Controller).
    static func configureCamera(_ camera: SCNCamera, quality: QualityPreset, style: CameraStyle) {
        camera.wantsHDR = true
        camera.automaticallyAdjustsZRange = false

        switch style {
        case .gameplay:
            camera.zNear = 0.1          // etwas größer als 0.05 → weniger Z-Fighting bei 2,5 km Sichtweite
            camera.zFar = 2500
        case .kombat:
            camera.zNear = 0.05
            camera.zFar = 1200
        case .cinematic:
            camera.zNear = 0.05
            camera.zFar = 2500
        }

        // Tonemapping / Belichtung
        camera.averageGray = 0.18
        camera.whitePoint = 1.0
        camera.exposureOffset = 0
        switch style {
        case .gameplay:
            camera.wantsExposureAdaptation = true
            camera.minimumExposure = -0.6
            camera.maximumExposure = 1.0
        case .kombat, .cinematic:
            camera.wantsExposureAdaptation = false
            camera.minimumExposure = -2
            camera.maximumExposure = 2
        }

        // Bloom
        let bloomScale: CGFloat = quality == .performance ? 0.7 : 1.0
        let hiRes = quality == .ultra
        switch style {
        case .gameplay:
            camera.bloomIntensity = 0.85 * bloomScale
            camera.bloomThreshold = 0.8
            camera.bloomBlurRadius = hiRes ? 12 : 8
        case .kombat:
            camera.bloomIntensity = 1.0 * bloomScale
            camera.bloomThreshold = 0.75
            camera.bloomBlurRadius = hiRes ? 12 : 9
        case .cinematic:
            camera.bloomIntensity = 1.35 * bloomScale
            camera.bloomThreshold = 0.65
            camera.bloomBlurRadius = hiRes ? 16 : 10
        }

        // SSAO (Radius in Metern: Stadt grob, Kampf fein)
        switch quality {
        case .ultra:
            camera.screenSpaceAmbientOcclusionIntensity = style == .gameplay ? 0.9 : 1.2
            camera.screenSpaceAmbientOcclusionRadius = style == .gameplay ? 1.2 : 0.45
        case .balanced:
            camera.screenSpaceAmbientOcclusionIntensity = style == .gameplay ? 0.7 : 0.9
            camera.screenSpaceAmbientOcclusionRadius = style == .gameplay ? 1.0 : 0.4
        case .performance:
            camera.screenSpaceAmbientOcclusionIntensity = 0
        }

        // Motion Blur (klein im Spiel, kaum im Kampf → Treffer bleiben knackig)
        switch (style, quality) {
        case (.gameplay, .ultra): camera.motionBlurIntensity = 0.18
        case (.gameplay, .balanced): camera.motionBlurIntensity = 0.12
        case (.kombat, .ultra): camera.motionBlurIntensity = 0.05
        case (.cinematic, .ultra): camera.motionBlurIntensity = 0.3
        case (.cinematic, .balanced): camera.motionBlurIntensity = 0.2
        default: camera.motionBlurIntensity = 0
        }

        // Filmischer Look
        switch style {
        case .gameplay:
            camera.saturation = 1.05
            camera.contrast = 0.1
            camera.vignettingPower = 0.45
            camera.vignettingIntensity = 0.9
            camera.colorFringeStrength = 0
        case .kombat:
            camera.saturation = 1.08
            camera.contrast = 0.14
            camera.vignettingPower = 0.6
            camera.vignettingIntensity = 1.0
            camera.colorFringeStrength = quality == .performance ? 0 : 0.2
        case .cinematic:
            camera.saturation = 0.98
            camera.contrast = 0.18
            camera.vignettingPower = 0.95
            camera.vignettingIntensity = 1.0
            camera.colorFringeStrength = quality == .performance ? 0 : 0.45
        }

        // Tiefenschärfe nur Ultra + Kino (focusDistance setzt die Cutscene)
        if style == .cinematic && quality == .ultra {
            camera.wantsDepthOfField = true
            camera.fStop = 1.8
            camera.focusDistance = 4
        } else {
            camera.wantsDepthOfField = false
        }
    }

    // MARK: - Materialien

    /// Physikalisch basiertes Material mit Einzelwerten.
    static func pbr(_ color: UIColor, roughness: Float, metalness: Float,
                    emission: UIColor? = nil, emissionIntensity: Float = 1) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = color
        m.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, roughness)))
        m.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metalness)))
        if let e = emission {
            m.emission.contents = e
            m.emission.intensity = CGFloat(emissionIntensity)
        } else {
            m.emission.contents = UIColor.black
        }
        m.isLitPerPixel = true
        return m
    }

    /// Texturiertes PBR-Material. tileScale wiederholt alle Texturen (contentsTransform).
    /// Emission (z. B. Fenster-Leuchtkarte) bekommt Intensität 1.5 → leichter Bloom.
    static func texturedPBR(diffuse: UIImage, normal: UIImage? = nil, roughness: Float, metalness: Float,
                            emission: UIImage? = nil, tileScale: Float = 1) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = diffuse
        m.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, roughness)))
        m.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metalness)))
        let transform = SCNMatrix4MakeScale(tileScale, tileScale, 1)
        setupTiling(m.diffuse, transform)
        if let n = normal {
            m.normal.contents = n
            m.normal.intensity = 1.0
            setupTiling(m.normal, transform)
        }
        if let e = emission {
            m.emission.contents = e
            m.emission.intensity = 1.5
            setupTiling(m.emission, transform)
        } else {
            m.emission.contents = UIColor.black
        }
        m.isLitPerPixel = true
        return m
    }

    /// Selbstleuchtendes Material (Neon, Lampen, Bildschirme) – Intensität > 1 erzeugt Bloom.
    static func emissive(_ color: UIColor, intensity: Float = 2) -> SCNMaterial {
        let m = pbr(UIColor(white: 0.02, alpha: 1), roughness: 0.5, metalness: 0,
                    emission: color, emissionIntensity: intensity)
        return m
    }

    private static func setupTiling(_ p: SCNMaterialProperty, _ transform: SCNMatrix4) {
        p.wrapS = .repeat
        p.wrapT = .repeat
        p.contentsTransform = transform
        p.minificationFilter = .linear
        p.magnificationFilter = .linear
        p.mipFilter = .linear
        p.maxAnisotropy = 8
    }

    // MARK: - Lichter

    /// Gerichtetes Mond-/Hauptlicht mit kaskadierten Schatten (Größe nach Qualität).
    /// direction = Richtung, in die das Licht scheint (z. B. (-0.4, -1, -0.3)).
    static func makeKeyLight(direction: SIMD3<Float>, color: UIColor, intensity: Float,
                             quality: QualityPreset, shadowExtent: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .directional
        light.color = color
        light.intensity = CGFloat(intensity)
        light.castsShadow = true
        light.shadowMode = .forward
        light.automaticallyAdjustsShadowProjection = true
        light.maximumShadowDistance = CGFloat(Swift.max(10, shadowExtent))
        light.shadowColor = UIColor(white: 0, alpha: 0.82)
        switch quality {
        case .ultra:
            light.shadowMapSize = CGSize(width: 2048, height: 2048)
            light.shadowCascadeCount = 4
            light.shadowSampleCount = 12
            light.shadowRadius = 1.5
        case .balanced:
            light.shadowMapSize = CGSize(width: 2048, height: 2048)
            light.shadowCascadeCount = 3
            light.shadowSampleCount = 6
            light.shadowRadius = 2.0
        case .performance:
            light.shadowMapSize = CGSize(width: 1024, height: 1024)
            light.shadowCascadeCount = 2
            light.shadowSampleCount = 2
            light.shadowRadius = 2.5
        }

        let node = SCNNode()
        node.name = "keyLight"
        node.light = light
        var dir = direction
        if simd_length_squared(dir) < 1e-8 { dir = SIMD3<Float>(-0.4, -1, -0.3) }
        dir = simd_normalize(dir)
        node.simdOrientation = simd_quatf(from: SIMD3<Float>(0, 0, -1), to: dir)
        node.simdPosition = -dir * 150
        return node
    }

    static func makeAmbient(color: UIColor, intensity: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .ambient
        light.color = color
        light.intensity = CGFloat(intensity)
        let node = SCNNode()
        node.name = "ambientLight"
        node.light = light
        return node
    }

    /// Punktlicht ohne Schatten, quadratischer Abfall bis `range` Meter.
    static func makePointLight(color: UIColor, intensity: Float, range: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = CGFloat(intensity)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.1, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let node = SCNNode()
        node.name = "pointLight"
        node.light = light
        return node
    }

    /// Spotlicht entlang lokal -Z. angle = äußerer Kegelwinkel in GRAD
    /// (Werte < 3.2 werden als Radiant interpretiert).
    static func makeSpotLight(color: UIColor, intensity: Float, angle: Float, range: Float, castsShadow: Bool) -> SCNNode {
        let light = SCNLight()
        light.type = .spot
        light.color = color
        light.intensity = CGFloat(intensity)
        var deg = angle
        if deg > 0 && deg < 3.2 { deg = deg * 180 / Float.pi }
        deg = Swift.max(1, Swift.min(170, deg))
        light.spotOuterAngle = CGFloat(deg)
        light.spotInnerAngle = CGFloat(deg * 0.55)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.1, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = castsShadow
        if castsShadow {
            light.shadowMode = .forward
            light.shadowMapSize = CGSize(width: 1024, height: 1024)
            light.shadowSampleCount = 8
            light.shadowRadius = 3
            light.shadowColor = UIColor(white: 0, alpha: 0.8)
            light.zNear = 0.1
            light.zFar = CGFloat(Swift.max(1, range))
        }
        let node = SCNNode()
        node.name = "spotLight"
        node.light = light
        return node
    }
}

// MARK: - Umgebung: prozeduraler Himmel (Cube-Map), IBL, Nebel

extension Render {

    private static var skyFaceCache: [String: [UIImage]] = [:]

    /// Richtung ZUM Mond (Himmelsposition) bzw. zur tiefstehenden Abendsonne.
    private static let moonSkyDirection: SIMD3<Float> = simd_normalize(SIMD3<Float>(-0.35, 0.42, -0.84))
    private static let sunSkyDirection: SIMD3<Float> = simd_normalize(SIMD3<Float>(-1.0, 0.035, 0.12))

    /// Himmel (Hintergrund) + Lichtumgebung (IBL) + Nebel.
    /// Der Nebel sollte zur Horizontfarbe passen (Hintergrund wird von SceneKit nicht vernebelt) –
    /// ohne fogColor wird eine passende Farbe gewählt.
    static func applyEnvironment(to scene: SCNScene, timeOfDay: TimeOfDay, quality: QualityPreset,
                                 fogStart: Float, fogEnd: Float, fogColor: UIColor? = nil) {
        let bgSize: Int
        let iblSize: Int
        switch quality {
        case .ultra:
            bgSize = 1024
            iblSize = 128
        case .balanced:
            bgSize = 768
            iblSize = 64
        case .performance:
            bgSize = 512
            iblSize = 64
        }
        let background = skyFaces(timeOfDay: timeOfDay, size: bgSize)
        let lighting = skyLightingFaces(timeOfDay: timeOfDay, size: iblSize)
        if background.count == 6 {
            scene.background.contents = background
        } else {
            scene.background.contents = defaultFogColor(timeOfDay)
        }
        scene.background.intensity = 1
        if lighting.count == 6 {
            scene.lightingEnvironment.contents = lighting
        }
        scene.lightingEnvironment.intensity = CGFloat(lightingIntensity(timeOfDay))

        let start = Swift.max(0, fogStart)
        let end = Swift.max(start + 1, fogEnd)
        scene.fogStartDistance = CGFloat(start)
        scene.fogEndDistance = CGFloat(end)
        scene.fogColor = fogColor ?? defaultFogColor(timeOfDay)
        scene.fogDensityExponent = 1.25
    }

    /// Nebelfarbe passend zum Horizont der Tageszeit.
    static func defaultFogColor(_ timeOfDay: TimeOfDay) -> UIColor {
        switch timeOfDay {
        case .night: return UIColor(red: 0.105, green: 0.085, blue: 0.11, alpha: 1)
        case .dusk: return UIColor(red: 0.50, green: 0.30, blue: 0.30, alpha: 1)
        case .stormNight: return UIColor(red: 0.085, green: 0.10, blue: 0.095, alpha: 1)
        }
    }

    /// Farbe des Himmels knapp über dem Horizont (für Silhouetten, Glows, Nebel).
    static func skyHorizonColor(_ timeOfDay: TimeOfDay) -> UIColor {
        let c = sampleSky(skyStops(timeOfDay), 0.02)
        return UIColor(red: CGFloat(c.x), green: CGFloat(c.y), blue: CGFloat(c.z), alpha: 1)
    }

    /// Richtung, in die das Haupt-/Mondlicht passend zum Himmel scheint (für makeKeyLight).
    static func skyLightDirection(_ timeOfDay: TimeOfDay) -> SIMD3<Float> {
        switch timeOfDay {
        case .night:
            return -moonSkyDirection
        case .dusk:
            return simd_normalize(SIMD3<Float>(1.0, -0.38, -0.12))
        case .stormNight:
            return simd_normalize(SIMD3<Float>(0.25, -1.0, 0.35))
        }
    }

    private static func lightingIntensity(_ timeOfDay: TimeOfDay) -> Float {
        switch timeOfDay {
        case .night: return 1.0
        case .dusk: return 1.2
        case .stormNight: return 0.75
        }
    }

    // MARK: Himmelsfarben (Höhe über Horizont → Farbe, sRGB)

    private static func skyStops(_ timeOfDay: TimeOfDay) -> [(Float, SIMD3<Float>)] {
        switch timeOfDay {
        case .night:
            return [
                (-1.0, SIMD3<Float>(0.010, 0.012, 0.018)),
                (-0.15, SIMD3<Float>(0.030, 0.030, 0.042)),
                (-0.02, SIMD3<Float>(0.110, 0.085, 0.095)),
                (0.0, SIMD3<Float>(0.260, 0.170, 0.150)),
                (0.04, SIMD3<Float>(0.180, 0.130, 0.160)),
                (0.12, SIMD3<Float>(0.075, 0.075, 0.130)),
                (0.35, SIMD3<Float>(0.028, 0.038, 0.080)),
                (1.0, SIMD3<Float>(0.008, 0.012, 0.035))
            ]
        case .dusk:
            return [
                (-1.0, SIMD3<Float>(0.030, 0.025, 0.035)),
                (-0.15, SIMD3<Float>(0.100, 0.060, 0.080)),
                (-0.02, SIMD3<Float>(0.450, 0.220, 0.160)),
                (0.0, SIMD3<Float>(0.980, 0.520, 0.220)),
                (0.05, SIMD3<Float>(0.950, 0.450, 0.280)),
                (0.15, SIMD3<Float>(0.620, 0.300, 0.420)),
                (0.35, SIMD3<Float>(0.300, 0.180, 0.420)),
                (0.65, SIMD3<Float>(0.130, 0.100, 0.300)),
                (1.0, SIMD3<Float>(0.060, 0.060, 0.180))
            ]
        case .stormNight:
            return [
                (-1.0, SIMD3<Float>(0.015, 0.018, 0.018)),
                (-0.10, SIMD3<Float>(0.040, 0.045, 0.045)),
                (0.0, SIMD3<Float>(0.150, 0.155, 0.130)),
                (0.06, SIMD3<Float>(0.110, 0.125, 0.115)),
                (0.25, SIMD3<Float>(0.060, 0.075, 0.070)),
                (1.0, SIMD3<Float>(0.030, 0.040, 0.040))
            ]
        }
    }

    private static func sampleSky(_ stops: [(Float, SIMD3<Float>)], _ e: Float) -> SIMD3<Float> {
        guard let first = stops.first, let last = stops.last else { return SIMD3<Float>(0, 0, 0) }
        if e <= first.0 { return first.1 }
        if e >= last.0 { return last.1 }
        for i in 1..<stops.count {
            let a = stops[i - 1]
            let b = stops[i]
            if e <= b.0 {
                let span = b.0 - a.0
                let f = span > 1e-6 ? (e - a.0) / span : 0
                let sm = f * f * (3 - 2 * f)
                return a.1 + (b.1 - a.1) * sm
            }
        }
        return last.1
    }

    private static func skySmooth(_ a: Float, _ b: Float, _ x: Float) -> Float {
        let t = Swift.max(0, Swift.min(1, (x - a) / (b - a)))
        return t * t * (3 - 2 * t)
    }

    private static func skyByte(_ v: Float) -> UInt8 {
        let x = v * 255 + 0.5
        if !(x > 0) { return 0 }
        if x >= 255 { return 255 }
        return UInt8(x)
    }

    // MARK: Cube-Map-Geometrie (Reihenfolge +X, -X, +Y, -Y, +Z, -Z; s nach rechts, t nach unten, je -1...1)

    private static func skyDirection(face: Int, s: Float, t: Float) -> SIMD3<Float> {
        switch face {
        case 0: return SIMD3<Float>(1, -t, -s)
        case 1: return SIMD3<Float>(-1, -t, s)
        case 2: return SIMD3<Float>(s, 1, t)
        case 3: return SIMD3<Float>(s, -1, -t)
        case 4: return SIMD3<Float>(s, -t, 1)
        default: return SIMD3<Float>(-s, -t, -1)
        }
    }

    /// Projiziert eine Richtung auf eine Würfelfläche → (0...1, 0...1) Bildkoordinaten, nil wenn nicht auf dieser Fläche.
    private static func skyProject(_ d: SIMD3<Float>, face: Int) -> SIMD2<Float>? {
        let ax = abs(d.x)
        let ay = abs(d.y)
        let az = abs(d.z)
        var s: Float = 0
        var t: Float = 0
        switch face {
        case 0:
            guard d.x > 0, ax >= ay, ax >= az else { return nil }
            s = -d.z / ax
            t = -d.y / ax
        case 1:
            guard d.x < 0, ax >= ay, ax >= az else { return nil }
            s = d.z / ax
            t = -d.y / ax
        case 2:
            guard d.y > 0, ay >= ax, ay >= az else { return nil }
            s = d.x / ay
            t = d.z / ay
        case 3:
            guard d.y < 0, ay >= ax, ay >= az else { return nil }
            s = d.x / ay
            t = -d.z / ay
        case 4:
            guard d.z > 0, az >= ax, az >= ay else { return nil }
            s = d.x / az
            t = -d.y / az
        default:
            guard d.z < 0, az >= ax, az >= ay else { return nil }
            s = -d.x / az
            t = -d.y / az
        }
        return SIMD2<Float>((s + 1) * 0.5, (t + 1) * 0.5)
    }

    /// Glatter Grundverlauf einer Würfelfläche, Pixel für Pixel aus der Blickrichtung berechnet.
    private static func skyBaseFace(face: Int, size: Int, timeOfDay: TimeOfDay, gain: Float) -> CGImage? {
        let n = Swift.max(4, size)
        let stops = Render.skyStops(timeOfDay)
        var bytes = [UInt8](repeating: 255, count: n * n * 4)
        let inv = 2 / Float(n)
        bytes.withUnsafeMutableBufferPointer { buf in
            for y in 0..<n {
                let t = (Float(y) + 0.5) * inv - 1
                for x in 0..<n {
                    let s = (Float(x) + 0.5) * inv - 1
                    let d = simd_normalize(Render.skyDirection(face: face, s: s, t: t))
                    let c = Render.sampleSky(stops, d.y) * gain
                    let i = (y * n + x) * 4
                    buf[i] = Render.skyByte(c.x)
                    buf[i + 1] = Render.skyByte(c.y)
                    buf[i + 2] = Render.skyByte(c.z)
                    buf[i + 3] = 255
                }
            }
        }
        return ProceduralTextures.makeCGImage(rgba: bytes, width: n, height: n)
    }

    /// 6 Hintergrund-Flächen (gecacht): Verlauf + Wolken + Sterne + Mond/Sonne + Dithering gegen Banding.
    static func skyFaces(timeOfDay: TimeOfDay, size: Int) -> [UIImage] {
        let px = Swift.max(64, Swift.min(2048, size))
        let key = "bg-\(timeOfDay.rawValue)-\(px)"
        if let cached = skyFaceCache[key] { return cached }
        let dither = ProceduralTextures.ditherOverlay()
        var faces: [UIImage] = []
        for face in 0..<6 {
            let base = skyBaseFace(face: face, size: 128, timeOfDay: timeOfDay, gain: 1)
            let image = ProceduralTextures.renderImage(width: px, height: px, opaque: true) { ctx in
                let rect = CGRect(x: 0, y: 0, width: px, height: px)
                ctx.interpolationQuality = .high
                if let b = base {
                    UIImage(cgImage: b).draw(in: rect)
                } else {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(rect)
                }
                Render.drawSkyDetails(ctx, face: face, size: CGFloat(px), timeOfDay: timeOfDay)
                ctx.interpolationQuality = .none
                dither.draw(in: rect, blendMode: .softLight, alpha: 0.18)
            }
            faces.append(image)
        }
        skyFaceCache[key] = faces
        return faces
    }

    /// 6 kleine, aufgehellte Flächen für die bildbasierte Beleuchtung (inkl. Mond-/Sonnen-Glanzpunkt).
    static func skyLightingFaces(timeOfDay: TimeOfDay, size: Int) -> [UIImage] {
        let px = Swift.max(16, Swift.min(512, size))
        let key = "ibl-\(timeOfDay.rawValue)-\(px)"
        if let cached = skyFaceCache[key] { return cached }
        var faces: [UIImage] = []
        for face in 0..<6 {
            let base = skyBaseFace(face: face, size: px, timeOfDay: timeOfDay, gain: 1.8)
            let image = ProceduralTextures.renderImage(width: px, height: px, opaque: true) { ctx in
                let rect = CGRect(x: 0, y: 0, width: px, height: px)
                let sz = CGFloat(px)
                if let b = base {
                    UIImage(cgImage: b).draw(in: rect)
                } else {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(rect)
                }
                switch timeOfDay {
                case .night:
                    if let uv = Render.skyProject(Render.moonSkyDirection, face: face) {
                        let p = CGPoint(x: CGFloat(uv.x) * sz, y: CGFloat(uv.y) * sz)
                        ProceduralTextures.drawRadial(ctx, center: p, radius: sz * 0.12,
                                                      colors: [UIColor(white: 1, alpha: 0.95),
                                                               UIColor(red: 0.7, green: 0.8, blue: 1, alpha: 0.25),
                                                               UIColor(red: 0.6, green: 0.7, blue: 1, alpha: 0)],
                                                      locations: [0, 0.3, 1])
                    }
                case .dusk:
                    if let uv = Render.skyProject(Render.sunSkyDirection, face: face) {
                        let p = CGPoint(x: CGFloat(uv.x) * sz, y: CGFloat(uv.y) * sz)
                        ProceduralTextures.drawRadial(ctx, center: p, radius: sz * 0.3,
                                                      colors: [UIColor(red: 1, green: 0.85, blue: 0.6, alpha: 1),
                                                               UIColor(red: 1, green: 0.55, blue: 0.25, alpha: 0.45),
                                                               UIColor(red: 1, green: 0.45, blue: 0.2, alpha: 0)],
                                                      locations: [0, 0.25, 1])
                    }
                case .stormNight:
                    break
                }
            }
            faces.append(image)
        }
        skyFaceCache[key] = faces
        return faces
    }

    // MARK: Himmelsdetails

    private static func drawSkyDetails(_ ctx: CGContext, face: Int, size: CGFloat, timeOfDay: TimeOfDay) {
        switch timeOfDay {
        case .night:
            drawSkyClouds(ctx, face: face, size: size, seed: 0xC10D,
                          dark: UIColor(red: 0.025, green: 0.035, blue: 0.065, alpha: 1),
                          light: UIColor(red: 0.17, green: 0.14, blue: 0.20, alpha: 1),
                          count: 5, alpha: 0.32)
            drawSkyStars(ctx, face: face, size: size, density: 1.0, seed: 0x57A8)
            if let uv = skyProject(moonSkyDirection, face: face) {
                drawMoon(ctx, at: CGPoint(x: CGFloat(uv.x) * size, y: CGFloat(uv.y) * size), size: size)
            }
        case .dusk:
            drawSkyStars(ctx, face: face, size: size, density: 0.15, seed: 0x57A9)
            drawSkyClouds(ctx, face: face, size: size, seed: 0xD05C,
                          dark: UIColor(red: 0.26, green: 0.12, blue: 0.22, alpha: 1),
                          light: UIColor(red: 0.95, green: 0.50, blue: 0.40, alpha: 1),
                          count: 6, alpha: 0.38)
            if let uv = skyProject(sunSkyDirection, face: face) {
                drawSun(ctx, at: CGPoint(x: CGFloat(uv.x) * size, y: CGFloat(uv.y) * size), size: size)
            }
        case .stormNight:
            drawSkyClouds(ctx, face: face, size: size, seed: 0x5707,
                          dark: UIColor(red: 0.012, green: 0.018, blue: 0.018, alpha: 1),
                          light: UIColor(red: 0.20, green: 0.24, blue: 0.22, alpha: 1),
                          count: 10, alpha: 0.6)
            // von Blitzen angeleuchtete Wolkenränder
            drawSkyClouds(ctx, face: face, size: size, seed: 0xB117,
                          dark: UIColor(red: 0.45, green: 0.55, blue: 0.62, alpha: 1),
                          light: UIColor(red: 0.62, green: 0.72, blue: 0.78, alpha: 1),
                          count: 2, alpha: 0.16)
        }
    }

    /// Weiche Wolkenballen – bleiben vollständig innerhalb der Fläche (keine sichtbaren Nähte).
    private static func drawSkyClouds(_ ctx: CGContext, face: Int, size: CGFloat, seed: UInt64,
                                      dark: UIColor, light: UIColor, count: Int, alpha: CGFloat) {
        if face == 3 || count <= 0 { return }
        var rng = ProceduralTextures.Rand(seed: seed &+ UInt64(face) &* 0x9E37_79B9)
        let isTop = face == 2
        for _ in 0..<count {
            let cx = rng.range(0.25, 0.75) * size
            let cy = isTop ? rng.range(0.25, 0.75) * size : rng.range(0.2, 0.44) * size
            let stretch: CGFloat = isTop ? rng.range(1.0, 1.8) : rng.range(1.8, 3.2)
            var r = rng.range(0.06, 0.17) * size
            let maxRX = Swift.min(cx, size - cx) * 0.92
            let maxRY = isTop ? Swift.min(cy, size - cy) * 0.92 : Swift.min(cy, size * 0.53 - cy) * 0.92
            r = Swift.min(r, maxRX / stretch, maxRY)
            if r < 2 { continue }
            let col = rng.chance(0.65) ? dark : light
            let a = alpha * rng.range(0.6, 1.0)
            ctx.saveGState()
            ctx.translateBy(x: cx, y: cy)
            ctx.scaleBy(x: stretch, y: 1)
            ProceduralTextures.drawRadial(ctx, center: CGPoint.zero, radius: r,
                                          colors: [col.withAlphaComponent(a),
                                                   col.withAlphaComponent(a * 0.55),
                                                   col.withAlphaComponent(0)],
                                          locations: [0, 0.5, 1])
            ctx.restoreGState()
        }
    }

    private static func drawSkyStars(_ ctx: CGContext, face: Int, size: CGFloat, density: CGFloat, seed: UInt64) {
        if face == 3 { return }
        var rng = ProceduralTextures.Rand(seed: seed &+ UInt64(face) &* 7919)
        let scale = size / 1024
        let count = Int(950 * density * scale * scale)
        if count <= 0 { return }
        let tints: [UIColor] = [
            UIColor.white,
            UIColor(red: 0.80, green: 0.88, blue: 1.00, alpha: 1),
            UIColor(red: 1.00, green: 0.90, blue: 0.78, alpha: 1),
            UIColor(red: 0.90, green: 0.93, blue: 1.00, alpha: 1)
        ]
        let sizeFactor = Swift.max(0.6, scale)
        for _ in 0..<count {
            let ux = rng.unit()
            let uy = rng.unit()
            let d = simd_normalize(skyDirection(face: face, s: Float(ux) * 2 - 1, t: Float(uy) * 2 - 1))
            if d.y < 0.03 { continue }
            let fade = CGFloat(skySmooth(0.03, 0.3, d.y))
            let u3 = rng.unit()
            let mag = u3 * u3 * u3
            let r = (0.45 + mag * 1.5) * sizeFactor
            let a = (0.2 + 0.8 * mag) * fade
            let tint = tints[rng.int(tints.count)]
            let p = CGPoint(x: ux * size, y: uy * size)
            if mag > 0.8 {
                ProceduralTextures.drawRadial(ctx, center: p, radius: r * 5,
                                              colors: [tint.withAlphaComponent(0.25 * a), tint.withAlphaComponent(0)],
                                              locations: [0, 1])
            }
            ctx.setFillColor(tint.withAlphaComponent(a).cgColor)
            ctx.fillEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2))
        }
    }

    private static func drawMoon(_ ctx: CGContext, at p: CGPoint, size: CGFloat) {
        let r = size * 0.028
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 7,
                                      colors: [UIColor(red: 0.70, green: 0.78, blue: 1.0, alpha: 0.22),
                                               UIColor(red: 0.55, green: 0.65, blue: 0.95, alpha: 0.07),
                                               UIColor(red: 0.50, green: 0.60, blue: 0.90, alpha: 0)],
                                      locations: [0, 0.35, 1])
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 2,
                                      colors: [UIColor(white: 1, alpha: 0.4), UIColor(white: 1, alpha: 0)],
                                      locations: [0, 1])
        let disc = CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2)
        ctx.saveGState()
        ctx.addEllipse(in: disc)
        ctx.clip()
        ProceduralTextures.drawRadial(ctx, center: CGPoint(x: p.x - r * 0.3, y: p.y - r * 0.3), radius: r * 1.6,
                                      colors: [UIColor(red: 1.0, green: 0.98, blue: 0.93, alpha: 1),
                                               UIColor(red: 0.86, green: 0.86, blue: 0.84, alpha: 1),
                                               UIColor(red: 0.70, green: 0.72, blue: 0.74, alpha: 1)],
                                      locations: [0, 0.55, 1], extend: true)
        var rng = ProceduralTextures.Rand(seed: 0x300D)
        for _ in 0..<14 {
            let mr = r * rng.range(0.08, 0.32)
            let mx = p.x + rng.range(-0.75, 0.75) * r
            let my = p.y + rng.range(-0.75, 0.75) * r
            ctx.setFillColor(UIColor(red: 0.52, green: 0.53, blue: 0.58, alpha: rng.range(0.12, 0.3)).cgColor)
            ctx.fillEllipse(in: CGRect(x: mx - mr, y: my - mr, width: mr * 2, height: mr * 2))
        }
        ctx.restoreGState()
    }

    private static func drawSun(_ ctx: CGContext, at p: CGPoint, size: CGFloat) {
        let r = size * 0.024
        ProceduralTextures.drawRadial(ctx, center: p, radius: size * 0.36,
                                      colors: [UIColor(red: 1.0, green: 0.62, blue: 0.28, alpha: 0.55),
                                               UIColor(red: 1.0, green: 0.48, blue: 0.22, alpha: 0.2),
                                               UIColor(red: 0.9, green: 0.35, blue: 0.25, alpha: 0)],
                                      locations: [0, 0.3, 1])
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 3.5,
                                      colors: [UIColor(red: 1.0, green: 0.85, blue: 0.6, alpha: 0.85),
                                               UIColor(red: 1.0, green: 0.7, blue: 0.4, alpha: 0)],
                                      locations: [0, 1])
        ctx.setFillColor(UIColor(red: 1.0, green: 0.93, blue: 0.78, alpha: 1).cgColor)
        ctx.fillEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2))
    }
}

// =====================================================================
// MARK: - Graphics/Textures.swift
// =====================================================================

// =====================================================================
//  ProceduralTextures – alle Texturen werden im Code erzeugt
//  (UIGraphicsImageRenderer / CoreGraphics), einmalig berechnet und gecacht.
//  Alle Kacheltexturen sind nahtlos (wrapS/wrapT = .repeat).
//
//  Maßstab (für MeshBuilder-uvScale):
//  - facade(): 4 Fensterachsen x 4 Stockwerke pro Kachel → uvScale 0.1 = 2,5 m pro Stockwerk
//  - brick(): 8 Ziegel x 24 Reihen pro Kachel (≈ 1,8 m) → uvScale ≈ 0.55
//  - concrete()/metalPanels(): 4 x 4 Platten pro Kachel → uvScale 0.1–0.25
//  - tiles(): 8 x 8 Fliesen pro Kachel → uvScale ≈ 0.6
//  - asphalt()/asphaltNormal(): ≈ 4 m Kachel → uvScale ≈ 0.25
// =====================================================================

enum ProceduralTextures {

    // MARK: - Cache

    private static var cache: [String: UIImage] = [:]

    private static func cached(_ key: String, _ make: () -> UIImage) -> UIImage {
        if let img = cache[key] { return img }
        let img = make()
        cache[key] = img
        return img
    }

    /// Gibt den Speicher aller erzeugten Texturen frei (z. B. bei Speicherwarnung).
    static func clearCache() {
        cache.removeAll()
    }

    // MARK: - Zufall (deterministisch, splitmix64)

    struct Rand {
        private var state: UInt64

        init(seed: UInt64) {
            state = seed &+ 0x9E37_79B9_7F4A_7C15
        }

        mutating func next() -> UInt64 {
            state = state &+ 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            return z ^ (z >> 31)
        }

        /// 0 ..< 1
        mutating func unit() -> CGFloat {
            return CGFloat(next() >> 11) / 9_007_199_254_740_992.0
        }

        mutating func unitF() -> Float {
            return Float(next() >> 40) / 16_777_216.0
        }

        mutating func range(_ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            return lo + (hi - lo) * unit()
        }

        /// 0 ..< n
        mutating func int(_ n: Int) -> Int {
            if n <= 1 { return 0 }
            return Int(next() % UInt64(n))
        }

        mutating func chance(_ p: CGFloat) -> Bool {
            return unit() < p
        }

        mutating func byte() -> UInt8 {
            return UInt8(truncatingIfNeeded: next() >> 56)
        }
    }

    /// Einfache RGB-Farbe für Rechnungen.
    struct TexRGB {
        var r: CGFloat
        var g: CGFloat
        var b: CGFloat

        init(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) {
            self.r = r
            self.g = g
            self.b = b
        }

        func color(_ k: CGFloat = 1, alpha: CGFloat = 1) -> UIColor {
            return UIColor(red: Swift.min(1, Swift.max(0, r * k)),
                           green: Swift.min(1, Swift.max(0, g * k)),
                           blue: Swift.min(1, Swift.max(0, b * k)),
                           alpha: alpha)
        }

        func mixed(_ o: TexRGB, _ t: CGFloat) -> TexRGB {
            return TexRGB(r + (o.r - r) * t, g + (o.g - g) * t, b + (o.b - b) * t)
        }
    }

    // MARK: - Zeichen-Helfer

    /// Bild mit Maßstab 1 (Pixel = Punkte), Standard-Farbraum.
    static func renderImage(width: Int, height: Int, opaque: Bool, _ draw: (CGContext) -> Void) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = opaque
        format.preferredRange = .standard
        let size = CGSize(width: Swift.max(1, width), height: Swift.max(1, height))
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { rc in
            draw(rc.cgContext)
        }
    }

    /// RGBA-Bytes (8 Bit, Zeile 0 = oben) → CGImage.
    static func makeCGImage(rgba: [UInt8], width: Int, height: Int, hasAlpha: Bool = false) -> CGImage? {
        guard width > 0, height > 0, rgba.count >= width * height * 4 else { return nil }
        let cfData = Data(rgba) as CFData
        guard let provider = CGDataProvider(data: cfData) else { return nil }
        let alphaInfo: CGImageAlphaInfo = hasAlpha ? .premultipliedLast : .noneSkipLast
        return CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                       bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                       bitmapInfo: CGBitmapInfo(rawValue: alphaInfo.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }

    /// Radialer Verlauf. extend = true füllt auch außerhalb des Radius mit der letzten Farbe.
    static func drawRadial(_ ctx: CGContext, center: CGPoint, radius: CGFloat,
                           colors: [UIColor], locations: [CGFloat], extend: Bool = false) {
        guard radius > 0, colors.count >= 2, colors.count == locations.count else { return }
        let cgColors = colors.map { $0.cgColor } as CFArray
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: locations) else { return }
        let options: CGGradientDrawingOptions = extend ? [.drawsAfterEndLocation] : []
        ctx.drawRadialGradient(gradient, startCenter: center, startRadius: 0,
                               endCenter: center, endRadius: radius, options: options)
    }

    /// Linearer Verlauf (füllt die gesamte Clip-Fläche).
    static func drawLinear(_ ctx: CGContext, from: CGPoint, to: CGPoint, colors: [UIColor], locations: [CGFloat]) {
        guard colors.count >= 2, colors.count == locations.count else { return }
        let cgColors = colors.map { $0.cgColor } as CFArray
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: locations) else { return }
        ctx.drawLinearGradient(gradient, start: from, end: to,
                               options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    }

    /// Ruft body für alle 9 Kachel-Versätze auf (nahtlose Features über die Bildkante).
    static func forEachWrap(_ size: CGFloat, _ body: (CGFloat, CGFloat) -> Void) {
        for oy in -1...1 {
            for ox in -1...1 {
                body(CGFloat(ox) * size, CGFloat(oy) * size)
            }
        }
    }

    /// Kachelbares Zufallsraster (cells x cells) mit 2 Pixel Wiederholungsrand für nahtloses Hochskalieren.
    static func randomGridImage(cells: Int, rng: inout Rand) -> UIImage? {
        let c = Swift.max(1, Swift.min(512, cells))
        let n = c + 4
        var values = [UInt8](repeating: 0, count: c * c)
        for i in 0..<(c * c) { values[i] = rng.byte() }
        var rgba = [UInt8](repeating: 255, count: n * n * 4)
        for y in 0..<n {
            let sy = ((y - 2) % c + c) % c
            for x in 0..<n {
                let sx = ((x - 2) % c + c) % c
                let v = values[sy * c + sx]
                let i = (y * n + x) * 4
                rgba[i] = v
                rgba[i + 1] = v
                rgba[i + 2] = v
            }
        }
        guard let cg = makeCGImage(rgba: rgba, width: n, height: n) else { return nil }
        return UIImage(cgImage: cg)
    }

    /// Eine Rausch-Oktave nahtlos über die ganze Fläche (weich interpoliert).
    static func drawNoiseOctave(_ ctx: CGContext, size: CGFloat, cells: Int, rng: inout Rand,
                                alpha: CGFloat, blend: CGBlendMode) {
        let c = Swift.max(1, Swift.min(512, cells))
        guard let img = randomGridImage(cells: c, rng: &rng) else { return }
        let cell = size / CGFloat(c)
        let n = CGFloat(c + 4)
        let rect = CGRect(x: -2.5 * cell, y: -2.5 * cell, width: n * cell, height: n * cell)
        ctx.saveGState()
        ctx.interpolationQuality = .high
        img.draw(in: rect, blendMode: blend, alpha: alpha)
        ctx.restoreGState()
    }

    /// Fraktales Rauschen (mehrere Oktaven), z. B. für Flecken, Schmutz, Wolken.
    static func drawFBM(_ ctx: CGContext, size: CGFloat, rng: inout Rand, startCells: Int, octaves: Int,
                        alpha: CGFloat, blend: CGBlendMode, persistence: CGFloat = 0.62) {
        var cells = Swift.max(1, startCells)
        var a = alpha
        for _ in 0..<Swift.max(1, octaves) {
            drawNoiseOctave(ctx, size: size, cells: cells, rng: &rng, alpha: a, blend: blend)
            cells = Swift.min(512, cells * 2)
            a *= persistence
        }
    }

    /// Viele kleine Punkte (Körnung, Zuschlagstoffe, Poren).
    static func drawSpeckles(_ ctx: CGContext, size: CGFloat, count: Int, rng: inout Rand,
                             minRadius: CGFloat, maxRadius: CGFloat, gray: ClosedRange<CGFloat>, alpha: ClosedRange<CGFloat>) {
        guard count > 0 else { return }
        for _ in 0..<count {
            let x = rng.unit() * size
            let y = rng.unit() * size
            let r = rng.range(minRadius, maxRadius)
            let g = rng.range(gray.lowerBound, gray.upperBound)
            let a = rng.range(alpha.lowerBound, alpha.upperBound)
            ctx.setFillColor(UIColor(white: g, alpha: a).cgColor)
            ctx.fillEllipse(in: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2))
        }
    }

    /// Mittelgraues Pixelrauschen (gegen Farbabstufungen in dunklen Verläufen).
    static func ditherOverlay() -> UIImage {
        return cached("dither") {
            let n = 512
            var rng = Rand(seed: 0xD17E)
            var rgba = [UInt8](repeating: 255, count: n * n * 4)
            for i in 0..<(n * n) {
                let v = rng.byte()
                rgba[i * 4] = v
                rgba[i * 4 + 1] = v
                rgba[i * 4 + 2] = v
            }
            if let cg = makeCGImage(rgba: rgba, width: n, height: n) {
                return UIImage(cgImage: cg)
            }
            return renderImage(width: 4, height: 4, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: 4, height: 4))
            }
        }
    }

    private static func normalByte(_ v: Float) -> UInt8 {
        let x = v * 127.5 + 127.5
        if !(x > 0) { return 0 }
        if x >= 255 { return 255 }
        return UInt8(x)
    }

    /// Flache Normal-Map (128, 128, 255).
    static func flatNormal() -> UIImage {
        return cached("flatNormal") {
            renderImage(width: 4, height: 4, opaque: true) { ctx in
                ctx.setFillColor(UIColor(red: 0.5, green: 0.5, blue: 1.0, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: 4, height: 4))
            }
        }
    }

    /// Normal-Map aus einem Höhenbild (hell = hoch), nahtlos per Sobel-Filter.
    /// Konvention: Grün = +V nach oben (OpenGL/SceneKit). strength ≈ 2 ... 8.
    static func normalMap(fromHeight image: UIImage, strength: Float) -> UIImage {
        guard let cg = image.cgImage else { return flatNormal() }
        let w = cg.width
        let h = cg.height
        guard w > 2, h > 2, w <= 4096, h <= 4096 else { return flatNormal() }
        var gray = [UInt8](repeating: 128, count: w * h)
        let drawn: Bool = gray.withUnsafeMutableBytes { raw -> Bool in
            guard let base = raw.baseAddress,
                  let ctx = CGContext(data: base, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                                      space: CGColorSpaceCreateDeviceGray(),
                                      bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return false }
            ctx.interpolationQuality = .none
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        if !drawn { return flatNormal() }

        let k = strength / (255 * 4)
        var out = [UInt8](repeating: 255, count: w * h * 4)
        gray.withUnsafeBufferPointer { g in
            out.withUnsafeMutableBufferPointer { o in
                for y in 0..<h {
                    let ym = ((y - 1 + h) % h) * w
                    let y0 = y * w
                    let yp = ((y + 1) % h) * w
                    for x in 0..<w {
                        let xm = (x - 1 + w) % w
                        let xp = (x + 1) % w
                        let tl = Float(g[ym + xm])
                        let tc = Float(g[ym + x])
                        let tr = Float(g[ym + xp])
                        let ml = Float(g[y0 + xm])
                        let mr = Float(g[y0 + xp])
                        let bl = Float(g[yp + xm])
                        let bc = Float(g[yp + x])
                        let br = Float(g[yp + xp])
                        let dx = (tr + 2 * mr + br) - (tl + 2 * ml + bl)
                        let dy = (bl + 2 * bc + br) - (tl + 2 * tc + tr)
                        let n = simd_normalize(SIMD3<Float>(-dx * k, dy * k, 1))
                        let i = (y0 + x) * 4
                        o[i] = ProceduralTextures.normalByte(n.x)
                        o[i + 1] = ProceduralTextures.normalByte(n.y)
                        o[i + 2] = ProceduralTextures.normalByte(n.z)
                        o[i + 3] = 255
                    }
                }
            }
        }
        guard let result = makeCGImage(rgba: out, width: w, height: h) else { return flatNormal() }
        return UIImage(cgImage: result)
    }

    // MARK: - Einfache Texturen

    /// Nahtloses fraktales Graustufen-Rauschen.
    static func noise(size: Int, seed: UInt64) -> UIImage {
        let px = Swift.max(16, Swift.min(2048, size))
        return cached("noise-\(px)-\(seed)") {
            renderImage(width: px, height: px, opaque: true) { ctx in
                var rng = Rand(seed: seed)
                let s = CGFloat(px)
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
                ProceduralTextures.drawNoiseOctave(ctx, size: s, cells: 4, rng: &rng, alpha: 1, blend: .normal)
                var cells = 8
                var a: CGFloat = 0.6
                while cells <= Swift.min(256, px / 2) {
                    ProceduralTextures.drawNoiseOctave(ctx, size: s, cells: cells, rng: &rng, alpha: a, blend: .overlay)
                    cells *= 2
                    a *= 0.72
                }
            }
        }
    }

    /// Weicher Leuchtpunkt für Partikel (heller Kern, sanfter Abfall, transparent).
    static func radialGlow(color: UIColor) -> UIImage {
        var r: CGFloat = 1
        var g: CGFloat = 1
        var b: CGFloat = 1
        var a: CGFloat = 1
        if !color.getRed(&r, green: &g, blue: &b, alpha: &a) {
            r = 1; g = 1; b = 1
        }
        r = Swift.min(1, Swift.max(0, r))
        g = Swift.min(1, Swift.max(0, g))
        b = Swift.min(1, Swift.max(0, b))
        let key = "glow-\(Int(r * 255))-\(Int(g * 255))-\(Int(b * 255))"
        return cached(key) {
            renderImage(width: 128, height: 128, opaque: false) { ctx in
                let base = TexRGB(r, g, b)
                let core = base.mixed(TexRGB(1, 1, 1), 0.55)
                ProceduralTextures.drawRadial(ctx, center: CGPoint(x: 64, y: 64), radius: 64,
                                              colors: [core.color(1, alpha: 1),
                                                       base.color(1, alpha: 0.82),
                                                       base.color(1, alpha: 0.42),
                                                       base.color(1, alpha: 0.16),
                                                       base.color(1, alpha: 0.05),
                                                       base.color(1, alpha: 0)],
                                              locations: [0, 0.1, 0.25, 0.45, 0.7, 1])
            }
        }
    }

    /// Weiße Scheibe mit weichem Rand (Partikel, Decals) – mit particleColor einfärben.
    static func softDisc() -> UIImage {
        return cached("softDisc") {
            renderImage(width: 128, height: 128, opaque: false) { ctx in
                ProceduralTextures.drawRadial(ctx, center: CGPoint(x: 64, y: 64), radius: 63,
                                              colors: [UIColor(white: 1, alpha: 1),
                                                       UIColor(white: 1, alpha: 0.95),
                                                       UIColor(white: 1, alpha: 0.5),
                                                       UIColor(white: 1, alpha: 0)],
                                              locations: [0, 0.5, 0.78, 1])
            }
        }
    }

    /// Äquirektanguläres Himmelsbild (2:1), Horizont in der Bildmitte.
    static func skyGradient(top: UIColor, horizon: UIColor, bottom: UIColor) -> UIImage {
        let key = "skyGrad-\(colorKey(top))-\(colorKey(horizon))-\(colorKey(bottom))"
        return cached(key) {
            renderImage(width: 512, height: 256, opaque: true) { ctx in
                let mid = horizon.blended3(with: top, t: 0.55)
                let low = horizon.blended3(with: bottom, t: 0.6)
                ProceduralTextures.drawLinear(ctx, from: CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 256),
                                              colors: [top, mid, horizon, low, bottom],
                                              locations: [0, 0.3, 0.5, 0.56, 1])
                ctx.interpolationQuality = .none
                ProceduralTextures.ditherOverlay().draw(in: CGRect(x: 0, y: 0, width: 512, height: 512),
                                                        blendMode: .softLight, alpha: 0.15)
            }
        }
    }

    private static func colorKey(_ c: UIColor) -> String {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 0
        if !c.getRed(&r, green: &g, blue: &b, alpha: &a) { return "x" }
        return "\(Int(r * 255))_\(Int(g * 255))_\(Int(b * 255))"
    }
}

extension UIColor {
    /// Lineare Mischung (eindeutiger Name, da Core/MathUtils bereits `blended(with:t:)` definiert).
    fileprivate func blended3(with other: UIColor, t: CGFloat) -> UIColor {
        var r1: CGFloat = 0, g1: CGFloat = 0, b1: CGFloat = 0, a1: CGFloat = 0
        var r2: CGFloat = 0, g2: CGFloat = 0, b2: CGFloat = 0, a2: CGFloat = 0
        _ = getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        _ = other.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)
        return UIColor(red: r1 + (r2 - r1) * t, green: g1 + (g2 - g1) * t,
                       blue: b1 + (b2 - b1) * t, alpha: a1 + (a2 - a1) * t)
    }
}

// MARK: - Oberflächen (Fassaden, Asphalt, Beton, Metall, Fliesen, Ziegel, Blut)

extension ProceduralTextures {

    /// Eine Fassaden-Textur deckt facadeTileMeters x facadeTileMeters Meter ab (4 x 4 Fenster, 3 m Geschosse).
    /// MeshBuilder: uvScale = 1 / facadeTileMeters verwenden.
    static let facadeTileMeters: Float = 12

    /// style 0 = Glasbüro, 1 = Ziegel-Wohnhaus, 2 = Beton, 3 = Neon-Gewerbe. lit = true liefert die Leuchtkarte (Emission).
    static func facade(style: Int, lit: Bool) -> UIImage {
        let s = ((style % 4) + 4) % 4
        return cached("facade\(s)\(lit ? "L" : "D")") {
            let size = 512
            let px = CGFloat(size)
            var rng = Rand(seed: UInt64(0xFACADE + s * 977))
            let wall: TexRGB
            let frame: TexRGB
            let glass: TexRGB
            switch s {
            case 0: wall = TexRGB(0.16, 0.18, 0.21); frame = TexRGB(0.30, 0.32, 0.35); glass = TexRGB(0.07, 0.10, 0.14)
            case 1: wall = TexRGB(0.36, 0.18, 0.13); frame = TexRGB(0.55, 0.50, 0.44); glass = TexRGB(0.06, 0.07, 0.09)
            case 2: wall = TexRGB(0.38, 0.37, 0.35); frame = TexRGB(0.24, 0.24, 0.24); glass = TexRGB(0.08, 0.09, 0.10)
            default: wall = TexRGB(0.10, 0.09, 0.12); frame = TexRGB(0.20, 0.18, 0.24); glass = TexRGB(0.05, 0.05, 0.08)
            }
            let cols = 4
            let rows = 4
            let cellW = px / CGFloat(cols)
            let cellH = px / CGFloat(rows)
            let winW: CGFloat = s == 0 ? cellW * 0.92 : cellW * 0.58
            let winH: CGFloat = s == 0 ? cellH * 0.78 : cellH * 0.56
            return renderImage(width: size, height: size, opaque: true) { ctx in
                if lit {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                } else {
                    ctx.setFillColor(wall.color().cgColor)
                    ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                    drawFBM(ctx, size: px, rng: &rng, startCells: 4, octaves: 4, alpha: 0.18, blend: .overlay)
                    if s == 1 {
                        // Ziegelfugen
                        ctx.setStrokeColor(UIColor(white: 0.12, alpha: 0.35).cgColor)
                        ctx.setLineWidth(1)
                        var y: CGFloat = 0
                        var row = 0
                        while y < px {
                            ctx.move(to: CGPoint(x: 0, y: y)); ctx.addLine(to: CGPoint(x: px, y: y))
                            var x: CGFloat = row % 2 == 0 ? 0 : 8
                            while x < px { ctx.move(to: CGPoint(x: x, y: y)); ctx.addLine(to: CGPoint(x: x, y: y + 6)); x += 16 }
                            y += 6; row += 1
                        }
                        ctx.strokePath()
                    }
                    // Geschossbänder
                    ctx.setFillColor(frame.color(0.8).cgColor)
                    for r in 0..<rows {
                        ctx.fill(CGRect(x: 0, y: CGFloat(r) * cellH, width: px, height: s == 0 ? 6 : 10))
                    }
                }
                for r in 0..<rows {
                    for c in 0..<cols {
                        let x = CGFloat(c) * cellW + (cellW - winW) / 2
                        let y = CGFloat(r) * cellH + (cellH - winH) * 0.6
                        let rect = CGRect(x: x, y: y, width: winW, height: winH)
                        let isLit = rng.chance(s == 3 ? 0.55 : 0.38)
                        let warm = rng.chance(0.7)
                        let shade = rng.range(0.55, 1.0)
                        if lit {
                            guard isLit else { continue }
                            let base: UIColor = warm
                                ? UIColor(red: 1.0, green: 0.72, blue: 0.42, alpha: 1)
                                : (s == 3 ? UIColor(red: 0.95, green: 0.25, blue: 0.6, alpha: 1) : UIColor(red: 0.6, green: 0.8, blue: 1.0, alpha: 1))
                            ctx.saveGState()
                            ctx.clip(to: rect)
                            drawLinear(ctx, from: CGPoint(x: rect.midX, y: rect.minY), to: CGPoint(x: rect.midX, y: rect.maxY),
                                       colors: [base.withAlphaComponent(shade * 0.55), base.withAlphaComponent(shade)],
                                       locations: [0, 1])
                            // Silhouette von Möbeln / Jalousien
                            if rng.chance(0.4) {
                                ctx.setFillColor(UIColor(white: 0, alpha: 0.55).cgColor)
                                ctx.fill(CGRect(x: rect.minX + rect.width * rng.range(0.1, 0.6), y: rect.maxY - rect.height * 0.35,
                                                width: rect.width * 0.25, height: rect.height * 0.35))
                            }
                            ctx.restoreGState()
                        } else {
                            ctx.setFillColor(frame.color().cgColor)
                            ctx.fill(rect.insetBy(dx: -3, dy: -3))
                            ctx.setFillColor((isLit ? glass.color(1.6) : glass.color()).cgColor)
                            ctx.fill(rect)
                            // Spiegelung
                            ctx.setFillColor(UIColor(white: 1, alpha: 0.05).cgColor)
                            ctx.fill(CGRect(x: rect.minX, y: rect.minY, width: rect.width * 0.35, height: rect.height))
                            if s != 0 {
                                ctx.setFillColor(frame.color(0.7).cgColor)
                                ctx.fill(CGRect(x: rect.midX - 1.5, y: rect.minY, width: 3, height: rect.height))
                            }
                        }
                    }
                }
            }
        }
    }

    static func asphalt() -> UIImage {
        return cached("asphalt") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xA5FA17)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.11, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 5, alpha: 0.35, blend: .overlay)
                drawSpeckles(ctx, size: px, count: 2600, rng: &rng, minRadius: 0.4, maxRadius: 1.4,
                             gray: 0.05...0.35, alpha: 0.3...0.8)
                // Risse
                ctx.setStrokeColor(UIColor(white: 0.03, alpha: 0.8).cgColor)
                ctx.setLineWidth(1.2)
                for _ in 0..<7 {
                    var p = CGPoint(x: rng.unit() * px, y: rng.unit() * px)
                    ctx.move(to: p)
                    for _ in 0..<12 {
                        p = CGPoint(x: p.x + rng.range(-14, 14), y: p.y + rng.range(-14, 14))
                        ctx.addLine(to: p)
                    }
                }
                ctx.strokePath()
            }
        }
    }

    static func asphaltNormal() -> UIImage {
        return cached("asphaltN") {
            return normalMap(fromHeight: asphalt(), strength: 2.0)
        }
    }

    static func concrete() -> UIImage {
        return cached("concrete") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xC0C0)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.42, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 2, octaves: 5, alpha: 0.3, blend: .overlay)
                drawSpeckles(ctx, size: px, count: 1500, rng: &rng, minRadius: 0.5, maxRadius: 1.8,
                             gray: 0.2...0.6, alpha: 0.2...0.5)
                ctx.setStrokeColor(UIColor(white: 0.25, alpha: 0.6).cgColor)
                ctx.setLineWidth(2)
                ctx.stroke(CGRect(x: 1, y: 1, width: px - 2, height: px - 2))
                // Wasserflecken
                for _ in 0..<5 {
                    let x = rng.unit() * px
                    ctx.setFillColor(UIColor(white: 0.2, alpha: 0.12).cgColor)
                    ctx.fill(CGRect(x: x, y: 0, width: rng.range(6, 30), height: px))
                }
            }
        }
    }

    static func metalPanels() -> UIImage {
        return cached("metal") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0x3E7A1)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 4, octaves: 4, alpha: 0.2, blend: .overlay)
                let panel = px / 4
                ctx.setStrokeColor(UIColor(white: 0.18, alpha: 1).cgColor)
                ctx.setLineWidth(3)
                for i in 0...4 {
                    let v = CGFloat(i) * panel
                    ctx.move(to: CGPoint(x: v, y: 0)); ctx.addLine(to: CGPoint(x: v, y: px))
                    ctx.move(to: CGPoint(x: 0, y: v)); ctx.addLine(to: CGPoint(x: px, y: v))
                }
                ctx.strokePath()
                ctx.setFillColor(UIColor(white: 0.25, alpha: 1).cgColor)
                for i in 0..<4 {
                    for j in 0..<4 {
                        for k in 0..<4 {
                            let cx = CGFloat(i) * panel + (k % 2 == 0 ? 10 : panel - 10)
                            let cy = CGFloat(j) * panel + (k < 2 ? 10 : panel - 10)
                            ctx.fillEllipse(in: CGRect(x: cx - 3, y: cy - 3, width: 6, height: 6))
                        }
                    }
                }
                // Rost
                drawSpeckles(ctx, size: px, count: 400, rng: &rng, minRadius: 1, maxRadius: 5,
                             gray: 0.25...0.4, alpha: 0.15...0.35)
            }
        }
    }

    static func tiles() -> UIImage {
        return cached("tiles") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0x711E5)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.3, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                let t = px / 8
                for i in 0..<8 {
                    for j in 0..<8 {
                        let g = rng.range(0.62, 0.8)
                        ctx.setFillColor(UIColor(red: g * 0.92, green: g, blue: g * 0.95, alpha: 1).cgColor)
                        ctx.fill(CGRect(x: CGFloat(i) * t + 2, y: CGFloat(j) * t + 2, width: t - 4, height: t - 4))
                    }
                }
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 4, alpha: 0.3, blend: .multiply)
            }
        }
    }

    static func brick() -> UIImage {
        return cached("brick") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xB21C)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.22, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                let bh = px / 16
                let bw = px / 8
                for r in 0..<16 {
                    let off: CGFloat = r % 2 == 0 ? 0 : bw / 2
                    for c in -1..<9 {
                        let k = rng.range(0.75, 1.1)
                        ctx.setFillColor(UIColor(red: 0.42 * k, green: 0.19 * k, blue: 0.14 * k, alpha: 1).cgColor)
                        ctx.fill(CGRect(x: CGFloat(c) * bw + off + 2, y: CGFloat(r) * bh + 2, width: bw - 4, height: bh - 4))
                    }
                }
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 4, alpha: 0.25, blend: .overlay)
            }
        }
    }

    static func bloodSplat() -> UIImage {
        return cached("bloodSplat") {
            let n = 256
            let px = CGFloat(n)
            var rng = Rand(seed: 0xB100D)
            return renderImage(width: n, height: n, opaque: false) { ctx in
                let c = CGPoint(x: px / 2, y: px / 2)
                let red = UIColor(red: 0.32, green: 0.0, blue: 0.01, alpha: 0.95)
                ctx.setFillColor(red.cgColor)
                ctx.fillEllipse(in: CGRect(x: c.x - px * 0.28, y: c.y - px * 0.25, width: px * 0.56, height: px * 0.5))
                for _ in 0..<26 {
                    let a = rng.range(0, .pi * 2)
                    let d = rng.range(px * 0.15, px * 0.46)
                    let r = rng.range(2, 14)
                    ctx.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
                }
            }
        }
    }
}

// =====================================================================
// MARK: - Character/Animations.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Animationen
//  Gelenke, Posen und die komplette Clip-Bibliothek (alle AnimClip-Fälle).
//
//  Konventionen (Posen-Raum, Radiant):
//  - Rumpf-Gelenke (hips, spine, chest, neck, head):
//      x+ = nach vorne beugen (Kopf: nicken), y+ = Drehung zur EIGENEN linken Seite,
//      z+ = Neigung zur eigenen rechten Seite.
//  - Gliedmaßen (beide Seiten gespiegelt, gleiche Zahlen = symmetrische Bewegung):
//      x+ = Gliedende nach vorne schwingen (Arm/Bein heben, Ellbogen beugen),
//      Schienbein: x- = Knie beugen, Fuß: x+ = Zehen hoch, Hand: x+ = Handgelenk beugen,
//      z+ = abspreizen (vom Körper weg), y+ = nach außen drehen / horizontal nach außen schwingen.
//  - Rotationsreihenfolge je Gelenk: erst Roll (z), dann Pitch (x), dann Yaw (y) um die Elternachse.
//  - hipsOffset wird für eine 1,80-m-Figur angegeben und vom Rig mit der Körpergröße skaliert.
//  - Die Figur schaut lokal nach +Z, ihre linke Seite liegt bei +X.
//
//  Die Schlüsselposen wurden mit einem Vorwärtskinematik-Werkzeug erstellt und geprüft
//  (Füße auf dem Boden, Fäuste auf Kopfhöhe beim Schlag, Liegen auf dem Rücken usw.).
// =====================================================================

// MARK: - Gelenke

enum Joint: String, CaseIterable {
    case hips, spine, chest, neck, head
    case lUpperArm, lForearm, lHand, rUpperArm, rForearm, rHand
    case lThigh, lShin, lFoot, rThigh, rShin, rFoot

    /// +1 = linke Körperseite, -1 = rechte Körperseite, 0 = Körpermitte.
    var rigSide: Int {
        switch self {
        case .lUpperArm, .lForearm, .lHand, .lThigh, .lShin, .lFoot: return 1
        case .rUpperArm, .rForearm, .rHand, .rThigh, .rShin, .rFoot: return -1
        case .hips, .spine, .chest, .neck, .head: return 0
        }
    }

    /// Elterngelenk in der Hierarchie (nil = Hüfte hängt direkt am Wurzelknoten).
    var rigParent: Joint? {
        switch self {
        case .hips: return nil
        case .spine: return .hips
        case .chest: return .spine
        case .neck: return .chest
        case .head: return .neck
        case .lUpperArm, .rUpperArm: return .chest
        case .lForearm: return .lUpperArm
        case .rForearm: return .rUpperArm
        case .lHand: return .lForearm
        case .rHand: return .rForearm
        case .lThigh, .rThigh: return .hips
        case .lShin: return .lThigh
        case .rShin: return .rThigh
        case .lFoot: return .lShin
        case .rFoot: return .rShin
        }
    }

    /// Das gespiegelte Gelenk (links <-> rechts).
    var rigMirror: Joint {
        switch self {
        case .hips, .spine, .chest, .neck, .head: return self
        case .lUpperArm: return .rUpperArm
        case .lForearm: return .rForearm
        case .lHand: return .rHand
        case .rUpperArm: return .lUpperArm
        case .rForearm: return .lForearm
        case .rHand: return .lHand
        case .lThigh: return .rThigh
        case .lShin: return .rShin
        case .lFoot: return .rFoot
        case .rThigh: return .lThigh
        case .rShin: return .lShin
        case .rFoot: return .lFoot
        }
    }

    /// Wandelt eine Posen-Rotation in echte lokale Euler-Winkel des Gelenkknotens um.
    func rigRawEuler(_ e: SIMD3<Float>) -> SIMD3<Float> {
        switch rigSide {
        case 1: return SIMD3<Float>(-e.x, e.y, e.z)
        case -1: return SIMD3<Float>(-e.x, -e.y, -e.z)
        default: return e
        }
    }
}

// MARK: - Pose

/// Lokale Euler-Rotationen (Radiant) pro Gelenk + Versatz der Hüfte.
struct Pose {
    var rotations: [Joint: SIMD3<Float>]
    var hipsOffset: SIMD3<Float>

    init(_ rotations: [Joint: SIMD3<Float>] = [:], hipsOffset: SIMD3<Float> = .zero) {
        self.rotations = rotations
        self.hipsOffset = hipsOffset
    }

    /// Rotation eines Gelenks (fehlend = 0).
    subscript(_ j: Joint) -> SIMD3<Float> {
        get { return rotations[j] ?? SIMD3<Float>(0, 0, 0) }
        set { rotations[j] = newValue }
    }

    /// Lineare Mischung a -> b (t = 0 → a, t = 1 → b). Für weiche Übergänge t vorher glätten.
    static func blend(_ a: Pose, _ b: Pose, _ t: Float) -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            let va = a.rotations[j]
            let vb = b.rotations[j]
            if va == nil && vb == nil { continue }
            let x = va ?? SIMD3<Float>(0, 0, 0)
            let y = vb ?? SIMD3<Float>(0, 0, 0)
            out[j] = x + (y - x) * t
        }
        return Pose(out, hipsOffset: a.hipsOffset + (b.hipsOffset - a.hipsOffset) * t)
    }

    /// Wie blend, aber die Gier-Drehung (y) der Rumpfgelenke nimmt den kürzesten Weg (±π) –
    /// verhindert, dass nach einer vollen Drehung (z.B. Drehkick) beim Überblenden zurückgedreht wird.
    static func rigBlendShortest(_ a: Pose, _ b: Pose, _ t: Float) -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            let va = a.rotations[j]
            let vb = b.rotations[j]
            if va == nil && vb == nil { continue }
            let x = va ?? SIMD3<Float>(0, 0, 0)
            let y = vb ?? SIMD3<Float>(0, 0, 0)
            var d = y - x
            if j.rigSide == 0 {
                d.y = wrapAngle(d.y)
            }
            out[j] = x + d * t
        }
        return Pose(out, hipsOffset: a.hipsOffset + (b.hipsOffset - a.hipsOffset) * t)
    }

    /// Additiv: addiert die Rotationen und den Hüftversatz von `other`, skaliert mit weight.
    func rigAdding(_ other: Pose, weight: Float = 1) -> Pose {
        var out = self
        for (j, r) in other.rotations {
            out[j] = out[j] + r * weight
        }
        out.hipsOffset += other.hipsOffset * weight
        return out
    }

    /// Spiegelt die Pose (links <-> rechts).
    func mirrored() -> Pose {
        var out: [Joint: SIMD3<Float>] = [:]
        for (j, r) in rotations {
            if j.rigSide == 0 {
                out[j] = SIMD3<Float>(r.x, -r.y, -r.z)
            } else {
                out[j.rigMirror] = r
            }
        }
        return Pose(out, hipsOffset: SIMD3<Float>(-hipsOffset.x, hipsOffset.y, hipsOffset.z))
    }

    /// Catmull-Rom-Spline durch p1 -> p2 (p0/p3 = Nachbarn) – für weiche Schleifen.
    static func rigCatmull(_ p0: Pose, _ p1: Pose, _ p2: Pose, _ p3: Pose, _ u: Float) -> Pose {
        let u2 = u * u
        let u3 = u2 * u
        let c0 = -0.5 * u3 + u2 - 0.5 * u
        let c1 = 1.5 * u3 - 2.5 * u2 + 1.0
        let c2 = -1.5 * u3 + 2.0 * u2 + 0.5 * u
        let c3 = 0.5 * u3 - 0.5 * u2
        var out: [Joint: SIMD3<Float>] = [:]
        out.reserveCapacity(Joint.allCases.count)
        for j in Joint.allCases {
            if p0.rotations[j] == nil && p1.rotations[j] == nil && p2.rotations[j] == nil && p3.rotations[j] == nil {
                continue
            }
            var acc = p0[j] * c0
            acc += p1[j] * c1
            acc += p2[j] * c2
            acc += p3[j] * c3
            out[j] = acc
        }
        var h = p0.hipsOffset * c0
        h += p1.hipsOffset * c1
        h += p2.hipsOffset * c2
        h += p3.hipsOffset * c3
        return Pose(out, hipsOffset: h)
    }
}

// MARK: - Keyframes & Clips

/// Wie ein Schlüsselbild ERREICHT wird (Kurve vom vorherigen Schlüssel zu diesem).
enum RigEase {
    case smooth     // Smoothstep
    case snap       // schneller Start, weiches Abbremsen (Schläge, Tritte)
    case accel      // langsamer Start, beschleunigt (Fallen)
    case linear

    func apply(_ u: Float) -> Float {
        let x = Swift.max(0, Swift.min(1, u))
        switch self {
        case .smooth: return x * x * (3 - 2 * x)
        case .snap:
            let k = 1 - x
            return 1 - k * k * k
        case .accel: return x * x
        case .linear: return x
        }
    }
}

struct RigKeyframe {
    let time: Float      // 0...1 (Anteil der Cliplänge)
    let pose: Pose
    let ease: RigEase
}

struct RigClip {
    let duration: Float          // Standardlänge in Sekunden (Schleifen: Länge eines Zyklus)
    let loops: Bool
    var breathing: Float         // Stärke der prozeduralen Atmung (0 = keine)
    private(set) var keys: [RigKeyframe] = []

    init(duration: Float, loops: Bool, breathing: Float = 1) {
        self.duration = duration
        self.loops = loops
        self.breathing = breathing
    }

    mutating func key(_ time: Float, _ ease: RigEase, pose: Pose) {
        keys.append(RigKeyframe(time: time, pose: pose, ease: ease))
    }

    mutating func key(_ time: Float, _ ease: RigEase, h: SIMD3<Float>, _ r: [Joint: SIMD3<Float>]) {
        keys.append(RigKeyframe(time: time, pose: Pose(r, hipsOffset: h), ease: ease))
    }

    /// Pose bei normierter Zeit (0...1). Schleifen: Catmull-Rom (zyklisch), sonst Ease pro Schlüssel.
    func sample(_ phase: Float) -> Pose {
        let n = keys.count
        if n == 0 { return Pose() }
        if n == 1 { return keys[0].pose }
        if loops {
            var t = phase.truncatingRemainder(dividingBy: 1)
            if t < 0 { t += 1 }
            if !t.isFinite { t = 0 }
            var i = n - 1
            for k in 0..<n {
                let next: Float = (k + 1 < n) ? keys[k + 1].time : 1.0 + keys[0].time
                if t >= keys[k].time && t < next {
                    i = k
                    break
                }
            }
            let t0 = keys[i].time
            let t1: Float = (i + 1 < n) ? keys[i + 1].time : 1.0 + keys[0].time
            var tt = t
            if tt < t0 { tt += 1 }
            let span = Swift.max(0.0001, t1 - t0)
            let u = Swift.max(0, Swift.min(1, (tt - t0) / span))
            let p0 = keys[(i - 1 + n) % n].pose
            let p1 = keys[i].pose
            let p2 = keys[(i + 1) % n].pose
            let p3 = keys[(i + 2) % n].pose
            return Pose.rigCatmull(p0, p1, p2, p3, u)
        }
        let t = Swift.max(0, Swift.min(1, phase.isFinite ? phase : 1))
        if t <= keys[0].time { return keys[0].pose }
        if t >= keys[n - 1].time { return keys[n - 1].pose }
        for k in 0..<(n - 1) {
            let a = keys[k]
            let b = keys[k + 1]
            if t >= a.time && t <= b.time {
                let span = Swift.max(0.0001, b.time - a.time)
                let u = b.ease.apply((t - a.time) / span)
                return Pose.blend(a.pose, b.pose, u)
            }
        }
        return keys[n - 1].pose
    }
}

// MARK: - Clip-Bibliothek

enum RigAnimLibrary {
    /// Ruhehaltung, auf die jede Pose addiert wird: Arme leicht abgespreizt, Ellbogen leicht gebeugt.
    static let restPose = Pose([
        .lUpperArm: SIMD3<Float>(0, 0, 0.1), .rUpperArm: SIMD3<Float>(0, 0, 0.1),
        .lForearm: SIMD3<Float>(0.15, 0, 0), .rForearm: SIMD3<Float>(0.15, 0, 0)
    ])

    private static var cache: [AnimClip: RigClip] = [:]

    /// Clip-Daten (einmal erzeugt, danach aus dem Cache).
    static func clip(_ c: AnimClip) -> RigClip {
        if let hit = cache[c] { return hit }
        let made = build(c)
        cache[c] = made
        return made
    }

    /// Standarddauer eines Clips in Sekunden.
    static func defaultDuration(_ c: AnimClip) -> Float {
        return clip(c).duration
    }

    /// true für Schleifen-Clips (idle, run, swing …).
    static func isLooping(_ c: AnimClip) -> Bool {
        return clip(c).loops
    }

    private static func v(_ x: Float, _ y: Float, _ z: Float) -> SIMD3<Float> {
        return SIMD3<Float>(x, y, z)
    }

    // MARK: Gemeinsame Posen (von mehreren Clips genutzt)
    private static let pCePump = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.05, 0, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, 0, 0), .lUpperArm: v(2.4, 0, 0.6),
        .lForearm: v(1.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.4, 0, 0.6),
        .rForearm: v(1.2, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.05, 0.25, 0.14),
        .lShin: v(-0.645, 0, 0), .lFoot: v(0.591, 0, -0.154), .rThigh: v(0, 0.3, 0.14),
        .rShin: v(-0.614, 0, 0), .rFoot: v(0.618, 0, -0.126)
    ], hipsOffset: v(0, -0.08, 0))
    private static let pCeUp = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.15, 0, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.35, 0, 0), .lUpperArm: v(2.75, 0, 0.5),
        .lForearm: v(0.25, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.75, 0, 0.5),
        .rForearm: v(0.25, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.05, 0.25, 0.14),
        .lShin: v(-0.258, 0, 0), .lFoot: v(0.204, 0, -0.154), .rThigh: v(0, 0.3, 0.14),
        .rShin: v(-0.268, 0, 0), .rFoot: v(0.273, 0, -0.126)
    ], hipsOffset: v(0, -0.02, 0))
    private static let pDsHit = Pose([
        .hips: v(0.1, 0.4, 0), .spine: v(0.2, 0.15, 0), .chest: v(0.05, 0.3, 0),
        .neck: v(-0.15, -0.2, 0), .head: v(-0.15, -0.3, 0), .lUpperArm: v(-0.8, 0.1, 0.35),
        .lForearm: v(0.5, 0, 0), .rUpperArm: v(1.8, 0.5, 0.05), .rForearm: v(0.05, 0, 0),
        .rHand: v(-0.2, 0, 0), .lThigh: v(1.05, 0, 0.06), .lShin: v(-0.452, 0, 0),
        .lFoot: v(-0.498, 0, -0.035), .rThigh: v(-0.75, 0.2, 0.08), .rShin: v(-0.15, 0, 0),
        .rFoot: v(-0.4, 0, 0)
    ], hipsOffset: v(0, -0.22, 0.2))
    private static let pGrPull = Pose([
        .hips: v(0.1, -0.15, 0), .spine: v(0.12, 0.05, 0), .chest: v(0.1, 0.05, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(-0.15, 0.05, 0), .lUpperArm: v(1.05, -0.4, 0.12),
        .lForearm: v(1.3, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(1.05, -0.45, 0.15),
        .rForearm: v(1.35, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
        .lShin: v(-0.997, 0, 0), .lFoot: v(0.341, 0, -0.077), .rThigh: v(-0.32, 0.4, 0.1),
        .rShin: v(-0.175, 0, 0), .rFoot: v(0.591, 0, -0.13)
    ], hipsOffset: v(0, -0.11, 0.06))
    private static let pGuard = Pose([
        .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
        .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
        .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
        .lShin: v(-0.595, 0, 0), .lFoot: v(-0.109, 0, -0.061), .rThigh: v(-0.32, 0.4, 0.1),
        .rShin: v(-0.218, 0, 0), .rFoot: v(0.587, 0, -0.113)
    ], hipsOffset: v(0, -0.1, 0))
    private static let pHh = Pose([
        .hips: v(-0.02, -0.25, 0), .spine: v(-0.15, 0, 0.05), .chest: v(-0.3, -0.1, 0.05),
        .neck: v(-0.3, 0.1, 0), .head: v(-0.4, 0.35, 0.15), .lUpperArm: v(0.3, 0.1, 0.55),
        .lForearm: v(0.7, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(0.2, 0.1, 0.5),
        .rForearm: v(0.8, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.588, 0.3, 0.06),
        .lShin: v(-0.221, 0, 0), .lFoot: v(-0.387, 0, -0.043), .rThigh: v(-0.173, 0.4, 0.1),
        .rShin: v(-0.569, 0, 0), .rFoot: v(0.724, 0, -0.091)
    ], hipsOffset: v(0, -0.1, -0.07))
    private static let pJkExt = Pose([
        .hips: v(-0.1, 0.25, 0), .spine: v(-0.15, 0, 0), .chest: v(-0.1, -0.15, 0),
        .neck: v(0.1, 0, 0), .head: v(0.15, -0.1, 0), .lUpperArm: v(-0.3, 0.2, 0.75),
        .lForearm: v(0.6, 0, 0), .rUpperArm: v(0.6, -0.4, 0.4), .rForearm: v(1.6, 0, 0),
        .lThigh: v(1, 0.1, 0.1), .lShin: v(-2, 0, 0), .lFoot: v(-0.4, 0, 0),
        .rThigh: v(1.5, -0.1, 0.05), .rShin: v(-0.05, 0, 0), .rFoot: v(0.3, 0, 0)
    ], hipsOffset: v(0, 0.05, 0))
    private static let pJtuck = Pose([
        .hips: v(0.1, 0, 0), .spine: v(0.12, 0, 0), .chest: v(0.05, 0, 0),
        .neck: v(-0.05, 0, 0), .head: v(-0.15, 0, 0), .lUpperArm: v(0.9, 0.1, 0.65),
        .lForearm: v(1.2, 0, 0), .rUpperArm: v(0.8, 0.1, 0.7), .rForearm: v(1.3, 0, 0),
        .lThigh: v(1.2, 0.1, 0.12), .lShin: v(-1.7, 0, 0), .lFoot: v(-0.3, 0, 0),
        .rThigh: v(0.95, 0.1, 0.12), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.3, 0, 0)
    ], hipsOffset: v(0, 0.05, 0))
    private static let pLieKd = Pose([
        .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0.02, 0.05, 0),
        .neck: v(0.05, 0.1, 0), .head: v(-0.15, 0.55, 0.05), .lUpperArm: v(0.35, 0, 0.75),
        .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
        .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
        .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
        .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
    ], hipsOffset: v(0, -0.8, -0.5))
    private static let pLookl = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.15, 0), .chest: v(-0.04, 0.25, -0.01),
        .neck: v(0, 0.25, 0), .head: v(-0.05, 0.4, 0), .lUpperArm: v(0.04, 0.05, 0.1),
        .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(-0.02, -0.03, 0.09),
        .rForearm: v(0.18, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0, 0.07),
        .lShin: v(-0.23, 0, 0), .lFoot: v(0.21, 0, -0.085), .rThigh: v(0.003, 0.3, 0.06),
        .rShin: v(-0.231, 0, 0), .rFoot: v(0.233, 0, -0.046)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pLookr = Pose([
        .hips: v(0, 0, -0.02), .spine: v(-0.02, -0.15, 0), .chest: v(-0.04, -0.25, 0.01),
        .neck: v(0, -0.25, 0), .head: v(-0.08, -0.4, 0), .lUpperArm: v(0, 0.05, 0.12),
        .lForearm: v(0.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.03, -0.03, 0.08),
        .rForearm: v(0.12, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.105, 0.3, 0.07),
        .lShin: v(-0.331, 0, 0), .lFoot: v(0.232, 0, -0.051), .rThigh: v(0.055, 0, 0.06),
        .rShin: v(-0.372, 0, 0), .rFoot: v(0.316, 0, -0.08)
    ], hipsOffset: v(-0.008, -0.018, 0))
    private static let pStand = Pose([
        .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.04, 0.02, -0.01),
        .neck: v(0.02, 0, 0), .head: v(0.03, -0.04, 0.01), .lUpperArm: v(0.04, 0.05, 0.1),
        .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(-0.02, -0.03, 0.09),
        .rForearm: v(0.18, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0.12, 0.07),
        .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
        .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pTa1 = Pose([
        .hips: v(0, -0.3, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.12, 0.2, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, -0.1, 0.1), .lUpperArm: v(1.1, -0.1, 0.1),
        .lForearm: v(0.45, 0, 0), .lHand: v(-0.7, 0, 0), .rUpperArm: v(0.1, 0.2, 0.55),
        .rForearm: v(1.8, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.742, 0.3, 0.06),
        .lShin: v(-0.598, 0, 0), .lFoot: v(-0.145, 0, -0.044), .rThigh: v(-0.262, 0.4, 0.1),
        .rShin: v(-0.439, 0, 0), .rFoot: v(0.703, 0, -0.097)
    ], hipsOffset: v(0, -0.11, -0.02))
    private static let pTa2 = Pose([
        .hips: v(0, -0.3, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.12, 0.2, 0),
        .neck: v(-0.1, 0, 0), .head: v(-0.2, -0.1, 0.1), .lUpperArm: v(1.1, -0.1, 0.1),
        .lForearm: v(1, 0, 0), .lHand: v(0.7, 0, 0), .rUpperArm: v(0.1, 0.2, 0.55),
        .rForearm: v(1.8, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.742, 0.3, 0.06),
        .lShin: v(-0.598, 0, 0), .lFoot: v(-0.145, 0, -0.044), .rThigh: v(-0.262, 0.4, 0.1),
        .rShin: v(-0.439, 0, 0), .rFoot: v(0.703, 0, -0.097)
    ], hipsOffset: v(0, -0.11, -0.02))
    private static let pThSlam = Pose([
        .hips: v(0.2, 1.15, 0), .spine: v(0.55, 0.25, 0), .chest: v(0.3, 0.3, 0),
        .neck: v(-0.06, 0.05, 0), .head: v(-0.3, -0.2, 0), .lUpperArm: v(1, -0.2, 0.25),
        .lForearm: v(0.3, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(1, -0.2, 0.25),
        .rForearm: v(0.3, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.9, -0.4, 0.1),
        .lShin: v(-1.691, 0, 0), .lFoot: v(0.978, 0, 0.002), .rThigh: v(0.2, 0, 0.15),
        .rShin: v(-1.233, 0, 0), .rFoot: v(1.233, 0, -0.15)
    ], hipsOffset: v(0, -0.28, 0.05))
    private static let pViUp = Pose([
        .spine: v(-0.08, 0, 0), .chest: v(-0.15, 0.1, 0), .neck: v(-0.15, 0, 0),
        .head: v(-0.3, -0.1, 0), .lUpperArm: v(0.15, 0, 0.3), .lForearm: v(0.7, 0, 0),
        .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.95, 0, 0.18), .rForearm: v(0.12, 0, 0),
        .lThigh: v(0.05, 0.25, 0.16), .lShin: v(-0.36, 0, 0), .lFoot: v(0.309, 0, -0.16),
        .rThigh: v(0, 0.3, 0.14), .rShin: v(-0.332, 0, 0), .rFoot: v(0.332, 0, -0.14)
    ], hipsOffset: v(0, -0.03, 0))
    private static let pWsShot = Pose([
        .hips: v(0, 0, 0.015), .spine: v(0, 0.1, 0), .chest: v(-0.05, 0.3, 0),
        .neck: v(0.02, 0, 0), .head: v(-0.1, -0.3, 0), .lUpperArm: v(0.3, 0, 0.3),
        .lForearm: v(0.9, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.85, 0.25, 0.05),
        .rForearm: v(0.05, 0, 0), .rHand: v(-0.75, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
        .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
        .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
    ], hipsOffset: v(0, -0.012, 0))
    private static let pZip1 = Pose([
        .hips: v(0.25, 0, 0), .spine: v(0.1, 0, 0), .chest: v(-0.05, 0, 0),
        .neck: v(-0.2, 0, 0), .head: v(-0.3, 0, 0), .lUpperArm: v(2.5, -0.1, 0.15),
        .lForearm: v(0.2, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(2.6, -0.1, 0.12),
        .rForearm: v(0.15, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(-0.25, 0, 0.05),
        .lShin: v(-0.4, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(-0.1, 0, 0.05),
        .rShin: v(-0.2, 0, 0), .rFoot: v(-0.6, 0, 0)
    ], hipsOffset: v(0, 0, 0))

    // MARK: Clip-Erzeugung (exhaustiv über alle AnimClip-Fälle)
    private static func build(_ clip: AnimClip) -> RigClip {
        switch clip {
        case .idle: return makeIdle()
        case .fightIdle: return makeFightIdle()
        case .crouch: return makeCrouch()
        case .walkForward: return makeWalkForward()
        case .walkBack: return makeWalkBack()
        case .run: return makeRun()
        case .sprint: return makeSprint()
        case .jump: return makeJump()
        case .fall: return makeFall()
        case .land: return makeLand()
        case .swing: return makeSwing()
        case .webShoot: return makeWebShoot()
        case .zip: return makeZip()
        case .wallRun: return makeWallRun()
        case .perch: return makePerch()
        case .dive: return makeDive()
        case .punch: return makePunch()
        case .punch2: return makePunch2()
        case .kick: return makeKick()
        case .kick2: return makeKick2()
        case .uppercut: return makeUppercut()
        case .sweep: return makeSweep()
        case .jumpKick: return makeJumpKick()
        case .block: return makeBlock()
        case .hitHigh: return makeHitHigh()
        case .hitLow: return makeHitLow()
        case .knockdown: return makeKnockdown()
        case .lieDown: return makeLieDown()
        case .getUp: return makeGetUp()
        case .dizzy: return makeDizzy()
        case .grab: return makeGrab()
        case .throwToss: return makeThrowToss()
        case .cast: return makeCast()
        case .dashStrike: return makeDashStrike()
        case .victory: return makeVictory()
        case .defeat: return makeDefeat()
        case .taunt: return makeTaunt()
        case .talk: return makeTalk()
        case .point: return makePoint()
        case .crossArms: return makeCrossArms()
        case .lookAround: return makeLookAround()
        case .kneel: return makeKneel()
        case .celebrate: return makeCelebrate()
        }
    }

    private static func makeIdle() -> RigClip {
        var c = RigClip(duration: 3, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.5, .smooth, h: v(-0.008, -0.018, 0), [
            .hips: v(0, 0, -0.02), .spine: v(-0.02, 0.02, 0), .chest: v(-0.035, -0.02, 0.012),
            .neck: v(0.02, 0, 0), .head: v(0.01, 0.06, -0.01), .lUpperArm: v(0, 0.05, 0.12),
            .lForearm: v(0.2, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.03, -0.03, 0.08),
            .rForearm: v(0.12, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.084, 0.12, 0.07),
            .lShin: v(-0.334, 0, 0), .lFoot: v(0.252, 0, -0.05), .rThigh: v(0.043, 0.15, 0.06),
            .rShin: v(-0.347, 0, 0), .rFoot: v(0.301, 0, -0.08)
        ])
        return c
    }

    private static func makeFightIdle() -> RigClip {
        var c = RigClip(duration: 0.9, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.5, .smooth, h: v(0, -0.13, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.11, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.8, -0.4, 0.22),
            .lForearm: v(1.9, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.62, -0.7, 0.28),
            .rForearm: v(2.1, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.865, 0.3, 0.06),
            .lShin: v(-0.792, 0, 0), .lFoot: v(-0.027, 0, -0.056), .rThigh: v(-0.17, 0.4, 0.1),
            .rShin: v(-0.551, 0, 0), .rFoot: v(0.768, 0, -0.117)
        ])
        return c
    }

    private static func makeCrouch() -> RigClip {
        var c = RigClip(duration: 1.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.42, 0.02), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.15, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.25, 0.3, 0.18), .lShin: v(-2.117, 0, 0), .lFoot: v(1.042, 0, -0.146),
            .rThigh: v(0.75, 0.4, 0.22), .rShin: v(-1.983, 0, 0), .rFoot: v(1.397, 0, -0.262)
        ])
        c.key(0.5, .smooth, h: v(0, -0.44, 0.02), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.18, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.277, 0.3, 0.18), .lShin: v(-2.172, 0, 0), .lFoot: v(1.07, 0, -0.142),
            .rThigh: v(0.755, 0.4, 0.22), .rShin: v(-2.032, 0, 0), .rFoot: v(1.441, 0, -0.262)
        ])
        return c
    }

    private static func makeWalkForward() -> RigClip {
        var c = RigClip(duration: 1, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.085, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.62, 0.3, 0.06),
            .lShin: v(-0.876, 0, 0), .lFoot: v(0.303, 0, -0.065), .rThigh: v(-0.28, 0.4, 0.1),
            .rShin: v(-0.214, 0, 0), .rFoot: v(0.542, 0, -0.114)
        ])
        c.key(0.25, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.45, 0.3, 0.06),
            .lShin: v(-0.126, 0, 0), .lFoot: v(-0.277, 0, -0.07), .rThigh: v(0.15, 0.4, 0.1),
            .rShin: v(-0.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.4, 0.3, 0.06),
            .lShin: v(-0.869, 0, 0), .lFoot: v(0.516, 0, -0.071), .rThigh: v(-0.42, 0.4, 0.1),
            .rFoot: v(0.469, 0, -0.109)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.9, 0, 0), .lFoot: v(0.4, 0, 0), .rThigh: v(-0.2, 0.4, 0.1),
            .rShin: v(-0.153, 0, 0), .rFoot: v(0.401, 0, -0.116)
        ])
        return c
    }

    private static func makeWalkBack() -> RigClip {
        var c = RigClip(duration: 1.1, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.085, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.62, 0.3, 0.06),
            .lShin: v(-0.876, 0, 0), .lFoot: v(0.303, 0, -0.065), .rThigh: v(-0.28, 0.4, 0.1),
            .rShin: v(-0.214, 0, 0), .rFoot: v(0.542, 0, -0.114)
        ])
        c.key(0.25, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.9, 0, 0), .lFoot: v(0.4, 0, 0), .rThigh: v(-0.2, 0.4, 0.1),
            .rShin: v(-0.153, 0, 0), .rFoot: v(0.401, 0, -0.116)
        ])
        c.key(0.5, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.4, 0.3, 0.06),
            .lShin: v(-0.869, 0, 0), .lFoot: v(0.516, 0, -0.071), .rThigh: v(-0.42, 0.4, 0.1),
            .rFoot: v(0.469, 0, -0.109)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, 0), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.45, 0.3, 0.06),
            .lShin: v(-0.126, 0, 0), .lFoot: v(-0.277, 0, -0.07), .rThigh: v(0.15, 0.4, 0.1),
            .rShin: v(-0.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        return c
    }

    private static func makeRun() -> RigClip {
        var c = RigClip(duration: 0.68, loops: true, breathing: 0.6)
        c.key(0, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0.048, 0.14, 0), .spine: v(0.16, 0.04, 0), .chest: v(0.064, -0.24, 0),
            .neck: v(-0.096, 0.06, 0), .head: v(-0.08, 0.08, 0), .lUpperArm: v(0.9, -0.25, 0.12),
            .lForearm: v(1.55, 0, 0), .lHand: v(0.15, 0, 0), .rUpperArm: v(-0.7, 0.1, 0.15),
            .rForearm: v(1.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(-0.55, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.65, 0.05, 0.03),
            .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.048, 0, 0), .spine: v(0.16, 0, 0), .chest: v(0.064, 0, 0),
            .neck: v(-0.096, 0, 0), .head: v(-0.08, 0, 0), .lUpperArm: v(0.1, -0.1, 0.14),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0, 0, 0.14),
            .rForearm: v(1.4, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.55, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.703, 0, 0), .rFoot: v(0.631, 0, -0.032)
        ])
        c.key(0.5, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0.048, -0.14, 0), .spine: v(0.16, -0.04, 0), .chest: v(0.064, 0.24, 0),
            .neck: v(-0.096, -0.06, 0), .head: v(-0.08, -0.08, 0), .lUpperArm: v(-0.7, 0.1, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.9, -0.25, 0.12),
            .rForearm: v(1.55, 0, 0), .rHand: v(0.15, 0, 0), .lThigh: v(0.65, 0.05, 0.03),
            .lFoot: v(0.25, 0, 0), .rThigh: v(-0.55, 0.05, 0.03), .rShin: v(-1, 0, 0),
            .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.08, 0), [
            .hips: v(0.048, 0, 0), .spine: v(0.16, 0, 0), .chest: v(0.064, 0, 0),
            .neck: v(-0.096, 0, 0), .head: v(-0.08, 0, 0), .lUpperArm: v(0, 0, 0.14),
            .lForearm: v(1.4, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.1, -0.1, 0.14),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.703, 0, 0), .lFoot: v(0.631, 0, -0.032), .rThigh: v(0.55, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeSprint() -> RigClip {
        var c = RigClip(duration: 0.5, loops: true, breathing: 0.5)
        c.key(0, .smooth, h: v(0, -0.06, 0), [
            .hips: v(0.096, 0.14, 0), .spine: v(0.32, 0.04, 0), .chest: v(0.128, -0.24, 0),
            .neck: v(-0.192, 0.06, 0), .head: v(-0.16, 0.08, 0), .lUpperArm: v(1.17, -0.25, 0.12),
            .lForearm: v(1.55, 0, 0), .lHand: v(0.15, 0, 0), .rUpperArm: v(-0.91, 0.1, 0.15),
            .rForearm: v(1.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(-0.688, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.812, 0.05, 0.03),
            .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.12, 0), [
            .hips: v(0.096, 0, 0), .spine: v(0.32, 0, 0), .chest: v(0.128, 0, 0),
            .neck: v(-0.192, 0, 0), .head: v(-0.16, 0, 0), .lUpperArm: v(0.1, -0.1, 0.14),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0, 0, 0.14),
            .rForearm: v(1.4, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.688, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.808, 0, 0), .rFoot: v(0.784, 0, -0.035)
        ])
        c.key(0.5, .smooth, h: v(0, -0.06, 0), [
            .hips: v(0.096, -0.14, 0), .spine: v(0.32, -0.04, 0), .chest: v(0.128, 0.24, 0),
            .neck: v(-0.192, -0.06, 0), .head: v(-0.16, -0.08, 0), .lUpperArm: v(-0.91, 0.1, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.17, -0.25, 0.12),
            .rForearm: v(1.55, 0, 0), .rHand: v(0.15, 0, 0), .lThigh: v(0.812, 0.05, 0.03),
            .lFoot: v(0.25, 0, 0), .rThigh: v(-0.688, 0.05, 0.03), .rShin: v(-1, 0, 0),
            .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.12, 0), [
            .hips: v(0.096, 0, 0), .spine: v(0.32, 0, 0), .chest: v(0.128, 0, 0),
            .neck: v(-0.192, 0, 0), .head: v(-0.16, 0, 0), .lUpperArm: v(0, 0, 0.14),
            .lForearm: v(1.4, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.1, -0.1, 0.14),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.808, 0, 0), .lFoot: v(0.784, 0, -0.035), .rThigh: v(0.688, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeJump() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.3, .smooth, h: v(0, -0.26, 0.02), [
            .hips: v(0.15, -0.2, 0), .spine: v(0.25, 0.05, 0), .chest: v(0.12, 0.08, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, 0.05, 0), .lUpperArm: v(-0.5, 0, 0.25),
            .lForearm: v(0.6, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(-0.6, 0, 0.25),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.341, 0.2, 0.08),
            .lShin: v(-1.359, 0, 0), .lFoot: v(0.162, 0, -0.059), .rThigh: v(0.111, 0.25, 0.1),
            .rShin: v(-1.193, 0, 0), .rFoot: v(1.228, 0, -0.137)
        ])
        c.key(0.55, .snap, h: v(0, 0.08, 0), [
            .spine: v(-0.05, 0, 0), .chest: v(-0.12, 0, 0), .neck: v(-0.05, 0, 0),
            .head: v(-0.15, 0, 0), .lUpperArm: v(2.2, 0, 0.35), .lForearm: v(0.4, 0, 0),
            .rUpperArm: v(2, 0, 0.35), .rForearm: v(0.5, 0, 0), .lThigh: v(0.05, 0.1, 0.05),
            .lShin: v(-0.08, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(-0.1, 0.1, 0.05),
            .rShin: v(-0.2, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(1, .smooth, pose: pJtuck)
        return c
    }

    private static func makeFall() -> RigClip {
        var c = RigClip(duration: 0.9, loops: true, breathing: 0.3)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.12, 0.05, 0), .spine: v(-0.1, 0, 0.03), .chest: v(-0.08, 0.05, 0),
            .neck: v(0.05, 0, 0), .head: v(0.25, 0, 0), .lUpperArm: v(0.9, 0.2, 1.15),
            .lForearm: v(0.7, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(0.6, 0.2, 1.25),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.55, 0.1, 0.12),
            .lShin: v(-0.9, 0, 0), .lFoot: v(-0.3, 0, 0), .rThigh: v(0.15, 0.1, 0.1),
            .rShin: v(-0.45, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.08, -0.05, 0), .spine: v(-0.12, 0, -0.03), .chest: v(-0.08, 0.05, 0),
            .neck: v(0.05, 0, 0), .head: v(0.25, 0, 0), .lUpperArm: v(0.65, 0.2, 1.3),
            .lForearm: v(0.7, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(0.85, 0.2, 1.1),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.2, 0.1, 0.1),
            .lShin: v(-0.5, 0, 0), .lFoot: v(-0.3, 0, 0), .rThigh: v(0.6, 0.1, 0.12),
            .rShin: v(-1, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        return c
    }

    private static func makeLand() -> RigClip {
        var c = RigClip(duration: 0.25, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pJtuck)
        c.key(0.35, .snap, h: v(0, -0.34, 0.02), [
            .hips: v(0.15, -0.2, 0), .spine: v(0.35, 0.05, 0), .chest: v(0.12, 0.08, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.25, 0, 0), .lUpperArm: v(0.3, 0, 0.6),
            .lForearm: v(0.6, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.3, 0, 0.6),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.533, 0.2, 0.08),
            .lShin: v(-1.605, 0, 0), .lFoot: v(0.216, 0, -0.044), .rThigh: v(0.156, 0.25, 0.1),
            .rShin: v(-1.434, 0, 0), .rFoot: v(1.423, 0, -0.137)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeSwing() -> RigClip {
        var c = RigClip(duration: 1.6, loops: true, breathing: 0.4)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(0.05, 0.1, 0), .spine: v(0.1, 0.05, -0.08), .chest: v(0, 0.1, -0.1),
            .neck: v(-0.1, -0.1, 0), .head: v(-0.15, -0.15, 0.05), .lUpperArm: v(0.4, 0.1, 0.95),
            .lForearm: v(0.9, 0, 0), .lHand: v(-0.1, 0, 0), .rUpperArm: v(2.95, 0, 0.12),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(1.1, 0, 0.1),
            .lShin: v(-1.7, 0, 0), .lFoot: v(-0.4, 0, 0), .rThigh: v(0.8, 0, 0.08),
            .rShin: v(-1.4, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(-0.12, 0.05, 0), .spine: v(-0.05, 0.05, -0.06), .chest: v(0, 0.1, -0.1),
            .neck: v(-0.1, -0.1, 0), .head: v(-0.05, -0.1, 0.04), .lUpperArm: v(0.2, 0.1, 1.1),
            .lForearm: v(0.5, 0, 0), .lHand: v(-0.1, 0, 0), .rUpperArm: v(2.95, 0, 0.12),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(0.45, 0, 0.08),
            .lShin: v(-0.6, 0, 0), .lFoot: v(-0.6, 0, 0), .rThigh: v(0.2, 0, 0.06),
            .rShin: v(-0.35, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        return c
    }

    private static func makeWebShoot() -> RigClip {
        var c = RigClip(duration: 0.3, loops: false, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(0, -0.15, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, 0.1, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.6, 0.1, 0.25),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.5, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(0.35, .snap, pose: pWsShot)
        c.key(1, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.1, 0), .chest: v(-0.05, 0.3, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.1, -0.3, 0), .lUpperArm: v(0.3, 0, 0.3),
            .lForearm: v(0.9, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.7, 0.2, 0.08),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.4, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makeZip() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 0.3)
        c.key(0, .smooth, pose: pWsShot)
        c.key(0.3, .snap, pose: pZip1)
        c.key(0.75, .smooth, pose: pZip1)
        c.key(1, .smooth, h: v(0, 0, 0), [
            .hips: v(0.05, 0, 0), .spine: v(0.1, 0, 0), .chest: v(-0.05, 0, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.3, 0, 0), .lUpperArm: v(2.2, -0.1, 0.2),
            .lForearm: v(0.6, 0, 0), .lHand: v(-0.2, 0, 0), .rUpperArm: v(2.3, -0.1, 0.2),
            .rForearm: v(0.5, 0, 0), .rHand: v(-0.2, 0, 0), .lThigh: v(1, 0, 0.1),
            .lShin: v(-1.4, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.8, 0, 0.1),
            .rShin: v(-1.2, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makeWallRun() -> RigClip {
        var c = RigClip(duration: 0.5, loops: true, breathing: 0.5)
        c.key(0, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.126, 0.14, 0), .spine: v(0.42, 0.04, 0), .chest: v(0.168, -0.24, 0),
            .neck: v(-0.252, 0.06, 0), .head: v(-0.21, 0.08, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(-0.66, 0.05, 0.03),
            .lShin: v(-1, 0, 0), .lFoot: v(-0.45, 0, 0), .rThigh: v(0.78, 0.05, 0.03),
            .rShin: v(-0.931, 0, 0), .rFoot: v(0.25, 0, 0)
        ])
        c.key(0.25, .smooth, h: v(0, -0.16, 0), [
            .hips: v(0.126, 0, 0), .spine: v(0.42, 0, 0), .chest: v(0.168, 0, 0),
            .neck: v(-0.252, 0, 0), .head: v(-0.21, 0, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.66, 0.05, 0.03),
            .lShin: v(-1.75, 0, 0), .lFoot: v(-0.2, 0, 0), .rThigh: v(0.12, 0.05, 0.03),
            .rShin: v(-0.909, 0, 0), .rFoot: v(0.915, 0, -0.036)
        ])
        c.key(0.5, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.126, -0.14, 0), .spine: v(0.42, -0.04, 0), .chest: v(0.168, 0.24, 0),
            .neck: v(-0.252, -0.06, 0), .head: v(-0.21, -0.08, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.78, 0.05, 0.03),
            .lShin: v(-0.931, 0, 0), .lFoot: v(0.25, 0, 0), .rThigh: v(-0.66, 0.05, 0.03),
            .rShin: v(-1, 0, 0), .rFoot: v(-0.45, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.16, 0), [
            .hips: v(0.126, 0, 0), .spine: v(0.42, 0, 0), .chest: v(0.168, 0, 0),
            .neck: v(-0.252, 0, 0), .head: v(-0.21, 0, 0), .lUpperArm: v(-0.95, 0.15, 0.35),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.15, 0.35),
            .rForearm: v(0.35, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.12, 0.05, 0.03),
            .lShin: v(-0.909, 0, 0), .lFoot: v(0.915, 0, -0.036), .rThigh: v(0.66, 0.05, 0.03),
            .rShin: v(-1.75, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        return c
    }

    private static func makePerch() -> RigClip {
        var c = RigClip(duration: 3.6, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.55, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.2, 0.08, 0),
            .neck: v(-0.3, 0, 0), .head: v(-0.65, -0.05, 0), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.65, 0.2, 0.42), .lShin: v(-2.46, 0, 0),
            .lFoot: v(1.063, 0, -0.141), .rThigh: v(1.55, 0.25, 0.5), .rShin: v(-2.457, 0, 0),
            .rFoot: v(1.127, 0, -0.213)
        ])
        c.key(0.35, .smooth, h: v(0, -0.54, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.17, 0.12, 0),
            .neck: v(-0.3, 0.08, 0), .head: v(-0.62, 0.25, 0.04), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.635, 0.2, 0.42), .lShin: v(-2.436, 0, 0),
            .lFoot: v(1.052, 0, -0.147), .rThigh: v(1.54, 0.25, 0.5), .rShin: v(-2.433, 0, 0),
            .rFoot: v(1.113, 0, -0.217)
        ])
        c.key(0.7, .smooth, h: v(0, -0.56, 0), [
            .hips: v(0.3, 0, 0), .spine: v(0.6, 0, 0), .chest: v(0.21, 0.04, 0),
            .neck: v(-0.3, -0.08, 0), .head: v(-0.67, -0.3, -0.03), .lUpperArm: v(1.1, -0.1, 0.05),
            .lHand: v(-1.2, 0, 0), .rUpperArm: v(0.55, 0, 0.45), .rForearm: v(1.35, 0, 0),
            .rHand: v(0.2, 0, 0), .lThigh: v(1.665, 0.2, 0.42), .lShin: v(-2.485, 0, 0),
            .lFoot: v(1.073, 0, -0.135), .rThigh: v(1.56, 0.25, 0.5), .rShin: v(-2.481, 0, 0),
            .rFoot: v(1.142, 0, -0.208)
        ])
        return c
    }

    private static func makeDive() -> RigClip {
        var c = RigClip(duration: 0.7, loops: true, breathing: 0.3)
        c.key(0, .smooth, h: v(0, 0, 0), [
            .hips: v(1.42, 0, 0), .spine: v(-0.05, 0, 0), .chest: v(-0.08, 0, 0),
            .neck: v(-0.35, 0, 0), .head: v(-0.55, 0, 0), .lUpperArm: v(-0.35, 0, 0.32),
            .lForearm: v(0.2, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.3, 0, 0.3),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(-0.06, 0, 0.03),
            .lShin: v(-0.12, 0, 0), .lFoot: v(-0.7, 0, 0), .rThigh: v(0.05, 0, 0.02),
            .rShin: v(-0.2, 0, 0), .rFoot: v(-0.7, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, 0, 0), [
            .hips: v(1.38, 0.03, 0.04), .spine: v(-0.05, 0, 0), .chest: v(-0.08, 0, 0),
            .neck: v(-0.35, 0, 0), .head: v(-0.55, 0, 0), .lUpperArm: v(-0.28, 0, 0.36),
            .lForearm: v(0.2, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.36, 0, 0.28),
            .rForearm: v(0.25, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.06, 0, 0.03),
            .lShin: v(-0.25, 0, 0), .lFoot: v(-0.7, 0, 0), .rThigh: v(-0.05, 0, 0.02),
            .rShin: v(-0.1, 0, 0), .rFoot: v(-0.7, 0, 0)
        ])
        return c
    }

    private static func makePunch() -> RigClip {
        var c = RigClip(duration: 0.32, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.2, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -0.5, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.1, 0, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.5, -0.6, 0.3),
            .rForearm: v(2.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.737, 0.3, 0.06),
            .lShin: v(-0.616, 0, 0), .lFoot: v(-0.075, 0, -0.061), .rThigh: v(-0.271, 0.4, 0.1),
            .rShin: v(-0.262, 0, 0), .rFoot: v(0.581, 0, -0.114)
        ])
        c.key(0.45, .snap, h: v(0, -0.115, 0.07), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.18, 0), .chest: v(0.12, 0.28, 0),
            .neck: v(-0.08, -0.2, 0), .head: v(0, -0.25, 0), .lUpperArm: v(0.6, -0.6, 0.2),
            .lForearm: v(2.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.9, 0.15, 0.05),
            .rForearm: v(0.06, 0, 0), .rHand: v(-0.1, 0, 0), .lThigh: v(0.86, 0, 0.06),
            .lShin: v(-0.793, 0, 0), .lFoot: v(0.013, 0, -0.043), .rThigh: v(-0.119, -0.05, 0.08),
            .rShin: v(-0.664, 0, 0), .rFoot: v(0.864, 0, -0.074)
        ])
        c.key(0.62, .smooth, h: v(0, -0.115, 0.07), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.18, 0), .chest: v(0.12, 0.25, 0),
            .neck: v(-0.08, -0.2, 0), .head: v(0, -0.25, 0), .lUpperArm: v(0.6, -0.6, 0.2),
            .lForearm: v(2.25, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(1.9, 0.15, 0.05),
            .rForearm: v(0.2, 0, 0), .rHand: v(-0.1, 0, 0), .lThigh: v(0.86, 0, 0.06),
            .lShin: v(-0.793, 0, 0), .lFoot: v(0.013, 0, -0.043), .rThigh: v(-0.119, -0.05, 0.08),
            .rShin: v(-0.664, 0, 0), .rFoot: v(0.864, 0, -0.074)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makePunch2() -> RigClip {
        var c = RigClip(duration: 0.36, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -0.2, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.3, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.5, -0.1, 0.6),
            .lForearm: v(1.9, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.773, 0.3, 0.06),
            .lShin: v(-0.592, 0, 0), .lFoot: v(-0.135, 0, -0.06), .rThigh: v(-0.338, 0.4, 0.1),
            .rShin: v(-0.242, 0, 0), .rFoot: v(0.628, 0, -0.112)
        ])
        c.key(0.48, .snap, h: v(0, -0.12, 0.03), [
            .hips: v(0.06, -0.5, 0), .spine: v(0.06, -0.15, 0), .chest: v(0.1, -0.2, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.45, 0), .lUpperArm: v(0.25, -0.25, 1.5),
            .lForearm: v(1.7, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28), .rForearm: v(2.15, 0, 0),
            .rHand: v(0.1, 0, 0), .lThigh: v(0.824, 0.3, 0.06), .lShin: v(-0.823, 0, 0),
            .lFoot: v(0.054, 0, -0.061), .rThigh: v(-0.255, 0.4, 0.1), .rShin: v(-0.337, 0, 0),
            .rFoot: v(0.649, 0, -0.119)
        ])
        c.key(0.64, .smooth, h: v(0, -0.12, 0.03), [
            .hips: v(0.06, -0.5, 0), .spine: v(0.06, -0.15, 0), .chest: v(0.1, -0.25, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.45, 0), .lUpperArm: v(0.25, -0.35, 1.45),
            .lForearm: v(1.7, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28), .rForearm: v(2.15, 0, 0),
            .rHand: v(0.1, 0, 0), .lThigh: v(0.824, 0.3, 0.06), .lShin: v(-0.823, 0, 0),
            .lFoot: v(0.054, 0, -0.061), .rThigh: v(-0.255, 0.4, 0.1), .rShin: v(-0.337, 0, 0),
            .rFoot: v(0.649, 0, -0.119)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKick() -> RigClip {
        var c = RigClip(duration: 0.45, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.25, .smooth, h: v(0, -0.06, 0.02), [
            .hips: v(0.05, 0.45, -0.15), .spine: v(0, -0.1, -0.2), .chest: v(0.05, -0.25, -0.1),
            .neck: v(0, -0.05, 0), .head: v(0.05, -0.1, 0.1), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.2, 0, 0.45), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.29, -0.35, 0.05), .lFoot: v(-0.292, 0, 0.11), .rThigh: v(1.45, 0, 0.55),
            .rShin: v(-2.1, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(0.48, .snap, h: v(0, -0.04, 0.03), [
            .hips: v(0.05, 1.15, -0.4), .spine: v(0, -0.25, -0.2), .chest: v(0.05, -0.45, -0.15),
            .neck: v(0, -0.2, 0.1), .head: v(0.05, -0.25, 0.2), .lUpperArm: v(0.8, -0.3, 0.45),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(-0.5, 0, 0.7), .rForearm: v(0.6, 0, 0),
            .lThigh: v(0.186, -0.75, 0.05), .lFoot: v(-0.423, 0, 0.279), .rThigh: v(1.5, 0, 1.3),
            .rShin: v(-0.1, 0, 0), .rFoot: v(-0.65, 0, 0)
        ])
        c.key(0.68, .smooth, h: v(0, -0.06, 0.02), [
            .hips: v(0.05, 0.8, 0), .spine: v(0, -0.1, -0.2), .chest: v(0.05, -0.25, -0.1),
            .neck: v(0, -0.05, 0), .head: v(0.05, -0.1, 0.1), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.2, 0, 0.45), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.553, -0.35, 0.05), .lShin: v(-0.147, 0, 0), .lFoot: v(-0.36, 0, -0.027),
            .rThigh: v(1.45, 0, 0.55), .rShin: v(-1.7, 0, 0), .rFoot: v(-0.6, 0, 0)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKick2() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.32, .accel, h: v(0, -0.1, 0), [
            .hips: v(0.15, -2, 0), .spine: v(0.2, -0.1, 0), .chest: v(0.1, -0.1, 0),
            .neck: v(0, 0.4, 0), .head: v(-0.05, 0.6, 0), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.6, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(0.12, -0.2, 0.05), .lShin: v(-0.661, 0, 0), .lFoot: v(0.689, 0, -0.02),
            .rThigh: v(0.9, 0.1, 0.1), .rShin: v(-1.8, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.55, .snap, h: v(0, -0.08, 0), [
            .hips: v(0.5, -3.05, 0), .spine: v(0.35, 0, 0), .chest: v(0.05, -0.1, 0),
            .neck: v(-0.3, 0.45, 0), .head: v(-0.35, 0.7, 0), .lUpperArm: v(0.7, -0.4, 0.35),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.3, -0.2, 0.5), .rForearm: v(1.6, 0, 0),
            .lThigh: v(0.359, -0.1, 0.05), .lShin: v(-0.488, 0, 0), .lFoot: v(0.627, 0, -0.002),
            .rThigh: v(-1.3, 0, 0.1), .rShin: v(-0.1, 0, 0), .rFoot: v(0.5, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.2, -3.9, 0), .spine: v(0.2, -0.1, 0), .chest: v(0.1, -0.1, 0),
            .neck: v(0, 0.2, 0), .head: v(0, 0.3, 0), .lUpperArm: v(0.85, -0.4, 0.3),
            .lForearm: v(1.85, 0, 0), .rUpperArm: v(0.6, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(0.642, -0.2, 0.05), .lShin: v(-1.08, 0, 0), .lFoot: v(0.634, 0, -0.006),
            .rThigh: v(0.5, 0.1, 0.1), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.1, 0), [
            .hips: v(0.05, -6.663, 0), .spine: v(0.05, 0.12, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(0.02, 0.07, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-0.595, 0, 0), .lFoot: v(-0.109, 0, -0.061), .rThigh: v(-0.32, 0.4, 0.1),
            .rShin: v(-0.218, 0, 0), .rFoot: v(0.587, 0, -0.113)
        ])
        return c
    }

    private static func makeUppercut() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.3, .smooth, h: v(0, -0.28, 0.02), [
            .hips: v(0.15, -0.55, 0), .spine: v(0.3, 0, 0.05), .chest: v(0.15, -0.25, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, 0.25, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.15, -0.2, 0.25),
            .rForearm: v(1.7, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(1.335, 0.3, 0.06),
            .lShin: v(-1.47, 0, 0), .lFoot: v(0.275, 0, -0.066), .rThigh: v(0.218, 0.4, 0.1),
            .rShin: v(-1.27, 0, 0), .rFoot: v(1.189, 0, -0.158)
        ])
        c.key(0.52, .snap, h: v(0, -0.08, 0.08), [
            .hips: v(-0.02, 0.2, 0), .spine: v(-0.12, 0.15, 0), .chest: v(-0.15, 0.3, 0),
            .neck: v(-0.05, -0.2, 0), .head: v(-0.15, -0.25, 0), .lUpperArm: v(0.6, -0.5, 0.3),
            .lForearm: v(2.2, 0, 0), .rUpperArm: v(2.55, -0.25, 0.1), .rForearm: v(1.05, 0, 0),
            .lThigh: v(0.657, 0.1, 0.06), .lShin: v(-0.639, 0, 0), .lFoot: v(-0.038, 0, -0.045),
            .rThigh: v(-0.372, 0.05, 0.08), .rShin: v(-0.354, 0, 0), .rFoot: v(0.707, 0, -0.074)
        ])
        c.key(0.72, .smooth, h: v(0, -0.08, 0.08), [
            .hips: v(-0.02, 0.2, 0), .spine: v(-0.12, 0.15, 0), .chest: v(-0.1, 0.28, 0),
            .neck: v(-0.05, -0.2, 0), .head: v(-0.15, -0.25, 0), .lUpperArm: v(0.6, -0.5, 0.3),
            .lForearm: v(2.2, 0, 0), .rUpperArm: v(2.55, -0.25, 0.1), .rForearm: v(1.2, 0, 0),
            .lThigh: v(0.657, 0.1, 0.06), .lShin: v(-0.639, 0, 0), .lFoot: v(-0.038, 0, -0.045),
            .rThigh: v(-0.372, 0.05, 0.08), .rShin: v(-0.354, 0, 0), .rFoot: v(0.707, 0, -0.074)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeSweep() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.25, .snap, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, -0.4, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, 0.1, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.2, 0.2, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.55, 0.2, 0.35), .lShin: v(-2.327, 0, 0),
            .lFoot: v(0.99, 0, -0.137), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.6, .snap, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, 1.15, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, -0.5, 0),
            .neck: v(-0.15, -0.2, 0), .head: v(-0.2, -0.45, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.931, -0.2, 0.3), .lShin: v(-2.258, 0, 0),
            .lFoot: v(0.592, 0, 0.081), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.75, .smooth, h: v(0.05, -0.5, 0), [
            .hips: v(0.25, 1.4, 0), .spine: v(0.25, 0.1, 0.1), .chest: v(0.1, -0.5, 0),
            .neck: v(-0.15, -0.2, 0), .head: v(-0.2, -0.45, 0), .lUpperArm: v(0.7, 0, 0.25),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(0.7, -0.5, 0.3),
            .rForearm: v(1.9, 0, 0), .lThigh: v(1.94, -0.2, 0.3), .lShin: v(-2.276, 0, 0),
            .lFoot: v(0.601, 0, 0.084), .rThigh: v(0.3, 0, 1.2), .rShin: v(-0.08, 0, 0),
            .rFoot: v(-0.2, 0, 0)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeJumpKick() -> RigClip {
        var c = RigClip(duration: 0.5, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pJtuck)
        c.key(0.3, .smooth, h: v(0, 0.05, 0), [
            .hips: v(0, 0.1, 0), .spine: v(-0.15, 0, 0), .chest: v(-0.1, -0.15, 0),
            .neck: v(0.1, 0, 0), .head: v(0.15, -0.1, 0), .lUpperArm: v(-0.3, 0.2, 0.75),
            .lForearm: v(0.6, 0, 0), .rUpperArm: v(0.6, -0.4, 0.4), .rForearm: v(1.6, 0, 0),
            .lThigh: v(1, 0.1, 0.1), .lShin: v(-2, 0, 0), .lFoot: v(-0.4, 0, 0),
            .rThigh: v(1.3, 0, 0.05), .rShin: v(-1.9, 0, 0), .rFoot: v(0.3, 0, 0)
        ])
        c.key(0.5, .snap, pose: pJkExt)
        c.key(0.75, .smooth, pose: pJkExt)
        c.key(1, .smooth, pose: pJtuck)
        return c
    }

    private static func makeBlock() -> RigClip {
        var c = RigClip(duration: 1.2, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.11, -0.02), [
            .hips: v(0.05, -0.3, 0), .spine: v(0.1, 0.1, 0), .chest: v(0.15, 0.2, 0),
            .neck: v(0.05, 0, 0), .head: v(0.22, 0, 0), .lUpperArm: v(1.3, -1.1, 0.15),
            .lForearm: v(1.75, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(1.3, -1.05, 0.15),
            .rForearm: v(1.75, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(0.791, 0.3, 0.06),
            .lShin: v(-0.595, 0, 0), .lFoot: v(-0.15, 0, -0.059), .rThigh: v(-0.195, 0.4, 0.1),
            .rShin: v(-0.475, 0, 0), .rFoot: v(0.717, 0, -0.117)
        ])
        c.key(0.5, .smooth, h: v(0, -0.125, -0.02), [
            .hips: v(0.05, -0.3, 0), .spine: v(0.1, 0.1, 0), .chest: v(0.17, 0.2, 0),
            .neck: v(0.05, 0, 0), .head: v(0.22, 0, 0), .lUpperArm: v(1.3, -1.1, 0.15),
            .lForearm: v(1.75, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(1.3, -1.05, 0.15),
            .rForearm: v(1.75, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(0.852, 0.3, 0.06),
            .lShin: v(-0.698, 0, 0), .lFoot: v(-0.107, 0, -0.056), .rThigh: v(-0.143, 0.4, 0.1),
            .rShin: v(-0.594, 0, 0), .rFoot: v(0.785, 0, -0.118)
        ])
        return c
    }

    private static func makeHitHigh() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .snap, pose: pHh)
        c.key(0.55, .smooth, h: v(0, -0.09, -0.04), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.05, 0.12, 0), .chest: v(-0.08, 0.1, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.1, 0.15, 0.05), .lUpperArm: v(0.6, -0.2, 0.3),
            .lForearm: v(1.5, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.65, 0.3, 0.06),
            .lShin: v(-0.314, 0, 0), .lFoot: v(-0.289, 0, -0.064), .rThigh: v(-0.203, 0.4, 0.1),
            .rShin: v(-0.376, 0, 0), .rFoot: v(0.627, 0, -0.116)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeHitLow() -> RigClip {
        var c = RigClip(duration: 0.35, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .snap, h: v(0, -0.14, -0.06), [
            .hips: v(0.1, -0.3, 0), .spine: v(0.4, 0, 0), .chest: v(0.3, 0.05, 0),
            .neck: v(0.1, 0, 0), .head: v(0.05, 0.05, 0), .lUpperArm: v(0.55, -0.55, 0.12),
            .lForearm: v(1.45, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.5, -0.6, 0.12),
            .rForearm: v(1.5, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.936, 0.3, 0.06),
            .lShin: v(-0.656, 0, 0), .lFoot: v(-0.187, 0, -0.069), .rThigh: v(0.057, 0.4, 0.1),
            .rShin: v(-0.84, 0, 0), .rFoot: v(0.876, 0, -0.139)
        ])
        c.key(0.55, .smooth, h: v(0, -0.1, -0.03), [
            .hips: v(0.05, -0.38, 0), .spine: v(0.15, 0.1, 0), .chest: v(0.08, 0.14, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.05, 0.05, 0), .lUpperArm: v(0.85, -0.4, 0.22),
            .lForearm: v(1.85, 0, 0), .lHand: v(0.1, 0, 0), .rUpperArm: v(0.6, -0.7, 0.28),
            .rForearm: v(2.15, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.727, 0.3, 0.06),
            .lShin: v(-0.48, 0, 0), .lFoot: v(-0.201, 0, -0.061), .rThigh: v(-0.19, 0.4, 0.1),
            .rShin: v(-0.429, 0, 0), .rFoot: v(0.666, 0, -0.117)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeKnockdown() -> RigClip {
        var c = RigClip(duration: 0.7, loops: false, breathing: 0)
        c.key(0, .smooth, pose: pHh)
        c.key(0.3, .accel, h: v(0, -0.3, -0.25), [
            .hips: v(-0.65, -0.1, 0), .spine: v(-0.1, 0, 0), .chest: v(-0.15, 0, 0),
            .neck: v(0.2, 0, 0), .head: v(0.3, 0.1, 0), .lUpperArm: v(1.5, 0.1, 0.6),
            .lForearm: v(0.5, 0, 0), .rUpperArm: v(1.7, 0.1, 0.5), .rForearm: v(0.4, 0, 0),
            .lThigh: v(0.75, 0.1, 0.1), .lShin: v(-0.6, 0, 0), .lFoot: v(-0.2, 0, 0),
            .rThigh: v(0.45, 0.1, 0.1), .rShin: v(-0.3, 0, 0), .rFoot: v(-0.2, 0, 0)
        ])
        c.key(0.62, .accel, h: v(0, -0.79, -0.5), [
            .hips: v(-1.571, 0, 0.03), .spine: v(0.08, 0, 0), .chest: v(0.12, 0, 0),
            .neck: v(0.25, 0, 0), .head: v(0.2, 0.1, 0), .lUpperArm: v(1, 0, 1),
            .lForearm: v(0.4, 0, 0), .rUpperArm: v(0.8, 0, 0.9), .rForearm: v(0.35, 0, 0),
            .lThigh: v(0.6, 0.1, 0.12), .lShin: v(-0.35, 0, 0), .lFoot: v(-0.3, 0, 0),
            .rThigh: v(0.45, -0.1, 0.06), .rShin: v(-0.2, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(0.8, .snap, h: v(0, -0.75, -0.5), [
            .hips: v(-1.48, 0, 0.03), .spine: v(0.08, 0, 0), .chest: v(0.05, 0.03, 0),
            .neck: v(0.25, 0, 0), .head: v(-0.05, 0.3, 0.03), .lUpperArm: v(0.5, 0, 0.85),
            .lForearm: v(0.4, 0, 0), .rUpperArm: v(0.2, 0, 0.6), .rForearm: v(0.35, 0, 0),
            .lThigh: v(0.3, 0.1, 0.12), .lShin: v(-0.35, 0, 0), .lFoot: v(-0.3, 0, 0),
            .rThigh: v(0.15, -0.1, 0.05), .rShin: v(-0.2, 0, 0), .rFoot: v(-0.4, 0, 0)
        ])
        c.key(1, .smooth, pose: pLieKd)
        return c
    }

    private static func makeLieDown() -> RigClip {
        var c = RigClip(duration: 4, loops: true, breathing: 0.25)
        c.key(0, .smooth, h: v(0, -0.8, -0.48), [
            .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0.02, 0.05, 0),
            .neck: v(0.05, 0.1, 0), .head: v(-0.15, 0.55, 0.05), .lUpperArm: v(0.35, 0, 0.75),
            .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
            .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
            .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
            .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
        ])
        c.key(0.5, .smooth, h: v(0, -0.8, -0.48), [
            .hips: v(-1.571, 0, 0.05), .spine: v(0, 0.05, 0), .chest: v(0, 0.05, 0),
            .neck: v(0.05, 0.1, 0), .head: v(-0.13, 0.57, 0.05), .lUpperArm: v(0.35, 0, 0.75),
            .lForearm: v(0.5, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(-0.05, 0, 0.45),
            .rForearm: v(0.25, 0, 0), .rHand: v(0.1, 0, 0), .lThigh: v(0.35, 0.1, 0.12),
            .lShin: v(-0.7, 0, 0), .lFoot: v(-0.35, 0, 0), .rThigh: v(0.06, -0.1, 0.05),
            .rShin: v(-0.08, 0, 0), .rFoot: v(-0.5, 0, 0)
        ])
        return c
    }

    private static func makeGetUp() -> RigClip {
        var c = RigClip(duration: 0.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pLieKd)
        c.key(0.32, .smooth, h: v(0, -0.66, -0.32), [
            .hips: v(-0.85, 0, 0), .spine: v(0.55, 0, 0), .chest: v(0.25, 0, 0),
            .neck: v(0.1, 0, 0), .head: v(0.1, 0, 0), .lUpperArm: v(-0.5, 0, 0.35),
            .lForearm: v(0.3, 0, 0), .lHand: v(-0.8, 0, 0), .rUpperArm: v(-0.55, 0, 0.35),
            .rForearm: v(0.3, 0, 0), .rHand: v(-0.8, 0, 0), .lThigh: v(1.55, 0.1, 0.2),
            .lShin: v(-2.1, 0, 0), .lFoot: v(0.2, 0, 0), .rThigh: v(1.35, 0.1, 0.15),
            .rShin: v(-1.9, 0, 0), .rFoot: v(0.2, 0, 0)
        ])
        c.key(0.65, .smooth, h: v(0, -0.36, -0.08), [
            .hips: v(0.2, -0.3, 0), .spine: v(0.25, 0.1, 0), .chest: v(0.15, 0.12, 0),
            .neck: v(-0.2, 0, 0), .head: v(-0.25, 0.08, 0), .lUpperArm: v(1, -0.4, 0.25),
            .lForearm: v(1.8, 0, 0), .rUpperArm: v(0.8, -0.6, 0.3), .rForearm: v(2.1, 0, 0),
            .lThigh: v(1.25, 0.3, 0.18), .lShin: v(-0.216, 0, 0), .lFoot: v(-0.859, 0, -0.146),
            .rThigh: v(0.75, 0.4, 0.22), .rShin: v(-1.825, 0, 0), .rFoot: v(1.239, 0, -0.262)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeDizzy() -> RigClip {
        var c = RigClip(duration: 1.9, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0.03, -0.06, 0), [
            .hips: v(0.02, 0.1, 0.07), .spine: v(0.12, 0.05, 0.06), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.15, 0.1, 0.08), .head: v(0.35, 0.2, 0.22), .lUpperArm: v(0.15, 0, 0.25),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.35, 0, 0.12),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.561, 0, 0), .lFoot: v(0.419, 0, -0.191), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.592, 0, 0), .rFoot: v(0.576, 0, -0.035)
        ])
        c.key(0.25, .smooth, h: v(0, -0.09, 0.02), [
            .hips: v(0.06, -0.05, 0), .spine: v(0.18, 0, 0), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.2, 0, 0), .head: v(0.5, 0, 0), .lUpperArm: v(0.3, 0, 0.18),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.25, 0, 0.2),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.737, 0, 0), .lFoot: v(0.646, 0, -0.128), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.65, 0, 0), .rFoot: v(0.659, 0, -0.112)
        ])
        c.key(0.5, .smooth, h: v(-0.03, -0.06, 0), [
            .hips: v(0.02, -0.1, -0.07), .spine: v(0.12, -0.05, -0.06), .chest: v(0.12, -0.05, -0.05),
            .neck: v(0.15, -0.1, -0.08), .head: v(0.35, -0.2, -0.22), .lUpperArm: v(0.35, 0, 0.12),
            .lForearm: v(0.55, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.15, 0, 0.25),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.05, 0.2, 0.1),
            .lShin: v(-0.592, 0, 0), .lFoot: v(0.576, 0, -0.035), .rThigh: v(0.15, 0.15, 0.12),
            .rShin: v(-0.561, 0, 0), .rFoot: v(0.419, 0, -0.191)
        ])
        c.key(0.75, .smooth, h: v(0, -0.05, -0.02), [
            .hips: v(0.06, -0.05, 0), .spine: v(0.06, 0, 0), .chest: v(0.12, 0.05, 0.05),
            .neck: v(0.2, 0, 0), .head: v(0.15, 0, 0), .lUpperArm: v(0.3, 0, 0.18),
            .lForearm: v(0.35, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(0.25, 0, 0.2),
            .rForearm: v(0.55, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.15, 0.15, 0.12),
            .lShin: v(-0.548, 0, 0), .lFoot: v(0.457, 0, -0.128), .rThigh: v(0.05, 0.2, 0.1),
            .rShin: v(-0.466, 0, 0), .rFoot: v(0.474, 0, -0.112)
        ])
        return c
    }

    private static func makeGrab() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.45, .snap, h: v(0, -0.13, 0.12), [
            .hips: v(0.1, -0.15, 0), .spine: v(0.25, 0.05, 0), .chest: v(0.1, 0.05, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.15, 0.05, 0), .lUpperArm: v(1.45, -0.15, 0.12),
            .lForearm: v(0.35, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(1.45, -0.2, 0.15),
            .rForearm: v(0.4, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.75, 0.3, 0.06),
            .lShin: v(-1.122, 0, 0), .lFoot: v(0.466, 0, -0.077), .rThigh: v(-0.32, 0.4, 0.1),
            .rShin: v(-0.259, 0, 0), .rFoot: v(0.675, 0, -0.13)
        ])
        c.key(0.7, .smooth, pose: pGrPull)
        c.key(1, .smooth, pose: pGrPull)
        return c
    }

    private static func makeThrowToss() -> RigClip {
        var c = RigClip(duration: 0.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGrPull)
        c.key(0.35, .smooth, h: v(0, -0.08, 0.02), [
            .hips: v(0, 0.6, 0), .spine: v(-0.2, 0.2, 0), .chest: v(-0.15, 0.35, 0),
            .neck: v(-0.06, 0.05, 0), .head: v(-0.2, -0.3, 0), .lUpperArm: v(2.2, -0.2, 0.4),
            .lForearm: v(0.7, 0, 0), .lHand: v(0.3, 0, 0), .rUpperArm: v(2.3, -0.2, 0.4),
            .rForearm: v(0.6, 0, 0), .rHand: v(0.3, 0, 0), .lThigh: v(0.4, -0.2, 0.08),
            .lShin: v(-0.88, 0, 0), .lFoot: v(0.479, 0, -0.074), .rThigh: v(-0.2, 0, 0.1),
            .rShin: v(-0.386, 0, 0), .rFoot: v(0.587, 0, -0.098)
        ])
        c.key(0.6, .snap, pose: pThSlam)
        c.key(0.75, .smooth, pose: pThSlam)
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeCast() -> RigClip {
        var c = RigClip(duration: 0.45, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.35, .smooth, h: v(0, -0.12, -0.02), [
            .hips: v(0.08, -0.7, 0), .spine: v(0.08, -0.1, 0), .chest: v(0.05, -0.35, 0),
            .neck: v(0, 0.25, 0), .head: v(0, 0.85, 0), .lUpperArm: v(0.3, -0.85, 0.15),
            .lForearm: v(2, 0, 0), .lHand: v(-0.4, 0, 0), .rUpperArm: v(-0.45, 0.2, 0.3),
            .rForearm: v(1.9, 0, 0), .rHand: v(-0.4, 0, 0), .lThigh: v(0.812, 0.3, 0.06),
            .lShin: v(-0.747, 0, 0), .lFoot: v(0.009, 0, -0.068), .rThigh: v(0.008, 0.4, 0.1),
            .rShin: v(-0.637, 0, 0), .rFoot: v(0.703, 0, -0.131)
        ])
        c.key(0.58, .snap, h: v(0, -0.155, 0.1), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.1, 0), .chest: v(0.06, 0.15, 0),
            .neck: v(0, -0.05, 0), .head: v(0, -0.18, 0), .lUpperArm: v(1.55, -0.35, 0.05),
            .lForearm: v(0.12, 0, 0), .lHand: v(-1, 0, 0), .rUpperArm: v(1.55, 0.05, 0.05),
            .rForearm: v(0.12, 0, 0), .rHand: v(-1, 0, 0), .lThigh: v(0.987, 0.2, 0.06),
            .lShin: v(-1.092, 0, 0), .lFoot: v(0.182, 0, -0.053), .rThigh: v(-0.276, 0.2, 0.1),
            .rShin: v(-0.568, 0, 0), .rFoot: v(0.925, 0, -0.11)
        ])
        c.key(0.78, .smooth, h: v(0, -0.155, 0.1), [
            .hips: v(0.08, 0.05, 0), .spine: v(0.08, 0.1, 0), .chest: v(0.06, 0.15, 0),
            .neck: v(0, -0.05, 0), .head: v(0, -0.18, 0), .lUpperArm: v(1.55, -0.35, 0.05),
            .lForearm: v(0.3, 0, 0), .lHand: v(-1, 0, 0), .rUpperArm: v(1.55, 0.05, 0.05),
            .rForearm: v(0.3, 0, 0), .rHand: v(-1, 0, 0), .lThigh: v(0.987, 0.2, 0.06),
            .lShin: v(-1.092, 0, 0), .lFoot: v(0.182, 0, -0.053), .rThigh: v(-0.276, 0.2, 0.1),
            .rShin: v(-0.568, 0, 0), .rFoot: v(0.925, 0, -0.11)
        ])
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeDashStrike() -> RigClip {
        var c = RigClip(duration: 0.4, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.22, .smooth, h: v(0, -0.2, 0.05), [
            .hips: v(0.15, -0.1, 0), .spine: v(0.4, 0.05, 0), .chest: v(0.15, 0.05, 0),
            .neck: v(-0.3, 0, 0), .head: v(-0.35, 0, 0), .lUpperArm: v(-0.9, 0.1, 0.3),
            .lForearm: v(0.4, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(-0.95, 0.1, 0.3),
            .rForearm: v(0.4, 0, 0), .rHand: v(-0.3, 0, 0), .lThigh: v(0.95, 0.1, 0.06),
            .lShin: v(-1.418, 0, 0), .lFoot: v(0.615, 0, -0.057), .rThigh: v(-0.55, 0.1, 0.06),
            .rShin: v(-0.7, 0, 0), .rFoot: v(-0.3, 0, 0)
        ])
        c.key(0.5, .snap, pose: pDsHit)
        c.key(0.72, .smooth, pose: pDsHit)
        c.key(1, .smooth, pose: pGuard)
        return c
    }

    private static func makeVictory() -> RigClip {
        var c = RigClip(duration: 1.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.18, .snap, pose: pViUp)
        c.key(0.4, .smooth, h: v(0, -0.05, 0), [
            .spine: v(-0.08, 0, 0), .chest: v(-0.1, 0.1, 0), .neck: v(-0.15, 0, 0),
            .head: v(-0.3, -0.1, 0), .lUpperArm: v(0.15, 0, 0.3), .lForearm: v(0.7, 0, 0),
            .lHand: v(0.1, 0, 0.05), .rUpperArm: v(2.95, 0, 0.18), .rForearm: v(0.55, 0, 0),
            .lThigh: v(0.05, 0.25, 0.16), .lShin: v(-0.495, 0, 0), .lFoot: v(0.444, 0, -0.16),
            .rThigh: v(0, 0.3, 0.14), .rShin: v(-0.46, 0, 0), .rFoot: v(0.46, 0, -0.14)
        ])
        c.key(0.55, .snap, pose: pViUp)
        c.key(1, .smooth, pose: pViUp)
        return c
    }

    private static func makeDefeat() -> RigClip {
        var c = RigClip(duration: 1.4, loops: false, breathing: 0.5)
        c.key(0, .smooth, pose: pHh)
        c.key(0.35, .accel, h: v(0, -0.44, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.35, 0, 0.04), .chest: v(0.25, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.5, 0.1, 0.08), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        c.key(0.45, .snap, h: v(0, -0.43, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.35, 0, 0.04), .chest: v(0.25, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.5, 0.1, 0.08), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.45, -0.04), [
            .hips: v(0.05, 0, 0), .spine: v(0.5, 0, 0.05), .chest: v(0.3, 0.05, 0),
            .neck: v(0.3, 0, 0), .head: v(0.6, 0.15, 0.12), .lUpperArm: v(0.12, 0, 0.18),
            .lForearm: v(0.3, 0, 0), .lHand: v(0.2, 0, 0), .rUpperArm: v(0.18, 0, 0.16),
            .rForearm: v(0.35, 0, 0), .rHand: v(0.2, 0, 0), .lThigh: v(-0.02, 0.1, 0.08),
            .lShin: v(-1.55, 0, 0), .lFoot: v(-1.2, 0, 0), .rThigh: v(0, 0.1, 0.08),
            .rShin: v(-1.55, 0, 0), .rFoot: v(-1.2, 0, 0)
        ])
        return c
    }

    private static func makeTaunt() -> RigClip {
        var c = RigClip(duration: 1.2, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pGuard)
        c.key(0.2, .smooth, pose: pTa1)
        c.key(0.35, .smooth, pose: pTa2)
        c.key(0.5, .smooth, pose: pTa1)
        c.key(0.65, .smooth, pose: pTa2)
        c.key(0.8, .smooth, pose: pTa1)
        c.key(1, .smooth, pose: pTa1)
        return c
    }

    private static func makeTalk() -> RigClip {
        var c = RigClip(duration: 2.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.04, 0.08, 0),
            .neck: v(0.02, 0, 0), .head: v(0.06, -0.08, 0.02), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(0.45, -0.1, 0.18),
            .rForearm: v(1.35, 0, 0), .rHand: v(-0.35, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(0.33, .smooth, h: v(-0.008, -0.018, 0), [
            .hips: v(0, 0, -0.02), .spine: v(-0.02, 0.02, 0), .chest: v(-0.035, -0.02, 0.012),
            .neck: v(0.02, 0, 0), .head: v(-0.04, 0.06, -0.02), .lUpperArm: v(0.4, -0.15, 0.15),
            .lForearm: v(1.25, 0, 0), .lHand: v(-0.4, 0, 0), .rUpperArm: v(0.35, -0.2, 0.22),
            .rForearm: v(1.1, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.084, 0.12, 0.07),
            .lShin: v(-0.334, 0, 0), .lFoot: v(0.252, 0, -0.05), .rThigh: v(0.043, 0.15, 0.06),
            .rShin: v(-0.347, 0, 0), .rFoot: v(0.301, 0, -0.08)
        ])
        c.key(0.66, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(-0.02, 0.02, 0), .chest: v(-0.03, -0.08, 0),
            .neck: v(0.02, 0, 0), .head: v(0.1, 0.1, 0), .lUpperArm: v(0.5, -0.1, 0.2),
            .lForearm: v(1.45, 0, 0), .lHand: v(-0.3, 0, 0), .rUpperArm: v(0.1, 0, 0.12),
            .rForearm: v(0.5, 0, 0), .rHand: v(0.12, 0, 0.04), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makePoint() -> RigClip {
        var c = RigClip(duration: 1, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.3, .snap, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.05, 0), .chest: v(-0.05, 0.22, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, -0.2, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.55, 0.1, 0.05),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        c.key(1, .smooth, h: v(0, -0.012, 0), [
            .hips: v(0, 0, 0.015), .spine: v(0, 0.05, 0), .chest: v(-0.05, 0.22, 0),
            .neck: v(0.02, 0, 0), .head: v(-0.05, -0.2, 0), .lUpperArm: v(0.04, 0.05, 0.1),
            .lForearm: v(0.12, 0, 0), .lHand: v(0.1, 0, 0.05), .rUpperArm: v(1.5, 0.1, 0.05),
            .rForearm: v(0.05, 0, 0), .rHand: v(-0.15, 0, 0), .lThigh: v(0.02, 0.12, 0.07),
            .lShin: v(-0.215, 0, 0), .lFoot: v(0.194, 0, -0.085), .rThigh: v(0, 0.15, 0.06),
            .rShin: v(-0.246, 0, 0), .rFoot: v(0.249, 0, -0.045)
        ])
        return c
    }

    private static func makeCrossArms() -> RigClip {
        var c = RigClip(duration: 3.4, loops: true, breathing: 1)
        c.key(0, .smooth, h: v(0.02, -0.015, 0), [
            .hips: v(0, 0.05, -0.04), .spine: v(-0.03, 0, 0), .chest: v(-0.06, 0, 0),
            .head: v(0.02, -0.05, 0.02), .lUpperArm: v(0.25, -1.3, 0.12), .lForearm: v(1.4, 0, 0),
            .rUpperArm: v(0.32, -1.35, 0.12), .rForearm: v(1.35, 0, 0), .lThigh: v(0.109, 0.15, 0.1),
            .lShin: v(-0.362, 0, 0), .lFoot: v(0.259, 0, -0.06), .rThigh: v(-0.04, 0.12, 0.04),
            .rShin: v(-0.194, 0, 0), .rFoot: v(0.23, 0, -0.08)
        ])
        c.key(0.5, .smooth, h: v(0, -0.02, 0), [
            .hips: v(0, 0.05, -0.04), .spine: v(-0.03, 0, 0), .chest: v(-0.04, 0.03, 0),
            .head: v(0.05, 0.12, 0), .lUpperArm: v(0.25, -1.3, 0.12), .lForearm: v(1.4, 0, 0),
            .rUpperArm: v(0.32, -1.35, 0.12), .rForearm: v(1.35, 0, 0), .lThigh: v(0.128, 0.15, 0.1),
            .lShin: v(-0.39, 0, 0), .lFoot: v(0.268, 0, -0.06), .rThigh: v(0.024, 0.12, 0.04),
            .rShin: v(-0.328, 0, 0), .rFoot: v(0.299, 0, -0.08)
        ])
        return c
    }

    private static func makeLookAround() -> RigClip {
        var c = RigClip(duration: 5, loops: true, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.25, .smooth, pose: pLookl)
        c.key(0.45, .smooth, pose: pLookl)
        c.key(0.6, .smooth, pose: pStand)
        c.key(0.75, .smooth, pose: pLookr)
        c.key(0.9, .smooth, pose: pLookr)
        return c
    }

    private static func makeKneel() -> RigClip {
        var c = RigClip(duration: 1, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.5, .smooth, h: v(0, -0.42, -0.05), [
            .hips: v(0, 0.1, 0), .spine: v(0.12, 0, 0), .chest: v(0.1, 0, 0),
            .neck: v(0.15, 0, 0), .head: v(0.3, 0, 0), .lUpperArm: v(0.55, -0.2, 0.25),
            .lForearm: v(1.1, 0, 0), .rUpperArm: v(0.15, 0, 0.12), .rForearm: v(0.3, 0, 0),
            .lThigh: v(1.5, 0.15, 0.08), .lShin: v(-1.966, 0, 0), .lFoot: v(0.466, 0, -0.006),
            .rThigh: v(-0.08, 0.1, 0.06), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.9, 0, 0)
        ])
        c.key(1, .smooth, h: v(0, -0.425, -0.05), [
            .hips: v(0, 0.1, 0), .spine: v(0.12, 0, 0), .chest: v(0.1, 0, 0),
            .neck: v(0.15, 0, 0), .head: v(0.35, 0, 0), .lUpperArm: v(0.55, -0.2, 0.25),
            .lForearm: v(1.1, 0, 0), .rUpperArm: v(0.15, 0, 0.12), .rForearm: v(0.3, 0, 0),
            .lThigh: v(1.5, 0.15, 0.08), .lShin: v(-1.966, 0, 0), .lFoot: v(0.466, 0, -0.006),
            .rThigh: v(-0.08, 0.1, 0.06), .rShin: v(-1.5, 0, 0), .rFoot: v(-0.9, 0, 0)
        ])
        return c
    }

    private static func makeCelebrate() -> RigClip {
        var c = RigClip(duration: 1.6, loops: false, breathing: 1)
        c.key(0, .smooth, pose: pStand)
        c.key(0.15, .snap, pose: pCeUp)
        c.key(0.3, .smooth, pose: pCePump)
        c.key(0.45, .snap, pose: pCeUp)
        c.key(0.6, .smooth, pose: pCePump)
        c.key(0.75, .snap, pose: pCeUp)
        c.key(1, .smooth, pose: pCeUp)
        return c
    }
}

// =====================================================================
// MARK: - Character/CharacterRig.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – CharacterRig
//  Prozedurale, stilisiert-realistische Figur aus SceneKit-Grundkörpern:
//  Gelenkhierarchie, PBR-Materialien aus FighterLook, Accessoires mit
//  Sekundärbewegung (Umhang, Schal, Kittel, Ranken), Materialzustände
//  (verkohlt / gefroren / Schatten), Treffer-Blitz und Zerstückelung.
//
//  Hierarchie: node (Wurzel an den Füßen, Blick +Z) → hips → spine → chest → neck → head,
//  chest → Oberarme → Unterarme → Hände, hips → Oberschenkel → Schienbeine → Füße.
//  Jedes Gelenk dreht um seinen Gelenkpunkt; die Geometrie hängt als Kind darunter.
// =====================================================================

enum Limb {
    case head, leftArm, rightArm, leftLeg, rightLeg, upperBody
}

enum RigMaterialState {
    case normal, charred, frozen, shadow
}

final class CharacterRig {

    // MARK: - Öffentliche API

    /// Wurzel an den Füßen; die Figur schaut lokal nach +Z.
    let node: SCNNode
    private(set) var look: FighterLook
    /// Körpergröße in Metern.
    let height: Float
    private(set) var currentClip: AnimClip = .idle
    /// Wird additiv auf die Clip-Pose gelegt (z.B. Lehnen beim Schwingen). hipsOffset in Metern (1,80-m-Figur).
    var proceduralOverride: Pose?

    /// 0...1 – bei One-Shots der Fortschritt, bei Schleifen die Phase im Zyklus.
    var clipProgress: Float {
        let d = Swift.max(0.0001, clipDuration)
        if clipData.loops {
            let p = (clipTime / d).truncatingRemainder(dividingBy: 1)
            return p.isFinite ? Swift.max(0, p) : 0
        }
        return Swift.min(1, Swift.max(0, clipTime / d))
    }

    /// true, sobald ein One-Shot-Clip durchgelaufen ist (hält dann das letzte Bild). Schleifen: immer false.
    var clipFinished: Bool {
        return !clipData.loops && clipTime >= clipDuration
    }

    var isDismembered: Bool {
        return !detachedLimbs.isEmpty || pelvisDetached
    }

    // MARK: - Interne Typen

    private struct Dims {
        var s: Float = 1        // Körpergröße / 1,80 m
        var ws: Float = 1       // Schulter-/Brustbreite
        var hw: Float = 1       // Hüftbreite
        var ts: Float = 1       // Dicke der Gliedmaßen
        var td: Float = 1       // Rumpftiefe
        var head: Float = 1     // Kopfgröße
        var belly: Float = 1
        var armSpread: Float = 0  // zusätzliche Abspreizung der Arme (breite Figuren)
    }

    private enum MatRole {
        case body       // reagiert auf Blitz und Materialzustände
        case glow       // leuchtende Details (Augen, Linien)
    }

    private final class MatEntry {
        let mat: SCNMaterial
        let role: MatRole
        let diffuse: UIColor
        let rough: Float
        let metal: Float
        let emission: UIColor
        let emissionIntensity: Float

        init(mat: SCNMaterial, role: MatRole, diffuse: UIColor, rough: Float, metal: Float,
             emission: UIColor, emissionIntensity: Float) {
            self.mat = mat
            self.role = role
            self.diffuse = diffuse
            self.rough = rough
            self.metal = metal
            self.emission = emission
            self.emissionIntensity = emissionIntensity
        }
    }

    private struct Palette {
        let suit: SCNMaterial
        let panel: SCNMaterial
        let skin: SCNMaterial
        let glove: SCNMaterial
        let boot: SCNMaterial
        let dark: SCNMaterial
        let glow: SCNMaterial
        let lens: SCNMaterial
        let metal: SCNMaterial
        let gold: SCNMaterial
        let hair: SCNMaterial
        let web: SCNMaterial
        let cyber: SCNMaterial
        let cloth: SCNMaterial
        let coat: SCNMaterial
        let blade: SCNMaterial
        let horn: SCNMaterial
        let eyeWhite: SCNMaterial
        let lips: SCNMaterial
        let headMat: SCNMaterial
        let superSuit: Bool     // Heldenanzug-Details (Seitenpaneele, Knieschoner, Stulpen)
    }

    /// Kette aus Segmenten, die per Schwerkraft + Fahrtwind + Flattern nachschwingt (Umhang, Schal, Kittel).
    private final class SwayChain {
        let anchor: SCNNode
        let segments: [SCNNode]
        let ref: SCNNode
        let side: Float          // -1: hinter dem Körper halten, +1: davor, 0: frei
        let minOffset: Float
        let stiffness: Float
        let drag: Float
        let flutter: Float
        let phase: Float
        var lastPos: SIMD3<Float>?
        var vel = SIMD3<Float>(0, 0, 0)

        init(anchor: SCNNode, segments: [SCNNode], ref: SCNNode, side: Float, minOffset: Float,
             stiffness: Float, drag: Float, flutter: Float, phase: Float) {
            self.anchor = anchor
            self.segments = segments
            self.ref = ref
            self.side = side
            self.minOffset = minOffset
            self.stiffness = stiffness
            self.drag = drag
            self.flutter = flutter
            self.phase = phase
        }

        func reset() {
            lastPos = nil
            vel = SIMD3<Float>(0, 0, 0)
        }

        func step(dt: Float, time: Float) {
            guard dt > 0 else { return }
            let p = anchor.simdWorldPosition
            if let lp = lastPos {
                let raw = (p - lp) / dt
                if raw.x.isFinite && raw.y.isFinite && raw.z.isFinite && simd_length(raw) < 80 {
                    vel = damp3(vel, raw, lambda: 12, dt: dt)
                }
            }
            lastPos = p
            let speed = simd_length(vel)
            let refQ = ref.simdWorldOrientation
            let refInv = refQ.inverse
            let gravity = SIMD3<Float>(0, -9.8, 0)
            for i in 0..<segments.count {
                let seg = segments[i]
                guard let parent = seg.parent else { continue }
                let fi = Float(i)
                let t = time * (5.5 + fi * 0.45) + phase + fi * 0.75
                let fl = flutter * (0.3 + Swift.min(speed, 14) / 14)
                var wind = -vel * drag
                wind += SIMD3<Float>(sinf(t), 0.4 * cosf(t * 1.37), sinf(t * 0.71 + 1.3)) * (fl * 3.0)
                var dirW = safeNormalize(gravity + wind, fallback: SIMD3<Float>(0, -1, 0))
                if side != 0 {
                    var dr = refInv.act(dirW)
                    if side < 0 {
                        dr.z = Swift.min(dr.z, -minOffset)
                    } else {
                        dr.z = Swift.max(dr.z, minOffset)
                    }
                    dr.y = Swift.min(dr.y, 0.3)
                    dirW = refQ.act(safeNormalize(dr, fallback: SIMD3<Float>(0, -1, 0)))
                }
                let local = parent.simdWorldOrientation.inverse.act(dirW)
                let target = CharacterRig.rotation(from: SIMD3<Float>(0, -1, 0), to: local)
                let k = 1 - expf(-stiffness * Swift.max(0.35, 1 - fi * 0.09) * dt)
                seg.simdOrientation = simd_slerp(seg.simdOrientation, target, Swift.max(0, Swift.min(1, k)))
            }
        }
    }

    /// Wellenförmig bewegte Ranke (schwarze Tentakel).
    private final class Tendril {
        let segments: [SCNNode]
        let base: [SIMD3<Float>]
        let phase: Float
        let freq: Float
        let amp: Float

        init(segments: [SCNNode], base: [SIMD3<Float>], phase: Float, freq: Float, amp: Float) {
            self.segments = segments
            self.base = base
            self.phase = phase
            self.freq = freq
            self.amp = amp
        }

        func step(time: Float) {
            for i in 0..<segments.count {
                let fi = Float(i)
                let w = time * freq + phase + fi * 0.85
                let b = i < base.count ? base[i] : SIMD3<Float>(0, 0, 0)
                let e = b + SIMD3<Float>(sinf(w) * amp, 0, cosf(w * 0.83 + fi) * amp * 0.8)
                segments[i].simdOrientation = CharacterRig.quatYXZ(e)
            }
        }
    }

    // MARK: - Zustand

    private let quality: QualityPreset
    private var dims = Dims()
    private var joints: [Joint: SCNNode] = [:]
    private var restPositions: [Joint: SIMD3<Float>] = [:]
    private var visRoots: [Joint: SCNNode] = [:]

    // Animation
    private var clipData: RigClip = RigAnimLibrary.clip(.idle)
    private var clipDuration: Float = 3
    private var clipTime: Float = 0
    private var fromPose = Pose()
    private var blendTime: Float = 0
    private var blendDuration: Float = 0
    private var lastBasePose = Pose()
    private var animTime: Float = 0
    private var hasUpdated = false

    // Sekundärbewegung / Accessoires
    private var swayChains: [SwayChain] = []
    private var tendrils: [Tendril] = []
    private var flameLights: [SCNLight] = []
    private var flameLightBase: CGFloat = 0

    // Materialien
    private var matEntries: [MatEntry] = []
    private var matState: RigMaterialState = .normal
    private var matAmount: Float = 0
    private var crackHeat: Float = 0
    private var flashAmount: Float = 0
    private var flashColor: UIColor = .white
    private var rimInstalled = false

    // Zerstückelung
    private var detachedLimbs: Set<Limb> = []
    private var stumpNodes: [SCNNode] = []
    private var ownDebris: [SCNNode] = []
    private static var liveDebris: [SCNNode] = []
    private static let maxLiveDebris = 20

    // Gemeinsame Bildressourcen
    private static var weaveCache: UIImage?
    private static var crackCache: UIImage?

    private static let charColor = UIColor(red: 0.035, green: 0.03, blue: 0.028, alpha: 1)
    private static let iceColor = UIColor(red: 0.72, green: 0.88, blue: 1.0, alpha: 1)
    private static let iceGlow = UIColor(red: 0.25, green: 0.75, blue: 1.0, alpha: 1)
    private static let shadowColor = UIColor(red: 0.012, green: 0.01, blue: 0.018, alpha: 1)
    private static let shadowGlow = UIColor(red: 0.55, green: 0.12, blue: 1.0, alpha: 1)

    private static let rimShaderSource = """
    #pragma arguments
    float rigRimAmount;
    float rigRimHue;
    #pragma body
    float rigRimTerm = 1.0 - saturate(dot(normalize(_surface.view), normalize(_surface.normal)));
    float3 rigRimColor = mix(float3(0.55, 0.12, 1.0), float3(0.45, 0.85, 1.0), rigRimHue);
    _surface.emission.rgb += rigRimColor * (rigRimTerm * rigRimTerm * rigRimTerm) * rigRimAmount;
    """

    // MARK: - Init

    init(look: FighterLook, quality: QualityPreset) {
        self.look = look
        self.quality = quality
        var h = look.height
        if !h.isFinite { h = 1.8 }
        self.height = Swift.max(1.4, Swift.min(2.7, h))
        self.node = SCNNode()
        node.name = "rig.root"
        dims = CharacterRig.makeDims(look: look, height: height)
        buildSkeleton()
        buildVisuals()
        clipData = RigAnimLibrary.clip(.idle)
        clipDuration = clipData.duration
        let first = clipData.sample(0)
        lastBasePose = first
        fromPose = first
        applyPose(first)
    }

    // MARK: - Gelenke

    func joint(_ j: Joint) -> SCNNode {
        return joints[j] ?? node
    }

    /// Weltposition eines Gelenks. Kopf = Kopfmitte, Hände = Faustmitte, Füße = Fußmitte, sonst Gelenkpunkt.
    func worldPosition(of j: Joint) -> SIMD3<Float> {
        guard let n = joints[j] else { return node.simdWorldPosition }
        let s = dims.s
        switch j {
        case .head:
            return n.simdConvertPosition(headCenterLocal, to: nil)
        case .lHand, .rHand:
            return n.simdConvertPosition(SIMD3<Float>(0, -0.065 * s, 0), to: nil)
        case .lFoot, .rFoot:
            return n.simdConvertPosition(SIMD3<Float>(0, -0.045 * s, 0.06 * s), to: nil)
        default:
            return n.simdWorldPosition
        }
    }

    // MARK: - Animation

    /// Spielt einen Clip. Schleifen laufen endlos, One-Shots einmal (duration skaliert sie) und halten das letzte Bild.
    /// Derselbe Clip ohne restart ändert nur die Länge (z.B. Lauftempo). blend = Überblendzeit in Sekunden.
    func play(_ clip: AnimClip, duration: Float? = nil, restart: Bool = false, blend: Float = 0.08) {
        let data = RigAnimLibrary.clip(clip)
        var dur = data.duration
        if let d = duration, d.isFinite, d > 0.01 {
            dur = d
        }
        if clip == currentClip && !restart {
            if data.loops {
                let phase = clipTime / Swift.max(0.0001, clipDuration)
                clipDuration = dur
                clipTime = phase * dur
            } else if duration != nil {
                let progress = clipTime / Swift.max(0.0001, clipDuration)
                clipDuration = dur
                clipTime = progress * dur
            }
            return
        }
        fromPose = lastBasePose
        blendTime = 0
        var b = blend
        if !b.isFinite || b < 0 { b = 0 }
        blendDuration = hasUpdated ? b : 0
        currentClip = clip
        clipData = data
        clipDuration = dur
        clipTime = 0
        evaluateAndApply()
    }

    /// Pro Frame aufrufen (dt bereits zeitskaliert für Zeitlupe/Hit-Stop).
    func update(dt: Float) {
        var d = dt
        if !d.isFinite || d < 0 { d = 0 }
        d = Swift.min(d, 0.1)
        animTime += d
        clipTime += d
        blendTime += d
        evaluateAndApply()
        if d > 0 {
            for c in swayChains { c.step(dt: d, time: animTime) }
        }
        for t in tendrils { t.step(time: animTime) }
        updateFlames()
        updateMaterialTimers(d)
        hasUpdated = true
    }

    private func sampleClip() -> Pose {
        let d = Swift.max(0.0001, clipDuration)
        if clipData.loops {
            return clipData.sample(clipTime / d)
        }
        return clipData.sample(Swift.min(1, clipTime / d))
    }

    private func evaluateAndApply() {
        var base = sampleClip()
        if blendDuration > 0.0001 && blendTime < blendDuration {
            let u = Swift.max(0, Swift.min(1, blendTime / blendDuration))
            let sm = u * u * (3 - 2 * u)
            base = Pose.rigBlendShortest(fromPose, base, sm)
        }
        lastBasePose = base
        var outPose = base
        // Atmung (prozedural, additiv)
        let br = clipData.breathing
        if br > 0.001 {
            let w = sinf(animTime * 2 * Float.pi / 3.4) * br
            outPose[.chest] = outPose[.chest] + SIMD3<Float>(-0.018 * w, 0, 0)
            outPose[.spine] = outPose[.spine] + SIMD3<Float>(0.006 * w, 0, 0)
            outPose[.neck] = outPose[.neck] + SIMD3<Float>(0.012 * w, 0, 0)
            outPose[.lUpperArm] = outPose[.lUpperArm] + SIMD3<Float>(0, 0, 0.012 * w)
            outPose[.rUpperArm] = outPose[.rUpperArm] + SIMD3<Float>(0, 0, 0.012 * w)
        }
        if let o = proceduralOverride {
            outPose = outPose.rigAdding(o)
        }
        applyPose(outPose)
    }

    private func applyPose(_ pose: Pose) {
        let rest = RigAnimLibrary.restPose
        let spread = dims.armSpread
        for j in Joint.allCases {
            guard let n = joints[j] else { continue }
            var r = rest[j] + pose[j]
            if spread != 0 && (j == .lUpperArm || j == .rUpperArm) {
                r.z += spread
            }
            let e = j.rigRawEuler(r)
            if !(e.x.isFinite && e.y.isFinite && e.z.isFinite) { continue }
            n.simdOrientation = CharacterRig.quatYXZ(e)
        }
        if let hn = joints[.hips], let hp = restPositions[.hips] {
            let off = pose.hipsOffset * dims.s
            if off.x.isFinite && off.y.isFinite && off.z.isFinite {
                hn.simdPosition = hp + off
            }
        }
    }

    // MARK: - Treffer-Blitz & Materialzustände

    /// Kurzer emissiver Blitz (klingt in ~0,12 s ab).
    func flashHit(color: UIColor = .white) {
        flashColor = color
        flashAmount = 1
        refreshMaterials()
    }

    /// amount 0...1 blendet vom normalen Aussehen zum Zustand.
    func setMaterialState(_ s: RigMaterialState, amount: Float) {
        var a = amount.isFinite ? amount : 0
        a = Swift.max(0, Swift.min(1, a))
        if s == .charred {
            if matState != .charred {
                crackHeat = 1
            } else if a > matAmount + 0.05 {
                crackHeat = Swift.max(crackHeat, 0.85)
            }
        }
        matState = s
        matAmount = (s == .normal) ? 0 : a
        if (s == .frozen || s == .shadow) && a > 0 {
            installRimShader()
        }
        refreshMaterials()
    }

    /// Neues Aussehen (z.B. Anzug wird schwarz): baut Geometrie, Materialien und Accessoires neu auf.
    func setLook(_ newLook: FighterLook) {
        look = newLook
        dims = CharacterRig.makeDims(look: newLook, height: height)
        buildVisuals()
        applyPose(lastBasePose)
    }

    private func updateMaterialTimers(_ dt: Float) {
        var dirty = false
        if flashAmount > 0 {
            flashAmount = Swift.max(0, flashAmount - dt / 0.12)
            dirty = true
        }
        if matState == .charred && matAmount > 0 && crackHeat > 0.14 {
            crackHeat = Swift.max(0.14, crackHeat - dt * 0.22)
            dirty = true
        }
        if dirty {
            refreshMaterials()
        }
    }

    private func installRimShader() {
        if rimInstalled { return }
        rimInstalled = true
        for e in matEntries where e.role == .body {
            e.mat.shaderModifiers = [.surface: CharacterRig.rimShaderSource]
            e.mat.setValue(NSNumber(value: Float(0)), forKey: "rigRimAmount")
            e.mat.setValue(NSNumber(value: Float(0)), forKey: "rigRimHue")
        }
    }

    private func refreshMaterials() {
        let a = matAmount
        let flash = flashAmount
        let cracks: UIImage? = (matState == .charred && a > 0.001) ? CharacterRig.crackTexture() : nil
        for e in matEntries {
            var diffuse = e.diffuse
            var rough = e.rough
            var metal = e.metal
            var emis: Any = e.emission
            var eInt = e.emissionIntensity
            var rim: Float = 0
            var rimHue: Float = 0
            if a > 0.001 {
                switch matState {
                case .normal:
                    break
                case .charred:
                    diffuse = e.diffuse.blended(with: CharacterRig.charColor, t: CGFloat(a))
                    if e.role == .body {
                        rough = lerpf(e.rough, 1, a)
                        metal = lerpf(e.metal, 0.02, a)
                        let heat = crackHeat * a
                        if heat > 0.01, let c = cracks {
                            emis = c
                            eInt = 2.6 * heat
                        }
                    } else {
                        eInt = e.emissionIntensity * (1 - a)
                    }
                case .frozen:
                    if e.role == .body {
                        diffuse = e.diffuse.blended(with: CharacterRig.iceColor, t: CGFloat(a * 0.85))
                        rough = lerpf(e.rough, 0.15, a)
                        metal = lerpf(e.metal, 0.12, a)
                        emis = CharacterRig.iceGlow
                        eInt = 0.3 * a
                        rim = 1.2 * a
                        rimHue = 1
                    }
                case .shadow:
                    if e.role == .body {
                        diffuse = e.diffuse.blended(with: CharacterRig.shadowColor, t: CGFloat(a))
                        rough = lerpf(e.rough, 0.1, a)
                        metal = lerpf(e.metal, 0.35, a)
                        emis = CharacterRig.shadowGlow
                        eInt = 0.12 * a
                        rim = 1.8 * a
                        rimHue = 0
                    } else {
                        emis = e.emission.blended(with: CharacterRig.shadowGlow, t: CGFloat(a))
                    }
                }
            }
            if flash > 0.001 && e.role == .body {
                emis = flashColor
                eInt = Swift.max(eInt, 3.0 * flash)
            }
            e.mat.diffuse.contents = diffuse
            e.mat.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, rough)))
            e.mat.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metal)))
            e.mat.emission.contents = emis
            e.mat.emission.intensity = CGFloat(eInt)
            if rimInstalled && e.role == .body {
                e.mat.setValue(NSNumber(value: rim), forKey: "rigRimAmount")
                e.mat.setValue(NSNumber(value: rimHue), forKey: "rigRimHue")
            }
        }
    }

    private func updateFlames() {
        if flameLights.isEmpty { return }
        let t = animTime
        let f1: Float = 0.14 * sinf(t * 17.0)
        let f2: Float = 0.08 * sinf(t * 31.0 + 1.3)
        let f: Float = 0.78 + f1 + f2
        let hidden = isDismembered && detachedLimbs.contains(.upperBody)
        for l in flameLights {
            l.intensity = hidden ? 0 : flameLightBase * CGFloat(f)
        }
    }

    // MARK: - Proportionen & Skelett

    private static func makeDims(look: FighterLook, height: Float) -> Dims {
        var d = Dims()
        d.s = height / 1.8
        switch look.build {
        case .lean:
            d.ws = 0.93; d.hw = 0.95; d.ts = 0.86; d.td = 0.92; d.head = 1.0; d.belly = 0.95; d.armSpread = 0
        case .athletic:
            d.ws = 1.0; d.hw = 1.0; d.ts = 1.0; d.td = 1.0; d.head = 1.0; d.belly = 1.0; d.armSpread = 0
        case .heavy:
            d.ws = 1.18; d.hw = 1.12; d.ts = 1.32; d.td = 1.2; d.head = 0.96; d.belly = 1.15; d.armSpread = 0.14
        case .giant:
            d.ws = 1.26; d.hw = 1.15; d.ts = 1.4; d.td = 1.22; d.head = 0.9; d.belly = 1.05; d.armSpread = 0.16
        }
        return d
    }

    /// Gelenkpositionen relativ zum Elterngelenk (Referenz 1,80 m, skaliert).
    private func layoutPositions() -> [Joint: SIMD3<Float>] {
        let d = dims
        let s = d.s
        let shoulderX = 0.205 * s * d.ws
        let hipX = 0.092 * s * d.hw
        var p: [Joint: SIMD3<Float>] = [:]
        p[.hips] = SIMD3<Float>(0, 0.954 * s, 0)
        p[.spine] = SIMD3<Float>(0, 0.10 * s, 0)
        p[.chest] = SIMD3<Float>(0, 0.21 * s, 0)
        p[.neck] = SIMD3<Float>(0, 0.225 * s, -0.01 * s)
        p[.head] = SIMD3<Float>(0, 0.085 * s, 0.01 * s)
        p[.lUpperArm] = SIMD3<Float>(shoulderX, 0.195 * s, -0.01 * s)
        p[.rUpperArm] = SIMD3<Float>(-shoulderX, 0.195 * s, -0.01 * s)
        p[.lForearm] = SIMD3<Float>(0, -0.29 * s, 0)
        p[.rForearm] = SIMD3<Float>(0, -0.29 * s, 0)
        p[.lHand] = SIMD3<Float>(0, -0.26 * s, 0)
        p[.rHand] = SIMD3<Float>(0, -0.26 * s, 0)
        p[.lThigh] = SIMD3<Float>(hipX, -0.06 * s, 0)
        p[.rThigh] = SIMD3<Float>(-hipX, -0.06 * s, 0)
        p[.lShin] = SIMD3<Float>(0, -0.405 * s, 0)
        p[.rShin] = SIMD3<Float>(0, -0.405 * s, 0)
        p[.lFoot] = SIMD3<Float>(0, -0.408 * s, 0)
        p[.rFoot] = SIMD3<Float>(0, -0.408 * s, 0)
        return p
    }

    private func buildSkeleton() {
        restPositions = layoutPositions()
        for j in Joint.allCases {
            let n = SCNNode()
            n.name = "rig." + j.rawValue
            n.simdPosition = restPositions[j] ?? SIMD3<Float>(0, 0, 0)
            if let p = j.rigParent, let pn = joints[p] {
                pn.addChildNode(n)
            } else {
                node.addChildNode(n)
            }
            joints[j] = n
        }
    }

    /// Kopfmitte im Kopfgelenk-Raum.
    private var headCenterLocal: SIMD3<Float> {
        let k: Float = dims.s * dims.head
        return SIMD3<Float>(0, 0.105, 0.005) * k
    }

    private var headRadius: Float {
        return 0.105 * dims.s * dims.head
    }

    private var headScale: SIMD3<Float> {
        return SIMD3<Float>(0.86 + (dims.ws - 1) * 0.15, 1.06, 1.0)
    }

    /// Brustkorb-Ellipsoid (Chest-Raum) – gemeinsam für Geometrie und Netzlinien.
    private var chestSurface: WebSurface {
        let d = dims
        return WebSurface(c: pv(0, 0.085, -0.005), r: 0.165 * d.s, k: SIMD3<Float>(1.1 * d.ws, 0.98, 0.7 * d.td))
    }

    /// Rücken/Seitenpaneel-Ellipsoid (Chest-Raum).
    private var latsSurface: WebSurface {
        let d = dims
        return WebSurface(c: pv(0, 0.06, -0.03 * d.td), r: 0.165 * d.s, k: SIMD3<Float>(1.135 * d.ws, 0.92, 0.6 * d.td))
    }

    // MARK: - Mathe-Helfer

    /// Euler (Posen-Raum bereits in Rohwinkel umgerechnet) → Quaternion, Reihenfolge Roll → Pitch → Yaw.
    private static func quatYXZ(_ e: SIMD3<Float>) -> simd_quatf {
        let qx = simd_quatf(angle: e.x, axis: SIMD3<Float>(1, 0, 0))
        let qy = simd_quatf(angle: e.y, axis: SIMD3<Float>(0, 1, 0))
        let qz = simd_quatf(angle: e.z, axis: SIMD3<Float>(0, 0, 1))
        return qy * qx * qz
    }

    /// Kürzeste Drehung, die Richtung a auf Richtung b abbildet (robust bei (anti)parallelen Vektoren).
    private static func rotation(from a: SIMD3<Float>, to b: SIMD3<Float>) -> simd_quatf {
        let identity = simd_quatf(angle: 0, axis: SIMD3<Float>(0, 1, 0))
        let la = simd_length(a)
        let lb = simd_length(b)
        if !(la > 1e-6) || !(lb > 1e-6) || !la.isFinite || !lb.isFinite { return identity }
        let u = a / la
        let v = b / lb
        let d = simd_dot(u, v)
        if d > 0.99999 { return identity }
        if d < -0.99999 {
            var axis = simd_cross(u, SIMD3<Float>(1, 0, 0))
            if simd_length(axis) < 1e-4 { axis = simd_cross(u, SIMD3<Float>(0, 0, 1)) }
            return simd_quatf(angle: Float.pi, axis: simd_normalize(axis))
        }
        return simd_quatf(from: u, to: v)
    }

    // MARK: - Materialien

    private func registerMaterial(_ color: UIColor, rough: Float, metal: Float, emission: UIColor? = nil,
                                  emissionIntensity: Float = 1, role: MatRole = .body, doubleSided: Bool = false,
                                  normalMap: UIImage? = nil, normalTile: Float = 6) -> SCNMaterial {
        let r = Swift.max(0.02, Swift.min(1, rough))
        let mt = Swift.max(0, Swift.min(1, metal))
        let mat = Render.pbr(color, roughness: r, metalness: mt, emission: emission, emissionIntensity: emissionIntensity)
        mat.isDoubleSided = doubleSided
        if let n = normalMap {
            mat.normal.contents = n
            mat.normal.intensity = 0.6
            mat.normal.wrapS = .repeat
            mat.normal.wrapT = .repeat
            mat.normal.contentsTransform = SCNMatrix4MakeScale(normalTile, normalTile, 1)
        }
        let entry = MatEntry(mat: mat, role: role, diffuse: color, rough: r, metal: mt,
                             emission: emission ?? UIColor.black,
                             emissionIntensity: emission == nil ? 0 : emissionIntensity)
        matEntries.append(entry)
        return mat
    }

    private func makePalette() -> Palette {
        let L = look
        let rough = Swift.max(0.05, Swift.min(1, L.roughness.isFinite ? L.roughness : 0.5))
        let metal = Swift.max(0, Swift.min(1, L.metalness.isFinite ? L.metalness : 0))
        let weave: UIImage? = quality == .performance ? nil : CharacterRig.weaveNormal()
        let superSuit = L.hasMask || L.eyeStyle != .human

        let suit = registerMaterial(L.primaryColor, rough: rough, metal: metal, normalMap: weave)
        let panel = registerMaterial(L.secondaryColor, rough: Swift.max(0.08, rough * 0.7), metal: Swift.min(1, metal + 0.15))
        let skin = registerMaterial(L.skinColor, rough: 0.5, metal: 0)
        let dark = registerMaterial(UIColor(white: 0.045, alpha: 1), rough: 0.45, metal: 0.35)
        let glow = registerMaterial(L.glowColor.withBrightness(0.35), rough: 0.35, metal: 0,
                                    emission: L.glowColor, emissionIntensity: 2.6, role: .glow)
        let lensEmission = UIColor.white.blended(with: L.glowColor, t: 0.12)
        let lens = registerMaterial(UIColor(white: 0.95, alpha: 1), rough: 0.18, metal: 0,
                                    emission: lensEmission, emissionIntensity: 1.5, role: .glow)
        let metalMat = registerMaterial(UIColor(white: 0.6, alpha: 1), rough: 0.28, metal: 1)
        let gold = registerMaterial(UIColor(red: 0.93, green: 0.72, blue: 0.32, alpha: 1), rough: 0.22, metal: 1)
        let hairColor = L.hairColor ?? UIColor(red: 0.12, green: 0.08, blue: 0.05, alpha: 1)
        let hair = registerMaterial(hairColor, rough: 0.72, metal: 0)
        let webEmission = UIColor(red: 0.62, green: 0.66, blue: 0.76, alpha: 1).blended(with: L.glowColor, t: 0.25)
        let web = registerMaterial(UIColor(red: 0.1, green: 0.1, blue: 0.12, alpha: 1), rough: 0.32, metal: 0.8,
                                   emission: webEmission, emissionIntensity: 0.55, role: .glow, doubleSided: true)
        let cyber = registerMaterial(UIColor(red: 0.22, green: 0.23, blue: 0.26, alpha: 1), rough: 0.3, metal: 1)
        let cloth = registerMaterial(L.secondaryColor, rough: 0.82, metal: 0, doubleSided: true)
        let coat = registerMaterial(UIColor(red: 0.9, green: 0.92, blue: 0.94, alpha: 1), rough: 0.78, metal: 0, doubleSided: true)
        let blade = registerMaterial(UIColor(red: 0.86, green: 0.88, blue: 0.92, alpha: 1), rough: 0.12, metal: 1)
        let hornColor = L.secondaryColor.blended(with: UIColor(red: 0.12, green: 0.1, blue: 0.09, alpha: 1), t: 0.55)
        let horn = registerMaterial(hornColor, rough: 0.42, metal: 0.2)
        let eyeWhite = registerMaterial(UIColor(white: 0.9, alpha: 1), rough: 0.2, metal: 0)
        let lipColor = L.skinColor.blended(with: UIColor(red: 0.55, green: 0.2, blue: 0.2, alpha: 1), t: 0.35)
        let lips = registerMaterial(lipColor, rough: 0.45, metal: 0)

        return Palette(suit: suit, panel: panel, skin: skin,
                       glove: superSuit ? panel : skin,
                       boot: superSuit ? panel : dark,
                       dark: dark, glow: glow, lens: lens, metal: metalMat, gold: gold, hair: hair, web: web,
                       cyber: cyber, cloth: cloth, coat: coat, blade: blade, horn: horn, eyeWhite: eyeWhite, lips: lips,
                       headMat: L.hasMask ? suit : skin, superSuit: superSuit)
    }

    /// Feines Rautengewebe als Normal-Map für den Anzug (einmal erzeugt).
    private static func weaveNormal() -> UIImage? {
        if let w = weaveCache { return w }
        let size = 128
        var bytes = [UInt8](repeating: 255, count: size * size * 4)
        func heightAt(_ x: Int, _ y: Int) -> Float {
            let fx = Float((x + size) % size) / Float(size)
            let fy = Float((y + size) % size) / Float(size)
            let u = fx * 2 * Float.pi * 8
            let v = fy * 2 * Float.pi * 8
            let a = abs(sinf((u + v) * 0.5))
            let b = abs(sinf((u - v) * 0.5))
            return a * b
        }
        let strength: Float = 2.2
        for y in 0..<size {
            for x in 0..<size {
                let dx = heightAt(x + 1, y) - heightAt(x - 1, y)
                let dy = heightAt(x, y + 1) - heightAt(x, y - 1)
                let n = simd_normalize(SIMD3<Float>(-dx * strength, -dy * strength, 1))
                let i = (y * size + x) * 4
                bytes[i] = UInt8(Swift.max(0, Swift.min(255, (n.x * 0.5 + 0.5) * 255)))
                bytes[i + 1] = UInt8(Swift.max(0, Swift.min(255, (n.y * 0.5 + 0.5) * 255)))
                bytes[i + 2] = UInt8(Swift.max(0, Swift.min(255, (n.z * 0.5 + 0.5) * 255)))
                bytes[i + 3] = 255
            }
        }
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let info = CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue)
        guard let provider = CGDataProvider(data: Data(bytes) as CFData),
              let cg = CGImage(width: size, height: size, bitsPerComponent: 8, bitsPerPixel: 32,
                               bytesPerRow: size * 4, space: colorSpace, bitmapInfo: info,
                               provider: provider, decode: nil, shouldInterpolate: true,
                               intent: .defaultIntent) else {
            return nil
        }
        let img = UIImage(cgImage: cg)
        weaveCache = img
        return img
    }

    /// Glühende Risse (Emissionstextur für "verkohlt").
    private static func crackTexture() -> UIImage? {
        if let c = crackCache { return c }
        let side: CGFloat = 256
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: side, height: side), format: format)
        var rng = SeededRandom(seed: 0xC4A2_17)
        var paths: [[CGPoint]] = []
        for _ in 0..<22 {
            var p = CGPoint(x: CGFloat(rng.float(0, 256)), y: CGFloat(rng.float(0, 256)))
            var ang = rng.float(0, Float.pi * 2)
            var pts: [CGPoint] = [p]
            let steps = rng.int(5, 12)
            for _ in 0..<steps {
                ang += rng.float(-0.8, 0.8)
                let len = CGFloat(rng.float(8, 22))
                p = CGPoint(x: p.x + CGFloat(cosf(ang)) * len, y: p.y + CGFloat(sinf(ang)) * len)
                pts.append(p)
                if rng.chance(0.18) {
                    let bAng = ang + rng.float(-1.4, 1.4)
                    let bLen = CGFloat(rng.float(10, 26))
                    paths.append([p, CGPoint(x: p.x + CGFloat(cosf(bAng)) * bLen, y: p.y + CGFloat(sinf(bAng)) * bLen)])
                }
            }
            paths.append(pts)
        }
        let img = renderer.image { ctx in
            let cg = ctx.cgContext
            cg.setFillColor(UIColor.black.cgColor)
            cg.fill(CGRect(x: 0, y: 0, width: side, height: side))
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            // weicher Glutschein
            cg.setStrokeColor(UIColor(red: 0.7, green: 0.12, blue: 0.0, alpha: 0.45).cgColor)
            cg.setLineWidth(7)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
            // heller Kern
            cg.setStrokeColor(UIColor(red: 1.0, green: 0.55, blue: 0.12, alpha: 1).cgColor)
            cg.setLineWidth(2.2)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
            cg.setStrokeColor(UIColor(red: 1.0, green: 0.9, blue: 0.6, alpha: 0.9).cgColor)
            cg.setLineWidth(0.8)
            for pts in paths {
                cg.addLines(between: pts)
                cg.strokePath()
            }
        }
        crackCache = img
        return img
    }

    // MARK: - Geometrie-Helfer

    private var segSphere: Int {
        switch quality {
        case .ultra: return 40
        case .balanced: return 28
        case .performance: return 18
        }
    }

    private var segRadial: Int {
        switch quality {
        case .ultra: return 36
        case .balanced: return 24
        case .performance: return 14
        }
    }

    private var segCap: Int {
        switch quality {
        case .ultra: return 14
        case .balanced: return 9
        case .performance: return 5
        }
    }

    private var particleScale: Float {
        switch quality {
        case .ultra: return 1
        case .balanced: return 0.7
        case .performance: return 0.4
        }
    }

    /// Referenzmaße (1,80 m) → skaliert.
    private func pv(_ x: Float, _ y: Float, _ z: Float) -> SIMD3<Float> {
        return SIMD3<Float>(x, y, z) * dims.s
    }

    /// Container für die Geometrie eines Gelenks (wird bei setLook komplett ersetzt).
    private func container(_ j: Joint) -> SCNNode {
        if let c = visRoots[j] { return c }
        let c = SCNNode()
        c.name = "rig.vis"
        joint(j).addChildNode(c)
        visRoots[j] = c
        return c
    }

    @discardableResult
    private func ellipsoid(_ parent: SCNNode, _ c: SIMD3<Float>, _ r: Float, _ scale: SIMD3<Float>, _ m: SCNMaterial,
                           shadow: Bool = true, detail: Float = 1) -> SCNNode {
        let g = SCNSphere(radius: CGFloat(Swift.max(0.0005, r)))
        g.segmentCount = Swift.max(10, Int(Float(segSphere) * detail))
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        n.simdScale = scale
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func capsule(_ parent: SCNNode, _ a: SIMD3<Float>, _ b: SIMD3<Float>, _ r: Float, _ m: SCNMaterial,
                         shadow: Bool = true, detail: Float = 1) -> SCNNode {
        let d = b - a
        let len = simd_length(d)
        let rr = Swift.max(0.0005, r)
        let g = SCNCapsule(capRadius: CGFloat(rr), height: CGFloat(len + 2 * rr))
        g.radialSegmentCount = Swift.max(6, Int(Float(segRadial) * detail))
        g.capSegmentCount = Swift.max(3, Int(Float(segCap) * detail))
        g.heightSegmentCount = 1
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = (a + b) * 0.5
        n.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: d)
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func box(_ parent: SCNNode, _ c: SIMD3<Float>, _ size: SIMD3<Float>, chamfer: Float, _ m: SCNMaterial,
                     orient: simd_quatf? = nil, shadow: Bool = true) -> SCNNode {
        let smallest = Swift.min(size.x, Swift.min(size.y, size.z))
        let ch = Swift.max(0, Swift.min(chamfer, smallest * 0.49))
        let g = SCNBox(width: CGFloat(size.x), height: CGFloat(size.y), length: CGFloat(size.z), chamferRadius: CGFloat(ch))
        g.chamferSegmentCount = quality == .performance ? 2 : 4
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func cylinder(_ parent: SCNNode, _ c: SIMD3<Float>, r: Float, h: Float, _ m: SCNMaterial,
                          orient: simd_quatf? = nil, scale: SIMD3<Float>? = nil, shadow: Bool = true) -> SCNNode {
        let g = SCNCylinder(radius: CGFloat(Swift.max(0.0005, r)), height: CGFloat(Swift.max(0.0005, h)))
        g.radialSegmentCount = segRadial
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        if let sc = scale { n.simdScale = sc }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    /// Kegel, dessen Grundfläche bei `base` liegt und der entlang `dir` um h wächst.
    @discardableResult
    private func cone(_ parent: SCNNode, base: SIMD3<Float>, dir: SIMD3<Float>, r0: Float, r1: Float, h: Float,
                      _ m: SCNMaterial, shadow: Bool = true) -> SCNNode {
        let g = SCNCone(topRadius: CGFloat(Swift.max(0, r1)), bottomRadius: CGFloat(Swift.max(0.0005, r0)),
                        height: CGFloat(Swift.max(0.0005, h)))
        g.radialSegmentCount = Swift.max(8, segRadial / 2)
        g.materials = [m]
        let n = SCNNode(geometry: g)
        let dn = safeNormalize(dir, fallback: SIMD3<Float>(0, 1, 0))
        n.simdPosition = base + dn * (h * 0.5)
        n.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: dn)
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    @discardableResult
    private func torus(_ parent: SCNNode, _ c: SIMD3<Float>, ring: Float, pipe: Float, _ m: SCNMaterial,
                       orient: simd_quatf? = nil, scale: SIMD3<Float>? = nil, shadow: Bool = false) -> SCNNode {
        let g = SCNTorus(ringRadius: CGFloat(Swift.max(0.001, ring)), pipeRadius: CGFloat(Swift.max(0.0005, pipe)))
        g.ringSegmentCount = Swift.max(12, segRadial)
        g.pipeSegmentCount = quality == .performance ? 6 : 10
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.simdPosition = c
        if let q = orient { n.simdOrientation = q }
        if let sc = scale { n.simdScale = sc }
        n.castsShadow = shadow
        parent.addChildNode(n)
        return n
    }

    // MARK: - Linienmuster (Netzlinien als ein Mesh pro Gelenk)

    private struct WebSurface {
        let c: SIMD3<Float>     // Mittelpunkt
        let r: Float            // Radius
        let k: SIMD3<Float>     // Skalierung je Achse
    }

    private struct LimbEll {
        let c: SIMD3<Float>     // Mittelpunkt
        let e: SIMD3<Float>     // Halbachsen
    }

    /// Querschnitt einer Gliedmaße entlang -Y: Kapseln (yOben, yUnten, Radius) + Ellipsoide (Muskeln).
    private struct LimbShape {
        var caps: [SIMD3<Float>] = []
        var ells: [LimbEll] = []
    }

    private static func surfacePoint(_ e: WebSurface, _ u: SIMD3<Float>, off: Float) -> (p: SIMD3<Float>, n: SIMD3<Float>) {
        let un = safeNormalize(u)
        let p = e.c + SIMD3<Float>(un.x * e.k.x, un.y * e.k.y, un.z * e.k.z) * e.r
        let n = safeNormalize(SIMD3<Float>(un.x / e.k.x, un.y / e.k.y, un.z / e.k.z))
        return (p + n * off, n)
    }

    /// Flaches Band von a nach b, das auf der Oberfläche (Normale na/nb) liegt; Vorderseite zeigt nach außen.
    private static func ribbon(_ mb: inout MeshBuilder, _ a: SIMD3<Float>, _ na: SIMD3<Float>,
                               _ b: SIMD3<Float>, _ nb: SIMD3<Float>, width: Float) {
        let dir = b - a
        if simd_length_squared(dir) < 1e-10 { return }
        let n = safeNormalize(na + nb, fallback: na)
        let sideRaw = simd_cross(dir, n)
        let l = simd_length(sideRaw)
        if l < 1e-8 || !l.isFinite { return }
        let side = sideRaw / l * (width * 0.5)
        mb.addQuad(a - side, a + side, b + side, b - side, uvScale: 1)
    }

    /// Netz aus Speichen und (leicht durchhängenden) Ringen um einen Pol auf einem Ellipsoid.
    private func webPattern(_ mb: inout MeshBuilder, on e: WebSurface, pole: SIMD3<Float>, radials: Int, phase: Float,
                            theta0: Float, theta1: Float, rings: [Float], width: Float, off: Float) {
        let axisA = safeNormalize(pole)
        var refAxis = SIMD3<Float>(0, 1, 0)
        if abs(simd_dot(refAxis, axisA)) > 0.9 { refAxis = SIMD3<Float>(1, 0, 0) }
        let b1 = safeNormalize(simd_cross(axisA, refAxis))
        let b2 = simd_cross(axisA, b1)
        func dirAt(_ th: Float, _ ph: Float) -> SIMD3<Float> {
            let radial = b1 * cosf(ph) + b2 * sinf(ph)
            return axisA * cosf(th) + radial * sinf(th)
        }
        let spokes = Swift.max(3, radials)
        let steps = quality == .ultra ? 12 : 8
        for k in 0..<spokes {
            let ph = phase + Float(k) / Float(spokes) * 2 * Float.pi
            var prev = CharacterRig.surfacePoint(e, dirAt(theta0, ph), off: off)
            for i in 1...steps {
                let th = theta0 + (theta1 - theta0) * Float(i) / Float(steps)
                let cur = CharacterRig.surfacePoint(e, dirAt(th, ph), off: off)
                CharacterRig.ribbon(&mb, prev.p, prev.n, cur.p, cur.n, width: width)
                prev = cur
            }
        }
        let perSpoke = quality == .ultra ? 5 : 3
        let ringSteps = spokes * perSpoke
        for th in rings {
            var prev = CharacterRig.surfacePoint(e, dirAt(th, phase), off: off)
            for i in 1...ringSteps {
                let f = Float(i) / Float(ringSteps)
                let ph = phase + f * 2 * Float.pi
                let local = Float(i % perSpoke) / Float(perSpoke)
                let sag = 1 - 0.1 * sinf(local * Float.pi)
                let cur = CharacterRig.surfacePoint(e, dirAt(th * sag, ph), off: off)
                CharacterRig.ribbon(&mb, prev.p, prev.n, cur.p, cur.n, width: width)
                prev = cur
            }
        }
    }

    /// Abstand der Gliedmaßen-Oberfläche von der Y-Achse bei Höhe y in Richtung a (x = sin a, z = cos a).
    private static func limbRadius(_ shape: LimbShape, y: Float, a: Float) -> Float {
        var best: Float = 0
        for cp in shape.caps {
            let top = Swift.max(cp.x, cp.y)
            let bot = Swift.min(cp.x, cp.y)
            let r = cp.z
            var rr: Float = 0
            if y <= top && y >= bot {
                rr = r
            } else if y > top && y - top < r {
                let d = y - top
                rr = (r * r - d * d).squareRoot()
            } else if y < bot && bot - y < r {
                let d = bot - y
                rr = (r * r - d * d).squareRoot()
            }
            best = Swift.max(best, rr)
        }
        let sa = sinf(a)
        let ca = cosf(a)
        for el in shape.ells {
            let dy = (y - el.c.y) / el.e.y
            let kk = 1 - dy * dy
            if kk <= 0 { continue }
            let k = kk.squareRoot()
            let ex = el.e.x * k
            let ez = el.e.z * k
            let ex2 = ex * ex
            let ez2 = ez * ez
            let qa = (sa * sa) / ex2 + (ca * ca) / ez2
            let qb = -2 * ((sa * el.c.x) / ex2 + (ca * el.c.z) / ez2)
            let qc = (el.c.x * el.c.x) / ex2 + (el.c.z * el.c.z) / ez2 - 1
            let disc = qb * qb - 4 * qa * qc
            if disc < 0 || qa <= 0 { continue }
            let t = (-qb + disc.squareRoot()) / (2 * qa)
            if t > best { best = t }
        }
        return best
    }

    /// Längslinien + Ringe auf einer Gliedmaße.
    private func webOnLimb(_ mb: inout MeshBuilder, _ shape: LimbShape, yTop: Float, yBot: Float, lines: Int,
                           rings: [Float], width: Float, off: Float, phase: Float) {
        let steps = quality == .ultra ? 14 : 9
        for k in 0..<lines {
            let a = phase + Float(k) / Float(Swift.max(1, lines)) * 2 * Float.pi
            let n = SIMD3<Float>(sinf(a), 0, cosf(a))
            var prevP: SIMD3<Float>? = nil
            for i in 0...steps {
                let y = yTop + (yBot - yTop) * Float(i) / Float(steps)
                let r = CharacterRig.limbRadius(shape, y: y, a: a)
                if r <= 0.0001 {
                    prevP = nil
                    continue
                }
                let p = SIMD3<Float>(n.x * (r + off), y, n.z * (r + off))
                if let pp = prevP {
                    CharacterRig.ribbon(&mb, pp, n, p, n, width: width)
                }
                prevP = p
            }
        }
        let ringSteps = quality == .ultra ? 28 : 18
        for y in rings {
            var prev: SIMD3<Float>? = nil
            var prevN = SIMD3<Float>(0, 0, 1)
            for i in 0...ringSteps {
                let a = Float(i) / Float(ringSteps) * 2 * Float.pi
                let n = SIMD3<Float>(sinf(a), 0, cosf(a))
                let r = CharacterRig.limbRadius(shape, y: y, a: a)
                if r <= 0.0001 {
                    prev = nil
                    continue
                }
                let p = SIMD3<Float>(n.x * (r + off), y, n.z * (r + off))
                if let pp = prev {
                    CharacterRig.ribbon(&mb, pp, prevN, p, n, width: width)
                }
                prev = p
                prevN = n
            }
        }
    }

    /// Flaches Emblem (Raute mit Schwingen), auf die Oberfläche projiziert.
    private func emblem(_ mb: inout MeshBuilder, on e: WebSurface, at u: SIMD3<Float>, size: Float, off: Float) {
        let center = CharacterRig.surfacePoint(e, u, off: 0)
        let n = center.n
        var up = SIMD3<Float>(0, 1, 0) - n * simd_dot(SIMD3<Float>(0, 1, 0), n)
        up = safeNormalize(up, fallback: SIMD3<Float>(0, 1, 0))
        let right = safeNormalize(simd_cross(up, n), fallback: SIMD3<Float>(1, 0, 0))
        func project(_ x: Float, _ y: Float) -> SIMD3<Float> {
            let sx: Float = x * size
            let sy: Float = y * size
            let ox: SIMD3<Float> = right * sx
            let oy: SIMD3<Float> = up * sy
            let flat: SIMD3<Float> = center.p + ox + oy
            let rel: SIMD3<Float> = flat - e.c
            let u: SIMD3<Float> = rel / e.k
            return CharacterRig.surfacePoint(e, u, off: off).p
        }
        func tri(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>) {
            let nn = simd_cross(b - a, c - a)
            if simd_dot(nn, n) >= 0 {
                mb.addTriangle(a, b, c, uvScale: 1)
            } else {
                mb.addTriangle(a, c, b, uvScale: 1)
            }
        }
        // zentrale Klinge (lange Raute)
        let top = project(0, 0.075)
        let rgt = project(0.026, 0.004)
        let bot = project(0, -0.09)
        let lft = project(-0.026, 0.004)
        tri(top, lft, bot)
        tri(top, bot, rgt)
        // Schwingen
        for sd in [Float(1), Float(-1)] {
            let a = project(0.022 * sd, 0.022)
            let b = project(0.082 * sd, 0.05)
            let c = project(0.034 * sd, -0.018)
            tri(a, b, c)
            let d = project(0.03 * sd, -0.03)
            let f = project(0.062 * sd, -0.012)
            let g = project(0.026 * sd, -0.06)
            tri(d, f, g)
        }
    }

    // MARK: - Körper

    private func buildVisuals() {
        for (_, v) in visRoots { v.removeFromParentNode() }
        visRoots.removeAll()
        matEntries.removeAll()
        swayChains.removeAll()
        tendrils.removeAll()
        flameLights.removeAll()
        rimInstalled = false
        restPositions = layoutPositions()
        for j in Joint.allCases where j != .hips {
            joints[j]?.simdPosition = restPositions[j] ?? SIMD3<Float>(0, 0, 0)
        }
        let m = makePalette()
        buildTorso(m)
        buildHead(m)
        buildArm(m, left: true)
        buildArm(m, left: false)
        buildLeg(m, left: true)
        buildLeg(m, left: false)
        buildAccessories(m)
        if matState == .frozen || matState == .shadow {
            if matAmount > 0 { installRimShader() }
        }
        refreshMaterials()
    }

    private func buildTorso(_ m: Palette) {
        let d = dims
        let s = d.s
        let hp = container(.hips)
        let sp = container(.spine)
        let ch = container(.chest)
        let coat = look.accessories.contains(.labCoat)

        // Becken + Gesäß
        ellipsoid(hp, pv(0, -0.02, -0.005), 0.13 * s, SIMD3<Float>(1.22 * d.hw, 0.72, 0.86 * d.td), m.suit)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(hp, pv(0.06 * sd * d.hw, -0.06, -0.045 * d.td), 0.085 * s, SIMD3<Float>(1, 1.05, 0.9 * d.td), m.suit)
        }
        // Gürtel mit Schnalle
        if !coat {
            cylinder(hp, pv(0, 0.035, 0), r: 1, h: 0.045 * s, m.dark,
                     scale: SIMD3<Float>(0.137 * s * d.hw, 1, 0.098 * s * d.td))
            box(hp, pv(0, 0.035, 0.098 * d.td + 0.003), SIMD3<Float>(0.05, 0.034, 0.012) * s, chamfer: 0.004 * s,
                m.superSuit ? m.glow : m.metal, shadow: false)
        }
        // Bauch
        let abW = 0.95 + (d.ws - 1) * 0.8
        ellipsoid(sp, pv(0, 0.04, 0.008), 0.12 * s, SIMD3<Float>(abW, 1.2, 0.8 * d.td * d.belly), m.suit)
        // Brustkorb, Brustmuskeln, Rücken (Seitenpaneele), Nacken
        let chestS = chestSurface
        ellipsoid(ch, chestS.c, chestS.r, chestS.k, m.suit)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(ch, pv(0.068 * sd * d.ws, 0.11, 0.055 * d.td), 0.08 * s, SIMD3<Float>(1.05 * d.ws, 0.72, 0.55 * d.td), m.suit)
        }
        if m.superSuit {
            let latsS = latsSurface
            ellipsoid(ch, latsS.c, latsS.r, latsS.k, m.panel)
        }
        let trapR = 0.062 * s * (1 + (d.ts - 1) * 0.5)
        capsule(ch, pv(-0.11 * d.ws, 0.17, -0.035 * d.td), pv(0.11 * d.ws, 0.17, -0.035 * d.td), trapR, m.suit)
    }

    private func buildHead(_ m: Palette) {
        let d = dims
        let s = d.s
        let hj = container(.head)
        let nj = container(.neck)
        let hasHood = look.accessories.contains(.hood)

        let neckR = 0.05 * s * (1 + (d.ts - 1) * 0.75)
        capsule(nj, pv(0, -0.02, 0), pv(0, 0.1, 0.012), neckR, look.hasMask ? m.suit : m.skin)

        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let hk = s * d.head
        ellipsoid(hj, c, r, hs, m.headMat)
        // Kiefer / Kinn
        ellipsoid(hj, SIMD3<Float>(0, 0.05, 0.03) * hk, 0.068 * hk, SIMD3<Float>(1.0 + (d.ws - 1) * 0.5, 0.78, 0.95), m.headMat)

        let surf = WebSurface(c: c, r: r, k: hs)
        switch look.eyeStyle {
        case .lenses:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.36 * sd, 0.13, 0.92), off: 0)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: 0.42 * sd, axis: SIMD3<Float>(0, 0, 1))
                let rimNode = ellipsoid(hj, sp.p - sp.n * (0.002 * s), 1, SIMD3<Float>(0.035, 0.023, 0.008) * hk, m.dark, shadow: false, detail: 0.6)
                rimNode.simdOrientation = q
                let lensNode = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.029, 0.0185, 0.0078) * hk, m.lens, shadow: false, detail: 0.6)
                lensNode.simdOrientation = q
                // Tropfenform: zweiter Lappen innen-unten
                let off = q.act(SIMD3<Float>(-0.013 * sd, -0.007, 0) * hk)
                let rim2 = ellipsoid(hj, sp.p + off - sp.n * (0.002 * s), 1, SIMD3<Float>(0.024, 0.018, 0.0082) * hk, m.dark, shadow: false, detail: 0.5)
                rim2.simdOrientation = q
                let lobe = ellipsoid(hj, sp.p + off, 1, SIMD3<Float>(0.019, 0.0135, 0.0079) * hk, m.lens, shadow: false, detail: 0.5)
                lobe.simdOrientation = q
            }
        case .glow:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.34 * sd, 0.11, 0.93), off: 0)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: 0.25 * sd, axis: SIMD3<Float>(0, 0, 1))
                let socket = ellipsoid(hj, sp.p - sp.n * (0.003 * s), 1, SIMD3<Float>(0.022, 0.012, 0.007) * hk, m.dark, shadow: false, detail: 0.5)
                socket.simdOrientation = q
                let eye = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.014, 0.0075, 0.006) * hk, m.glow, shadow: false, detail: 0.5)
                eye.simdOrientation = q
            }
        case .visor:
            ellipsoid(hj, c + SIMD3<Float>(0, 0.012 * hk, 0.27 * r), 1,
                      SIMD3<Float>(0.95 * r * hs.x, 0.16 * r, 0.81 * r), m.glow, shadow: false)
        case .human:
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.33 * sd, 0.1, 0.94), off: -0.002 * s)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n)
                let white = ellipsoid(hj, sp.p, 1, SIMD3<Float>(0.0135, 0.0085, 0.006) * hk, m.eyeWhite, shadow: false, detail: 0.5)
                white.simdOrientation = q
                ellipsoid(hj, sp.p + sp.n * (0.0045 * s), 0.0058 * hk, SIMD3<Float>(1, 1, 0.6), m.dark, shadow: false, detail: 0.4)
            }
        }

        // Gesicht (ohne Maske)
        if !look.hasMask {
            let browMat = look.hairColor != nil ? m.hair : m.dark
            for sd in [Float(1), Float(-1)] {
                let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.33 * sd, 0.27, 0.9), off: 0.002 * s)
                let q = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: sp.n) * simd_quatf(angle: -0.12 * sd, axis: SIMD3<Float>(0, 0, 1))
                box(hj, sp.p, SIMD3<Float>(0.032, 0.006, 0.008) * hk, chamfer: 0.002 * s, browMat, orient: q, shadow: false)
                // Ohren
                ellipsoid(hj, c + SIMD3<Float>(sd * (r * hs.x - 0.004 * s), -0.005 * s, -0.008 * s), 1,
                          SIMD3<Float>(0.01, 0.027, 0.018) * hk, m.skin, detail: 0.5)
            }
            let nose = CharacterRig.surfacePoint(surf, SIMD3<Float>(0, -0.05, 1), off: 0)
            ellipsoid(hj, nose.p + nose.n * (0.006 * s), 1, SIMD3<Float>(0.011, 0.021, 0.015) * hk, m.skin, shadow: false, detail: 0.5)
            let mouth = CharacterRig.surfacePoint(surf, SIMD3<Float>(0, -0.42, 0.9), off: 0.001 * s)
            let mq = CharacterRig.rotation(from: SIMD3<Float>(0, 0, 1), to: mouth.n)
            box(hj, mouth.p, SIMD3<Float>(0.032, 0.0045, 0.008) * hk, chamfer: 0.002 * s, m.lips, orient: mq, shadow: false)
            if look.hairColor != nil && !hasHood {
                ellipsoid(hj, c + SIMD3<Float>(0, 0.25 * r, -0.12 * r), r,
                          SIMD3<Float>(hs.x * 1.07, hs.y * 0.84, hs.z * 1.06), m.hair)
            }
        }
    }

    // Gliedmaßen-Formen (gemeinsam für Geometrie und Netzlinien)

    private func upperArmShape(_ sd: Float, _ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(-0.02 * s, -0.27 * s, 0.048 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0.012 * sd * s, -0.03 * s, 0), e: SIMD3<Float>(0.066, 0.0739, 0.066) * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.12 * s, 0.016 * k), e: SIMD3<Float>(0.044, 0.088, 0.044) * k))
        return sh
    }

    private func forearmShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.13 * s, 0.043 * k))
        sh.caps.append(SIMD3<Float>(-0.1 * s, -0.248 * s, 0.034 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.065 * s, 0.004 * s), e: SIMD3<Float>(0.047, 0.0893, 0.0447) * k))
        return sh
    }

    private func thighShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.39 * s, 0.072 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.14 * s, 0.02 * k), e: SIMD3<Float>(0.0646, 0.1428, 0.0612) * k))
        return sh
    }

    private func shinShape(_ k: Float) -> LimbShape {
        let s = dims.s
        var sh = LimbShape()
        sh.caps.append(SIMD3<Float>(0, -0.40 * s, 0.05 * k))
        sh.ells.append(LimbEll(c: SIMD3<Float>(0, -0.12 * s, -0.022 * k), e: SIMD3<Float>(0.055, 0.1155, 0.0578) * k))
        return sh
    }

    private func armThickness(left: Bool) -> Float {
        let cyber = !left && look.accessories.contains(.cyberArm)
        return dims.s * dims.ts * (cyber ? 1.08 : 1)
    }

    private func buildArm(_ m: Palette, left: Bool) {
        let s = dims.s
        let sd: Float = left ? 1 : -1
        let cyber = !left && look.accessories.contains(.cyberArm)
        let coat = look.accessories.contains(.labCoat)
        let ua = container(left ? .lUpperArm : .rUpperArm)
        let fa = container(left ? .lForearm : .rForearm)
        let hd = container(left ? .lHand : .rHand)
        let armMat = cyber ? m.cyber : m.suit
        let shoulderMat = cyber ? m.cyber : (m.superSuit ? m.panel : m.suit)
        let k = armThickness(left: left)

        let uaShape = upperArmShape(sd, k)
        for cp in uaShape.caps {
            capsule(ua, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, armMat)
        }
        if uaShape.ells.count >= 2 {
            ellipsoid(ua, uaShape.ells[0].c, 1, uaShape.ells[0].e, shoulderMat)
            ellipsoid(ua, uaShape.ells[1].c, 1, uaShape.ells[1].e, armMat)
        }
        let faShape = forearmShape(k)
        for cp in faShape.caps {
            capsule(fa, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, armMat)
        }
        for el in faShape.ells {
            ellipsoid(fa, el.c, 1, el.e, armMat)
        }
        if m.superSuit && !cyber && !coat {
            capsule(fa, pv(0, -0.125, 0), pv(0, -0.252, 0), 0.034 * k + 0.0045 * s, m.glove)
        }
        let fistMat = cyber ? m.cyber : m.glove
        buildFist(hd, sd: sd, mat: fistMat, k: s * (1 + (dims.ts - 1) * 0.6))
    }

    private func buildFist(_ hd: SCNNode, sd: Float, mat: SCNMaterial, k: Float) {
        // Faust: schmal in X, Daumen vorne (+Z), Knöchel unten
        box(hd, SIMD3<Float>(0, -0.05, 0.006) * k, SIMD3<Float>(0.05, 0.09, 0.088) * k, chamfer: 0.018 * k, mat)
        box(hd, SIMD3<Float>(-0.012 * sd, -0.088, 0.008) * k, SIMD3<Float>(0.044, 0.042, 0.084) * k, chamfer: 0.016 * k, mat)
        capsule(hd, SIMD3<Float>(-0.006 * sd, -0.028, 0.044) * k, SIMD3<Float>(-0.02 * sd, -0.07, 0.05) * k, 0.012 * k, mat,
                shadow: false, detail: 0.6)
    }

    private func buildLeg(_ m: Palette, left: Bool) {
        let s = dims.s
        let k = s * dims.ts
        let th = container(left ? .lThigh : .rThigh)
        let sh = container(left ? .lShin : .rShin)
        let ft = container(left ? .lFoot : .rFoot)

        let tShape = thighShape(k)
        for cp in tShape.caps {
            capsule(th, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, m.suit)
        }
        for el in tShape.ells {
            ellipsoid(th, el.c, 1, el.e, m.suit)
        }
        let sShape = shinShape(k)
        for cp in sShape.caps {
            capsule(sh, SIMD3<Float>(0, cp.x, 0), SIMD3<Float>(0, cp.y, 0), cp.z, m.suit)
        }
        for el in sShape.ells {
            ellipsoid(sh, el.c, 1, el.e, m.suit)
        }
        if m.superSuit {
            // Knieschoner
            ellipsoid(sh, SIMD3<Float>(0, -0.005 * s, 0.042 * k), 0.034 * k, SIMD3<Float>(1, 1.05, 0.7), m.panel, detail: 0.6)
        }
        // Stiefelschaft
        capsule(sh, pv(0, -0.21, 0), pv(0, -0.405, 0), 0.056 * k, m.boot)
        // Fuß + Sohle
        let fk = s * (1 + (dims.ts - 1) * 0.5)
        box(ft, pv(0, -0.041, 0.05), SIMD3<Float>(0.095 * fk, 0.08 * s, 0.25 * s), chamfer: 0.03 * s, m.boot)
        box(ft, pv(0, -0.072, 0.05), SIMD3<Float>(0.1 * fk, 0.018 * s, 0.258 * s), chamfer: 0.006 * s, m.dark, shadow: false)
    }

    // MARK: - Accessoires

    private func buildAccessories(_ m: Palette) {
        var done = Set<Accessory>()
        for a in look.accessories {
            if done.contains(a) { continue }
            done.insert(a)
            switch a {
            case .webLines: buildWebLines(m)
            case .chainBlades: buildChainBlades(m)
            case .katana: buildKatana(m)
            case .scarf: buildScarf(m)
            case .shoulderPads: buildShoulderPads(m)
            case .cyberArm: buildCyberDetails(m)
            case .horns: buildHorns(m)
            case .crown: buildCrown(m)
            case .cape: buildCape(m)
            case .flameAura: buildFlameAura(m)
            case .tendrils: buildTendrils(m)
            case .spikes: buildSpikes(m)
            case .labCoat: buildLabCoat(m)
            case .hood: buildHood(m)
            }
        }
    }

    private func addMeshNode(_ mb: MeshBuilder, to j: Joint, material: SCNMaterial) {
        if mb.isEmpty { return }
        let n = SCNNode(geometry: mb.build(material: material))
        n.name = "rig.web"
        n.castsShadow = false
        container(j).addChildNode(n)
    }

    /// Dunkel-silbern leuchtende Netzlinien auf Maske, Brust, Rücken, Bauch und Gliedmaßen + Brustemblem.
    private func buildWebLines(_ m: Palette) {
        let d = dims
        let s = d.s
        let width = 0.0034 * s
        let off = 0.0022 * s
        let ultra = quality == .ultra
        let lines = ultra ? 6 : 4

        // Brust vorne + Emblem
        var chestMB = MeshBuilder()
        let chestSurf = chestSurface
        webPattern(&chestMB, on: chestSurf, pole: SIMD3<Float>(0, 0.25, 1), radials: ultra ? 10 : 8, phase: Float.pi / 8,
                   theta0: 0.16, theta1: 1.35, rings: [0.34, 0.66, 0.98, 1.28], width: width, off: off)
        // Rücken (auf den Seitenpaneelen, falls vorhanden)
        let backSurf: WebSurface
        if m.superSuit {
            backSurf = latsSurface
        } else {
            backSurf = chestSurf
        }
        webPattern(&chestMB, on: backSurf, pole: SIMD3<Float>(0, 0.25, -1), radials: 8, phase: Float.pi / 8,
                   theta0: 0.12, theta1: 1.2, rings: [0.42, 0.8, 1.12], width: width, off: off)
        addMeshNode(chestMB, to: .chest, material: m.web)

        var emblemMB = MeshBuilder()
        emblem(&emblemMB, on: chestSurf, at: SIMD3<Float>(0, 0.25, 1), size: s * d.ws, off: 0.0035 * s)
        emblem(&emblemMB, on: backSurf, at: SIMD3<Float>(0, 0.3, -1), size: s * d.ws * 0.6, off: 0.0035 * s)
        addMeshNode(emblemMB, to: .chest, material: m.glow)

        // Bauch: Ringe + Meridiane
        var absMB = MeshBuilder()
        let abW = 0.95 + (d.ws - 1) * 0.8
        let absSurf = WebSurface(c: pv(0, 0.04, 0.008), r: 0.12 * s, k: SIMD3<Float>(abW, 1.2, 0.8 * d.td * d.belly))
        webPattern(&absMB, on: absSurf, pole: SIMD3<Float>(0, 1, 0), radials: 8, phase: Float.pi / 8,
                   theta0: 0.95, theta1: 2.2, rings: [1.3, 1.62, 1.95], width: width, off: off)
        addMeshNode(absMB, to: .spine, material: m.web)

        // Maske
        if look.hasMask {
            var headMB = MeshBuilder()
            let headSurf = WebSurface(c: headCenterLocal, r: headRadius, k: headScale)
            webPattern(&headMB, on: headSurf, pole: SIMD3<Float>(0, 0.05, 1), radials: ultra ? 12 : 10, phase: Float.pi / 12,
                       theta0: 0.12, theta1: 2.5, rings: [0.42, 0.8, 1.2, 1.62, 2.05], width: width * 0.85, off: off * 0.8)
            addMeshNode(headMB, to: .head, material: m.web)
        }

        // Gliedmaßen
        let ringCountUA: [Float] = ultra ? [-0.22, -0.26] : [-0.24]
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            if !left && look.accessories.contains(.cyberArm) { continue }
            let k = armThickness(left: left)
            var uaMB = MeshBuilder()
            webOnLimb(&uaMB, upperArmShape(sd, k), yTop: -0.01 * s, yBot: -0.285 * s, lines: lines,
                      rings: ringCountUA.map { $0 * s }, width: width, off: off, phase: 0.3)
            addMeshNode(uaMB, to: left ? .lUpperArm : .rUpperArm, material: m.web)
            var faMB = MeshBuilder()
            webOnLimb(&faMB, forearmShape(k), yTop: -0.005 * s, yBot: -0.2 * s, lines: lines,
                      rings: [-0.035 * s, -0.1 * s], width: width, off: off, phase: 0.3)
            addMeshNode(faMB, to: left ? .lForearm : .rForearm, material: m.web)
        }
        let legK = s * d.ts
        for left in [true, false] {
            var thMB = MeshBuilder()
            webOnLimb(&thMB, thighShape(legK), yTop: -0.02 * s, yBot: -0.38 * s, lines: lines + 2,
                      rings: ultra ? [-0.08 * s, -0.2 * s, -0.32 * s] : [-0.12 * s, -0.3 * s],
                      width: width, off: off, phase: 0.2)
            addMeshNode(thMB, to: left ? .lThigh : .rThigh, material: m.web)
            var shMB = MeshBuilder()
            webOnLimb(&shMB, shinShape(legK), yTop: -0.03 * s, yBot: -0.2 * s, lines: lines + 2,
                      rings: [-0.08 * s, -0.17 * s], width: width, off: off, phase: 0.2)
            addMeshNode(shMB, to: left ? .lShin : .rShin, material: m.web)
        }
    }

    /// Kettenklingen: Klinge an der Unterarm-Außenseite, gewickelte Kette und eine schwingende Kettenschleppe.
    private func buildChainBlades(_ m: Palette) {
        let s = dims.s
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let fa = container(left ? .lForearm : .rForearm)
            let k = armThickness(left: left)
            let bx = sd * (0.043 * k + 0.012 * s)
            // Klinge (Spitze zeigt Richtung Ellbogen und darüber hinaus)
            box(fa, SIMD3<Float>(bx, -0.08 * s, -0.008 * s), SIMD3<Float>(0.006 * s, 0.3 * s, 0.038 * s), chamfer: 0.002 * s, m.blade)
            let tip = SCNPyramid(width: CGFloat(0.006 * s), height: CGFloat(0.075 * s), length: CGFloat(0.038 * s))
            tip.materials = [m.blade]
            let tipNode = SCNNode(geometry: tip)
            tipNode.simdPosition = SIMD3<Float>(bx, 0.07 * s, -0.008 * s)
            tipNode.castsShadow = false
            fa.addChildNode(tipNode)
            // leuchtende Schneide
            box(fa, SIMD3<Float>(bx, -0.07 * s, -0.008 * s - 0.019 * s), SIMD3<Float>(0.0068 * s, 0.3 * s, 0.003 * s),
                chamfer: 0, m.glow, shadow: false)
            // gewickelte Kette
            let links = quality == .performance ? 6 : 10
            for i in 0..<links {
                let a = Float(i) * (2 * Float.pi / 4.5)
                let y = -0.05 * s - Float(i) * 0.017 * s
                let rad = (y > -0.13 * s ? 0.045 * k : 0.037 * k) + 0.004 * s
                let n = SIMD3<Float>(sinf(a), 0, cosf(a))
                let pos = SIMD3<Float>(n.x * rad, y, n.z * rad)
                let q: simd_quatf
                if i % 2 == 0 {
                    q = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: n)
                } else {
                    let tangent = SIMD3<Float>(cosf(a), -0.25, -sinf(a))
                    q = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: simd_cross(n, tangent))
                }
                torus(fa, pos, ring: 0.0105 * s, pipe: 0.0028 * s, m.metal, orient: q)
            }
            // schwingende Kettenschleppe am Handgelenk
            let anchor = SCNNode()
            anchor.simdPosition = SIMD3<Float>(sd * 0.04 * k, -0.235 * s, -0.01 * s)
            fa.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            let count = quality == .performance ? 4 : 6
            let segLen = 0.03 * s
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let q = (i % 2 == 0) ? simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(1, 0, 0))
                                     : simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(0, 0, 1))
                torus(seg, SIMD3<Float>(0, -segLen * 0.5, 0), ring: 0.011 * s, pipe: 0.0028 * s, m.metal,
                      orient: q, scale: SIMD3<Float>(1, 1, 1.35))
                segs.append(seg)
                parent = seg
            }
            cone(parent, base: SIMD3<Float>(0, -segLen, 0), dir: SIMD3<Float>(0, -1, 0), r0: 0.012 * s, r1: 0, h: 0.05 * s, m.blade, shadow: false)
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(left ? .lForearm : .rForearm),
                                        side: 0, minOffset: 0, stiffness: 14, drag: 0.25, flutter: 0.12, phase: sd * 2.1))
        }
    }

    /// Katana schräg auf dem Rücken, Griff über der rechten Schulter.
    private func buildKatana(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let holder = SCNNode()
        holder.simdPosition = pv(0, 0.05, -(0.125 * d.td + 0.032))
        holder.simdOrientation = simd_quatf(angle: 0.45, axis: SIMD3<Float>(0, 0, 1))
        ch.addChildNode(holder)
        let sheath = cylinder(holder, pv(0, -0.04, 0), r: 0.02 * s, h: 0.68 * s, m.dark, scale: SIMD3<Float>(1, 1, 0.62))
        sheath.name = "rig.katana"
        cylinder(holder, pv(0, -0.38, 0), r: 0.021 * s, h: 0.03 * s, m.gold, scale: SIMD3<Float>(1, 1, 0.62))
        cylinder(holder, pv(0, 0.305, 0), r: 0.042 * s, h: 0.01 * s, m.gold)
        cylinder(holder, pv(0, 0.42, 0), r: 0.016 * s, h: 0.22 * s, m.cloth)
        if quality != .performance {
            for i in 0..<6 {
                let y = 0.33 + Float(i) * 0.034
                torus(holder, pv(0, y, 0), ring: 0.0165 * s, pipe: 0.0035 * s, m.panel,
                      orient: simd_quatf(angle: 0.5, axis: SIMD3<Float>(1, 0, 0)))
            }
        }
        cylinder(holder, pv(0, 0.535, 0), r: 0.018 * s, h: 0.014 * s, m.gold)
    }

    /// Schal um den Hals mit zwei flatternden Enden.
    private func buildScarf(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let nt = 1 + (d.ts - 1) * 0.75
        torus(ch, pv(0, 0.215, -0.005), ring: 0.064 * s * nt, pipe: 0.024 * s, m.cloth,
              scale: SIMD3<Float>(1.05, 0.85, 1.0), shadow: true)
        let count = quality == .ultra ? 7 : (quality == .balanced ? 5 : 4)
        let segLen = 0.52 * s / Float(count)
        for sd in [Float(1), Float(-1)] {
            let anchor = SCNNode()
            anchor.simdPosition = pv(0.032 * sd, 0.2, -0.075 * nt)
            ch.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let w = (0.075 - 0.012 * Float(i) / Float(count)) * s
                box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.08, 0.012 * s), chamfer: 0.004 * s, m.cloth)
                segs.append(seg)
                parent = seg
            }
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.chest), side: -1, minOffset: 0.08,
                                        stiffness: 7, drag: 0.8, flutter: 0.6, phase: sd * 1.7))
        }
    }

    /// Mehrlagige Schulterpanzer.
    private func buildShoulderPads(_ m: Palette) {
        let s = dims.s
        let armor = registerMaterial(look.secondaryColor, rough: 0.3, metal: 0.85)
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let ua = container(left ? .lUpperArm : .rUpperArm)
            let k = s * dims.ts
            let q1 = simd_quatf(angle: -0.35 * sd, axis: SIMD3<Float>(0, 0, 1))
            let p1 = ellipsoid(ua, SIMD3<Float>(0.025 * sd, 0.008, 0) * k, 0.095 * k, SIMD3<Float>(1.0, 0.55, 1.08), armor)
            p1.simdOrientation = q1
            torus(ua, SIMD3<Float>(0.025 * sd, 0.0, 0) * k, ring: 0.093 * k, pipe: 0.006 * k, m.gold,
                  orient: q1, scale: SIMD3<Float>(1, 1, 1.08), shadow: false)
            let q2 = simd_quatf(angle: -0.6 * sd, axis: SIMD3<Float>(0, 0, 1))
            let p2 = ellipsoid(ua, SIMD3<Float>(0.052 * sd, -0.045, 0) * k, 0.082 * k, SIMD3<Float>(1.0, 0.5, 1.02), armor)
            p2.simdOrientation = q2
            // Nieten
            for i in 0..<3 {
                let a = (Float(i) - 1) * 0.6
                let pos = SIMD3<Float>(0.03 * sd + sinf(a) * 0.0, 0.055, cosf(a) * 0.07) * k
                ellipsoid(ua, pos, 0.008 * k, SIMD3<Float>(1, 1, 1), m.gold, shadow: false, detail: 0.3)
            }
        }
    }

    /// Cyber-Arm (rechts): leuchtende Nähte, Kolben, Gelenkring.
    private func buildCyberDetails(_ m: Palette) {
        let s = dims.s
        let k = armThickness(left: false)
        let ua = container(.rUpperArm)
        let fa = container(.rForearm)
        let hd = container(.rHand)
        let pipe = 0.0035 * s
        torus(ua, pv(0, -0.2, 0), ring: 0.051 * k, pipe: pipe, m.glow)
        torus(ua, pv(0, -0.25, 0), ring: 0.05 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.015, 0), ring: 0.046 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.15, 0), ring: 0.04 * k, pipe: pipe, m.glow)
        torus(fa, pv(0, -0.245, 0), ring: 0.037 * k, pipe: pipe, m.glow)
        for sd in [Float(1), Float(-1)] {
            capsule(ua, SIMD3<Float>(sd * 0.049 * k, -0.08 * s, 0), SIMD3<Float>(sd * 0.049 * k, -0.23 * s, 0), 0.0025 * s,
                    m.glow, shadow: false, detail: 0.4)
            capsule(fa, SIMD3<Float>(sd * 0.041 * k, -0.03 * s, 0), SIMD3<Float>(sd * 0.036 * k, -0.135 * s, 0), 0.0025 * s,
                    m.glow, shadow: false, detail: 0.4)
        }
        // Kolben an der Unterarm-Rückseite
        capsule(fa, SIMD3<Float>(0, -0.03 * s, -0.048 * k), SIMD3<Float>(0, -0.2 * s, -0.04 * k), 0.007 * s, m.metal, detail: 0.5)
        capsule(fa, SIMD3<Float>(0.012 * s, -0.04 * s, -0.046 * k), SIMD3<Float>(0.012 * s, -0.12 * s, -0.042 * k), 0.005 * s, m.metal, detail: 0.5)
        // Knöchel-Leuchtpunkte
        let fk = s * (1 + (dims.ts - 1) * 0.6)
        for i in 0..<4 {
            let z = (-0.025 + Float(i) * 0.017) * fk
            ellipsoid(hd, SIMD3<Float>(0.006 * fk, -0.108 * fk, z + 0.008 * fk), 0.0055 * fk, SIMD3<Float>(1, 1, 1), m.glow,
                      shadow: false, detail: 0.3)
        }
        // Gelenkring am Rumpf
        let ch = container(.chest)
        let shoulder = restPositions[.rUpperArm] ?? pv(-0.205, 0.195, -0.01)
        torus(ch, shoulder, ring: 0.058 * k, pipe: 0.008 * s, m.metal,
              orient: simd_quatf(angle: Float.pi / 2, axis: SIMD3<Float>(0, 0, 1)), shadow: true)
    }

    /// Gebogene Hörner aus Kegelsegmenten.
    private func buildHorns(_ m: Palette) {
        let s = dims.s
        let hk = s * dims.head
        let hj = container(.head)
        let surf = WebSurface(c: headCenterLocal, r: headRadius, k: headScale)
        for sd in [Float(1), Float(-1)] {
            let sp = CharacterRig.surfacePoint(surf, SIMD3<Float>(0.42 * sd, 0.62, 0.35), off: -0.004 * s)
            let root = SCNNode()
            root.simdPosition = sp.p
            root.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0),
                                                         to: safeNormalize(sp.n + SIMD3<Float>(0.35 * sd, 0.6, -0.2)))
            hj.addChildNode(root)
            var parent = root
            var radius = 0.03 * hk
            for i in 0..<3 {
                let h = (0.075 - 0.01 * Float(i)) * hk
                let r1 = radius * 0.64
                cone(parent, base: SIMD3<Float>(0, 0, 0), dir: SIMD3<Float>(0, 1, 0), r0: radius, r1: r1, h: h, m.horn)
                let next = SCNNode()
                next.simdPosition = SIMD3<Float>(0, h * 0.96, 0)
                next.simdOrientation = simd_quatf(angle: -0.5, axis: SIMD3<Float>(1, 0, 0)) * simd_quatf(angle: 0.12 * sd, axis: SIMD3<Float>(0, 0, 1))
                parent.addChildNode(next)
                parent = next
                radius = r1
            }
            cone(parent, base: SIMD3<Float>(0, 0, 0), dir: SIMD3<Float>(0, 1, 0), r0: radius, r1: 0.0005, h: 0.05 * hk, m.horn, shadow: false)
        }
    }

    /// Krone: Reif mit Zacken und leuchtenden Steinen.
    private func buildCrown(_ m: Palette) {
        let s = dims.s
        let hj = container(.head)
        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let lift: Float = 0.42
        let f = (1 - (lift / hs.y) * (lift / hs.y)).squareRoot()
        let semiX = r * hs.x * f * 1.01
        let semiZ = r * hs.z * f * 1.01
        let y = c.y + lift * r
        let band = SCNTube(innerRadius: CGFloat(semiX * 0.98), outerRadius: CGFloat(semiX * 0.98 + 0.008 * s), height: CGFloat(0.034 * s))
        band.radialSegmentCount = segRadial
        band.materials = [m.gold]
        let bandNode = SCNNode(geometry: band)
        bandNode.simdPosition = SIMD3<Float>(c.x, y, c.z)
        bandNode.simdScale = SIMD3<Float>(1, 1, semiZ / Swift.max(0.001, semiX))
        hj.addChildNode(bandNode)
        let spikes = 9
        for i in 0..<spikes {
            let a = (Float(i) / Float(spikes - 1) - 0.5) * 2 * 2.6
            let px = sinf(a) * (semiX + 0.004 * s)
            let pz = cosf(a) * (semiZ + 0.004 * s)
            let center = i == spikes / 2
            let h: Float = (center ? 0.075 : (0.04 + 0.012 * cosf(a))) * s
            let base = SIMD3<Float>(c.x + px, y + 0.012 * s, c.z + pz)
            let outward = safeNormalize(SIMD3<Float>(px, 0, pz))
            cone(hj, base: base, dir: safeNormalize(SIMD3<Float>(0, 1, 0) + outward * 0.18), r0: 0.011 * s, r1: 0.0008 * s, h: h, m.gold, shadow: false)
            if i % 2 == 0 {
                ellipsoid(hj, SIMD3<Float>(c.x + sinf(a) * (semiX + 0.009 * s), y, c.z + cosf(a) * (semiZ + 0.009 * s)),
                          (center ? 0.011 : 0.007) * s, SIMD3<Float>(1, 1, 0.7), m.glow, shadow: false, detail: 0.4)
            }
        }
    }

    /// Umhang aus Segmenten, die nachschwingen.
    private func buildCape(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        // Schulterspange
        capsule(ch, pv(-0.15 * d.ws, 0.172, -0.11 * d.td), pv(0.15 * d.ws, 0.172, -0.11 * d.td), 0.02 * s, m.gold, detail: 0.6)
        for sd in [Float(1), Float(-1)] {
            ellipsoid(ch, pv(0.16 * sd * d.ws, 0.172, -0.1 * d.td), 0.03 * s, SIMD3<Float>(1, 1, 0.6), m.gold, detail: 0.5)
        }
        let anchor = SCNNode()
        anchor.simdPosition = pv(0, 0.168, -(0.135 * d.td + 0.006))
        ch.addChildNode(anchor)
        let count = quality == .ultra ? 9 : (quality == .balanced ? 6 : 4)
        let total = 1.12 * s
        let segLen = total / Float(count)
        var segs: [SCNNode] = []
        var parent = anchor
        for i in 0..<count {
            let seg = SCNNode()
            seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
            parent.addChildNode(seg)
            let t = count > 1 ? Float(i) / Float(count - 1) : 0
            let w = (0.4 + 0.22 * t) * s * d.ws
            box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.06, 0.012 * s), chamfer: 0.004 * s, m.cloth)
            segs.append(seg)
            parent = seg
        }
        swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.chest), side: -1, minOffset: 0.1,
                                    stiffness: 9, drag: 0.55, flutter: 0.35, phase: 0.4))
    }

    private func makeFlameSystem(rate: Float, size: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.loops = true
        p.birthRate = CGFloat(rate * particleScale)
        p.particleLifeSpan = 0.5
        p.particleLifeSpanVariation = 0.2
        p.particleVelocity = 0.35
        p.particleVelocityVariation = 0.25
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 25
        p.acceleration = SCNVector3(x: 0, y: 1.6, z: 0)
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleAngularVelocityVariation = 90
        p.particleImage = ProceduralTextures.radialGlow(color: .white)
        p.blendMode = .additive
        p.emitterShape = SCNSphere(radius: CGFloat(size * 0.45))
        p.birthLocation = .volume
        p.particleIntensity = 1.8
        let sizeAnim = CAKeyframeAnimation()
        sizeAnim.values = [NSNumber(value: size * 0.55), NSNumber(value: size), NSNumber(value: size * 0.25)]
        sizeAnim.keyTimes = [NSNumber(value: Float(0)), NSNumber(value: Float(0.35)), NSNumber(value: Float(1))]
        sizeAnim.duration = 1
        let colorAnim = CAKeyframeAnimation()
        colorAnim.values = [UIColor(red: 1.0, green: 0.92, blue: 0.6, alpha: 1),
                            UIColor(red: 1.0, green: 0.5, blue: 0.1, alpha: 0.9),
                            UIColor(red: 0.75, green: 0.12, blue: 0.02, alpha: 0.5),
                            UIColor(red: 0.2, green: 0.02, blue: 0.0, alpha: 0)]
        colorAnim.keyTimes = [NSNumber(value: Float(0)), NSNumber(value: Float(0.25)), NSNumber(value: Float(0.6)), NSNumber(value: Float(1))]
        colorAnim.duration = 1
        p.particleColor = .white
        p.propertyControllers = [.size: SCNParticlePropertyController(animation: sizeAnim),
                                 .color: SCNParticlePropertyController(animation: colorAnim)]
        return p
    }

    /// Flammen an Händen und Schultern (eigene, dauerhafte Partikelsysteme) + flackerndes Licht.
    private func buildFlameAura(_ m: Palette) {
        let d = dims
        let s = d.s
        for j in [Joint.lHand, Joint.rHand] {
            let emitter = SCNNode()
            emitter.simdPosition = pv(0, -0.065, 0)
            container(j).addChildNode(emitter)
            emitter.addParticleSystem(makeFlameSystem(rate: 70, size: 0.11 * s))
        }
        let ch = container(.chest)
        for sd in [Float(1), Float(-1)] {
            let emitter = SCNNode()
            emitter.simdPosition = pv(0.19 * sd * d.ws, 0.2, -0.03)
            ch.addChildNode(emitter)
            emitter.addParticleSystem(makeFlameSystem(rate: 34, size: 0.13 * s))
        }
        if quality != .performance {
            let light = SCNLight()
            light.type = .omni
            light.color = UIColor(red: 1.0, green: 0.48, blue: 0.16, alpha: 1)
            light.intensity = 300
            light.attenuationStartDistance = 0.1
            light.attenuationEndDistance = CGFloat(3.2 * s)
            light.castsShadow = false
            let ln = SCNNode()
            ln.light = light
            ln.simdPosition = pv(0, 0.12, 0.22)
            ch.addChildNode(ln)
            flameLights.append(light)
            flameLightBase = 300
        }
    }

    /// Schwarze, sich windende Ranken aus dem Rücken.
    private func buildTendrils(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let tendrilMat = registerMaterial(UIColor(red: 0.018, green: 0.016, blue: 0.026, alpha: 1), rough: 0.18, metal: 0.3)
        let anchors: [(SIMD3<Float>, SIMD3<Float>)] = [
            (SIMD3<Float>(0.09, 0.14, -0.11), SIMD3<Float>(0.6, 0.55, -0.6)),
            (SIMD3<Float>(-0.09, 0.14, -0.11), SIMD3<Float>(-0.6, 0.55, -0.6)),
            (SIMD3<Float>(0.07, 0.02, -0.11), SIMD3<Float>(0.8, -0.1, -0.6)),
            (SIMD3<Float>(-0.07, 0.02, -0.11), SIMD3<Float>(-0.8, -0.1, -0.6)),
            (SIMD3<Float>(0.03, 0.2, -0.1), SIMD3<Float>(0.25, 0.9, -0.45)),
            (SIMD3<Float>(-0.03, 0.2, -0.1), SIMD3<Float>(-0.25, 0.9, -0.45))
        ]
        let count = quality == .ultra ? 6 : (quality == .balanced ? 4 : 3)
        let segCount = quality == .ultra ? 8 : (quality == .balanced ? 6 : 5)
        let segLen = 0.11 * s
        for i in 0..<Swift.min(count, anchors.count) {
            let a = anchors[i]
            let root = SCNNode()
            root.simdPosition = SIMD3<Float>(a.0.x * d.ws, a.0.y, a.0.z * d.td) * s
            root.simdOrientation = CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: a.1)
            ch.addChildNode(root)
            var parent = root
            var segs: [SCNNode] = []
            var base: [SIMD3<Float>] = []
            for kIdx in 0..<segCount {
                let seg = SCNNode()
                seg.simdPosition = kIdx == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, segLen, 0)
                parent.addChildNode(seg)
                let t = Float(kIdx) / Float(segCount)
                let r0 = (0.024 - 0.017 * t) * s
                capsule(seg, SIMD3<Float>(0, 0, 0), SIMD3<Float>(0, segLen, 0), r0, tendrilMat, shadow: kIdx < 3, detail: 0.55)
                segs.append(seg)
                base.append(SIMD3<Float>(0.16 + 0.06 * t, 0, (i % 2 == 0 ? 0.05 : -0.05)))
                parent = seg
            }
            ellipsoid(parent, SIMD3<Float>(0, segLen, 0), 0.009 * s, SIMD3<Float>(1, 1.6, 1), m.glow, shadow: false, detail: 0.4)
            tendrils.append(Tendril(segments: segs, base: base, phase: Float(i) * 1.3,
                                    freq: 2.2 + 0.35 * Float(i % 3), amp: 0.24))
        }
    }

    /// Stacheln auf Schultern, Rücken und Unterarmen.
    private func buildSpikes(_ m: Palette) {
        let d = dims
        let s = d.s
        let spikeMat = registerMaterial(UIColor(white: 0.13, alpha: 1), rough: 0.35, metal: 0.9)
        for left in [true, false] {
            let sd: Float = left ? 1 : -1
            let ua = container(left ? .lUpperArm : .rUpperArm)
            let k = s * d.ts
            for i in 0..<3 {
                let fi = Float(i)
                let base = SIMD3<Float>(sd * 0.055, 0.02 - 0.028 * fi, (fi - 1) * 0.03) * k
                cone(ua, base: base, dir: safeNormalize(SIMD3<Float>(sd, 0.75, (fi - 1) * 0.3)), r0: 0.016 * k, r1: 0.0008 * s,
                     h: (0.075 - 0.012 * fi) * s, spikeMat)
            }
            let fa = container(left ? .lForearm : .rForearm)
            let fk = armThickness(left: left)
            for i in 0..<2 {
                let y = (-0.08 - 0.07 * Float(i)) * s
                cone(fa, base: SIMD3<Float>(sd * 0.04 * fk, y, -0.01 * s), dir: safeNormalize(SIMD3<Float>(sd * 0.8, 0.55, -0.2)),
                     r0: 0.011 * s, r1: 0.0006 * s, h: 0.045 * s, spikeMat, shadow: false)
            }
        }
        let ch = container(.chest)
        for i in 0..<4 {
            let fi = Float(i)
            let y = 0.17 - fi * 0.055
            cone(ch, base: pv(0, y, -0.12 * d.td), dir: safeNormalize(SIMD3<Float>(0, 0.35, -1)), r0: 0.016 * s, r1: 0.0008 * s,
                 h: (0.07 - 0.01 * fi) * s, spikeMat)
        }
    }

    /// Offener Laborkittel mit Ärmeln, Revers und schwingenden Schößen.
    private func buildLabCoat(_ m: Palette) {
        let d = dims
        let s = d.s
        let ch = container(.chest)
        let sp = container(.spine)
        let hp = container(.hips)
        ellipsoid(ch, pv(0, 0.075, -0.024), 0.172 * s, SIMD3<Float>(1.14 * d.ws, 1.0, 0.72 * d.td), m.coat)
        ellipsoid(sp, pv(0, 0.04, -0.02), 0.128 * s, SIMD3<Float>(1.02 * d.ws, 1.22, 0.82 * d.td * d.belly), m.coat)
        ellipsoid(hp, pv(0, -0.015, -0.02), 0.138 * s, SIMD3<Float>(1.22 * d.hw, 0.74, 0.88 * d.td), m.coat)
        // Revers
        for sd in [Float(1), Float(-1)] {
            let q = simd_quatf(angle: 0.35 * sd, axis: SIMD3<Float>(0, 0, 1)) * simd_quatf(angle: -0.25, axis: SIMD3<Float>(1, 0, 0))
            box(ch, pv(0.062 * sd * d.ws, 0.15, 0.1 * d.td), SIMD3<Float>(0.05, 0.13, 0.008) * s, chamfer: 0.003 * s, m.coat, orient: q)
        }
        // Ärmel
        for left in [true, false] {
            let k = armThickness(left: left)
            capsule(container(left ? .lUpperArm : .rUpperArm), pv(0, -0.005, 0), pv(0, -0.27, 0), 0.058 * k, m.coat)
            capsule(container(left ? .lForearm : .rForearm), pv(0, 0, 0), pv(0, -0.19, 0), 0.052 * k, m.coat)
        }
        // Schöße (schwingen beim Laufen)
        let count = quality == .performance ? 2 : 3
        let segLen = 0.52 * s / Float(count)
        let panels: [(SIMD3<Float>, Float, Float)] = [
            (pv(0, 0, -0.118 * d.td), 0.3 * d.hw, -1),
            (pv(0.085 * d.hw, 0, 0.1 * d.td), 0.13 * d.hw, 1),
            (pv(-0.085 * d.hw, 0, 0.1 * d.td), 0.13 * d.hw, 1)
        ]
        for (idx, panel) in panels.enumerated() {
            let anchor = SCNNode()
            anchor.simdPosition = panel.0
            hp.addChildNode(anchor)
            var segs: [SCNNode] = []
            var parent = anchor
            for i in 0..<count {
                let seg = SCNNode()
                seg.simdPosition = i == 0 ? SIMD3<Float>(0, 0, 0) : SIMD3<Float>(0, -segLen, 0)
                parent.addChildNode(seg)
                let w = (panel.1 + 0.02 * Float(i)) * s
                box(seg, SIMD3<Float>(0, -segLen * 0.5, 0), SIMD3<Float>(w, segLen * 1.06, 0.01 * s), chamfer: 0.003 * s, m.coat)
                segs.append(seg)
                parent = seg
            }
            swayChains.append(SwayChain(anchor: anchor, segments: segs, ref: joint(.hips), side: panel.2,
                                        minOffset: panel.2 < 0 ? 0.08 : 0.05, stiffness: 10, drag: 0.4, flutter: 0.18,
                                        phase: Float(idx) * 1.1))
        }
    }

    /// Kapuze (nach hinten versetzt, Gesicht bleibt frei) + Überwurf auf den Schultern.
    private func buildHood(_ m: Palette) {
        let d = dims
        let s = d.s
        let hj = container(.head)
        let c = headCenterLocal
        let r = headRadius
        let hs = headScale
        let hoodMat = registerMaterial(look.primaryColor.withBrightness(0.6), rough: 0.85, metal: 0)
        ellipsoid(hj, c + SIMD3<Float>(0, 0.29 * r, -0.62 * r), r * 1.25, SIMD3<Float>(hs.x * 1.1, 1.0, 1.08), hoodMat)
        cone(hj, base: c + SIMD3<Float>(0, 1.05 * r, -0.95 * r), dir: safeNormalize(SIMD3<Float>(0, 0.45, -1)),
             r0: 0.05 * s, r1: 0.004 * s, h: 0.08 * s, hoodMat)
        let ch = container(.chest)
        let nt = 1 + (d.ts - 1) * 0.75
        let mantle = SCNCone(topRadius: CGFloat(0.075 * s * nt), bottomRadius: CGFloat(0.2 * s * d.ws), height: CGFloat(0.13 * s))
        mantle.radialSegmentCount = segRadial
        mantle.materials = [hoodMat]
        let mn = SCNNode(geometry: mantle)
        mn.simdPosition = pv(0, 0.215, -0.02)
        mn.simdScale = SIMD3<Float>(1, 1, 0.75 * d.td)
        ch.addChildNode(mn)
    }

    // MARK: - Zerstückelung

    private var pelvisDetached = false

    private static var stumpMatBlood: SCNMaterial?
    private static var stumpMatDry: SCNMaterial?
    private static var boneMat: SCNMaterial?

    private static func stumpMaterial(blood: Bool) -> SCNMaterial {
        if blood {
            if let m = stumpMatBlood { return m }
            let m = Render.pbr(UIColor(red: 0.3, green: 0.012, blue: 0.022, alpha: 1), roughness: 0.3, metalness: 0,
                               emission: UIColor(red: 0.22, green: 0.0, blue: 0.015, alpha: 1), emissionIntensity: 0.3)
            stumpMatBlood = m
            return m
        }
        if let m = stumpMatDry { return m }
        let m = Render.pbr(UIColor(red: 0.05, green: 0.045, blue: 0.045, alpha: 1), roughness: 0.9, metalness: 0,
                           emission: UIColor(red: 0.6, green: 0.15, blue: 0.02, alpha: 1), emissionIntensity: 0.35)
        stumpMatDry = m
        return m
    }

    private static func boneMaterial() -> SCNMaterial {
        if let m = boneMat { return m }
        let m = Render.pbr(UIColor(red: 0.86, green: 0.82, blue: 0.74, alpha: 1), roughness: 0.55, metalness: 0)
        boneMat = m
        return m
    }

    private func rootJoint(of limb: Limb) -> Joint {
        switch limb {
        case .head: return .neck
        case .leftArm: return .lUpperArm
        case .rightArm: return .rUpperArm
        case .leftLeg: return .lThigh
        case .rightLeg: return .rThigh
        case .upperBody: return .spine
        }
    }

    /// true, wenn das Gelenk oder eines seiner Elterngelenke ausgeblendet ist.
    private func isEffectivelyHidden(_ j: Joint) -> Bool {
        var cur: Joint? = j
        while let c = cur {
            if joints[c]?.isHidden == true { return true }
            cur = c.rigParent
        }
        return false
    }

    /// Endpunkte (Welt) und Radius der vereinfachten Kollisionsform eines abgetrennten Teils.
    private func limbSegment(_ limb: Limb) -> (start: SIMD3<Float>, end: SIMD3<Float>, radius: Float, mass: Float) {
        let d = dims
        let s = d.s
        switch limb {
        case .head:
            let a = joint(.neck).simdWorldPosition
            let b = joint(.head).simdConvertPosition(SIMD3<Float>(0, 0.21 * s * d.head, 0.005 * s), to: nil)
            return (a, b, 0.1 * s * d.head, 4.5 * s)
        case .leftArm, .rightArm:
            let left = limb == .leftArm
            let a = joint(left ? .lUpperArm : .rUpperArm).simdWorldPosition
            let b = joint(left ? .lHand : .rHand).simdConvertPosition(SIMD3<Float>(0, -0.1 * s, 0), to: nil)
            return (a, b, 0.052 * s * d.ts, 4.0 * s * d.ts)
        case .leftLeg, .rightLeg:
            let left = limb == .leftLeg
            let a = joint(left ? .lThigh : .rThigh).simdWorldPosition
            let b = joint(left ? .lFoot : .rFoot).simdConvertPosition(SIMD3<Float>(0, -0.04 * s, 0.06 * s), to: nil)
            return (a, b, 0.072 * s * d.ts, 10 * s * d.ts)
        case .upperBody:
            let a = joint(.spine).simdWorldPosition
            let b = joint(.neck).simdConvertPosition(SIMD3<Float>(0, 0.12 * s, 0), to: nil)
            return (a, b, 0.17 * s * d.ws, 32 * s * d.ts)
        }
    }

    /// Schnittfläche (rot-schwarze Scheibe + Knochen), optional mit kurzem Blutstrahl.
    @discardableResult
    private func addCutCap(to parent: SCNNode, at pos: SIMD3<Float>, orient: simd_quatf?, radius: Float, sign: Float,
                           bloodEnabled: Bool, gush: Bool, bone: Bool, scene: SCNScene?) -> SCNNode {
        let cap = SCNNode()
        cap.name = "rig.stump"
        cap.simdPosition = pos
        if let q = orient { cap.simdOrientation = q }
        parent.addChildNode(cap)
        let disc = SCNCylinder(radius: CGFloat(radius), height: CGFloat(radius * 0.22))
        disc.radialSegmentCount = 20
        disc.materials = [CharacterRig.stumpMaterial(blood: bloodEnabled)]
        let dn = SCNNode(geometry: disc)
        dn.simdPosition = SIMD3<Float>(0, sign * radius * 0.04, 0)
        dn.castsShadow = false
        cap.addChildNode(dn)
        if bone {
            let b = SCNCylinder(radius: CGFloat(radius * 0.26), height: CGFloat(radius * 0.3))
            b.radialSegmentCount = 12
            b.materials = [CharacterRig.boneMaterial()]
            let bn = SCNNode(geometry: b)
            bn.simdPosition = SIMD3<Float>(0, sign * radius * 0.07, 0)
            bn.castsShadow = false
            cap.addChildNode(bn)
        }
        if gush && bloodEnabled {
            let p = SCNParticleSystem()
            p.loops = false
            p.emissionDuration = 1.4
            p.birthRate = CGFloat(110 * particleScale)
            p.particleLifeSpan = 0.75
            p.particleLifeSpanVariation = 0.3
            p.particleVelocity = CGFloat(1.7 * dims.s)
            p.particleVelocityVariation = 0.9
            p.emittingDirection = SCNVector3(x: 0, y: sign, z: 0)
            p.spreadingAngle = 22
            p.isAffectedByGravity = true
            p.particleSize = CGFloat(0.02 * dims.s)
            p.particleSizeVariation = CGFloat(0.012 * dims.s)
            p.particleColor = UIColor(red: 0.4, green: 0.0, blue: 0.02, alpha: 1)
            p.particleImage = ProceduralTextures.softDisc()
            p.blendMode = .alpha
            cap.addParticleSystem(p)
        }
        return cap
    }

    private func registerDebris(_ n: SCNNode) {
        ownDebris.append(n)
        CharacterRig.liveDebris = CharacterRig.liveDebris.filter { $0.parent != nil }
        CharacterRig.liveDebris.append(n)
        while CharacterRig.liveDebris.count > CharacterRig.maxLiveDebris {
            let old = CharacterRig.liveDebris.removeFirst()
            old.removeAllActions()
            old.removeFromParentNode()
        }
        n.runAction(SCNAction.sequence([SCNAction.wait(duration: 11),
                                        SCNAction.fadeOut(duration: 1.0),
                                        SCNAction.removeFromParentNode()]))
    }

    /// Klont den Teilbaum `jn` als freies Physik-Trümmerteil in die Szene.
    private func spawnDebris(from jn: SCNNode, start: SIMD3<Float>, end: SIMD3<Float>, radius: Float, mass: Float,
                             sphere: Bool, stripChildJoints: Bool, impulse: SIMD3<Float>, capSign: Float,
                             scene: SCNScene, bloodEnabled: Bool) -> SCNNode {
        let axisRaw = end - start
        var len = simd_length(axisRaw)
        if !len.isFinite || len < 0.01 { len = 0.01 }
        var center = (start + end) * 0.5
        if !(center.x.isFinite && center.y.isFinite && center.z.isFinite) { center = jn.simdWorldPosition }

        let wrapper = SCNNode()
        wrapper.name = "rig.debris"
        scene.rootNode.addChildNode(wrapper)
        var m = simd_float4x4(CharacterRig.rotation(from: SIMD3<Float>(0, 1, 0), to: axisRaw))
        m.columns.3 = SIMD4<Float>(center.x, center.y, center.z, 1)
        wrapper.simdWorldTransform = m

        let visual = jn.clone()
        visual.isHidden = false
        if stripChildJoints {
            for child in visual.childNodes {
                let nm = child.name ?? ""
                if nm.hasPrefix("rig.") && nm != "rig.vis" {
                    child.removeFromParentNode()
                }
            }
        }
        visual.enumerateHierarchy { n, _ in
            n.removeAllParticleSystems()
            n.light = nil
        }
        wrapper.addChildNode(visual)
        visual.simdWorldTransform = jn.simdWorldTransform
        // Schnittfläche am abgetrennten Teil
        addCutCap(to: visual, at: SIMD3<Float>(0, 0, 0), orient: nil, radius: radius * 0.9, sign: capSign,
                  bloodEnabled: bloodEnabled, gush: false, bone: !sphere, scene: nil)

        // Vereinfachte Kollisionsform (Kugel / Kapsel), NICHT aus der Geometrie
        let shapeGeometry: SCNGeometry
        if sphere {
            shapeGeometry = SCNSphere(radius: CGFloat(Swift.max(0.03, len * 0.5)))
        } else {
            shapeGeometry = SCNCapsule(capRadius: CGFloat(radius), height: CGFloat(len + 2 * radius))
        }
        let body = SCNPhysicsBody(type: .dynamic, shape: SCNPhysicsShape(geometry: shapeGeometry, options: nil))
        body.mass = CGFloat(Swift.max(0.5, mass))
        body.friction = 0.9
        body.restitution = 0.12
        body.damping = 0.08
        body.angularDamping = 0.35
        body.continuousCollisionDetectionThreshold = CGFloat(radius * 0.5)
        wrapper.physicsBody = body

        var v = impulse
        if !(v.x.isFinite && v.y.isFinite && v.z.isFinite) { v = SIMD3<Float>(0, 3, 0) }
        let vl = simd_length(v)
        if vl > 22 { v = v * (22 / vl) }
        body.velocity = SCNVector3(x: v.x, y: v.y, z: v.z)
        let spinAxis = randUnit3()
        let spin = randf(4, 11)
        body.angularVelocity = SCNVector4(x: spinAxis.x, y: spinAxis.y, z: spinAxis.z, w: spin)

        registerDebris(wrapper)
        return wrapper
    }

    /// Trennt ein Körperteil ab: Klon mit Physik in die Szene, Original ausblenden, Stumpf + Blut.
    /// impulse ≈ Abfluggeschwindigkeit in m/s (wird auf 22 m/s begrenzt).
    @discardableResult
    func detach(_ limb: Limb, impulse: SIMD3<Float>, in scene: SCNScene, bloodEnabled: Bool) -> SCNNode? {
        if detachedLimbs.contains(limb) || pelvisDetached { return nil }
        let rj = rootJoint(of: limb)
        guard let jn = joints[rj], !isEffectivelyHidden(rj) else { return nil }
        detachedLimbs.insert(limb)

        let seg = limbSegment(limb)
        let isLimb = limb != .head && limb != .upperBody
        // Teil zeigt bei Gliedmaßen entlang -Y vom Gelenk weg, bei Kopf/Oberkörper entlang +Y
        let partSign: Float = isLimb ? -1 : 1
        let cutWorld = jn.simdWorldPosition
        let cutOrientation = jn.simdWorldOrientation

        let piece = spawnDebris(from: jn, start: seg.start, end: seg.end, radius: seg.radius, mass: seg.mass,
                                sphere: limb == .head, stripChildJoints: false, impulse: impulse, capSign: -partSign,
                                scene: scene, bloodEnabled: bloodEnabled)
        jn.isHidden = true

        // Stumpf am Körper
        if let parentJoint = rj.rigParent, let pn = joints[parentJoint] {
            let capRadius: Float
            switch limb {
            case .head: capRadius = 0.05 * dims.s * (1 + (dims.ts - 1) * 0.75)
            case .upperBody: capRadius = 0.13 * dims.s * dims.ws
            default: capRadius = seg.radius
            }
            let cap = addCutCap(to: pn, at: restPositions[rj] ?? jn.simdPosition, orient: jn.simdOrientation,
                                radius: capRadius, sign: partSign, bloodEnabled: bloodEnabled, gush: true,
                                bone: limb != .upperBody, scene: scene)
            stumpNodes.append(cap)
        }

        // Blut / Ersatzeffekt
        let out = safeNormalize(cutOrientation.act(SIMD3<Float>(0, partSign, 0)) + SIMD3<Float>(0, 0.6, 0),
                                fallback: SIMD3<Float>(0, 1, 0))
        if bloodEnabled {
            FX.spawn(.bloodSpray, at: cutWorld, in: scene, direction: out, scale: limb == .upperBody ? 1.5 : 1.1)
            FX.spawn(.bloodSpray, at: cutWorld, in: scene, direction: safeNormalize(-out + SIMD3<Float>(0, 0.8, 0)), scale: 0.6)
            let ground = SIMD3<Float>(cutWorld.x, node.simdWorldPosition.y + 0.01, cutWorld.z)
            FX.spawn(.bloodPool, at: ground, in: scene, scale: limb == .upperBody ? 1.6 : 1.0)
        } else {
            FX.spawn(.smoke, at: cutWorld, in: scene, direction: out, scale: 0.6)
            FX.spawn(.sparks, at: cutWorld, in: scene, direction: out, scale: 0.8)
        }
        return piece
    }

    /// Zerplatzt in Einzelteile (Kopf, Arme, Beine, Oberkörper, Becken).
    func detachAll(impulseScale: Float, in scene: SCNScene, bloodEnabled: Bool) {
        var k = impulseScale.isFinite ? impulseScale : 1
        k = Swift.max(0, Swift.min(k, 4))
        let center = joint(.spine).simdWorldPosition
        let order: [Limb] = [.head, .leftArm, .rightArm, .leftLeg, .rightLeg]
        for limb in order {
            let p = joint(rootJoint(of: limb)).simdWorldPosition
            var dir = safeNormalize(p - center, fallback: randUnit3())
            dir.y = abs(dir.y) + 0.55
            dir = safeNormalize(dir + randUnit3() * 0.25, fallback: SIMD3<Float>(0, 1, 0))
            detach(limb, impulse: dir * (4.5 * k), in: scene, bloodEnabled: bloodEnabled)
        }
        let torsoDir = safeNormalize(randUnit3() * 0.5 + SIMD3<Float>(0, 1, 0), fallback: SIMD3<Float>(0, 1, 0))
        detach(.upperBody, impulse: torsoDir * (3.2 * k), in: scene, bloodEnabled: bloodEnabled)

        // Becken als letztes Stück
        if !pelvisDetached, let hips = joints[.hips], !hips.isHidden {
            pelvisDetached = true
            let s = dims.s
            let a = hips.simdConvertPosition(SIMD3<Float>(0, 0.06 * s, 0), to: nil)
            let b = hips.simdConvertPosition(SIMD3<Float>(0, -0.1 * s, 0), to: nil)
            let pDir = safeNormalize(randUnit3() * 0.4 + SIMD3<Float>(0, 1, 0), fallback: SIMD3<Float>(0, 1, 0))
            _ = spawnDebris(from: hips, start: a, end: b, radius: 0.14 * s * dims.hw, mass: 14 * s,
                            sphere: false, stripChildJoints: true, impulse: pDir * (2.5 * k), capSign: 1,
                            scene: scene, bloodEnabled: bloodEnabled)
            hips.isHidden = true
        }
        if bloodEnabled {
            FX.spawn(.bloodBurst, at: center, in: scene, scale: 1.6)
            FX.spawn(.bloodPool, at: SIMD3<Float>(center.x, node.simdWorldPosition.y + 0.01, center.z), in: scene, scale: 2.0)
        } else {
            FX.spawn(.smoke, at: center, in: scene, scale: 1.4)
        }
    }

    /// Neue Runde: alles wieder anfügen/einblenden, Trümmer entfernen, Material normal.
    func resetBody() {
        for (_, n) in joints { n.isHidden = false }
        for n in stumpNodes { n.removeFromParentNode() }
        stumpNodes.removeAll()
        for n in ownDebris {
            n.removeAllActions()
            n.removeFromParentNode()
        }
        ownDebris.removeAll()
        CharacterRig.liveDebris = CharacterRig.liveDebris.filter { $0.parent != nil }
        detachedLimbs.removeAll()
        pelvisDetached = false
        flashAmount = 0
        matState = .normal
        matAmount = 0
        crackHeat = 0
        node.isHidden = false
        node.opacity = 1
        for c in swayChains { c.reset() }
        refreshMaterials()
    }
}

// =====================================================================
// MARK: - Audio/AudioDirector.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – AudioDirector
//  100 % prozedurales Audio, keine Dateien:
//   • Soundeffekte werden zur Laufzeit synthetisiert (Rauschen, Filter,
//     Pitch-Sweeps, FM, Hüllkurven), als AVAudioPCMBuffer gecacht und über
//     einen Pool von AVAudioPlayerNodes abgespielt.
//   • Musik: pro MusicMood ein nahtloser Loop (Drones, Pads, Bass, Taiko,
//     Chor, Arpeggien …), einmalig im Hintergrund gerendert und mit
//     Lautstärke-Rampen überblendet.
//   • Sprache: AVSpeechSynthesizer (de-DE) – Ansager + Dialogstimmen.
//  Alle öffentlichen Methoden nur vom Main-Thread aufrufen.
// =====================================================================

final class AudioDirector {

    static let shared = AudioDirector()

    // MARK: - Konstanten & Hilfstypen

    private static let sfxVoiceCount = 14
    private static let musicVoiceCount = 3
    private static let maxPitchedFrames = 2_500_000      // ≈ 10 MB für tonhöhenverschobene Varianten
    private static let deferredPlayWindow: Double = 0.35

    private struct SfxKey: Hashable {
        let name: String
        let variant: Int
    }

    private struct PitchedKey: Hashable {
        let key: SfxKey
        let step: Int
    }

    private struct DeferredPlay {
        let key: SfxKey
        let volume: Float
        let pitch: Float
        let time: Double
    }

    // MARK: - Engine-Graph

    private let engine = AVAudioEngine()
    private let sfxMixer = AVAudioMixerNode()
    private let sfxEQ = AVAudioUnitEQ(numberOfBands: 2)
    private let musicMixer = AVAudioMixerNode()
    private let musicVarispeed = AVAudioUnitVarispeed()
    private let musicEQ = AVAudioUnitEQ(numberOfBands: 2)
    private var sfxPlayers: [AVAudioPlayerNode] = []
    private var sfxBusyUntil: [Double] = []
    private var sfxStartedAt: [Double] = []
    private var musicPlayers: [AVAudioPlayerNode] = []
    private var musicLevel: [Float] = []
    private var musicTarget: [Float] = []
    private var activeMusic = 0
    private var musicFadeRate: Float = 0.5
    private let monoFormat: AVAudioFormat?
    private let stereoFormat: AVAudioFormat?
    private var graphBuilt = false
    private var observersInstalled = false
    private var observerTokens: [NSObjectProtocol] = []
    private var tickTimer: Timer?
    private var lastTick: Double = 0
    private var lastStartAttempt: Double = -10
    private var needsMusicRefresh = false
    private var musicRetryClock: Float = 0

    // MARK: - Zustand

    private var settings = GameSettings()
    private var requestedMood: MusicMood = MusicMood.none
    private var playingMood: MusicMood = MusicMood.none

    // SFX-Caches
    private var sfxCache: [SfxKey: AVAudioPCMBuffer] = [:]
    private var pitchedCache: [PitchedKey: AVAudioPCMBuffer] = [:]
    private var pitchedFrames = 0
    private var sfxPending: Set<SfxKey> = []
    private var sfxQueueList: [SfxKey] = []
    private var sfxJobInFlight = false
    private var deferredPlays: [DeferredPlay] = []
    private var lastPlayTime: [SoundEffect: Double] = [:]
    private var lastVariant: [SoundEffect: Int] = [:]
    private var prewarmStarted = false

    // Musik-Cache
    private var musicCache: [MusicMood: AVAudioPCMBuffer] = [:]
    private var musicWanted: [MusicMood] = []
    private var musicJobInFlight = false
    private var musicJobMood: MusicMood = MusicMood.none
    private var musicPrewarmPending = false

    private let synthQueue = DispatchQueue(label: "silkstrike.audio.sfx", qos: .utility)
    private let musicQueue = DispatchQueue(label: "silkstrike.audio.music", qos: .userInitiated)

    // Zeitlupe / Ducking
    private var slowTarget: Float = 1
    private var slowCurrent: Float = 1
    private var appliedSlow: Float = -1
    private var sfxSlowPitch: Float = 1
    private var duck: Float = 1
    private var appliedSfxVolume: Float = -1
    private var appliedMusicVolume: Float = -1

    // Sprache
    private let announcer = AVSpeechSynthesizer()
    private let dialog = AVSpeechSynthesizer()
    private var voicesLoaded = false
    private var maleVoice: AVSpeechSynthesisVoice?
    private var femaleVoice: AVSpeechSynthesisVoice?
    private var anyGermanVoice: AVSpeechSynthesisVoice?

    private init() {
        monoFormat = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 1)
        stereoFormat = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)
    }

    // MARK: - Öffentliche API

    /// Audio-Session + Engine starten. Mehrfach aufrufbar (z. B. bei jeder Rückkehr in den Vordergrund).
    func start() {
        configureSession()
        buildGraphIfNeeded()
        installObserversIfNeeded()
        _ = startEngine(force: true)
        startTimerIfNeeded()
        Haptics.prepare()
        if !prewarmStarted {
            prewarmStarted = true
            beginPrewarm()
        }
        needsMusicRefresh = false
        refreshMusic()
    }

    func apply(_ newSettings: GameSettings) {
        settings = newSettings
        applyVolumes(force: true)
        if !newSettings.voicesEnabled { stopSpeech() }
        refreshMusic()
    }

    /// Spielt einen synthetisierten Soundeffekt. volume 0…1, pitch 0.25…4 (1 = Original).
    func play(_ sfx: SoundEffect, volume: Float = 1, pitch: Float = 1) {
        guard graphBuilt, settings.sfxVolume > 0.001, volume > 0.001 else { return }
        let now = CACurrentMediaTime()
        if let last = lastPlayTime[sfx], now - last < 0.025 { return }   // identische Doppel-Trigger im selben Frame
        lastPlayTime[sfx] = now

        let count = AudioSFXSynth.variantCount(sfx)
        var variant = 0
        if count > 1 {
            variant = Int.random(in: 0..<count)
            if let lastV = lastVariant[sfx], lastV == variant { variant = (variant + 1) % count }
            lastVariant[sfx] = variant
        }
        var p = pitch.isFinite ? pitch : 1
        if AudioSFXSynth.jitters(sfx) { p *= Float.random(in: 0.965...1.035) }
        let v = (volume.isFinite ? volume : 1) * AudioSFXSynth.mixLevel(sfx)
        playKey(SfxKey(name: sfx.rawValue, variant: variant), volume: v, pitch: p, now: now)
    }

    /// Prozedurale Musik je Stimmung (nahtloser Loop, Überblendung).
    func setMusic(_ mood: MusicMood) {
        requestedMood = mood
        refreshMusic()
    }

    /// Tiefer, dramatischer Ansager (deutsch) + dumpfer Kino-Schlag.
    func announce(_ text: String) {
        playKey(SfxKey(name: AudioSFXSynth.announceBoomName, variant: 0), volume: 0.7, pitch: 1, now: CACurrentMediaTime())
        guard settings.voicesEnabled else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let utterance = AVSpeechUtterance(string: AudioDirector.speechText(trimmed))
        utterance.voice = germanVoice(male: true)
        utterance.pitchMultiplier = 0.6
        utterance.rate = AudioDirector.clampRate(AVSpeechUtteranceDefaultSpeechRate * 0.82)
        utterance.volume = 1
        utterance.preUtteranceDelay = 0.04
        _ = announcer.stopSpeaking(at: .immediate)
        announcer.speak(utterance)
    }

    /// Dialogzeile mit Stimmlage der Figur (nil = Erzähler).
    func speak(_ text: String, as cast: CastMember?) {
        guard settings.voicesEnabled else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        var pitch: Float = 0.82
        var rate: Float = 0.46
        var male = true
        if let c = cast {
            let (vp, vr) = Roster.voice(for: c)
            pitch = vp
            rate = vr
            male = AudioDirector.isMaleCast(c)
        }
        let utterance = AVSpeechUtterance(string: AudioDirector.speechText(trimmed))
        utterance.voice = germanVoice(male: male)
        utterance.pitchMultiplier = max(0.5, min(2.0, pitch.isFinite ? pitch : 1))
        utterance.rate = AudioDirector.clampRate(rate.isFinite ? rate : 0.48)
        utterance.volume = 1
        _ = dialog.stopSpeaking(at: .immediate)
        dialog.speak(utterance)
    }

    func stopSpeech() {
        _ = announcer.stopSpeaking(at: .immediate)
        _ = dialog.stopSpeaking(at: .immediate)
    }

    var isSpeaking: Bool {
        return announcer.isSpeaking || dialog.isSpeaking
    }

    /// 1 = normal, < 1 = Zeitlupe: Musik wird langsamer/tiefer und dumpfer, Effekte tiefer und wuchtiger.
    func setSlowMotion(_ factor: Float) {
        let f = factor.isFinite ? factor : 1
        slowTarget = max(0.05, min(1, f))
    }

    // Zusätzliche Helfer (optional nutzbar)

    var currentMood: MusicMood { return requestedMood }

    /// Stoppt sofort alle laufenden Soundeffekte (z. B. beim Szenenwechsel).
    func stopAllEffects() {
        for p in sfxPlayers { p.stop() }
        for i in 0..<sfxBusyUntil.count { sfxBusyUntil[i] = 0 }
        deferredPlays.removeAll()
    }

    // MARK: - Session & Graph

    private func configureSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try? session.setPreferredIOBufferDuration(0.006)
        try? session.setActive(true)
    }

    private func buildGraphIfNeeded() {
        guard !graphBuilt, let mono = monoFormat, let stereo = stereoFormat else { return }
        graphBuilt = true

        engine.attach(sfxMixer)
        engine.attach(sfxEQ)
        engine.attach(musicMixer)
        engine.attach(musicVarispeed)
        engine.attach(musicEQ)

        for _ in 0..<AudioDirector.sfxVoiceCount {
            let p = AVAudioPlayerNode()
            engine.attach(p)
            engine.connect(p, to: sfxMixer, format: mono)
            sfxPlayers.append(p)
            sfxBusyUntil.append(0)
            sfxStartedAt.append(0)
        }
        for _ in 0..<AudioDirector.musicVoiceCount {
            let p = AVAudioPlayerNode()
            engine.attach(p)
            engine.connect(p, to: musicMixer, format: stereo)
            p.volume = 0
            musicPlayers.append(p)
            musicLevel.append(0)
            musicTarget.append(0)
        }

        let main = engine.mainMixerNode
        engine.connect(sfxMixer, to: sfxEQ, format: stereo)
        engine.connect(sfxEQ, to: main, format: stereo)
        engine.connect(musicMixer, to: musicVarispeed, format: stereo)
        engine.connect(musicVarispeed, to: musicEQ, format: stereo)
        engine.connect(musicEQ, to: main, format: stereo)
        main.outputVolume = 1

        let sb = sfxEQ.bands
        if sb.count >= 2 {
            sb[0].filterType = .lowShelf
            sb[0].frequency = 140
            sb[0].gain = 0
            sb[0].bypass = false
            sb[1].filterType = .lowPass
            sb[1].frequency = 18000
            sb[1].bypass = true
        }
        let mb = musicEQ.bands
        if mb.count >= 2 {
            mb[0].filterType = .lowPass
            mb[0].frequency = 18000
            mb[0].bypass = true
            mb[1].filterType = .lowShelf
            mb[1].frequency = 120
            mb[1].gain = 0
            mb[1].bypass = false
        }
        musicVarispeed.rate = 1
        applyVolumes(force: true)
        engine.prepare()
    }

    /// Startet die Engine falls nötig. Bei einem echten (Neu-)Start werden alle Player zurückgesetzt.
    private func startEngine(force: Bool) -> Bool {
        guard graphBuilt else { return false }
        if engine.isRunning { return true }
        let now = CACurrentMediaTime()
        if !force && now - lastStartAttempt < 1.0 { return false }
        lastStartAttempt = now
        do {
            try engine.start()
        } catch {
            return false
        }
        guard engine.isRunning else { return false }
        for p in sfxPlayers { p.stop() }
        for i in 0..<sfxBusyUntil.count { sfxBusyUntil[i] = 0 }
        for p in musicPlayers {
            p.stop()
            p.volume = 0
        }
        for i in 0..<musicLevel.count {
            musicLevel[i] = 0
            musicTarget[i] = 0
        }
        playingMood = MusicMood.none
        needsMusicRefresh = true
        return true
    }

    private func installObserversIfNeeded() {
        guard !observersInstalled else { return }
        observersInstalled = true
        let nc = NotificationCenter.default
        let t1 = nc.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            self?.handleEngineReset()
        }
        let t2 = nc.addObserver(forName: AVAudioSession.interruptionNotification,
                                object: AVAudioSession.sharedInstance(), queue: .main) { [weak self] note in
            self?.handleInterruption(note)
        }
        observerTokens = [t1, t2]
    }

    private func handleEngineReset() {
        lastStartAttempt = -10
        if startEngine(force: true) {
            needsMusicRefresh = false
            refreshMusic()
        }
    }

    private func handleInterruption(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        if type == .ended {
            try? AVAudioSession.sharedInstance().setActive(true)
            handleEngineReset()
        }
    }

    private func startTimerIfNeeded() {
        guard tickTimer == nil else { return }
        lastTick = CACurrentMediaTime()
        let t = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        RunLoop.main.add(t, forMode: .common)
        tickTimer = t
    }

    // MARK: - Lautstärken

    private func applyVolumes(force: Bool) {
        let sv = max(0, min(1, settings.sfxVolume)) * 0.9
        let mv = (settings.musicEnabled ? max(0, min(1, settings.musicVolume)) : 0) * duck
        if force || abs(sv - appliedSfxVolume) > 0.001 {
            sfxMixer.outputVolume = sv
            appliedSfxVolume = sv
        }
        if force || abs(mv - appliedMusicVolume) > 0.001 {
            musicMixer.outputVolume = mv
            appliedMusicVolume = mv
        }
    }

    // MARK: - Tick (Fades, Zeitlupe, Ducking) – 30 Hz auf dem Main-RunLoop

    private func tick() {
        let now = CACurrentMediaTime()
        var dt = Float(now - lastTick)
        lastTick = now
        if !(dt > 0) || dt > 0.25 { dt = 1.0 / 30.0 }

        if needsMusicRefresh {
            needsMusicRefresh = false
            refreshMusic()
        }

        // Musik-Überblendungen
        for i in 0..<musicPlayers.count {
            let target = musicTarget[i]
            var lvl = musicLevel[i]
            if lvl != target {
                let step = musicFadeRate * dt
                if lvl < target {
                    lvl = min(target, lvl + step)
                } else {
                    lvl = max(target, lvl - step * 1.25)
                }
                musicLevel[i] = lvl
                musicPlayers[i].volume = lvl * lvl * (3 - 2 * lvl)
                if lvl <= 0.0001 && target <= 0 {
                    musicPlayers[i].stop()
                }
            }
        }

        // Musik leiser, während gesprochen wird
        let duckTarget: Float = isSpeaking ? 0.55 : 1
        duck += (duckTarget - duck) * min(1, dt * 5)
        applyVolumes(force: false)

        // Zeitlupe weich nachführen (kein Zippern bei Hit-Stops)
        slowCurrent += (slowTarget - slowCurrent) * min(1, dt * 7)
        if abs(slowCurrent - appliedSlow) > 0.002 {
            applySlowMotionParams(slowCurrent)
        }

        // Verfallene Wartende entfernen
        if !deferredPlays.isEmpty {
            deferredPlays.removeAll { now - $0.time > AudioDirector.deferredPlayWindow }
        }

        // Gelegentlich prüfen, ob die gewünschte Musik läuft (z. B. nach fehlgeschlagenem Engine-Start)
        musicRetryClock += dt
        if musicRetryClock > 1.2 {
            musicRetryClock = 0
            let desired = desiredMood
            if desired != playingMood, musicCache[desired] != nil {
                refreshMusic()
            }
        }
    }

    private func applySlowMotionParams(_ s: Float) {
        appliedSlow = s
        let amount = max(0, min(1, (1 - s) / 0.9))     // 0 = normal, 1 = extreme Zeitlupe
        musicVarispeed.rate = 1 - 0.36 * amount
        sfxSlowPitch = 1 - 0.3 * amount
        let mb = musicEQ.bands
        if mb.count >= 2 {
            if amount < 0.01 {
                mb[0].bypass = true
                mb[1].gain = 0
            } else {
                mb[0].bypass = false
                mb[0].frequency = 450 + 17500 * pow(1 - amount, 2.2)
                mb[1].gain = 4 * amount
            }
        }
        let sb = sfxEQ.bands
        if sb.count >= 2 {
            sb[0].gain = 5 * amount
            if amount < 0.01 {
                sb[1].bypass = true
            } else {
                sb[1].bypass = false
                sb[1].frequency = 2800 + 16000 * pow(1 - amount, 1.5)
            }
        }
    }

    // MARK: - SFX-Wiedergabe

    private func playKey(_ key: SfxKey, volume: Float, pitch: Float, now: Double) {
        guard graphBuilt else { return }
        guard let base = baseBuffer(for: key) else {
            deferredPlays.append(DeferredPlay(key: key, volume: volume, pitch: pitch, time: now))
            if deferredPlays.count > 16 { deferredPlays.removeFirst() }
            return
        }
        guard startEngine(force: false) else { return }
        let effPitch = max(0.25, min(4, pitch * sfxSlowPitch))
        let buffer = pitchedBuffer(base: base, key: key, pitch: effPitch)
        guard let idx = pickVoice(now: now) else { return }
        let player = sfxPlayers[idx]
        let duration = Double(buffer.frameLength) / 44100.0
        sfxBusyUntil[idx] = now + duration + 0.02
        sfxStartedAt[idx] = now
        player.volume = max(0, min(1, volume))
        player.pan = Float.random(in: -0.12...0.12)
        player.scheduleBuffer(buffer, at: nil, options: [.interrupts], completionHandler: nil)
        if !player.isPlaying { player.play() }
    }

    private func pickVoice(now: Double) -> Int? {
        let count = sfxPlayers.count
        guard count > 0, sfxBusyUntil.count == count, sfxStartedAt.count == count else { return nil }
        for i in 0..<count where sfxBusyUntil[i] <= now {
            return i
        }
        // Alle belegt: ältesten Sound stehlen
        var oldest = 0
        for i in 1..<count where sfxStartedAt[i] < sfxStartedAt[oldest] {
            oldest = i
        }
        return oldest
    }

    private func baseBuffer(for key: SfxKey) -> AVAudioPCMBuffer? {
        if let b = sfxCache[key] { return b }
        if AudioSFXSynth.isLong(key.name) {
            enqueueSynth(key, front: true)
            return nil
        }
        // Kurze Sounds: sofort synchron erzeugen (dauert nur Millisekunden)
        let samples = AudioSFXSynth.render(name: key.name, variant: key.variant)
        guard let b = AudioDirector.makeBuffer(mono: samples, format: monoFormat) else { return nil }
        sfxCache[key] = b
        if sfxPending.contains(key), let i = sfxQueueList.firstIndex(of: key) {
            sfxQueueList.remove(at: i)
            sfxPending.remove(key)
        }
        return b
    }

    private func pitchedBuffer(base: AVAudioPCMBuffer, key: SfxKey, pitch: Float) -> AVAudioPCMBuffer {
        let step = Int((pitch * 50).rounded())
        if step == 50 || step <= 0 { return base }
        let pk = PitchedKey(key: key, step: step)
        if let b = pitchedCache[pk] { return b }
        guard let b = resample(base, ratio: Float(step) / 50) else { return base }
        if pitchedFrames + Int(b.frameLength) > AudioDirector.maxPitchedFrames {
            pitchedCache.removeAll()
            pitchedFrames = 0
        }
        pitchedCache[pk] = b
        pitchedFrames += Int(b.frameLength)
        return b
    }

    /// Lineare Neuabtastung: ratio > 1 = höher/kürzer, < 1 = tiefer/länger.
    private func resample(_ src: AVAudioPCMBuffer, ratio: Float) -> AVAudioPCMBuffer? {
        guard ratio > 0.05, let fmt = monoFormat, let sp = src.floatChannelData else { return nil }
        let n = Int(src.frameLength)
        guard n > 1 else { return nil }
        let outN = max(1, Int(Double(n - 1) / Double(ratio)))
        guard let out = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(outN)),
              let dp = out.floatChannelData else { return nil }
        out.frameLength = AVAudioFrameCount(outN)
        let s = sp[0]
        let d = dp[0]
        let r = Double(ratio)
        for i in 0..<outN {
            let p = Double(i) * r
            let i0 = min(Int(p), n - 1)
            let i1 = min(i0 + 1, n - 1)
            let f = Float(p - Double(i0))
            let a = s[i0]
            d[i] = a + (s[i1] - a) * f
        }
        return out
    }

    // MARK: - Hintergrund-Synthese (SFX)

    private func beginPrewarm() {
        // Häufige Kampf- und UI-Sounds zuerst
        let order: [SoundEffect] = [
            .punchLight, .punchHeavy, .kick, .block, .whoosh, .uiSelect, .uiConfirm, .uiBack,
            .webShoot, .webZip, .swingRelease, .land, .boneCrack, .gore, .slice, .bodyFall,
            .metalHit, .heartbeat, .thunder, .fire, .ice, .electric, .explosion, .teleport,
            .chain, .roar, .riftHum, .crowd
        ]
        var all = order
        for s in SoundEffect.allCases where !all.contains(s) { all.append(s) }
        for s in all {
            for v in 0..<AudioSFXSynth.variantCount(s) {
                enqueueSynth(SfxKey(name: s.rawValue, variant: v), front: false)
            }
        }
        enqueueSynth(SfxKey(name: AudioSFXSynth.announceBoomName, variant: 0), front: false)

        // Musik-Vorrat: nach dem ersten angeforderten Stück (oder spätestens nach 4 s)
        musicPrewarmPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
            self?.flushMusicPrewarm()
        }
    }

    private func enqueueSynth(_ key: SfxKey, front: Bool) {
        if sfxCache[key] != nil { return }
        if sfxPending.contains(key) {
            if front, let i = sfxQueueList.firstIndex(of: key) {
                sfxQueueList.remove(at: i)
                sfxQueueList.insert(key, at: 0)
            }
            return
        }
        sfxPending.insert(key)
        if front {
            sfxQueueList.insert(key, at: 0)
        } else {
            sfxQueueList.append(key)
        }
        pumpSynthQueue()
    }

    private func pumpSynthQueue() {
        guard !sfxJobInFlight else { return }
        while !sfxQueueList.isEmpty {
            let next = sfxQueueList.removeFirst()
            if sfxCache[next] != nil {
                sfxPending.remove(next)
                continue
            }
            sfxJobInFlight = true
            let fmt = monoFormat
            synthQueue.async { [weak self] in
                let samples = AudioSFXSynth.render(name: next.name, variant: next.variant)
                let buffer = AudioDirector.makeBuffer(mono: samples, format: fmt)
                DispatchQueue.main.async {
                    self?.finishSynthJob(next, buffer)
                }
            }
            return
        }
    }

    private func finishSynthJob(_ key: SfxKey, _ buffer: AVAudioPCMBuffer?) {
        sfxJobInFlight = false
        sfxPending.remove(key)
        if let b = buffer, sfxCache[key] == nil {
            sfxCache[key] = b
        }
        if !deferredPlays.isEmpty, sfxCache[key] != nil {
            let now = CACurrentMediaTime()
            let ready = deferredPlays.filter { $0.key == key }
            if !ready.isEmpty {
                deferredPlays.removeAll { $0.key == key }
                for d in ready where now - d.time < AudioDirector.deferredPlayWindow {
                    playKey(d.key, volume: d.volume, pitch: d.pitch, now: now)
                }
            }
        }
        pumpSynthQueue()
    }

    static func makeBuffer(mono samples: [Float], format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, !samples.isEmpty,
              let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(samples.count)),
              let ch = buf.floatChannelData else { return nil }
        buf.frameLength = AVAudioFrameCount(samples.count)
        let dst = ch[0]
        for i in 0..<samples.count { dst[i] = samples[i] }
        return buf
    }

    static func makeBuffer(left: [Float], right: [Float], format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, fmt.channelCount >= 2 else { return nil }
        let n = min(left.count, right.count)
        guard n > 0,
              let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(n)),
              let ch = buf.floatChannelData else { return nil }
        buf.frameLength = AVAudioFrameCount(n)
        let dl = ch[0]
        let dr = ch[1]
        for i in 0..<n {
            dl[i] = left[i]
            dr[i] = right[i]
        }
        return buf
    }

    // MARK: - Musik

    private var desiredMood: MusicMood {
        return settings.musicEnabled ? requestedMood : MusicMood.none
    }

    private func refreshMusic() {
        let desired = desiredMood
        if desired == playingMood {
            if desired != MusicMood.none, engine.isRunning,
               activeMusic < musicPlayers.count, !musicPlayers[activeMusic].isPlaying {
                // Player wurde extern gestoppt → neu ansetzen
                playingMood = MusicMood.none
                transitionMusic(to: desired)
            }
            return
        }
        transitionMusic(to: desired)
    }

    private func transitionMusic(to mood: MusicMood) {
        if mood == MusicMood.none {
            fadeOutAllMusic(seconds: 1.6)
            playingMood = MusicMood.none
            return
        }
        if let buffer = musicCache[mood] {
            crossfade(to: buffer, mood: mood)
        } else {
            // Noch nicht gerendert: altes Stück ausblenden, neues mit Priorität rendern
            if playingMood != MusicMood.none {
                fadeOutAllMusic(seconds: 1.4)
                playingMood = MusicMood.none
            }
            requestMusicRender(mood, urgent: true)
        }
    }

    private func fadeOutAllMusic(seconds: Float) {
        for i in 0..<musicTarget.count { musicTarget[i] = 0 }
        musicFadeRate = 1 / max(0.1, seconds)
    }

    private func crossfade(to buffer: AVAudioPCMBuffer, mood: MusicMood) {
        guard musicPlayers.count >= 2, musicLevel.count == musicPlayers.count else { return }
        guard startEngine(force: false) else { return }
        // Den leisesten freien Player nehmen (kein hartes Abschneiden laufender Ausblendungen)
        var next = -1
        var lowest: Float = 2
        for i in 0..<musicPlayers.count where i != activeMusic {
            if musicLevel[i] < lowest {
                lowest = musicLevel[i]
                next = i
            }
        }
        if next < 0 { next = (activeMusic + 1) % musicPlayers.count }
        let p = musicPlayers[next]
        p.stop()
        p.volume = 0
        musicLevel[next] = 0
        p.scheduleBuffer(buffer, at: nil, options: [.loops], completionHandler: nil)
        p.play()
        for i in 0..<musicTarget.count { musicTarget[i] = 0 }
        musicTarget[next] = 1
        activeMusic = next
        playingMood = mood
        musicFadeRate = 1 / AudioDirector.fadeSeconds(for: mood)
    }

    private static func fadeSeconds(for mood: MusicMood) -> Float {
        switch mood {
        case .none: return 1.5
        case .menu: return 2.4
        case .roam: return 2.0
        case .tension: return 2.0
        case .combat: return 1.0
        case .boss: return 1.0
        case .sad: return 2.6
        case .victory: return 0.6
        }
    }

    private func requestMusicRender(_ mood: MusicMood, urgent: Bool) {
        guard mood != MusicMood.none, musicCache[mood] == nil else { return }
        if musicJobInFlight && musicJobMood == mood { return }
        if let i = musicWanted.firstIndex(of: mood) { musicWanted.remove(at: i) }
        if urgent {
            musicWanted.insert(mood, at: 0)
        } else {
            musicWanted.append(mood)
        }
        if urgent { flushMusicPrewarm() }
        pumpMusicQueue()
    }

    private func flushMusicPrewarm() {
        guard musicPrewarmPending else { return }
        musicPrewarmPending = false
        let list: [MusicMood] = [.combat, .roam, .menu, .tension, .boss, .victory, .sad]
        for m in list where musicCache[m] == nil && !musicWanted.contains(m) {
            if musicJobInFlight && musicJobMood == m { continue }
            musicWanted.append(m)
        }
        pumpMusicQueue()
    }

    private func pumpMusicQueue() {
        guard !musicJobInFlight else { return }
        while !musicWanted.isEmpty {
            let mood = musicWanted.removeFirst()
            if musicCache[mood] != nil || mood == MusicMood.none { continue }
            musicJobInFlight = true
            musicJobMood = mood
            let fmt = stereoFormat
            musicQueue.async { [weak self] in
                let buffer = AudioMusicSynth.render(mood, format: fmt)
                DispatchQueue.main.async {
                    self?.finishMusicJob(mood, buffer)
                }
            }
            return
        }
    }

    private func finishMusicJob(_ mood: MusicMood, _ buffer: AVAudioPCMBuffer?) {
        musicJobInFlight = false
        musicJobMood = MusicMood.none
        if let b = buffer { musicCache[mood] = b }
        if desiredMood == mood && playingMood != mood {
            refreshMusic()
        }
        pumpMusicQueue()
    }

    // MARK: - Sprache

    private func germanVoice(male: Bool) -> AVSpeechSynthesisVoice? {
        if !voicesLoaded { loadVoices() }
        if male { return maleVoice ?? anyGermanVoice }
        return femaleVoice ?? anyGermanVoice
    }

    private func loadVoices() {
        voicesLoaded = true
        let all = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.hasPrefix("de") }
        let deDE = all.filter { $0.language == "de-DE" }
        let pool = deDE.isEmpty ? all : deDE
        maleVoice = pool.filter { $0.gender == .male }.max(by: { $0.quality.rawValue < $1.quality.rawValue })
        femaleVoice = pool.filter { $0.gender == .female }.max(by: { $0.quality.rawValue < $1.quality.rawValue })
        anyGermanVoice = AVSpeechSynthesisVoice(language: "de-DE") ?? pool.first
    }

    private static func clampRate(_ r: Float) -> Float {
        return max(AVSpeechUtteranceMinimumSpeechRate, min(AVSpeechUtteranceMaximumSpeechRate, r))
    }

    /// Reine Großbuchstaben ("VOLLENDE ES!") würden teils buchstabiert → "Vollende Es!".
    private static func speechText(_ text: String) -> String {
        let hasLower = text.rangeOfCharacter(from: CharacterSet.lowercaseLetters) != nil
        return hasLower ? text : text.capitalized
    }

    private static func isMaleCast(_ cast: CastMember) -> Bool {
        switch cast {
        case .fighter(let id):
            switch id {
            case .saya, .inferna: return false
            case .silkstrike, .nachtseide, .vex, .brutus, .malrek: return true
            }
        case .heroDarkSuit, .morgrim: return true
        case .lena, .civilian: return false
        }
    }
}

// =====================================================================
//  AudioDSP – kleine DSP-Bausteine (thread-sicher, rein funktional)
// =====================================================================

enum AudioDSP {
    static let sr: Float = 44100
    static let twoPi: Float = 2 * Float.pi
    static let tableSize = 4096

    /// xorshift64* – deterministisches Rauschen pro Sound.
    struct Rand {
        private var state: UInt64
        init(seed: UInt64) {
            state = (seed &* 0x9E3779B97F4A7C15) | 1
        }
        mutating func next() -> UInt64 {
            state ^= state >> 12
            state ^= state << 25
            state ^= state >> 27
            return state &* 2685821657736338717
        }
        /// 0 ..< 1
        mutating func unit() -> Float {
            return Float(next() >> 40) / 16777216.0
        }
        /// -1 ... 1
        mutating func bi() -> Float {
            return unit() * 2 - 1
        }
        mutating func range(_ lo: Float, _ hi: Float) -> Float {
            return lo + (hi - lo) * unit()
        }
    }

    /// Zustandsvariablen-Filter (TPT / Simper) – stabil bei allen Frequenzen.
    struct SVF {
        var ic1: Float = 0
        var ic2: Float = 0
        var k: Float = 1.414
        var a1: Float = 0
        var a2: Float = 0
        var a3: Float = 0

        mutating func set(cutoff: Float, q: Float) {
            let fc = min(max(cutoff, 10), AudioDSP.sr * 0.45)
            let g = tan(Float.pi * fc / AudioDSP.sr)
            k = 1 / max(q, 0.05)
            a1 = 1 / (1 + g * (g + k))
            a2 = g * a1
            a3 = g * a2
        }

        /// (Tiefpass, Bandpass, Hochpass). Normierter Bandpass = band * k.
        mutating func tick(_ v0: Float) -> (Float, Float, Float) {
            let v3 = v0 - ic2
            let v1 = a1 * ic1 + a2 * v3
            let v2 = ic2 + a2 * ic1 + a3 * v3
            ic1 = 2 * v1 - ic1
            ic2 = 2 * v2 - ic2
            return (v2, v1, v0 - k * v1 - v2)
        }
    }

    /// Einpoliger Tief-/Hochpass.
    struct OnePole {
        var y: Float = 0
        var a: Float = 1
        init(cutoff: Float) {
            a = AudioDSP.lpCoef(cutoff)
        }
        mutating func lp(_ x: Float) -> Float {
            y += a * (x - y)
            return y
        }
        mutating func hp(_ x: Float) -> Float {
            y += a * (x - y)
            return x - y
        }
    }

    static func lpCoef(_ cutoff: Float) -> Float {
        let fc = min(max(cutoff, 1), sr * 0.49)
        return 1 - exp(-twoPi * fc / sr)
    }

    static func hz(_ midi: Float) -> Float {
        return 440 * pow(2, (midi - 69) / 12)
    }

    static let sineTable: [Float] = AudioDSP.makeTable(harmonics: 1, oddOnly: false)
    static let sawTable: [Float] = AudioDSP.makeTable(harmonics: 16, oddOnly: false)

    /// Bandbegrenzte Wellenform (Sägezahn bzw. Sinus), Größe tableSize + 1 (Schutzpunkt für Interpolation).
    static func makeTable(harmonics: Int, oddOnly: Bool) -> [Float] {
        let n = tableSize
        var t = [Float](repeating: 0, count: n + 1)
        for i in 0..<n {
            let x = Double(i) / Double(n) * 2 * Double.pi
            var v: Double = 0
            for h in 1...max(1, harmonics) {
                if oddOnly && h % 2 == 0 { continue }
                v += sin(x * Double(h)) / Double(h)
            }
            t[i] = Float(v)
        }
        var m: Float = 0
        for i in 0..<n { m = max(m, abs(t[i])) }
        if m > 0 {
            for i in 0..<n { t[i] /= m }
        }
        t[n] = t[0]
        return t
    }

    /// Tabellen-Oszillator, phase in Perioden (beliebiger Wert, wird gewickelt).
    static func lookup(_ table: [Float], _ phase: Float) -> Float {
        let p = phase - floor(phase)
        let x = p * Float(tableSize)
        var i = Int(x)
        if i >= tableSize { i = tableSize - 1 }
        if i < 0 { i = 0 }
        let f = x - Float(i)
        let a = table[i]
        return a + (table[i + 1] - a) * f
    }

    /// FNV-1a – stabiler Seed aus einem Namen.
    static func hashName(_ s: String) -> UInt64 {
        var h: UInt64 = 14695981039346656037
        for b in s.utf8 {
            h ^= UInt64(b)
            h = h &* 1099511628211
        }
        return h
    }
}

// =====================================================================
//  AudioSFXSynth – synthetisiert jeden SoundEffect (mono, 44,1 kHz)
// =====================================================================

enum AudioSFXSynth {

    static let announceBoomName = "_announceBoom"

    static func variantCount(_ s: SoundEffect) -> Int {
        switch s {
        case .punchLight, .punchHeavy, .kick, .whoosh, .boneCrack, .gore: return 3
        case .block, .slice, .metalHit, .land, .thunder, .chain, .bodyFall, .webShoot: return 2
        case .webZip, .fire, .ice, .electric, .explosion, .teleport, .roar,
             .uiSelect, .uiConfirm, .uiBack, .heartbeat, .riftHum, .crowd, .swingRelease: return 1
        }
    }

    /// Leichte Zufallsverstimmung gegen den "Maschinengewehr-Effekt".
    static func jitters(_ s: SoundEffect) -> Bool {
        switch s {
        case .punchLight, .punchHeavy, .kick, .block, .whoosh, .webShoot, .land, .bodyFall,
             .boneCrack, .gore, .slice, .chain, .metalHit, .swingRelease, .webZip:
            return true
        case .fire, .ice, .electric, .explosion, .teleport, .roar, .uiSelect, .uiConfirm,
             .uiBack, .heartbeat, .thunder, .riftHum, .crowd:
            return false
        }
    }

    /// Relative Mischpegel (Peaks sind normiert).
    static func mixLevel(_ s: SoundEffect) -> Float {
        switch s {
        case .punchLight: return 0.78
        case .punchHeavy: return 1.0
        case .kick: return 0.88
        case .block: return 0.72
        case .whoosh: return 0.5
        case .webShoot: return 0.56
        case .webZip: return 0.5
        case .land: return 0.78
        case .bodyFall: return 0.85
        case .boneCrack: return 0.88
        case .gore: return 0.82
        case .slice: return 0.72
        case .fire: return 0.72
        case .ice: return 0.66
        case .electric: return 0.56
        case .explosion: return 1.0
        case .teleport: return 0.66
        case .chain: return 0.62
        case .roar: return 0.88
        case .uiSelect: return 0.45
        case .uiConfirm: return 0.62
        case .uiBack: return 0.5
        case .heartbeat: return 0.85
        case .thunder: return 0.95
        case .riftHum: return 0.62
        case .crowd: return 0.58
        case .metalHit: return 0.68
        case .swingRelease: return 0.46
        }
    }

    /// Lange Sounds werden nie synchron auf dem Main-Thread erzeugt.
    static func isLong(_ name: String) -> Bool {
        if name == announceBoomName { return true }
        guard let s = SoundEffect(rawValue: name) else { return false }
        switch s {
        case .thunder, .crowd, .riftHum, .explosion, .roar, .fire: return true
        default: return false
        }
    }

    static func render(name: String, variant: Int) -> [Float] {
        var rng = AudioDSP.Rand(seed: AudioDSP.hashName(name) &+ UInt64(max(0, variant)) &* 7919)
        if let s = SoundEffect(rawValue: name) {
            return renderEffect(s, variant: max(0, variant), rng: &rng)
        }
        if name == announceBoomName {
            return announceBoom(&rng)
        }
        return [Float](repeating: 0, count: 64)
    }

    private static func renderEffect(_ e: SoundEffect, variant v: Int, rng r: inout AudioDSP.Rand) -> [Float] {
        switch e {
        case .punchLight: return punchLight(v, &r)
        case .punchHeavy: return punchHeavy(v, &r)
        case .kick: return kick(v, &r)
        case .block: return block(v, &r)
        case .whoosh: return whoosh(v, &r)
        case .webShoot: return webShoot(v, &r)
        case .webZip: return webZip(&r)
        case .land: return land(v, &r)
        case .bodyFall: return bodyFall(v, &r)
        case .boneCrack: return boneCrack(v, &r)
        case .gore: return gore(v, &r)
        case .slice: return slice(v, &r)
        case .fire: return fire(&r)
        case .ice: return ice(&r)
        case .electric: return electric(&r)
        case .explosion: return explosion(&r)
        case .teleport: return teleport(&r)
        case .chain: return chain(&r)
        case .roar: return roar(&r)
        case .uiSelect: return uiSelect(&r)
        case .uiConfirm: return uiConfirm(&r)
        case .uiBack: return uiBack(&r)
        case .heartbeat: return heartbeat(&r)
        case .thunder: return thunder(v, &r)
        case .riftHum: return riftHum(&r)
        case .crowd: return crowd(&r)
        case .metalHit: return metalHit(v, &r)
        case .swingRelease: return swingRelease(&r)
        }
    }

    // MARK: Baukasten

    enum NoiseMode {
        case white
        case low(Float)
        case high(Float)
        case band(Float, Float)                     // Mitte, Güte
        case bandSweep(Float, Float, Float, Float)  // von, nach, Zeitkonstante, Güte
        case lowSweep(Float, Float, Float, Float)   // von, nach, Zeitkonstante, Güte
    }

    struct Buf {
        var s: [Float]
        let sr: Float = 44100

        init(seconds: Float) {
            s = [Float](repeating: 0, count: max(64, Int(seconds * 44100)))
        }

        private func span(_ t0: Float, _ length: Float) -> (Int, Int)? {
            let start = Int(max(0, t0) * sr)
            guard start < s.count else { return nil }
            let n = min(s.count - start, Int(max(0, length) * sr))
            guard n > 0 else { return nil }
            return (start, n)
        }

        /// Sinus mit exponentiellem Pitch-Sweep (Wumms / Bauch-Treffer).
        mutating func thump(at t0: Float, f0: Float, f1: Float, sweep: Float, decay: Float, amp: Float, attack: Float = 0.001) {
            guard let (start, n) = span(t0, attack + decay * 8) else { return }
            var ph: Float = 0
            let sw = max(sweep, 0.0001)
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let f = f1 + (f0 - f1) * exp(-t / sw)
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += sin(ph * AudioDSP.twoPi) * e * amp
            }
        }

        /// Gefiltertes Rauschen mit Hüllkurve. Pegel ist grob auf gleiche Lautheit normiert.
        mutating func noise(_ r: inout AudioDSP.Rand, at t0: Float, attack: Float, decay: Float, amp: Float, mode: NoiseMode, length: Float = 0) {
            let len = length > 0 ? length : attack + decay * 8
            guard let (start, n) = span(t0, len) else { return }
            var svf = AudioDSP.SVF()
            var norm: Float = 1
            switch mode {
            case .white:
                norm = 1
            case .low(let fc):
                svf.set(cutoff: fc, q: 0.707)
                norm = min(10, sqrt(22050 / (1.6 * max(fc, 20))))
            case .high(let fc):
                svf.set(cutoff: fc, q: 0.707)
                norm = 1.1
            case .band(let fc, let q):
                svf.set(cutoff: fc, q: q)
                norm = min(12, sqrt(22050 * q / (1.6 * max(fc, 20))))
            case .bandSweep(let a, _, _, let q):
                svf.set(cutoff: a, q: q)
            case .lowSweep(let a, _, _, let q):
                svf.set(cutoff: a, q: q)
            }
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let x = r.bi()
                var y: Float = 0
                switch mode {
                case .white:
                    y = x
                case .low:
                    y = svf.tick(x).0
                case .high:
                    y = svf.tick(x).2
                case .band:
                    y = svf.tick(x).1 * svf.k
                case .bandSweep(let a, let b, let tau, let q):
                    if i % 8 == 0 {
                        let fc = b + (a - b) * exp(-t / max(tau, 0.0001))
                        svf.set(cutoff: fc, q: q)
                        norm = min(12, sqrt(22050 * q / (1.6 * max(fc, 20))))
                    }
                    y = svf.tick(x).1 * svf.k
                case .lowSweep(let a, let b, let tau, let q):
                    if i % 8 == 0 {
                        let fc = b + (a - b) * exp(-t / max(tau, 0.0001))
                        svf.set(cutoff: fc, q: q)
                        norm = min(10, sqrt(22050 / (1.6 * max(fc, 20))))
                    }
                    y = svf.tick(x).0
                }
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += y * e * amp * norm * 0.6
            }
        }

        /// Summe gedämpfter (oft unharmonischer) Sinus-Teiltöne – Metall, Glocke, Eis.
        mutating func partials(at t0: Float, freqs: [Float], decays: [Float], amps: [Float], amp: Float, attack: Float = 0.0005, drop: Float = 0) {
            let m = min(freqs.count, min(decays.count, amps.count))
            guard m > 0 else { return }
            var maxDecay: Float = 0.01
            for k in 0..<m { maxDecay = max(maxDecay, decays[k]) }
            guard let (start, n) = span(t0, maxDecay * 7 + attack) else { return }
            let at = max(attack, 0.00001)
            for k in 0..<m {
                var ph = Float(k) * 0.37
                let dec = exp(-1 / (max(decays[k], 0.0005) * sr))
                var e: Float = 1
                let fk = min(freqs[k], sr * 0.45)
                for i in 0..<n {
                    let t = Float(i) / sr
                    let f = drop > 0 ? fk * (1 + drop * exp(-t / 0.03)) : fk
                    ph += f / sr
                    if ph >= 1 { ph -= 1 }
                    let a = t < at ? t / at : 1
                    s[start + i] += sin(ph * AudioDSP.twoPi) * e * a * amps[k] * amp
                    e *= dec
                }
            }
        }

        /// FM-Ton, optional mit exponentiellem Frequenz-Sweep (sweepTo > 0).
        mutating func fm(at t0: Float, carrier: Float, ratio: Float, index: Float, indexDecay: Float, decay: Float, amp: Float,
                         attack: Float = 0.001, sweepTo: Float = 0, sweepTau: Float = 0.05) {
            guard let (start, n) = span(t0, attack + decay * 8) else { return }
            var pc: Float = 0
            var pm: Float = 0
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let fc = sweepTo > 0 ? sweepTo + (carrier - sweepTo) * exp(-t / max(sweepTau, 0.0001)) : carrier
                pm += fc * ratio / sr
                pm -= floor(pm)
                pc += fc / sr
                pc -= floor(pc)
                let idx = index * exp(-t / max(indexDecay, 0.0001))
                let v = sin(pc * AudioDSP.twoPi + idx * sin(pm * AudioDSP.twoPi))
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += v * e * amp
            }
        }

        /// Sehr kurzer, heller Knack.
        mutating func click(_ r: inout AudioDSP.Rand, at t0: Float, amp: Float, width: Float = 0.0012, bright: Float = 4000) {
            noise(&r, at: t0, attack: 0.00005, decay: width, amp: amp * 1.4, mode: .high(bright))
        }

        /// Zufällig verteilte Knackser (Feuer, Trümmer, Blitzeinschlag).
        mutating func crackle(_ r: inout AudioDSP.Rand, from t0: Float, to t1: Float, count: Int, amp: Float, decayTau: Float, bright: Float = 3000) {
            guard count > 0 else { return }
            for _ in 0..<count {
                let t = r.range(t0, t1)
                let fall = exp(-(t - t0) / max(decayTau, 0.001))
                let rnd = r.range(0.3, 1)
                let dec = r.range(0.0006, 0.003)
                let fc = r.range(bright * 0.6, bright * 1.6)
                noise(&r, at: t, attack: 0.00005, decay: dec, amp: amp * fall * rnd, mode: .band(fc, 1.2))
            }
        }

        /// DC entfernen, normieren, Sättigung, Ränder blenden, Stille am Ende kappen.
        mutating func finish(drive: Float, peak: Float) -> [Float] {
            var y: Float = 0
            var xPrev: Float = 0
            for i in 0..<s.count {
                let x = s[i]
                y = x - xPrev + 0.9985 * y
                xPrev = x
                s[i] = y
            }
            var m: Float = 0
            for v in s { m = max(m, abs(v)) }
            guard m > 1e-6 else { return s }
            let g = 1 / m
            if drive > 0.05 {
                let nrm = 1 / tanh(drive)
                for i in 0..<s.count { s[i] = tanh(s[i] * g * drive) * nrm }
            } else {
                for i in 0..<s.count { s[i] *= g }
            }
            var m2: Float = 0
            for v in s { m2 = max(m2, abs(v)) }
            let g2: Float = m2 > 1e-6 ? peak / m2 : 0
            var last = s.count - 1
            while last > 256 && abs(s[last]) * g2 < 0.0004 { last -= 1 }
            var out = Array(s[0...last])
            let count = out.count
            let fadeIn = min(count, 24)
            let fadeOut = min(count, 240)
            for i in 0..<count {
                var v = out[i] * g2
                if i < fadeIn { v *= Float(i) / Float(fadeIn) }
                let rem = count - 1 - i
                if rem < fadeOut { v *= Float(rem) / Float(fadeOut) }
                out[i] = v
            }
            return out
        }
    }

    // MARK: Kampf

    private static func punchLight(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.28)
        b.thump(at: 0, f0: 240 + 25 * vf, f1: 95, sweep: 0.022, decay: 0.05, amp: 0.85)
        b.thump(at: 0, f0: 420, f1: 190, sweep: 0.012, decay: 0.03, amp: 0.35)
        b.noise(&r, at: 0, attack: 0.0004, decay: 0.013, amp: 0.8, mode: .band(2300 + 400 * vf, 1.1))
        b.noise(&r, at: 0.001, attack: 0.001, decay: 0.03, amp: 0.55, mode: .low(1100))
        b.click(&r, at: 0, amp: 0.4)
        return b.finish(drive: 1.8, peak: 0.95)
    }

    private static func punchHeavy(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.55)
        // tiefer Wumms + Sub
        b.thump(at: 0, f0: 160 - 10 * vf, f1: 56, sweep: 0.04, decay: 0.12, amp: 1)
        b.thump(at: 0, f0: 75, f1: 38, sweep: 0.08, decay: 0.2, amp: 0.4, attack: 0.003)
        // Körper (trägt auch auf kleinen iPhone-/iPad-Lautsprechern)
        b.thump(at: 0, f0: 330, f1: 125, sweep: 0.018, decay: 0.05, amp: 0.6)
        // Knall
        b.click(&r, at: 0, amp: 0.9, width: 0.0015, bright: 3500)
        b.noise(&r, at: 0, attack: 0.0003, decay: 0.014, amp: 0.9, mode: .high(2800))
        b.noise(&r, at: 0.007, attack: 0.0005, decay: 0.025, amp: 0.75, mode: .band(1700 + 300 * vf, 1.3))
        // Fleisch
        b.noise(&r, at: 0, attack: 0.002, decay: 0.07, amp: 0.8, mode: .band(650, 0.9))
        b.noise(&r, at: 0.01, attack: 0.004, decay: 0.12, amp: 0.3, mode: .lowSweep(4200, 300, 0.035, 0.8))
        return b.finish(drive: 2.6, peak: 0.98)
    }

    private static func kick(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.42)
        b.thump(at: 0, f0: 175 + 10 * vf, f1: 62, sweep: 0.03, decay: 0.085, amp: 1)
        b.thump(at: 0, f0: 300, f1: 130, sweep: 0.015, decay: 0.04, amp: 0.5)
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.03, amp: 0.75, mode: .band(1250, 1))
        b.noise(&r, at: 0.002, attack: 0.0003, decay: 0.008, amp: 0.5, mode: .band(3800, 1.8))
        b.click(&r, at: 0, amp: 0.5)
        return b.finish(drive: 2.0, peak: 0.95)
    }

    private static func block(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.32)
        b.thump(at: 0, f0: 280, f1: 120, sweep: 0.015, decay: 0.035, amp: 0.7)
        b.fm(at: 0, carrier: 540 + 60 * vf, ratio: 1.48, index: 3, indexDecay: 0.015, decay: 0.045, amp: 0.45)
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.02, amp: 0.5, mode: .low(1900))
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.004, amp: 0.4, mode: .high(5000))
        b.partials(at: 0.002, freqs: [1260, 2330], decays: [0.05, 0.035], amps: [0.15, 0.1], amp: 1)
        return b.finish(drive: 1.5, peak: 0.88)
    }

    private static func whoosh(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        let dur: Float = 0.28 + 0.05 * vf
        var b = Buf(seconds: dur + 0.02)
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(dur * b.sr))
        let peakPos: Float = 0.36 + 0.05 * vf
        let fLow: Float = 320 + 60 * vf
        let fHigh: Float = 1900 + 300 * vf
        var air = AudioDSP.OnePole(cutoff: 500)
        for i in 0..<n {
            let u = Float(i) / Float(n)
            let e: Float = u < peakPos ? pow(u / peakPos, 1.6) : pow(max(0, 1 - u) / (1 - peakPos), 2.2)
            if i % 8 == 0 { svf.set(cutoff: fLow + (fHigh - fLow) * e, q: 1.4) }
            let x = r.bi()
            let o = svf.tick(x)
            let low = air.lp(x)
            b.s[i] += (o.1 * svf.k * 2.2 + low * 1.5) * e
        }
        return b.finish(drive: 0.8, peak: 0.85)
    }

    private static func land(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.5)
        b.thump(at: 0, f0: 115, f1: 46, sweep: 0.045, decay: 0.14, amp: 1)
        b.thump(at: 0, f0: 240, f1: 95, sweep: 0.02, decay: 0.05, amp: 0.8)
        b.noise(&r, at: 0, attack: 0.001, decay: 0.06, amp: 0.8, mode: .low(750))
        b.noise(&r, at: 0.002, attack: 0.002, decay: 0.1, amp: 0.3, mode: .bandSweep(3200, 800, 0.08, 0.8))
        b.crackle(&r, from: 0.005, to: 0.2, count: 14 + 4 * v, amp: 0.5, decayTau: 0.08, bright: 2600)
        return b.finish(drive: 2.2, peak: 0.95)
    }

    private static func bodyFall(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.9)
        let hits: [(Float, Float)] = [(0, 1), (0.085 + 0.02 * vf, 0.6), (0.2 + 0.03 * vf, 0.35)]
        for h in hits {
            b.thump(at: h.0, f0: 100, f1: 44, sweep: 0.04, decay: 0.1, amp: h.1)
            b.thump(at: h.0, f0: 220, f1: 95, sweep: 0.02, decay: 0.045, amp: 0.75 * h.1)
            b.noise(&r, at: h.0, attack: 0.001, decay: 0.05, amp: 0.7 * h.1, mode: .low(520))
            b.noise(&r, at: h.0, attack: 0.0005, decay: 0.02, amp: 0.4 * h.1, mode: .band(1400, 0.8))
        }
        b.noise(&r, at: 0.04, attack: 0.03, decay: 0.15, amp: 0.1, mode: .bandSweep(2600, 900, 0.2, 0.9))
        return b.finish(drive: 2.0, peak: 0.95)
    }

    private static func boneCrack(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.45)
        // trockener Bruch
        b.fm(at: 0, carrier: 1100 + 120 * vf, ratio: 2.7, index: 4, indexDecay: 0.004, decay: 0.012, amp: 0.6)
        b.thump(at: 0, f0: 190, f1: 80, sweep: 0.012, decay: 0.03, amp: 0.45)
        // Serie scharfer Klicks
        let extra = Int(r.unit() * 3)
        let clickCount = 6 + v + extra
        var t: Float = 0.001
        var a: Float = 1
        for _ in 0..<clickCount {
            b.click(&r, at: t, amp: a * 0.9, width: 0.0007, bright: 3500)
            let pf = r.range(1800, 4200)
            b.partials(at: t, freqs: [pf], decays: [0.004], amps: [0.4 * a], amp: 1)
            t += r.range(0.004, 0.024)
            a *= 0.8
        }
        // Knirschen (granulares, bandgefiltertes Rauschen)
        var svf = AudioDSP.SVF()
        svf.set(cutoff: 1700, q: 1.4)
        let n = min(b.s.count, Int(0.22 * b.sr))
        var gate: Float = 1
        for i in 0..<n {
            if i % 120 == 0 {
                let chance = r.unit()
                gate = chance < 0.55 ? r.range(0.4, 1) : 0
            }
            let tt = Float(i) / b.sr
            let x = r.bi()
            let o = svf.tick(x)
            b.s[i] += o.1 * svf.k * gate * exp(-tt / 0.07) * 2.2
        }
        return b.finish(drive: 2.4, peak: 0.95)
    }

    private static func gore(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.75)
        // Aufprall-Klatscher
        b.noise(&r, at: 0, attack: 0.001, decay: 0.08, amp: 0.8, mode: .lowSweep(3600, 500, 0.03, 1.2))
        // nasses Schmatzen: resonanter Tiefpass mit wackelnder Grenzfrequenz
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(0.55 * b.sr))
        var lfoPh = r.unit()
        let lfoRate: Float = 11 + 6 * r.unit()
        for i in 0..<n {
            let t = Float(i) / b.sr
            let e = min(1, t / 0.012) * exp(-t / 0.2)
            lfoPh += lfoRate / b.sr
            if lfoPh >= 1 { lfoPh -= 1 }
            if i % 8 == 0 {
                let wob = 0.5 + 0.5 * sin(lfoPh * AudioDSP.twoPi)
                svf.set(cutoff: 380 + 1100 * wob * (0.4 + 0.6 * e), q: 5)
            }
            let x = r.bi()
            let o = svf.tick(x)
            b.s[i] += o.0 * e * 1.6
        }
        // Tropfen / Blasen
        let extra = Int(r.unit() * 3)
        let drops = 5 + v + extra
        for _ in 0..<drops {
            let t0 = r.range(0.06, 0.6)
            let f0 = r.range(280, 700)
            let amp = r.range(0.12, 0.3)
            b.fm(at: t0, carrier: f0, ratio: 1, index: 0, indexDecay: 1, decay: 0.012, amp: amp, attack: 0.001, sweepTo: f0 * 2.4, sweepTau: 0.012)
        }
        b.thump(at: 0, f0: 130, f1: 50, sweep: 0.02, decay: 0.06, amp: 0.5)
        return b.finish(drive: 1.8, peak: 0.95)
    }

    private static func slice(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.55)
        // Klingen-"Schiing": nach oben gleitendes Bandrauschen
        b.noise(&r, at: 0, attack: 0.004, decay: 0.07, amp: 0.7, mode: .bandSweep(2400, 8800, 0.05, 2.2))
        let k: Float = 1 + 0.035 * vf
        b.partials(at: 0.004, freqs: [2210 * k, 3380 * k, 4960 * k, 6720 * k], decays: [0.25, 0.18, 0.12, 0.08],
                   amps: [0.22, 0.18, 0.14, 0.09], amp: 1, attack: 0.003)
        // Schnitt ins Fleisch
        b.noise(&r, at: 0.022, attack: 0.002, decay: 0.04, amp: 0.4, mode: .band(900, 1))
        return b.finish(drive: 1.2, peak: 0.85)
    }

    // MARK: Elemente & Spezialangriffe

    private static func fire(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 1.15)
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(1.1 * b.sr))
        for i in 0..<n {
            let t = Float(i) / b.sr
            let e = (1 - exp(-t / 0.04)) * exp(-t / 0.38)
            if i % 8 == 0 { svf.set(cutoff: 300 + 3200 * e, q: 0.9) }
            let x = r.bi()
            b.s[i] += svf.tick(x).0 * e * 2.4
        }
        b.noise(&r, at: 0, attack: 0.03, decay: 0.4, amp: 0.5, mode: .low(170))
        b.crackle(&r, from: 0.02, to: 0.95, count: 34, amp: 0.45, decayTau: 0.5, bright: 3000)
        b.thump(at: 0, f0: 90, f1: 45, sweep: 0.05, decay: 0.15, amp: 0.4, attack: 0.01)
        return b.finish(drive: 1.6, peak: 0.9)
    }

    private static func ice(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.95)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.012, amp: 0.8, mode: .high(2600))
        b.noise(&r, at: 0.002, attack: 0.001, decay: 0.05, amp: 0.4, mode: .band(3300, 1.5))
        b.thump(at: 0, f0: 320, f1: 120, sweep: 0.01, decay: 0.035, amp: 0.3)
        // Splitter-Klingeln
        for _ in 0..<16 {
            let u1 = r.unit()
            let u2 = r.unit()
            let t0 = 0.5 * u1 * u2          // Häufung am Anfang
            let f = r.range(2400, 8200)
            let d1 = r.range(0.03, 0.14)
            let a1 = r.range(0.08, 0.22)
            b.partials(at: t0, freqs: [f, f * 1.53], decays: [d1, 0.03], amps: [a1, 0.06], amp: 1)
        }
        return b.finish(drive: 1.0, peak: 0.85)
    }

    private static func electric(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.75)
        let n = min(b.s.count, Int(0.7 * b.sr))
        var ph: Float = 0
        var f: Float = 95
        var gate: Float = 1
        var hp = AudioDSP.SVF()
        hp.set(cutoff: 1500, q: 0.7)
        for i in 0..<n {
            let t = Float(i) / b.sr
            if i % 220 == 0 {
                f = 80 + r.unit() * 60
                let g = r.unit()
                gate = g < 0.7 ? 1 : 0.15
            }
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            let sq: Float = ph < 0.5 ? 1 : -1
            let ph2 = (ph * 2) - floor(ph * 2)
            let sq2: Float = ph2 < 0.5 ? 1 : -1
            let nz = r.bi()
            let zap = hp.tick(nz * sq2).2
            let e = min(1, t / 0.004) * exp(-t / 0.3)
            b.s[i] += (sq * 0.35 + zap * 0.8 + nz * 0.08) * gate * e
        }
        b.crackle(&r, from: 0, to: 0.5, count: 10, amp: 0.6, decayTau: 0.3, bright: 5000)
        return b.finish(drive: 2.6, peak: 0.8)
    }

    private static func explosion(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 2.5)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.015, amp: 0.9, mode: .white)
        b.thump(at: 0, f0: 90, f1: 26, sweep: 0.12, decay: 0.5, amp: 1, attack: 0.002)
        b.thump(at: 0, f0: 210, f1: 70, sweep: 0.05, decay: 0.15, amp: 0.5)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.75, amp: 0.85, mode: .lowSweep(1600, 110, 0.45, 0.8), length: 2.45)
        b.noise(&r, at: 0.01, attack: 0.02, decay: 0.3, amp: 0.6, mode: .band(700, 0.7))
        b.crackle(&r, from: 0.05, to: 1.7, count: 46, amp: 0.55, decayTau: 0.6, bright: 2800)
        return b.finish(drive: 3.0, peak: 1.0)
    }

    private static func teleport(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.8)
        let suckEnd: Float = 0.48
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(suckEnd * b.sr))
        var ph: Float = 0
        // Einsaugen: absteigender Bandpass, anschwellend
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / suckEnd
            let e = pow(u, 2.2)
            if i % 8 == 0 { svf.set(cutoff: 4200 * pow(0.06, u) + 200, q: 3) }
            let x = r.bi()
            let o = svf.tick(x)
            let f = 1500 * pow(0.06, u) + 60
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            let tail = min(1, (suckEnd - t) / 0.01)
            b.s[i] += (o.1 * svf.k * 1.4 + sin(ph * AudioDSP.twoPi) * 0.25) * e * max(0, tail)
        }
        // Plopp beim Auftauchen
        b.thump(at: suckEnd, f0: 250, f1: 55, sweep: 0.02, decay: 0.08, amp: 0.9)
        b.noise(&r, at: suckEnd, attack: 0.0005, decay: 0.03, amp: 0.5, mode: .band(900, 0.9))
        b.partials(at: suckEnd, freqs: [1870, 2810, 3940], decays: [0.15, 0.1, 0.07], amps: [0.1, 0.07, 0.05], amp: 1)
        return b.finish(drive: 1.6, peak: 0.9)
    }

    private static func chain(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.65)
        b.noise(&r, at: 0, attack: 0.01, decay: 0.06, amp: 0.3, mode: .bandSweep(1400, 5200, 0.05, 1.2))
        var t: Float = 0.015
        let extra = Int(r.unit() * 4)
        let count = 7 + extra
        var a: Float = 1
        for _ in 0..<count {
            let f = r.range(1800, 3300)
            b.partials(at: t, freqs: [f, f * 1.47, f * 2.09, f * 2.83], decays: [0.05, 0.035, 0.025, 0.018],
                       amps: [0.3, 0.22, 0.15, 0.1], amp: a)
            b.click(&r, at: t, amp: 0.35 * a, width: 0.0006, bright: 5000)
            t += r.range(0.022, 0.06)
            a *= r.range(0.78, 0.95)
        }
        return b.finish(drive: 1.3, peak: 0.85)
    }

    private static func roar(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 1.85)
        let dur: Float = 1.75
        let n = min(b.s.count, Int(dur * b.sr))
        var f1 = AudioDSP.SVF()
        f1.set(cutoff: 560, q: 4)
        var f2 = AudioDSP.SVF()
        f2.set(cutoff: 1150, q: 5)
        var f3 = AudioDSP.SVF()
        f3.set(cutoff: 2450, q: 6)
        var br = AudioDSP.SVF()
        br.set(cutoff: 900, q: 0.8)
        var ph: Float = 0
        var phs: Float = 0
        let saw = AudioDSP.sawTable
        var jitter: Float = 0
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / dur
            if i % 441 == 0 { jitter = r.bi() * 0.04 }
            let f0 = (88 - 22 * u) * (1 + 0.03 * sin(t * 5.5 * AudioDSP.twoPi) + jitter)
            ph += f0 / b.sr
            if ph >= 1 { ph -= 1 }
            phs += f0 * 0.5 / b.sr
            if phs >= 1 { phs -= 1 }
            let src = AudioDSP.lookup(saw, ph)
            let nz = r.bi()
            let a1 = f1.tick(src + nz * 0.3).1 * f1.k
            let a2 = f2.tick(src + nz * 0.3).1 * f2.k
            let a3 = f3.tick(src + nz * 0.2).1 * f3.k
            let breath = br.tick(nz).1 * br.k
            let sub = sin(phs * AudioDSP.twoPi)
            let release: Float = u > 0.65 ? max(0, 1 - (u - 0.65) / 0.35) : 1
            let env = min(1, t / 0.22) * release
            let v = (1.4 * a1 + 0.8 * a2 + 0.35 * a3 + 0.35 * breath + 0.15 * sub) * env
            b.s[i] += tanh(v * 2.2)
        }
        return b.finish(drive: 1.5, peak: 0.92)
    }

    // MARK: UI

    private static func uiSelect(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.12)
        b.partials(at: 0, freqs: [1650, 3300], decays: [0.025, 0.012], amps: [0.6, 0.18], amp: 1, attack: 0.0008)
        b.thump(at: 0, f0: 500, f1: 380, sweep: 0.01, decay: 0.012, amp: 0.3)
        b.click(&r, at: 0, amp: 0.15)
        return b.finish(drive: 0.5, peak: 0.7)
    }

    private static func uiConfirm(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.85)
        b.thump(at: 0, f0: 170, f1: 62, sweep: 0.04, decay: 0.18, amp: 0.75)
        b.fm(at: 0, carrier: 660, ratio: 1.4, index: 2.4, indexDecay: 0.12, decay: 0.32, amp: 0.38, attack: 0.002)
        b.fm(at: 0.06, carrier: 990, ratio: 1.4, index: 2, indexDecay: 0.1, decay: 0.28, amp: 0.28, attack: 0.002)
        b.noise(&r, at: 0, attack: 0.001, decay: 0.12, amp: 0.06, mode: .high(7000))
        return b.finish(drive: 1.2, peak: 0.8)
    }

    private static func uiBack(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.4)
        b.fm(at: 0, carrier: 740, ratio: 1.4, index: 1.6, indexDecay: 0.06, decay: 0.09, amp: 0.4)
        b.fm(at: 0.07, carrier: 494, ratio: 1.4, index: 1.6, indexDecay: 0.06, decay: 0.12, amp: 0.4)
        b.thump(at: 0.07, f0: 140, f1: 70, sweep: 0.02, decay: 0.06, amp: 0.3)
        b.click(&r, at: 0, amp: 0.08)
        return b.finish(drive: 0.8, peak: 0.7)
    }

    // MARK: Atmosphäre

    private static func heartbeat(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.95)
        b.thump(at: 0, f0: 72, f1: 42, sweep: 0.03, decay: 0.075, amp: 1, attack: 0.004)
        b.thump(at: 0, f0: 150, f1: 85, sweep: 0.02, decay: 0.05, amp: 0.35, attack: 0.004)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.05, amp: 0.35, mode: .low(170))
        b.thump(at: 0.27, f0: 66, f1: 40, sweep: 0.03, decay: 0.065, amp: 0.72, attack: 0.004)
        b.thump(at: 0.27, f0: 140, f1: 80, sweep: 0.02, decay: 0.045, amp: 0.25, attack: 0.004)
        b.noise(&r, at: 0.27, attack: 0.004, decay: 0.045, amp: 0.25, mode: .low(160))
        return b.finish(drive: 1.6, peak: 0.95)
    }

    private static func thunder(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        let total: Float = 5.2
        var b = Buf(seconds: total)
        // Einschlag-Knacken
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.035, amp: 0.8, mode: .high(900))
        b.crackle(&r, from: 0, to: 0.4 + 0.2 * vf, count: 36, amp: 0.9, decayTau: 0.18, bright: 2200)
        // rollendes Grollen: braunes Rauschen, tiefpassgefiltert, langsam moduliert
        let n = b.s.count
        var brown: Float = 0
        var lp = AudioDSP.SVF()
        lp.set(cutoff: 240 + 60 * vf, q: 0.7)
        var mid = AudioDSP.SVF()
        mid.set(cutoff: 900, q: 0.7)
        var roll: Float = 0.6
        var rollTarget: Float = 0.6
        for i in 0..<n {
            let t = Float(i) / b.sr
            if i % 2205 == 0 { rollTarget = r.range(0.25, 1) }
            roll += (rollTarget - roll) * 0.0009
            let w = r.bi()
            brown = brown * 0.996 + w * 0.06
            let lo = lp.tick(brown).0
            let w2 = r.bi()
            let mi = mid.tick(w2).0
            let e = min(1, t / 0.07) * exp(-t / 1.5)
            let e2 = min(1, t / 0.02) * exp(-t / 0.5)
            b.s[i] += lo * 2.4 * roll * e + mi * 0.5 * e2
        }
        return b.finish(drive: 1.5, peak: 0.95)
    }

    private static func riftHum(_ r: inout AudioDSP.Rand) -> [Float] {
        let total: Float = 3.4
        var b = Buf(seconds: total)
        let n = b.s.count
        // verstimmte tiefe Drones + hörbare Obertöne (kleine Lautsprecher)
        let freqs: [Float] = [55, 55.7, 82.4, 110.9, 164.3, 220.5, 331.2, 441.7]
        let amps: [Float] = [0.45, 0.4, 0.25, 0.22, 0.12, 0.16, 0.1, 0.06]
        var phases = [Float](repeating: 0, count: freqs.count)
        var bp = AudioDSP.SVF()
        bp.set(cutoff: 420, q: 2)
        let saw = AudioDSP.sawTable
        var sawPh: Float = 0
        var lp = AudioDSP.OnePole(cutoff: 900)
        for i in 0..<n {
            let t = Float(i) / b.sr
            var v: Float = 0
            for k in 0..<freqs.count {
                phases[k] += freqs[k] / b.sr
                if phases[k] >= 1 { phases[k] -= 1 }
                v += sin(phases[k] * AudioDSP.twoPi) * amps[k]
            }
            sawPh += 110.3 / b.sr
            if sawPh >= 1 { sawPh -= 1 }
            v += lp.lp(AudioDSP.lookup(saw, sawPh)) * 0.3
            let x = r.bi()
            let breath = bp.tick(x).1 * bp.k * (0.5 + 0.5 * sin(t * 0.7 * AudioDSP.twoPi))
            v += breath * 0.8
            let wob = 1 - 0.18 * (0.5 + 0.5 * sin(t * 6 * AudioDSP.twoPi))
            let env = min(1, t / 0.45) * min(1, (total - t) / 0.7)
            b.s[i] += v * wob * max(0, env)
        }
        return b.finish(drive: 1.2, peak: 0.85)
    }

    private static func crowd(_ r: inout AudioDSP.Rand) -> [Float] {
        let total: Float = 3.6
        var b = Buf(seconds: total)
        let n = b.s.count
        // viele gefilterte Rausch-"Stimmen" mit Silben-Rhythmus
        for _ in 0..<12 {
            var f1 = AudioDSP.SVF()
            f1.set(cutoff: r.range(380, 1200), q: r.range(3, 6))
            var f2 = AudioDSP.SVF()
            f2.set(cutoff: r.range(1500, 2700), q: r.range(4, 8))
            var level: Float = 0
            var target: Float = 0
            let syll = max(100, Int(b.sr / r.range(3, 7)))
            let offset = Int(r.unit() * Float(syll))
            let gain = r.range(0.5, 1)
            for i in 0..<n {
                if (i + offset) % syll == 0 {
                    let c = r.unit()
                    target = c < 0.8 ? r.range(0.3, 1) : 0.05
                }
                level += (target - level) * 0.0025
                let x = r.bi()
                let o1 = f1.tick(x).1 * f1.k
                let o2 = f2.tick(x).1 * f2.k
                b.s[i] += (o1 + 0.5 * o2) * level * gain
            }
        }
        b.noise(&r, at: 0, attack: 0.5, decay: 2.0, amp: 0.3, mode: .low(300), length: total)
        for i in 0..<n {
            let t = Float(i) / b.sr
            let env = min(1, t / 0.6) * min(1, (total - t) / 1.0)
            b.s[i] *= max(0, env)
        }
        return b.finish(drive: 1.3, peak: 0.85)
    }

    private static func metalHit(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 1.1)
        let k: Float = 1 + 0.045 * vf
        b.partials(at: 0, freqs: [380 * k, 1020 * k, 1690 * k, 2410 * k, 3530 * k, 4870 * k],
                   decays: [0.6, 0.45, 0.3, 0.22, 0.15, 0.1],
                   amps: [0.55, 0.45, 0.35, 0.28, 0.2, 0.14], amp: 1, attack: 0.0005, drop: 0.012)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.006, amp: 0.7, mode: .high(3000))
        b.thump(at: 0, f0: 160, f1: 85, sweep: 0.015, decay: 0.04, amp: 0.4)
        return b.finish(drive: 1.2, peak: 0.85)
    }

    private static func swingRelease(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.45)
        let dur: Float = 0.38
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(dur * b.sr))
        for i in 0..<n {
            let u = Float(i) / Float(n)
            let e = sin(Float.pi * u) * (1 - u * 0.4)
            if i % 8 == 0 { svf.set(cutoff: 420 + 2000 * u, q: 1.5) }
            let x = r.bi()
            b.s[i] += svf.tick(x).1 * svf.k * e * 1.6
        }
        b.click(&r, at: 0, amp: 0.45, width: 0.001, bright: 5000)
        b.fm(at: 0, carrier: 1450, ratio: 1, index: 0, indexDecay: 1, decay: 0.035, amp: 0.2, attack: 0.001, sweepTo: 880, sweepTau: 0.02)
        return b.finish(drive: 1.0, peak: 0.8)
    }

    // MARK: Netz

    private static func webShoot(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.34)
        // hohes "Thwip": resonantes Bandrauschen fällt schnell ab
        b.noise(&r, at: 0, attack: 0.002, decay: 0.06, amp: 0.8, mode: .bandSweep(7500 - 600 * vf, 1700, 0.04, 4.5))
        b.fm(at: 0, carrier: 3300, ratio: 0.5, index: 0.8, indexDecay: 0.03, decay: 0.05, amp: 0.35, attack: 0.002, sweepTo: 620, sweepTau: 0.022)
        b.thump(at: 0, f0: 420, f1: 150, sweep: 0.01, decay: 0.014, amp: 0.4)
        b.noise(&r, at: 0.01, attack: 0.005, decay: 0.035, amp: 0.15, mode: .high(6500))
        return b.finish(drive: 1.3, peak: 0.9)
    }

    private static func webZip(_ r: inout AudioDSP.Rand) -> [Float] {
        let dur: Float = 0.55
        var b = Buf(seconds: 0.6)
        var svf = AudioDSP.SVF()
        var amPh: Float = 0
        var ph: Float = 0
        let n = min(b.s.count, Int(dur * b.sr))
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / dur
            let e = min(1, t / 0.015) * pow(max(0, 1 - u), 1.4)
            if i % 8 == 0 { svf.set(cutoff: 700 * pow(7, u), q: 3) }
            let amRate = 45 + 90 * u
            amPh += amRate / b.sr
            if amPh >= 1 { amPh -= 1 }
            let teeth: Float = amPh < 0.35 ? 1 : 0.45
            let x = r.bi()
            let o = svf.tick(x)
            let f = 260 * pow(4.5, u)
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            b.s[i] += (o.1 * svf.k * 1.6 * teeth + sin(ph * AudioDSP.twoPi) * 0.22) * e
        }
        b.noise(&r, at: 0, attack: 0.001, decay: 0.02, amp: 0.4, mode: .bandSweep(6000, 2000, 0.02, 3))
        return b.finish(drive: 1.4, peak: 0.88)
    }

    // MARK: Ansager-Schlag

    private static func announceBoom(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 2.4)
        b.thump(at: 0, f0: 68, f1: 30, sweep: 0.15, decay: 0.7, amp: 1, attack: 0.004)
        b.thump(at: 0, f0: 190, f1: 75, sweep: 0.04, decay: 0.12, amp: 0.55, attack: 0.003)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.25, amp: 0.35, mode: .band(500, 0.8))
        b.noise(&r, at: 0, attack: 0.004, decay: 0.8, amp: 0.45, mode: .low(260), length: 2.35)
        b.noise(&r, at: 0, attack: 0.0004, decay: 0.02, amp: 0.4, mode: .high(1800))
        b.partials(at: 0.01, freqs: [440, 659, 987, 1318], decays: [1.0, 0.8, 0.6, 0.5],
                   amps: [0.05, 0.04, 0.03, 0.02], amp: 1, attack: 0.02)
        return b.finish(drive: 1.8, peak: 0.95)
    }
}

// =====================================================================
//  AudioMusicSynth – prozedurale, nahtlos loopende Musik pro Stimmung
//  (Noten, die über das Loop-Ende hinausklingen, werden an den Anfang
//   gewickelt; Filter/Hall/Delay laufen zirkulär → kein Knacksen.)
// =====================================================================

enum AudioMusicSynth {

    static func render(_ mood: MusicMood, format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, fmt.channelCount >= 2 else { return nil }
        var c: Canvas
        var peak: Float = 0.75
        var drive: Float = 1.4
        switch mood {
        case .none:
            return nil
        case .menu:
            c = composeMenu()
            peak = 0.7
            drive = 1.2
        case .roam:
            c = composeRoam()
            peak = 0.72
            drive = 1.5
        case .tension:
            c = composeTension()
            peak = 0.7
            drive = 1.4
        case .combat:
            c = composeCombat()
            peak = 0.8
            drive = 1.8
        case .boss:
            c = composeBoss()
            peak = 0.82
            drive = 1.9
        case .sad:
            c = composeSad()
            peak = 0.66
            drive = 1.0
        case .victory:
            c = composeVictory()
            peak = 0.78
            drive = 1.5
        }
        c.master(peak: peak, drive: drive)
        return AudioDirector.makeBuffer(left: c.l, right: c.r, format: fmt)
    }

    /// Einpoliger Filter, zirkulär (zweiter Durchlauf schreibt, Zustand vom Loop-Ende).
    static func circularOnePole(_ x: inout [Float], cutoff: Float, highpass: Bool) {
        let n = x.count
        guard n > 0 else { return }
        let a = AudioDSP.lpCoef(cutoff)
        var y: Float = 0
        for i in 0..<n { y += a * (x[i] - y) }
        for i in 0..<n {
            let xi = x[i]
            y += a * (xi - y)
            x[i] = highpass ? xi - y : y
        }
    }

    // MARK: Hall-Bausteine (zirkulär: 1. Durchlauf wärmt den Zustand an, 2. Durchlauf schreibt)

    /// Gedämpfter Kammfilter über das ganze Signal; Ausgang wird auf `acc` addiert.
    static func combPass(_ input: [Float], _ acc: inout [Float], length: Int, fb: Float, damp: Float) {
        let n = input.count
        guard n > 0, acc.count >= n, length > 0 else { return }
        var buf = [Float](repeating: 0, count: length)
        var idx = 0
        var store: Float = 0
        input.withUnsafeBufferPointer { inp in
            acc.withUnsafeMutableBufferPointer { out in
                buf.withUnsafeMutableBufferPointer { b in
                    guard let ip = inp.baseAddress, let op = out.baseAddress, let bp = b.baseAddress else { return }
                    for pass in 0..<2 {
                        for i in 0..<n {
                            let y = bp[idx]
                            store = y * (1 - damp) + store * damp
                            bp[idx] = ip[i] + store * fb
                            if pass == 1 { op[i] += y }
                            idx += 1
                            if idx >= length { idx = 0 }
                        }
                    }
                }
            }
        }
    }

    /// Schroeder-Allpass (g = 0.5), in-place über das ganze Signal.
    static func allpassPass(_ x: inout [Float], length: Int) {
        let n = x.count
        guard n > 0, length > 0 else { return }
        var buf = [Float](repeating: 0, count: length)
        var idx = 0
        x.withUnsafeMutableBufferPointer { xb in
            buf.withUnsafeMutableBufferPointer { b in
                guard let xp = xb.baseAddress, let bp = b.baseAddress else { return }
                for pass in 0..<2 {
                    for i in 0..<n {
                        let input = xp[i]
                        let bv = bp[idx]
                        bp[idx] = input + bv * 0.5
                        if pass == 1 { xp[i] = bv - input }
                        idx += 1
                        if idx >= length { idx = 0 }
                    }
                }
            }
        }
    }

    // MARK: Leinwand + Instrumente

    struct Canvas {
        let sr: Float
        let frames: Int
        let beat: Float
        let seconds: Float
        var l: [Float]
        var r: [Float]
        var sendL: [Float]
        var sendR: [Float]
        var rng: AudioDSP.Rand

        init(bpm: Float, bars: Int, seed: UInt64) {
            sr = AudioDSP.sr
            beat = 60 / bpm
            let secs = beat * 4 * Float(max(1, bars))
            frames = max(44100, Int((secs * AudioDSP.sr).rounded()))
            seconds = Float(frames) / AudioDSP.sr
            l = [Float](repeating: 0, count: frames)
            r = [Float](repeating: 0, count: frames)
            sendL = [Float](repeating: 0, count: frames)
            sendR = [Float](repeating: 0, count: frames)
            rng = AudioDSP.Rand(seed: seed)
        }

        static func panGains(_ pan: Float) -> (Float, Float) {
            let a = (max(-1, min(1, pan)) + 1) * 0.25 * Float.pi
            return (cos(a), sin(a))
        }

        func startIndex(_ t: Float) -> Int {
            var i = Int((t * sr).rounded()) % frames
            if i < 0 { i += frames }
            return i
        }

        func noteLength(_ secs: Float) -> Int {
            return min(frames - 1, max(1, Int(secs * sr)))
        }

        /// Durchgehender, exakt periodischer Drone (ganzzahlige Zyklen pro Loop).
        mutating func drone(_ midi: Float, amp: Float, pan: Float = 0, beatHz: Float = 0.2, saw: Bool = false,
                            cutoff: Float = 400, lfoCycles: Int = 2, lfoDepth: Float = 0.3) {
            let secs = Double(frames) / Double(sr)
            let base = Double(AudioDSP.hz(midi))
            let c1 = max(1, (base * secs).rounded())
            let c2 = max(1, ((base + Double(beatHz)) * secs).rounded())
            let step1 = c1 / Double(frames)
            let step2 = c2 / Double(frames)
            let table = saw ? AudioDSP.sawTable : AudioDSP.sineTable
            let sine = AudioDSP.sineTable
            var lpL = AudioDSP.OnePole(cutoff: cutoff)
            var lpR = AudioDSP.OnePole(cutoff: cutoff)
            let (gl, gr) = Canvas.panGains(pan)
            let cyc = Float(max(1, lfoCycles))
            let off = rng.unit()
            let passes = saw ? 2 : 1
            for pass in 0..<passes {
                let write = pass == passes - 1
                for i in 0..<frames {
                    let a = Double(i) * step1
                    let b = Double(i) * step2
                    let s1 = AudioDSP.lookup(table, Float(a - a.rounded(.down)))
                    let s2 = AudioDSP.lookup(table, Float(b - b.rounded(.down)))
                    var vl = s1 * 0.6 + s2 * 0.4
                    var vr = s1 * 0.4 + s2 * 0.6
                    if saw {
                        vl = lpL.lp(vl)
                        vr = lpR.lp(vr)
                    }
                    if write {
                        let u = Float(i) / Float(frames)
                        let lfo = 1 - lfoDepth * (0.5 + 0.5 * AudioDSP.lookup(sine, u * cyc + off))
                        l[i] += vl * amp * lfo * gl * 1.41
                        r[i] += vr * amp * lfo * gr * 1.41
                    }
                }
            }
        }

        /// Wind-/Atmosphären-Rauschen über den ganzen Loop.
        mutating func wind(amp: Float, cutoff: Float, lfoCycles: Int = 3) {
            var nl = [Float](repeating: 0, count: frames)
            var nr = [Float](repeating: 0, count: frames)
            for i in 0..<frames {
                let a = rng.bi()
                let b = rng.bi()
                nl[i] = a
                nr[i] = b
            }
            AudioMusicSynth.circularOnePole(&nl, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nl, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nr, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nr, cutoff: cutoff, highpass: false)
            let gain = amp * min(20, sqrt(22050 / (max(cutoff, 20) * 1.2)))
            let cyc = Float(max(1, lfoCycles))
            let off = rng.unit()
            let sine = AudioDSP.sineTable
            for i in 0..<frames {
                let u = Float(i) / Float(frames)
                let lfoL = 0.55 + 0.45 * AudioDSP.lookup(sine, u * cyc + off)
                let lfoR = 0.55 + 0.45 * AudioDSP.lookup(sine, u * cyc + off + 0.25)
                l[i] += nl[i] * gain * lfoL
                r[i] += nr[i] * gain * lfoR
            }
        }

        /// Breiter Synth-Pad / Streicher (3 verstimmte Sägezähne, Tiefpass), optional Tremolo.
        mutating func pad(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, bright: Float = 0.5,
                          attack: Float = 0.8, release: Float = 1.4, detune: Float = 0.1, tremolo: Float = 0) {
            let f = AudioDSP.hz(midi)
            let n = noteLength(dur + release)
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let dDown: Float = pow(2, -detune / 12)
            let dUp: Float = pow(2, detune / 12)
            let inc0 = f * dDown / sr
            let inc1 = f / sr
            let inc2 = f * dUp / sr
            var p0 = rng.unit()
            var p1 = rng.unit()
            var p2 = rng.unit()
            let cut = min(9000, f * (1.5 + 6 * bright))
            var lpL = AudioDSP.OnePole(cutoff: cut)
            var lpR = AudioDSP.OnePole(cutoff: cut)
            let (gl, gr) = Canvas.panGains(pan)
            let atkN = max(1, attack * sr)
            let durN = dur * sr
            let relN = max(1, release * sr)
            var trem: Float = 0
            let tremInc = tremolo / sr
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                env = env * env * (3 - 2 * env)
                if tremolo > 0 {
                    trem += tremInc
                    if trem >= 1 { trem -= 1 }
                    env *= 0.6 + 0.4 * AudioDSP.lookup(sine, trem)
                }
                p0 += inc0
                if p0 >= 1 { p0 -= 1 }
                p1 += inc1
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2
                if p2 >= 1 { p2 -= 1 }
                let s0 = AudioDSP.lookup(saw, p0)
                let s1 = AudioDSP.lookup(saw, p1)
                let s2 = AudioDSP.lookup(saw, p2)
                let a = lpL.lp(s0 + 0.6 * s1)
                let b = lpR.lp(s2 + 0.6 * s1)
                let g = env * amp * 0.8
                l[idx] += a * g * gl
                r[idx] += b * g * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Gezupfter, gesättigter Synth-Bass mit Filter-Hüllkurve (+ Sub-Oktave).
        mutating func bass(_ midi: Float, at t0: Float, dur: Float, amp: Float, cutoff: Float = 400,
                           envAmt: Float = 2000, envDecay: Float = 0.07, drive: Float = 1.6) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 0.03
            let n = noteLength(dur + rel)
            let durN = dur * sr
            let relN = rel * sr
            let atkN: Float = 0.002 * sr
            var svf = AudioDSP.SVF()
            var fe: Float = 1
            let fdec = exp(-1 / (max(envDecay, 0.001) * sr))
            var p0: Float = 0
            var p1: Float = 0
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let dr = max(0.2, drive)
            let norm = 1 / tanh(dr)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                if i % 16 == 0 { svf.set(cutoff: cutoff + envAmt * fe, q: 1.1) }
                p0 += f / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * 0.5 / sr
                if p1 >= 1 { p1 -= 1 }
                let y = svf.tick(AudioDSP.lookup(saw, p0)).0 + 0.55 * AudioDSP.lookup(sine, p1)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                let v = tanh(y * dr) * norm * env * amp
                l[idx] += v * 0.707
                r[idx] += v * 0.707
                fe *= fdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// FM-Pluck / Glocke (ratio 1.4 = glockig, 2–3 = gläsern).
        mutating func pluck(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0, decay: Float = 0.5,
                            ratio: Float = 2, index: Float = 1.5, send: Float = 0) {
            let f = AudioDSP.hz(midi)
            let n = noteLength(decay * 4.6)
            let sine = AudioDSP.sineTable
            var pc: Float = 0
            var pm: Float = 0
            var e: Float = 1
            let dec = exp(-1 / (max(decay, 0.01) * sr))
            var ie: Float = 1
            let idec = exp(-1 / (max(0.01, decay * 0.3) * sr))
            let atkN: Float = 0.0025 * sr
            let incC = f / sr
            let incM = f * ratio / sr
            let idxScale = index / AudioDSP.twoPi
            let fadeN = max(1, Float(n) * 0.2)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                pm += incM
                pm -= floor(pm)
                pc += incC
                pc -= floor(pc)
                let mod = AudioDSP.lookup(sine, pm) * idxScale * ie
                let s = AudioDSP.lookup(sine, pc + mod)
                let fi = Float(i)
                let a: Float = fi < atkN ? fi / atkN : 1
                let tailFade = min(1, Float(n - i) / fadeN)
                let v = s * e * a * amp * tailFade
                l[idx] += v * gl
                r[idx] += v * gr
                if send > 0 {
                    sendL[idx] += v * gl * send
                    sendR[idx] += v * gr * send
                }
                e *= dec
                ie *= idec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Klavierähnlicher Ton (leicht unharmonische Teiltöne + Hammergeräusch).
        mutating func piano(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0, decay: Float = 1.6, send: Float = 0) {
            let f = AudioDSP.hz(midi)
            // 4 leicht gespreizte Teiltöne (Saiten-Inharmonizität), höhere klingen schneller ab
            let nyq = sr * 0.45
            let f1 = f
            let f2 = f * 2 * sqrt(1 + 0.0016)
            let f3 = f * 3 * sqrt(1 + 0.0036)
            let f4 = f * 4 * sqrt(1 + 0.0064)
            let inc1 = f1 < nyq ? f1 / sr : 0
            let inc2 = f2 < nyq ? f2 / sr : 0
            let inc3 = f3 < nyq ? f3 / sr : 0
            let inc4 = f4 < nyq ? f4 / sr : 0
            let d = max(0.05, decay)
            let dec1 = exp(-1 / (d * sr))
            let dec2 = exp(-1 / (d / 1.74 * sr))
            let dec3 = exp(-1 / (d / 2.41 * sr))
            let dec4 = exp(-1 / (d / 3.03 * sr))
            var p1: Float = 0
            var p2: Float = 0
            var p3: Float = 0
            var p4: Float = 0
            var e1: Float = 1
            var e2: Float = 0.5
            var e3: Float = 0.26
            var e4: Float = 0.15
            let n = noteLength(min(d * 2.8, 5))
            let fadeN = max(1, Float(n) * 0.3)
            var ne: Float = 1
            let ndec = exp(-1 / (0.006 * sr))
            var lp = AudioDSP.OnePole(cutoff: 2500)
            var atk: Float = 0
            let atkInc = 1 / (0.002 * sr)
            let sine = AudioDSP.sineTable
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                p1 += inc1
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2
                if p2 >= 1 { p2 -= 1 }
                p3 += inc3
                if p3 >= 1 { p3 -= 1 }
                p4 += inc4
                if p4 >= 1 { p4 -= 1 }
                var v = AudioDSP.lookup(sine, p1) * e1 + AudioDSP.lookup(sine, p2) * e2
                v += AudioDSP.lookup(sine, p3) * e3 + AudioDSP.lookup(sine, p4) * e4
                e1 *= dec1
                e2 *= dec2
                e3 *= dec3
                e4 *= dec4
                if ne > 1e-5 {          // Hammergeräusch (danach abschalten: keine Subnormal-Zahlen)
                    let x = rng.bi()
                    v += lp.lp(x) * ne * 0.6
                    ne *= ndec
                }
                atk = min(1, atk + atkInc)
                let tailFade = min(1, Float(n - i) / fadeN)
                let out = v * amp * atk * tailFade
                l[idx] += out * gl
                r[idx] += out * gr
                if send > 0 {
                    sendL[idx] += out * gl * send
                    sendR[idx] += out * gr * send
                }
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Taiko-Trommel: tiefer Pitch-Drop + Fell-Schlag.
        mutating func taiko(at t0: Float, amp: Float, pitch: Float = 1, pan: Float = 0) {
            let n = noteLength(1.1)
            let sine = AudioDSP.sineTable
            var ph: Float = 0
            var ph2: Float = 0
            var env: Float = 1
            let dec = exp(-1 / (0.38 * sr))
            var env2: Float = 1
            let dec2 = exp(-1 / (0.12 * sr))
            var nenv: Float = 1
            let ndec = exp(-1 / (0.03 * sr))
            var pe: Float = 1
            let pdec = exp(-1 / (0.035 * sr))
            var lp = AudioDSP.OnePole(cutoff: 900)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let f = (52 + 80 * pe) * pitch
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                ph2 += f * 1.58 / sr
                if ph2 >= 1 { ph2 -= 1 }
                let body = AudioDSP.lookup(sine, ph) * env + AudioDSP.lookup(sine, ph2) * env2 * 0.35
                let x = rng.bi()
                let skin = lp.lp(x) * nenv * 2.2
                let v = tanh((body + skin) * amp * 1.4)
                l[idx] += v * gl
                r[idx] += v * gr
                env *= dec
                env2 *= dec2
                nenv *= ndec
                pe *= pdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func kick(at t0: Float, amp: Float) {
            let n = noteLength(0.55)
            let sine = AudioDSP.sineTable
            var ph: Float = 0
            var pe: Float = 1
            let pdec = exp(-1 / (0.03 * sr))
            var e: Float = 1
            let edec = exp(-1 / (0.2 * sr))
            var ce: Float = 1
            let cdec = exp(-1 / (0.0025 * sr))
            var idx = startIndex(t0)
            for _ in 0..<n {
                let f = 44 + 115 * pe
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                var click: Float = 0
                if ce > 1e-5 {
                    let x = rng.bi()
                    click = x * ce * 0.35
                    ce *= cdec
                }
                let v = tanh((AudioDSP.lookup(sine, ph) * e + click) * amp * 1.8)
                l[idx] += v * 0.707
                r[idx] += v * 0.707
                pe *= pdec
                e *= edec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func snare(at t0: Float, amp: Float, pan: Float = 0) {
            let n = noteLength(0.5)
            let sine = AudioDSP.sineTable
            var bp = AudioDSP.SVF()
            bp.set(cutoff: 2300, q: 0.7)
            var hp = AudioDSP.SVF()
            hp.set(cutoff: 5000, q: 0.7)
            var p1: Float = 0
            var p2: Float = 0
            var te: Float = 1
            let tdec = exp(-1 / (0.05 * sr))
            var ne: Float = 1
            let ndec = exp(-1 / (0.13 * sr))
            var pe: Float = 1
            let pdec = exp(-1 / (0.008 * sr))
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let pm = 1 + 0.5 * pe
                p1 += 185 * pm / sr
                if p1 >= 1 { p1 -= 1 }
                p2 += 330 * pm / sr
                if p2 >= 1 { p2 -= 1 }
                let tone = (AudioDSP.lookup(sine, p1) + 0.6 * AudioDSP.lookup(sine, p2)) * te
                let x = rng.bi()
                let nz = bp.tick(x).1 * bp.k * 1.6 + hp.tick(x).2 * 0.5
                let v = tanh((tone * 0.8 + nz * ne) * amp * 1.5)
                l[idx] += v * gl
                r[idx] += v * gr
                te *= tdec
                ne *= ndec
                pe *= pdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func hat(at t0: Float, amp: Float, open: Bool = false, pan: Float = 0) {
            let decay: Float = open ? 0.14 : 0.025
            let n = noteLength(decay * 6)
            var hp = AudioDSP.SVF()
            hp.set(cutoff: 7200, q: 0.7)
            var bp = AudioDSP.SVF()
            bp.set(cutoff: 10000, q: 1.2)
            var env: Float = 1
            let dec = exp(-1 / (decay * sr))
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let x = rng.bi()
                let h = hp.tick(x).2
                let b = bp.tick(h).1 * bp.k
                let v = (h * 0.6 + b * 0.6) * env * amp
                l[idx] += v * gl
                r[idx] += v * gr
                env *= dec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Pauke: unharmonische Teiltöne, kurzer Pitch-Drop, Schlägelgeräusch.
        mutating func timpani(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0) {
            let f = AudioDSP.hz(midi)
            // Kesselmoden (unharmonisch): 1, 1.504, 1.742, 2.0
            let inc1 = f / sr
            let inc2 = f * 1.504 / sr
            let inc3 = f * 1.742 / sr
            let inc4 = f * 2.0 / sr
            let dec1 = exp(-1 / (1.3 * sr))
            let dec2 = exp(-1 / (0.7 * sr))
            let dec3 = exp(-1 / (0.5 * sr))
            let dec4 = exp(-1 / (0.4 * sr))
            var p1: Float = 0
            var p2: Float = 0
            var p3: Float = 0
            var p4: Float = 0
            var e1: Float = 1
            var e2: Float = 0.5
            var e3: Float = 0.3
            var e4: Float = 0.25
            let n = noteLength(1.7)
            let fadeN = max(1, Float(n) * 0.25)
            var pe: Float = 1
            let pdec = exp(-1 / (0.02 * sr))
            var ne: Float = 1
            let ndec = exp(-1 / (0.015 * sr))
            var lp = AudioDSP.OnePole(cutoff: 700)
            let sine = AudioDSP.sineTable
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let bend = 1 + 0.035 * pe
                p1 += inc1 * bend
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2 * bend
                if p2 >= 1 { p2 -= 1 }
                p3 += inc3 * bend
                if p3 >= 1 { p3 -= 1 }
                p4 += inc4 * bend
                if p4 >= 1 { p4 -= 1 }
                var v = AudioDSP.lookup(sine, p1) * e1 + AudioDSP.lookup(sine, p2) * e2
                v += AudioDSP.lookup(sine, p3) * e3 + AudioDSP.lookup(sine, p4) * e4
                e1 *= dec1
                e2 *= dec2
                e3 *= dec3
                e4 *= dec4
                if ne > 1e-5 {          // Schlägelgeräusch
                    let x = rng.bi()
                    v += lp.lp(x) * ne * 2.0
                    ne *= ndec
                }
                if pe > 1e-6 { pe *= pdec } else { pe = 0 }
                let tailFade = min(1, Float(n - i) / fadeN)
                let out = v * amp * tailFade
                l[idx] += out * gl
                r[idx] += out * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Synthetischer Chor ("Ah"/"Oh"): verstimmte Sägezähne mit Vibrato durch Formantfilter.
        mutating func choir(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, vowel: Int = 0) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 1.2
            let n = noteLength(dur + rel)
            let atkN: Float = 0.7 * sr
            let durN = dur * sr
            let relN = rel * sr
            let formants: [Float] = vowel == 0 ? [760, 1150, 2600] : [460, 820, 2500]
            var fA = AudioDSP.SVF()
            fA.set(cutoff: formants[0], q: 5)
            var fB = AudioDSP.SVF()
            fB.set(cutoff: formants[1], q: 7)
            var fC = AudioDSP.SVF()
            fC.set(cutoff: formants[2], q: 9)
            var body = AudioDSP.OnePole(cutoff: min(3000, f * 4))
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let d1: Float = pow(2, -0.08 / 12)
            let d2: Float = pow(2, 0.07 / 12)
            var p0 = rng.unit()
            var p1 = rng.unit()
            var p2 = rng.unit()
            var vph = rng.unit()
            let vrate: Float = (4.8 + 0.8 * rng.unit()) / sr
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                env = env * env * (3 - 2 * env)
                vph += vrate
                if vph >= 1 { vph -= 1 }
                let vib = AudioDSP.lookup(sine, vph)
                let vib0 = 1 + 0.005 * vib
                let vib1 = 1 - 0.004 * vib
                let vib2 = 1 + 0.0025 * vib
                p0 += f * vib0 / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * d1 * vib1 / sr
                if p1 >= 1 { p1 -= 1 }
                p2 += f * d2 * vib2 / sr
                if p2 >= 1 { p2 -= 1 }
                let src = AudioDSP.lookup(saw, p0) + AudioDSP.lookup(saw, p1) + AudioDSP.lookup(saw, p2)
                let a = fA.tick(src).1 * fA.k
                let b = fB.tick(src).1 * fB.k
                let c3 = fC.tick(src).1 * fC.k
                let lo = body.lp(src)
                let v = (a + 0.55 * b + 0.22 * c3 + 0.25 * lo) * env * amp * 0.5
                l[idx] += v * gl
                r[idx] += v * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Blechbläser-artiger Synth (Filter öffnet beim Anblasen, verzögertes Vibrato).
        mutating func brass(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, bright: Float = 1) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 0.28
            let n = noteLength(dur + rel)
            let durN = dur * sr
            let relN = rel * sr
            let atkN: Float = 0.035 * sr
            var svf = AudioDSP.SVF()
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            var p0 = rng.unit()
            var p1 = rng.unit()
            var vib: Float = 0
            let d: Float = pow(2, 0.06 / 12)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                let t = fi / sr
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                if i % 16 == 0 {
                    let fenv: Float = t < 0.06 ? t / 0.06 : 0.55 + 0.45 * exp(-(t - 0.06) / 0.25)
                    svf.set(cutoff: f * (1.2 + (2.5 + 5 * bright) * fenv), q: 0.9)
                }
                vib += 5.5 / sr
                if vib >= 1 { vib -= 1 }
                let vibAmt: Float = t > 0.3 ? 0.003 * min(1, (t - 0.3) / 0.4) : 0
                let fm = 1 + vibAmt * AudioDSP.lookup(sine, vib)
                p0 += f * fm / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * d * fm / sr
                if p1 >= 1 { p1 -= 1 }
                let src = AudioDSP.lookup(saw, p0) + AudioDSP.lookup(saw, p1)
                let y = svf.tick(src).0
                let v = tanh(y * 0.9) * env * amp
                l[idx] += v * gl
                r[idx] += v * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Rausch-Steigerung (Riser) – Bandpass gleitet von `from` nach `to`.
        mutating func swell(at t0: Float, dur: Float, amp: Float, from: Float, to: Float) {
            let n = noteLength(dur)
            var fl = AudioDSP.SVF()
            var fr = AudioDSP.SVF()
            let ratio = max(0.01, to / max(from, 1))
            var idx = startIndex(t0)
            let fadeN = Float(min(n, 220))
            for i in 0..<n {
                let u = Float(i) / Float(n)
                if i % 16 == 0 {
                    let fc = from * pow(ratio, u)
                    fl.set(cutoff: fc, q: 0.8)
                    fr.set(cutoff: fc * 1.05, q: 0.8)
                }
                let e = pow(u, 2.5) * min(1, Float(n - i) / fadeN)
                let a = rng.bi()
                let b = rng.bi()
                let vl = fl.tick(a).1 * fl.k * e * amp * 2
                let vr = fr.tick(b).1 * fr.k * e * amp * 2
                l[idx] += vl
                r[idx] += vr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Becken-Crash (Stereo-Rauschen, Hochpass, langes Ausklingen).
        mutating func crash(at t0: Float, amp: Float) {
            let n = noteLength(1.8)
            var hl = AudioDSP.SVF()
            hl.set(cutoff: 5200, q: 0.6)
            var hr = AudioDSP.SVF()
            hr.set(cutoff: 5600, q: 0.6)
            var env: Float = 1
            let dec = exp(-1 / (0.55 * sr))
            var idx = startIndex(t0)
            for i in 0..<n {
                let a = rng.bi()
                let b = rng.bi()
                let atk = min(1, Float(i) / 40)
                let vl = hl.tick(a).2 * env * amp * atk
                let vr = hr.tick(b).2 * env * amp * atk
                l[idx] += vl
                r[idx] += vr
                env *= dec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Ping-Pong-Delay auf dem Send-Bus (zirkulär).
        mutating func applyDelay(time: Float, feedback: Float, mix: Float) {
            let d = max(1, min(frames - 1, Int(time * sr)))
            var bufL = [Float](repeating: 0, count: d)
            var bufR = [Float](repeating: 0, count: d)
            var outL = [Float](repeating: 0, count: frames)
            var outR = [Float](repeating: 0, count: frames)
            var dampL = AudioDSP.OnePole(cutoff: 3200)
            var dampR = AudioDSP.OnePole(cutoff: 3200)
            var di = 0
            for pass in 0..<2 {
                for i in 0..<frames {
                    let yl = bufL[di]
                    let yr = bufR[di]
                    let inL = sendL[i]
                    let inR = sendR[i]
                    let fbR = dampR.lp(yr) * feedback
                    let fbL = dampL.lp(yl) * feedback
                    bufL[di] = inL + fbR
                    bufR[di] = inR * 0.3 + fbL
                    if pass == 1 {
                        outL[i] = yl
                        outR[i] = yr
                    }
                    di += 1
                    if di >= d { di = 0 }
                }
            }
            for i in 0..<frames {
                l[i] += outL[i] * mix
                r[i] += outR[i] * mix
            }
        }

        /// Schroeder/Freeverb-artiger Hall (4 Kämme + 2 Allpässe je Kanal), zirkulär.
        mutating func applyReverb(mix: Float, room: Float, damp: Float) {
            var input = [Float](repeating: 0, count: frames)
            for i in 0..<frames { input[i] = (l[i] + r[i]) * 0.14 }
            AudioMusicSynth.circularOnePole(&input, cutoff: 220, highpass: true)
            var wetL = [Float](repeating: 0, count: frames)
            var wetR = [Float](repeating: 0, count: frames)
            for len in [1116, 1277, 1422, 1557] {
                AudioMusicSynth.combPass(input, &wetL, length: len, fb: room, damp: damp)
                AudioMusicSynth.combPass(input, &wetR, length: len + 23, fb: room, damp: damp)
            }
            AudioMusicSynth.allpassPass(&wetL, length: 556)
            AudioMusicSynth.allpassPass(&wetL, length: 341)
            AudioMusicSynth.allpassPass(&wetR, length: 579)
            AudioMusicSynth.allpassPass(&wetR, length: 364)
            for i in 0..<frames {
                l[i] += wetL[i] * mix
                r[i] += wetR[i] * mix
            }
        }

        /// DC-Filter, Normierung, sanfte Sättigung.
        mutating func master(peak: Float, drive: Float) {
            AudioMusicSynth.circularOnePole(&l, cutoff: 24, highpass: true)
            AudioMusicSynth.circularOnePole(&r, cutoff: 24, highpass: true)
            var m: Float = 0
            for i in 0..<frames { m = max(m, abs(l[i]), abs(r[i])) }
            guard m > 1e-6 else { return }
            let g = 1 / m
            let k = max(0.3, drive)
            let norm = peak / tanh(k)
            for i in 0..<frames {
                l[i] = tanh(l[i] * g * k) * norm
                r[i] = tanh(r[i] * g * k) * norm
            }
        }
    }

    // MARK: - Kompositionen

    /// Menü: dunkel, mysteriös – d-Moll, Drone, Pads, gläsernes Arpeggio, ferne Pauken.
    static func composeMenu() -> Canvas {
        var c = Canvas(bpm: 72, bars: 4, seed: 11)
        let chords: [[Float]] = [[50, 53, 57], [50, 53, 58], [50, 55, 58], [49, 52, 57]]   // Dm – B – Gm – A
        let roots: [Float] = [38, 34, 31, 33]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        c.drone(26, amp: 0.2, beatHz: 0.18, saw: false, lfoCycles: 1, lfoDepth: 0.35)
        c.drone(38, amp: 0.07, beatHz: 0.31, saw: true, cutoff: 260, lfoCycles: 2, lfoDepth: 0.5)
        c.wind(amp: 0.05, cutoff: 700, lfoCycles: 3)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            for k in 0..<tones.count {
                c.pad(tones[k], at: t0, dur: bar, amp: 0.07, pan: Float(k - 1) * 0.45, bright: 0.35, attack: 1.4, release: 1.8, detune: 0.11)
            }
            c.pad(roots[b], at: t0, dur: bar, amp: 0.11, pan: 0, bright: 0.12, attack: 0.6, release: 1.2, detune: 0.05)
            let pattern: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[0] + 24,
                                    tones[2] + 12, tones[1] + 12, tones[0] + 24, tones[2] + 12]
            for s in 0..<8 {
                let accent: Float = s == 0 ? 1.0 : 0.75
                let pan: Float = s % 2 == 0 ? -0.35 : 0.35
                c.pluck(pattern[s], at: t0 + Float(s) * eighth, amp: 0.055 * accent, pan: pan, decay: 0.9, ratio: 3, index: 1.1, send: 0.55)
            }
        }
        c.timpani(38, at: 0, amp: 0.32)
        c.timpani(31, at: 2 * bar, amp: 0.3)
        c.pluck(81, at: bar + 2 * c.beat, amp: 0.05, pan: 0.5, decay: 2.5, ratio: 1.4, index: 2.2, send: 0.6)
        c.pluck(85, at: 3 * bar + 2 * c.beat, amp: 0.045, pan: -0.5, decay: 2.5, ratio: 1.4, index: 2.2, send: 0.6)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.42, mix: 0.6)
        c.applyReverb(mix: 0.5, room: 0.88, damp: 0.3)
        return c
    }

    /// Offene Welt: nächtlich-heroisch, c-Moll, pulsierender Achtelbass, Arpeggio, Leitmotiv.
    static func composeRoam() -> Canvas {
        var c = Canvas(bpm: 104, bars: 8, seed: 23)
        let chords: [[Float]] = [[60, 63, 67], [60, 63, 68], [58, 63, 67], [58, 62, 65],
                                 [60, 63, 67], [60, 63, 68], [60, 65, 68], [59, 62, 67]]   // Cm Ab Eb B♭ Cm Ab Fm G
        let roots: [Float] = [36, 32, 39, 34, 36, 32, 41, 43]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        let s16 = c.beat * 0.25
        let bassOffsets: [Float] = [0, 0, 12, 0, 0, 0, 12, 7]
        c.wind(amp: 0.03, cutoff: 900, lfoCycles: 4)
        c.drone(24, amp: 0.08, beatHz: 0.2, saw: false, lfoCycles: 2, lfoDepth: 0.4)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            for k in 0..<tones.count {
                c.pad(tones[k], at: t0, dur: bar, amp: 0.05, pan: Float(k - 1) * 0.5, bright: 0.55, attack: 0.5, release: 1.0, detune: 0.09)
            }
            for s in 0..<8 {
                let acc: Float = (s == 0 || s == 4) ? 1.0 : 0.78
                c.bass(roots[b] + bassOffsets[s], at: t0 + Float(s) * eighth, dur: eighth * 0.8, amp: 0.2 * acc,
                       cutoff: 320, envAmt: 1600 * acc, envDecay: 0.06, drive: 1.6)
            }
            c.kick(at: t0, amp: 0.42)
            c.kick(at: t0 + 2 * c.beat, amp: 0.36)
            if b % 2 == 1 { c.kick(at: t0 + 2.75 * c.beat, amp: 0.22) }
            c.snare(at: t0 + c.beat, amp: 0.2, pan: 0.05)
            c.snare(at: t0 + 3 * c.beat, amp: 0.22, pan: 0.05)
            for s in 0..<16 {
                let a: Float = s % 2 == 0 ? 0.05 : 0.022
                c.hat(at: t0 + Float(s) * s16, amp: a, open: s == 14 && b % 2 == 1, pan: 0.25)
            }
            let arp: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[1] + 12]
            for s in 0..<16 {
                let pan = -0.5 + Float(s) / 15
                let a: Float = s % 4 == 0 ? 0.04 : 0.028
                c.pluck(arp[s % 4], at: t0 + Float(s) * s16, amp: a, pan: pan, decay: 0.28, ratio: 2, index: 1.3, send: 0.35)
            }
        }
        let motif: [(Float, Float, Float)] = [
            (67, 0, 1.5), (72, 1.5, 0.5), (74, 2, 1), (75, 3, 1), (74, 4, 2), (72, 6, 1), (70, 7, 1),
            (67, 16, 1.5), (72, 17.5, 0.5), (74, 18, 1), (75, 19, 1), (77, 20, 2), (75, 22, 1), (74, 23, 1), (72, 24, 4)
        ]
        for m in motif {
            c.brass(m.0, at: m.1 * c.beat, dur: m.2 * c.beat, amp: 0.075, pan: 0.1, bright: 0.5)
        }
        c.applyDelay(time: c.beat * 0.75, feedback: 0.35, mix: 0.45)
        c.applyReverb(mix: 0.32, room: 0.85, damp: 0.3)
        return c
    }

    /// Spannung: Tritonus-Drone, Herzschlag-Taikos, dissonantes Streicher-Tremolo, metallische Pings.
    static func composeTension() -> Canvas {
        var c = Canvas(bpm: 84, bars: 4, seed: 37)
        let bar = c.beat * 4
        c.drone(25, amp: 0.2, beatHz: 0.22, saw: false, lfoCycles: 2, lfoDepth: 0.3)
        c.drone(31, amp: 0.09, beatHz: 0.37, saw: false, lfoCycles: 3, lfoDepth: 0.5)
        c.drone(37, amp: 0.05, beatHz: 0.15, saw: true, cutoff: 300, lfoCycles: 1, lfoDepth: 0.6)
        c.wind(amp: 0.045, cutoff: 500, lfoCycles: 2)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            for beatIdx in [0, 2] {
                let t = t0 + Float(beatIdx) * c.beat
                c.taiko(at: t, amp: 0.34, pitch: 0.62)
                c.taiko(at: t + 0.27, amp: 0.2, pitch: 0.58)
            }
            for q in 0..<4 {
                c.bass(37, at: t0 + Float(q) * c.beat, dur: c.beat * 0.5, amp: 0.1, cutoff: 200, envAmt: 500, envDecay: 0.09, drive: 1.3)
            }
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.03 : 0.018
                let pan: Float = s % 2 == 0 ? -0.3 : 0.3
                c.hat(at: t0 + Float(s) * c.beat * 0.5, amp: a, open: false, pan: pan)
            }
        }
        c.pad(80, at: 0, dur: 2 * bar, amp: 0.022, pan: -0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7)
        c.pad(81, at: 0, dur: 2 * bar, amp: 0.018, pan: 0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7.5)
        c.pad(81, at: 2 * bar, dur: 2 * bar, amp: 0.022, pan: -0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7)
        c.pad(82, at: 2 * bar, dur: 2 * bar, amp: 0.02, pan: 0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 8)
        c.pluck(86, at: bar + 3 * c.beat, amp: 0.05, pan: 0.6, decay: 2.2, ratio: 1.41, index: 3, send: 0.7)
        c.pluck(80, at: 3 * bar + 1.5 * c.beat, amp: 0.045, pan: -0.6, decay: 2.2, ratio: 1.41, index: 3, send: 0.7)
        c.applyDelay(time: c.beat * 1.5, feedback: 0.45, mix: 0.5)
        c.applyReverb(mix: 0.45, room: 0.88, damp: 0.35)
        return c
    }

    /// Kampf: 132 BPM, treibender 16tel-Bass, Taiko-Grooves mit Fills, Chor, Blech-Stabs.
    static func composeCombat() -> Canvas {
        var c = Canvas(bpm: 132, bars: 8, seed: 51)
        let chords: [[Float]] = [[62, 65, 69], [62, 65, 69], [62, 65, 70], [60, 64, 67],
                                 [62, 65, 69], [62, 65, 69], [63, 67, 70], [60, 64, 67]]   // Dm Dm B♭ C Dm Dm E♭ C
        let roots: [Float] = [38, 38, 34, 36, 38, 38, 39, 36]
        let bar = c.beat * 4
        let s16 = c.beat * 0.25
        let eighth = c.beat * 0.5
        let grooveHits: [(Float, Float, Float)] = [(0, 0.6, 1), (1.5, 0.3, 1.15), (2, 0.5, 0.95), (3, 0.32, 1.2), (3.5, 0.3, 1.1)]
        let fillHits: [(Float, Float, Float)] = [(0, 0.6, 1), (1.5, 0.32, 1.1), (2, 0.42, 1.2), (2.25, 0.3, 1.25), (2.5, 0.45, 1.15),
                                                 (2.75, 0.34, 1.3), (3, 0.5, 1.1), (3.25, 0.4, 1.2), (3.5, 0.55, 1.0), (3.75, 0.62, 0.9)]
        c.drone(26, amp: 0.1, beatHz: 0.25, saw: false, lfoCycles: 4, lfoDepth: 0.3)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            let root = roots[b]
            for s in 0..<16 {
                let pos = s % 4
                let note = root + (pos == 2 ? 12 : 0)
                let acc: Float = pos == 0 ? 1 : 0.72
                c.bass(note, at: t0 + Float(s) * s16, dur: s16 * 0.82, amp: 0.2 * acc, cutoff: 260, envAmt: 2300 * acc, envDecay: 0.05, drive: 2.2)
            }
            let hits = (b == 3 || b == 7) ? fillHits : grooveHits
            for h in hits {
                c.taiko(at: t0 + h.0 * c.beat, amp: h.1, pitch: h.2, pan: (h.2 - 1) * 1.5)
            }
            c.kick(at: t0, amp: 0.45)
            c.kick(at: t0 + 2 * c.beat, amp: 0.4)
            c.kick(at: t0 + 2.75 * c.beat, amp: 0.24)
            c.snare(at: t0 + c.beat, amp: 0.3, pan: 0)
            c.snare(at: t0 + 3 * c.beat, amp: 0.32, pan: 0)
            for s in 0..<16 {
                let a: Float = s % 2 == 0 ? 0.055 : 0.025
                c.hat(at: t0 + Float(s) * s16, amp: a, open: s == 6 && b % 2 == 0, pan: 0.3)
            }
            for n in tones {
                c.brass(n, at: t0, dur: c.beat * 0.4, amp: 0.06, pan: 0, bright: 1)
            }
            if b % 2 == 1 {
                for n in tones {
                    c.brass(n, at: t0 + 2.5 * c.beat, dur: c.beat * 0.3, amp: 0.045, pan: 0, bright: 0.9)
                }
            }
            let choirAmp: Float = b < 4 ? 0.028 : 0.045
            for k in 0..<tones.count {
                c.choir(tones[k] - 12, at: t0, dur: bar, amp: choirAmp, pan: Float(k - 1) * 0.5, vowel: 0)
            }
            let ost: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[1] + 12]
            for s in 0..<8 {
                let pan: Float = s % 2 == 0 ? -0.4 : 0.4
                c.pluck(ost[s % 4], at: t0 + Float(s) * eighth, amp: 0.035, pan: pan, decay: 0.22, ratio: 1, index: 2.2, send: 0.25)
            }
        }
        c.swell(at: 7 * bar, dur: bar, amp: 0.09, from: 600, to: 9000)
        c.crash(at: 0, amp: 0.1)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.4)
        c.applyReverb(mix: 0.26, room: 0.84, damp: 0.3)
        return c
    }

    /// Endboss: Orgel-Drone, massive Halbtempo-Taikos, Chor, Totenglocke, Tritonus-Harmonik.
    static func composeBoss() -> Canvas {
        var c = Canvas(bpm: 116, bars: 8, seed: 67)
        let chords: [[Float]] = [[60, 63, 67], [60, 63, 67], [61, 65, 68], [61, 65, 68],
                                 [60, 63, 67], [60, 63, 67], [61, 66, 70], [59, 62, 67]]   // Cm Cm D♭ D♭ Cm Cm G♭ G
        let roots: [Float] = [36, 36, 37, 37, 36, 36, 42, 43]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        let s16 = c.beat * 0.25
        let grooveHits: [(Float, Float, Float)] = [(0, 0.72, 0.85), (0.75, 0.32, 1.0), (1.5, 0.4, 0.95), (2, 0.66, 0.8), (3.5, 0.34, 1.05)]
        let fillHits: [(Float, Float, Float)] = [(0, 0.72, 0.85), (1, 0.4, 1.0), (2, 0.6, 0.85), (2.5, 0.45, 1.0),
                                                 (3, 0.55, 1.1), (3.25, 0.5, 1.15), (3.5, 0.6, 1.2), (3.75, 0.7, 1.25)]
        c.drone(24, amp: 0.14, beatHz: 0.2, saw: true, cutoff: 220, lfoCycles: 4, lfoDepth: 0.35)
        c.drone(36, amp: 0.06, beatHz: 0.33, saw: true, cutoff: 500, lfoCycles: 2, lfoDepth: 0.5)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            let root = roots[b]
            for s in 0..<8 {
                let acc: Float = s % 4 == 0 ? 1 : 0.75
                let note = root + (s % 2 == 1 ? 12 : 0)
                c.bass(note, at: t0 + Float(s) * eighth, dur: eighth * 0.75, amp: 0.22 * acc, cutoff: 220, envAmt: 1500 * acc, envDecay: 0.07, drive: 2.6)
            }
            let hits = b == 7 ? fillHits : grooveHits
            for h in hits {
                c.taiko(at: t0 + h.0 * c.beat, amp: h.1, pitch: h.2, pan: (h.2 - 1) * 1.2)
            }
            c.kick(at: t0, amp: 0.48)
            c.kick(at: t0 + 2 * c.beat, amp: 0.4)
            c.snare(at: t0 + 2 * c.beat, amp: 0.34, pan: 0)
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.04 : 0.025
                c.hat(at: t0 + Float(s) * eighth, amp: a, open: false, pan: -0.25)
            }
            let vowel = b < 4 ? 1 : 0
            for k in 0..<tones.count {
                c.choir(tones[k] - 12, at: t0, dur: bar, amp: 0.05, pan: Float(k - 1) * 0.55, vowel: vowel)
            }
            c.choir(root + 12, at: t0, dur: bar, amp: 0.035, pan: 0, vowel: vowel)
            for s in 0..<16 {
                c.pluck(tones[s % 3] + 12, at: t0 + Float(s) * s16, amp: 0.022, pan: 0.45, decay: 0.15, ratio: 1, index: 1.8, send: 0.2)
            }
        }
        for bIdx in [2, 6] {
            for n in chords[bIdx] {
                c.brass(n - 12, at: Float(bIdx) * bar, dur: c.beat * 1.5, amp: 0.075, pan: 0, bright: 0.9)
            }
        }
        for bIdx in [0, 2, 4, 6] {
            c.pluck(48, at: Float(bIdx) * bar, amp: 0.13, pan: 0, decay: 2.8, ratio: 1.4, index: 2.6, send: 0.3)
        }
        c.crash(at: 0, amp: 0.1)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.3)
        c.applyReverb(mix: 0.32, room: 0.87, damp: 0.28)
        return c
    }

    /// Trauer: a-Moll, Klavier-Arpeggien, zarte Streicher, Cello-Grundton.
    static func composeSad() -> Canvas {
        var c = Canvas(bpm: 66, bars: 4, seed: 79)
        let chords: [[Float]] = [[57, 60, 64], [57, 60, 65], [57, 62, 65], [56, 59, 64]]   // Am F Dm E
        let roots: [Float] = [45, 41, 38, 40]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        c.wind(amp: 0.02, cutoff: 600, lfoCycles: 2)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let t = chords[b]
            let low = roots[b]
            let pattern: [Float] = [low, t[0], t[1], t[2], t[0] + 12, t[2], t[1], t[0]]
            for s in 0..<8 {
                let a: Float = s == 0 ? 0.15 : 0.1
                c.piano(pattern[s], at: t0 + Float(s) * eighth, amp: a, pan: -0.2 + Float(s) * 0.05, decay: 1.8, send: 0.2)
            }
            for k in 0..<t.count {
                c.pad(t[k], at: t0, dur: bar, amp: 0.03, pan: Float(k - 1) * 0.5, bright: 0.25, attack: 1.6, release: 2.0, detune: 0.08)
            }
            c.pad(low - 12, at: t0, dur: bar, amp: 0.09, pan: 0, bright: 0.15, attack: 0.9, release: 1.5, detune: 0.04)
        }
        let melody: [(Float, Float)] = [(76, 0), (74, 3), (72, 4), (69, 6), (74, 8), (77, 10), (76, 12), (68, 15)]
        for m in melody {
            c.piano(m.0, at: m.1 * c.beat, amp: 0.15, pan: 0.15, decay: 2.6, send: 0.35)
        }
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.35)
        c.applyReverb(mix: 0.55, room: 0.89, damp: 0.35)
        return c
    }

    /// Sieg: D-Dur mit B♭/C-Wechsel (heroisch), Blech, Pauken-Wirbel, helle Arpeggien.
    static func composeVictory() -> Canvas {
        var c = Canvas(bpm: 100, bars: 4, seed: 97)
        let chords: [[Float]] = [[62, 66, 69], [62, 65, 70], [60, 64, 67], [62, 66, 69]]   // D B♭ C D
        let roots: [Float] = [38, 34, 36, 38]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let t = chords[b]
            for k in 0..<t.count {
                c.brass(t[k], at: t0, dur: bar * 0.92, amp: 0.05, pan: Float(k - 1) * 0.4, bright: 0.75)
            }
            c.brass(roots[b] + 12, at: t0, dur: bar * 0.92, amp: 0.06, pan: 0, bright: 0.5)
            c.pad(roots[b], at: t0, dur: bar, amp: 0.1, pan: 0, bright: 0.2, attack: 0.3, release: 0.8, detune: 0.05)
            c.timpani(roots[b], at: t0, amp: 0.34)
            c.kick(at: t0, amp: 0.36)
            c.kick(at: t0 + 2 * c.beat, amp: 0.3)
            c.snare(at: t0 + c.beat, amp: 0.18, pan: 0)
            c.snare(at: t0 + 3 * c.beat, amp: 0.2, pan: 0)
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.04 : 0.025
                c.hat(at: t0 + Float(s) * eighth, amp: a, open: s == 7, pan: 0.2)
            }
            let arp: [Float] = [t[0] + 12, t[1] + 12, t[2] + 12, t[0] + 24, t[2] + 12, t[1] + 12, t[2] + 12, t[0] + 24]
            for s in 0..<8 {
                let pan: Float = s % 2 == 0 ? -0.35 : 0.35
                c.pluck(arp[s], at: t0 + Float(s) * eighth, amp: 0.04, pan: pan, decay: 0.45, ratio: 2, index: 1.4, send: 0.35)
            }
        }
        for s in 0..<16 {
            let p = Float(s) / 15
            c.timpani(36, at: 2 * bar + 2 * c.beat + Float(s) * c.beat * 0.125, amp: 0.07 + 0.2 * p)
        }
        let melody: [(Float, Float, Float)] = [
            (69, 0, 1), (74, 1, 1), (78, 2, 2), (77, 4, 1.5), (74, 5.5, 0.5), (70, 6, 2),
            (72, 8, 1), (76, 9, 1), (79, 10, 2), (81, 12, 3), (78, 15, 1)
        ]
        for m in melody {
            c.brass(m.0, at: m.1 * c.beat, dur: m.2 * c.beat, amp: 0.07, pan: 0.05, bright: 1)
        }
        c.crash(at: 0, amp: 0.12)
        c.swell(at: 3 * bar + 2 * c.beat, dur: 2 * c.beat, amp: 0.07, from: 1000, to: 10000)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.35)
        c.applyReverb(mix: 0.38, room: 0.87, damp: 0.25)
        return c
    }
}

// =====================================================================
// MARK: - Audio/Haptics.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Haptik
//  Gecachte, vorbereitete Feedback-Generatoren (nur Main-Thread).
//  Kurze Mindestabstände verhindern "Dauerbrummen" bei Kombo-Hagel.
// =====================================================================

enum Haptics {

    /// Global abschaltbar (z. B. für ein späteres Einstellungs-Flag).
    static var isEnabled: Bool = true

    private static let lightGen = UIImpactFeedbackGenerator(style: .light)
    private static let mediumGen = UIImpactFeedbackGenerator(style: .medium)
    private static let heavyGen = UIImpactFeedbackGenerator(style: .heavy)
    private static let rigidGen = UIImpactFeedbackGenerator(style: .rigid)
    private static let notifyGen = UINotificationFeedbackGenerator()
    private static let selectGen = UISelectionFeedbackGenerator()
    private static var lastFire: [Int: Double] = [:]

    /// Generatoren aufwärmen (Latenz beim ersten Treffer vermeiden).
    static func prepare() {
        lightGen.prepare()
        mediumGen.prepare()
        heavyGen.prepare()
        rigidGen.prepare()
        notifyGen.prepare()
        selectGen.prepare()
    }

    static func light() {
        guard allow(slot: 0, minInterval: 0.03) else { return }
        lightGen.impactOccurred()
        lightGen.prepare()
    }

    static func medium() {
        guard allow(slot: 1, minInterval: 0.04) else { return }
        mediumGen.impactOccurred()
        mediumGen.prepare()
    }

    static func heavy() {
        guard allow(slot: 2, minInterval: 0.05) else { return }
        heavyGen.impactOccurred()
        heavyGen.prepare()
    }

    static func success() {
        guard allow(slot: 3, minInterval: 0.25) else { return }
        notifyGen.notificationOccurred(.success)
        notifyGen.prepare()
    }

    static func warning() {
        guard allow(slot: 4, minInterval: 0.25) else { return }
        notifyGen.notificationOccurred(.warning)
        notifyGen.prepare()
    }

    // Zusätzliche Varianten

    static func error() {
        guard allow(slot: 5, minInterval: 0.25) else { return }
        notifyGen.notificationOccurred(.error)
        notifyGen.prepare()
    }

    static func selection() {
        guard allow(slot: 6, minInterval: 0.03) else { return }
        selectGen.selectionChanged()
        selectGen.prepare()
    }

    /// Harter, kurzer "Knack" (Block, Knochenbruch).
    static func rigid() {
        guard allow(slot: 7, minInterval: 0.04) else { return }
        rigidGen.impactOccurred()
        rigidGen.prepare()
    }

    /// Stufenlose Stärke 0…1 (Treffer skaliert mit Schaden).
    static func impact(_ intensity: Float) {
        let v = intensity.isFinite ? max(0, min(1, intensity)) : 0
        guard v > 0.01 else { return }
        guard allow(slot: 8, minInterval: 0.035) else { return }
        heavyGen.impactOccurred(intensity: CGFloat(v))
        heavyGen.prepare()
    }

    private static func allow(slot: Int, minInterval: Double) -> Bool {
        guard isEnabled else { return false }
        let now = CACurrentMediaTime()
        if let last = lastFire[slot], now - last < minInterval { return false }
        lastFire[slot] = now
        return true
    }
}

// =====================================================================
// MARK: - Data/Fighters.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Kämpferdaten (Roster)
//  Alle 7 Kämpfer des Blutturniers + Nebenfiguren für Cutscenes.
//  Reine Daten: Aussehen, Werte, Spezialangriffe, Exekutionen, Stimmen.
// =====================================================================

enum Roster {

    // MARK: - Öffentliche API

    /// Alle 7 Kämpfer in Anzeige-Reihenfolge (entspricht FighterID.allCases).
    static let all: [FighterDef] = FighterID.allCases.map { Roster.makeDef($0) }

    /// Definition eines Kämpfers (immer vorhanden).
    static func def(_ id: FighterID) -> FighterDef {
        if let d = Roster.defsByID[id] { return d }
        return Roster.makeDef(id)
    }

    /// Kai im Schwarzseide-Anzug: Silhouette von Silkstrike, glänzend schwarz,
    /// weiße gezackte Linsen, feine Ranken, violett-weiße Netzlinien.
    static let heroDarkSuitLook: FighterLook = FighterLook(
        build: .athletic,
        height: 1.80,
        skinColor: Roster.rgb(0xC89A7C),
        primaryColor: Roster.rgb(0x07070A),
        secondaryColor: Roster.rgb(0x13101C),
        glowColor: Roster.rgb(0xC9B6FF),
        metalness: 0.24,
        roughness: 0.11,
        hasMask: true,
        eyeStyle: .lenses,
        hairColor: nil,
        accessories: [.webLines, .tendrils]
    )

    /// Aussehen jeder Figur, die in Cutscenes auftreten kann.
    static func look(for cast: CastMember) -> FighterLook {
        switch cast {
        case .fighter(let id):
            return Roster.def(id).look
        case .heroDarkSuit:
            return Roster.heroDarkSuitLook
        case .lena:
            return Roster.lenaLook
        case .morgrim:
            return Roster.morgrimLook
        case .civilian:
            return Roster.civilianLook
        }
    }

    /// Angezeigter Name (Untertitel, HUD).
    static func displayName(for cast: CastMember) -> String {
        switch cast {
        case .fighter(let id):
            return Roster.def(id).name
        case .heroDarkSuit:
            return "Silkstrike"
        case .lena:
            return "Dr. Lena Hart"
        case .morgrim:
            return "Morgrim"
        case .civilian:
            return "Passantin"
        }
    }

    /// Stimmlage für AVSpeechSynthesizer: pitch 0.5 ... 2.0, rate 0.0 ... 1.0.
    static func voice(for cast: CastMember) -> (pitch: Float, rate: Float) {
        switch cast {
        case .fighter(let id):
            let d = Roster.def(id)
            return (pitch: d.voicePitch, rate: d.voiceRate)
        case .heroDarkSuit:
            // Kai, aber tiefer, langsamer, kälter
            return (pitch: 0.84, rate: 0.47)
        case .lena:
            return (pitch: 1.12, rate: 0.50)
        case .morgrim:
            // theatralischer Herold
            return (pitch: 0.66, rate: 0.42)
        case .civilian:
            return (pitch: 1.22, rate: 0.55)
        }
    }

    // MARK: - Zusätzliche Helfer (optional nutzbar)

    /// Signaturfarbe eines Kämpfers für UI (Auswahl, Banner, Namensleisten).
    static func signatureColor(_ id: FighterID) -> UIColor {
        switch id {
        case .silkstrike: return Roster.rgb(0x9E0F1E)
        case .nachtseide: return Roster.rgb(0x8A3DFF)
        case .vex: return Roster.rgb(0xB5521C)
        case .saya: return Roster.rgb(0x6B4BD8)
        case .brutus: return Roster.rgb(0xF2B705)
        case .inferna: return Roster.rgb(0xFF6A14)
        case .malrek: return Roster.rgb(0xB0101C)
        }
    }

    /// Sicherer Zugriff auf Spezialangriff 0 oder 1.
    static func special(_ id: FighterID, index: Int) -> SpecialMoveDef {
        let list = Roster.def(id).specials
        if list.isEmpty {
            return SpecialMoveDef(name: "Spezial", kind: .dashStrike, damage: 80, cooldown: 5,
                                  range: 5, color: .white, sound: .whoosh)
        }
        let i = Swift.max(0, Swift.min(list.count - 1, index))
        return list[i]
    }

    /// Endgegner (Kaiser Malrek).
    static func isBoss(_ id: FighterID) -> Bool {
        switch id {
        case .malrek: return true
        case .silkstrike, .nachtseide, .vex, .saya, .brutus, .inferna: return false
        }
    }

    // MARK: - Interna

    private static let defsByID: [FighterID: FighterDef] = {
        var d: [FighterID: FighterDef] = [:]
        for f in Roster.all { d[f.id] = f }
        return d
    }()

    private static func rgb(_ hex: UInt32) -> UIColor {
        let r = CGFloat((hex >> 16) & 0xFF) / 255.0
        let g = CGFloat((hex >> 8) & 0xFF) / 255.0
        let b = CGFloat(hex & 0xFF) / 255.0
        return UIColor(red: r, green: g, blue: b, alpha: 1.0)
    }

    private static func makeDef(_ id: FighterID) -> FighterDef {
        switch id {
        case .silkstrike: return Roster.silkstrikeDef()
        case .nachtseide: return Roster.nachtseideDef()
        case .vex: return Roster.vexDef()
        case .saya: return Roster.sayaDef()
        case .brutus: return Roster.brutusDef()
        case .inferna: return Roster.infernaDef()
        case .malrek: return Roster.malrekDef()
        }
    }

    // MARK: - Silkstrike (Held)

    private static func silkstrikeDef() -> FighterDef {
        let look = FighterLook(
            build: .athletic,
            height: 1.80,
            skinColor: Roster.rgb(0xC89A7C),
            primaryColor: Roster.rgb(0x9E0F1E),     // Karmesinrot
            secondaryColor: Roster.rgb(0x1E1F24),   // Anthrazit
            glowColor: Roster.rgb(0xE4EAF4),        // Silber-Weiß (Netzlinien, Linsen)
            metalness: 0.08,
            roughness: 0.42,
            hasMask: true,
            eyeStyle: .lenses,
            hairColor: nil,
            accessories: [.webLines]
        )
        let stats = FighterStats(maxHealth: 1000, walkSpeed: 3.0, power: 1.0, defense: 1.0, jumpVelocity: 9.2)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Netzgeschoss", kind: .projectile, damage: 70, cooldown: 3.0,
                           range: 12, color: Roster.rgb(0xF2F5FA), sound: .webShoot),
            SpecialMoveDef(name: "Netzzug", kind: .pullIn, damage: 55, cooldown: 5.5,
                           range: 8, color: Roster.rgb(0xDCE4F0), sound: .webZip)
        ]
        let execution = ExecutionDef(
            name: "Netz-Abriss",
            kind: .webDecapitate,
            description: "Silkstrike fesselt den Gegner mit zwei Netzsträngen und reißt ihm mit einem gewaltigen Ruck den Kopf von den Schultern."
        )
        return FighterDef(
            id: .silkstrike,
            name: "Silkstrike",
            realName: "Kai Ronan",
            title: "Der Netzläufer von Neo-Haven",
            bio: "Seit ein Splitter aus dem Riss Kai Ronans Blut mit lebender Seide verschmolzen hat, jagt er nachts durch die Häuserschluchten von Neo-Haven. Dr. Lena Hart lehrte ihn, die Kraft zu bändigen – doch das Blutturnier verlangt mehr von ihm als Mut.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "NETZBRECHER",
            introQuote: "Neo-Haven steht unter meinem Schutz. Dreh um, solange du noch kannst.",
            winQuote: "Bleib liegen. Die Stadt braucht mich noch.",
            voicePitch: 1.0,
            voiceRate: 0.52
        )
    }

    // MARK: - Nachtseide (dunkles Spiegelbild)

    private static func nachtseideDef() -> FighterDef {
        let look = FighterLook(
            build: .athletic,
            height: 1.94,
            skinColor: Roster.rgb(0x2A2530),
            primaryColor: Roster.rgb(0x060608),     // glänzendes Schwarz
            secondaryColor: Roster.rgb(0x16101F),   // Schwarz mit Violettstich
            glowColor: Roster.rgb(0x8A3DFF),        // Violett
            metalness: 0.28,
            roughness: 0.08,
            hasMask: true,
            eyeStyle: .lenses,                      // weiße, gezackte Linsen
            hairColor: nil,
            accessories: [.tendrils]
        )
        let stats = FighterStats(maxHealth: 1000, walkSpeed: 2.9, power: 1.08, defense: 0.95, jumpVelocity: 9.0)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Rankenpeitsche", kind: .pullIn, damage: 80, cooldown: 5.0,
                           range: 7.5, color: Roster.rgb(0x7A2CF0), sound: .whoosh),
            SpecialMoveDef(name: "Schattensprung", kind: .teleportStrike, damage: 100, cooldown: 7.0,
                           range: 10, color: Roster.rgb(0x5B1FB8), sound: .teleport)
        ]
        let execution = ExecutionDef(
            name: "Seelenfraß",
            kind: .devour,
            description: "Schwarze Ranken umschlingen das Opfer, ziehen sich enger und enger zusammen – bis nur noch zerfallende Seide und Knochen übrig bleiben."
        )
        return FighterDef(
            id: .nachtseide,
            name: "Nachtseide",
            realName: "Schwarzseide-Symbiont",
            title: "Das hungrige Spiegelbild",
            bio: "Ein lebendes Gewebe aus Schwarzseide, ausgespuckt vom Riss und ewig auf der Suche nach einem Wirt. Es kopiert die Kräfte jedes Körpers, den es berührt, und flüstert seinen Opfern ihre dunkelsten Wünsche ein, bevor es sie verschlingt.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "SCHWARZER HUNGER",
            introQuote: "Dein Fleisch... wird unsere Seide.",
            winQuote: "Hunger gestillt. Vorerst.",
            voicePitch: 0.55,
            voiceRate: 0.43
        )
    }

    // MARK: - Vex (Kettenklingen-Söldner)

    private static func vexDef() -> FighterDef {
        let look = FighterLook(
            build: .athletic,
            height: 1.84,
            skinColor: Roster.rgb(0xB98466),
            primaryColor: Roster.rgb(0x3B4048),     // Geschützmetall
            secondaryColor: Roster.rgb(0x8C3A14),   // Rost
            glowColor: Roster.rgb(0xFF8A2A),        // glühende Kettenglieder
            metalness: 0.5,
            roughness: 0.36,
            hasMask: false,
            eyeStyle: .human,
            hairColor: Roster.rgb(0xC9C3BA),        // silbergrau
            accessories: [.chainBlades, .scarf]
        )
        let stats = FighterStats(maxHealth: 1000, walkSpeed: 2.8, power: 1.04, defense: 1.0, jumpVelocity: 8.4)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Kettenwurf", kind: .pullIn, damage: 70, cooldown: 5.0,
                           range: 8.5, color: Roster.rgb(0xD0661F), sound: .chain),
            SpecialMoveDef(name: "Klingenwirbel", kind: .dashStrike, damage: 105, cooldown: 5.5,
                           range: 5.5, color: Roster.rgb(0xC8D0DA), sound: .slice)
        ]
        let execution = ExecutionDef(
            name: "Kettenschnitt",
            kind: .splitInHalf,
            description: "Vex schleudert beide Kettenklingen, schlingt sie um die Taille des Gegners und zieht ihn mit einem Ruck in zwei Hälften."
        )
        return FighterDef(
            id: .vex,
            name: "Vex",
            realName: "Viktor Vex",
            title: "Der Kettenhund des Kaisers",
            bio: "Ein Söldner ohne Flagge, der für den richtigen Preis jede Kette sprengt – und jeden Hals durchtrennt. Seine Klingen schmiedete er aus den Ankerketten des Hafens; seit Kaiser Malrek ihn bezahlt, jagt er jeden, der dem Turnier im Weg steht.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "KETTENREIßER",
            introQuote: "Nichts Persönliches. Auf deinen Kopf ist nur ein guter Preis ausgesetzt.",
            winQuote: "Bezahlt wird pro Stück.",
            voicePitch: 0.78,
            voiceRate: 0.51
        )
    }

    // MARK: - Saya Kurogane (Schatten-Kunoichi)

    private static func sayaDef() -> FighterDef {
        let look = FighterLook(
            build: .lean,
            height: 1.68,
            skinColor: Roster.rgb(0xE2BC9E),
            primaryColor: Roster.rgb(0x1F1A4A),     // tiefes Indigo
            secondaryColor: Roster.rgb(0x0B0B10),   // Schwarz
            glowColor: Roster.rgb(0xB07CFF),        // Violett
            metalness: 0.05,
            roughness: 0.62,
            hasMask: true,
            eyeStyle: .glow,
            hairColor: Roster.rgb(0x0A0A0E),
            accessories: [.katana, .hood, .scarf]
        )
        let stats = FighterStats(maxHealth: 1000, walkSpeed: 3.3, power: 0.95, defense: 0.92, jumpVelocity: 9.6)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Schattenschritt", kind: .teleportStrike, damage: 95, cooldown: 6.5,
                           range: 10, color: Roster.rgb(0x7E4BE0), sound: .teleport),
            SpecialMoveDef(name: "Kunai-Hagel", kind: .projectile, damage: 65, cooldown: 3.2,
                           range: 13, color: Roster.rgb(0xC9BFFF), sound: .whoosh)
        ]
        let execution = ExecutionDef(
            name: "Schattenklinge",
            kind: .shadowSlice,
            description: "Saya verschwindet in einem Schatten. Ein einziges Aufblitzen ihres Katanas – dann fliegen Kopf und Arme."
        )
        return FighterDef(
            id: .saya,
            name: "Saya",
            realName: "Saya Kurogane",
            title: "Die Klinge im Schatten",
            bio: "Die letzte Erbin des Kurogane-Clans kämpft im Blutturnier, um die Ehre ihrer ausgelöschten Familie zurückzuholen. Sie wandert durch Schatten wie andere durch offene Türen – und ihr Katana irrt sich nie.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "MONDSCHNITT",
            introQuote: "Du hörst meine Klinge erst, wenn es zu spät ist.",
            winQuote: "Der Schatten vergisst nicht.",
            voicePitch: 1.16,
            voiceRate: 0.46
        )
    }

    // MARK: - Brutus Hale (Cyborg-Schläger)

    private static func brutusDef() -> FighterDef {
        let look = FighterLook(
            build: .heavy,
            height: 2.06,
            skinColor: Roster.rgb(0xA8775E),
            primaryColor: Roster.rgb(0x8E949B),     // Chrom
            secondaryColor: Roster.rgb(0xF2B705),   // Industriegelb
            glowColor: Roster.rgb(0xFF2A1A),        // rotes Visier
            metalness: 0.78,
            roughness: 0.26,
            hasMask: false,
            eyeStyle: .visor,
            hairColor: nil,                         // kahl
            accessories: [.cyberArm, .shoulderPads]
        )
        let stats = FighterStats(maxHealth: 1200, walkSpeed: 2.2, power: 1.18, defense: 1.12, jumpVelocity: 7.2)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Hydraulikgriff", kind: .grabSlam, damage: 140, cooldown: 7.0,
                           range: 1.7, color: Roster.rgb(0xF2B705), sound: .metalHit),
            SpecialMoveDef(name: "Bodenbrecher", kind: .groundWave, damage: 95, cooldown: 5.0,
                           range: 9, color: Roster.rgb(0xFF9A1F), sound: .explosion)
        ]
        let execution = ExecutionDef(
            name: "Hydraulikpresse",
            kind: .headCrush,
            description: "Brutus packt den Kopf des Gegners mit seiner Stahlfaust, hebt ihn hoch und presst, bis die Hydraulik zischt und nichts mehr übrig ist."
        )
        return FighterDef(
            id: .brutus,
            name: "Brutus",
            realName: "Brutus Hale",
            title: "Der Koloss der Gießerei",
            bio: "Einst Vorarbeiter der Hale-Gießerei, bis ein Unfall im Schmelzwerk ihm Arm und halbes Gesicht nahm. Malreks Ingenieure gaben ihm Stahl, Hydraulik und eine Wut, die heißer glüht als jeder Hochofen.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "STAHLHAMMER",
            introQuote: "Fleisch gegen Stahl? Ich weiß, wer gewinnt.",
            winQuote: "Altmetall. Ab in den Ofen.",
            voicePitch: 0.7,
            voiceRate: 0.47
        )
    }

    // MARK: - Inferna (Feuerhexe)

    private static func infernaDef() -> FighterDef {
        let look = FighterLook(
            build: .lean,
            height: 1.74,
            skinColor: Roster.rgb(0x7A4A3A),        // rauchige, glutwarme Haut
            primaryColor: Roster.rgb(0xC2410C),     // Glutorange
            secondaryColor: Roster.rgb(0x120C0A),   // Schwarz
            glowColor: Roster.rgb(0xFFC83A),        // Gelb
            metalness: 0.06,
            roughness: 0.52,
            hasMask: false,
            eyeStyle: .glow,
            hairColor: Roster.rgb(0xB0260C),        // flammenrot
            accessories: [.flameAura, .horns]
        )
        let stats = FighterStats(maxHealth: 1000, walkSpeed: 2.75, power: 1.03, defense: 0.94, jumpVelocity: 8.6)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Höllenfeuer", kind: .projectile, damage: 85, cooldown: 3.4,
                           range: 13, color: Roster.rgb(0xFF6A14), sound: .fire),
            SpecialMoveDef(name: "Aschewelle", kind: .groundWave, damage: 90, cooldown: 5.0,
                           range: 9, color: Roster.rgb(0xFF3D0A), sound: .explosion)
        ]
        let execution = ExecutionDef(
            name: "Aschegericht",
            kind: .incinerate,
            description: "Inferna entfacht eine Säule aus Höllenfeuer, die den Gegner bei lebendigem Leib verbrennt – bis nur noch Asche im Wind tanzt."
        )
        return FighterDef(
            id: .inferna,
            name: "Inferna",
            realName: "Selene Asch",
            title: "Die Hexe des brennenden Doms",
            bio: "Seit sie das Feuer aus dem Riss getrunken hat, brennt in ihr eine Flamme, die niemals erlischt. Den Domplatz legte sie in einer einzigen Nacht in Schutt und Asche – nur um zu sehen, wie schön er brennt.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "HÖLLENSCHLUND",
            introQuote: "Komm näher, Kleiner. Ich will sehen, wie du brennst.",
            winQuote: "Asche zu Asche. So will es der Brauch.",
            voicePitch: 1.06,
            voiceRate: 0.53
        )
    }

    // MARK: - Kaiser Malrek (Endboss)

    private static func malrekDef() -> FighterDef {
        let look = FighterLook(
            build: .giant,
            height: 2.35,
            skinColor: Roster.rgb(0x9A938F),
            primaryColor: Roster.rgb(0x17171B),     // schwarzes Eisen
            secondaryColor: Roster.rgb(0x7E0A12),   // Blutrot
            glowColor: Roster.rgb(0xFF1E1E),        // rote Augen
            metalness: 0.86,
            roughness: 0.32,
            hasMask: true,
            eyeStyle: .glow,
            hairColor: nil,
            accessories: [.crown, .cape, .spikes]
        )
        let stats = FighterStats(maxHealth: 1300, walkSpeed: 2.3, power: 1.2, defense: 1.15, jumpVelocity: 7.6)
        let specials: [SpecialMoveDef] = [
            SpecialMoveDef(name: "Blutspeer", kind: .projectile, damage: 95, cooldown: 3.8,
                           range: 14, color: Roster.rgb(0xC0101E), sound: .slice),
            SpecialMoveDef(name: "Kaisergriff", kind: .grabSlam, damage: 160, cooldown: 7.5,
                           range: 1.9, color: Roster.rgb(0x8E0A14), sound: .roar)
        ]
        let execution = ExecutionDef(
            name: "Kaiserurteil",
            kind: .impaleBurst,
            description: "Malrek rammt einen Speer aus geronnenem Blut durch den Gegner, hebt ihn über sein Haupt und lässt ihn von innen zerbersten."
        )
        return FighterDef(
            id: .malrek,
            name: "Malrek",
            realName: "Kaiser Malrek",
            title: "Herrscher des Blutturniers",
            bio: "Durch den Riss hat Malrek ein Dutzend Welten erobert und ihre stärksten Krieger auf seinem Blutturm geopfert. Nun soll Neo-Haven fallen – und ihr letzter Held vor seinem Thron knien.",
            look: look,
            stats: stats,
            specials: specials,
            execution: execution,
            brutalName: "BLUTKRONE",
            introQuote: "Knie nieder. Dein Blut gehört dem Turnier.",
            winQuote: "Das Turnier ist ewig. Du warst es nicht.",
            voicePitch: 0.5,
            voiceRate: 0.39
        )
    }

    // MARK: - Nebenfiguren

    /// Dr. Lena Hart – Wissenschaftlerin, Kais Mentorin.
    private static let lenaLook: FighterLook = FighterLook(
        build: .lean,
        height: 1.70,
        skinColor: Roster.rgb(0xEBC6AA),
        primaryColor: Roster.rgb(0x3D4A5C),         // schieferblaue Bluse
        secondaryColor: Roster.rgb(0x262A31),       // dunkle Hose
        glowColor: Roster.rgb(0x8FE6FF),
        metalness: 0.0,
        roughness: 0.7,
        hasMask: false,
        eyeStyle: .human,
        hairColor: Roster.rgb(0x3A2316),            // dunkelbraun
        accessories: [.labCoat]
    )

    /// Morgrim – hagerer Herold des Blutturniers.
    private static let morgrimLook: FighterLook = FighterLook(
        build: .lean,
        height: 2.02,
        skinColor: Roster.rgb(0xDCD6CB),            // bleich
        primaryColor: Roster.rgb(0x141318),         // schwarze Robe
        secondaryColor: Roster.rgb(0x3E0E14),       // weinroter Umhang
        glowColor: Roster.rgb(0xA8FFC0),            // fahles Grün
        metalness: 0.05,
        roughness: 0.72,
        hasMask: false,
        eyeStyle: .glow,
        hairColor: Roster.rgb(0xC8C2B8),            // aschfahle Brauen
        accessories: [.hood, .cape]
    )

    /// Passantin / Geisel – schlichte Alltagskleidung.
    private static let civilianLook: FighterLook = FighterLook(
        build: .lean,
        height: 1.68,
        skinColor: Roster.rgb(0xC99475),
        primaryColor: Roster.rgb(0x5A6B7D),         // Jacke
        secondaryColor: Roster.rgb(0x2C2E33),       // Jeans
        glowColor: Roster.rgb(0xFFFFFF),
        metalness: 0.0,
        roughness: 0.8,
        hasMask: false,
        eyeStyle: .human,
        hairColor: Roster.rgb(0x2B1D15),
        accessories: []
    )
}

// =====================================================================
// MARK: - Data/Story.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Blutturnier · Story, Kapitel und Zwischensequenzen
// =====================================================================

enum StoryData {

    static let epilogueCutscene = "epilogue"

    static func cutscene(_ id: String) -> CutsceneDef? {
        return cutscenes[id]
    }

    // MARK: Kapitel

    static let chapters: [ChapterDef] = [
        ChapterDef(number: 0, title: "Neonregen", subtitle: "Ein Riss am Himmel über Neo-Haven",
                   introCutscene: "prolog_intro", objectiveText: "Schwing zu Lenas Labor im Hart-Tower",
                   objective: .labTower, opponent: .vex, arena: .rainRooftop, heroDarkSuit: false,
                   preFightCutscene: "prolog_prefight", outroCutscene: "prolog_outro", aiLevel: 0.3, timeOfDay: .dusk),
        ChapterDef(number: 1, title: "Ketten im Regen", subtitle: "Vex macht Jagd auf den Hafen",
                   introCutscene: "ch1_intro", objectiveText: "Vex jagt Hafenarbeiter – schwing zum Hafenkran",
                   objective: .harborCrane, opponent: .vex, arena: .rainRooftop, heroDarkSuit: false,
                   preFightCutscene: "ch1_prefight", outroCutscene: "ch1_outro", aiLevel: 0.45, timeOfDay: .night),
        ChapterDef(number: 2, title: "Schatten der Kurogane", subtitle: "Lena ist verschwunden",
                   introCutscene: "ch2_intro", objectiveText: "Folge Sayas Spur zum U-Bahn-Eingang",
                   objective: .subwayEntrance, opponent: .saya, arena: .subway, heroDarkSuit: false,
                   preFightCutscene: "ch2_prefight", outroCutscene: "ch2_outro", aiLevel: 0.55, timeOfDay: .night),
        ChapterDef(number: 3, title: "Schwarzseide", subtitle: "Was dich stärker macht, frisst dich auf",
                   introCutscene: "ch3_intro", objectiveText: "Brutus Hale wartet in seiner Gießerei",
                   objective: .foundry, opponent: .brutus, arena: .foundry, heroDarkSuit: true,
                   preFightCutscene: "ch3_prefight", outroCutscene: "ch3_outro", aiLevel: 0.65, timeOfDay: .stormNight),
        ChapterDef(number: 4, title: "Die Hexe aus Asche", subtitle: "Die Altstadt brennt",
                   introCutscene: "ch4_intro", objectiveText: "Inferna setzt die Altstadt in Brand – zum Dom!",
                   objective: .cathedral, opponent: .inferna, arena: .burningSquare, heroDarkSuit: true,
                   preFightCutscene: "ch4_prefight", outroCutscene: "ch4_outro", aiLevel: 0.75, timeOfDay: .night),
        ChapterDef(number: 5, title: "Spiegelbild", subtitle: "Der gefährlichste Gegner trägt dein Gesicht",
                   introCutscene: "ch5_intro", objectiveText: "Reiß die Schwarzseide dort ab, wo sie herkam: am Rissherz im Stadtpark",
                   objective: .riftCore, opponent: .nachtseide, arena: .riftRealm, heroDarkSuit: false,
                   preFightCutscene: "ch5_prefight", outroCutscene: "ch5_outro", aiLevel: 0.85, timeOfDay: .stormNight),
        ChapterDef(number: 6, title: "Der Blutturm", subtitle: "Das Finale des Blutturniers",
                   introCutscene: "ch6_intro", objectiveText: "Der Blutturm ist erwacht – beende das Turnier",
                   objective: .bloodTower, opponent: .malrek, arena: .bloodTower, heroDarkSuit: false,
                   preFightCutscene: "ch6_prefight", outroCutscene: "ch6_outro", aiLevel: 1.0, timeOfDay: .stormNight)
    ]

    static let creditsLines: [String] = [
        "SILKSTRIKE – BLUTTURNIER",
        "",
        "Eine Idee von Santo",
        "",
        "Story, Spieldesign & Programmierung",
        "Santo & Claude",
        "",
        "Besetzung",
        "Kai Ronan – Silkstrike",
        "Dr. Lena Hart",
        "Morgrim, der Herold",
        "Vex · Saya Kurogane · Brutus Hale · Inferna",
        "Nachtseide",
        "Kaiser Malrek",
        "",
        "Alle Grafiken, Klänge und Musik werden live im Code erzeugt.",
        "Gebaut mit Swift, SwiftUI und SceneKit.",
        "",
        "Danke fürs Spielen.",
        "",
        "„Ein Turnier endet. Ein anderes beginnt.“"
    ]

    // MARK: Bausteine

    private static let kai = CastMember.fighter(.silkstrike)

    private static func L(_ cast: CastMember?, _ text: String) -> DialogLine {
        let name = cast.map { Roster.displayName(for: $0) } ?? ""
        let d = Swift.max(2.4, Float(text.count) * 0.062 + 0.9)
        return DialogLine(speaker: name, voice: cast, text: text, duration: d)
    }

    private static func cam(_ from: SIMD3<Float>, _ to: SIMD3<Float>, look: SIMD3<Float>, lookTo: SIMD3<Float>? = nil,
                            fov: Float = 45, fovTo: Float? = nil, easing: Easing = .easeInOut, focus: Float? = nil) -> CameraMove {
        return CameraMove(from: from, to: to, lookFrom: look, lookTo: lookTo ?? look,
                          fovFrom: fov, fovTo: fovTo ?? fov, easing: easing, focusDistance: focus)
    }

    private static func shot(_ c: CameraMove, _ lines: [DialogLine], extra: Float = 1.0, minimum: Float = 3, events: [TimedEvent] = []) -> Shot {
        var total: Float = extra
        for l in lines { total += l.duration }
        return Shot(duration: Swift.max(minimum, total), camera: c, lines: lines, events: events)
    }

    private static func at(_ t: Float, _ e: CutsceneEvent) -> TimedEvent {
        return TimedEvent(time: t, event: e)
    }

    private static func actor(_ key: String, _ cast: CastMember, _ x: Float, _ z: Float, yaw: Float, _ clip: AnimClip) -> CutsceneActor {
        return CutsceneActor(key: key, cast: cast, position: SIMD3<Float>(x, 0, z), yawDegrees: yaw, clip: clip)
    }

    private static func v(_ x: Float, _ y: Float, _ z: Float) -> SIMD3<Float> {
        return SIMD3<Float>(x, y, z)
    }

    // Standard-Einstellungen für Dialoge zwischen links (x = -1.2) und rechts (x = +1.2)
    private static func overLeft(fov: Float = 40) -> CameraMove {
        return cam(v(-2.3, 1.65, 1.5), v(-2.1, 1.62, 1.2), look: v(1.2, 1.5, 0), fov: fov)
    }
    private static func overRight(fov: Float = 40) -> CameraMove {
        return cam(v(2.3, 1.65, 1.5), v(2.1, 1.62, 1.2), look: v(-1.2, 1.5, 0), fov: fov)
    }
    private static func twoShot() -> CameraMove {
        return cam(v(0, 1.45, 5.0), v(0, 1.5, 4.0), look: v(0, 1.3, 0), fov: 42)
    }
    private static func heroLow(_ x: Float) -> CameraMove {
        return cam(v(x + 0.6, 0.35, 2.2), v(x + 0.3, 0.45, 1.7), look: v(x, 1.7, 0), fov: 38, fovTo: 34)
    }

    // MARK: Zwischensequenzen

    static let cutscenes: [String: CutsceneDef] = {
        let all: [CutsceneDef] = [
            prologIntro(), prologPrefight(), prologOutro(),
            ch1Intro(), ch1Prefight(), ch1Outro(),
            ch2Intro(), ch2Prefight(), ch2Outro(),
            ch3Intro(), ch3Prefight(), ch3Outro(),
            ch4Intro(), ch4Prefight(), ch4Outro(),
            ch5Intro(), ch5Prefight(), ch5Outro(),
            ch6Intro(), ch6Prefight(), ch6Outro(),
            epilogue()
        ]
        var dict: [String: CutsceneDef] = [:]
        for c in all { dict[c.id] = c }
        return dict
    }()

    // ---------------------------------------------------------------- Prolog

    private static func prologIntro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 2, 14), v(0, 6, 22), look: v(0, 1.5, 0), lookTo: v(0, 3, -40), fov: 55, fovTo: 60),
                            [L(nil, "Neo-Haven. Zwölf Millionen Menschen. Und keiner schaut nach oben.")], extra: 2,
                            events: [at(0, .music(.tension)), at(0.5, .sound(.thunder))])
        let s2: Shot = shot(heroLow(0),
                            [L(kai, "Zwei Jahre mit Spinnenseide im Blut. Und immer noch kein Plan, wie man pünktlich ist."),
                             L(kai, "Morgen Physikprüfung. Heute Nacht: Patrouille. Klingt fair.")],
                            events: [at(0.2, .clip(actor: "kai", .perch)), at(3.5, .clip(actor: "kai", .lookAround))])
        let s3: Shot = shot(cam(v(0, 1.6, 4), v(0, 2.4, 6), look: v(0, 1.6, 0), lookTo: v(0, 30, -60), fov: 45, fovTo: 62),
                            [L(kai, "Okay… DAS war gerade nicht der Mond.")], extra: 2.5,
                            events: [at(0.3, .sound(.riftHum)), at(0.8, .flash(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1))),
                                     at(0.9, .shake(0.6)), at(1.0, .clip(actor: "kai", .crossArms))])
        let s4: Shot = shot(cam(v(-3, 3, 9), v(-2, 2.5, 7), look: v(0, 2, 0), fov: 50),
                            [L(.morgrim, "Hört mich, Kinder dieser Welt. Das Blutturnier hat begonnen."),
                             L(.morgrim, "Eure Welt stellt einen Champion. Oder sie brennt."),
                             L(kai, "Na super. Und ich hab morgen Prüfung.")],
                            events: [at(0, .show(actor: "morgrim")), at(0.1, .effect(.riftPortal, position: v(4, 2, -3))),
                                     at(0.2, .clip(actor: "morgrim", .point))])
        let s5: Shot = shot(cam(v(0, 1.4, 3), v(0, 1.8, 4.5), look: v(0, 1.4, 0), fov: 40),
                            [L(.lena, "Kai? Hier Lena. Siehst du das auch? Komm sofort ins Labor."),
                             L(kai, "Bin schon unterwegs. Halt den Kaffee warm.")],
                            events: [at(0, .hide(actor: "morgrim")), at(0.2, .clip(actor: "kai", .talk)), at(5.5, .clip(actor: "kai", .jump))])
        return CutsceneDef(id: "prolog_intro", title: "PROLOG · NEONREGEN", stage: .cityRooftop, timeOfDay: .dusk, music: .tension,
                           actors: [actor("kai", kai, 0, 0, yaw: 180, .perch),
                                    actor("morgrim", .morgrim, 3.5, -2.5, yaw: -40, .crossArms)],
                           shots: [s1, s2, s3, s4, s5])
    }

    private static func prologPrefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 3, 9), v(0, 2, 6.5), look: v(0, 1.2, 0), fov: 50),
                            [L(.lena, "Kai, die Energiesignatur kommt direkt auf dich zu!")],
                            events: [at(0.5, .sound(.riftHum)), at(1.5, .effect(.riftPortal, position: v(1.5, 1.5, 0))),
                                     at(1.8, .show(actor: "vex")), at(1.9, .shake(0.5)), at(1.9, .sound(.chain))])
        let s2: Shot = shot(heroLow(1.5),
                            [L(.fighter(.vex), "Ein Champion in Strumpfhosen. Malrek hat Humor."),
                             L(.fighter(.vex), "Ich bin Vex. Ich bin nur hier, um zu sehen, wie viel du aushältst.")],
                            events: [at(0.2, .clip(actor: "vex", .taunt))])
        let s3: Shot = shot(overRight(),
                            [L(kai, "Probekampf? Ich hasse Probekämpfe."),
                             L(.fighter(.vex), "Dann lern schnell, Spinne.")],
                            events: [at(0.1, .clip(actor: "kai", .fightIdle)), at(4.5, .clip(actor: "vex", .fightIdle))])
        return CutsceneDef(id: "prolog_prefight", title: nil, stage: .arena(.rainRooftop), timeOfDay: .dusk, music: .combat,
                           actors: [actor("kai", kai, -1.5, 0, yaw: 90, .idle),
                                    actor("vex", .fighter(.vex), 1.5, 0, yaw: -90, .crossArms)],
                           shots: [s1, s2, s3])
    }

    private static func prologOutro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(1.5, 0.8, 3.2), v(1.0, 1.0, 2.6), look: v(1.2, 0.6, 0), fov: 40),
                            [L(.fighter(.vex), "Nicht schlecht… für einen Anfänger."),
                             L(.fighter(.vex), "Aber das war nur das Aufwärmen. Das Turnier fängt erst an.")],
                            events: [at(0, .clip(actor: "vex", .kneel))])
        let s2: Shot = shot(cam(v(0, 2, 6), v(0, 2.5, 8), look: v(1.2, 1, 0), fov: 45),
                            [L(kai, "Hey! Wir waren noch nicht fertig!")],
                            events: [at(0.4, .effect(.shadowBurst, position: v(1.2, 1, 0))), at(0.45, .hide(actor: "vex")),
                                     at(0.45, .sound(.teleport)), at(0.6, .clip(actor: "kai", .point))])
        let s3: Shot = shot(cam(v(-1.6, 1.6, 2.4), v(-1.4, 1.6, 2.0), look: v(-1.2, 1.5, 0), fov: 36),
                            [L(.lena, "Kai… das Ding an seinen Ketten. Das war keine Seide aus unserer Welt."),
                             L(kai, "Lena, bitte sag mir, dass du einen Plan hast."),
                             L(.lena, "Ich habe eine Theorie. Und Angst. Komm vorbei, wenn du kannst.")],
                            events: [at(0.1, .clip(actor: "kai", .talk))])
        return CutsceneDef(id: "prolog_outro", title: nil, stage: .arena(.rainRooftop), timeOfDay: .dusk, music: .sad,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .fightIdle),
                                    actor("vex", .fighter(.vex), 1.2, 0, yaw: -90, .kneel)],
                           shots: [s1, s2, s3])
    }

    // ---------------------------------------------------------------- Kapitel 1

    private static func ch1Intro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 2.2, 7), v(0, 2.0, 5), look: v(0, 1.3, 0), fov: 48),
                            [L(.lena, "Ich habe die Signatur von gestern Nacht weiterverfolgt. Sie springt durch den Hafen."),
                             L(.lena, "Und Kai… es verschwinden Hafenarbeiter. Drei in einer Stunde.")],
                            events: [at(0, .music(.tension)), at(0.3, .clip(actor: "lena", .talk))])
        let s2: Shot = shot(overRight(fov: 38),
                            [L(kai, "Vex."),
                             L(.lena, "Er sammelt sie. Wie Trophäen. Für das Turnier."),
                             L(kai, "Dann hole ich sie mir zurück.")],
                            events: [at(0.2, .clip(actor: "kai", .crossArms))])
        let s3: Shot = shot(cam(v(-1.6, 1.4, 2.4), v(-1.2, 1.5, 1.8), look: v(-1.2, 1.6, 0), fov: 34),
                            [L(.lena, "Pass auf dich auf. Ich kann keine Formeln mehr erklären, wenn du tot bist."),
                             L(kai, "Charmant wie immer, Doktor.")],
                            events: [at(4.5, .clip(actor: "kai", .point))])
        return CutsceneDef(id: "ch1_intro", title: "KAPITEL 1 · KETTEN IM REGEN", stage: .lab, timeOfDay: .night, music: .tension,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("lena", .lena, 1.2, 0, yaw: -90, .talk)],
                           shots: [s1, s2, s3])
    }

    private static func ch1Prefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(4, 3, 8), v(2, 2, 6), look: v(1.4, 1.3, 0), fov: 46),
                            [L(.fighter(.vex), "Da ist ja meine Spinne. Bist du gekommen, um die Kette zu küssen?")],
                            events: [at(0.2, .clip(actor: "vex", .taunt)), at(0.4, .sound(.chain))])
        let s2: Shot = shot(overLeft(),
                            [L(kai, "Wo sind die Arbeiter, Vex?"),
                             L(.fighter(.vex), "Im Tausch gegen Seelen. Malrek zahlt gut. Besser als dein Gewissen."),
                             L(kai, "Mein Gewissen schlägt härter, als du denkst.")],
                            events: [at(0.1, .clip(actor: "kai", .fightIdle))])
        let s3: Shot = shot(cam(v(0, 0.5, 3), v(0, 0.7, 2.4), look: v(0, 1.3, 0), fov: 50, fovTo: 40),
                            [L(.fighter(.vex), "Dann zeig's mir.")], extra: 1.5,
                            events: [at(0.4, .clip(actor: "vex", .fightIdle)), at(1.2, .sound(.thunder)), at(1.2, .flash(.white))])
        return CutsceneDef(id: "ch1_prefight", title: nil, stage: .arena(.rainRooftop), timeOfDay: .night, music: .combat,
                           actors: [actor("kai", kai, -1.4, 0, yaw: 90, .idle),
                                    actor("vex", .fighter(.vex), 1.4, 0, yaw: -90, .crossArms)],
                           shots: [s1, s2, s3])
    }

    private static func ch1Outro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(1, 0.6, 3), v(0.6, 0.9, 2.2), look: v(1.2, 0.5, 0), fov: 38),
                            [L(.fighter(.vex), "Du… kapierst es nicht. Ich bin nur eine Kette. Malrek ist die Hand."),
                             L(.fighter(.vex), "Und die Hand hat schon ein Auge auf dich geworfen.")],
                            events: [at(0, .clip(actor: "vex", .kneel)), at(0.5, .effect(.shadowBurst, position: v(1.2, 0.4, 0)))])
        let s2: Shot = shot(cam(v(-1.8, 1.5, 2.2), v(-1.5, 1.5, 1.8), look: v(1.2, 0.4, 0), fov: 36),
                            [L(.lena, "Kai, sieh dir die Ketten an. Da tropft etwas Schwarzes heraus."),
                             L(kai, "Es bewegt sich. Lena, es bewegt sich."),
                             L(.lena, "Nimm eine Probe. Vorsichtig. Wir müssen wissen, womit wir es zu tun haben.")],
                            events: [at(0.5, .clip(actor: "kai", .kneel))])
        let s3: Shot = shot(cam(v(0, 2.5, 6), v(0, 4, 9), look: v(0, 1, 0), fov: 50),
                            [L(nil, "Die Arbeiter kommen nach Hause. Doch etwas Dunkles reist mit.")], extra: 1.5,
                            events: [at(0.2, .music(.sad))])
        return CutsceneDef(id: "ch1_outro", title: nil, stage: .arena(.rainRooftop), timeOfDay: .night, music: .sad,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("vex", .fighter(.vex), 1.2, 0, yaw: -90, .kneel)],
                           shots: [s1, s2, s3])
    }

    // ---------------------------------------------------------------- Kapitel 2

    private static func ch2Intro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 2, 6), v(0, 1.7, 4.5), look: v(0, 1.2, 0), fov: 46),
                            [L(kai, "Lena? Ich hab die Probe. Lena?")], extra: 1.5,
                            events: [at(0, .music(.tension)), at(1.5, .sound(.heartbeat))])
        let s2: Shot = shot(cam(v(1.5, 1.2, 2.5), v(1.0, 1.3, 2.0), look: v(1.2, 1.0, 0), fov: 38),
                            [L(nil, "Das Labor ist verwüstet. In der Wand steckt ein schwarzer Kunai."),
                             L(kai, "Kurogane. Das Zeichen auf der Klinge… das ist ein Clanwappen.")],
                            events: [at(0.2, .clip(actor: "kai", .kneel)), at(0.3, .effect(.shadowBurst, position: v(1.5, 1.2, -1)))])
        let s3: Shot = shot(cam(v(0, 1.0, 3), v(0, 1.6, 2.2), look: v(0, 1.6, 0), fov: 40, fovTo: 32),
                            [L(.morgrim, "Die Schattenklinge hat deine Gelehrte, Champion."),
                             L(.morgrim, "Folge dem Schatten unter die Stadt. Oder vergiss sie."),
                             L(kai, "Ich vergesse nie jemanden.")],
                            events: [at(0, .clip(actor: "kai", .fightIdle)), at(8.0, .clip(actor: "kai", .jump))])
        return CutsceneDef(id: "ch2_intro", title: "KAPITEL 2 · SCHATTEN DER KUROGANE", stage: .lab, timeOfDay: .night, music: .tension,
                           actors: [actor("kai", kai, 0, 0.5, yaw: 0, .lookAround)],
                           shots: [s1, s2, s3])
    }

    private static func ch2Prefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(-4, 2, 7), v(-2.5, 1.8, 5.5), look: v(1.5, 1.2, 0), fov: 46),
                            [L(.lena, "Kai! Es ist eine Falle!")],
                            events: [at(0.2, .clip(actor: "lena", .kneel)), at(1.6, .effect(.shadowBurst, position: v(1.3, 1, 0))),
                                     at(1.7, .show(actor: "saya")), at(1.7, .sound(.teleport))])
        let s2: Shot = shot(cam(v(2.6, 1.6, 2), v(2.3, 1.6, 1.6), look: v(1.3, 1.6, 0), fov: 34),
                            [L(.fighter(.saya), "Ich bin Saya Kurogane. Ich habe nichts gegen dich, Champion."),
                             L(.fighter(.saya), "Aber mein Eid gehört Malrek. Und Eide werden mit Blut gehalten.")],
                            events: [at(0.1, .clip(actor: "saya", .crossArms))])
        let s3: Shot = shot(overLeft(),
                            [L(kai, "Lass sie gehen. Dann musst du keinen Eid brechen."),
                             L(.fighter(.saya), "Besiege mich. Dann muss ich es nicht.")],
                            events: [at(0.1, .clip(actor: "kai", .fightIdle)), at(4.5, .clip(actor: "saya", .fightIdle))])
        return CutsceneDef(id: "ch2_prefight", title: nil, stage: .arena(.subway), timeOfDay: .night, music: .combat,
                           actors: [actor("kai", kai, -1.4, 0, yaw: 90, .idle),
                                    actor("saya", .fighter(.saya), 1.3, 0, yaw: -90, .crossArms),
                                    actor("lena", .lena, 4.5, -2.5, yaw: -120, .kneel)],
                           shots: [s1, s2, s3])
    }

    private static func ch2Outro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0.5, 1.0, 2.6), v(0.3, 1.2, 2.0), look: v(1.2, 1.0, 0), fov: 36),
                            [L(.fighter(.saya), "Du hättest mich töten können."),
                             L(kai, "Ich bin nicht hier, um zu töten. Ich bin hier, um Leute nach Hause zu bringen.")],
                            events: [at(0, .clip(actor: "saya", .kneel))])
        let s2: Shot = shot(cam(v(2.4, 1.6, 1.8), v(2.2, 1.6, 1.5), look: v(1.2, 1.2, 0), fov: 34),
                            [L(.fighter(.saya), "Malrek hält meine Schwester in seinem Turm. Darum diene ich."),
                             L(.fighter(.saya), "Mein Eid gehört Malrek. Mein Herz nicht.")],
                            events: [at(0.3, .clip(actor: "saya", .talk))])
        let s3: Shot = shot(cam(v(0, 2, 6), v(0, 2.2, 7), look: v(1.2, 1, 0), fov: 44),
                            [L(.lena, "Sie ist weg… Kai, ich hab die Probe analysiert, bevor sie kamen."),
                             L(.lena, "Diese schwarze Seide reagiert auf dich. Auf deine Wut. Sei vorsichtig damit.")],
                            events: [at(0.2, .effect(.shadowBurst, position: v(1.2, 1, 0))), at(0.25, .hide(actor: "saya")),
                                     at(0.3, .sound(.teleport)), at(1.0, .show(actor: "lena"))])
        return CutsceneDef(id: "ch2_outro", title: nil, stage: .arena(.subway), timeOfDay: .night, music: .sad,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("saya", .fighter(.saya), 1.2, 0, yaw: -90, .kneel),
                                    actor("lena", .lena, -2.6, -1.2, yaw: 60, .idle)],
                           shots: [s1, s2, s3])
    }

    // ---------------------------------------------------------------- Kapitel 3

    private static func ch3Intro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 1.6, 4), v(0.6, 1.5, 3), look: v(0, 1.3, 0), fov: 42),
                            [L(.lena, "Brutus Hale hat die Stadt verkauft. Für einen Körper, der nicht stirbt."),
                             L(kai, "Der Typ, der mir mit sechzehn den Ferienjob gekündigt hat? Hab ihn immer gemocht.")],
                            events: [at(0, .music(.tension)), at(0.2, .clip(actor: "lena", .talk))])
        let s2: Shot = shot(overLeft(fov: 36),
                            [L(.lena, "Er wartet in seiner Gießerei. Und er weiß, dass du die Probe trägst."),
                             L(kai, "Die Probe ist sicher. In meinem Gürtel."),
                             L(.lena, "Genau das macht mir Sorgen.")],
                            events: [at(0.2, .clip(actor: "kai", .crossArms))])
        return CutsceneDef(id: "ch3_intro", title: "KAPITEL 3 · SCHWARZSEIDE", stage: .lab, timeOfDay: .stormNight, music: .tension,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("lena", .lena, 1.2, 0, yaw: -90, .talk)],
                           shots: [s1, s2])
    }

    private static func ch3Prefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(5, 2.5, 8), v(3, 2, 6), look: v(1.5, 1.6, 0), fov: 48),
                            [L(.fighter(.brutus), "RONAN! Der kleine Praktikant mit dem Spinnenkostüm!"),
                             L(.fighter(.brutus), "Malrek hat mir einen Körper aus Stahl gegeben. Und dir? Einen Schlafanzug.")],
                            events: [at(0.2, .clip(actor: "brutus", .taunt)), at(0.6, .sound(.metalHit))])
        let s2: Shot = shot(cam(v(-1.0, 1.0, 2.6), v(-1.2, 1.1, 2.0), look: v(-1.4, 1.2, 0), fov: 36),
                            [L(nil, "Ein Schlag. Kai kracht in die Wand. Die Probe zerbricht."),
                             L(.fighter(.nachtseide), "Endlich… Lass mich rein, Kai.")],
                            events: [at(0.2, .clip(actor: "kai", .hitHigh)), at(0.25, .shake(0.7)), at(0.25, .sound(.punchHeavy)),
                                     at(1.2, .clip(actor: "kai", .kneel)), at(2.5, .effect(.shadowBurst, position: v(-1.4, 1, 0))),
                                     at(2.6, .sound(.roar)), at(2.7, .slowMotion(0.4))])
        let s3: Shot = shot(cam(v(-2.4, 0.4, 2.0), v(-2.0, 0.6, 1.6), look: v(-1.4, 1.7, 0), fov: 40, fovTo: 32),
                            [L(kai, "Was… ist… das?"),
                             L(.fighter(.nachtseide), "Das bist du. Ohne Angst.")],
                            events: [at(0.1, .slowMotion(1)), at(0.3, .setCast(actor: "kai", .heroDarkSuit)),
                                     at(0.3, .flash(UIColor(red: 0.4, green: 0, blue: 0.6, alpha: 1))), at(0.4, .shake(0.8)),
                                     at(1.0, .clip(actor: "kai", .getUp)), at(3.0, .clip(actor: "kai", .fightIdle))])
        let s4: Shot = shot(cam(v(0, 0.6, 3.2), v(0, 0.8, 2.6), look: v(0, 1.4, 0), fov: 46),
                            [L(.fighter(.brutus), "Neues Kostüm? Bricht genauso leicht."),
                             L(kai, "Komm her und find's raus.")],
                            events: [at(0.1, .clip(actor: "brutus", .fightIdle)), at(0.2, .music(.combat))])
        return CutsceneDef(id: "ch3_prefight", title: nil, stage: .arena(.foundry), timeOfDay: .stormNight, music: .tension,
                           actors: [actor("kai", kai, -1.4, 0, yaw: 90, .fightIdle),
                                    actor("brutus", .fighter(.brutus), 1.5, 0, yaw: -90, .crossArms)],
                           shots: [s1, s2, s3, s4])
    }

    private static func ch3Outro() -> CutsceneDef {
        let dark = CastMember.heroDarkSuit
        let s1: Shot = shot(cam(v(0.4, 0.8, 2.4), v(0.2, 1.0, 1.9), look: v(1.0, 0.7, 0), fov: 36),
                            [L(.fighter(.brutus), "Gnade… Ronan, bitte…"),
                             L(.fighter(.nachtseide), "Er hat die Stadt verkauft. Mach ihn kaputt. Er hat es verdient.")],
                            events: [at(0, .clip(actor: "brutus", .kneel)), at(0.4, .clip(actor: "kai", .grab))])
        let s2: Shot = shot(cam(v(-1.8, 1.6, 1.6), v(-1.6, 1.6, 1.3), look: v(-0.6, 1.6, 0), fov: 32),
                            [L(.lena, "Kai! Hör auf! Das bist nicht du!")], extra: 1.6,
                            events: [at(0.1, .sound(.heartbeat)), at(1.0, .slowMotion(0.5)), at(2.2, .slowMotion(1))])
        let s3: Shot = shot(cam(v(0, 1.6, 4), v(0, 1.7, 5), look: v(-0.6, 1.3, 0), fov: 42),
                            [L(dark, "Ich… ich hätte ihn fast umgebracht."),
                             L(.lena, "Aber du hast es nicht getan. Halt dich daran fest."),
                             L(dark, "Und was, wenn ich das nächste Mal nicht mehr loslasse?")],
                            events: [at(0, .clip(actor: "kai", .kneel)), at(0.5, .music(.sad))])
        return CutsceneDef(id: "ch3_outro", title: nil, stage: .arena(.foundry), timeOfDay: .stormNight, music: .sad,
                           actors: [actor("kai", dark, -0.6, 0, yaw: 90, .fightIdle),
                                    actor("brutus", .fighter(.brutus), 1.0, 0, yaw: -90, .kneel)],
                           shots: [s1, s2, s3])
    }

    // ---------------------------------------------------------------- Kapitel 4

    private static func ch4Intro() -> CutsceneDef {
        let dark = CastMember.heroDarkSuit
        let s1: Shot = shot(cam(v(0, 3, 10), v(0, 2, 7), look: v(0, 1.5, 0), fov: 52),
                            [L(nil, "Die Altstadt brennt. Und mitten im Feuer singt jemand.")], extra: 1.5,
                            events: [at(0, .music(.tension)), at(0.5, .effect(.fireBurst, position: v(3, 0.5, -3))),
                                     at(1.2, .effect(.fireBurst, position: v(-3, 0.5, -4)))])
        let s2: Shot = shot(heroLow(0),
                            [L(.fighter(.nachtseide), "Hörst du sie? Sie verbrennt deine Stadt. Lass mich die Arbeit machen, Kai."),
                             L(dark, "Halt die Klappe. Ich mach das auf meine Art.")],
                            events: [at(0.2, .clip(actor: "kai", .perch))])
        let s3: Shot = shot(cam(v(0, 1.5, 3.5), v(0.5, 1.6, 2.8), look: v(0, 1.5, 0), fov: 40),
                            [L(.lena, "Inferna ist am Dom. Kai… die Seide wächst. Ich sehe es auf den Scans."),
                             L(dark, "Dann sollte ich mich beeilen.")],
                            events: [at(4.0, .clip(actor: "kai", .jump))])
        return CutsceneDef(id: "ch4_intro", title: "KAPITEL 4 · DIE HEXE AUS ASCHE", stage: .cityRooftop, timeOfDay: .night, music: .tension,
                           actors: [actor("kai", dark, 0, 0, yaw: 180, .perch)],
                           shots: [s1, s2, s3])
    }

    private static func ch4Prefight() -> CutsceneDef {
        let dark = CastMember.heroDarkSuit
        let s1: Shot = shot(cam(v(3, 1.2, 5), v(2.2, 1.6, 3.5), look: v(1.5, 1.6, 0), fov: 44),
                            [L(.fighter(.inferna), "Ein Spinnlein, schwarz wie Ruß, kommt zu Infernas Feuerkuss!"),
                             L(.fighter(.inferna), "Ich hab meine eigene Welt verbrannt, Kleiner. Deine ist nur Zunder.")],
                            events: [at(0.2, .clip(actor: "inferna", .taunt)), at(0.5, .effect(.fireBurst, position: v(1.5, 1.2, 0))),
                                     at(0.5, .sound(.fire))])
        let s2: Shot = shot(overLeft(),
                            [L(dark, "Warum? Warum dienst du ihm?"),
                             L(.fighter(.inferna), "Weil Malrek mir versprochen hat, dass das Feuer niemals ausgeht.")],
                            events: [at(0.2, .clip(actor: "kai", .fightIdle))])
        let s3: Shot = shot(cam(v(0, 0.5, 3.2), v(0, 0.6, 2.6), look: v(0, 1.4, 0), fov: 48),
                            [L(dark, "Dann mach ich's aus.")], extra: 1.5,
                            events: [at(0.4, .clip(actor: "inferna", .fightIdle)), at(1.0, .music(.combat))])
        return CutsceneDef(id: "ch4_prefight", title: nil, stage: .arena(.burningSquare), timeOfDay: .night, music: .combat,
                           actors: [actor("kai", dark, -1.4, 0, yaw: 90, .idle),
                                    actor("inferna", .fighter(.inferna), 1.5, 0, yaw: -90, .crossArms)],
                           shots: [s1, s2, s3])
    }

    private static func ch4Outro() -> CutsceneDef {
        let dark = CastMember.heroDarkSuit
        let s1: Shot = shot(cam(v(0, 1.2, 3), v(0, 1.4, 2.4), look: v(0, 1.4, 0), fov: 38),
                            [L(.fighter(.nachtseide), "Sie hat gebrannt, weil ICH dich stark gemacht habe."),
                             L(.fighter(.nachtseide), "Ohne mich bist du wieder nur ein Junge mit einer Prüfung."),
                             L(dark, "Vielleicht. Aber dann bin wenigstens ich es.")],
                            events: [at(0, .clip(actor: "kai", .kneel)), at(0.3, .effect(.shadowBurst, position: v(0, 1, 0)))])
        let s2: Shot = shot(cam(v(-2, 1.6, 3), v(-1.5, 1.7, 2.4), look: v(0, 1.5, 0), fov: 40),
                            [L(.lena, "Kai, die Seide stammt aus dem Rissherz über dem Stadtpark."),
                             L(.lena, "Wenn du sie loswerden willst, dann dort, wo sie herkam."),
                             L(dark, "Dann geh ich zurück zum Anfang.")],
                            events: [at(0.2, .clip(actor: "kai", .getUp)), at(2.0, .music(.sad))])
        return CutsceneDef(id: "ch4_outro", title: nil, stage: .arena(.burningSquare), timeOfDay: .night, music: .sad,
                           actors: [actor("kai", dark, 0, 0, yaw: 0, .kneel)],
                           shots: [s1, s2])
    }

    // ---------------------------------------------------------------- Kapitel 5

    private static func ch5Intro() -> CutsceneDef {
        let dark = CastMember.heroDarkSuit
        let s1: Shot = shot(cam(v(0, 1.5, 4), v(0, 1.6, 3.2), look: v(0, 1.4, 0), fov: 40),
                            [L(.lena, "Wenn du sie abreißt, wehrt sie sich. Sie wird versuchen, du zu sein."),
                             L(dark, "Dann sehe ich wenigstens mal, wie ich von außen aussehe.")],
                            events: [at(0, .music(.tension)), at(0.2, .clip(actor: "lena", .talk))])
        let s2: Shot = shot(overRight(fov: 36),
                            [L(.lena, "Kai… ich habe dich nie gefragt, warum du das alles machst."),
                             L(dark, "Weil es jemand machen muss. Und weil ich's kann. Meistens."),
                             L(.lena, "Komm zurück. Das ist keine Bitte.")],
                            events: [at(0.2, .clip(actor: "kai", .crossArms))])
        return CutsceneDef(id: "ch5_intro", title: "KAPITEL 5 · SPIEGELBILD", stage: .lab, timeOfDay: .stormNight, music: .tension,
                           actors: [actor("kai", dark, -1.2, 0, yaw: 90, .idle),
                                    actor("lena", .lena, 1.2, 0, yaw: -90, .talk)],
                           shots: [s1, s2])
    }

    private static func ch5Prefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 2.5, 7), v(0, 1.8, 4.5), look: v(-1.2, 1.4, 0), fov: 50),
                            [L(nil, "Im Herzen des Risses. Die Seide brennt auf der Haut.")], extra: 1.0,
                            events: [at(0, .sound(.riftHum)), at(0.5, .clip(actor: "kai", .kneel))])
        let s2: Shot = shot(cam(v(-2.2, 1.0, 2.0), v(-1.8, 1.2, 1.6), look: v(-1.2, 1.4, 0), fov: 34),
                            [L(kai, "Raus. Aus. Mir!")], extra: 2.4,
                            events: [at(0.4, .clip(actor: "kai", .getUp)), at(1.0, .slowMotion(0.35)),
                                     at(1.1, .setCast(actor: "kai", .fighter(.silkstrike))),
                                     at(1.1, .effect(.shadowBurst, position: v(-1.2, 1.2, 0))),
                                     at(1.1, .flash(.white)), at(1.1, .shake(1)), at(1.2, .sound(.roar)),
                                     at(1.3, .show(actor: "nacht")), at(2.0, .slowMotion(1))])
        let s3: Shot = shot(cam(v(2.6, 1.5, 1.8), v(2.4, 1.6, 1.4), look: v(1.4, 1.6, 0), fov: 34),
                            [L(.fighter(.nachtseide), "Du wirfst mich weg? Ich BIN deine Kraft, Kai."),
                             L(.fighter(.nachtseide), "Jeder Schlag, den du je bereut hast. Ich hab sie alle gespeichert.")],
                            events: [at(0.2, .clip(actor: "nacht", .taunt))])
        let s4: Shot = shot(overLeft(),
                            [L(kai, "Dann lösche ich dich eben. Schlag für Schlag.")], extra: 1.5,
                            events: [at(0.2, .clip(actor: "kai", .fightIdle)), at(1.0, .clip(actor: "nacht", .fightIdle)),
                                     at(1.2, .music(.boss))])
        return CutsceneDef(id: "ch5_prefight", title: nil, stage: .arena(.riftRealm), timeOfDay: .stormNight, music: .tension,
                           actors: [actor("kai", .heroDarkSuit, -1.2, 0, yaw: 90, .idle),
                                    actor("nacht", .fighter(.nachtseide), 1.4, 0, yaw: -90, .crossArms)],
                           shots: [s1, s2, s3, s4])
    }

    private static func ch5Outro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0.4, 1.0, 2.6), v(0.2, 1.2, 2.0), look: v(1.2, 1.0, 0), fov: 36),
                            [L(.fighter(.nachtseide), "Ohne mich… wirst du verlieren. Gegen ihn."),
                             L(kai, "Ich bin nicht du. Aber ich weiß jetzt, wie du klingst."),
                             L(kai, "Und wenn ich dich wieder höre, weiß ich, dass ich aufpassen muss.")],
                            events: [at(0, .clip(actor: "nacht", .kneel)), at(7.5, .effect(.shadowBurst, position: v(1.2, 1, 0))),
                                     at(7.6, .hide(actor: "nacht")), at(7.6, .sound(.teleport))])
        let s2: Shot = shot(cam(v(0, 2, 6), v(0, 6, 12), look: v(0, 2, 0), lookTo: v(0, 20, -60), fov: 45, fovTo: 60),
                            [L(.morgrim, "Der Champion hat sich selbst bezwungen. Wie… unterhaltsam."),
                             L(.morgrim, "Der Kaiser erwartet dich. Der Turm erwacht.")],
                            events: [at(0.5, .sound(.thunder)), at(0.6, .shake(0.6)), at(1.0, .music(.boss))])
        return CutsceneDef(id: "ch5_outro", title: nil, stage: .arena(.riftRealm), timeOfDay: .stormNight, music: .sad,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("nacht", .fighter(.nachtseide), 1.2, 0, yaw: -90, .kneel)],
                           shots: [s1, s2])
    }

    // ---------------------------------------------------------------- Kapitel 6

    private static func ch6Intro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 1, 5), v(0, 3, 9), look: v(0, 2, 0), lookTo: v(0, 40, -80), fov: 50, fovTo: 64),
                            [L(nil, "Im Zentrum von Neo-Haven bricht ein Turm aus dem Asphalt. Rot. Lebendig.")], extra: 2,
                            events: [at(0, .music(.boss)), at(0.5, .shake(0.8)), at(0.5, .sound(.thunder)),
                                     at(1.5, .flash(UIColor(red: 1, green: 0, blue: 0.05, alpha: 1)))])
        let s2: Shot = shot(heroLow(0),
                            [L(.lena, "Kai, die Energie da oben würde die halbe Küste auslöschen."),
                             L(kai, "Also kein Druck."),
                             L(.lena, "Ich meine es ernst. Komm. Zurück.")],
                            events: [at(0.2, .clip(actor: "kai", .perch))])
        let s3: Shot = shot(cam(v(0, 1.6, 3), v(0, 1.7, 2.4), look: v(0, 1.6, 0), fov: 40),
                            [L(kai, "Lena. Wenn das hier vorbei ist… erklärst du mir die Prüfungsaufgaben?"),
                             L(.lena, "Wenn das hier vorbei ist, schreibe ich sie dir persönlich auf.")],
                            events: [at(0.1, .clip(actor: "kai", .getUp)), at(6.5, .clip(actor: "kai", .jump))])
        return CutsceneDef(id: "ch6_intro", title: "FINALE · DER BLUTTURM", stage: .cityRooftop, timeOfDay: .stormNight, music: .boss,
                           actors: [actor("kai", kai, 0, 0, yaw: 180, .perch)],
                           shots: [s1, s2, s3])
    }

    private static func ch6Prefight() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 1.2, 9), v(0, 2.5, 6), look: v(1.6, 2.0, -1), fov: 52, fovTo: 44),
                            [L(.fighter(.malrek), "Ich habe hundert Welten gekostet, Junge. Jede Welt kniet."),
                             L(.fighter(.malrek), "Deine ist nur die nächste.")],
                            events: [at(0, .music(.boss)), at(0.4, .clip(actor: "malrek", .crossArms)), at(1.0, .sound(.roar))])
        let s2: Shot = shot(overRight(fov: 36),
                            [L(kai, "Hundert Welten? Und keine hat dir beigebracht, wann man aufhören sollte?"),
                             L(.fighter(.malrek), "Mut. Wie köstlich. Dein Blut wird süß sein.")],
                            events: [at(0.2, .clip(actor: "kai", .point))])
        let s3: Shot = shot(cam(v(-3, 1.2, 3), v(-2.4, 1.3, 2.4), look: v(1.6, 2.0, 0), fov: 42),
                            [L(.fighter(.saya), "Champion. Meine Schwester ist frei. Mein Eid ist erloschen."),
                             L(.fighter(.saya), "Beende es. Für uns alle.")],
                            events: [at(0, .show(actor: "saya")), at(0.1, .effect(.shadowBurst, position: v(-3.5, 1, -2.5)))])
        let s4: Shot = shot(cam(v(0, 0.4, 3.2), v(0, 0.5, 2.6), look: v(0, 1.6, 0), fov: 50, fovTo: 42),
                            [L(.fighter(.malrek), "Dann komm. Lass das Blutturnier sein Ende finden.")], extra: 1.5,
                            events: [at(0, .hide(actor: "saya")), at(0.4, .clip(actor: "malrek", .fightIdle)),
                                     at(0.6, .clip(actor: "kai", .fightIdle)), at(1.2, .sound(.thunder)), at(1.2, .flash(.white))])
        return CutsceneDef(id: "ch6_prefight", title: nil, stage: .arena(.bloodTower), timeOfDay: .stormNight, music: .boss,
                           actors: [actor("kai", kai, -1.4, 0, yaw: 90, .idle),
                                    actor("malrek", .fighter(.malrek), 1.6, 0, yaw: -90, .crossArms),
                                    actor("saya", .fighter(.saya), -3.5, -2.5, yaw: 60, .idle)],
                           shots: [s1, s2, s3, s4])
    }

    private static func ch6Outro() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0.6, 1.0, 3), v(0.3, 1.3, 2.4), look: v(1.4, 1.4, 0), fov: 38),
                            [L(.fighter(.malrek), "Unmöglich… Ein Kind… aus einer Welt aus Beton…"),
                             L(kai, "Ein Kind mit Prüfung morgen früh. Und ich bin echt schlecht gelaunt.")],
                            events: [at(0, .clip(actor: "malrek", .kneel)), at(0.4, .clip(actor: "kai", .fightIdle))])
        let s2: Shot = shot(cam(v(0, 3, 9), v(0, 8, 16), look: v(0, 2, 0), lookTo: v(0, 25, -60), fov: 50, fovTo: 64),
                            [L(nil, "Der Riss kollabiert. Der Blutturm stürzt in sich zusammen.")], extra: 2,
                            events: [at(0.2, .effect(.explosion, position: v(1.4, 1.5, 0))), at(0.2, .hide(actor: "malrek")),
                                     at(0.25, .shake(1)), at(0.3, .sound(.explosion)), at(0.4, .flash(UIColor(red: 1, green: 0.2, blue: 0.1, alpha: 1))),
                                     at(1.5, .sound(.thunder)), at(2.0, .music(.victory))])
        let s3: Shot = shot(cam(v(-2.5, 1.5, 3), v(-2.2, 1.5, 2.4), look: v(-1.2, 1.5, 0), fov: 38),
                            [L(.fighter(.saya), "Danke, Champion. Meine Schwester und ich… wir schulden dir alles."),
                             L(kai, "Dann bring ihr bei, keine Eide mit Kaisern zu schwören.")],
                            events: [at(0, .show(actor: "saya")), at(0.3, .clip(actor: "saya", .kneel)), at(5.5, .clip(actor: "kai", .celebrate))])
        return CutsceneDef(id: "ch6_outro", title: nil, stage: .arena(.bloodTower), timeOfDay: .stormNight, music: .victory,
                           actors: [actor("kai", kai, -1.2, 0, yaw: 90, .idle),
                                    actor("malrek", .fighter(.malrek), 1.4, 0, yaw: -90, .kneel),
                                    actor("saya", .fighter(.saya), -3, -1.5, yaw: 70, .idle)],
                           shots: [s1, s2, s3])
    }

    // ---------------------------------------------------------------- Epilog

    private static func epilogue() -> CutsceneDef {
        let s1: Shot = shot(cam(v(0, 2, 10), v(0, 3, 14), look: v(0, 1.5, 0), lookTo: v(0, 10, -80), fov: 50, fovTo: 60),
                            [L(nil, "Sonnenaufgang über Neo-Haven. Zum ersten Mal seit Wochen ohne roten Himmel.")], extra: 2,
                            events: [at(0, .music(.victory))])
        let s2: Shot = shot(twoShot(),
                            [L(.lena, "Du hast es geschafft. Du hast uns alle gerettet."),
                             L(kai, "Wir. Ohne deine Formeln wäre ich jetzt ein schwarzer Fleck auf einem Dach."),
                             L(.lena, "Morgen ist übrigens deine Prüfung."),
                             L(kai, "Ach… DAS. Das macht mir echt Angst.")],
                            events: [at(0.2, .clip(actor: "kai", .talk)), at(0.3, .clip(actor: "lena", .talk)),
                                     at(9.0, .clip(actor: "kai", .celebrate))])
        let s3: Shot = shot(cam(v(0, 1.5, 4), v(0, 6, 20), look: v(0, 1.4, 0), lookTo: v(0, 3, -50), fov: 45, fovTo: 58),
                            [L(.morgrim, "Ein Turnier endet. Ein anderes beginnt.")], extra: 3,
                            events: [at(0.5, .sound(.riftHum)), at(2.5, .flash(UIColor(red: 0.8, green: 0, blue: 0, alpha: 1)))])
        return CutsceneDef(id: "epilogue", title: "EPILOG", stage: .cityRooftop, timeOfDay: .dusk, music: .victory,
                           actors: [actor("kai", kai, -0.8, 0, yaw: 150, .idle),
                                    actor("lena", .lena, 0.8, 0, yaw: -150, .idle)],
                           shots: [s1, s2, s3])
    }
}

// =====================================================================
// MARK: - World/CityBuilder.swift
// =====================================================================

// =====================================================================
//  Neo-Haven – prozedurale Stadt (Kollision, Schwing-Ankerpunkte, Verkehr)
// =====================================================================

struct BuildingBox {
    let min: SIMD3<Float>
    let max: SIMD3<Float>
    var center: SIMD3<Float> { return (min + max) * 0.5 }
    var top: Float { return max.y }
}

struct CityCollision {
    var hitGround: Bool = false
    var onRoof: Bool = false
    var hitWall: Bool = false
    var wallNormal: SIMD3<Float> = .zero
}

final class City {
    let root: SCNNode
    let size: Float
    let buildings: [BuildingBox]
    let landmarks: [LandmarkID: SIMD3<Float>]
    let collectiblePositions: [SIMD3<Float>]
    let thugSpawnPoints: [SIMD3<Float>]

    private let gridCell: Float = 50
    private var grid: [Int: [Int]] = [:]
    private let bloodTowerNode: SCNNode
    private let bloodTowerBox: BuildingBox
    private var bloodTowerActive = false
    private let traffic: CityTraffic
    private let blinkMaterial: SCNMaterial
    private let neonMaterials: [SCNMaterial]
    private var time: Float = 0

    fileprivate init(root: SCNNode, size: Float, buildings: [BuildingBox], landmarks: [LandmarkID: SIMD3<Float>],
                     collectibles: [SIMD3<Float>], thugSpawns: [SIMD3<Float>], bloodTower: SCNNode,
                     bloodTowerBox: BuildingBox, traffic: CityTraffic, blinkMaterial: SCNMaterial, neon: [SCNMaterial]) {
        self.root = root
        self.size = size
        self.buildings = buildings
        self.landmarks = landmarks
        self.collectiblePositions = collectibles
        self.thugSpawnPoints = thugSpawns
        self.bloodTowerNode = bloodTower
        self.bloodTowerBox = bloodTowerBox
        self.traffic = traffic
        self.blinkMaterial = blinkMaterial
        self.neonMaterials = neon
        for (i, b) in buildings.enumerated() {
            let x0 = Int(floor(b.min.x / gridCell)), x1 = Int(floor(b.max.x / gridCell))
            let z0 = Int(floor(b.min.z / gridCell)), z1 = Int(floor(b.max.z / gridCell))
            for gx in x0...x1 {
                for gz in z0...z1 {
                    grid[cityGridKey(gx, gz), default: []].append(i)
                }
            }
        }
        bloodTower.isHidden = true
    }

    private func cityGridKey(_ x: Int, _ z: Int) -> Int {
        return (x + 1000) * 4000 + (z + 1000)
    }

    // MARK: Abfragen

    func buildingsNear(_ p: SIMD3<Float>, radius: Float) -> [BuildingBox] {
        let x0 = Int(floor((p.x - radius) / gridCell)), x1 = Int(floor((p.x + radius) / gridCell))
        let z0 = Int(floor((p.z - radius) / gridCell)), z1 = Int(floor((p.z + radius) / gridCell))
        var seen = Set<Int>()
        var result: [BuildingBox] = []
        if x1 >= x0 && z1 >= z0 && (x1 - x0) < 80 && (z1 - z0) < 80 {
            for gx in x0...x1 {
                for gz in z0...z1 {
                    guard let list = grid[cityGridKey(gx, gz)] else { continue }
                    for i in list where !seen.contains(i) {
                        seen.insert(i)
                        result.append(buildings[i])
                    }
                }
            }
        }
        if bloodTowerActive {
            let b = bloodTowerBox
            let dx = Swift.max(b.min.x - p.x, 0, p.x - b.max.x)
            let dz = Swift.max(b.min.z - p.z, 0, p.z - b.max.z)
            if dx * dx + dz * dz <= radius * radius { result.append(b) }
        }
        return result
    }

    func surfaceHeight(at p: SIMD3<Float>) -> Float {
        var best: Float = 0
        for b in buildingsNear(p, radius: 2) {
            if p.x >= b.min.x && p.x <= b.max.x && p.z >= b.min.z && p.z <= b.max.z && b.top <= p.y + 0.5 {
                best = Swift.max(best, b.top)
            }
        }
        return best
    }

    func resolveCollision(position: inout SIMD3<Float>, velocity: inout SIMD3<Float>, radius: Float, height: Float) -> CityCollision {
        var info = CityCollision()
        for b in buildingsNear(position, radius: radius + 4) {
            if position.y >= b.top - 0.001 { continue }
            if position.y + height <= b.min.y { continue }
            let cx = clampf(position.x, b.min.x, b.max.x)
            let cz = clampf(position.z, b.min.z, b.max.z)
            let dx = position.x - cx
            let dz = position.z - cz
            let d2 = dx * dx + dz * dz
            if d2 >= radius * radius { continue }
            // Dachlandung: knapp unter der Dachkante und fallend
            let depth = b.top - position.y
            if depth < 1.6 && velocity.y <= 0.5 {
                let insideXZ = position.x > b.min.x && position.x < b.max.x && position.z > b.min.z && position.z < b.max.z
                if insideXZ || depth < 0.6 {
                    position.y = b.top
                    if velocity.y < 0 { velocity.y = 0 }
                    info.hitGround = true
                    info.onRoof = true
                    continue
                }
            }
            var n = SIMD3<Float>(0, 0, 0)
            var push: Float = 0
            if d2 > 1e-8 {
                let d = d2.squareRoot()
                n = SIMD3<Float>(dx / d, 0, dz / d)
                push = radius - d
            } else {
                // Mittelpunkt steckt in der Box: kürzesten Weg nach außen nehmen
                let options: [(Float, SIMD3<Float>)] = [
                    (position.x - b.min.x, SIMD3<Float>(-1, 0, 0)),
                    (b.max.x - position.x, SIMD3<Float>(1, 0, 0)),
                    (position.z - b.min.z, SIMD3<Float>(0, 0, -1)),
                    (b.max.z - position.z, SIMD3<Float>(0, 0, 1))
                ]
                var best = options[0]
                for o in options where o.0 < best.0 { best = o }
                n = best.1
                push = best.0 + radius
            }
            position += n * push
            let vn = simd_dot(velocity, n)
            if vn < 0 { velocity -= n * vn }
            info.hitWall = true
            info.wallNormal = n
        }
        if position.y <= 0 {
            position.y = 0
            if velocity.y < 0 { velocity.y = 0 }
            info.hitGround = true
        }
        let limit = size * 0.5 + 180
        position.x = clampf(position.x, -limit, limit)
        position.z = clampf(position.z, -limit, limit)
        return info
    }

    func findSwingAnchor(from p: SIMD3<Float>, velocity: SIMD3<Float>, aim: SIMD3<Float>) -> SIMD3<Float>? {
        let flatAim = safeNormalize(flatten(aim), fallback: SIMD3<Float>(0, 0, -1))
        let flatVel = flatten(velocity)
        let dir = safeNormalize(flatAim * 0.65 + safeNormalize(flatVel, fallback: flatAim) * 0.35, fallback: flatAim)
        let probe = p + dir * 32
        var best: SIMD3<Float>? = nil
        var bestScore: Float = -Float.greatestFiniteMagnitude
        for b in buildingsNear(probe, radius: 60) {
            let y = Swift.min(b.top, p.y + 34)
            if y < p.y + 6 { continue }
            // nächster Punkt auf dem Gebäudeumriss zur Sonde, leicht außerhalb
            let cx = clampf(probe.x, b.min.x, b.max.x)
            let cz = clampf(probe.z, b.min.z, b.max.z)
            var c = SIMD3<Float>(cx, y, cz)
            let inside = probe.x > b.min.x && probe.x < b.max.x && probe.z > b.min.z && probe.z < b.max.z
            if inside {
                // Sonde steckt im Gebäude: Kante zum Spieler hin nehmen
                c.x = clampf(p.x, b.min.x, b.max.x)
                c.z = clampf(p.z, b.min.z, b.max.z)
            }
            let outward = safeNormalize(flatten(c - b.center), fallback: -dir)
            c += outward * 0.3
            let delta = c - p
            let dist = simd_length(delta)
            if dist < 12 || dist > 75 { continue }
            let fwd = simd_dot(safeNormalize(flatten(delta), fallback: dir), dir)
            if fwd < 0.15 { continue }
            let score = fwd * 2.2 - abs(dist - 34) / 30 + (c.y - p.y) / 45
            if score > bestScore {
                bestScore = score
                best = c
            }
        }
        return best
    }

    func raycast(from: SIMD3<Float>, direction: SIMD3<Float>, maxDistance: Float) -> SIMD3<Float>? {
        let d = safeNormalize(direction)
        var tBest = maxDistance
        var hit = false
        let mid = from + d * (maxDistance * 0.5)
        for b in buildingsNear(mid, radius: maxDistance * 0.5 + 5) {
            var tmin: Float = 0
            var tmax: Float = tBest
            var ok = true
            for axis in 0..<3 {
                let o = from[axis]
                let dir = d[axis]
                if abs(dir) < 1e-6 {
                    if o < b.min[axis] || o > b.max[axis] { ok = false; break }
                } else {
                    var t1 = (b.min[axis] - o) / dir
                    var t2 = (b.max[axis] - o) / dir
                    if t1 > t2 { swap(&t1, &t2) }
                    tmin = Swift.max(tmin, t1)
                    tmax = Swift.min(tmax, t2)
                    if tmin > tmax { ok = false; break }
                }
            }
            if ok && tmin > 0.01 && tmin < tBest {
                tBest = tmin
                hit = true
            }
        }
        if d.y < -1e-4 {
            let tg = -from.y / d.y
            if tg > 0 && tg < tBest {
                tBest = tg
                hit = true
            }
        }
        return hit ? from + d * tBest : nil
    }

    func setBloodTowerActive(_ active: Bool) {
        bloodTowerActive = active
        bloodTowerNode.isHidden = !active
    }

    func update(dt: Float, cameraPosition: SIMD3<Float>) {
        time += dt
        traffic.update(dt: dt)
        let blink = fmodf(time, 1.4) < 0.18
        blinkMaterial.emission.intensity = blink ? 6 : 0.2
        for (i, m) in neonMaterials.enumerated() {
            let flick = sinf(time * (7 + Float(i) * 3.1)) + sinf(time * 13.7 + Float(i))
            m.emission.intensity = CGFloat(flick > 1.75 ? 0.4 : 2.6)
        }
    }
}

// MARK: - Bauer

enum CityBuilder {

    private static let blockPitch: Float = 100
    private static let streetWidth: Float = 20
    private static let blocks = 9

    /// Sammelt Geometrie pro Material.
    private struct CityMeshSet {
        var facades: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var roofs = MeshBuilder()
        var metal = MeshBuilder()
        var stone = MeshBuilder()
        var sidewalks = MeshBuilder()
        var glow = MeshBuilder()
        var blink = MeshBuilder()
        var neon: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var trees = MeshBuilder()
        var trunks = MeshBuilder()
        var grass = MeshBuilder()
        var crimson = MeshBuilder()
    }

    private enum CityDistrict {
        case center, plaza, park, oldTown, industry, harbor, residential
    }

    private static func district(_ i: Int, _ j: Int) -> CityDistrict {
        if i == 4 && j == 4 { return .plaza }
        if (i == 6 || i == 7) && (j == 1 || j == 2) { return .park }
        if (3...5).contains(i) && (3...5).contains(j) { return .center }
        if i <= 2 && j <= 3 { return .oldTown }
        if i >= 6 && (5...7).contains(j) { return .industry }
        if j == 8 { return .harbor }
        return .residential
    }

    /// Blockgrenzen (x0, z0, x1, z1) ohne Straßen.
    private static func blockRect(_ i: Int, _ j: Int) -> (Float, Float, Float, Float) {
        let half = Float(blocks) * blockPitch * 0.5
        let x0 = -half + Float(i) * blockPitch + streetWidth * 0.5
        let z0 = -half + Float(j) * blockPitch + streetWidth * 0.5
        return (x0, z0, x0 + blockPitch - streetWidth, z0 + blockPitch - streetWidth)
    }

    static func build(seed: UInt64, quality: QualityPreset, timeOfDay: TimeOfDay) -> City {
        var rng = SeededRandom(seed: seed)
        let root = SCNNode()
        root.name = "NeoHaven"
        let size = Float(blocks) * blockPitch
        var mesh = CityMeshSet()
        var boxes: [BuildingBox] = []
        var landmarks: [LandmarkID: SIMD3<Float>] = [:]
        var collectibles: [SIMD3<Float>] = []
        var thugSpawns: [SIMD3<Float>] = []
        var roofTops: [SIMD3<Float>] = []

        func addBuilding(_ lo: SIMD3<Float>, _ hi: SIMD3<Float>, style: Int, props: Bool) {
            guard hi.x - lo.x > 1, hi.z - lo.z > 1, hi.y - lo.y > 1 else { return }
            boxes.append(BuildingBox(min: lo, max: hi))
            let s = ((style % 4) + 4) % 4
            mesh.facades[s].addBox(min: lo, max: hi, uvScale: 1 / ProceduralTextures.facadeTileMeters)
            // Dachplatte + Brüstung
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 0.05, hi.z), uvScale: 0.12)
            let t: Float = 0.35
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 1.1, lo.z + t), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, hi.z - t), max: SIMD3<Float>(hi.x, hi.y + 1.1, hi.z), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(lo.x + t, hi.y + 1.1, hi.z), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(hi.x - t, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 1.1, hi.z), uvScale: 0.25)
            let top = SIMD3<Float>((lo.x + hi.x) * 0.5, hi.y, (lo.z + hi.z) * 0.5)
            roofTops.append(top)
            guard props else { return }
            let w = hi.x - lo.x
            let d = hi.z - lo.z
            // Klimageräte
            let acCount = rng.int(1, 4)
            for _ in 0..<acCount {
                let px = rng.float(lo.x + 2, Swift.max(lo.x + 2.1, hi.x - 4))
                let pz = rng.float(lo.z + 2, Swift.max(lo.z + 2.1, hi.z - 4))
                mesh.metal.addBox(min: SIMD3<Float>(px, hi.y, pz), max: SIMD3<Float>(px + 2.2, hi.y + 1.4, pz + 1.6), uvScale: 0.3)
            }
            // Wassertank
            if rng.chance(0.4) && w > 12 && d > 12 {
                let c = SIMD3<Float>(lo.x + w * 0.3, hi.y + 3, lo.z + d * 0.65)
                for k in 0..<4 {
                    let ox: Float = k % 2 == 0 ? -1.4 : 1.4
                    let oz: Float = k < 2 ? -1.4 : 1.4
                    mesh.metal.addBox(min: SIMD3<Float>(c.x + ox - 0.15, hi.y, c.z + oz - 0.15),
                                      max: SIMD3<Float>(c.x + ox + 0.15, hi.y + 3, c.z + oz + 0.15), uvScale: 0.3)
                }
                mesh.stone.addCylinder(center: c, radius: 2.1, height: 3.6, segments: quality == .performance ? 8 : 14, uvScale: 0.2)
                mesh.stone.addCone(center: c + SIMD3<Float>(0, 3.6, 0), radius: 2.3, height: 1.2, segments: quality == .performance ? 8 : 14)
            }
            // Antenne mit Blinklicht
            if hi.y > 60 && rng.chance(0.6) {
                let a = SIMD3<Float>(lo.x + w * 0.7, hi.y, lo.z + d * 0.3)
                let h = rng.float(6, 18)
                mesh.metal.addCylinder(center: a, radius: 0.15, height: h, segments: 6)
                mesh.blink.addBox(min: a + SIMD3<Float>(-0.35, h, -0.35), max: a + SIMD3<Float>(0.35, h + 0.7, 0.35), uvScale: 1)
            }
            // Leuchtreklame
            if rng.chance(0.25) {
                let ny = hi.y + 1.2
                let neonIndex = rng.int(0, 3)
                if rng.chance(0.5) {
                    mesh.metal.addBox(min: SIMD3<Float>(lo.x + 2, hi.y, lo.z + 0.4), max: SIMD3<Float>(lo.x + 2.3, ny + 4, lo.z + 0.7), uvScale: 0.3)
                    mesh.neon[neonIndex].addBox(min: SIMD3<Float>(lo.x + 1, ny, lo.z + 0.2), max: SIMD3<Float>(Swift.min(hi.x - 1, lo.x + 14), ny + 3.5, lo.z + 0.5), uvScale: 1)
                } else {
                    mesh.neon[neonIndex].addBox(min: SIMD3<Float>(hi.x + 0.05, hi.y * 0.55, lo.z + d * 0.4), max: SIMD3<Float>(hi.x + 0.6, hi.y * 0.55 + 9, lo.z + d * 0.4 + 2.5), uvScale: 1)
                }
            }
        }

        func addTower(x0: Float, z0: Float, x1: Float, z1: Float, height: Float, style: Int) {
            var h0: Float = 0
            var lo = SIMD3<Float>(x0, 0, z0)
            var hi = SIMD3<Float>(x1, 0, z1)
            let tiers = height > 90 ? (height > 160 ? 3 : 2) : 1
            for t in 0..<tiers {
                let frac: Float = tiers == 1 ? 1 : (t == tiers - 1 ? 1 : (t == 0 ? 0.55 : 0.82))
                let hTop = height * frac
                lo.y = h0
                hi.y = hTop
                addBuilding(lo, hi, style: style, props: t == tiers - 1)
                h0 = hTop
                let inset = Swift.min(hi.x - lo.x, hi.z - lo.z) * 0.12
                lo.x += inset; lo.z += inset; hi.x -= inset; hi.z -= inset
            }
        }

        // --- Bodenflächen -------------------------------------------------------
        let half = size * 0.5
        var ground = MeshBuilder()
        ground.addQuad(SIMD3<Float>(-half - 150, 0, -half - 150), SIMD3<Float>(-half - 150, 0, half + 10),
                       SIMD3<Float>(half + 150, 0, half + 10), SIMD3<Float>(half + 150, 0, -half - 150), uvScale: 0.125)
        var lanes = MeshBuilder()
        var lampPosts = MeshBuilder()
        var lampHeads = MeshBuilder()
        for k in 0...blocks {
            let c = -half + Float(k) * blockPitch
            var s: Float = -half
            while s < half {
                lanes.addBox(min: SIMD3<Float>(c - 0.12, 0.02, s), max: SIMD3<Float>(c + 0.12, 0.04, s + 3), uvScale: 1)
                lanes.addBox(min: SIMD3<Float>(s, 0.02, c - 0.12), max: SIMD3<Float>(s + 3, 0.04, c + 0.12), uvScale: 1)
                s += 8
            }
            var t: Float = -half + 20
            while t < half {
                for side: Float in [-1, 1] {
                    let p1 = SIMD3<Float>(c + side * 8.5, 0, t)
                    let p2 = SIMD3<Float>(t, 0, c + side * 8.5)
                    for p in [p1, p2] {
                        lampPosts.addCylinder(center: p, radius: 0.12, height: 7, segments: 6)
                        lampHeads.addBox(min: p + SIMD3<Float>(-0.4, 7, -0.4), max: p + SIMD3<Float>(0.4, 7.25, 0.4), uvScale: 1)
                    }
                }
                t += 50
            }
        }

        // --- Blöcke --------------------------------------------------------------
        for i in 0..<blocks {
            for j in 0..<blocks {
                let (x0, z0, x1, z1) = blockRect(i, j)
                let dist = district(i, j)
                if dist != .park {
                    mesh.sidewalks.addBox(min: SIMD3<Float>(x0 - 3, 0, z0 - 3), max: SIMD3<Float>(x1 + 3, 0.15, z1 + 3), uvScale: 0.25)
                }
                switch dist {
                case .plaza:
                    // Platz für den Blutturm (Sockel + Ziel am Boden)
                    mesh.stone.addBox(min: SIMD3<Float>(x0 + 10, 0.15, z0 + 10), max: SIMD3<Float>(x1 - 10, 0.6, z1 - 10), uvScale: 0.2)
                    landmarks[.bloodTower] = SIMD3<Float>((x0 + x1) * 0.5, 0.6, z1 - 6)
                case .park:
                    mesh.grass.addBox(min: SIMD3<Float>(x0 - 3, 0, z0 - 3), max: SIMD3<Float>(x1 + 3, 0.2, z1 + 3), uvScale: 0.1)
                    let treeCount = quality == .performance ? 10 : 22
                    for _ in 0..<treeCount {
                        let p = SIMD3<Float>(rng.float(x0, x1), 0.2, rng.float(z0, z1))
                        let h = rng.float(5, 10)
                        mesh.trunks.addCylinder(center: p, radius: 0.3, height: h * 0.45, segments: 6)
                        mesh.trees.addCone(center: p + SIMD3<Float>(0, h * 0.35, 0), radius: h * 0.32, height: h * 0.75, segments: 8, capBottom: true)
                    }
                default:
                    break
                }
                if dist == .plaza || dist == .park { continue }

                let isDom = (i == 1 && j == 1)
                let isFoundry = (i == 7 && j == 6)
                let isLab = (i == 5 && j == 2)
                let isHome = (i == 2 && j == 5)
                let isCrane = (i == 2 && j == 8)

                if isDom {
                    let cx = (x0 + x1) * 0.5
                    let cz = (z0 + z1) * 0.5
                    // Kirchenschiff
                    let nlo = SIMD3<Float>(cx - 14, 0, cz - 32), nhi = SIMD3<Float>(cx + 14, 30, cz + 30)
                    boxes.append(BuildingBox(min: nlo, max: nhi))
                    mesh.stone.addBox(min: nlo, max: nhi, uvScale: 0.15)
                    mesh.stone.addBox(min: SIMD3<Float>(cx - 15, 30, cz - 32), max: SIMD3<Float>(cx + 15, 31, cz + 30), uvScale: 0.15)
                    // Strebepfeiler
                    var zz = cz - 28
                    while zz < cz + 28 {
                        mesh.stone.addBox(min: SIMD3<Float>(cx - 17, 0, zz), max: SIMD3<Float>(cx - 14, 22, zz + 2), uvScale: 0.2)
                        mesh.stone.addBox(min: SIMD3<Float>(cx + 14, 0, zz), max: SIMD3<Float>(cx + 17, 22, zz + 2), uvScale: 0.2)
                        mesh.glow.addBox(min: SIMD3<Float>(cx - 14.05, 8, zz + 3), max: SIMD3<Float>(cx + 14.05, 20, zz + 5), uvScale: 1)
                        zz += 8
                    }
                    // Zwei Türme mit Spitzen
                    for side: Float in [-1, 1] {
                        let tlo = SIMD3<Float>(cx + side * 9 - 6, 0, cz + 30), thi = SIMD3<Float>(cx + side * 9 + 6, 72, cz + 42)
                        boxes.append(BuildingBox(min: tlo, max: thi))
                        mesh.stone.addBox(min: tlo, max: thi, uvScale: 0.15)
                        mesh.stone.addCone(center: SIMD3<Float>(cx + side * 9, 72, cz + 36), radius: 7, height: 34, segments: 4)
                        collectibles.append(SIMD3<Float>(cx + side * 9, 73.5, cz + 36))
                    }
                    // Rosettenfenster
                    mesh.glow.addCylinder(center: SIMD3<Float>(cx, 20, cz + 42.05), radius: 5, height: 0.2, segments: 16)
                    landmarks[.cathedral] = SIMD3<Float>(cx, 31, cz)
                    continue
                }
                if isFoundry {
                    let lo = SIMD3<Float>(x0 + 4, 0, z0 + 8), hi = SIMD3<Float>(x1 - 4, 22, z1 - 20)
                    boxes.append(BuildingBox(min: lo, max: hi))
                    mesh.metal.addBox(min: lo, max: hi, uvScale: 0.08)
                    mesh.glow.addBox(min: SIMD3<Float>(lo.x + 4, 6, hi.z + 0.02), max: SIMD3<Float>(hi.x - 4, 12, hi.z + 0.1), uvScale: 1)
                    for k in 0..<3 {
                        let c = SIMD3<Float>(lo.x + 12 + Float(k) * 22, 0, z1 - 10)
                        boxes.append(BuildingBox(min: c - SIMD3<Float>(3, 0, 3), max: c + SIMD3<Float>(3, 64, 3)))
                        mesh.stone.addCylinder(center: c, radius: 3, height: 64, segments: 12, uvScale: 0.1)
                        mesh.glow.addCylinder(center: c + SIMD3<Float>(0, 61, 0), radius: 3.1, height: 2.5, segments: 12)
                    }
                    landmarks[.foundry] = SIMD3<Float>((lo.x + hi.x) * 0.5, 22, (lo.z + hi.z) * 0.5)
                    continue
                }
                if isCrane {
                    // Lagerhalle + Hafenkran am Wasser
                    addBuilding(SIMD3<Float>(x0 + 2, 0, z0 + 2), SIMD3<Float>(x1 - 30, 14, z1 - 30), style: 2, props: true)
                    let base = SIMD3<Float>(x1 - 14, 0, z1 + 4)
                    let towerLo = base - SIMD3<Float>(4, 0, 4)
                    let towerHi = base + SIMD3<Float>(4, 52, 4)
                    boxes.append(BuildingBox(min: towerLo, max: towerHi))
                    for k in 0..<4 {
                        let ox: Float = k % 2 == 0 ? -3.6 : 3.6
                        let oz: Float = k < 2 ? -3.6 : 3.6
                        mesh.crimson.addBox(min: base + SIMD3<Float>(ox - 0.5, 0, oz - 0.5), max: base + SIMD3<Float>(ox + 0.5, 52, oz + 0.5), uvScale: 0.2)
                    }
                    mesh.crimson.addBox(min: base + SIMD3<Float>(-4, 50, -4), max: base + SIMD3<Float>(4, 53, 4), uvScale: 0.2)
                    mesh.crimson.addBox(min: base + SIMD3<Float>(-1.2, 53, -40), max: base + SIMD3<Float>(1.2, 55.5, 26), uvScale: 0.2)
                    mesh.blink.addBox(min: base + SIMD3<Float>(-0.4, 55.5, -40), max: base + SIMD3<Float>(0.4, 56.3, -39.2), uvScale: 1)
                    landmarks[.harborCrane] = base + SIMD3<Float>(0, 53, 0)
                    // Container
                    for k in 0..<10 {
                        let cxp = x0 + 4 + Float(k % 5) * 7
                        let czp = z1 - 24 + Float(k / 5) * 3.2
                        let stack = Float(1 + (k * 7) % 3)
                        let lo = SIMD3<Float>(cxp, 0, czp), hi = SIMD3<Float>(cxp + 6, 2.6 * stack, czp + 2.5)
                        boxes.append(BuildingBox(min: lo, max: hi))
                        mesh.neon[k % 3].addBox(min: lo, max: hi, uvScale: 0.3)
                    }
                    continue
                }

                // Normale Bebauung: 1–4 Grundstücke
                let w = x1 - x0
                let d = z1 - z0
                let splitX = rng.chance(0.6)
                let splitZ = rng.chance(0.6)
                let xs: [Float] = splitX ? [x0, x0 + w * rng.float(0.4, 0.6), x1] : [x0, x1]
                let zs: [Float] = splitZ ? [z0, z0 + d * rng.float(0.4, 0.6), z1] : [z0, z1]
                for a in 0..<(xs.count - 1) {
                    for b in 0..<(zs.count - 1) {
                        let lx0 = xs[a] + 1.5, lx1 = xs[a + 1] - 1.5
                        let lz0 = zs[b] + 1.5, lz1 = zs[b + 1] - 1.5
                        var height: Float
                        var style: Int
                        switch dist {
                        case .center: height = rng.float(90, 210); style = rng.chance(0.6) ? 0 : 3
                        case .oldTown: height = rng.float(16, 40); style = 1
                        case .industry: height = rng.float(12, 30); style = 2
                        case .harbor: height = rng.float(10, 22); style = 2
                        default: height = rng.float(25, 95); style = rng.int(0, 4)
                        }
                        if isLab && a == 0 && b == 0 {
                            addTower(x0: x0 + 6, z0: z0 + 6, x1: x1 - 6, z1: z1 - 6, height: 185, style: 0)
                            mesh.glow.addBox(min: SIMD3<Float>(x0 + 14, 185 * 0.82 + 2, z0 + 14), max: SIMD3<Float>(x1 - 14, 185 * 0.82 + 3, z1 - 14), uvScale: 1)
                            landmarks[.labTower] = SIMD3<Float>((x0 + x1) * 0.5, 185, (z0 + z1) * 0.5)
                            break
                        }
                        if isLab { continue }
                        if isHome && a == 0 && b == 0 {
                            height = 36
                            style = 1
                            addBuilding(SIMD3<Float>(lx0, 0, lz0), SIMD3<Float>(lx1, height, lz1), style: style, props: false)
                            landmarks[.heroApartment] = SIMD3<Float>((lx0 + lx1) * 0.5, height, (lz0 + lz1) * 0.5)
                            continue
                        }
                        addTower(x0: lx0, z0: lz0, x1: lx1, z1: lz1, height: height, style: style)
                    }
                }
            }
        }

        // U-Bahn-Eingang (Straßenniveau)
        do {
            let (x0, z0, _, _) = blockRect(3, 6)
            let p = SIMD3<Float>(x0 - 1, 0, z0 - 1)
            mesh.metal.addBox(min: p + SIMD3<Float>(-1.5, 0, -4), max: p + SIMD3<Float>(1.5, 3, 0), uvScale: 0.3)
            mesh.glow.addBox(min: p + SIMD3<Float>(-0.8, 3, -0.8), max: p + SIMD3<Float>(0.8, 4.6, 0.8), uvScale: 1)
            landmarks[.subwayEntrance] = p + SIMD3<Float>(-5, 0, 3)
        }
        // Rissherz über dem Stadtpark
        do {
            let (x0, z0, _, _) = blockRect(6, 1)
            let (_, _, x1, z1) = blockRect(7, 2)
            let c = SIMD3<Float>((x0 + x1) * 0.5, 0.2, (z0 + z1) * 0.5)
            landmarks[.riftCore] = c
            let rift = FX.makeRiftSwirl(color: UIColor(red: 0.9, green: 0.05, blue: 0.12, alpha: 1))
            rift.simdPosition = c + SIMD3<Float>(0, 70, 0)
            rift.simdScale = SIMD3<Float>(repeating: 7)
            root.addChildNode(rift)
        }

        // Fehlende Wahrzeichen absichern
        let fallback = roofTops.first ?? SIMD3<Float>(0, 0, 0)
        for id in LandmarkID.allCases where landmarks[id] == nil {
            landmarks[id] = fallback
        }

        // Sammelobjekte & Schläger-Spawns
        var tops = roofTops
        var shuffleRng = SeededRandom(seed: seed ^ 0x5EED)
        tops.shuffle(using: &shuffleRng)
        for t in tops.prefix(Swift.max(0, 40 - collectibles.count)) {
            collectibles.append(t + SIMD3<Float>(0, 1.4, 0))
        }
        for k in 0..<12 {
            let a = k % 8 + 1
            let b = (k * 5) % 8 + 1
            let x = -half + Float(a) * blockPitch
            let z = -half + Float(b) * blockPitch
            thugSpawns.append(SIMD3<Float>(x, 0, z))
        }
        for t in tops.suffix(4) { thugSpawns.append(t) }

        // --- Materialien & Nodes --------------------------------------------------
        let wet: Float = timeOfDay == .dusk ? 0.55 : 0.3
        let groundMat = Render.texturedPBR(diffuse: ProceduralTextures.asphalt(), normal: ProceduralTextures.asphaltNormal(),
                                           roughness: wet, metalness: 0.05)
        root.addChildNode(ground.buildNode(material: groundMat, name: "ground", castsShadow: false))
        root.addChildNode(lanes.buildNode(material: Render.pbr(UIColor(white: 0.8, alpha: 1), roughness: 0.5, metalness: 0,
                                                               emission: UIColor(white: 0.25, alpha: 1)), name: "lanes", castsShadow: false))
        let concreteMat = Render.texturedPBR(diffuse: ProceduralTextures.concrete(), roughness: 0.85, metalness: 0)
        root.addChildNode(mesh.sidewalks.buildNode(material: concreteMat, name: "sidewalks", castsShadow: false))
        root.addChildNode(lampPosts.buildNode(material: Render.pbr(UIColor(white: 0.15, alpha: 1), roughness: 0.4, metalness: 0.8), name: "lamps"))
        root.addChildNode(lampHeads.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.78, blue: 0.5, alpha: 1), intensity: 4), name: "lampHeads", castsShadow: false))

        for s in 0..<4 where !mesh.facades[s].isEmpty {
            let mat = Render.texturedPBR(diffuse: ProceduralTextures.facade(style: s, lit: false),
                                         roughness: s == 0 ? 0.25 : 0.7, metalness: s == 0 ? 0.5 : 0.05,
                                         emission: ProceduralTextures.facade(style: s, lit: true))
            mat.emission.intensity = timeOfDay == .dusk ? 0.9 : 1.6
            root.addChildNode(mesh.facades[s].buildNode(material: mat, name: "facade\(s)"))
        }
        root.addChildNode(mesh.roofs.buildNode(material: concreteMat, name: "roofs"))
        let metalMat = Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.45, metalness: 0.7)
        root.addChildNode(mesh.metal.buildNode(material: metalMat, name: "metal"))
        let stoneMat = Render.texturedPBR(diffuse: ProceduralTextures.brick(), roughness: 0.8, metalness: 0, tileScale: 1)
        stoneMat.diffuse.contents = UIColor(red: 0.42, green: 0.40, blue: 0.38, alpha: 1)
        root.addChildNode(mesh.stone.buildNode(material: stoneMat, name: "stone"))
        root.addChildNode(mesh.glow.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.55, blue: 0.2, alpha: 1), intensity: 3), name: "glow", castsShadow: false))
        let blinkMat = Render.emissive(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 6)
        root.addChildNode(mesh.blink.buildNode(material: blinkMat, name: "blink", castsShadow: false))
        let neonColors: [UIColor] = [UIColor(red: 1, green: 0.1, blue: 0.45, alpha: 1),
                                     UIColor(red: 0.1, green: 0.85, blue: 1, alpha: 1),
                                     UIColor(red: 1, green: 0.6, blue: 0.1, alpha: 1)]
        var neonMats: [SCNMaterial] = []
        for k in 0..<3 {
            let m = Render.emissive(neonColors[k], intensity: 2.6)
            neonMats.append(m)
            if !mesh.neon[k].isEmpty {
                root.addChildNode(mesh.neon[k].buildNode(material: m, name: "neon\(k)", castsShadow: false))
            }
        }
        root.addChildNode(mesh.grass.buildNode(material: Render.pbr(UIColor(red: 0.07, green: 0.14, blue: 0.06, alpha: 1), roughness: 0.95, metalness: 0), name: "grass", castsShadow: false))
        root.addChildNode(mesh.trees.buildNode(material: Render.pbr(UIColor(red: 0.05, green: 0.16, blue: 0.07, alpha: 1), roughness: 0.9, metalness: 0), name: "trees"))
        root.addChildNode(mesh.trunks.buildNode(material: Render.pbr(UIColor(red: 0.16, green: 0.1, blue: 0.06, alpha: 1), roughness: 0.9, metalness: 0), name: "trunks"))
        root.addChildNode(mesh.crimson.buildNode(material: Render.pbr(UIColor(red: 0.75, green: 0.12, blue: 0.08, alpha: 1), roughness: 0.5, metalness: 0.6), name: "crane"))

        // Wasser (Hafen)
        var water = MeshBuilder()
        water.addQuad(SIMD3<Float>(-half - 400, -0.6, half + 10), SIMD3<Float>(-half - 400, -0.6, half + 700),
                      SIMD3<Float>(half + 400, -0.6, half + 700), SIMD3<Float>(half + 400, -0.6, half + 10), uvScale: 0.05)
        let waterMat = Render.pbr(UIColor(red: 0.01, green: 0.03, blue: 0.05, alpha: 1), roughness: 0.06, metalness: 0.85)
        root.addChildNode(water.buildNode(material: waterMat, name: "water", castsShadow: false))

        // Ein paar echte Lichter an Wahrzeichen
        let lightSpots: [(LandmarkID, UIColor)] = [(.cathedral, UIColor(red: 1, green: 0.6, blue: 0.3, alpha: 1)),
                                                   (.foundry, UIColor(red: 1, green: 0.4, blue: 0.1, alpha: 1)),
                                                   (.subwayEntrance, UIColor(red: 0.4, green: 0.7, blue: 1, alpha: 1))]
        for (id, color) in lightSpots {
            if let p = landmarks[id] {
                let l = Render.makePointLight(color: color, intensity: 2500, range: 60)
                l.simdPosition = p + SIMD3<Float>(0, 12, 0)
                root.addChildNode(l)
            }
        }

        // Blutturm (nur im Finale sichtbar)
        let towerBase = landmarks[.bloodTower] ?? SIMD3<Float>(0, 0, 0)
        let towerCenter = SIMD3<Float>(0, 0, towerBase.z - 34)
        let tower = makeBloodTower(at: towerCenter, quality: quality)
        root.addChildNode(tower)
        let towerBox = BuildingBox(min: towerCenter + SIMD3<Float>(-16, 0, -16), max: towerCenter + SIMD3<Float>(16, 300, 16))

        let traffic = CityTraffic(size: size, blockPitch: blockPitch, quality: quality, seed: seed)
        root.addChildNode(traffic.root)

        return City(root: root, size: size, buildings: boxes, landmarks: landmarks, collectibles: collectibles,
                    thugSpawns: thugSpawns, bloodTower: tower, bloodTowerBox: towerBox, traffic: traffic,
                    blinkMaterial: blinkMat, neon: neonMats)
    }

    private static func makeBloodTower(at c: SIMD3<Float>, quality: QualityPreset) -> SCNNode {
        let node = SCNNode()
        node.name = "Blutturm"
        var body = MeshBuilder()
        var veins = MeshBuilder()
        var y: Float = 0
        var r: Float = 16
        let segs = 10
        for k in 0..<segs {
            let h: Float = 32
            body.addBox(min: c + SIMD3<Float>(-r, y, -r), max: c + SIMD3<Float>(r, y + h, r), uvScale: 0.05)
            veins.addBox(min: c + SIMD3<Float>(-r - 0.1, y + h * 0.3, -0.6), max: c + SIMD3<Float>(r + 0.1, y + h * 0.75, 0.6), uvScale: 1)
            veins.addBox(min: c + SIMD3<Float>(-0.6, y + h * 0.3, -r - 0.1), max: c + SIMD3<Float>(0.6, y + h * 0.75, r + 0.1), uvScale: 1)
            if k % 2 == 0 {
                for sx: Float in [-1, 1] {
                    body.addCone(center: c + SIMD3<Float>(sx * (r + 2), y + h * 0.6, 0), radius: 2, height: 9, segments: 5)
                }
            }
            y += h
            r *= 0.86
        }
        body.addCone(center: c + SIMD3<Float>(0, y, 0), radius: r, height: 40, segments: 6)
        node.addChildNode(body.buildNode(material: Render.pbr(UIColor(red: 0.08, green: 0.01, blue: 0.015, alpha: 1), roughness: 0.3, metalness: 0.7), name: "towerBody"))
        node.addChildNode(veins.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.04, blue: 0.08, alpha: 1), intensity: 5), name: "towerVeins", castsShadow: false))
        let rift = FX.makeRiftSwirl(color: UIColor(red: 1, green: 0.05, blue: 0.1, alpha: 1))
        rift.simdPosition = c + SIMD3<Float>(0, y + 60, 0)
        rift.simdScale = SIMD3<Float>(repeating: 9)
        node.addChildNode(rift)
        for k in 0..<3 {
            let l = Render.makePointLight(color: UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 6000, range: 160)
            l.simdPosition = c + SIMD3<Float>(0, 40 + Float(k) * 100, 26)
            node.addChildNode(l)
        }
        return node
    }

    // MARK: Kulisse für Cutscenes / Titel

    static func buildBackdrop(seed: UInt64, quality: QualityPreset, timeOfDay: TimeOfDay, clearRadius: Float) -> SCNNode {
        var rng = SeededRandom(seed: seed)
        let root = SCNNode()
        root.name = "Skyline"
        var facades: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var roofs = MeshBuilder()
        var blink = MeshBuilder()
        let count = quality == .performance ? 90 : (quality == .balanced ? 150 : 220)
        let groundY: Float = -60
        for _ in 0..<count {
            let ang = rng.float(0, Float.pi * 2)
            let dist = clearRadius + 12 + rng.float(0, 260) * rng.float(0.3, 1)
            let cx = cosf(ang) * dist
            let cz = sinf(ang) * dist
            let w = rng.float(10, 28)
            let d = rng.float(10, 28)
            let h = rng.float(30, dist > 150 ? 230 : 140)
            let lo = SIMD3<Float>(cx - w * 0.5, groundY, cz - d * 0.5)
            let hi = SIMD3<Float>(cx + w * 0.5, groundY + h, cz + d * 0.5)
            let s = rng.int(0, 4)
            facades[s].addBox(min: lo, max: hi, uvScale: 1 / ProceduralTextures.facadeTileMeters)
            roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 0.6, hi.z), uvScale: 0.1)
            if h > 120 && rng.chance(0.5) {
                blink.addBox(min: SIMD3<Float>(cx - 0.4, hi.y + 4, cz - 0.4), max: SIMD3<Float>(cx + 0.4, hi.y + 4.8, cz + 0.4), uvScale: 1)
                roofs.addBox(min: SIMD3<Float>(cx - 0.1, hi.y, cz - 0.1), max: SIMD3<Float>(cx + 0.1, hi.y + 4, cz + 0.1), uvScale: 1)
            }
        }
        for s in 0..<4 where !facades[s].isEmpty {
            let mat = Render.texturedPBR(diffuse: ProceduralTextures.facade(style: s, lit: false),
                                         roughness: s == 0 ? 0.25 : 0.7, metalness: s == 0 ? 0.5 : 0.05,
                                         emission: ProceduralTextures.facade(style: s, lit: true))
            mat.emission.intensity = timeOfDay == .dusk ? 0.9 : 1.6
            root.addChildNode(facades[s].buildNode(material: mat, name: "bgFacade\(s)", castsShadow: false))
        }
        root.addChildNode(roofs.buildNode(material: Render.pbr(UIColor(white: 0.2, alpha: 1), roughness: 0.8, metalness: 0), name: "bgRoofs", castsShadow: false))
        let blinkMat = Render.emissive(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 5)
        let pulse = CABasicAnimation(keyPath: "emission.intensity")
        pulse.fromValue = 0.2
        pulse.toValue = 6
        pulse.duration = 0.7
        pulse.autoreverses = true
        pulse.repeatCount = .infinity
        blinkMat.addAnimation(pulse, forKey: "blink")
        root.addChildNode(blink.buildNode(material: blinkMat, name: "bgBlink", castsShadow: false))
        var ground = MeshBuilder()
        let r = clearRadius + 600
        ground.addQuad(SIMD3<Float>(-r, groundY, -r), SIMD3<Float>(-r, groundY, r), SIMD3<Float>(r, groundY, r), SIMD3<Float>(r, groundY, -r), uvScale: 0.05)
        root.addChildNode(ground.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.asphalt(), roughness: 0.35, metalness: 0.05),
                                           name: "bgGround", castsShadow: false))
        return root
    }
}

// MARK: - Verkehr

final class CityTraffic {
    let root = SCNNode()

    private struct CityCar {
        let node: SCNNode
        let alongX: Bool
        let fixed: Float
        let dir: Float
        var s: Float
        let speed: Float
    }

    private var cars: [CityCar] = []
    private let half: Float

    init(size: Float, blockPitch: Float, quality: QualityPreset, seed: UInt64) {
        half = size * 0.5
        root.name = "Traffic"
        var rng = SeededRandom(seed: seed ^ 0xCA25)
        let count: Int
        switch quality {
        case .performance: count = 22
        case .balanced: count = 40
        case .ultra: count = 64
        }
        var body = MeshBuilder()
        body.addBox(min: SIMD3<Float>(-0.95, 0.3, -2.2), max: SIMD3<Float>(0.95, 1.05, 2.2), uvScale: 1)
        body.addBox(min: SIMD3<Float>(-0.85, 1.05, -1.1), max: SIMD3<Float>(0.85, 1.55, 1.0), uvScale: 1)
        var front = MeshBuilder()
        front.addBox(min: SIMD3<Float>(-0.85, 0.65, 2.2), max: SIMD3<Float>(-0.45, 0.85, 2.26), uvScale: 1)
        front.addBox(min: SIMD3<Float>(0.45, 0.65, 2.2), max: SIMD3<Float>(0.85, 0.85, 2.26), uvScale: 1)
        var rear = MeshBuilder()
        rear.addBox(min: SIMD3<Float>(-0.9, 0.7, -2.26), max: SIMD3<Float>(0.9, 0.85, -2.2), uvScale: 1)
        let paint: [UIColor] = [UIColor(white: 0.08, alpha: 1), UIColor(red: 0.5, green: 0.05, blue: 0.05, alpha: 1),
                                UIColor(white: 0.7, alpha: 1), UIColor(red: 0.05, green: 0.12, blue: 0.3, alpha: 1),
                                UIColor(red: 0.85, green: 0.65, blue: 0.1, alpha: 1)]
        let bodyGeos: [SCNGeometry] = paint.map { body.build(material: Render.pbr($0, roughness: 0.25, metalness: 0.8)) }
        let frontGeo = front.build(material: Render.emissive(UIColor(red: 1, green: 0.95, blue: 0.8, alpha: 1), intensity: 8))
        let rearGeo = rear.build(material: Render.emissive(UIColor(red: 1, green: 0.05, blue: 0.05, alpha: 1), intensity: 5))
        let streets = Int(size / blockPitch)
        for i in 0..<count {
            let alongX = i % 2 == 0
            let k = rng.int(0, streets + 1)
            let dir: Float = rng.chance(0.5) ? 1 : -1
            let fixed = -half + Float(k) * blockPitch + dir * 4
            let node = SCNNode()
            let b = SCNNode(geometry: bodyGeos[i % bodyGeos.count])
            node.addChildNode(b)
            node.addChildNode(SCNNode(geometry: frontGeo))
            node.addChildNode(SCNNode(geometry: rearGeo))
            // Fahrtrichtung: Modell schaut nach +Z
            if alongX {
                node.simdEulerAngles = SIMD3<Float>(0, dir > 0 ? Float.pi / 2 : -Float.pi / 2, 0)
            } else {
                node.simdEulerAngles = SIMD3<Float>(0, dir > 0 ? 0 : Float.pi, 0)
            }
            root.addChildNode(node)
            cars.append(CityCar(node: node, alongX: alongX, fixed: fixed, dir: dir,
                                s: rng.float(-half, half), speed: rng.float(10, 19)))
        }
    }

    func update(dt: Float) {
        for i in cars.indices {
            var c = cars[i]
            c.s += c.dir * c.speed * dt
            if c.s > half + 40 { c.s = -half - 40 }
            if c.s < -half - 40 { c.s = half + 40 }
            c.node.simdPosition = c.alongX ? SIMD3<Float>(c.s, 0, c.fixed) : SIMD3<Float>(c.fixed, 0, c.s)
            cars[i] = c
        }
    }
}

// =====================================================================
// MARK: - World/OpenWorldController.swift
// =====================================================================

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

// =====================================================================
// MARK: - World/Thugs.swift
// =====================================================================

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

// =====================================================================
// MARK: - World/WorldCamera.swift
// =====================================================================

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

// =====================================================================
// MARK: - Kombat/ArenaBuilder.swift
// =====================================================================

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

// =====================================================================
// MARK: - Kombat/Executions.swift
// =====================================================================

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

// =====================================================================
// MARK: - Kombat/Fighter.swift
// =====================================================================

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

// =====================================================================
// MARK: - Kombat/KombatAI.swift
// =====================================================================

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

// =====================================================================
// MARK: - Kombat/KombatController.swift
// =====================================================================

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

// =====================================================================
// MARK: - Cutscene/CutsceneController.swift
// =====================================================================

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

// =====================================================================
// MARK: - UI/GameHUD.swift
// =====================================================================

// =====================================================================
//  Theme, Touch-Steuerung und Spiel-HUDs (Kombat, offene Welt, Cutscene)
// =====================================================================

enum Theme {
    static let blood = Color(red: 0.72, green: 0.03, blue: 0.09)
    static let bloodBright = Color(red: 1.0, green: 0.16, blue: 0.22)
    static let gold = Color(red: 1.0, green: 0.8, blue: 0.36)
    static let steel = Color(white: 0.78)
    static let ink = Color(red: 0.03, green: 0.02, blue: 0.035)
    static let violet = Color(red: 0.62, green: 0.32, blue: 1.0)
    static let cyan = Color(red: 0.3, green: 0.85, blue: 1.0)

    static func title(_ size: CGFloat) -> Font { return .system(size: size, weight: .black, design: .default) }
    static func body(_ size: CGFloat) -> Font { return .system(size: size, weight: .semibold, design: .default) }
    static func mono(_ size: CGFloat) -> Font { return .system(size: size, weight: .heavy, design: .monospaced) }
}

struct GlassPanelStyle: ViewModifier {
    var corner: CGFloat = 14
    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: corner, style: .continuous).stroke(Theme.blood.opacity(0.55), lineWidth: 1))
    }
}

extension View {
    func glassPanel(corner: CGFloat = 14) -> some View {
        return modifier(GlassPanelStyle(corner: corner))
    }

    func glowText(_ color: Color, radius: CGFloat = 8) -> some View {
        return shadow(color: color.opacity(0.9), radius: radius).shadow(color: .black.opacity(0.8), radius: 2, x: 0, y: 2)
    }
}

// MARK: - Touch-Steuerung

struct VirtualJoystick: View {
    let input: InputState
    var radius: CGFloat = 60

    @State private var origin: CGPoint? = nil
    @State private var knob: CGSize = .zero

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.clear.contentShape(Rectangle())
                if let o = origin {
                    Circle()
                        .fill(Color.white.opacity(0.08))
                        .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 2))
                        .frame(width: radius * 2, height: radius * 2)
                        .position(o)
                    Circle()
                        .fill(Theme.blood.opacity(0.75))
                        .overlay(Circle().stroke(Color.white.opacity(0.7), lineWidth: 2))
                        .frame(width: radius * 0.9, height: radius * 0.9)
                        .position(x: o.x + knob.width, y: o.y + knob.height)
                } else {
                    Circle()
                        .stroke(Color.white.opacity(0.18), style: StrokeStyle(lineWidth: 2, dash: [6, 6]))
                        .frame(width: radius * 2, height: radius * 2)
                        .position(x: radius + 40, y: geo.size.height - radius - 40)
                }
            }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { v in
                        let o = origin ?? v.startLocation
                        if origin == nil { origin = o }
                        var dx = v.location.x - o.x
                        var dy = v.location.y - o.y
                        let len = (dx * dx + dy * dy).squareRoot()
                        if len > radius {
                            dx = dx / len * radius
                            dy = dy / len * radius
                        }
                        knob = CGSize(width: dx, height: dy)
                        var mx = Float(dx / radius)
                        var my = Float(-dy / radius)
                        if abs(mx) < 0.12 { mx = 0 }
                        if abs(my) < 0.12 { my = 0 }
                        input.move = SIMD2<Float>(mx, my)
                    }
                    .onEnded { _ in
                        origin = nil
                        knob = .zero
                        input.move = .zero
                    }
            )
        }
    }
}

struct ActionButton: View {
    let title: String
    let icon: String
    let button: GameButton
    let input: InputState
    var size: CGFloat = 64
    var color: Color = Theme.blood
    var enabled: Bool = true

    @State private var pressed = false

    var body: some View {
        ZStack {
            Circle()
                .fill(color.opacity(enabled ? (pressed ? 0.9 : 0.5) : 0.15))
            Circle()
                .stroke(Color.white.opacity(enabled ? 0.75 : 0.25), lineWidth: 2)
            VStack(spacing: 1) {
                Image(systemName: icon)
                    .font(.system(size: size * 0.3, weight: .bold))
                Text(title)
                    .font(.system(size: Swift.max(8, size * 0.14), weight: .heavy))
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            }
            .foregroundColor(.white.opacity(enabled ? 1 : 0.4))
            .padding(4)
        }
        .frame(width: size, height: size)
        .scaleEffect(pressed ? 0.9 : 1)
        .animation(.easeOut(duration: 0.08), value: pressed)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    guard enabled, !pressed else { return }
                    pressed = true
                    input.press(button)
                    Haptics.light()
                }
                .onEnded { _ in
                    if pressed { input.release(button) }
                    pressed = false
                }
        )
    }
}

struct PauseButton: View {
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: "pause.fill")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Color.black.opacity(0.45)))
                .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 1))
        }
    }
}

struct LetterboxBars: View {
    let visible: Bool
    var body: some View {
        GeometryReader { geo in
            let h = visible ? geo.size.height * 0.11 : 0
            VStack(spacing: 0) {
                Rectangle().fill(Color.black).frame(height: h)
                Spacer(minLength: 0)
                Rectangle().fill(Color.black).frame(height: h)
            }
            .animation(.easeInOut(duration: 0.45), value: visible)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

// MARK: - Kombat-HUD

struct KombatHUDView: View {
    @ObservedObject var hud: KombatHUD
    let input: InputState
    let onPause: () -> Void

    init(hud: KombatHUD, input: InputState, onPause: @escaping () -> Void) {
        self.hud = hud
        self.input = input
        self.onPause = onPause
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.4, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                LetterboxBars(visible: hud.cinematic)
                if !hud.cinematic {
                    topBar(scale: s)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .frame(maxHeight: .infinity, alignment: .top)
                }
                bannerView(scale: s)
                comboView(scale: s)
                if hud.controlsEnabled && !hud.cinematic && !hud.matchOver {
                    controls(scale: s, size: geo.size)
                }
                if hud.showExecutePrompt {
                    executeButton(scale: s)
                }
                Color(uiColor: hud.flashColor)
                    .opacity(hud.flashOpacity)
                    .ignoresSafeArea()
                    .allowsHitTesting(false)
            }
        }
    }

    private func topBar(scale s: CGFloat) -> some View {
        HStack(alignment: .top, spacing: 10 * s) {
            fighterBar(name: hud.p1Name, health: hud.p1Health, lag: hud.p1HealthLag, meter: hud.p1Meter,
                       rounds: hud.p1Rounds, mirrored: false, scale: s)
            VStack(spacing: 4) {
                Text("\(hud.timer)")
                    .font(Theme.mono(30 * s))
                    .foregroundColor(hud.timer <= 10 ? Theme.bloodBright : .white)
                    .glowText(Theme.blood)
                    .frame(width: 70 * s, height: 50 * s)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.6)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.gold.opacity(0.7), lineWidth: 1.5))
                PauseButton(action: onPause)
                    .scaleEffect(0.85)
            }
            fighterBar(name: hud.p2Name, health: hud.p2Health, lag: hud.p2HealthLag, meter: hud.p2Meter,
                       rounds: hud.p2Rounds, mirrored: true, scale: s)
        }
    }

    private func fighterBar(name: String, health: Float, lag: Float, meter: Float, rounds: Int, mirrored: Bool, scale s: CGFloat) -> some View {
        VStack(alignment: mirrored ? .trailing : .leading, spacing: 4 * s) {
            GeometryReader { g in
                let w = g.size.width
                ZStack(alignment: mirrored ? .trailing : .leading) {
                    Rectangle().fill(Color.black.opacity(0.65))
                    Rectangle().fill(Theme.bloodBright.opacity(0.85))
                        .frame(width: w * CGFloat(lag))
                    Rectangle()
                        .fill(LinearGradient(colors: [Theme.gold, Color(red: 0.95, green: 0.45, blue: 0.1)],
                                             startPoint: .top, endPoint: .bottom))
                        .frame(width: w * CGFloat(health))
                }
                .overlay(Rectangle().stroke(Color.white.opacity(0.6), lineWidth: 1.5))
                .animation(.linear(duration: 0.08), value: health)
            }
            .frame(height: 22 * s)
            HStack(spacing: 6) {
                if mirrored { roundDots(rounds, scale: s) }
                Text(name)
                    .font(Theme.title(15 * s))
                    .foregroundColor(.white)
                    .glowText(Theme.blood, radius: 4)
                if !mirrored { roundDots(rounds, scale: s) }
            }
            GeometryReader { g in
                ZStack(alignment: mirrored ? .trailing : .leading) {
                    Capsule().fill(Color.black.opacity(0.55))
                    Capsule()
                        .fill(meter >= 1 ? Theme.violet : Theme.cyan.opacity(0.8))
                        .frame(width: g.size.width * CGFloat(Swift.min(1, meter)))
                }
            }
            .frame(width: 180 * s, height: 7 * s)
            if meter >= 1 && !mirrored {
                Text("BRUTAL BEREIT")
                    .font(Theme.title(10 * s))
                    .foregroundColor(Theme.violet)
                    .glowText(Theme.violet, radius: 6)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func roundDots(_ won: Int, scale s: CGFloat) -> some View {
        HStack(spacing: 4) {
            ForEach(0..<Swift.max(1, hud.roundsToWin), id: \.self) { i in
                Image(systemName: i < won ? "drop.fill" : "drop")
                    .font(.system(size: 12 * s, weight: .bold))
                    .foregroundColor(i < won ? Theme.bloodBright : Color.white.opacity(0.5))
            }
        }
    }

    @ViewBuilder
    private func bannerView(scale s: CGFloat) -> some View {
        if let b = hud.banner {
            Text(b)
                .font(Theme.title(bannerSize(hud.bannerStyle) * s))
                .foregroundColor(bannerColor(hud.bannerStyle))
                .multilineTextAlignment(.center)
                .glowText(hud.bannerStyle == .fight || hud.bannerStyle == .round ? Theme.gold : Theme.blood, radius: 14)
                .minimumScaleFactor(0.4)
                .lineLimit(2)
                .padding(.horizontal, 30)
                .transition(.scale(scale: 2.2).combined(with: .opacity))
                .id(b)
                .allowsHitTesting(false)
        }
    }

    private func bannerSize(_ style: BannerStyle) -> CGFloat {
        switch style {
        case .round, .fight: return 72
        case .finish, .execution: return 78
        case .brutal: return 54
        case .victory, .defeat: return 60
        case .info: return 34
        }
    }

    private func bannerColor(_ style: BannerStyle) -> Color {
        switch style {
        case .round, .fight, .victory: return Theme.gold
        case .finish, .execution, .defeat: return Theme.bloodBright
        case .brutal: return Theme.violet
        case .info: return .white
        }
    }

    @ViewBuilder
    private func comboView(scale s: CGFloat) -> some View {
        if let c = hud.comboText {
            Text(c)
                .font(Theme.title(26 * s))
                .foregroundColor(.white)
                .glowText(Theme.bloodBright, radius: 10)
                .rotationEffect(.degrees(-6))
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .padding(.leading, 30)
                .padding(.bottom, 80)
                .transition(.move(edge: .leading).combined(with: .opacity))
                .id(c)
                .allowsHitTesting(false)
        }
    }

    private func controls(scale s: CGFloat, size: CGSize) -> some View {
        let b = 66 * s
        return ZStack {
            HStack(spacing: 0) {
                VirtualJoystick(input: input, radius: 58 * s)
                    .frame(width: size.width * 0.42)
                Spacer()
            }
            VStack(spacing: 10 * s) {
                HStack(spacing: 10 * s) {
                    ActionButton(title: hud.special1Name, icon: "sparkles", button: .special1, input: input,
                                 size: b * 0.85, color: Theme.violet, enabled: hud.special1Ready)
                    ActionButton(title: hud.special2Name, icon: "bolt.fill", button: .special2, input: input,
                                 size: b * 0.85, color: Theme.violet, enabled: hud.special2Ready)
                    if hud.canBrutal {
                        ActionButton(title: "BRUTAL", icon: "flame.fill", button: .brutal, input: input,
                                     size: b * 0.95, color: Theme.bloodBright)
                    }
                }
                HStack(spacing: 10 * s) {
                    ActionButton(title: "BLOCK", icon: "shield.fill", button: .block, input: input, size: b, color: Color.gray)
                    ActionButton(title: "SCHLAG", icon: "hand.raised.fill", button: .punch, input: input, size: b * 1.1)
                    ActionButton(title: "TRITT", icon: "figure.kickboxing", button: .kick, input: input, size: b * 1.1)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            .padding(.trailing, 20)
            .padding(.bottom, 18)
        }
    }

    private func executeButton(scale s: CGFloat) -> some View {
        VStack {
            Spacer()
            ZStack {
                Circle()
                    .trim(from: 0, to: CGFloat(Swift.max(0, Swift.min(1, hud.executeTimeLeft / 6))))
                    .stroke(Theme.bloodBright, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 150 * s, height: 150 * s)
                ActionButton(title: "EXEKUTION", icon: "drop.triangle.fill", button: .execute, input: input,
                             size: 128 * s, color: Theme.blood)
            }
            .padding(.bottom, 30)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.trailing, 40)
    }
}

// MARK: - Welt-HUD

struct WorldHUDView: View {
    @ObservedObject var hud: WorldHUD
    let input: InputState
    let onPause: () -> Void

    init(hud: WorldHUD, input: InputState, onPause: @escaping () -> Void) {
        self.hud = hud
        self.input = input
        self.onPause = onPause
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.35, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                HStack(spacing: 0) {
                    VirtualJoystick(input: input, radius: 58 * s)
                        .frame(width: geo.size.width * 0.42)
                    Spacer()
                }
                VStack(alignment: .leading, spacing: 8) {
                    objectivePanel(scale: s)
                    healthBar(scale: s)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(.leading, 18)
                .padding(.top, 10)
                minimap(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                    .padding(.trailing, 18)
                    .padding(.top, 10)
                centerInfo(scale: s)
                speedReadout(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                    .padding(.leading, 24)
                    .padding(.bottom, 170 * s)
                buttons(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(.trailing, 20)
                    .padding(.bottom, 18)
                PauseButton(action: onPause)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    .padding(.top, 10)
            }
        }
    }

    private func objectivePanel(scale s: CGFloat) -> some View {
        HStack(spacing: 10) {
            if hud.objectiveDistance != nil {
                Image(systemName: "location.north.fill")
                    .font(.system(size: 22 * s, weight: .bold))
                    .foregroundColor(Theme.bloodBright)
                    .rotationEffect(.radians(Double(hud.objectiveArrowAngle)))
                    .glowText(Theme.blood, radius: 6)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(hud.objective)
                    .font(Theme.body(13 * s))
                    .foregroundColor(.white)
                    .lineLimit(2)
                if let d = hud.objectiveDistance {
                    Text("\(Int(d)) m")
                        .font(Theme.mono(12 * s))
                        .foregroundColor(Theme.gold)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: 330 * s, alignment: .leading)
        .glassPanel()
    }

    private func healthBar(scale s: CGFloat) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "heart.fill").foregroundColor(Theme.bloodBright)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.black.opacity(0.6))
                    Capsule().fill(Theme.bloodBright).frame(width: g.size.width * CGFloat(hud.health))
                }
            }
            .frame(width: 150 * s, height: 9 * s)
            Image(systemName: "diamond.fill").foregroundColor(Theme.bloodBright).font(.system(size: 12 * s))
            Text("\(hud.collectibles)/\(hud.collectiblesTotal)")
                .font(Theme.mono(12 * s))
                .foregroundColor(.white)
        }
    }

    private func minimap(scale s: CGFloat) -> some View {
        let size = 120 * s
        return ZStack {
            Circle().fill(Color.black.opacity(0.55))
            Circle().stroke(Theme.blood.opacity(0.8), lineWidth: 2)
            if let o = hud.minimapObjective {
                Circle()
                    .fill(Theme.bloodBright)
                    .frame(width: 10, height: 10)
                    .position(x: CGFloat(o.x) * size, y: CGFloat(o.y) * size)
                    .glowText(Theme.bloodBright, radius: 5)
            }
            Image(systemName: "location.north.fill")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(Theme.gold)
                .rotationEffect(.radians(Double(-hud.minimapHeroHeading) + Double.pi))
                .position(x: CGFloat(hud.minimapHero.x) * size, y: CGFloat(hud.minimapHero.y) * size)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }

    @ViewBuilder
    private func centerInfo(scale s: CGFloat) -> some View {
        VStack(spacing: 10) {
            if let t = hud.toast {
                Text(t)
                    .font(Theme.title(20 * s))
                    .foregroundColor(.white)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 8)
                    .glassPanel()
                    .transition(.opacity)
            }
            if hud.combo >= 2 {
                Text("\(hud.combo)× KOMBO")
                    .font(Theme.title(24 * s))
                    .foregroundColor(Theme.gold)
                    .glowText(Theme.blood)
            }
            Spacer()
            if let p = hud.interactPrompt {
                Button {
                    input.press(.interact)
                    input.release(.interact)
                    Haptics.medium()
                } label: {
                    Text(p)
                        .font(Theme.title(20 * s))
                        .foregroundColor(.white)
                        .padding(.horizontal, 26)
                        .padding(.vertical, 12)
                        .background(Capsule().fill(Theme.blood))
                        .overlay(Capsule().stroke(Color.white.opacity(0.8), lineWidth: 2))
                        .glowText(Theme.bloodBright, radius: 10)
                }
                .padding(.bottom, 40)
            }
        }
        .padding(.top, 70)
        .animation(.easeInOut(duration: 0.25), value: hud.toast)
    }

    private func speedReadout(scale s: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(hud.speedKmh)")
                .font(Theme.mono(30 * s))
                .foregroundColor(hud.speedKmh > 90 ? Theme.gold : .white)
                .glowText(hud.speedKmh > 90 ? Theme.bloodBright : .clear, radius: 8)
            Text("KM/H")
                .font(Theme.title(10 * s))
                .foregroundColor(.white.opacity(0.7))
        }
        .allowsHitTesting(false)
    }

    private func buttons(scale s: CGFloat) -> some View {
        let b = 64 * s
        return VStack(alignment: .trailing, spacing: 10 * s) {
            HStack(spacing: 10 * s) {
                ActionButton(title: "ZIP", icon: "arrow.up.right", button: .zip, input: input, size: b * 0.85, color: Theme.violet)
                ActionButton(title: "ANGRIFF", icon: "hand.raised.fill", button: .attack, input: input, size: b, color: Color.gray)
            }
            HStack(spacing: 10 * s) {
                ActionButton(title: "SPRUNG", icon: "arrow.up", button: .jump, input: input, size: b)
                ActionButton(title: "NETZ", icon: "scribble.variable", button: .web, input: input, size: b * 1.35,
                             color: hud.isSwinging ? Theme.bloodBright : Theme.blood)
            }
        }
    }
}

// MARK: - Cutscene-Overlay

struct CutsceneOverlayView: View {
    @ObservedObject var hud: CutsceneHUD
    let onSkip: () -> Void

    init(hud: CutsceneHUD, onSkip: @escaping () -> Void) {
        self.hud = hud
        self.onSkip = onSkip
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.4, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                LetterboxBars(visible: hud.letterbox)
                VStack(spacing: 6) {
                    Spacer()
                    if let line = hud.line {
                        VStack(spacing: 4) {
                            if let sp = hud.speaker {
                                Text(sp)
                                    .font(Theme.title(14 * s))
                                    .foregroundColor(Theme.bloodBright)
                                    .tracking(2)
                            }
                            Text(line)
                                .font(Theme.body(19 * s))
                                .foregroundColor(.white)
                                .multilineTextAlignment(.center)
                                .shadow(color: .black, radius: 4, x: 0, y: 2)
                        }
                        .padding(.horizontal, 60)
                        .id(line)
                        .transition(.opacity)
                    }
                }
                .padding(.bottom, geo.size.height * 0.035)
                .animation(.easeInOut(duration: 0.25), value: hud.line)
                if let t = hud.title {
                    Text(t)
                        .font(Theme.title(40 * s))
                        .tracking(8)
                        .foregroundColor(.white)
                        .glowText(Theme.blood, radius: 16)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                        .transition(.opacity)
                }
                Color.black.opacity(hud.fadeOpacity).ignoresSafeArea().allowsHitTesting(false)
                Color(uiColor: hud.flashColor).opacity(hud.flashOpacity).ignoresSafeArea().allowsHitTesting(false)
                Button(action: onSkip) {
                    HStack(spacing: 6) {
                        Text("Überspringen")
                        Image(systemName: "forward.end.fill")
                    }
                    .font(Theme.body(13))
                    .foregroundColor(.white.opacity(0.8))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(Capsule().fill(Color.black.opacity(0.4)))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                .padding(.top, 14)
                .padding(.trailing, 18)
            }
            .animation(.easeInOut(duration: 0.6), value: hud.title)
        }
    }
}

// =====================================================================
// MARK: - UI/MenuViews.swift
// =====================================================================

// =====================================================================
//  Menüs: Titel, Kapitel, Kämpferauswahl, Einstellungen, Ergebnis,
//  Credits, Pause, Ladevorhang
// =====================================================================

struct MenuButton: View {
    let title: String
    var subtitle: String? = nil
    var icon: String = "chevron.right"
    var prominent: Bool = false
    let action: () -> Void

    var body: some View {
        Button {
            AudioDirector.shared.play(.uiConfirm)
            Haptics.light()
            action()
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(Theme.title(prominent ? 24 : 19))
                        .foregroundColor(.white)
                    if let s = subtitle {
                        Text(s)
                            .font(Theme.body(12))
                            .foregroundColor(.white.opacity(0.65))
                    }
                }
                Spacer()
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundColor(Theme.bloodBright)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, prominent ? 14 : 11)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(prominent ? AnyShapeStyle(LinearGradient(colors: [Theme.blood, Color(red: 0.35, green: 0, blue: 0.04)],
                                                                    startPoint: .leading, endPoint: .trailing))
                                    : AnyShapeStyle(Color.black.opacity(0.45)))
            )
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.blood.opacity(0.7), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

struct BackButton: View {
    let action: () -> Void
    var body: some View {
        Button {
            AudioDirector.shared.play(.uiBack)
            action()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "chevron.left")
                Text("Zurück")
            }
            .font(Theme.body(15))
            .foregroundColor(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Capsule().fill(Color.black.opacity(0.5)))
            .overlay(Capsule().stroke(Color.white.opacity(0.3), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Titel

struct TitleMenuView: View {
    @ObservedObject var game: GameManager
    @State private var glow = false

    var body: some View {
        GeometryReader { geo in
            HStack(alignment: .center, spacing: 30) {
                logo(width: geo.size.width)
                    .frame(maxWidth: .infinity, alignment: .leading)
                menu
                    .frame(width: Swift.min(360, geo.size.width * 0.38))
            }
            .padding(.horizontal, 40)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(LinearGradient(colors: [Color.black.opacity(0.75), Color.black.opacity(0.1), Color.black.opacity(0.6)],
                                       startPoint: .leading, endPoint: .trailing).ignoresSafeArea())
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { glow = true }
        }
    }

    private func logo(width: CGFloat) -> some View {
        let size = Swift.min(86, width * 0.08)
        return VStack(alignment: .leading, spacing: 4) {
            Text("SILKSTRIKE")
                .font(Theme.title(size))
                .italic()
                .foregroundColor(.white)
                .shadow(color: Theme.bloodBright.opacity(glow ? 0.95 : 0.4), radius: glow ? 24 : 10)
                .minimumScaleFactor(0.5)
                .lineLimit(1)
            Text("B L U T T U R N I E R")
                .font(Theme.title(size * 0.3))
                .foregroundColor(Theme.bloodBright)
                .glowText(Theme.blood, radius: 10)
            Text("Neo-Haven braucht einen Champion.")
                .font(Theme.body(14))
                .foregroundColor(.white.opacity(0.7))
                .padding(.top, 10)
        }
    }

    private var menu: some View {
        VStack(spacing: 10) {
            if game.storyProgress > 0 && !game.storyCompleted, let ch = game.chapter(at: game.storyProgress) {
                MenuButton(title: "WEITERSPIELEN", subtitle: "\(GameManager.chapterLabel(ch)) · \(ch.title)", icon: "play.fill", prominent: true) {
                    game.continueStoryFromProgress()
                }
            }
            MenuButton(title: "STORY", subtitle: "Das Blutturnier", icon: "book.fill", prominent: game.storyProgress == 0) {
                game.openStory()
            }
            MenuButton(title: "KAMPF", subtitle: "1 gegen 1 gegen die KI", icon: "figure.martial.arts") {
                game.openVersus()
            }
            MenuButton(title: "FREIES SCHWINGEN", subtitle: "Ganz Neo-Haven erkunden", icon: "building.2.fill") {
                game.startFreeRoam()
            }
            MenuButton(title: "EINSTELLUNGEN", icon: "gearshape.fill") {
                game.openSettings()
            }
            MenuButton(title: "CREDITS", icon: "star.fill") {
                game.openCredits()
            }
        }
    }
}

// MARK: - Kapitel

struct ChapterSelectView: View {
    @ObservedObject var game: GameManager

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                BackButton { game.backToTitle() }
                Spacer()
                Text("STORY")
                    .font(Theme.title(28))
                    .foregroundColor(.white)
                    .glowText(Theme.blood)
                Spacer()
                Color.clear.frame(width: 90, height: 10)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    ForEach(Array(game.chapters.enumerated()), id: \.offset) { pair in
                        chapterCard(index: pair.offset, ch: pair.element)
                    }
                }
                .padding(.horizontal, 4)
                .padding(.vertical, 6)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.black.opacity(0.55).ignoresSafeArea())
    }

    private func chapterCard(index: Int, ch: ChapterDef) -> some View {
        let unlocked = game.isChapterUnlocked(index)
        let opp = Roster.def(ch.opponent)
        return Button {
            guard unlocked else {
                AudioDirector.shared.play(.uiBack)
                return
            }
            AudioDirector.shared.play(.uiConfirm)
            Haptics.medium()
            game.startChapter(index)
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text(GameManager.chapterLabel(ch))
                    .font(Theme.title(13))
                    .foregroundColor(Theme.bloodBright)
                Text(ch.title.uppercased())
                    .font(Theme.title(22))
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .minimumScaleFactor(0.6)
                Text(ch.subtitle)
                    .font(Theme.body(13))
                    .foregroundColor(.white.opacity(0.75))
                    .lineLimit(3)
                Spacer()
                HStack {
                    Circle().fill(Color(uiColor: Roster.signatureColor(ch.opponent))).frame(width: 12, height: 12)
                    Text("Gegner: \(opp.name)")
                        .font(Theme.body(12))
                        .foregroundColor(.white.opacity(0.85))
                }
                Text(ch.arena.displayName)
                    .font(Theme.body(11))
                    .foregroundColor(.white.opacity(0.55))
            }
            .padding(16)
            .frame(width: 220, height: 250, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(LinearGradient(colors: [Color(uiColor: Roster.signatureColor(ch.opponent)).opacity(0.45), Color.black.opacity(0.75)],
                                         startPoint: .top, endPoint: .bottom))
            )
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(unlocked ? Theme.blood : Color.gray.opacity(0.4), lineWidth: 1.5))
            .overlay(
                Group {
                    if !unlocked {
                        ZStack {
                            RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.black.opacity(0.65))
                            Image(systemName: "lock.fill").font(.system(size: 34)).foregroundColor(.white.opacity(0.7))
                        }
                    }
                }
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Kämpferauswahl

struct FighterSelectView: View {
    @ObservedObject var game: GameManager

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                BackButton { game.backToTitle() }
                Spacer()
                Text("KÄMPFERWAHL")
                    .font(Theme.title(26))
                    .foregroundColor(.white)
                    .glowText(Theme.blood)
                Spacer()
                Color.clear.frame(width: 90, height: 10)
            }
            HStack(alignment: .top, spacing: 18) {
                column(title: "DU", selection: game.versusPlayer) { id in game.versusPlayer = id }
                versusInfo
                column(title: "GEGNER", selection: game.versusCPU) { id in game.versusCPU = id }
            }
            optionsRow
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.black.opacity(0.6).ignoresSafeArea())
    }

    private func column(title: String, selection: FighterID, onPick: @escaping (FighterID) -> Void) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(Theme.title(14)).foregroundColor(Theme.bloodBright)
            ScrollView(showsIndicators: false) {
                VStack(spacing: 6) {
                    ForEach(FighterID.allCases) { id in
                        fighterRow(id, selected: id == selection) {
                            AudioDirector.shared.play(.uiSelect)
                            Haptics.light()
                            onPick(id)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func fighterRow(_ id: FighterID, selected: Bool, action: @escaping () -> Void) -> some View {
        let d = Roster.def(id)
        return Button(action: action) {
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(uiColor: Roster.signatureColor(id)))
                    .frame(width: 8, height: 34)
                VStack(alignment: .leading, spacing: 1) {
                    Text(d.name.uppercased()).font(Theme.title(15)).foregroundColor(.white)
                    Text(d.title).font(Theme.body(10)).foregroundColor(.white.opacity(0.65)).lineLimit(1)
                }
                Spacer()
                if selected { Image(systemName: "checkmark.circle.fill").foregroundColor(Theme.gold) }
            }
            .padding(8)
            .background(RoundedRectangle(cornerRadius: 10).fill(selected ? Theme.blood.opacity(0.55) : Color.black.opacity(0.4)))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? Theme.gold : Color.white.opacity(0.15), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var versusInfo: some View {
        let p = Roster.def(game.versusPlayer)
        let c = Roster.def(game.versusCPU)
        return VStack(spacing: 10) {
            Text(p.name.uppercased()).font(Theme.title(22)).foregroundColor(.white)
            Text("VS").font(Theme.title(40)).foregroundColor(Theme.bloodBright).glowText(Theme.blood, radius: 12)
            Text(c.name.uppercased()).font(Theme.title(22)).foregroundColor(.white)
            Text(c.bio)
                .font(Theme.body(11))
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
                .lineLimit(5)
            Text("Exekution: \(p.execution.name)")
                .font(Theme.body(11))
                .foregroundColor(Theme.gold)
            MenuButton(title: "KÄMPFT!", icon: "flame.fill", prominent: true) {
                game.startVersusMatch()
            }
        }
        .frame(maxWidth: 260)
        .padding(.top, 20)
    }

    private var optionsRow: some View {
        HStack(spacing: 12) {
            Picker("Arena", selection: $game.versusArena) {
                ForEach(ArenaID.allCases) { a in Text(a.displayName).tag(a) }
            }
            .pickerStyle(.menu)
            .tint(.white)
            .glassPanel(corner: 10)
            Picker("Schwierigkeit", selection: $game.versusDifficulty) {
                ForEach(Difficulty.allCases) { d in Text(d.displayName).tag(d) }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 320)
            if game.darkSuitUnlocked && game.versusPlayer == .silkstrike {
                Toggle("Schwarzseide", isOn: $game.versusDarkSuit)
                    .toggleStyle(.switch)
                    .tint(Theme.violet)
                    .foregroundColor(.white)
                    .frame(maxWidth: 190)
            }
            Button {
                game.randomizeVersusCPU()
                AudioDirector.shared.play(.uiSelect)
            } label: {
                Image(systemName: "dice.fill").font(.system(size: 20)).foregroundColor(.white)
                    .padding(8).background(Circle().fill(Color.black.opacity(0.5)))
            }
        }
    }
}

// MARK: - Einstellungen

struct SettingsPanel: View {
    @ObservedObject var game: GameManager

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 16) {
                section("GRAFIK") {
                    Picker("Grafikstufe", selection: $game.settings.quality) {
                        ForEach(QualityPreset.allCases) { q in Text(q.displayName).tag(q) }
                    }
                    .pickerStyle(.segmented)
                    Text("Ultra rendert in der vollen Auflösung des Displays mit HDR, Bloom, Schatten und Tiefenschärfe. „Leistung“ zielt auf 120 FPS. Die neue Stufe gilt ab der nächsten Szene.")
                        .font(Theme.body(11))
                        .foregroundColor(.white.opacity(0.6))
                    Toggle("FPS anzeigen", isOn: $game.settings.showFPS)
                }
                section("SPIEL") {
                    Picker("Schwierigkeit", selection: $game.settings.difficulty) {
                        ForEach(Difficulty.allCases) { d in Text(d.displayName).tag(d) }
                    }
                    .pickerStyle(.segmented)
                    Toggle("Blut & Exekutions-Effekte", isOn: $game.settings.bloodEnabled)
                }
                section("AUDIO") {
                    Toggle("Sprachausgabe", isOn: $game.settings.voicesEnabled)
                    Toggle("Musik", isOn: $game.settings.musicEnabled)
                    labeledSlider("Effekte", value: $game.settings.sfxVolume)
                    labeledSlider("Musik-Lautstärke", value: $game.settings.musicVolume)
                }
                section("KAMERA") {
                    labeledSlider("Empfindlichkeit", value: $game.settings.cameraSensitivity, range: 0.3...2.5)
                    Toggle("Y-Achse umkehren", isOn: $game.settings.invertCameraY)
                }
            }
            .tint(Theme.bloodBright)
            .foregroundColor(.white)
            .padding(4)
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(Theme.title(14)).foregroundColor(Theme.bloodBright)
            content()
        }
        .padding(14)
        .glassPanel()
    }

    private func labeledSlider(_ title: String, value: Binding<Float>, range: ClosedRange<Float> = 0...1) -> some View {
        HStack {
            Text(title).font(Theme.body(13)).frame(width: 150, alignment: .leading)
            Slider(value: value, in: range)
        }
    }
}

struct SettingsView: View {
    @ObservedObject var game: GameManager

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                BackButton { game.backToTitle() }
                Spacer()
                Text("EINSTELLUNGEN").font(Theme.title(26)).foregroundColor(.white).glowText(Theme.blood)
                Spacer()
                Color.clear.frame(width: 90, height: 10)
            }
            SettingsPanel(game: game)
                .frame(maxWidth: 640)
                .frame(maxWidth: .infinity)
        }
        .padding(20)
        .background(Color.black.opacity(0.6).ignoresSafeArea())
    }
}

// MARK: - Ergebnis

struct ResultsView: View {
    @ObservedObject var game: GameManager

    var body: some View {
        let r = game.lastResult
        let won = r?.playerWon ?? false
        return VStack(spacing: 16) {
            Text(won ? "SIEG" : "NIEDERLAGE")
                .font(Theme.title(64))
                .foregroundColor(won ? Theme.gold : Theme.bloodBright)
                .glowText(won ? Theme.blood : .black, radius: 18)
            if let r = r {
                HStack(spacing: 14) {
                    stat("RUNDEN", "\(r.roundsWon) : \(r.roundsLost)")
                    stat("MAX. KOMBO", "\(r.maxCombo)")
                    stat("SCHADEN", "\(Int(r.totalDamageDealt))")
                    stat("ZEIT", "\(Int(r.seconds)) s")
                    stat("EXEKUTION", r.executionPerformed ? "JA" : (r.playerWasExecuted ? "ERLITTEN" : "NEIN"))
                }
            }
            if let n = game.newlyUnlockedChapter, let ch = game.chapter(at: n) {
                Text("Freigeschaltet: \(GameManager.chapterLabel(ch)) · \(ch.title)")
                    .font(Theme.body(15))
                    .foregroundColor(Theme.gold)
            }
            buttons
                .frame(maxWidth: 420)
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.opacity(0.65).ignoresSafeArea())
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(spacing: 4) {
            Text(title).font(Theme.title(10)).foregroundColor(.white.opacity(0.6))
            Text(value).font(Theme.mono(20)).foregroundColor(.white)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .glassPanel(corner: 10)
    }

    @ViewBuilder
    private var buttons: some View {
        let won = game.lastResult?.playerWon ?? false
        VStack(spacing: 10) {
            if game.mode == .story {
                if won {
                    MenuButton(title: game.isLastChapter ? "EPILOG" : "WEITER", icon: "play.fill", prominent: true) { game.continueStory() }
                } else {
                    MenuButton(title: "NOCHMAL", icon: "arrow.clockwise", prominent: true) { game.retryKombat() }
                    MenuButton(title: "ZURÜCK IN DIE STADT", icon: "building.2.fill") { game.returnToCityAfterLoss() }
                }
            } else {
                MenuButton(title: "REVANCHE", icon: "arrow.clockwise", prominent: true) { game.retryKombat() }
                MenuButton(title: "NEUE AUSWAHL", icon: "person.2.fill") { game.openFighterSelect() }
            }
            MenuButton(title: "HAUPTMENÜ", icon: "house.fill") { game.returnToMainMenu() }
        }
    }
}

// MARK: - Credits

struct CreditsView: View {
    @ObservedObject var game: GameManager
    @State private var offset: CGFloat = 0

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                Color.black.opacity(0.75).ignoresSafeArea()
                VStack(spacing: 14) {
                    ForEach(Array(StoryData.creditsLines.enumerated()), id: \.offset) { pair in
                        Text(pair.element)
                            .font(pair.offset == 0 ? Theme.title(34) : Theme.body(18))
                            .foregroundColor(pair.offset == 0 ? Theme.bloodBright : .white)
                            .multilineTextAlignment(.center)
                    }
                }
                .frame(maxWidth: .infinity)
                .offset(y: geo.size.height - offset)
                BackButton { game.backToTitle() }
                    .padding(20)
            }
            .onAppear {
                offset = 0
                withAnimation(.linear(duration: 40)) {
                    offset = geo.size.height + 900
                }
            }
        }
    }
}

// MARK: - Pause & Laden

struct PauseMenuView: View {
    @ObservedObject var game: GameManager

    var body: some View {
        ZStack {
            Color.black.opacity(0.6).ignoresSafeArea()
            if game.showPauseSettings {
                VStack(spacing: 12) {
                    HStack {
                        BackButton { game.showPauseSettings = false }
                        Spacer()
                    }
                    SettingsPanel(game: game)
                }
                .frame(maxWidth: 640)
                .padding(24)
            } else {
                VStack(spacing: 12) {
                    Text("PAUSE").font(Theme.title(44)).foregroundColor(.white).glowText(Theme.blood)
                    MenuButton(title: "FORTSETZEN", icon: "play.fill", prominent: true) { game.setPaused(false) }
                    if game.screen == .kombat {
                        MenuButton(title: "KAMPF NEU STARTEN", icon: "arrow.clockwise") { game.retryKombat() }
                    }
                    MenuButton(title: "EINSTELLUNGEN", icon: "gearshape.fill") { game.showPauseSettings = true }
                    MenuButton(title: "HAUPTMENÜ", icon: "house.fill") { game.returnToMainMenu() }
                }
                .frame(maxWidth: 380)
            }
        }
    }
}

struct LoadingCurtain: View {
    let info: GameManager.LoadingInfo

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 14) {
                if let l = info.vsLeft, let r = info.vsRight {
                    HStack(spacing: 30) {
                        nameBlock(l)
                        Text("VS").font(Theme.title(54)).foregroundColor(Theme.bloodBright).glowText(Theme.blood, radius: 16)
                        nameBlock(r)
                    }
                } else if !info.title.isEmpty {
                    Text(info.title)
                        .font(Theme.title(40))
                        .tracking(4)
                        .foregroundColor(.white)
                        .glowText(Theme.blood, radius: 12)
                }
                if !info.subtitle.isEmpty {
                    Text(info.subtitle).font(Theme.body(17)).foregroundColor(.white.opacity(0.8))
                }
                if !info.tip.isEmpty {
                    Text(info.tip)
                        .font(Theme.body(13))
                        .foregroundColor(.white.opacity(0.55))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 520)
                        .padding(.top, 20)
                }
                ProgressView().tint(Theme.bloodBright).padding(.top, 10)
            }
            .padding(30)
        }
        .transition(.opacity)
    }

    private func nameBlock(_ id: FighterID) -> some View {
        let d = Roster.def(id)
        return VStack(spacing: 4) {
            Text(d.name.uppercased()).font(Theme.title(30)).foregroundColor(.white)
            Text(d.title).font(Theme.body(12)).foregroundColor(Color(uiColor: Roster.signatureColor(id)))
        }
    }
}

struct FPSBadge: View {
    @ObservedObject var counter: GameManager.FPSCounter
    var body: some View {
        Text("\(counter.fps) FPS")
            .font(Theme.mono(12))
            .foregroundColor(.green)
            .padding(6)
            .background(Color.black.opacity(0.5))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            .padding(6)
            .allowsHitTesting(false)
    }
}

// =====================================================================
// MARK: - UI/RootView.swift
// =====================================================================

// =====================================================================
//  RootView – 3D-Szene im Hintergrund, darüber der aktuelle Bildschirm
// =====================================================================

struct RootView: View {
    @StateObject private var game = GameManager()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        ZStack {
            SceneViewHost(game.activeController,
                          input: game.input,
                          quality: game.settings.quality,
                          isPlaying: true,
                          lookEnabled: game.screen == .openWorld)
                .ignoresSafeArea()
            screenOverlay
            if game.paused {
                PauseMenuView(game: game)
                    .transition(.opacity)
            }
            if let info = game.loading {
                LoadingCurtain(info: info)
            }
            if game.settings.showFPS {
                FPSBadge(counter: game.fpsCounter)
            }
        }
        .background(Color.black)
        .onChange(of: scenePhase) { _, phase in
            game.handleScenePhase(phase)
        }
        .onAppear {
            UIApplication.shared.isIdleTimerDisabled = true
        }
    }

    @ViewBuilder
    private var screenOverlay: some View {
        switch game.screen {
        case .title:
            TitleMenuView(game: game).transition(.opacity)
        case .chapterSelect:
            ChapterSelectView(game: game).transition(.opacity)
        case .fighterSelect:
            FighterSelectView(game: game).transition(.opacity)
        case .settings:
            SettingsView(game: game).transition(.opacity)
        case .openWorld:
            WorldHUDView(hud: game.worldHUD, input: game.input, onPause: { game.setPaused(true) })
        case .cutscene:
            CutsceneOverlayView(hud: game.cutsceneHUD, onSkip: { game.skipCutscene() })
        case .kombat:
            KombatHUDView(hud: game.kombatHUD, input: game.input, onPause: { game.setPaused(true) })
        case .results:
            ResultsView(game: game).transition(.opacity)
        case .credits:
            CreditsView(game: game).transition(.opacity)
        }
    }
}

// =====================================================================
// MARK: - UI/SceneViewHost.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – SceneViewHost
//  SwiftUI-Hülle um eine SCNView. Tauscht Szene + Kamera, sobald sich
//  der aktive Controller ändert. Ziehen in der rechten Bildschirmhälfte
//  (nur dort, wo keine SwiftUI-Bedienelemente liegen) → input.addLook.
// =====================================================================

struct SceneViewHost: UIViewRepresentable {
    var controller: GameSceneController?
    var input: InputState
    var quality: QualityPreset
    var isPlaying: Bool
    var lookEnabled: Bool

    init(_ controller: GameSceneController?,
         input: InputState,
         quality: QualityPreset,
         isPlaying: Bool = true,
         lookEnabled: Bool = true) {
        self.controller = controller
        self.input = input
        self.quality = quality
        self.isPlaying = isPlaying
        self.lookEnabled = lookEnabled
    }

    // MARK: Coordinator

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var input: InputState
        /// Schwach gehalten: wird der alte Controller freigegeben, gilt der nächste sicher als „neu“
        /// (ObjectIdentifier allein könnte bei wiederverwendeter Speicheradresse täuschen).
        weak var attachedController: AnyObject?
        var attachedID: ObjectIdentifier?
        var appliedQuality: QualityPreset?
        var lookEnabled: Bool = true

        init(input: InputState) {
            self.input = input
            super.init()
        }

        @objc func handlePan(_ recognizer: UIPanGestureRecognizer) {
            guard let v = recognizer.view else { return }
            switch recognizer.state {
            case .began, .changed:
                let t = recognizer.translation(in: v)
                recognizer.setTranslation(CGPoint.zero, in: v)
                if lookEnabled && (t.x != 0 || t.y != 0) {
                    input.addLook(SIMD2<Float>(Float(t.x), Float(t.y)))
                }
            default:
                break
            }
        }

        func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
            guard lookEnabled, let v = gestureRecognizer.view else { return false }
            let p = gestureRecognizer.location(in: v)
            return p.x >= v.bounds.width * 0.45
        }

        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            return true
        }
    }

    func makeCoordinator() -> Coordinator {
        return Coordinator(input: input)
    }

    // MARK: UIViewRepresentable

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView(frame: CGRect(x: 0, y: 0, width: 100, height: 100), options: nil)
        Render.configure(view: view, quality: quality)
        view.rendersContinuously = true
        view.isPlaying = true
        view.allowsCameraControl = false
        view.isMultipleTouchEnabled = true
        view.backgroundColor = UIColor.black

        let coordinator = context.coordinator
        coordinator.appliedQuality = quality
        coordinator.lookEnabled = lookEnabled

        let pan = UIPanGestureRecognizer(target: coordinator, action: #selector(Coordinator.handlePan(_:)))
        pan.cancelsTouchesInView = false
        pan.delaysTouchesBegan = false
        pan.delaysTouchesEnded = false
        pan.maximumNumberOfTouches = 1
        pan.delegate = coordinator
        view.addGestureRecognizer(pan)

        SceneViewHost.attach(controller, to: view, coordinator: coordinator)
        view.isPlaying = isPlaying
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        let coordinator = context.coordinator
        coordinator.input = input
        coordinator.lookEnabled = lookEnabled

        if coordinator.appliedQuality != quality {
            coordinator.appliedQuality = quality
            Render.configure(view: view, quality: quality)
            view.rendersContinuously = true
        }

        SceneViewHost.attach(controller, to: view, coordinator: coordinator)

        if view.isPlaying != isPlaying {
            view.isPlaying = isPlaying
        }
    }

    static func dismantleUIView(_ uiView: SCNView, coordinator: Coordinator) {
        uiView.isPlaying = false
        coordinator.attachedController = nil
        coordinator.attachedID = nil
    }

    /// Setzt Szene + Kamera nur, wenn sich die Controller-Identität geändert hat.
    private static func attach(_ controller: GameSceneController?, to view: SCNView, coordinator: Coordinator) {
        let incoming: AnyObject? = controller.map { $0 as AnyObject }
        let current: AnyObject? = coordinator.attachedController
        if incoming === current { return }

        guard let c = controller else {
            coordinator.attachedController = nil
            coordinator.attachedID = nil
            view.scene = nil
            return
        }
        coordinator.attachedController = c as AnyObject
        coordinator.attachedID = ObjectIdentifier(c as AnyObject)
        view.scene = c.scene
        view.pointOfView = c.cameraNode
        view.isPlaying = true
        c.didAttach(to: view)
    }
}

// =====================================================================
// MARK: - UI/TitleBackdropController.swift
// =====================================================================

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

// =====================================================================
// MARK: - App/GameManager.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – GameManager
//  Einzige Quelle der Wahrheit für Bildschirmfluss, Einstellungen,
//  Story-Fortschritt, aktive 3D-Szene und Spielschleife.
//  Alles läuft auf dem Main-Thread.
// =====================================================================

final class GameManager: ObservableObject {

    // MARK: - Verschachtelte Typen

    /// Wo im Story-Ablauf eines Kapitels wir gerade sind.
    enum StoryPhase: Equatable {
        case none
        case intro
        case world
        case preFight
        case kombat
        case outro
        case epilogue
    }

    /// Inhalt des schwarzen Lade-Vorhangs zwischen zwei Szenen.
    struct LoadingInfo: Equatable {
        var title: String
        var subtitle: String
        var tip: String
        var vsLeft: FighterID?
        var vsRight: FighterID?

        static let blank = LoadingInfo(title: "", subtitle: "", tip: "", vsLeft: nil, vsRight: nil)
    }

    /// Kleines eigenes Modell, damit die FPS-Anzeige nicht die ganze UI neu zeichnet.
    final class FPSCounter: ObservableObject {
        @Published var fps: Int = 0
    }

    // MARK: - Veröffentlichter Zustand

    @Published var screen: GameScreen = .title
    @Published var mode: GameMode = .story
    @Published var settings: GameSettings {
        didSet { settingsDidChange(from: oldValue) }
    }
    /// Höchstes freigeschaltetes Kapitel (Index in StoryData.chapters), gespeichert.
    @Published private(set) var storyProgress: Int
    /// Finale geschafft (gespeichert).
    @Published private(set) var storyCompleted: Bool
    @Published var currentChapterIndex: Int = 0
    @Published var lastResult: KombatResult? = nil
    @Published private(set) var paused: Bool = false
    /// Der SceneViewHost beobachtet diese Referenz.
    @Published private(set) var activeController: GameSceneController? = nil
    @Published private(set) var storyPhase: StoryPhase = .none
    @Published private(set) var loading: LoadingInfo? = nil
    @Published var showPauseSettings: Bool = false
    /// Gerade durch einen Sieg freigeschaltetes Kapitel (für den Ergebnis-Bildschirm).
    @Published private(set) var newlyUnlockedChapter: Int? = nil
    /// Credits laufen nach dem Epilog (statt aus dem Hauptmenü).
    @Published private(set) var creditsAfterEpilogue: Bool = false

    // Versus-Auswahl
    @Published var versusPlayer: FighterID = .silkstrike
    @Published var versusCPU: FighterID = .vex
    @Published var versusArena: ArenaID = .rainRooftop
    @Published var versusDifficulty: Difficulty
    @Published var versusDarkSuit: Bool = false

    // MARK: - Besitz

    let input: InputState
    let controllerBridge: ControllerBridge
    let gameLoop: GameLoop
    let kombatHUD = KombatHUD()
    let worldHUD = WorldHUD()
    let cutsceneHUD = CutsceneHUD()
    let fpsCounter = FPSCounter()

    private(set) var lastKombatSetup: KombatSetup? = nil
    private var fpsAccumulator: Float = 0
    private var transitionSerial: Int = 0
    private var tipIndex: Int = 0

    private static let progressKey = "silkstrike.storyProgress.v1"
    private static let completedKey = "silkstrike.storyCompleted.v1"

    private static let loadingTips: [String] = [
        "Halte NETZ gedrückt, um zu schwingen – lass im tiefsten Punkt los, um am weitesten zu fliegen.",
        "Netzsprint zieht dich blitzschnell zu der Stelle, auf die die Kamera zielt.",
        "Blocken fängt den Großteil des Schadens ab – Würfe und Griffe brechen aber jede Deckung.",
        "Ist deine Brutal-Leiste voll, entfessle den Brutal-Schlag.",
        "Erscheint „VOLLENDE ES!“, bleiben dir nur Sekunden für die Exekution.",
        "Auf den Dächern von Neo-Haven liegen Blutsiegel versteckt.",
        "Ein Gamecontroller oder eine Tastatur wird automatisch erkannt.",
        "Spezialangriffe brauchen Zeit zum Aufladen – setze sie gezielt ein.",
        "In den Einstellungen kannst du Blut abschalten und die Grafikstufe wählen."
    ]

    // MARK: - Init

    init() {
        let loaded = GameSettings.load()
        let inputState = InputState()
        let loop = GameLoop()
        let defaults = UserDefaults.standard
        let maxIndex = Swift.max(0, StoryData.chapters.count - 1)
        let savedProgress = defaults.integer(forKey: GameManager.progressKey)

        self.settings = loaded
        self.versusDifficulty = loaded.difficulty
        self.storyProgress = Swift.min(Swift.max(0, savedProgress), maxIndex)
        self.storyCompleted = defaults.bool(forKey: GameManager.completedKey)
        self.input = inputState
        self.controllerBridge = ControllerBridge(input: inputState)
        self.gameLoop = loop

        FX.quality = loaded.quality
        FX.bloodEnabled = loaded.bloodEnabled
        AudioDirector.shared.start()
        AudioDirector.shared.apply(loaded)

        loop.preferredMaxFPS = GameLoop.recommendedMaxFPS(for: loaded.quality)
        loop.onUpdate = { [weak self] dt in
            self?.tick(dt: dt)
        }
        controllerBridge.start()
        loop.start()

        replaceController {
            TitleBackdropController(quality: loaded.quality, darkSuit: false)
        }
        AudioDirector.shared.setMusic(.menu)
    }

    deinit {
        gameLoop.stop()
        controllerBridge.stop()
    }

    // MARK: - Abfragen für die UI

    var chapters: [ChapterDef] { StoryData.chapters }

    func chapter(at index: Int) -> ChapterDef? {
        let list = StoryData.chapters
        guard index >= 0, index < list.count else { return nil }
        return list[index]
    }

    var currentChapter: ChapterDef? { chapter(at: currentChapterIndex) }

    var isLastChapter: Bool { currentChapterIndex >= StoryData.chapters.count - 1 }

    func isChapterUnlocked(_ index: Int) -> Bool { index <= storyProgress }

    /// "PROLOG" oder "KAPITEL 3".
    static func chapterLabel(_ ch: ChapterDef) -> String {
        return ch.number == 0 ? "PROLOG" : "KAPITEL \(ch.number)"
    }

    /// Schwarzseide darf im Versus gewählt werden, sobald Kapitel 3 geschafft ist.
    var darkSuitUnlocked: Bool {
        if storyCompleted { return true }
        let list = StoryData.chapters
        guard let idx = list.firstIndex(where: { $0.heroDarkSuit }) else { return false }
        return storyProgress > idx
    }

    var isInGameplay: Bool { screen == .openWorld || screen == .kombat }

    // MARK: - Spielschleife

    private func tick(dt: Float) {
        controllerBridge.poll()
        handleSystemButtons()
        if !paused, let c = activeController {
            c.update(dt: dt)
        }
        updateFPS(dt: dt)
    }

    private func handleSystemButtons() {
        guard loading == nil else {
            _ = input.consumePress(.pause)
            return
        }
        switch screen {
        case .openWorld, .kombat:
            if input.consumePress(.pause) {
                setPaused(!paused)
            }
        case .cutscene:
            if input.consumePress(.skip) || input.consumePress(.pause) {
                skipCutscene()
            }
        case .title, .chapterSelect, .fighterSelect, .settings, .results, .credits:
            break
        }
    }

    private func updateFPS(dt: Float) {
        guard settings.showFPS else { return }
        fpsAccumulator += dt
        if fpsAccumulator >= 0.5 {
            fpsAccumulator = 0
            let value = Int(gameLoop.measuredFPS.rounded())
            if value != fpsCounter.fps { fpsCounter.fps = value }
        }
    }

    // MARK: - Einstellungen

    private func settingsDidChange(from old: GameSettings) {
        guard old != settings else { return }
        settings.save()
        AudioDirector.shared.apply(settings)
        FX.quality = settings.quality
        FX.bloodEnabled = settings.bloodEnabled
        if old.quality != settings.quality {
            gameLoop.preferredMaxFPS = GameLoop.recommendedMaxFPS(for: settings.quality)
        }
    }

    // MARK: - App-Lebenszyklus

    func handleScenePhase(_ phase: ScenePhase) {
        if phase == .active {
            gameLoop.isPaused = false
            AudioDirector.shared.start()
        } else if phase == .inactive {
            if isInGameplay && loading == nil { setPaused(true) }
        } else if phase == .background {
            if isInGameplay { setPaused(true) }
            gameLoop.isPaused = true
        }
    }

    // MARK: - Pause

    func setPaused(_ p: Bool) {
        if p && !isInGameplay { return }
        guard paused != p else { return }
        paused = p
        if !p { showPauseSettings = false }
        if let k = activeController as? KombatController {
            k.setPaused(p)
        }
        input.reset()
        if p {
            AudioDirector.shared.play(.uiBack, volume: 0.8, pitch: 0.9)
            Haptics.light()
        } else {
            AudioDirector.shared.play(.uiConfirm, volume: 0.7)
        }
    }

    // MARK: - Menü-Navigation

    func openStory() {
        mode = .story
        navigateMenu(to: .chapterSelect)
    }

    func openVersus() {
        mode = .versus
        if !darkSuitUnlocked { versusDarkSuit = false }
        navigateMenu(to: .fighterSelect)
    }

    func openSettings() {
        navigateMenu(to: .settings)
    }

    func openCredits() {
        creditsAfterEpilogue = false
        navigateMenu(to: .credits)
    }

    func backToTitle() {
        navigateMenu(to: .title)
    }

    func openChapterSelect() {
        mode = .story
        navigateMenu(to: .chapterSelect)
    }

    func openFighterSelect() {
        mode = .versus
        navigateMenu(to: .fighterSelect)
    }

    /// Zurück ins Hauptmenü (aus dem Spiel, der Pause oder dem Ergebnis).
    func returnToMainMenu() {
        storyPhase = .none
        newlyUnlockedChapter = nil
        navigateMenu(to: .title)
    }

    /// Menübildschirme laufen vor der Titelkulisse. Fehlt sie, wird sie mit Vorhang aufgebaut.
    private func navigateMenu(to target: GameScreen) {
        if activeController is TitleBackdropController && loading == nil {
            if paused { paused = false }
            withAnimation(.easeInOut(duration: 0.35)) {
                screen = target
            }
            return
        }
        transition(LoadingInfo.blank) { [weak self] in
            guard let self = self else { return }
            self.storyPhase = .none
            self.replaceController {
                TitleBackdropController(quality: self.settings.quality, darkSuit: false)
            }
            AudioDirector.shared.setMusic(target == .credits && self.creditsAfterEpilogue ? .victory : .menu)
            self.screen = target
        }
    }

    // MARK: - Story

    /// Höchstes freigeschaltetes Kapitel starten.
    func continueStoryFromProgress() {
        startChapter(storyProgress)
    }

    func startChapter(_ index: Int) {
        guard let ch = chapter(at: index), isChapterUnlocked(index) else { return }
        mode = .story
        currentChapterIndex = index
        newlyUnlockedChapter = nil
        lastResult = nil
        storyPhase = .intro
        let info = LoadingInfo(title: GameManager.chapterLabel(ch),
                               subtitle: ch.title,
                               tip: ch.subtitle,
                               vsLeft: nil,
                               vsRight: nil)
        playCutscene(id: ch.introCutscene, info: info) { [weak self] in
            self?.enterStoryWorld()
        }
    }

    /// Kai trägt in der offenen Welt den Anzug, den er am Ende des Vorkapitels trug
    /// (Kapitel 3: erst im Vorkampf wird der Anzug schwarz, Kapitel 5: erst dort reißt er ab).
    private func worldDarkSuit(for index: Int) -> Bool {
        guard index > 0, let previous = chapter(at: index - 1) else { return false }
        return previous.heroDarkSuit
    }

    private func enterStoryWorld() {
        guard let ch = currentChapter else {
            returnToMainMenu()
            return
        }
        storyPhase = .world
        let ctx = WorldContext(chapter: ch,
                               spawnAt: .heroApartment,
                               timeOfDay: ch.timeOfDay,
                               heroDarkSuit: worldDarkSuit(for: currentChapterIndex))
        let info = LoadingInfo(title: "NEO-HAVEN",
                               subtitle: ch.objectiveText,
                               tip: nextTip(),
                               vsLeft: nil,
                               vsRight: nil)
        enterWorld(ctx, info: info)
    }

    private func objectiveReached() {
        guard mode == .story, storyPhase == .world, screen == .openWorld, let ch = currentChapter else { return }
        storyPhase = .preFight
        if let pre = ch.preFightCutscene, StoryData.cutscene(pre) != nil {
            playCutscene(id: pre, info: LoadingInfo.blank) { [weak self] in
                self?.startStoryKombat()
            }
        } else {
            startStoryKombat()
        }
    }

    private func startStoryKombat() {
        guard let ch = currentChapter else {
            returnToMainMenu()
            return
        }
        let level = Swift.min(1.2, Swift.max(0.1, ch.aiLevel * settings.difficulty.aiMultiplier))
        let setup = KombatSetup(player: .silkstrike,
                                playerUsesDarkSuit: ch.heroDarkSuit,
                                cpu: ch.opponent,
                                arena: ch.arena,
                                aiLevel: level,
                                roundsToWin: 2,
                                roundSeconds: 90,
                                isStory: true)
        mode = .story
        startKombat(setup)
    }

    private func unlockAfterWin(index: Int) {
        let count = StoryData.chapters.count
        let defaults = UserDefaults.standard
        if index + 1 < count {
            if storyProgress < index + 1 {
                storyProgress = index + 1
                newlyUnlockedChapter = index + 1
                defaults.set(storyProgress, forKey: GameManager.progressKey)
            }
        } else if !storyCompleted {
            storyCompleted = true
            defaults.set(true, forKey: GameManager.completedKey)
        }
    }

    /// Ergebnis-Bildschirm „Weiter“ nach einem Story-Sieg.
    func continueStory() {
        let next = currentChapterIndex + 1
        if next < StoryData.chapters.count {
            startChapter(next)
        } else {
            playEpilogue()
        }
    }

    private func playEpilogue() {
        storyPhase = .epilogue
        mode = .story
        let info = LoadingInfo(title: "EPILOG", subtitle: "Sonnenaufgang über Neo-Haven", tip: "", vsLeft: nil, vsRight: nil)
        playCutscene(id: StoryData.epilogueCutscene, info: info) { [weak self] in
            self?.showCreditsAfterEpilogue()
        }
    }

    private func showCreditsAfterEpilogue() {
        creditsAfterEpilogue = true
        storyPhase = .none
        navigateMenu(to: .credits)
    }

    /// Nach einer Niederlage: zurück in die offene Welt des Kapitels.
    func returnToCityAfterLoss() {
        guard mode == .story, currentChapter != nil else {
            returnToMainMenu()
            return
        }
        enterStoryWorld()
    }

    // MARK: - Freies Schwingen

    func startFreeRoam() {
        mode = .freeRoam
        storyPhase = .none
        lastResult = nil
        let ctx = WorldContext(chapter: nil, spawnAt: .heroApartment, timeOfDay: .night, heroDarkSuit: false)
        let info = LoadingInfo(title: "FREIES SCHWINGEN",
                               subtitle: "Neo-Haven gehört dir",
                               tip: nextTip(),
                               vsLeft: nil,
                               vsRight: nil)
        enterWorld(ctx, info: info)
    }

    private func enterWorld(_ ctx: WorldContext, info: LoadingInfo) {
        transition(info) { [weak self] in
            guard let self = self else { return }
            self.worldHUD.toast = nil
            self.worldHUD.interactPrompt = nil
            self.worldHUD.health = 1
            AudioDirector.shared.setMusic(.roam)
            self.replaceController {
                let world = OpenWorldController(context: ctx, settings: self.settings, input: self.input, hud: self.worldHUD)
                world.onReachObjective = { [weak self, weak world] in
                    DispatchQueue.main.async {
                        guard let self = self, let world = world, self.isActive(world) else { return }
                        self.objectiveReached()
                    }
                }
                world.onHeroDefeated = { [weak self, weak world] in
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
                        guard let self = self, let world = world, self.isActive(world) else { return }
                        world.respawn()
                    }
                }
                return world
            }
            self.screen = .openWorld
        }
    }

    // MARK: - Versus

    func startVersusMatch() {
        mode = .versus
        storyPhase = .none
        let level = Swift.min(1.2, 0.85 * versusDifficulty.aiMultiplier)
        let setup = KombatSetup(player: versusPlayer,
                                playerUsesDarkSuit: versusPlayer == .silkstrike && versusDarkSuit && darkSuitUnlocked,
                                cpu: versusCPU,
                                arena: versusArena,
                                aiLevel: level,
                                roundsToWin: 2,
                                roundSeconds: 90,
                                isStory: false)
        startKombat(setup)
    }

    func randomizeVersusCPU() {
        let options = FighterID.allCases.filter { $0 != versusPlayer }
        if let pick = options.randomElement() { versusCPU = pick }
    }

    // MARK: - Kombat

    private func startKombat(_ setup: KombatSetup) {
        lastKombatSetup = setup
        lastResult = nil
        let arenaName = setup.arena.displayName
        let info = LoadingInfo(title: "\(Roster.def(setup.player).name.uppercased())  VS  \(Roster.def(setup.cpu).name.uppercased())",
                               subtitle: arenaName,
                               tip: nextTip(),
                               vsLeft: setup.player,
                               vsRight: setup.cpu)
        transition(info, delay: 1.25) { [weak self] in
            guard let self = self else { return }
            self.resetKombatHUD()
            AudioDirector.shared.setMusic(setup.cpu == .malrek ? .boss : .combat)
            self.replaceController {
                let k = KombatController(setup: setup, settings: self.settings, input: self.input, hud: self.kombatHUD)
                k.onMatchEnd = { [weak self, weak k] result in
                    DispatchQueue.main.async {
                        guard let self = self, let k = k, self.isActive(k) else { return }
                        self.handleMatchEnd(result)
                    }
                }
                return k
            }
            if self.mode == .story { self.storyPhase = .kombat }
            self.screen = .kombat
        }
    }

    /// „Nochmal“ / „Revanche“ / „Kampf neu starten“.
    func retryKombat() {
        guard let setup = lastKombatSetup else {
            returnToMainMenu()
            return
        }
        if setup.isStory { mode = .story } else { mode = .versus }
        startKombat(setup)
    }

    private func handleMatchEnd(_ result: KombatResult) {
        guard screen == .kombat else { return }
        lastResult = result
        if paused {
            paused = false
            showPauseSettings = false
        }
        if mode == .story && result.playerWon {
            storyPhase = .outro
            unlockAfterWin(index: currentChapterIndex)
            guard let ch = currentChapter, StoryData.cutscene(ch.outroCutscene) != nil else {
                showResultsOverBackdrop()
                return
            }
            playCutscene(id: ch.outroCutscene, info: LoadingInfo.blank) { [weak self] in
                self?.showResultsOverBackdrop()
            }
        } else {
            // Niederlage oder Versus: Arena bleibt im Hintergrund stehen.
            AudioDirector.shared.setMusic(result.playerWon ? .victory : .sad)
            if result.playerWon { Haptics.success() } else { Haptics.warning() }
            withAnimation(.easeInOut(duration: 0.5)) {
                screen = .results
            }
        }
    }

    private func showResultsOverBackdrop() {
        transition(LoadingInfo.blank) { [weak self] in
            guard let self = self else { return }
            self.replaceController {
                TitleBackdropController(quality: self.settings.quality, darkSuit: false)
            }
            AudioDirector.shared.setMusic(.victory)
            Haptics.success()
            self.screen = .results
        }
    }

    private func resetKombatHUD() {
        let h = kombatHUD
        h.banner = nil
        h.bannerStyle = .info
        h.comboText = nil
        h.showExecutePrompt = false
        h.cinematic = false
        h.flashOpacity = 0
        h.controlsEnabled = false
        h.matchOver = false
        h.playerWon = false
        h.p1Health = 1
        h.p2Health = 1
        h.p1HealthLag = 1
        h.p2HealthLag = 1
        h.p1Rounds = 0
        h.p2Rounds = 0
    }

    // MARK: - Cutscenes

    func skipCutscene() {
        guard screen == .cutscene, loading == nil else { return }
        if let c = activeController as? CutsceneController {
            AudioDirector.shared.stopSpeech()
            c.skip()
        }
    }

    private func playCutscene(id: String, info: LoadingInfo, then next: @escaping () -> Void) {
        guard let def = StoryData.cutscene(id) else {
            next()
            return
        }
        transition(info) { [weak self] in
            guard let self = self else { return }
            let hud = self.cutsceneHUD
            hud.title = nil
            hud.speaker = nil
            hud.line = nil
            hud.letterbox = true
            hud.fadeOpacity = 1
            hud.flashOpacity = 0
            AudioDirector.shared.setMusic(def.music)
            self.replaceController {
                let c = CutsceneController(def: def, settings: self.settings, hud: hud)
                c.onFinished = { [weak self, weak c] in
                    DispatchQueue.main.async {
                        guard let self = self, let c = c, self.isActive(c) else { return }
                        next()
                    }
                }
                return c
            }
            self.screen = .cutscene
        }
    }

    // MARK: - Szenenwechsel

    func isActive(_ object: AnyObject) -> Bool {
        guard let c = activeController else { return false }
        return (c as AnyObject) === object
    }

    /// Alten Controller abbauen, Eingaben leeren, neuen Controller bauen und veröffentlichen.
    private func replaceController(_ make: () -> GameSceneController?) {
        let old = activeController
        old?.teardown()
        AudioDirector.shared.stopSpeech()
        AudioDirector.shared.setSlowMotion(1)
        input.reset()
        paused = false
        showPauseSettings = false
        let next = make()
        input.reset()
        activeController = next
    }

    /// Schwarzer Vorhang → Arbeit (Szene bauen) → Vorhang auf.
    private func transition(_ info: LoadingInfo, delay: Double = 0.3, _ work: @escaping () -> Void) {
        transitionSerial += 1
        let serial = transitionSerial
        if paused {
            paused = false
            if let k = activeController as? KombatController { k.setPaused(false) }
        }
        showPauseSettings = false
        withAnimation(.easeIn(duration: 0.25)) {
            loading = info
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self = self, serial == self.transitionSerial else { return }
            work()
            // Ein paar Frames rendern lassen, bevor der Vorhang aufgeht.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
                guard let self = self, serial == self.transitionSerial else { return }
                withAnimation(.easeOut(duration: 0.5)) {
                    self.loading = nil
                }
            }
        }
    }

    private func nextTip() -> String {
        let tips = GameManager.loadingTips
        guard !tips.isEmpty else { return "" }
        tipIndex = (tipIndex + 1) % tips.count
        return tips[tipIndex]
    }
}

// =====================================================================
// MARK: - App/SilkstrikeApp.swift
// =====================================================================

// =====================================================================
//  SILKSTRIKE – Blutturnier
//  Einstiegspunkt der App (Swift Playgrounds & Xcode)
// =====================================================================

@main
struct SilkstrikeApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
                .statusBarHidden(true)
                .persistentSystemOverlays(.hidden)
                .preferredColorScheme(.dark)
                .ignoresSafeArea()
        }
    }
}
