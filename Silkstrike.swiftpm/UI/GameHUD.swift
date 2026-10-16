import SwiftUI
import UIKit
import simd

// =====================================================================
//  Theme, Touch-Steuerung und Spiel-HUDs (Kombat, offene Welt, Cutscene)
// =====================================================================

enum Theme {
    static let blood = Color(red: 0.72, green: 0.03, blue: 0.09)
    static let bloodBright = Color(red: 1.0, green: 0.16, blue: 0.22)
    static let gold = Color(red: 1.0, green: 0.8, blue: 0.36)
    static let steel = Color(white: 0.78)
    static let ink = Color(red: 0.03, green: 0.02, blue: 0.035)
    static let violet = Color(red: 0.62, green: 0.32, blue: 1.0)
    static let cyan = Color(red: 0.3, green: 0.85, blue: 1.0)

    static func title(_ size: CGFloat) -> Font { return .system(size: size, weight: .black, design: .default) }
    static func body(_ size: CGFloat) -> Font { return .system(size: size, weight: .semibold, design: .default) }
    static func mono(_ size: CGFloat) -> Font { return .system(size: size, weight: .heavy, design: .monospaced) }
}

struct GlassPanelStyle: ViewModifier {
    var corner: CGFloat = 14
    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: corner, style: .continuous).stroke(Theme.blood.opacity(0.55), lineWidth: 1))
    }
}

extension View {
    func glassPanel(corner: CGFloat = 14) -> some View {
        return modifier(GlassPanelStyle(corner: corner))
    }

    func glowText(_ color: Color, radius: CGFloat = 8) -> some View {
        return shadow(color: color.opacity(0.9), radius: radius).shadow(color: .black.opacity(0.8), radius: 2, x: 0, y: 2)
    }
}

// MARK: - Touch-Steuerung

struct VirtualJoystick: View {
    let input: InputState
    var radius: CGFloat = 60

    @State private var origin: CGPoint? = nil
    @State private var knob: CGSize = .zero

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.clear.contentShape(Rectangle())
                if let o = origin {
                    Circle()
                        .fill(Color.white.opacity(0.08))
                        .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 2))
                        .frame(width: radius * 2, height: radius * 2)
                        .position(o)
                    Circle()
                        .fill(Theme.blood.opacity(0.75))
                        .overlay(Circle().stroke(Color.white.opacity(0.7), lineWidth: 2))
                        .frame(width: radius * 0.9, height: radius * 0.9)
                        .position(x: o.x + knob.width, y: o.y + knob.height)
                } else {
                    Circle()
                        .stroke(Color.white.opacity(0.18), style: StrokeStyle(lineWidth: 2, dash: [6, 6]))
                        .frame(width: radius * 2, height: radius * 2)
                        .position(x: radius + 40, y: geo.size.height - radius - 40)
                }
            }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { v in
                        let o = origin ?? v.startLocation
                        if origin == nil { origin = o }
                        var dx = v.location.x - o.x
                        var dy = v.location.y - o.y
                        let len = (dx * dx + dy * dy).squareRoot()
                        if len > radius {
                            dx = dx / len * radius
                            dy = dy / len * radius
                        }
                        knob = CGSize(width: dx, height: dy)
                        var mx = Float(dx / radius)
                        var my = Float(-dy / radius)
                        if abs(mx) < 0.12 { mx = 0 }
                        if abs(my) < 0.12 { my = 0 }
                        input.move = SIMD2<Float>(mx, my)
                    }
                    .onEnded { _ in
                        origin = nil
                        knob = .zero
                        input.move = .zero
                    }
            )
        }
    }
}

struct ActionButton: View {
    let title: String
    let icon: String
    let button: GameButton
    let input: InputState
    var size: CGFloat = 64
    var color: Color = Theme.blood
    var enabled: Bool = true

    @State private var pressed = false

    var body: some View {
        ZStack {
            Circle()
                .fill(color.opacity(enabled ? (pressed ? 0.9 : 0.5) : 0.15))
            Circle()
                .stroke(Color.white.opacity(enabled ? 0.75 : 0.25), lineWidth: 2)
            VStack(spacing: 1) {
                Image(systemName: icon)
                    .font(.system(size: size * 0.3, weight: .bold))
                Text(title)
                    .font(.system(size: Swift.max(8, size * 0.14), weight: .heavy))
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            }
            .foregroundColor(.white.opacity(enabled ? 1 : 0.4))
            .padding(4)
        }
        .frame(width: size, height: size)
        .scaleEffect(pressed ? 0.9 : 1)
        .animation(.easeOut(duration: 0.08), value: pressed)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    guard enabled, !pressed else { return }
                    pressed = true
                    input.press(button)
                    Haptics.light()
                }
                .onEnded { _ in
                    if pressed { input.release(button) }
                    pressed = false
                }
        )
    }
}

