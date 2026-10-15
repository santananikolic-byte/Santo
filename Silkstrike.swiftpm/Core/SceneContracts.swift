import Foundation
import SceneKit
import Combine
import UIKit
import simd

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
