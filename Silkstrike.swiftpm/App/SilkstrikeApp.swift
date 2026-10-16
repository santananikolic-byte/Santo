import SwiftUI

// =====================================================================
//  SILKSTRIKE – Blutturnier
//  Einstiegspunkt der App (Swift Playgrounds & Xcode)
// =====================================================================

@main
struct SilkstrikeApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
                .statusBarHidden(true)
                .persistentSystemOverlays(.hidden)
                .preferredColorScheme(.dark)
                .ignoresSafeArea()
        }
    }
}
