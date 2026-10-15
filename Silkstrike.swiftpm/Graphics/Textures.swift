import Foundation
import UIKit
import CoreGraphics
import simd

// =====================================================================
//  ProceduralTextures – alle Texturen werden im Code erzeugt
//  (UIGraphicsImageRenderer / CoreGraphics), einmalig berechnet und gecacht.
//  Alle Kacheltexturen sind nahtlos (wrapS/wrapT = .repeat).
//
//  Maßstab (für MeshBuilder-uvScale):
//  - facade(): 4 Fensterachsen x 4 Stockwerke pro Kachel → uvScale 0.1 = 2,5 m pro Stockwerk
//  - brick(): 8 Ziegel x 24 Reihen pro Kachel (≈ 1,8 m) → uvScale ≈ 0.55
//  - concrete()/metalPanels(): 4 x 4 Platten pro Kachel → uvScale 0.1–0.25
//  - tiles(): 8 x 8 Fliesen pro Kachel → uvScale ≈ 0.6
//  - asphalt()/asphaltNormal(): ≈ 4 m Kachel → uvScale ≈ 0.25
// =====================================================================

enum ProceduralTextures {

    // MARK: - Cache

    private static var cache: [String: UIImage] = [:]

    private static func cached(_ key: String, _ make: () -> UIImage) -> UIImage {
        if let img = cache[key] { return img }
        let img = make()
        cache[key] = img
        return img
    }

    /// Gibt den Speicher aller erzeugten Texturen frei (z. B. bei Speicherwarnung).
    static func clearCache() {
        cache.removeAll()
    }

    // MARK: - Zufall (deterministisch, splitmix64)

    struct Rand {
        private var state: UInt64

        init(seed: UInt64) {
            state = seed &+ 0x9E37_79B9_7F4A_7C15
        }

        mutating func next() -> UInt64 {
            state = state &+ 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            return z ^ (z >> 31)
        }

        /// 0 ..< 1
        mutating func unit() -> CGFloat {
            return CGFloat(next() >> 11) / 9_007_199_254_740_992.0
        }

        mutating func unitF() -> Float {
            return Float(next() >> 40) / 16_777_216.0
        }

        mutating func range(_ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            return lo + (hi - lo) * unit()
        }

        /// 0 ..< n
        mutating func int(_ n: Int) -> Int {
            if n <= 1 { return 0 }
            return Int(next() % UInt64(n))
        }

        mutating func chance(_ p: CGFloat) -> Bool {
            return unit() < p
        }

        mutating func byte() -> UInt8 {
            return UInt8(truncatingIfNeeded: next() >> 56)
        }
    }

    /// Einfache RGB-Farbe für Rechnungen.
    struct TexRGB {
        var r: CGFloat
        var g: CGFloat
        var b: CGFloat

        init(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) {
            self.r = r
            self.g = g
            self.b = b
        }

        func color(_ k: CGFloat = 1, alpha: CGFloat = 1) -> UIColor {
            return UIColor(red: Swift.min(1, Swift.max(0, r * k)),
                           green: Swift.min(1, Swift.max(0, g * k)),
                           blue: Swift.min(1, Swift.max(0, b * k)),
                           alpha: alpha)
        }

        func mixed(_ o: TexRGB, _ t: CGFloat) -> TexRGB {
            return TexRGB(r + (o.r - r) * t, g + (o.g - g) * t, b + (o.b - b) * t)
        }
    }

    // MARK: - Zeichen-Helfer

