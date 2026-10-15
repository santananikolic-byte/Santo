import Foundation
import QuartzCore
import GameController
import simd

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
