import Foundation
import UIKit
import SceneKit
import QuartzCore
import simd

// =====================================================================
//  SILKSTRIKE – Effekte
//  Partikel (Blut, Funken, Feuer, Rauch, Eis, Blitze …), Blutlachen,
//  Netzfäden, Kamerawackeln, Geschoss-Optik und Rissportale.
//
//  Alle Partikelbilder werden HIER prozedural erzeugt (keine Assets).
//  HDR-Regeln: Blut = dunkles, glänzendes Rot (Alpha-Blend), Feuer /
//  Funken / Glühen / Strom / Riss = additiv mit particleIntensity > 1
//  (damit Bloom greift), Rauch / Staub / Asche = Alpha-Blend.
// =====================================================================

// MARK: - Deterministischer Zufall für die Sprite-Erzeugung

fileprivate struct FXSpriteRNG {
    private var state: UInt64

    init(_ seed: UInt64) {
        state = seed &* 0x9E3779B97F4A7C15 &+ 0x632BE59BD9B4E019
    }

    mutating func next() -> CGFloat {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        let bits = (state >> 40) & 0xFFFFFF
        return CGFloat(bits) / CGFloat(0xFFFFFF)
    }

    mutating func range(_ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
        return lo + (hi - lo) * next()
    }
}

// MARK: - Sprite-Bank (prozedurale Partikelbilder, gecacht)

fileprivate enum FXSpriteBank {
    static var cache: [String: UIImage] = [:]

    // ---------- Farb-Helfer ----------

    static func components(_ c: UIColor) -> (r: CGFloat, g: CGFloat, b: CGFloat, a: CGFloat) {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 1
        if c.getRed(&r, green: &g, blue: &b, alpha: &a) {
            return (FXSpriteBank.clamp01(r), FXSpriteBank.clamp01(g), FXSpriteBank.clamp01(b), FXSpriteBank.clamp01(a))
        }
        var w: CGFloat = 0
        if c.getWhite(&w, alpha: &a) {
            let ww = FXSpriteBank.clamp01(w)
            return (ww, ww, ww, FXSpriteBank.clamp01(a))
        }
        return (1, 1, 1, 1)
    }

    static func clamp01(_ v: CGFloat) -> CGFloat {
        if !v.isFinite { return 0 }
        return Swift.min(1, Swift.max(0, v))
    }

    static func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> UIColor {
        return UIColor(red: r, green: g, blue: b, alpha: a)
    }

    static func white(_ a: CGFloat) -> UIColor {
        return UIColor(red: 1, green: 1, blue: 1, alpha: a)
    }

    static func key(_ c: UIColor) -> String {
        let k = FXSpriteBank.components(c)
        return "\(Int(k.r * 255))_\(Int(k.g * 255))_\(Int(k.b * 255))"
    }

    static func mix(_ a: UIColor, _ b: UIColor, _ t: CGFloat) -> UIColor {
        let k = FXSpriteBank.clamp01(t)
        let c0 = FXSpriteBank.components(a)
        let c1 = FXSpriteBank.components(b)
        return UIColor(red: c0.r + (c1.r - c0.r) * k,
                       green: c0.g + (c1.g - c0.g) * k,
                       blue: c0.b + (c1.b - c0.b) * k,
                       alpha: c0.a + (c1.a - c0.a) * k)
    }

    /// RGB mit k multiplizieren, Alpha setzen.
    static func scaled(_ c: UIColor, _ k: CGFloat, alpha: CGFloat) -> UIColor {
        let v = FXSpriteBank.components(c)
        return UIColor(red: FXSpriteBank.clamp01(v.r * k),
                       green: FXSpriteBank.clamp01(v.g * k),
                       blue: FXSpriteBank.clamp01(v.b * k),
                       alpha: FXSpriteBank.clamp01(alpha))
    }

    static func luminance(_ c: UIColor) -> CGFloat {
        let v = FXSpriteBank.components(c)
        return 0.2126 * v.r + 0.7152 * v.g + 0.0722 * v.b
    }

    /// Feuerfarben (rot/orange/gelb) → klassische Flammenpalette verwenden.
    static func isWarm(_ c: UIColor) -> Bool {
        let v = FXSpriteBank.components(c)
        return v.r > 0.55 && v.r > v.b * 1.4 && v.g <= v.r
    }

    // ---------- Zeichen-Helfer ----------

    static func renderer(_ size: CGFloat) -> UIGraphicsImageRenderer {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        return UIGraphicsImageRenderer(size: CGSize(width: size, height: size), format: format)
    }

    static func radial(_ cg: CGContext, _ center: CGPoint, _ radius: CGFloat, _ colors: [UIColor], _ locations: [CGFloat]) {
        guard radius > 0, colors.count >= 2, colors.count == locations.count else { return }
        let cgColors: [CGColor] = colors.map { $0.cgColor }
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                        colors: cgColors as CFArray,
                                        locations: locations) else { return }
        cg.drawRadialGradient(gradient, startCenter: center, startRadius: 0,
                              endCenter: center, endRadius: radius, options: [])
    }

    // ---------- Basis-Sprites (weiß, werden per particleColor eingefärbt) ----------

    /// Weiches Glühen (Feuer-Kern, Treffer, Halos).
    static var glow: UIImage {
        if let c = cache["glow"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(1), FXSpriteBank.white(0.62), FXSpriteBank.white(0.2),
                                 FXSpriteBank.white(0.05), FXSpriteBank.white(0)],
                                [0, 0.16, 0.42, 0.72, 1])
        }
        cache["glow"] = img
        return img
    }

    /// Kleiner, harter Leuchtpunkt (Funken, Glut, Regen – wird per stretchFactor gestreckt).
    static var spark: UIImage {
        if let c = cache["spark"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let s: CGFloat = 64
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(1), FXSpriteBank.white(1), FXSpriteBank.white(0.35), FXSpriteBank.white(0)],
                                [0, 0.18, 0.45, 1])
        }
        cache["spark"] = img
        return img
    }

    /// Wolkige Rauchpuste.
    static var smoke: UIImage {
        if let c = cache["smoke"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(11)
            FXSpriteBank.radial(cg, CGPoint(x: s / 2, y: s / 2), s * 0.42,
                                [FXSpriteBank.white(0.35), FXSpriteBank.white(0.15), FXSpriteBank.white(0)],
                                [0, 0.5, 1])
            for _ in 0..<16 {
                let r = s * rng.range(0.12, 0.22)
                let maxOff = Swift.max(0, s * 0.47 - r)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = rng.range(0, maxOff * 0.75)
                let p = CGPoint(x: s / 2 + cos(a) * d, y: s / 2 + sin(a) * d)
                FXSpriteBank.radial(cg, p, r,
                                    [FXSpriteBank.white(0.24), FXSpriteBank.white(0.12), FXSpriteBank.white(0)],
                                    [0, 0.5, 1])
            }
        }
        cache["smoke"] = img
        return img
    }

    /// Flammenzunge: heller Kern + unruhige Ränder.
    static var fire: UIImage {
        if let c = cache["fire"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(29)
            for _ in 0..<12 {
                let r = s * rng.range(0.1, 0.2)
                let maxOff = Swift.max(0, s * 0.46 - r)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = rng.range(0, maxOff * 0.7)
                let p = CGPoint(x: s / 2 + cos(a) * d, y: s / 2 + sin(a) * d)
                FXSpriteBank.radial(cg, p, r,
                                    [FXSpriteBank.white(0.4), FXSpriteBank.white(0.18), FXSpriteBank.white(0)],
                                    [0, 0.45, 1])
            }
            FXSpriteBank.radial(cg, CGPoint(x: s / 2, y: s / 2), s * 0.3,
                                [FXSpriteBank.white(0.95), FXSpriteBank.white(0.45), FXSpriteBank.white(0)],
                                [0, 0.4, 1])
        }
        cache["fire"] = img
        return img
    }

    /// Bluttropfen mit eingebackenem dunklem Rot + kleinem Glanzlicht (particleColor = weiß).
    static var bloodDrop: UIImage {
        if let c = cache["bloodDrop"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let c = CGPoint(x: s / 2, y: s / 2)
            FXSpriteBank.radial(cg, c, s * 0.44,
                                [FXSpriteBank.rgb(0.40, 0.018, 0.026, 1),
                                 FXSpriteBank.rgb(0.30, 0.010, 0.018, 1),
                                 FXSpriteBank.rgb(0.17, 0.004, 0.010, 0.92),
                                 FXSpriteBank.rgb(0.10, 0.0, 0.004, 0)],
                                [0, 0.55, 0.82, 1])
            FXSpriteBank.radial(cg, CGPoint(x: s * 0.41, y: s * 0.38), s * 0.11,
                                [FXSpriteBank.rgb(1.0, 0.72, 0.70, 0.7), FXSpriteBank.rgb(0.7, 0.2, 0.2, 0)],
                                [0, 1])
        }
        cache["bloodDrop"] = img
        return img
    }

    /// Wie bloodDrop, aber graustufig (für eingefärbtes Blut, z.B. schwarzes Ranken-Blut).
    static var grayDrop: UIImage {
        if let c = cache["grayDrop"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let c = CGPoint(x: s / 2, y: s / 2)
            FXSpriteBank.radial(cg, c, s * 0.44,
                                [FXSpriteBank.white(1), FXSpriteBank.rgb(0.75, 0.75, 0.75, 1),
                                 FXSpriteBank.rgb(0.45, 0.45, 0.45, 0.92), FXSpriteBank.rgb(0.3, 0.3, 0.3, 0)],
                                [0, 0.55, 0.82, 1])
            FXSpriteBank.radial(cg, CGPoint(x: s * 0.41, y: s * 0.38), s * 0.11,
                                [FXSpriteBank.white(0.8), FXSpriteBank.white(0)],
                                [0, 1])
        }
        cache["grayDrop"] = img
        return img
    }

    /// Eissplitter mit heller Kante.
    static var shard: UIImage {
        if let c = cache["shard"] { return c }
        let img = FXSpriteBank.renderer(64).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 64
            let path = CGMutablePath()
            path.move(to: CGPoint(x: s * 0.50, y: s * 0.04))
            path.addLine(to: CGPoint(x: s * 0.70, y: s * 0.40))
            path.addLine(to: CGPoint(x: s * 0.58, y: s * 0.96))
            path.addLine(to: CGPoint(x: s * 0.33, y: s * 0.56))
            path.closeSubpath()
            cg.addPath(path)
            cg.setFillColor(FXSpriteBank.white(0.55).cgColor)
            cg.fillPath()
            let facet = CGMutablePath()
            facet.move(to: CGPoint(x: s * 0.50, y: s * 0.04))
            facet.addLine(to: CGPoint(x: s * 0.70, y: s * 0.40))
            facet.addLine(to: CGPoint(x: s * 0.52, y: s * 0.52))
            facet.closeSubpath()
            cg.addPath(facet)
            cg.setFillColor(FXSpriteBank.white(0.85).cgColor)
            cg.fillPath()
            cg.addPath(path)
            cg.setStrokeColor(FXSpriteBank.white(1).cgColor)
            cg.setLineWidth(1.5)
            cg.setLineJoin(.round)
            cg.strokePath()
        }
        cache["shard"] = img
        return img
    }

    /// Gezackter Blitz mit Seitenarm und Glühen.
    static var bolt: UIImage {
        if let c = cache["bolt"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            var rng = FXSpriteRNG(5)
            var main: [CGPoint] = []
            var x = s * 0.5
            for i in 0...11 {
                let y = s * 0.05 + CGFloat(i) / 11 * s * 0.9
                main.append(CGPoint(x: x, y: y))
                x = Swift.min(Swift.max(x + rng.range(-s * 0.1, s * 0.1), s * 0.18), s * 0.82)
            }
            var branch: [CGPoint] = []
            if main.count > 5 {
                var bp = main[4]
                branch.append(bp)
                for _ in 0..<5 {
                    bp = CGPoint(x: Swift.min(Swift.max(bp.x + rng.range(s * 0.02, s * 0.08), s * 0.1), s * 0.9),
                                 y: Swift.min(bp.y + rng.range(s * 0.04, s * 0.08), s * 0.94))
                    branch.append(bp)
                }
            }
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            // Glühen
            cg.setShadow(offset: .zero, blur: 7, color: FXSpriteBank.white(0.9).cgColor)
            cg.setStrokeColor(FXSpriteBank.white(0.75).cgColor)
            cg.setLineWidth(3.2)
            cg.addLines(between: main)
            cg.strokePath()
            if branch.count > 1 {
                cg.setLineWidth(2.0)
                cg.addLines(between: branch)
                cg.strokePath()
            }
            // heißer Kern
            cg.setShadow(offset: .zero, blur: 0, color: nil)
            cg.setStrokeColor(FXSpriteBank.white(1).cgColor)
            cg.setLineWidth(1.3)
            cg.addLines(between: main)
            cg.strokePath()
            if branch.count > 1 {
                cg.setLineWidth(0.9)
                cg.addLines(between: branch)
                cg.strokePath()
            }
        }
        cache["bolt"] = img
        return img
    }

    /// Ring (Schockwelle).
    static var ring: UIImage {
        if let c = cache["ring"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.white(0), FXSpriteBank.white(0), FXSpriteBank.white(0.95),
                                 FXSpriteBank.white(0.3), FXSpriteBank.white(0)],
                                [0, 0.6, 0.8, 0.88, 1])
        }
        cache["ring"] = img
        return img
    }

    /// Netz-Spinnennetz (Netz trifft).
    static var web: UIImage {
        if let c = cache["web"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 128
            let c = CGPoint(x: s / 2, y: s / 2)
            var rng = FXSpriteRNG(91)
            let spokes = 9
            var angles: [CGFloat] = []
            for i in 0..<spokes {
                angles.append(CGFloat(i) / CGFloat(spokes) * CGFloat.pi * 2 + rng.range(-0.15, 0.15))
            }
            cg.setLineCap(.round)
            cg.setLineJoin(.round)
            cg.setShadow(offset: .zero, blur: 2, color: FXSpriteBank.white(0.8).cgColor)
            cg.setStrokeColor(FXSpriteBank.white(0.95).cgColor)
            cg.setLineWidth(1.7)
            for a in angles {
                cg.move(to: c)
                cg.addLine(to: CGPoint(x: c.x + cos(a) * s * 0.47, y: c.y + sin(a) * s * 0.47))
            }
            cg.strokePath()
            cg.setLineWidth(1.15)
            for ringIndex in 1...4 {
                let rr = s * 0.47 * CGFloat(ringIndex) / 4.6
                for (i, a) in angles.enumerated() {
                    let rj = rr * rng.range(0.88, 1.04)
                    let p = CGPoint(x: c.x + cos(a) * rj, y: c.y + sin(a) * rj)
                    if i == 0 { cg.move(to: p) } else { cg.addLine(to: p) }
                }
                cg.closePath()
            }
            cg.strokePath()
            // Außen weich ausblenden
            cg.setShadow(offset: .zero, blur: 0, color: nil)
            cg.setBlendMode(.destinationIn)
            FXSpriteBank.radial(cg, c, s * 0.5,
                                [FXSpriteBank.white(1), FXSpriteBank.white(1), FXSpriteBank.white(0)],
                                [0, 0.62, 1])
            cg.setBlendMode(.normal)
        }
        cache["web"] = img
        return img
    }

    /// Unregelmäßige Ascheflocke / Splitter.
    static var flake: UIImage {
        if let c = cache["flake"] { return c }
        let img = FXSpriteBank.renderer(32).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 32
            var rng = FXSpriteRNG(23)
            let path = CGMutablePath()
            let n = 7
            for i in 0..<n {
                let a = CGFloat(i) / CGFloat(n) * CGFloat.pi * 2
                let r = s * rng.range(0.2, 0.46)
                let p = CGPoint(x: s / 2 + cos(a) * r, y: s / 2 + sin(a) * r)
                if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
            cg.addPath(path)
            cg.setFillColor(FXSpriteBank.white(0.9).cgColor)
            cg.fillPath()
        }
        cache["flake"] = img
        return img
    }

    /// Schwarze Leere im Rissportal (Alpha-Blend).
    static var voidDisc: UIImage {
        if let c = cache["voidDisc"] { return c }
        let img = FXSpriteBank.renderer(128).image { ctx in
            let s: CGFloat = 128
            FXSpriteBank.radial(ctx.cgContext, CGPoint(x: s / 2, y: s / 2), s / 2,
                                [FXSpriteBank.rgb(0, 0, 0, 0.97), FXSpriteBank.rgb(0, 0, 0, 0.9),
                                 FXSpriteBank.rgb(0, 0, 0, 0.45), FXSpriteBank.rgb(0, 0, 0, 0)],
                                [0, 0.45, 0.72, 1])
        }
        cache["voidDisc"] = img
        return img
    }

    // ---------- Eingefärbte Sprites ----------

    /// Färbt ein weißes Sprite ein (Alpha bleibt). Für additive Billboards/Halos.
    static func tinted(_ base: UIImage, baseKey: String, color: UIColor) -> UIImage {
        let k = baseKey + "#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let size = Swift.max(1, base.size.width)
        let v = FXSpriteBank.components(color)
        let opaque = UIColor(red: v.r, green: v.g, blue: v.b, alpha: 1)
        let img = FXSpriteBank.renderer(size).image { ctx in
            let rect = CGRect(x: 0, y: 0, width: size, height: size)
            base.draw(in: rect)
            ctx.cgContext.setBlendMode(.sourceIn)
            ctx.cgContext.setFillColor(opaque.cgColor)
            ctx.cgContext.fill(rect)
        }
        cache[k] = img
        return img
    }

    /// Blutlachen-Textur: Hauptlache + Ausläufer + Spritzer, Mitte dunkler (dickeres Blut).
    static func splat(_ color: UIColor) -> UIImage {
        let k = "splat#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let v = FXSpriteBank.components(color)
        let img = FXSpriteBank.renderer(256).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 256
            let c = CGPoint(x: s / 2, y: s / 2)
            var rng = FXSpriteRNG(4242)
            cg.setFillColor(FXSpriteBank.rgb(v.r, v.g, v.b, 1).cgColor)
            // Hauptkörper
            for _ in 0..<10 {
                let r = s * rng.range(0.11, 0.19)
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0, 0.11)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
            }
            // Ausläufer mit "Hals"
            for _ in 0..<8 {
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0.2, 0.31)
                let r = s * rng.range(0.035, 0.075)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
                let d2 = d * 0.62
                let r2 = r * 0.8
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d2 - r2, y: c.y + sin(a) * d2 - r2, width: r2 * 2, height: r2 * 2))
            }
            // Spritzer
            for _ in 0..<22 {
                let a = rng.range(0, CGFloat.pi * 2)
                let d = s * rng.range(0.32, 0.45)
                let r = s * rng.range(0.005, 0.02)
                cg.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
            }
            // dunklere, dickere Mitte – nur auf bereits gefüllte Pixel
            cg.setBlendMode(.sourceAtop)
            FXSpriteBank.radial(cg, c, s * 0.34,
                                [FXSpriteBank.rgb(v.r * 0.5, v.g * 0.4, v.b * 0.5, 0.85),
                                 FXSpriteBank.rgb(v.r * 0.7, v.g * 0.6, v.b * 0.7, 0.4),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.55, 1])
            cg.setBlendMode(.normal)
        }
        cache[k] = img
        return img
    }

    /// Spiralarme für das Rissportal (eingebacken in der Portalfarbe, additiv).
    static func swirl(_ color: UIColor) -> UIImage {
        let k = "swirl#" + FXSpriteBank.key(color)
        if let c = cache[k] { return c }
        let v = FXSpriteBank.components(color)
        let hot = FXSpriteBank.components(FXSpriteBank.mix(color, .white, 0.6))
        let img = FXSpriteBank.renderer(256).image { ctx in
            let cg = ctx.cgContext
            let s: CGFloat = 256
            let c = CGPoint(x: s / 2, y: s / 2)
            let arms = 5
            for arm in 0..<arms {
                let offset = CGFloat(arm) / CGFloat(arms) * CGFloat.pi * 2
                for k in 0..<80 {
                    let t = CGFloat(k) / 80
                    let ang = offset + t * CGFloat.pi * 2.4
                    let rad = s * 0.43 * (1 - t * 0.88)
                    let p = CGPoint(x: c.x + cos(ang) * rad, y: c.y + sin(ang) * rad)
                    let dotR = s * (0.018 + 0.035 * (1 - t))
                    let alpha = 0.06 + 0.22 * t
                    FXSpriteBank.radial(cg, p, dotR,
                                        [FXSpriteBank.rgb(v.r, v.g, v.b, alpha), FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                        [0, 1])
                }
            }
            // Randglühen
            FXSpriteBank.radial(cg, c, s * 0.5,
                                [FXSpriteBank.rgb(v.r, v.g, v.b, 0), FXSpriteBank.rgb(v.r, v.g, v.b, 0),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0.55), FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.72, 0.86, 1])
            // heißer Kern
            FXSpriteBank.radial(cg, c, s * 0.16,
                                [FXSpriteBank.rgb(hot.r, hot.g, hot.b, 0.9), FXSpriteBank.rgb(v.r, v.g, v.b, 0.4),
                                 FXSpriteBank.rgb(v.r, v.g, v.b, 0)],
                                [0, 0.45, 1])
        }
        cache[k] = img
        return img
    }
}

