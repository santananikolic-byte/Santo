import Foundation
import UIKit
import simd

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
