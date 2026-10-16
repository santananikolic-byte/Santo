import SwiftUI
import UIKit

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