// MARK: - FX

enum FX {
    /// Einmal vom Spiel gesetzt; skaliert Partikelanzahlen (Leistung 0.4x, Ausgewogen 0.7x, Ultra 1x).
    static var quality: QualityPreset = .balanced {
        didSet { FX.prewarm() }
    }
    /// false: Blut wird zu dunklem Staub/Funken, keine Lachen.
    static var bloodEnabled: Bool = true

    /// Name aller kurzlebigen FX-Knoten (direkte Kinder von scene.rootNode) – für cleanup(in:).
    static let transientNodeName = "silkFX.transient"

    private static var livePools: [SCNNode] = []
    private static var liveLights: [SCNNode] = []
    private static var spriteMaterialCache: [String: SCNMaterial] = [:]
    private static var poolMaterialCache: [String: SCNMaterial] = [:]
    private static let maxLivePools = 24

    private static let bloodPoolColor = UIColor(red: 0.30, green: 0.012, blue: 0.02, alpha: 1)
    private static let bloodMistColor = UIColor(red: 0.22, green: 0.006, blue: 0.012, alpha: 0.6)
    private static let defaultRiftColor = UIColor(red: 0.62, green: 0.16, blue: 1.0, alpha: 1)

    // MARK: Öffentliche API

    /// Erzeugt alle Partikelbilder vorab (verhindert Ruckler beim ersten Treffer). Optional.
    static func prewarm() {
        _ = FXSpriteBank.glow
        _ = FXSpriteBank.spark
        _ = FXSpriteBank.smoke
        _ = FXSpriteBank.fire
        _ = FXSpriteBank.bloodDrop
        _ = FXSpriteBank.grayDrop
        _ = FXSpriteBank.shard
        _ = FXSpriteBank.bolt
        _ = FXSpriteBank.ring
        _ = FXSpriteBank.web
        _ = FXSpriteBank.flake
        _ = FXSpriteBank.voidDisc
        _ = FXSpriteBank.splat(FX.bloodPoolColor)
    }

    static func spawn(_ kind: EffectKind, at position: SIMD3<Float>, in scene: SCNScene,
                      direction: SIMD3<Float> = SIMD3<Float>(0, 1, 0), scale: Float = 1, color: UIColor? = nil) {
        guard FX.isFinite3(position) else { return }
        let dir = FX.safeDirection(direction)
        var s = scale
        if !s.isFinite || s <= 0 { s = 1 }
        s = Swift.min(Swift.max(s, 0.05), 8)

        switch kind {
        case .bloodSpray:
            if bloodEnabled {
                spawnBloodSpray(position, dir, s, color, scene)
            } else {
                spawnBloodless(position, dir, s, scene)
            }
        case .bloodBurst:
            if bloodEnabled {
                spawnBloodBurst(position, s, color, scene)
            } else {
                spawnBloodless(position, dir, s * 1.3, scene)
            }
        case .bloodPool:
            if bloodEnabled {
                spawnBloodPool(position, s, color, scene)
            }
        case .sparks:
            spawnSparks(position, dir, s, color, scene)
        case .hitFlash:
            spawnHitFlash(position, s, color, scene)
        case .fireBurst:
            spawnFireBurst(position, dir, s, color, scene)
        case .embers:
            spawnEmbers(position, dir, s, color, scene)
        case .iceShatter:
            spawnIceShatter(position, s, color, scene)
        case .smoke:
            spawnSmoke(position, dir, s, color, scene)
        case .dust:
            spawnDust(position, s, color, scene)
        case .shadowBurst:
            spawnShadowBurst(position, s, color, scene)
        case .webHit:
            spawnWebHit(position, dir, s, color, scene)
        case .riftPortal:
            spawnRiftPortal(position, s, color, scene)
        case .explosion:
            spawnExplosion(position, s, color, scene)
        case .electric:
            spawnElectric(position, s, color, scene)
        case .ash:
            spawnAsh(position, s, color, scene)
        }
    }

    /// Regen: an den Kamera-Knoten hängen (folgt der Kamera). intensity 0…2 (1 = kräftiger Regen).
    static func makeRain(intensity: Float) -> SCNParticleSystem {
        var k = intensity.isFinite ? intensity : 1
        k = Swift.min(Swift.max(k, 0), 2)
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(1400 * k * countScale)
        p.emitterShape = SCNBox(width: 24, height: 20, length: 24, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0.08, y: -1, z: 0.03)
        p.spreadingAngle = 3
        p.particleVelocity = 16
        p.particleVelocityVariation = 4
        p.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        p.particleLifeSpan = 1.1
        p.particleLifeSpanVariation = 0.3
        p.particleSize = 0.018
        p.particleSizeVariation = 0.006
        p.stretchFactor = 0.045
        p.particleColor = UIColor(red: 0.72, green: 0.78, blue: 0.88, alpha: 0.32)
        p.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.15, w: 0.1)
        p.warmupDuration = 1.2
        FX.addCurve(p, .opacity, [0, 1, 1, 0], [0, 0.08, 0.85, 1])

