import Foundation
import UIKit

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
