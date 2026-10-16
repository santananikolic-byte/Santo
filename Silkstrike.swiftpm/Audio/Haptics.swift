import UIKit
import QuartzCore

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