        // feiner Sprühnebel, wo Tropfen "aufschlagen" (nur ab Ausgewogen)
        if quality != .performance && k > 0.05 {
            let mist = SCNParticleSystem()
            mist.particleImage = FXSpriteBank.smoke
            mist.blendMode = .alpha
            mist.sortingMode = .none
            mist.isLightingEnabled = false
            mist.isLocal = false
            mist.loops = false
            mist.emissionDuration = 0.05
            mist.birthRate = 20
            mist.birthDirection = .random
            mist.spreadingAngle = 180
            mist.particleVelocity = 0.4
            mist.particleVelocityVariation = 0.2
            mist.dampingFactor = 1.5
            mist.particleLifeSpan = 0.6
            mist.particleLifeSpanVariation = 0.2
            mist.particleSize = 1
            mist.particleAngleVariation = 180
            mist.particleColor = UIColor(red: 0.8, green: 0.84, blue: 0.9, alpha: 0.07)
            FX.addCurve(mist, .size, [0.1, 0.38], [0, 1])
            FX.addCurve(mist, .opacity, [0, 1, 0], [0, 0.2, 1])
            p.systemSpawnedOnDying = mist
        }
        return p
    }

    /// Schwebende Glut (Gießerei, brennender Domplatz). Emitter: 26 x 3 x 26 m um den Knoten.
    static func makeEmbersAmbient() -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(45 * countScale + 6)
        p.emitterShape = SCNBox(width: 26, height: 3, length: 26, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 35
        p.particleVelocity = 0.7
        p.particleVelocityVariation = 0.45
        p.acceleration = SCNVector3(x: 0.18, y: 0.1, z: 0.06)
        p.dampingFactor = 0.15
        p.particleLifeSpan = 6
        p.particleLifeSpanVariation = 2
        p.particleSize = 0.032
        p.particleSizeVariation = 0.016
        p.particleColor = UIColor(red: 1.0, green: 0.5, blue: 0.14, alpha: 1)
        p.particleColorVariation = SCNVector4(x: 0.03, y: 0.1, z: 0.25, w: 0)
        p.particleIntensity = 2.6
        p.particleIntensityVariation = 1.4
        p.warmupDuration = 5
        FX.addCurve(p, .opacity, [0, 1, 0.5, 1, 0.35, 0], [0, 0.08, 0.3, 0.55, 0.8, 1])
        return p
    }

    /// Fallende Asche (brennende Stadt, Riss). Emitter: 30 x 10 x 30 m um den Knoten (Knoten ca. 5 m hoch setzen).
    static func makeAshAmbient() -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.flake
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(60 * countScale + 8)
        p.emitterShape = SCNBox(width: 30, height: 10, length: 30, chamferRadius: 0)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: -1, z: 0)
        p.spreadingAngle = 30
        p.particleVelocity = 0.35
        p.particleVelocityVariation = 0.2
        p.acceleration = SCNVector3(x: 0.12, y: -0.05, z: 0.04)
        p.particleLifeSpan = 9
        p.particleLifeSpanVariation = 3
        p.particleSize = 0.035
        p.particleSizeVariation = 0.02
        p.particleAngleVariation = 180
        p.particleAngularVelocity = 0
        p.particleAngularVelocityVariation = 90
        p.particleColor = UIColor(red: 0.30, green: 0.28, blue: 0.27, alpha: 0.85)
        p.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.4, w: 0.1)
        p.warmupDuration = 6
        FX.addCurve(p, .opacity, [0, 1, 1, 0], [0, 0.1, 0.85, 1])
        return p
    }

    /// Schleifendes, animiertes Rissportal (Ringe + Strudel + eingesaugte Partikel + pulsierendes Licht).
    /// Wurzel = Portalmitte, Radius ca. 1.3 m (Knoten ca. 1.6 m über dem Boden platzieren, simdScale zum Vergrößern).
    static func makeRiftSwirl(color: UIColor) -> SCNNode {
        let radius: Float = 1.3
        let lowDetail = quality == .performance
        let root = SCNNode()
        root.name = "fx.riftSwirl"
        root.castsShadow = false

        // Billboard (dreht sich nur um Y) – die Scheibe schaut immer zur Kamera.
        let face = SCNNode()
        let billboard = SCNBillboardConstraint()
        billboard.freeAxes = .Y
        face.constraints = [billboard]
        root.addChildNode(face)

        let pulse = SCNNode()
        face.addChildNode(pulse)
        let up = SCNAction.scale(to: 1.06, duration: 0.9)
        up.timingMode = .easeInEaseOut
        let down = SCNAction.scale(to: 0.95, duration: 0.9)
        down.timingMode = .easeInEaseOut
        pulse.runAction(.repeatForever(.sequence([up, down])))

        // Halo
        let haloImage = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: color)
        let halo = SCNPlane(width: CGFloat(radius * 3.6), height: CGFloat(radius * 3.6))
        halo.materials = [FX.spriteMaterial(haloImage, key: "glow#" + FXSpriteBank.key(color), boost: 1.0)]
        let haloNode = SCNNode(geometry: halo)
        haloNode.castsShadow = false
        haloNode.renderingOrder = 39
        haloNode.simdPosition = SIMD3<Float>(0, 0, -0.02)
        pulse.addChildNode(haloNode)

        // Schwarze Leere
        let voidPlane = SCNPlane(width: CGFloat(radius * 2.1), height: CGFloat(radius * 2.1))
        voidPlane.materials = [FX.spriteMaterial(FXSpriteBank.voidDisc, key: "voidDisc", boost: 1, additive: false)]
        let voidNode = SCNNode(geometry: voidPlane)
        voidNode.castsShadow = false
        voidNode.renderingOrder = 40
        pulse.addChildNode(voidNode)

        // Zwei gegenläufige Strudel
        let swirlImage = FXSpriteBank.swirl(color)
        let swirlMaterial = FX.spriteMaterial(swirlImage, key: "swirl#" + FXSpriteBank.key(color), boost: 1.8)
        for i in 0..<2 {
            let size = radius * (i == 0 ? 2.3 : 1.75)
            let plane = SCNPlane(width: CGFloat(size), height: CGFloat(size))
            plane.materials = [swirlMaterial]
            let swirlNode = SCNNode(geometry: plane)
            swirlNode.castsShadow = false
            swirlNode.renderingOrder = 41 + i
            swirlNode.simdPosition = SIMD3<Float>(0, 0, 0.01 * Float(i + 1))
            let turn: CGFloat = i == 0 ? -1 : 1
            swirlNode.runAction(.repeatForever(.rotateBy(x: 0, y: 0, z: turn * CGFloat.pi * 2, duration: i == 0 ? 5.0 : 3.2)))
            pulse.addChildNode(swirlNode)
        }

        // Rahmenring (liegt in der Scheibenebene)
        let ringMaterial = FX.glowLineMaterial(color, boost: 2.2)
        let frame = SCNTorus(ringRadius: CGFloat(radius * 1.02), pipeRadius: 0.035)
        frame.ringSegmentCount = lowDetail ? 40 : 72
        frame.pipeSegmentCount = 8
        frame.materials = [ringMaterial]
        let frameNode = SCNNode(geometry: frame)
        frameNode.castsShadow = false
        frameNode.simdEulerAngles = SIMD3<Float>(Float.pi / 2, 0, 0)
        pulse.addChildNode(frameNode)

        // Kreisende 3D-Ringe (Gyroskop)
        let ringSpecs: [(r: Float, tiltX: Float, tiltZ: Float, axis: SIMD3<Float>, duration: Double)] = [
            (1.18, 1.25, 0.3, SIMD3<Float>(0, 1, 0), 3.4),
            (1.32, 0.4, 1.1, SIMD3<Float>(1, 0, 0.3), 4.6),
            (1.45, -0.9, -0.5, SIMD3<Float>(0.2, 1, -0.6), 6.0)
        ]
        let ringCount = lowDetail ? 2 : 3
        for i in 0..<ringCount {
            let spec = ringSpecs[i]
            let torus = SCNTorus(ringRadius: CGFloat(radius * spec.r), pipeRadius: 0.016)
            torus.ringSegmentCount = lowDetail ? 40 : 72
            torus.pipeSegmentCount = 6
            torus.materials = [ringMaterial]
            let ringNode = SCNNode(geometry: torus)
            ringNode.castsShadow = false
            ringNode.simdEulerAngles = SIMD3<Float>(spec.tiltX, 0, spec.tiltZ)
            let gimbal = SCNNode()
            gimbal.addChildNode(ringNode)
            let a = FX.safeDirection(spec.axis)
            let full = CGFloat.pi * 2
            let spin = SCNAction.rotateBy(x: full * CGFloat(a.x), y: full * CGFloat(a.y), z: full * CGFloat(a.z),
                                          duration: spec.duration)
            gimbal.runAction(.repeatForever(spin))
            root.addChildNode(gimbal)
        }

        // Eingesaugte Partikel
        let suck = SCNParticleSystem()
        suck.particleImage = FXSpriteBank.spark
        suck.blendMode = .additive
        suck.sortingMode = .none
        suck.isLightingEnabled = false
        suck.isLocal = false
        suck.loops = true
        suck.emissionDuration = 1
        suck.birthRate = CGFloat(70 * countScale + 10)
        suck.emitterShape = SCNSphere(radius: CGFloat(radius * 1.55))
        suck.birthLocation = .surface
        suck.birthDirection = .surfaceNormal
        suck.particleVelocity = -2.2      // negativ = nach innen
        suck.particleVelocityVariation = 0.3
        suck.particleLifeSpan = 0.85
        suck.particleLifeSpanVariation = 0.1
        suck.particleSize = 0.035
        suck.particleSizeVariation = 0.015
        suck.stretchFactor = 0.06
        suck.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        suck.particleIntensity = 2.2
        FX.addCurve(suck, .opacity, [0, 1, 1, 0], [0, 0.25, 0.8, 1])
        root.addParticleSystem(suck)

        // Schwebende Funken am Rand
        if !lowDetail {
            let motes = SCNParticleSystem()
            motes.particleImage = FXSpriteBank.glow
            motes.blendMode = .additive
            motes.sortingMode = .none
            motes.isLightingEnabled = false
            motes.isLocal = false
            motes.loops = true
            motes.emissionDuration = 1
            motes.birthRate = CGFloat(18 * countScale + 4)
            motes.emitterShape = SCNSphere(radius: CGFloat(radius * 1.1))
            motes.birthLocation = .volume
            motes.birthDirection = .random
            motes.spreadingAngle = 180
            motes.particleVelocity = 0.25
            motes.particleVelocityVariation = 0.15
            motes.particleLifeSpan = 1.6
            motes.particleLifeSpanVariation = 0.5
            motes.particleSize = 0.09
            motes.particleSizeVariation = 0.05
            motes.particleColor = color
            motes.particleIntensity = 1.6
            FX.addCurve(motes, .opacity, [0, 0.8, 0], [0, 0.4, 1])
            root.addParticleSystem(motes)
        }

        // Pulsierendes Licht
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = 820
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = 9
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let lightNode = SCNNode()
        lightNode.light = light
        lightNode.simdPosition = SIMD3<Float>(0, 0, 0.4)
        let period: Double = 1.8
        let pulseLight = SCNAction.customAction(duration: period) { node, elapsed in
            let phase = Double(elapsed) / period * Double.pi * 2
            node.light?.intensity = CGFloat(820 + 380 * sin(phase))
        }
        lightNode.runAction(.repeatForever(pulseLight))
        root.addChildNode(lightNode)

        return root
    }

    /// Bewegungsspur für Fäuste/Füße/Geschosse (Partikel bleiben im Weltraum zurück).
    static func makeTrail(color: UIColor) -> SCNParticleSystem {
        return FX.trailSystem(color: color, size: 0.09, dark: FXSpriteBank.luminance(color) < 0.12)
    }

    /// Entfernt alle kurzlebigen FX-Knoten (Treffer, Blutlachen, Lichtblitze …) aus der Szene.
    static func cleanup(in scene: SCNScene) {
        let children = scene.rootNode.childNodes
        for child in children where child.name == transientNodeName {
            child.removeAllActions()
            child.removeAllParticleSystems()
            child.removeFromParentNode()
        }
        livePools.removeAll(where: { $0.parent == nil })
        liveLights.removeAll(where: { $0.parent == nil })
    }

    // MARK: - Gemeinsame Helfer (fileprivate: auch für ProjectileVisual)

    fileprivate static var countScale: Float {
        switch quality {
        case .performance: return 0.4
        case .balanced: return 0.7
        case .ultra: return 1.0
        }
    }

    private static var maxFlashLights: Int {
        switch quality {
        case .performance: return 1
        case .balanced: return 2
        case .ultra: return 4
        }
    }

    /// Partikelanzahl nach Qualität und Effektgröße.
    private static func count(_ base: Float, _ s: Float) -> Float {
        let sizeFactor = Swift.min(2.5, Swift.max(0.5, s))
        return Swift.max(1, (base * countScale * sizeFactor).rounded())
    }

    private static func cg(_ v: Float) -> CGFloat {
        return CGFloat(v)
    }

    private static func vec(_ v: SIMD3<Float>) -> SCNVector3 {
        return SCNVector3(x: v.x, y: v.y, z: v.z)
    }

    private static func isFinite3(_ v: SIMD3<Float>) -> Bool {
        return v.x.isFinite && v.y.isFinite && v.z.isFinite
    }

    fileprivate static func safeDirection(_ v: SIMD3<Float>) -> SIMD3<Float> {
        guard FX.isFinite3(v) else { return SIMD3<Float>(0, 1, 0) }
        let l = simd_length(v)
        if !l.isFinite || l < 1e-5 { return SIMD3<Float>(0, 1, 0) }
        return v / l
    }

    /// Kurzer, nicht schleifender Partikelstoß: count Partikel innerhalb von duration Sekunden.
    private static func makeBurst(_ image: UIImage, additive: Bool, count: Float, over duration: Float = 0.05) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = image
        p.blendMode = additive ? .additive : .alpha
        p.sortingMode = additive ? .none : .projectedDepth
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isAffectedByPhysicsFields = false
        p.isLocal = false
        p.loops = false
        p.orientationMode = .billboardScreenAligned
        p.particleColor = .white
        let d = Swift.max(0.02, duration)
        p.emissionDuration = CGFloat(d)
        p.birthRate = CGFloat(Swift.max(1, count) / d)
        return p
    }

    /// Kugelförmiger Stoß in alle Richtungen.
    private static func makeOmni(_ p: SCNParticleSystem, radius: Float) {
        p.emitterShape = SCNSphere(radius: CGFloat(Swift.max(0.005, radius)))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
    }

    /// Wert-Kurve über die Lebenszeit (opacity / size …).
    /// Bei .size immer particleSize = 1 setzen – dann stimmen absolute UND relative Deutung überein.
    fileprivate static func addCurve(_ p: SCNParticleSystem, _ property: SCNParticleSystem.ParticleProperty,
                                     _ values: [Float], _ times: [Float]) {
        guard values.count >= 2, values.count == times.count else { return }
        let anim = CAKeyframeAnimation()
        anim.values = values.map { NSNumber(value: $0) }
        anim.keyTimes = times.map { NSNumber(value: $0) }
        anim.duration = 1
        var dict = p.propertyControllers ?? [:]
        dict[property] = SCNParticlePropertyController(animation: anim)
        p.propertyControllers = dict
    }

    /// Farbverlauf über die Lebenszeit (particleColor bleibt weiß).
    fileprivate static func addColorCurve(_ p: SCNParticleSystem, _ colors: [UIColor], _ times: [Float]) {
        guard colors.count >= 2, colors.count == times.count else { return }
        let anim = CAKeyframeAnimation()
        anim.values = colors
        anim.keyTimes = times.map { NSNumber(value: $0) }
        anim.duration = 1
        var dict = p.propertyControllers ?? [:]
        dict[.color] = SCNParticlePropertyController(animation: anim)
        p.propertyControllers = dict
        p.particleColor = .white
    }

    fileprivate static func fireColors(_ tint: UIColor?) -> [UIColor] {
        if let t = tint, !FXSpriteBank.isWarm(t) {
            return [FXSpriteBank.mix(t, .white, 0.7).withAlphaComponent(1),
                    FXSpriteBank.scaled(t, 1, alpha: 0.95),
                    FXSpriteBank.scaled(t, 0.55, alpha: 0.6),
                    FXSpriteBank.scaled(t, 0.15, alpha: 0)]
        }
        return [UIColor(red: 1.0, green: 0.93, blue: 0.70, alpha: 1.0),
                UIColor(red: 1.0, green: 0.56, blue: 0.14, alpha: 0.95),
                UIColor(red: 0.75, green: 0.16, blue: 0.03, alpha: 0.6),
                UIColor(red: 0.18, green: 0.03, blue: 0.01, alpha: 0.0)]
    }

    private static func sparkColors(_ tint: UIColor?) -> [UIColor] {
        if let t = tint {
            return [FXSpriteBank.mix(t, .white, 0.75).withAlphaComponent(1),
                    FXSpriteBank.scaled(t, 1, alpha: 1),
                    FXSpriteBank.scaled(t, 0.6, alpha: 0.8),
                    FXSpriteBank.scaled(t, 0.3, alpha: 0)]
        }
        return [UIColor(red: 1.0, green: 0.96, blue: 0.82, alpha: 1),
                UIColor(red: 1.0, green: 0.72, blue: 0.28, alpha: 1),
                UIColor(red: 1.0, green: 0.36, blue: 0.06, alpha: 0.8),
                UIColor(red: 0.55, green: 0.08, blue: 0.0, alpha: 0)]
    }

    /// Hängt Systeme an einen kurzlebigen Knoten und entfernt ihn, wenn alle Partikel tot sind.
    @discardableResult
    private static func emit(_ systems: [SCNParticleSystem], at position: SIMD3<Float>, in scene: SCNScene) -> SCNNode {
        let node = SCNNode()
        node.name = transientNodeName
        node.simdPosition = position
        node.castsShadow = false
        var longest: Double = 0.1
        for p in systems {
            node.addParticleSystem(p)
            let life = Double(p.emissionDuration + p.emissionDurationVariation + p.particleLifeSpan + p.particleLifeSpanVariation)
            longest = Swift.max(longest, life)
        }
        scene.rootNode.addChildNode(node)
        node.runAction(.sequence([.wait(duration: longest + 0.2), .removeFromParentNode()]))
        return node
    }

    /// Material für Billboard-Sprites (additiv mit HDR-Boost oder Alpha).
    fileprivate static func spriteMaterial(_ image: UIImage, key: String, boost: Float, additive: Bool = true) -> SCNMaterial {
        let k = key + "|" + String(Int(boost * 100)) + (additive ? "a" : "n")
        if let m = spriteMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .constant
        m.diffuse.contents = image
        if additive {
            m.blendMode = .add
            if boost > 1 {
                m.emission.contents = image
                m.emission.intensity = CGFloat(boost - 1)
            }
        } else {
            m.blendMode = .alpha
        }
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = true
        spriteMaterialCache[k] = m
        return m
    }

    /// Leuchtende Linie/Ring (additiv, unbeleuchtet, HDR-hell).
    fileprivate static func glowLineMaterial(_ color: UIColor, boost: Float) -> SCNMaterial {
        let k = "line#" + FXSpriteBank.key(color) + "|" + String(Int(boost * 100))
        if let m = spriteMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .constant
        m.diffuse.contents = color
        if boost > 1 {
            m.emission.contents = color
            m.emission.intensity = CGFloat(boost - 1)
        }
        m.blendMode = .add
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = false
        spriteMaterialCache[k] = m
        return m
    }

    /// Einzelnes Billboard, das wächst und ausblendet (Blitz-Kern, Schockwelle).
    private static func spawnSprite(_ image: UIImage, key: String, at position: SIMD3<Float>, in scene: SCNScene,
                                    size: Float, from startScale: Float, to endScale: Float,
                                    duration: Double, boost: Float) {
        let plane = SCNPlane(width: cg(size), height: cg(size))
        plane.materials = [spriteMaterial(image, key: key, boost: boost)]
        let node = SCNNode(geometry: plane)
        node.name = transientNodeName
        node.castsShadow = false
        node.renderingOrder = 60
        node.simdPosition = position
        node.simdScale = SIMD3<Float>(repeating: Swift.max(0.001, startScale))
        node.constraints = [SCNBillboardConstraint()]
        scene.rootNode.addChildNode(node)
        let grow = SCNAction.scale(to: cg(endScale), duration: duration)
        grow.timingMode = .easeOut
        let fade = SCNAction.fadeOut(duration: duration)
        fade.timingMode = .easeIn
        node.runAction(.sequence([.group([grow, fade]), .removeFromParentNode()]))
    }

    /// Sehr kurzes Punktlicht (Anzahl gleichzeitiger FX-Lichter ist nach Qualität begrenzt).
    private static func flashLight(at position: SIMD3<Float>, in scene: SCNScene, color: UIColor,
                                   intensity: Float, range: Float, duration: Double, flicker: Bool = false) {
        liveLights.removeAll(where: { $0.parent == nil })
        if liveLights.count >= maxFlashLights { return }
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = CGFloat(intensity)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.5, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let node = SCNNode()
        node.light = light
        node.name = transientNodeName
        node.simdPosition = position
        scene.rootNode.addChildNode(node)
        liveLights.append(node)
        let peak = CGFloat(intensity)
        let total = Swift.max(0.02, duration)
        let fade = SCNAction.customAction(duration: total) { n, elapsed in
            let t = Swift.min(1, Swift.max(0, Double(elapsed) / total))
            var k = (1 - t) * (1 - t)
            if flicker {
                k *= 0.3 + 0.7 * abs(sin(t * 53.0))
            }
            n.light?.intensity = peak * CGFloat(k)
        }
        node.runAction(.sequence([fade, .removeFromParentNode()]))
    }

    // MARK: - Blut

    private static func spawnBloodSpray(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dropImage = tint == nil ? FXSpriteBank.bloodDrop : FXSpriteBank.grayDrop
        let dropColor = tint ?? UIColor.white

        // Tropfen (gestreckt, fallen mit Schwerkraft)
        let drops = makeBurst(dropImage, additive: false, count: count(70, s), over: 0.1)
        drops.particleColor = dropColor
        drops.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        drops.emitterShape = SCNSphere(radius: cg(0.035 * s))
        drops.birthLocation = .volume
        drops.birthDirection = .constant
        drops.emittingDirection = vec(dir)
        drops.spreadingAngle = 22
        drops.particleVelocity = cg(5.8 * vs)
        drops.particleVelocityVariation = cg(3.0 * vs)
        drops.acceleration = SCNVector3(x: 0, y: -10.5, z: 0)
        drops.dampingFactor = 0.25
        drops.particleLifeSpan = 0.9
        drops.particleLifeSpanVariation = 0.35
        drops.particleSize = cg(0.03 * s)
        drops.particleSizeVariation = cg(0.018 * s)
        drops.stretchFactor = 0.04
        addCurve(drops, .opacity, [1, 1, 0], [0, 0.82, 1])

        // dicke Batzen
        let globs = makeBurst(dropImage, additive: false, count: count(12, s), over: 0.12)
        globs.particleColor = dropColor
        globs.birthDirection = .constant
        globs.emittingDirection = vec(dir)
        globs.spreadingAngle = 14
        globs.particleVelocity = cg(3.6 * vs)
        globs.particleVelocityVariation = cg(1.4 * vs)
        globs.acceleration = SCNVector3(x: 0, y: -11, z: 0)
        globs.particleLifeSpan = 1.0
        globs.particleLifeSpanVariation = 0.3
        globs.particleSize = cg(0.07 * s)
        globs.particleSizeVariation = cg(0.03 * s)
        globs.particleAngleVariation = 180
        globs.stretchFactor = 0.015
        addCurve(globs, .opacity, [1, 1, 0], [0, 0.85, 1])

        // feiner Nebel
        let mist = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.08)
        mist.particleColor = tint.map { $0.withAlphaComponent(0.55) } ?? bloodMistColor
        mist.birthDirection = .constant
        mist.emittingDirection = vec(dir)
        mist.spreadingAngle = 40
        mist.particleVelocity = cg(1.6 * vs)
        mist.particleVelocityVariation = 0.7
        mist.dampingFactor = 2.2
        mist.particleLifeSpan = 0.55
        mist.particleLifeSpanVariation = 0.15
        mist.particleSize = 1
        mist.particleAngleVariation = 180
        addCurve(mist, .size, [0.14 * s, 0.5 * s], [0, 1])
        addCurve(mist, .opacity, [0, 0.7, 0], [0, 0.12, 1])

        emit([drops, globs, mist], at: p, in: scene)
    }

    private static func spawnBloodBurst(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dropImage = tint == nil ? FXSpriteBank.bloodDrop : FXSpriteBank.grayDrop
        let dropColor = tint ?? UIColor.white

        let drops = makeBurst(dropImage, additive: false, count: count(150, s), over: 0.08)
        makeOmni(drops, radius: 0.12 * s)
        drops.particleColor = dropColor
        drops.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        drops.particleVelocity = cg(4.8 * vs)
        drops.particleVelocityVariation = cg(2.6 * vs)
        drops.acceleration = SCNVector3(x: 0, y: -10.5, z: 0)
        drops.dampingFactor = 0.3
        drops.particleLifeSpan = 1.0
        drops.particleLifeSpanVariation = 0.35
        drops.particleSize = cg(0.032 * s)
        drops.particleSizeVariation = cg(0.02 * s)
        drops.stretchFactor = 0.035
        addCurve(drops, .opacity, [1, 1, 0], [0, 0.82, 1])

        let globs = makeBurst(dropImage, additive: false, count: count(26, s), over: 0.1)
        makeOmni(globs, radius: 0.1 * s)
        globs.particleColor = dropColor
        globs.particleVelocity = cg(3.2 * vs)
        globs.particleVelocityVariation = cg(1.6 * vs)
        globs.acceleration = SCNVector3(x: 0, y: -11, z: 0)
        globs.particleLifeSpan = 1.1
        globs.particleLifeSpanVariation = 0.3
        globs.particleSize = cg(0.075 * s)
        globs.particleSizeVariation = cg(0.035 * s)
        globs.particleAngleVariation = 180
        globs.stretchFactor = 0.012
        addCurve(globs, .opacity, [1, 1, 0], [0, 0.85, 1])

        let mist = makeBurst(FXSpriteBank.smoke, additive: false, count: count(22, s), over: 0.1)
        makeOmni(mist, radius: 0.15 * s)
        mist.particleColor = tint.map { $0.withAlphaComponent(0.6) } ?? bloodMistColor
        mist.particleVelocity = cg(1.8 * vs)
        mist.particleVelocityVariation = 0.8
        mist.dampingFactor = 2.4
        mist.particleLifeSpan = 0.7
        mist.particleLifeSpanVariation = 0.2
        mist.particleSize = 1
        mist.particleAngleVariation = 180
        mist.particleAngularVelocityVariation = 60
        addCurve(mist, .size, [0.2 * s, 0.8 * s], [0, 1])
        addCurve(mist, .opacity, [0, 0.75, 0], [0, 0.1, 1])

        emit([drops, globs, mist], at: p, in: scene)
    }

    /// Blutlache: flaches, glänzendes Decal; wächst ~1.5 s, verblasst nach 20 s, max. 24 gleichzeitig.
    private static func spawnBloodPool(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        livePools.removeAll(where: { $0.parent == nil })
        while livePools.count >= maxLivePools {
            let oldest = livePools.removeFirst()
            oldest.removeAllActions()
            oldest.runAction(.sequence([.fadeOut(duration: 0.5), .removeFromParentNode()]))
        }
        let w = 1.1 * s * Float.random(in: 0.8...1.2)
        let h = 1.1 * s * Float.random(in: 0.8...1.2)
        let plane = SCNPlane(width: cg(w), height: cg(h))
        plane.materials = [poolMaterial(tint ?? bloodPoolColor)]
        let node = SCNNode(geometry: plane)
        node.name = transientNodeName
        node.castsShadow = false
        node.renderingOrder = 10
        // leicht gestaffelte Höhe gegen Z-Fighting überlappender Lachen
        let lift: Float = 0.006 + Float(livePools.count % 12) * 0.0008
        node.simdPosition = SIMD3<Float>(p.x, p.y + lift, p.z)
        let flat = simd_quatf(angle: -Float.pi / 2, axis: SIMD3<Float>(1, 0, 0))
        let spin = simd_quatf(angle: Float.random(in: 0..<(Float.pi * 2)), axis: SIMD3<Float>(0, 1, 0))
        node.simdOrientation = spin * flat
        node.simdScale = SIMD3<Float>(repeating: 0.12)
        scene.rootNode.addChildNode(node)
        livePools.append(node)
        let grow = SCNAction.scale(to: 1, duration: 1.5)
        grow.timingMode = .easeOut
        node.runAction(.sequence([grow, .wait(duration: 18.5), .fadeOut(duration: 2.0), .removeFromParentNode()]))
    }

    private static func poolMaterial(_ color: UIColor) -> SCNMaterial {
        let k = FXSpriteBank.key(color)
        if let m = poolMaterialCache[k] { return m }
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = FXSpriteBank.splat(color)
        m.roughness.contents = NSNumber(value: 0.12)
        m.metalness.contents = NSNumber(value: 0.0)
        m.blendMode = .alpha
        m.writesToDepthBuffer = false
        m.readsFromDepthBuffer = true
        m.isDoubleSided = false
        poolMaterialCache[k] = m
        return m
    }

    /// Blut deaktiviert: dunkler Staub + graue Funken.
    private static func spawnBloodless(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let dust = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.08)
        dust.particleColor = UIColor(red: 0.2, green: 0.2, blue: 0.22, alpha: 0.75)
        dust.birthDirection = .constant
        dust.emittingDirection = vec(dir)
        dust.spreadingAngle = 50
        dust.particleVelocity = cg(1.4 * vs)
        dust.particleVelocityVariation = 0.6
        dust.dampingFactor = 2.0
        dust.particleLifeSpan = 0.7
        dust.particleLifeSpanVariation = 0.2
        dust.particleSize = 1
        dust.particleAngleVariation = 180
        addCurve(dust, .size, [0.18 * s, 0.55 * s], [0, 1])
        addCurve(dust, .opacity, [0, 0.8, 0], [0, 0.15, 1])

        let sp = makeBurst(FXSpriteBank.spark, additive: true, count: count(22, s), over: 0.05)
        sp.birthDirection = .constant
        sp.emittingDirection = vec(dir)
        sp.spreadingAngle = 45
        sp.particleVelocity = cg(5.5 * vs)
        sp.particleVelocityVariation = cg(2.5 * vs)
        sp.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sp.particleLifeSpan = 0.32
        sp.particleLifeSpanVariation = 0.12
        sp.particleSize = cg(0.016 * s)
        sp.stretchFactor = 0.05
        sp.particleColor = UIColor(red: 0.85, green: 0.85, blue: 0.9, alpha: 1)
        sp.particleIntensity = 1.4
        addCurve(sp, .opacity, [1, 0], [0, 1])

        emit([dust, sp], at: p, in: scene)
    }

    // MARK: - Funken & Treffer

    private static func spawnSparks(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let sp = makeBurst(FXSpriteBank.spark, additive: true, count: count(48, s), over: 0.05)
        sp.birthDirection = .constant
        sp.emittingDirection = vec(dir)
        sp.spreadingAngle = 55
        sp.particleVelocity = cg(6.5 * vs)
        sp.particleVelocityVariation = cg(3.5 * vs)
        sp.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sp.dampingFactor = 0.6
        sp.particleLifeSpan = 0.42
        sp.particleLifeSpanVariation = 0.22
        sp.particleSize = cg(0.02 * s)
        sp.particleSizeVariation = cg(0.008 * s)
        sp.stretchFactor = 0.06
        sp.particleIntensity = 3.2
        sp.particleIntensityVariation = 1.5
        addColorCurve(sp, sparkColors(tint), [0, 0.25, 0.6, 1])

        let core = makeBurst(FXSpriteBank.glow, additive: true, count: 2, over: 0.04)
        core.particleVelocity = 0
        core.particleLifeSpan = 0.09
        core.particleSize = cg(0.35 * s)
        core.particleColor = tint ?? UIColor(red: 1.0, green: 0.85, blue: 0.55, alpha: 1)
        core.particleIntensity = 2.5
        addCurve(core, .opacity, [1, 0], [0, 1])

        emit([sp, core], at: p, in: scene)
    }

    private static func spawnHitFlash(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 1.0, green: 0.92, blue: 0.78, alpha: 1)
        let ck = FXSpriteBank.key(c)
        flashLight(at: p, in: scene, color: c, intensity: 2600 * Swift.min(2, s), range: 4.5 * s, duration: 0.13)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: c), key: "glow#" + ck,
                    at: p, in: scene, size: 1.1 * s, from: 0.45, to: 1.15, duration: 0.12, boost: 2.5)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.ring, baseKey: "ring", color: c), key: "ring#" + ck,
                    at: p, in: scene, size: 1.0 * s, from: 0.25, to: 1.7, duration: 0.2, boost: 1.6)

        let streaks = makeBurst(FXSpriteBank.spark, additive: true, count: count(12, s), over: 0.03)
        makeOmni(streaks, radius: 0.03 * s)
        streaks.particleVelocity = cg(9 * vs)
        streaks.particleVelocityVariation = cg(3 * vs)
        streaks.particleLifeSpan = 0.08
        streaks.particleLifeSpanVariation = 0.03
        streaks.particleSize = cg(0.03 * s)
        streaks.stretchFactor = 0.035
        streaks.particleColor = FXSpriteBank.mix(c, .white, 0.4)
        streaks.particleIntensity = 4
        addCurve(streaks, .opacity, [1, 0], [0, 1])
        emit([streaks], at: p, in: scene)
    }

    // MARK: - Feuer, Glut, Explosion

    private static func spawnFireBurst(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()

        let fire = makeBurst(FXSpriteBank.fire, additive: true, count: count(90, s), over: 0.12)
        fire.emitterShape = SCNSphere(radius: cg(0.12 * s))
        fire.birthLocation = .volume
        fire.birthDirection = .constant
        fire.emittingDirection = vec(dir)
        fire.spreadingAngle = 40
        fire.particleVelocity = cg(3.0 * vs)
        fire.particleVelocityVariation = cg(1.6 * vs)
        fire.acceleration = SCNVector3(x: 0, y: 2.2, z: 0)
        fire.dampingFactor = 1.6
        fire.particleLifeSpan = 0.75
        fire.particleLifeSpanVariation = 0.25
        fire.particleSize = 1
        fire.particleAngleVariation = 180
        fire.particleAngularVelocityVariation = 120
        fire.particleIntensity = 2.6
        fire.particleIntensityVariation = 0.8
        addCurve(fire, .size, [0.18 * s, 0.32 * s, 0.5 * s], [0, 0.3, 1])
        addColorCurve(fire, fireColors(tint), [0, 0.2, 0.55, 1])

        let embers = makeBurst(FXSpriteBank.spark, additive: true, count: count(26, s), over: 0.1)
        embers.birthDirection = .constant
        embers.emittingDirection = vec(dir)
        embers.spreadingAngle = 60
        embers.particleVelocity = cg(4 * vs)
        embers.particleVelocityVariation = cg(2 * vs)
        embers.acceleration = SCNVector3(x: 0, y: 0.6, z: 0)
        embers.dampingFactor = 0.8
        embers.particleLifeSpan = 1.3
        embers.particleLifeSpanVariation = 0.5
        embers.particleSize = cg(0.018 * s)
        embers.particleSizeVariation = cg(0.008 * s)
        embers.stretchFactor = 0.02
        embers.particleIntensity = 3.5
        addColorCurve(embers, sparkColors(tint == nil || FXSpriteBank.isWarm(tint ?? .orange) ? nil : tint), [0, 0.2, 0.6, 1])

        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(10, s), over: 0.15)
        smoke.birthDirection = .constant
        smoke.emittingDirection = vec(dir)
        smoke.spreadingAngle = 35
        smoke.particleVelocity = cg(1.2 * vs)
        smoke.particleVelocityVariation = 0.5
        smoke.acceleration = SCNVector3(x: 0, y: 0.9, z: 0)
        smoke.dampingFactor = 0.8
        smoke.particleLifeSpan = 2.0
        smoke.particleLifeSpanVariation = 0.5
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 30
        smoke.particleColor = UIColor(red: 0.12, green: 0.11, blue: 0.11, alpha: 1)
        addCurve(smoke, .size, [0.4 * s, 1.3 * s], [0, 1])
        addCurve(smoke, .opacity, [0, 0, 0.45, 0], [0, 0.15, 0.35, 1])

        let lightColor = (tint == nil || FXSpriteBank.isWarm(tint ?? .orange))
            ? UIColor(red: 1.0, green: 0.55, blue: 0.2, alpha: 1)
            : (tint ?? UIColor.orange)
        flashLight(at: p, in: scene, color: lightColor, intensity: 3200 * Swift.min(2, s), range: 6 * s, duration: 0.35)
        emit([fire, embers, smoke], at: p, in: scene)
    }

    private static func spawnEmbers(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let e = makeBurst(FXSpriteBank.spark, additive: true, count: count(40, s), over: 0.15)
        e.emitterShape = SCNSphere(radius: cg(0.15 * s))
        e.birthLocation = .volume
        e.birthDirection = .constant
        e.emittingDirection = vec(dir)
        e.spreadingAngle = 60
        e.particleVelocity = cg(1.5 * vs)
        e.particleVelocityVariation = cg(1.0 * vs)
        e.acceleration = SCNVector3(x: 0.2, y: 0.8, z: 0.1)
        e.dampingFactor = 0.4
        e.particleLifeSpan = 1.6
        e.particleLifeSpanVariation = 0.6
        e.particleSize = cg(0.025 * s)
        e.particleSizeVariation = cg(0.012 * s)
        e.particleColor = tint ?? UIColor(red: 1.0, green: 0.5, blue: 0.14, alpha: 1)
        e.particleColorVariation = SCNVector4(x: 0.03, y: 0.1, z: 0.25, w: 0)
        e.particleIntensity = 3
        e.particleIntensityVariation = 1.2
        addCurve(e, .opacity, [0, 1, 0.5, 1, 0], [0, 0.1, 0.4, 0.65, 1])
        emit([e], at: p, in: scene)
    }

    private static func spawnExplosion(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let lightColor = (tint == nil || FXSpriteBank.isWarm(tint ?? .orange))
            ? UIColor(red: 1.0, green: 0.6, blue: 0.3, alpha: 1)
            : (tint ?? UIColor.orange)
        flashLight(at: p, in: scene, color: lightColor, intensity: 6500 * Swift.min(2, s), range: 14 * s, duration: 0.45)

        let flashColor = FXSpriteBank.mix(lightColor, .white, 0.5)
        let fk = FXSpriteBank.key(flashColor)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: flashColor), key: "glow#" + fk,
                    at: p, in: scene, size: 3.0 * s, from: 0.5, to: 1.2, duration: 0.25, boost: 2.5)
        spawnSprite(FXSpriteBank.tinted(FXSpriteBank.ring, baseKey: "ring", color: flashColor), key: "ring#" + fk,
                    at: p, in: scene, size: 1.0 * s, from: 0.5, to: 7.0, duration: 0.38, boost: 1.4)

        let fireball = makeBurst(FXSpriteBank.fire, additive: true, count: count(110, s), over: 0.08)
        makeOmni(fireball, radius: 0.3 * s)
        fireball.particleVelocity = cg(6 * vs)
        fireball.particleVelocityVariation = cg(3 * vs)
        fireball.acceleration = SCNVector3(x: 0, y: 1.5, z: 0)
        fireball.dampingFactor = 3.2
        fireball.particleLifeSpan = 0.9
        fireball.particleLifeSpanVariation = 0.3
        fireball.particleSize = 1
        fireball.particleAngleVariation = 180
        fireball.particleAngularVelocityVariation = 90
        fireball.particleIntensity = 3
        fireball.particleIntensityVariation = 1
        addCurve(fireball, .size, [0.5 * s, 1.2 * s, 1.6 * s], [0, 0.35, 1])
        addColorCurve(fireball, fireColors(tint), [0, 0.18, 0.5, 1])

        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(36, s), over: 0.2)
        smoke.emitterShape = SCNSphere(radius: cg(0.4 * s))
        smoke.birthLocation = .volume
        smoke.birthDirection = .constant
        smoke.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        smoke.spreadingAngle = 80
        smoke.particleVelocity = cg(2.5 * vs)
        smoke.particleVelocityVariation = cg(1.2 * vs)
        smoke.acceleration = SCNVector3(x: 0, y: 1.1, z: 0)
        smoke.dampingFactor = 1.2
        smoke.particleLifeSpan = 3.2
        smoke.particleLifeSpanVariation = 0.8
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 25
        smoke.particleColor = UIColor(red: 0.07, green: 0.065, blue: 0.06, alpha: 1)
        addCurve(smoke, .size, [0.7 * s, 2.2 * s, 3.0 * s], [0, 0.4, 1])
        addCurve(smoke, .opacity, [0, 0.7, 0.5, 0], [0, 0.12, 0.5, 1])

        let sparks = makeBurst(FXSpriteBank.spark, additive: true, count: count(90, s), over: 0.06)
        makeOmni(sparks, radius: 0.2 * s)
        sparks.particleVelocity = cg(11 * vs)
        sparks.particleVelocityVariation = cg(5 * vs)
        sparks.acceleration = SCNVector3(x: 0, y: -9.8, z: 0)
        sparks.dampingFactor = 0.4
        sparks.particleLifeSpan = 1.0
        sparks.particleLifeSpanVariation = 0.4
        sparks.particleSize = cg(0.025 * s)
        sparks.particleSizeVariation = cg(0.01 * s)
        sparks.stretchFactor = 0.05
        sparks.particleIntensity = 4
        addColorCurve(sparks, sparkColors(nil), [0, 0.2, 0.6, 1])

        let debris = makeBurst(FXSpriteBank.flake, additive: false, count: count(30, s), over: 0.05)
        debris.emitterShape = SCNSphere(radius: cg(0.25 * s))
        debris.birthLocation = .volume
        debris.birthDirection = .constant
        debris.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        debris.spreadingAngle = 75
        debris.particleVelocity = cg(7 * vs)
        debris.particleVelocityVariation = cg(3 * vs)
        debris.acceleration = SCNVector3(x: 0, y: -14, z: 0)
        debris.particleLifeSpan = 1.6
        debris.particleLifeSpanVariation = 0.4
        debris.particleSize = cg(0.06 * s)
        debris.particleSizeVariation = cg(0.03 * s)
        debris.particleAngleVariation = 180
        debris.particleAngularVelocityVariation = 720
        debris.particleColor = UIColor(red: 0.05, green: 0.045, blue: 0.04, alpha: 1)
        addCurve(debris, .opacity, [1, 1, 0], [0, 0.85, 1])

        emit([fireball, smoke, sparks, debris], at: p, in: scene)
    }

    // MARK: - Eis, Rauch, Staub, Schatten, Netz, Strom, Asche

    private static func spawnIceShatter(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let iceColor = tint ?? UIColor(red: 0.72, green: 0.9, blue: 1.0, alpha: 1)

        let shards = makeBurst(FXSpriteBank.shard, additive: false, count: count(40, s), over: 0.05)
        makeOmni(shards, radius: 0.15 * s)
        shards.particleVelocity = cg(5 * vs)
        shards.particleVelocityVariation = cg(2.5 * vs)
        shards.acceleration = SCNVector3(x: 0, y: -12, z: 0)
        shards.dampingFactor = 0.3
        shards.particleLifeSpan = 0.9
        shards.particleLifeSpanVariation = 0.3
        shards.particleSize = cg(0.075 * s)
        shards.particleSizeVariation = cg(0.04 * s)
        shards.particleAngleVariation = 180
        shards.particleAngularVelocityVariation = 540
        shards.particleColor = iceColor
        shards.particleColorVariation = SCNVector4(x: 0, y: 0.15, z: 0.15, w: 0)
        addCurve(shards, .opacity, [1, 1, 0], [0, 0.75, 1])

        let glints = makeBurst(FXSpriteBank.spark, additive: true, count: count(24, s), over: 0.05)
        makeOmni(glints, radius: 0.15 * s)
        glints.particleVelocity = cg(4 * vs)
        glints.particleVelocityVariation = cg(2 * vs)
        glints.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        glints.particleLifeSpan = 0.5
        glints.particleLifeSpanVariation = 0.2
        glints.particleSize = cg(0.02 * s)
        glints.particleColor = FXSpriteBank.mix(iceColor, .white, 0.6)
        glints.particleIntensity = 3
        addCurve(glints, .opacity, [1, 0.3, 1, 0], [0, 0.3, 0.6, 1])

        let mist = makeBurst(FXSpriteBank.glow, additive: true, count: count(10, s), over: 0.06)
        makeOmni(mist, radius: 0.1 * s)
        mist.particleVelocity = cg(1 * vs)
        mist.particleVelocityVariation = 0.4
        mist.dampingFactor = 1.5
        mist.particleLifeSpan = 0.7
        mist.particleLifeSpanVariation = 0.2
        mist.particleSize = 1
        mist.particleColor = iceColor.withAlphaComponent(0.35)
        mist.particleIntensity = 0.8
        addCurve(mist, .size, [0.35 * s, 0.9 * s], [0, 1])
        addCurve(mist, .opacity, [0.8, 0], [0, 1])

        flashLight(at: p, in: scene, color: iceColor, intensity: 1500 * Swift.min(2, s), range: 4 * s, duration: 0.2)
        emit([shards, glints, mist], at: p, in: scene)
    }

    private static func spawnSmoke(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let smoke = makeBurst(FXSpriteBank.smoke, additive: false, count: count(18, s), over: 0.2)
        smoke.emitterShape = SCNSphere(radius: cg(0.15 * s))
        smoke.birthLocation = .volume
        smoke.birthDirection = .constant
        smoke.emittingDirection = vec(dir)
        smoke.spreadingAngle = 40
        smoke.particleVelocity = cg(0.8 * vs)
        smoke.particleVelocityVariation = cg(0.4 * vs)
        smoke.acceleration = SCNVector3(x: 0, y: 0.4, z: 0)
        smoke.dampingFactor = 0.8
        smoke.particleLifeSpan = 2.2
        smoke.particleLifeSpanVariation = 0.6
        smoke.particleSize = 1
        smoke.particleAngleVariation = 180
        smoke.particleAngularVelocityVariation = 30
        smoke.particleColor = tint ?? UIColor(red: 0.18, green: 0.18, blue: 0.2, alpha: 1)
        addCurve(smoke, .size, [0.5 * s, 1.4 * s], [0, 1])
        addCurve(smoke, .opacity, [0, 0.55, 0], [0, 0.18, 1])
        emit([smoke], at: p, in: scene)
    }

    private static func spawnDust(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let ring = makeBurst(FXSpriteBank.smoke, additive: false, count: count(26, s), over: 0.06)
        ring.emitterShape = SCNTube(innerRadius: cg(0.22 * s), outerRadius: cg(0.24 * s), height: cg(0.06 * s))
        ring.birthLocation = .surface
        ring.birthDirection = .surfaceNormal
        ring.particleVelocity = cg(2.4 * vs)
        ring.particleVelocityVariation = cg(1.0 * vs)
        ring.acceleration = SCNVector3(x: 0, y: 0.25, z: 0)
        ring.dampingFactor = 2.6
        ring.particleLifeSpan = 1.3
        ring.particleLifeSpanVariation = 0.4
        ring.particleSize = 1
        ring.particleAngleVariation = 180
        ring.particleAngularVelocityVariation = 40
        ring.particleColor = tint ?? UIColor(red: 0.27, green: 0.25, blue: 0.23, alpha: 0.55)
        addCurve(ring, .size, [0.3 * s, 1.05 * s], [0, 1])
        addCurve(ring, .opacity, [0, 1, 0], [0, 0.12, 1])

        let pebbles = makeBurst(FXSpriteBank.flake, additive: false, count: count(10, s), over: 0.04)
        pebbles.birthDirection = .constant
        pebbles.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        pebbles.spreadingAngle = 55
        pebbles.particleVelocity = cg(3 * vs)
        pebbles.particleVelocityVariation = cg(1.2 * vs)
        pebbles.acceleration = SCNVector3(x: 0, y: -12, z: 0)
        pebbles.particleLifeSpan = 0.7
        pebbles.particleLifeSpanVariation = 0.2
        pebbles.particleSize = cg(0.03 * s)
        pebbles.particleSizeVariation = cg(0.015 * s)
        pebbles.particleAngleVariation = 180
        pebbles.particleAngularVelocityVariation = 400
        pebbles.particleColor = UIColor(red: 0.16, green: 0.15, blue: 0.14, alpha: 1)
        addCurve(pebbles, .opacity, [1, 1, 0], [0, 0.8, 1])

        emit([ring, pebbles], at: p, in: scene)
    }

    private static func spawnShadowBurst(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let glowColor = tint ?? UIColor(red: 0.55, green: 0.12, blue: 1.0, alpha: 1)

        let dark = makeBurst(FXSpriteBank.smoke, additive: false, count: count(36, s), over: 0.06)
        makeOmni(dark, radius: 0.15 * s)
        dark.particleVelocity = cg(3.2 * vs)
        dark.particleVelocityVariation = cg(1.6 * vs)
        dark.dampingFactor = 2.4
        dark.particleLifeSpan = 1.0
        dark.particleLifeSpanVariation = 0.3
        dark.particleSize = 1
        dark.particleAngleVariation = 180
        dark.particleAngularVelocityVariation = 90
        dark.particleColor = UIColor(red: 0.03, green: 0.0, blue: 0.05, alpha: 0.85)
        addCurve(dark, .size, [0.3 * s, 1.1 * s], [0, 1])
        addCurve(dark, .opacity, [1, 0.8, 0], [0, 0.4, 1])

        let wisps = makeBurst(FXSpriteBank.glow, additive: true, count: count(40, s), over: 0.06)
        makeOmni(wisps, radius: 0.1 * s)
        wisps.particleVelocity = cg(4.5 * vs)
        wisps.particleVelocityVariation = cg(2 * vs)
        wisps.dampingFactor = 1.5
        wisps.particleLifeSpan = 0.6
        wisps.particleLifeSpanVariation = 0.2
        wisps.particleSize = cg(0.12 * s)
        wisps.particleSizeVariation = cg(0.05 * s)
        wisps.stretchFactor = 0.08
        wisps.particleColor = glowColor
        wisps.particleIntensity = 2.4
        addCurve(wisps, .opacity, [1, 0], [0, 1])

        let core = makeBurst(FXSpriteBank.glow, additive: true, count: 3, over: 0.04)
        core.particleVelocity = 0
        core.particleLifeSpan = 0.18
        core.particleSize = cg(0.9 * s)
        core.particleColor = glowColor
        core.particleIntensity = 2
        addCurve(core, .opacity, [1, 0], [0, 1])

        flashLight(at: p, in: scene, color: glowColor, intensity: 2400 * Swift.min(2, s), range: 6 * s, duration: 0.3)
        emit([dark, wisps, core], at: p, in: scene)
    }

    private static func spawnWebHit(_ p: SIMD3<Float>, _ dir: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 0.95, green: 0.97, blue: 1.0, alpha: 1)

        let splat = makeBurst(FXSpriteBank.web, additive: false, count: 2, over: 0.04)
        splat.sortingMode = .none
        splat.particleVelocity = 0
        splat.particleLifeSpan = 0.45
        splat.particleSize = 1
        splat.particleAngleVariation = 180
        splat.particleColor = c
        addCurve(splat, .size, [0.25 * s, 0.85 * s, 0.9 * s], [0, 0.25, 1])
        addCurve(splat, .opacity, [1, 1, 0], [0, 0.6, 1])

        let strands = makeBurst(FXSpriteBank.spark, additive: true, count: count(22, s), over: 0.04)
        strands.birthDirection = .constant
        strands.emittingDirection = vec(dir)
        strands.spreadingAngle = 70
        strands.particleVelocity = cg(5 * vs)
        strands.particleVelocityVariation = cg(2 * vs)
        strands.dampingFactor = 3
        strands.particleLifeSpan = 0.3
        strands.particleLifeSpanVariation = 0.1
        strands.particleSize = cg(0.015 * s)
        strands.stretchFactor = 0.12
        strands.particleColor = c
        strands.particleIntensity = 1.4
        addCurve(strands, .opacity, [1, 0], [0, 1])

        let puff = makeBurst(FXSpriteBank.glow, additive: false, count: count(6, s), over: 0.04)
        puff.birthDirection = .constant
        puff.emittingDirection = vec(dir)
        puff.spreadingAngle = 60
        puff.particleVelocity = cg(0.8 * vs)
        puff.dampingFactor = 2
        puff.particleLifeSpan = 0.35
        puff.particleSize = 1
        puff.particleColor = c.withAlphaComponent(0.35)
        addCurve(puff, .size, [0.2 * s, 0.5 * s], [0, 1])
        addCurve(puff, .opacity, [1, 0], [0, 1])

        emit([splat, strands, puff], at: p, in: scene)
    }

    private static func spawnRiftPortal(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let c = tint ?? defaultRiftColor
        let portal = makeRiftSwirl(color: c)
        portal.name = transientNodeName
        portal.simdPosition = p
        portal.simdScale = SIMD3<Float>(repeating: 0.01)
        scene.rootNode.addChildNode(portal)
        let open = SCNAction.scale(to: cg(s), duration: 0.35)
        open.timingMode = .easeOut
        let close = SCNAction.scale(to: 0.01, duration: 0.4)
        close.timingMode = .easeIn
        portal.runAction(.sequence([open, .wait(duration: 1.9), close, .removeFromParentNode()]))

        // Öffnungs-Stoß
        let vs = s.squareRoot()
        let wisps = makeBurst(FXSpriteBank.glow, additive: true, count: count(30, s), over: 0.08)
        makeOmni(wisps, radius: 0.3 * s)
        wisps.particleVelocity = cg(3.5 * vs)
        wisps.particleVelocityVariation = cg(1.5 * vs)
        wisps.dampingFactor = 2
        wisps.particleLifeSpan = 0.6
        wisps.particleLifeSpanVariation = 0.2
        wisps.particleSize = cg(0.14 * s)
        wisps.stretchFactor = 0.06
        wisps.particleColor = c
        wisps.particleIntensity = 2.2
        addCurve(wisps, .opacity, [1, 0], [0, 1])
        emit([wisps], at: p, in: scene)
    }

    private static func spawnElectric(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let c = tint ?? UIColor(red: 0.55, green: 0.8, blue: 1.0, alpha: 1)

        // flackernde Blitze über ~0.35 s
        let bolts = makeBurst(FXSpriteBank.bolt, additive: true, count: count(16, s), over: 0.35)
        bolts.emitterShape = SCNSphere(radius: cg(0.35 * s))
        bolts.birthLocation = .volume
        bolts.particleVelocity = 0
        bolts.particleLifeSpan = 0.09
        bolts.particleLifeSpanVariation = 0.05
        bolts.particleSize = cg(0.45 * s)
        bolts.particleSizeVariation = cg(0.2 * s)
        bolts.particleAngleVariation = 180
        bolts.particleColor = FXSpriteBank.mix(c, .white, 0.25)
        bolts.particleIntensity = 3.5
        bolts.particleIntensityVariation = 1.5

        let sparks = makeBurst(FXSpriteBank.spark, additive: true, count: count(30, s), over: 0.3)
        makeOmni(sparks, radius: 0.25 * s)
        sparks.particleVelocity = cg(5 * vs)
        sparks.particleVelocityVariation = cg(2.5 * vs)
        sparks.acceleration = SCNVector3(x: 0, y: -6, z: 0)
        sparks.particleLifeSpan = 0.3
        sparks.particleLifeSpanVariation = 0.15
        sparks.particleSize = cg(0.016 * s)
        sparks.stretchFactor = 0.05
        sparks.particleColor = FXSpriteBank.mix(c, .white, 0.5)
        sparks.particleIntensity = 3
        addCurve(sparks, .opacity, [1, 0], [0, 1])

        let haze = makeBurst(FXSpriteBank.glow, additive: true, count: 3, over: 0.05)
        haze.particleVelocity = 0
        haze.particleLifeSpan = 0.4
        haze.particleSize = cg(1.0 * s)
        haze.particleColor = c
        haze.particleIntensity = 1.2
        addCurve(haze, .opacity, [0.8, 0.3, 0.7, 0], [0, 0.3, 0.55, 1])

        flashLight(at: p, in: scene, color: c, intensity: 2200 * Swift.min(2, s), range: 5 * s, duration: 0.4, flicker: true)
        emit([bolts, sparks, haze], at: p, in: scene)
    }

    private static func spawnAsh(_ p: SIMD3<Float>, _ s: Float, _ tint: UIColor?, _ scene: SCNScene) {
        let vs = s.squareRoot()
        let flakes = makeBurst(FXSpriteBank.flake, additive: false, count: count(90, s), over: 0.25)
        flakes.emitterShape = SCNSphere(radius: cg(0.35 * s))
        flakes.birthLocation = .volume
        flakes.birthDirection = .constant
        flakes.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        flakes.spreadingAngle = 70
        flakes.particleVelocity = cg(1.2 * vs)
        flakes.particleVelocityVariation = cg(0.8 * vs)
        flakes.acceleration = SCNVector3(x: 0.1, y: -0.7, z: 0.05)
        flakes.dampingFactor = 0.9
        flakes.particleLifeSpan = 3.0
        flakes.particleLifeSpanVariation = 1.0
        flakes.particleSize = cg(0.045 * s)
        flakes.particleSizeVariation = cg(0.025 * s)
        flakes.particleAngleVariation = 180
        flakes.particleAngularVelocityVariation = 200
        flakes.particleColor = tint ?? UIColor(red: 0.16, green: 0.15, blue: 0.15, alpha: 0.95)
        flakes.particleColorVariation = SCNVector4(x: 0, y: 0, z: 0.3, w: 0)
        addCurve(flakes, .opacity, [0, 1, 1, 0], [0, 0.05, 0.7, 1])

        let glowing = makeBurst(FXSpriteBank.spark, additive: true, count: count(24, s), over: 0.25)
        glowing.emitterShape = SCNSphere(radius: cg(0.3 * s))
        glowing.birthLocation = .volume
        glowing.birthDirection = .constant
        glowing.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        glowing.spreadingAngle = 50
        glowing.particleVelocity = cg(1.5 * vs)
        glowing.particleVelocityVariation = 0.6
        glowing.acceleration = SCNVector3(x: 0, y: 0.4, z: 0)
        glowing.dampingFactor = 0.6
        glowing.particleLifeSpan = 1.5
        glowing.particleLifeSpanVariation = 0.6
        glowing.particleSize = cg(0.02 * s)
        glowing.particleColor = UIColor(red: 1.0, green: 0.45, blue: 0.1, alpha: 1)
        glowing.particleIntensity = 3
        addCurve(glowing, .opacity, [1, 0.6, 1, 0], [0, 0.3, 0.6, 1])

        let cloud = makeBurst(FXSpriteBank.smoke, additive: false, count: count(8, s), over: 0.2)
        cloud.emitterShape = SCNSphere(radius: cg(0.3 * s))
        cloud.birthLocation = .volume
        cloud.birthDirection = .constant
        cloud.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        cloud.spreadingAngle = 60
        cloud.particleVelocity = cg(0.6 * vs)
        cloud.dampingFactor = 0.8
        cloud.particleLifeSpan = 2.5
        cloud.particleLifeSpanVariation = 0.5
        cloud.particleSize = 1
        cloud.particleAngleVariation = 180
        cloud.particleColor = UIColor(red: 0.1, green: 0.1, blue: 0.1, alpha: 1)
        addCurve(cloud, .size, [0.5 * s, 1.6 * s], [0, 1])
        addCurve(cloud, .opacity, [0, 0.4, 0], [0, 0.2, 1])

        emit([flakes, glowing, cloud], at: p, in: scene)
    }

    // MARK: - Schleifende Systeme für Geschosse

    fileprivate static func trailSystem(color: UIColor, size: Float, dark: Bool) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = dark ? FXSpriteBank.smoke : FXSpriteBank.glow
        p.blendMode = dark ? .alpha : .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isAffectedByGravity = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(160 * countScale + 20)
        p.particleVelocity = 0
        p.particleLifeSpan = 0.22
        p.particleLifeSpanVariation = 0.05
        p.particleSize = 1
        p.particleColor = dark ? UIColor(red: 0.04, green: 0.0, blue: 0.06, alpha: 0.8) : color
        p.particleIntensity = dark ? 1 : 1.8
        let sz = Swift.max(0.01, size)
        FX.addCurve(p, .size, [sz, sz * 0.25], [0, 1])
        FX.addCurve(p, .opacity, [0.75, 0], [0, 1])
        return p
    }

    fileprivate static func flameLicks(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.fire
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(70 * countScale + 15)
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.55))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
        p.particleVelocity = CGFloat(r * 1.5)
        p.particleVelocityVariation = CGFloat(r)
        p.acceleration = SCNVector3(x: 0, y: 1.5, z: 0)
        p.particleLifeSpan = 0.32
        p.particleLifeSpanVariation = 0.1
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleAngularVelocityVariation = 180
        p.particleIntensity = 2.4
        FX.addCurve(p, .size, [r * 1.3, r * 0.5], [0, 1])
        FX.addColorCurve(p, FX.fireColors(color), [0, 0.25, 0.6, 1])
        return p
    }

    fileprivate static func darkWisps(radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.smoke
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(50 * countScale + 10)
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.5))
        p.birthLocation = .volume
        p.birthDirection = .random
        p.spreadingAngle = 180
        p.particleVelocity = 0.3
        p.particleVelocityVariation = 0.15
        p.particleLifeSpan = 0.45
        p.particleLifeSpanVariation = 0.1
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleColor = UIColor(red: 0.03, green: 0.0, blue: 0.05, alpha: 0.7)
        FX.addCurve(p, .size, [r * 1.2, r * 2.2], [0, 1])
        FX.addCurve(p, .opacity, [0.8, 0], [0, 1])
        return p
    }

    fileprivate static func risingSparks(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.spark
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(90 * countScale + 15)
        p.emitterShape = SCNCylinder(radius: CGFloat(r * 1.1), height: 0.02)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 20
        p.particleVelocity = 2.5
        p.particleVelocityVariation = 1
        p.particleLifeSpan = 0.45
        p.particleLifeSpanVariation = 0.15
        p.particleSize = CGFloat(r * 0.18)
        p.particleSizeVariation = CGFloat(r * 0.08)
        p.stretchFactor = 0.04
        p.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        p.particleIntensity = 2.4
        FX.addCurve(p, .opacity, [1, 0.8, 0], [0, 0.5, 1])
        return p
    }

    fileprivate static func groundDustTrail(radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.smoke
        p.blendMode = .alpha
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = false
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = CGFloat(25 * countScale + 5)
        p.emitterShape = SCNCylinder(radius: CGFloat(r), height: 0.05)
        p.birthLocation = .volume
        p.birthDirection = .constant
        p.emittingDirection = SCNVector3(x: 0, y: 1, z: 0)
        p.spreadingAngle = 40
        p.particleVelocity = 0.6
        p.particleVelocityVariation = 0.3
        p.dampingFactor = 1.2
        p.particleLifeSpan = 0.9
        p.particleLifeSpanVariation = 0.3
        p.particleSize = 1
        p.particleAngleVariation = 180
        p.particleColor = UIColor(red: 0.25, green: 0.23, blue: 0.21, alpha: 0.6)
        FX.addCurve(p, .size, [r * 0.8, r * 1.8], [0, 1])
        FX.addCurve(p, .opacity, [0, 0.6, 0], [0, 0.2, 1])
        return p
    }

    fileprivate static func crackle(color: UIColor, radius r: Float) -> SCNParticleSystem {
        let p = SCNParticleSystem()
        p.particleImage = FXSpriteBank.bolt
        p.blendMode = .additive
        p.sortingMode = .none
        p.isLightingEnabled = false
        p.isLocal = true
        p.loops = true
        p.emissionDuration = 1
        p.birthRate = 18
        p.emitterShape = SCNSphere(radius: CGFloat(r * 0.6))
        p.birthLocation = .volume
        p.particleVelocity = 0
        p.particleLifeSpan = 0.07
        p.particleLifeSpanVariation = 0.03
        p.particleSize = CGFloat(r * 2.2)
        p.particleSizeVariation = CGFloat(r * 0.8)
        p.particleAngleVariation = 180
        p.particleColor = FXSpriteBank.mix(color, .white, 0.3)
        p.particleIntensity = 3
        return p
    }
}

