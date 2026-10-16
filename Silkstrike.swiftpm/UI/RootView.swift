import SwiftUI

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