struct PauseButton: View {
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: "pause.fill")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Color.black.opacity(0.45)))
                .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 1))
        }
    }
}

struct LetterboxBars: View {
    let visible: Bool
    var body: some View {
        GeometryReader { geo in
            let h = visible ? geo.size.height * 0.11 : 0
            VStack(spacing: 0) {
                Rectangle().fill(Color.black).frame(height: h)
                Spacer(minLength: 0)
                Rectangle().fill(Color.black).frame(height: h)
            }
            .animation(.easeInOut(duration: 0.45), value: visible)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

// MARK: - Kombat-HUD

struct KombatHUDView: View {
    @ObservedObject var hud: KombatHUD
    let input: InputState
    let onPause: () -> Void

    init(hud: KombatHUD, input: InputState, onPause: @escaping () -> Void) {
        self.hud = hud
        self.input = input
        self.onPause = onPause
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.4, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                LetterboxBars(visible: hud.cinematic)
                if !hud.cinematic {
                    topBar(scale: s)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .frame(maxHeight: .infinity, alignment: .top)
                }
                bannerView(scale: s)
                comboView(scale: s)
                if hud.controlsEnabled && !hud.cinematic && !hud.matchOver {
                    controls(scale: s, size: geo.size)
                }
                if hud.showExecutePrompt {
                    executeButton(scale: s)
                }
                Color(uiColor: hud.flashColor)
                    .opacity(hud.flashOpacity)
                    .ignoresSafeArea()
                    .allowsHitTesting(false)
            }
        }
    }

    private func topBar(scale s: CGFloat) -> some View {
        HStack(alignment: .top, spacing: 10 * s) {
            fighterBar(name: hud.p1Name, health: hud.p1Health, lag: hud.p1HealthLag, meter: hud.p1Meter,
                       rounds: hud.p1Rounds, mirrored: false, scale: s)
            VStack(spacing: 4) {
                Text("\(hud.timer)")
                    .font(Theme.mono(30 * s))
                    .foregroundColor(hud.timer <= 10 ? Theme.bloodBright : .white)
                    .glowText(Theme.blood)
                    .frame(width: 70 * s, height: 50 * s)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.6)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.gold.opacity(0.7), lineWidth: 1.5))
                PauseButton(action: onPause)
                    .scaleEffect(0.85)
            }
            fighterBar(name: hud.p2Name, health: hud.p2Health, lag: hud.p2HealthLag, meter: hud.p2Meter,
                       rounds: hud.p2Rounds, mirrored: true, scale: s)
        }
    }

    private func fighterBar(name: String, health: Float, lag: Float, meter: Float, rounds: Int, mirrored: Bool, scale s: CGFloat) -> some View {
        VStack(alignment: mirrored ? .trailing : .leading, spacing: 4 * s) {
            GeometryReader { g in
                let w = g.size.width
                ZStack(alignment: mirrored ? .trailing : .leading) {
                    Rectangle().fill(Color.black.opacity(0.65))
                    Rectangle().fill(Theme.bloodBright.opacity(0.85))
                        .frame(width: w * CGFloat(lag))
                    Rectangle()
                        .fill(LinearGradient(colors: [Theme.gold, Color(red: 0.95, green: 0.45, blue: 0.1)],
                                             startPoint: .top, endPoint: .bottom))
                        .frame(width: w * CGFloat(health))
                }
                .overlay(Rectangle().stroke(Color.white.opacity(0.6), lineWidth: 1.5))
                .animation(.linear(duration: 0.08), value: health)
            }
            .frame(height: 22 * s)
            HStack(spacing: 6) {
                if mirrored { roundDots(rounds, scale: s) }
                Text(name)
                    .font(Theme.title(15 * s))
                    .foregroundColor(.white)
                    .glowText(Theme.blood, radius: 4)
                if !mirrored { roundDots(rounds, scale: s) }
            }
            GeometryReader { g in
                ZStack(alignment: mirrored ? .trailing : .leading) {
                    Capsule().fill(Color.black.opacity(0.55))
                    Capsule()
                        .fill(meter >= 1 ? Theme.violet : Theme.cyan.opacity(0.8))
                        .frame(width: g.size.width * CGFloat(Swift.min(1, meter)))
                }
            }
            .frame(width: 180 * s, height: 7 * s)
            if meter >= 1 && !mirrored {
                Text("BRUTAL BEREIT")
                    .font(Theme.title(10 * s))
                    .foregroundColor(Theme.violet)
                    .glowText(Theme.violet, radius: 6)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func roundDots(_ won: Int, scale s: CGFloat) -> some View {
        HStack(spacing: 4) {
            ForEach(0..<Swift.max(1, hud.roundsToWin), id: \.self) { i in
                Image(systemName: i < won ? "drop.fill" : "drop")
                    .font(.system(size: 12 * s, weight: .bold))
                    .foregroundColor(i < won ? Theme.bloodBright : Color.white.opacity(0.5))
            }
        }
    }

    @ViewBuilder
    private func bannerView(scale s: CGFloat) -> some View {
        if let b = hud.banner {
            Text(b)
                .font(Theme.title(bannerSize(hud.bannerStyle) * s))
                .foregroundColor(bannerColor(hud.bannerStyle))
                .multilineTextAlignment(.center)
                .glowText(hud.bannerStyle == .fight || hud.bannerStyle == .round ? Theme.gold : Theme.blood, radius: 14)
                .minimumScaleFactor(0.4)
                .lineLimit(2)
                .padding(.horizontal, 30)
                .transition(.scale(scale: 2.2).combined(with: .opacity))
                .id(b)
                .allowsHitTesting(false)
        }
    }

    private func bannerSize(_ style: BannerStyle) -> CGFloat {
        switch style {
        case .round, .fight: return 72
        case .finish, .execution: return 78
        case .brutal: return 54
        case .victory, .defeat: return 60
        case .info: return 34
        }
    }

    private func bannerColor(_ style: BannerStyle) -> Color {
        switch style {
        case .round, .fight, .victory: return Theme.gold
        case .finish, .execution, .defeat: return Theme.bloodBright
        case .brutal: return Theme.violet
        case .info: return .white
        }
    }

    @ViewBuilder
    private func comboView(scale s: CGFloat) -> some View {
        if let c = hud.comboText {
            Text(c)
                .font(Theme.title(26 * s))
                .foregroundColor(.white)
                .glowText(Theme.bloodBright, radius: 10)
                .rotationEffect(.degrees(-6))
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .padding(.leading, 30)
                .padding(.bottom, 80)
                .transition(.move(edge: .leading).combined(with: .opacity))
                .id(c)
                .allowsHitTesting(false)
        }
    }

    private func controls(scale s: CGFloat, size: CGSize) -> some View {
        let b = 66 * s
        return ZStack {
            HStack(spacing: 0) {
                VirtualJoystick(input: input, radius: 58 * s)
                    .frame(width: size.width * 0.42)
                Spacer()
            }
            VStack(spacing: 10 * s) {
                HStack(spacing: 10 * s) {
                    ActionButton(title: hud.special1Name, icon: "sparkles", button: .special1, input: input,
                                 size: b * 0.85, color: Theme.violet, enabled: hud.special1Ready)
                    ActionButton(title: hud.special2Name, icon: "bolt.fill", button: .special2, input: input,
                                 size: b * 0.85, color: Theme.violet, enabled: hud.special2Ready)
                    if hud.canBrutal {
                        ActionButton(title: "BRUTAL", icon: "flame.fill", button: .brutal, input: input,
                                     size: b * 0.95, color: Theme.bloodBright)
                    }
                }
                HStack(spacing: 10 * s) {
                    ActionButton(title: "BLOCK", icon: "shield.fill", button: .block, input: input, size: b, color: Color.gray)
                    ActionButton(title: "SCHLAG", icon: "hand.raised.fill", button: .punch, input: input, size: b * 1.1)
                    ActionButton(title: "TRITT", icon: "figure.kickboxing", button: .kick, input: input, size: b * 1.1)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            .padding(.trailing, 20)
            .padding(.bottom, 18)
        }
    }

    private func executeButton(scale s: CGFloat) -> some View {
        VStack {
            Spacer()
            ZStack {
                Circle()
                    .trim(from: 0, to: CGFloat(Swift.max(0, Swift.min(1, hud.executeTimeLeft / 6))))
                    .stroke(Theme.bloodBright, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 150 * s, height: 150 * s)
                ActionButton(title: "EXEKUTION", icon: "drop.triangle.fill", button: .execute, input: input,
                             size: 128 * s, color: Theme.blood)
            }
            .padding(.bottom, 30)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.trailing, 40)
    }
}

// MARK: - Welt-HUD

struct WorldHUDView: View {
    @ObservedObject var hud: WorldHUD
    let input: InputState
    let onPause: () -> Void

    init(hud: WorldHUD, input: InputState, onPause: @escaping () -> Void) {
        self.hud = hud
        self.input = input
        self.onPause = onPause
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.35, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                HStack(spacing: 0) {
                    VirtualJoystick(input: input, radius: 58 * s)
                        .frame(width: geo.size.width * 0.42)
                    Spacer()
                }
                VStack(alignment: .leading, spacing: 8) {
                    objectivePanel(scale: s)
                    healthBar(scale: s)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(.leading, 18)
                .padding(.top, 10)
                minimap(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                    .padding(.trailing, 18)
                    .padding(.top, 10)
                centerInfo(scale: s)
                speedReadout(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                    .padding(.leading, 24)
                    .padding(.bottom, 170 * s)
                buttons(scale: s)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(.trailing, 20)
                    .padding(.bottom, 18)
                PauseButton(action: onPause)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    .padding(.top, 10)
            }
        }
    }

    private func objectivePanel(scale s: CGFloat) -> some View {
        HStack(spacing: 10) {
            if hud.objectiveDistance != nil {
                Image(systemName: "location.north.fill")
                    .font(.system(size: 22 * s, weight: .bold))
                    .foregroundColor(Theme.bloodBright)
                    .rotationEffect(.radians(Double(hud.objectiveArrowAngle)))
                    .glowText(Theme.blood, radius: 6)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(hud.objective)
                    .font(Theme.body(13 * s))
                    .foregroundColor(.white)
                    .lineLimit(2)
                if let d = hud.objectiveDistance {
                    Text("\(Int(d)) m")
                        .font(Theme.mono(12 * s))
                        .foregroundColor(Theme.gold)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: 330 * s, alignment: .leading)
        .glassPanel()
    }

    private func healthBar(scale s: CGFloat) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "heart.fill").foregroundColor(Theme.bloodBright)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.black.opacity(0.6))
                    Capsule().fill(Theme.bloodBright).frame(width: g.size.width * CGFloat(hud.health))
                }
            }
            .frame(width: 150 * s, height: 9 * s)
            Image(systemName: "diamond.fill").foregroundColor(Theme.bloodBright).font(.system(size: 12 * s))
            Text("\(hud.collectibles)/\(hud.collectiblesTotal)")
                .font(Theme.mono(12 * s))
                .foregroundColor(.white)
        }
    }

    private func minimap(scale s: CGFloat) -> some View {
        let size = 120 * s
        return ZStack {
            Circle().fill(Color.black.opacity(0.55))
            Circle().stroke(Theme.blood.opacity(0.8), lineWidth: 2)
            if let o = hud.minimapObjective {
                Circle()
                    .fill(Theme.bloodBright)
                    .frame(width: 10, height: 10)
                    .position(x: CGFloat(o.x) * size, y: CGFloat(o.y) * size)
                    .glowText(Theme.bloodBright, radius: 5)
            }
            Image(systemName: "location.north.fill")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(Theme.gold)
                .rotationEffect(.radians(Double(-hud.minimapHeroHeading) + Double.pi))
                .position(x: CGFloat(hud.minimapHero.x) * size, y: CGFloat(hud.minimapHero.y) * size)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }

    @ViewBuilder
    private func centerInfo(scale s: CGFloat) -> some View {
        VStack(spacing: 10) {
            if let t = hud.toast {
                Text(t)
                    .font(Theme.title(20 * s))
                    .foregroundColor(.white)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 8)
                    .glassPanel()
                    .transition(.opacity)
            }
            if hud.combo >= 2 {
                Text("\(hud.combo)× KOMBO")
                    .font(Theme.title(24 * s))
                    .foregroundColor(Theme.gold)
                    .glowText(Theme.blood)
            }
            Spacer()
            if let p = hud.interactPrompt {
                Button {
                    input.press(.interact)
                    input.release(.interact)
                    Haptics.medium()
                } label: {
                    Text(p)
                        .font(Theme.title(20 * s))
                        .foregroundColor(.white)
                        .padding(.horizontal, 26)
                        .padding(.vertical, 12)
                        .background(Capsule().fill(Theme.blood))
                        .overlay(Capsule().stroke(Color.white.opacity(0.8), lineWidth: 2))
                        .glowText(Theme.bloodBright, radius: 10)
                }
                .padding(.bottom, 40)
            }
        }
        .padding(.top, 70)
        .animation(.easeInOut(duration: 0.25), value: hud.toast)
    }

    private func speedReadout(scale s: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(hud.speedKmh)")
                .font(Theme.mono(30 * s))
                .foregroundColor(hud.speedKmh > 90 ? Theme.gold : .white)
                .glowText(hud.speedKmh > 90 ? Theme.bloodBright : .clear, radius: 8)
            Text("KM/H")
                .font(Theme.title(10 * s))
                .foregroundColor(.white.opacity(0.7))
        }
        .allowsHitTesting(false)
    }

    private func buttons(scale s: CGFloat) -> some View {
        let b = 64 * s
        return VStack(alignment: .trailing, spacing: 10 * s) {
            HStack(spacing: 10 * s) {
                ActionButton(title: "ZIP", icon: "arrow.up.right", button: .zip, input: input, size: b * 0.85, color: Theme.violet)
                ActionButton(title: "ANGRIFF", icon: "hand.raised.fill", button: .attack, input: input, size: b, color: Color.gray)
            }
            HStack(spacing: 10 * s) {
                ActionButton(title: "SPRUNG", icon: "arrow.up", button: .jump, input: input, size: b)
                ActionButton(title: "NETZ", icon: "scribble.variable", button: .web, input: input, size: b * 1.35,
                             color: hud.isSwinging ? Theme.bloodBright : Theme.blood)
            }
        }
    }
}