// MARK: - WebStrand

/// Dünne leuchtende Linie zwischen zwei Weltpunkten (Netz, Ketten, Ranken).
/// node an scene.rootNode (oder einen unskalierten Knoten) hängen und jeden Frame update(from:to:) aufrufen.
final class WebStrand {
    let node: SCNNode
    private let coreNode: SCNNode
    private let glowNode: SCNNode

    init(color: UIColor = .white, radius: Float = 0.012) {
        let r: Float = (radius.isFinite && radius > 0.0005) ? radius : 0.012
        let root = SCNNode()
        root.name = "fx.webStrand"
        root.castsShadow = false

        // Kern: Einheitszylinder (Höhe 1, entlang +Y) – Länge über simdScale.y
        let core = SCNCylinder(radius: CGFloat(r), height: 1)
        core.radialSegmentCount = 8
        core.heightSegmentCount = 1
        let coreMaterial = SCNMaterial()
        coreMaterial.lightingModel = .constant
        coreMaterial.diffuse.contents = color
        coreMaterial.emission.contents = color
        coreMaterial.emission.intensity = 0.6
        core.materials = [coreMaterial]
        let coreN = SCNNode(geometry: core)
        coreN.castsShadow = false
        root.addChildNode(coreN)

        // weicher Schimmer (additiv, breiter)
        let glow = SCNCylinder(radius: CGFloat(r * 3.2), height: 1)
        glow.radialSegmentCount = 8
        glow.heightSegmentCount = 1
        let glowMaterial = SCNMaterial()
        glowMaterial.lightingModel = .constant
        glowMaterial.diffuse.contents = FXSpriteBank.scaled(color, 0.22, alpha: 1)
        glowMaterial.blendMode = .add
        glowMaterial.writesToDepthBuffer = false
        glowMaterial.readsFromDepthBuffer = true
        glow.materials = [glowMaterial]
        let glowN = SCNNode(geometry: glow)
        glowN.castsShadow = false
        glowN.renderingOrder = 30
        glowN.isHidden = FX.quality == .performance
        root.addChildNode(glowN)

        root.simdScale = SIMD3<Float>(1, 0.0001, 1)
        node = root
        coreNode = coreN
        glowNode = glowN
    }

