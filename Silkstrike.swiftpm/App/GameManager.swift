import Foundation
import SwiftUI
import SceneKit
import Combine
import UIKit

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