// MARK: - Cutscene-Overlay

struct CutsceneOverlayView: View {
    @ObservedObject var hud: CutsceneHUD
    let onSkip: () -> Void

    init(hud: CutsceneHUD, onSkip: @escaping () -> Void) {
        self.hud = hud
        self.onSkip = onSkip
    }

    var body: some View {
        GeometryReader { geo in
            let s = Swift.min(1.4, Swift.max(0.75, geo.size.width / 900))
            ZStack {
                LetterboxBars(visible: hud.letterbox)
                VStack(spacing: 6) {
                    Spacer()
                    if let line = hud.line {
                        VStack(spacing: 4) {
                            if let sp = hud.speaker {
                                Text(sp)
                                    .font(Theme.title(14 * s))
                                    .foregroundColor(Theme.bloodBright)
                                    .tracking(2)
                            }
                            Text(line)
                                .font(Theme.body(19 * s))
                                .foregroundColor(.white)
                                .multilineTextAlignment(.center)
                                .shadow(color: .black, radius: 4, x: 0, y: 2)
                        }
                        .padding(.horizontal, 60)
                        .id(line)
                        .transition(.opacity)
                    }
                }
                .padding(.bottom, geo.size.height * 0.035)
                .animation(.easeInOut(duration: 0.25), value: hud.line)
                if let t = hud.title {
                    Text(t)
                        .font(Theme.title(40 * s))
                        .tracking(8)
                        .foregroundColor(.white)
                        .glowText(Theme.blood, radius: 16)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                        .transition(.opacity)
                }
                Color.black.opacity(hud.fadeOpacity).ignoresSafeArea().allowsHitTesting(false)
                Color(uiColor: hud.flashColor).opacity(hud.flashOpacity).ignoresSafeArea().allowsHitTesting(false)
                Button(action: onSkip) {
                    HStack(spacing: 6) {
                        Text("Überspringen")
                        Image(systemName: "forward.end.fill")
                    }
                    .font(Theme.body(13))
                    .foregroundColor(.white.opacity(0.8))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(Capsule().fill(Color.black.opacity(0.4)))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                .padding(.top, 14)
                .padding(.trailing, 18)
            }
            .animation(.easeInOut(duration: 0.6), value: hud.title)
        }
    }
}
