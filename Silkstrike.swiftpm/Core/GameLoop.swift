import Foundation
import QuartzCore

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
