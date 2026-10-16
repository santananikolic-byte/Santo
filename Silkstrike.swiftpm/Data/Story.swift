import Foundation
import UIKit
import simd

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