    /// Bild mit Maßstab 1 (Pixel = Punkte), Standard-Farbraum.
    static func renderImage(width: Int, height: Int, opaque: Bool, _ draw: (CGContext) -> Void) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = opaque
        format.preferredRange = .standard
        let size = CGSize(width: Swift.max(1, width), height: Swift.max(1, height))
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { rc in
            draw(rc.cgContext)
        }
    }

    /// RGBA-Bytes (8 Bit, Zeile 0 = oben) → CGImage.
    static func makeCGImage(rgba: [UInt8], width: Int, height: Int, hasAlpha: Bool = false) -> CGImage? {
        guard width > 0, height > 0, rgba.count >= width * height * 4 else { return nil }
        let cfData = Data(rgba) as CFData
        guard let provider = CGDataProvider(data: cfData) else { return nil }
        let alphaInfo: CGImageAlphaInfo = hasAlpha ? .premultipliedLast : .noneSkipLast
        return CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                       bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                       bitmapInfo: CGBitmapInfo(rawValue: alphaInfo.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }

    /// Radialer Verlauf. extend = true füllt auch außerhalb des Radius mit der letzten Farbe.
    static func drawRadial(_ ctx: CGContext, center: CGPoint, radius: CGFloat,
                           colors: [UIColor], locations: [CGFloat], extend: Bool = false) {
        guard radius > 0, colors.count >= 2, colors.count == locations.count else { return }
        let cgColors = colors.map { $0.cgColor } as CFArray
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: locations) else { return }
        let options: CGGradientDrawingOptions = extend ? [.drawsAfterEndLocation] : []
        ctx.drawRadialGradient(gradient, startCenter: center, startRadius: 0,
                               endCenter: center, endRadius: radius, options: options)
    }

    /// Linearer Verlauf (füllt die gesamte Clip-Fläche).
    static func drawLinear(_ ctx: CGContext, from: CGPoint, to: CGPoint, colors: [UIColor], locations: [CGFloat]) {
        guard colors.count >= 2, colors.count == locations.count else { return }
        let cgColors = colors.map { $0.cgColor } as CFArray
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: locations) else { return }
        ctx.drawLinearGradient(gradient, start: from, end: to,
                               options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    }

    /// Ruft body für alle 9 Kachel-Versätze auf (nahtlose Features über die Bildkante).
    static func forEachWrap(_ size: CGFloat, _ body: (CGFloat, CGFloat) -> Void) {
        for oy in -1...1 {
            for ox in -1...1 {
                body(CGFloat(ox) * size, CGFloat(oy) * size)
            }
        }
    }

    /// Kachelbares Zufallsraster (cells x cells) mit 2 Pixel Wiederholungsrand für nahtloses Hochskalieren.
    static func randomGridImage(cells: Int, rng: inout Rand) -> UIImage? {
        let c = Swift.max(1, Swift.min(512, cells))
        let n = c + 4
        var values = [UInt8](repeating: 0, count: c * c)
        for i in 0..<(c * c) { values[i] = rng.byte() }
        var rgba = [UInt8](repeating: 255, count: n * n * 4)
        for y in 0..<n {
            let sy = ((y - 2) % c + c) % c
            for x in 0..<n {
                let sx = ((x - 2) % c + c) % c
                let v = values[sy * c + sx]
                let i = (y * n + x) * 4
                rgba[i] = v
                rgba[i + 1] = v
                rgba[i + 2] = v
            }
        }
        guard let cg = makeCGImage(rgba: rgba, width: n, height: n) else { return nil }
        return UIImage(cgImage: cg)
    }

    /// Eine Rausch-Oktave nahtlos über die ganze Fläche (weich interpoliert).
    static func drawNoiseOctave(_ ctx: CGContext, size: CGFloat, cells: Int, rng: inout Rand,
                                alpha: CGFloat, blend: CGBlendMode) {
        let c = Swift.max(1, Swift.min(512, cells))
        guard let img = randomGridImage(cells: c, rng: &rng) else { return }
        let cell = size / CGFloat(c)
        let n = CGFloat(c + 4)
        let rect = CGRect(x: -2.5 * cell, y: -2.5 * cell, width: n * cell, height: n * cell)
        ctx.saveGState()
        ctx.interpolationQuality = .high
        img.draw(in: rect, blendMode: blend, alpha: alpha)
        ctx.restoreGState()
    }

    /// Fraktales Rauschen (mehrere Oktaven), z. B. für Flecken, Schmutz, Wolken.
    static func drawFBM(_ ctx: CGContext, size: CGFloat, rng: inout Rand, startCells: Int, octaves: Int,
                        alpha: CGFloat, blend: CGBlendMode, persistence: CGFloat = 0.62) {
        var cells = Swift.max(1, startCells)
        var a = alpha
        for _ in 0..<Swift.max(1, octaves) {
            drawNoiseOctave(ctx, size: size, cells: cells, rng: &rng, alpha: a, blend: blend)
            cells = Swift.min(512, cells * 2)
            a *= persistence
        }
    }

    /// Viele kleine Punkte (Körnung, Zuschlagstoffe, Poren).
    static func drawSpeckles(_ ctx: CGContext, size: CGFloat, count: Int, rng: inout Rand,
                             minRadius: CGFloat, maxRadius: CGFloat, gray: ClosedRange<CGFloat>, alpha: ClosedRange<CGFloat>) {
        guard count > 0 else { return }
        for _ in 0..<count {
            let x = rng.unit() * size
            let y = rng.unit() * size
            let r = rng.range(minRadius, maxRadius)
            let g = rng.range(gray.lowerBound, gray.upperBound)
            let a = rng.range(alpha.lowerBound, alpha.upperBound)
            ctx.setFillColor(UIColor(white: g, alpha: a).cgColor)
            ctx.fillEllipse(in: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2))
        }
    }

    /// Mittelgraues Pixelrauschen (gegen Farbabstufungen in dunklen Verläufen).
    static func ditherOverlay() -> UIImage {
        return cached("dither") {
            let n = 512
            var rng = Rand(seed: 0xD17E)
            var rgba = [UInt8](repeating: 255, count: n * n * 4)
            for i in 0..<(n * n) {
                let v = rng.byte()
                rgba[i * 4] = v
                rgba[i * 4 + 1] = v
                rgba[i * 4 + 2] = v
            }
            if let cg = makeCGImage(rgba: rgba, width: n, height: n) {
                return UIImage(cgImage: cg)
            }
            return renderImage(width: 4, height: 4, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: 4, height: 4))
            }
        }
    }

    private static func normalByte(_ v: Float) -> UInt8 {
        let x = v * 127.5 + 127.5
        if !(x > 0) { return 0 }
        if x >= 255 { return 255 }
        return UInt8(x)
    }

    /// Flache Normal-Map (128, 128, 255).
    static func flatNormal() -> UIImage {
        return cached("flatNormal") {
            renderImage(width: 4, height: 4, opaque: true) { ctx in
                ctx.setFillColor(UIColor(red: 0.5, green: 0.5, blue: 1.0, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: 4, height: 4))
            }
        }
    }

    /// Normal-Map aus einem Höhenbild (hell = hoch), nahtlos per Sobel-Filter.
    /// Konvention: Grün = +V nach oben (OpenGL/SceneKit). strength ≈ 2 ... 8.
    static func normalMap(fromHeight image: UIImage, strength: Float) -> UIImage {
        guard let cg = image.cgImage else { return flatNormal() }
        let w = cg.width
        let h = cg.height
        guard w > 2, h > 2, w <= 4096, h <= 4096 else { return flatNormal() }
        var gray = [UInt8](repeating: 128, count: w * h)
        let drawn: Bool = gray.withUnsafeMutableBytes { raw -> Bool in
            guard let base = raw.baseAddress,
                  let ctx = CGContext(data: base, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                                      space: CGColorSpaceCreateDeviceGray(),
                                      bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return false }
            ctx.interpolationQuality = .none
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        if !drawn { return flatNormal() }

        let k = strength / (255 * 4)
        var out = [UInt8](repeating: 255, count: w * h * 4)
        gray.withUnsafeBufferPointer { g in
            out.withUnsafeMutableBufferPointer { o in
                for y in 0..<h {
                    let ym = ((y - 1 + h) % h) * w
                    let y0 = y * w
                    let yp = ((y + 1) % h) * w
                    for x in 0..<w {
                        let xm = (x - 1 + w) % w
                        let xp = (x + 1) % w
                        let tl = Float(g[ym + xm])
                        let tc = Float(g[ym + x])
                        let tr = Float(g[ym + xp])
                        let ml = Float(g[y0 + xm])
                        let mr = Float(g[y0 + xp])
                        let bl = Float(g[yp + xm])
                        let bc = Float(g[yp + x])
                        let br = Float(g[yp + xp])
                        let dx = (tr + 2 * mr + br) - (tl + 2 * ml + bl)
                        let dy = (bl + 2 * bc + br) - (tl + 2 * tc + tr)
                        let n = simd_normalize(SIMD3<Float>(-dx * k, dy * k, 1))
                        let i = (y0 + x) * 4
                        o[i] = ProceduralTextures.normalByte(n.x)
                        o[i + 1] = ProceduralTextures.normalByte(n.y)
                        o[i + 2] = ProceduralTextures.normalByte(n.z)
                        o[i + 3] = 255
                    }
                }
            }
        }
        guard let result = makeCGImage(rgba: out, width: w, height: h) else { return flatNormal() }
        return UIImage(cgImage: result)
    }

    // MARK: - Einfache Texturen

    /// Nahtloses fraktales Graustufen-Rauschen.
    static func noise(size: Int, seed: UInt64) -> UIImage {
        let px = Swift.max(16, Swift.min(2048, size))
        return cached("noise-\(px)-\(seed)") {
            renderImage(width: px, height: px, opaque: true) { ctx in
                var rng = Rand(seed: seed)
                let s = CGFloat(px)
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
                ProceduralTextures.drawNoiseOctave(ctx, size: s, cells: 4, rng: &rng, alpha: 1, blend: .normal)
                var cells = 8
                var a: CGFloat = 0.6
                while cells <= Swift.min(256, px / 2) {
                    ProceduralTextures.drawNoiseOctave(ctx, size: s, cells: cells, rng: &rng, alpha: a, blend: .overlay)
                    cells *= 2
                    a *= 0.72
                }
            }
        }
    }

    /// Weicher Leuchtpunkt für Partikel (heller Kern, sanfter Abfall, transparent).
    static func radialGlow(color: UIColor) -> UIImage {
        var r: CGFloat = 1
        var g: CGFloat = 1
        var b: CGFloat = 1
        var a: CGFloat = 1
        if !color.getRed(&r, green: &g, blue: &b, alpha: &a) {
            r = 1; g = 1; b = 1
        }
        r = Swift.min(1, Swift.max(0, r))
        g = Swift.min(1, Swift.max(0, g))
        b = Swift.min(1, Swift.max(0, b))
        let key = "glow-\(Int(r * 255))-\(Int(g * 255))-\(Int(b * 255))"
        return cached(key) {
            renderImage(width: 128, height: 128, opaque: false) { ctx in
                let base = TexRGB(r, g, b)
                let core = base.mixed(TexRGB(1, 1, 1), 0.55)
                ProceduralTextures.drawRadial(ctx, center: CGPoint(x: 64, y: 64), radius: 64,
                                              colors: [core.color(1, alpha: 1),
                                                       base.color(1, alpha: 0.82),
                                                       base.color(1, alpha: 0.42),
                                                       base.color(1, alpha: 0.16),
                                                       base.color(1, alpha: 0.05),
                                                       base.color(1, alpha: 0)],
                                              locations: [0, 0.1, 0.25, 0.45, 0.7, 1])
            }
        }
    }

    /// Weiße Scheibe mit weichem Rand (Partikel, Decals) – mit particleColor einfärben.
    static func softDisc() -> UIImage {
        return cached("softDisc") {
            renderImage(width: 128, height: 128, opaque: false) { ctx in
                ProceduralTextures.drawRadial(ctx, center: CGPoint(x: 64, y: 64), radius: 63,
                                              colors: [UIColor(white: 1, alpha: 1),
                                                       UIColor(white: 1, alpha: 0.95),
                                                       UIColor(white: 1, alpha: 0.5),
                                                       UIColor(white: 1, alpha: 0)],
                                              locations: [0, 0.5, 0.78, 1])
            }
        }
    }

    /// Äquirektanguläres Himmelsbild (2:1), Horizont in der Bildmitte.
    static func skyGradient(top: UIColor, horizon: UIColor, bottom: UIColor) -> UIImage {
        let key = "skyGrad-\(colorKey(top))-\(colorKey(horizon))-\(colorKey(bottom))"
        return cached(key) {
            renderImage(width: 512, height: 256, opaque: true) { ctx in
                let mid = horizon.blended3(with: top, t: 0.55)
                let low = horizon.blended3(with: bottom, t: 0.6)
                ProceduralTextures.drawLinear(ctx, from: CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 256),
                                              colors: [top, mid, horizon, low, bottom],
                                              locations: [0, 0.3, 0.5, 0.56, 1])
                ctx.interpolationQuality = .none
                ProceduralTextures.ditherOverlay().draw(in: CGRect(x: 0, y: 0, width: 512, height: 512),
                                                        blendMode: .softLight, alpha: 0.15)
            }
        }
    }

    private static func colorKey(_ c: UIColor) -> String {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 0
        if !c.getRed(&r, green: &g, blue: &b, alpha: &a) { return "x" }
        return "\(Int(r * 255))_\(Int(g * 255))_\(Int(b * 255))"
    }
}

extension UIColor {
    /// Lineare Mischung (eindeutiger Name, da Core/MathUtils bereits `blended(with:t:)` definiert).
    fileprivate func blended3(with other: UIColor, t: CGFloat) -> UIColor {
        var r1: CGFloat = 0, g1: CGFloat = 0, b1: CGFloat = 0, a1: CGFloat = 0
        var r2: CGFloat = 0, g2: CGFloat = 0, b2: CGFloat = 0, a2: CGFloat = 0
        _ = getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        _ = other.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)
        return UIColor(red: r1 + (r2 - r1) * t, green: g1 + (g2 - g1) * t,
                       blue: b1 + (b2 - b1) * t, alpha: a1 + (a2 - a1) * t)
    }
}