    /// Weltpositionen der beiden Enden.
    func update(from: SIMD3<Float>, to: SIMD3<Float>) {
        guard from.x.isFinite, from.y.isFinite, from.z.isFinite,
              to.x.isFinite, to.y.isFinite, to.z.isFinite else { return }
        let d = to - from
        let len = simd_length(d)
        node.simdWorldPosition = (from + to) * 0.5
        if len > 1e-5 {
            node.simdWorldOrientation = WebStrand.rotationFromUp(to: d / len)
        }
        node.simdScale = SIMD3<Float>(1, Swift.max(len, 0.0001), 1)
    }

    var isHidden: Bool {
        get { return node.isHidden }
        set { node.isHidden = newValue }
    }

    /// Quaternion, das +Y auf dir dreht (stabil auch bei exakt entgegengesetzter Richtung).
    static func rotationFromUp(to dir: SIMD3<Float>) -> simd_quatf {
        let up = SIMD3<Float>(0, 1, 0)
        let dp = simd_dot(up, dir)
        if dp > 0.99999 {
            return simd_quatf(angle: 0, axis: SIMD3<Float>(1, 0, 0))
        }
        if dp < -0.99999 {
            return simd_quatf(angle: Float.pi, axis: SIMD3<Float>(1, 0, 0))
        }
        return simd_quatf(from: up, to: dir)
    }
}

// MARK: - CameraShake

/// Trauma-basiertes Kamerawackeln: Amplitude = trauma², glattes Rauschen aus Sinus-Summen, Abbau ~1.2/s.
final class CameraShake {
    private(set) var trauma: Float = 0
    var maxTranslation: Float = 0.28      // Meter bei trauma = 1
    var maxRoll: Float = 0.07             // Radiant bei trauma = 1
    var decayPerSecond: Float = 1.2
    var frequency: Float = 24
    private var time: Float = 0

    init() {}

    func add(_ trauma: Float) {
        guard trauma.isFinite else { return }
        self.trauma = Swift.min(1, Swift.max(0, self.trauma + trauma))
    }

    func update(dt: Float) -> (offset: SIMD3<Float>, roll: Float) {
        let step: Float = (dt.isFinite && dt > 0) ? Swift.min(dt, 0.1) : 0
        time += step
        if time > 10_000 { time = 0 }
        trauma = Swift.max(0, trauma - decayPerSecond * step)
        let amp = trauma * trauma
        if amp < 0.0001 {
            return (offset: SIMD3<Float>(0, 0, 0), roll: 0)
        }
        let t = time * frequency
        let x = CameraShake.smoothNoise(t, seed: 1.3)
        let y = CameraShake.smoothNoise(t, seed: 7.9)
        let z = CameraShake.smoothNoise(t, seed: 3.7)
        let r = CameraShake.smoothNoise(t, seed: 5.1)
        let offset = SIMD3<Float>(x, y, z * 0.5) * (maxTranslation * amp)
        return (offset: offset, roll: r * maxRoll * amp)
    }

    func reset() {
        trauma = 0
        time = 0
    }

    /// Perlin-artiges, glattes Rauschen in etwa [-1, 1].
    private static func smoothNoise(_ t: Float, seed: Float) -> Float {
        let a = sin(t * 1.0 + seed * 12.9898)
        let b = sin(t * 2.17 + seed * 78.233) * 0.5
        let c = sin(t * 4.73 + seed * 37.719) * 0.25
        let d = sin(t * 0.61 + seed * 4.1) * 0.35
        return (a + b + c + d) / 2.1
    }
}

// MARK: - ProjectileVisual

/// Leuchtendes Geschoss (Orb / Feuerball / Netzkopf / Bodenwelle). Nur Optik – Bewegung macht der Controller.
/// Orientierungsunabhängig; bei .groundWave liegt der Ursprung auf Bodenhöhe.
final class ProjectileVisual {
    let node: SCNNode
    let style: SpecialKind

    init(color: UIColor, radius: Float, style: SpecialKind) {
        let r: Float = (radius.isFinite && radius > 0.02) ? Swift.min(radius, 3) : 0.2
        let root = SCNNode()
        root.name = "fx.projectile"
        root.castsShadow = false
        let dark = FXSpriteBank.luminance(color) < 0.12
        let glowColor: UIColor = dark ? UIColor(red: 0.5, green: 0.14, blue: 0.9, alpha: 1) : color

        switch style {
        case .projectile, .dashStrike, .teleportStrike, .counter:
            ProjectileVisual.buildOrb(on: root, color: color, glow: glowColor, radius: r, dark: dark)
        case .grabSlam:
            ProjectileVisual.buildOrb(on: root, color: color, glow: glowColor, radius: r, dark: dark)
            root.addParticleSystem(FX.crackle(color: glowColor, radius: r))
        case .pullIn:
            ProjectileVisual.buildHead(on: root, color: color, glow: glowColor, radius: r, dark: dark)
        case .groundWave:
            ProjectileVisual.buildWave(on: root, color: color, glow: glowColor, radius: r)
        }

        if FX.quality != .performance {
            let light = SCNLight()
            light.type = .omni
            light.color = glowColor
            light.intensity = dark ? 350 : 650
            light.attenuationStartDistance = 0
            light.attenuationEndDistance = CGFloat(Swift.max(3, r * 14))
            light.attenuationFalloffExponent = 2
            light.castsShadow = false
            let lightNode = SCNNode()
            lightNode.light = light
            if style == .groundWave {
                lightNode.simdPosition = SIMD3<Float>(0, r * 0.8, 0)
            }
            root.addChildNode(lightNode)
        }

        self.node = root
        self.style = style
    }

    private static func coreMaterial(_ color: UIColor, dark: Bool, boost: CGFloat) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .constant
        if dark {
            m.diffuse.contents = UIColor(red: 0.02, green: 0.0, blue: 0.04, alpha: 1)
        } else {
            let hot = FXSpriteBank.mix(color, .white, 0.7)
            m.diffuse.contents = hot
            m.emission.contents = hot
            m.emission.intensity = boost
        }
        return m
    }

    private static func addHalo(to parent: SCNNode, color: UIColor, size: Float, boost: Float) -> SCNNode {
        let image = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: color)
        let plane = SCNPlane(width: CGFloat(size), height: CGFloat(size))
        plane.materials = [FX.spriteMaterial(image, key: "glow#" + FXSpriteBank.key(color), boost: boost)]
        let halo = SCNNode(geometry: plane)
        halo.constraints = [SCNBillboardConstraint()]
        halo.castsShadow = false
        halo.renderingOrder = 55
        parent.addChildNode(halo)
        return halo
    }

    private static func buildOrb(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float, dark: Bool) {
        let segments = FX.quality == .performance ? 16 : 32
        let core = SCNSphere(radius: CGFloat(r * 0.5))
        core.segmentCount = segments
        core.materials = [ProjectileVisual.coreMaterial(color, dark: dark, boost: 1.6)]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        root.addChildNode(coreNode)

        let halo = ProjectileVisual.addHalo(to: root, color: glow, size: r * 4.4, boost: 1.8)
        let a1 = SCNAction.scale(to: 1.12, duration: 0.12)
        let a2 = SCNAction.scale(to: 0.92, duration: 0.14)
        halo.runAction(.repeatForever(.sequence([a1, a2])))

        // Energieringe
        let ringMaterial = FX.glowLineMaterial(glow, boost: 2.0)
        for i in 0..<2 {
            let torus = SCNTorus(ringRadius: CGFloat(r * (0.8 + 0.15 * Float(i))), pipeRadius: CGFloat(r * 0.045))
            torus.ringSegmentCount = FX.quality == .performance ? 24 : 48
            torus.pipeSegmentCount = 6
            torus.materials = [ringMaterial]
            let ring = SCNNode(geometry: torus)
            ring.castsShadow = false
            ring.simdEulerAngles = i == 0 ? SIMD3<Float>(1.1, 0, 0.4) : SIMD3<Float>(-0.6, 0, 1.2)
            let gimbal = SCNNode()
            gimbal.addChildNode(ring)
            let turn: CGFloat = i == 0 ? 1 : -1
            let spin = SCNAction.rotateBy(x: 0, y: CGFloat.pi * 2 * turn, z: 0, duration: i == 0 ? 0.45 : 0.6)
            gimbal.runAction(.repeatForever(spin))
            root.addChildNode(gimbal)
        }

        root.addParticleSystem(FX.trailSystem(color: glow, size: r * 1.3, dark: dark))
        if dark {
            root.addParticleSystem(FX.darkWisps(radius: r))
        } else if FXSpriteBank.isWarm(color) {
            root.addParticleSystem(FX.flameLicks(color: color, radius: r))
        }
    }

    private static func buildHead(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float, dark: Bool) {
        let material = ProjectileVisual.coreMaterial(color, dark: dark, boost: 1.2)
        let spinner = SCNNode()
        root.addChildNode(spinner)

        let core = SCNSphere(radius: CGFloat(r * 0.42))
        core.segmentCount = FX.quality == .performance ? 16 : 24
        core.materials = [material]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        spinner.addChildNode(coreNode)

        // sechs Stacheln (Kettenkopf / Netzkugel)
        let dirs: [SIMD3<Float>] = [
            SIMD3<Float>(1, 0, 0), SIMD3<Float>(-1, 0, 0),
            SIMD3<Float>(0, 1, 0), SIMD3<Float>(0, -1, 0),
            SIMD3<Float>(0, 0, 1), SIMD3<Float>(0, 0, -1)
        ]
        let spikeHeight = r * 0.75
        let cone = SCNCone(topRadius: 0, bottomRadius: CGFloat(r * 0.16), height: CGFloat(spikeHeight))
        cone.radialSegmentCount = 10
        cone.materials = [material]
        for d in dirs {
            let spike = SCNNode(geometry: cone)
            spike.castsShadow = false
            spike.simdOrientation = WebStrand.rotationFromUp(to: d)
            spike.simdPosition = d * (r * 0.42 + spikeHeight * 0.5)
            spinner.addChildNode(spike)
        }
        let spin = SCNAction.rotateBy(x: CGFloat.pi * 2, y: CGFloat.pi * 1.4, z: 0, duration: 0.5)
        spinner.runAction(.repeatForever(spin))

        _ = ProjectileVisual.addHalo(to: root, color: glow, size: r * 3.2, boost: 1.4)
        root.addParticleSystem(FX.trailSystem(color: glow, size: r * 0.9, dark: dark))
    }

    private static func buildWave(on root: SCNNode, color: UIColor, glow: UIColor, radius r: Float) {
        // leuchtende Kuppel (untere Hälfte steckt im Boden)
        let dome = SCNSphere(radius: CGFloat(r))
        dome.segmentCount = FX.quality == .performance ? 16 : 28
        let domeMaterial = SCNMaterial()
        domeMaterial.lightingModel = .constant
        let soft = FXSpriteBank.scaled(glow, 0.45, alpha: 1)
        domeMaterial.diffuse.contents = soft
        domeMaterial.emission.contents = soft
        domeMaterial.emission.intensity = 0.8
        domeMaterial.blendMode = .add
        domeMaterial.writesToDepthBuffer = false
        domeMaterial.readsFromDepthBuffer = true
        dome.materials = [domeMaterial]
        let domeNode = SCNNode(geometry: dome)
        domeNode.castsShadow = false
        domeNode.renderingOrder = 50
        domeNode.simdScale = SIMD3<Float>(1.3, 0.6, 1.3)
        root.addChildNode(domeNode)
        let grow = SCNAction.scale(by: 1.08, duration: 0.15)
        grow.timingMode = .easeInEaseOut
        domeNode.runAction(.repeatForever(.sequence([grow, grow.reversed()])))

        // heißer Kern
        let core = SCNSphere(radius: CGFloat(r * 0.45))
        core.segmentCount = 16
        core.materials = [ProjectileVisual.coreMaterial(color, dark: false, boost: 1.4)]
        let coreNode = SCNNode(geometry: core)
        coreNode.castsShadow = false
        coreNode.simdScale = SIMD3<Float>(1.4, 0.6, 1.4)
        root.addChildNode(coreNode)

        // Bodenglühen (flach)
        let image = FXSpriteBank.tinted(FXSpriteBank.glow, baseKey: "glow", color: glow)
        let plane = SCNPlane(width: CGFloat(r * 5), height: CGFloat(r * 5))
        plane.materials = [FX.spriteMaterial(image, key: "glow#" + FXSpriteBank.key(glow), boost: 1.5)]
        let groundGlow = SCNNode(geometry: plane)
        groundGlow.castsShadow = false
        groundGlow.renderingOrder = 45
        groundGlow.simdEulerAngles = SIMD3<Float>(-Float.pi / 2, 0, 0)
        groundGlow.simdPosition = SIMD3<Float>(0, 0.02, 0)
        root.addChildNode(groundGlow)

        root.addParticleSystem(FX.risingSparks(color: glow, radius: r))
        root.addParticleSystem(FX.groundDustTrail(radius: r))
        if FXSpriteBank.isWarm(color) {
            root.addParticleSystem(FX.flameLicks(color: color, radius: r))
        }
    }
}
