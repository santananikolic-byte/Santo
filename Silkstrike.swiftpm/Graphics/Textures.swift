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

// MARK: - Oberflächen (Fassaden, Asphalt, Beton, Metall, Fliesen, Ziegel, Blut)

extension ProceduralTextures {

    /// Eine Fassaden-Textur deckt facadeTileMeters x facadeTileMeters Meter ab (4 x 4 Fenster, 3 m Geschosse).
    /// MeshBuilder: uvScale = 1 / facadeTileMeters verwenden.
    static let facadeTileMeters: Float = 12

    /// style 0 = Glasbüro, 1 = Ziegel-Wohnhaus, 2 = Beton, 3 = Neon-Gewerbe. lit = true liefert die Leuchtkarte (Emission).
    static func facade(style: Int, lit: Bool) -> UIImage {
        let s = ((style % 4) + 4) % 4
        return cached("facade\(s)\(lit ? "L" : "D")") {
            let size = 512
            let px = CGFloat(size)
            var rng = Rand(seed: UInt64(0xFACADE + s * 977))
            let wall: TexRGB
            let frame: TexRGB
            let glass: TexRGB
            switch s {
            case 0: wall = TexRGB(0.16, 0.18, 0.21); frame = TexRGB(0.30, 0.32, 0.35); glass = TexRGB(0.07, 0.10, 0.14)
            case 1: wall = TexRGB(0.36, 0.18, 0.13); frame = TexRGB(0.55, 0.50, 0.44); glass = TexRGB(0.06, 0.07, 0.09)
            case 2: wall = TexRGB(0.38, 0.37, 0.35); frame = TexRGB(0.24, 0.24, 0.24); glass = TexRGB(0.08, 0.09, 0.10)
            default: wall = TexRGB(0.10, 0.09, 0.12); frame = TexRGB(0.20, 0.18, 0.24); glass = TexRGB(0.05, 0.05, 0.08)
            }
            let cols = 4
            let rows = 4
            let cellW = px / CGFloat(cols)
            let cellH = px / CGFloat(rows)
            let winW: CGFloat = s == 0 ? cellW * 0.92 : cellW * 0.58
            let winH: CGFloat = s == 0 ? cellH * 0.78 : cellH * 0.56
            return renderImage(width: size, height: size, opaque: true) { ctx in
                if lit {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                } else {
                    ctx.setFillColor(wall.color().cgColor)
                    ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                    drawFBM(ctx, size: px, rng: &rng, startCells: 4, octaves: 4, alpha: 0.18, blend: .overlay)
                    if s == 1 {
                        // Ziegelfugen
                        ctx.setStrokeColor(UIColor(white: 0.12, alpha: 0.35).cgColor)
                        ctx.setLineWidth(1)
                        var y: CGFloat = 0
                        var row = 0
                        while y < px {
                            ctx.move(to: CGPoint(x: 0, y: y)); ctx.addLine(to: CGPoint(x: px, y: y))
                            var x: CGFloat = row % 2 == 0 ? 0 : 8
                            while x < px { ctx.move(to: CGPoint(x: x, y: y)); ctx.addLine(to: CGPoint(x: x, y: y + 6)); x += 16 }
                            y += 6; row += 1
                        }
                        ctx.strokePath()
                    }
                    // Geschossbänder
                    ctx.setFillColor(frame.color(0.8).cgColor)
                    for r in 0..<rows {
                        ctx.fill(CGRect(x: 0, y: CGFloat(r) * cellH, width: px, height: s == 0 ? 6 : 10))
                    }
                }
                for r in 0..<rows {
                    for c in 0..<cols {
                        let x = CGFloat(c) * cellW + (cellW - winW) / 2
                        let y = CGFloat(r) * cellH + (cellH - winH) * 0.6
                        let rect = CGRect(x: x, y: y, width: winW, height: winH)
                        let isLit = rng.chance(s == 3 ? 0.55 : 0.38)
                        let warm = rng.chance(0.7)
                        let shade = rng.range(0.55, 1.0)
                        if lit {
                            guard isLit else { continue }
                            let base: UIColor = warm
                                ? UIColor(red: 1.0, green: 0.72, blue: 0.42, alpha: 1)
                                : (s == 3 ? UIColor(red: 0.95, green: 0.25, blue: 0.6, alpha: 1) : UIColor(red: 0.6, green: 0.8, blue: 1.0, alpha: 1))
                            ctx.saveGState()
                            ctx.clip(to: rect)
                            drawLinear(ctx, from: CGPoint(x: rect.midX, y: rect.minY), to: CGPoint(x: rect.midX, y: rect.maxY),
                                       colors: [base.withAlphaComponent(shade * 0.55), base.withAlphaComponent(shade)],
                                       locations: [0, 1])
                            // Silhouette von Möbeln / Jalousien
                            if rng.chance(0.4) {
                                ctx.setFillColor(UIColor(white: 0, alpha: 0.55).cgColor)
                                ctx.fill(CGRect(x: rect.minX + rect.width * rng.range(0.1, 0.6), y: rect.maxY - rect.height * 0.35,
                                                width: rect.width * 0.25, height: rect.height * 0.35))
                            }
                            ctx.restoreGState()
                        } else {
                            ctx.setFillColor(frame.color().cgColor)
                            ctx.fill(rect.insetBy(dx: -3, dy: -3))
                            ctx.setFillColor((isLit ? glass.color(1.6) : glass.color()).cgColor)
                            ctx.fill(rect)
                            // Spiegelung
                            ctx.setFillColor(UIColor(white: 1, alpha: 0.05).cgColor)
                            ctx.fill(CGRect(x: rect.minX, y: rect.minY, width: rect.width * 0.35, height: rect.height))
                            if s != 0 {
                                ctx.setFillColor(frame.color(0.7).cgColor)
                                ctx.fill(CGRect(x: rect.midX - 1.5, y: rect.minY, width: 3, height: rect.height))
                            }
                        }
                    }
                }
            }
        }
    }

    static func asphalt() -> UIImage {
        return cached("asphalt") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xA5FA17)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.11, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 5, alpha: 0.35, blend: .overlay)
                drawSpeckles(ctx, size: px, count: 2600, rng: &rng, minRadius: 0.4, maxRadius: 1.4,
                             gray: 0.05...0.35, alpha: 0.3...0.8)
                // Risse
                ctx.setStrokeColor(UIColor(white: 0.03, alpha: 0.8).cgColor)
                ctx.setLineWidth(1.2)
                for _ in 0..<7 {
                    var p = CGPoint(x: rng.unit() * px, y: rng.unit() * px)
                    ctx.move(to: p)
                    for _ in 0..<12 {
                        p = CGPoint(x: p.x + rng.range(-14, 14), y: p.y + rng.range(-14, 14))
                        ctx.addLine(to: p)
                    }
                }
                ctx.strokePath()
            }
        }
    }

    static func asphaltNormal() -> UIImage {
        return cached("asphaltN") {
            return normalMap(fromHeight: asphalt(), strength: 2.0)
        }
    }

    static func concrete() -> UIImage {
        return cached("concrete") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xC0C0)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.42, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 2, octaves: 5, alpha: 0.3, blend: .overlay)
                drawSpeckles(ctx, size: px, count: 1500, rng: &rng, minRadius: 0.5, maxRadius: 1.8,
                             gray: 0.2...0.6, alpha: 0.2...0.5)
                ctx.setStrokeColor(UIColor(white: 0.25, alpha: 0.6).cgColor)
                ctx.setLineWidth(2)
                ctx.stroke(CGRect(x: 1, y: 1, width: px - 2, height: px - 2))
                // Wasserflecken
                for _ in 0..<5 {
                    let x = rng.unit() * px
                    ctx.setFillColor(UIColor(white: 0.2, alpha: 0.12).cgColor)
                    ctx.fill(CGRect(x: x, y: 0, width: rng.range(6, 30), height: px))
                }
            }
        }
    }

    static func metalPanels() -> UIImage {
        return cached("metal") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0x3E7A1)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.5, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                drawFBM(ctx, size: px, rng: &rng, startCells: 4, octaves: 4, alpha: 0.2, blend: .overlay)
                let panel = px / 4
                ctx.setStrokeColor(UIColor(white: 0.18, alpha: 1).cgColor)
                ctx.setLineWidth(3)
                for i in 0...4 {
                    let v = CGFloat(i) * panel
                    ctx.move(to: CGPoint(x: v, y: 0)); ctx.addLine(to: CGPoint(x: v, y: px))
                    ctx.move(to: CGPoint(x: 0, y: v)); ctx.addLine(to: CGPoint(x: px, y: v))
                }
                ctx.strokePath()
                ctx.setFillColor(UIColor(white: 0.25, alpha: 1).cgColor)
                for i in 0..<4 {
                    for j in 0..<4 {
                        for k in 0..<4 {
                            let cx = CGFloat(i) * panel + (k % 2 == 0 ? 10 : panel - 10)
                            let cy = CGFloat(j) * panel + (k < 2 ? 10 : panel - 10)
                            ctx.fillEllipse(in: CGRect(x: cx - 3, y: cy - 3, width: 6, height: 6))
                        }
                    }
                }
                // Rost
                drawSpeckles(ctx, size: px, count: 400, rng: &rng, minRadius: 1, maxRadius: 5,
                             gray: 0.25...0.4, alpha: 0.15...0.35)
            }
        }
    }

    static func tiles() -> UIImage {
        return cached("tiles") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0x711E5)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.3, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                let t = px / 8
                for i in 0..<8 {
                    for j in 0..<8 {
                        let g = rng.range(0.62, 0.8)
                        ctx.setFillColor(UIColor(red: g * 0.92, green: g, blue: g * 0.95, alpha: 1).cgColor)
                        ctx.fill(CGRect(x: CGFloat(i) * t + 2, y: CGFloat(j) * t + 2, width: t - 4, height: t - 4))
                    }
                }
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 4, alpha: 0.3, blend: .multiply)
            }
        }
    }

    static func brick() -> UIImage {
        return cached("brick") {
            let n = 512
            let px = CGFloat(n)
            var rng = Rand(seed: 0xB21C)
            return renderImage(width: n, height: n, opaque: true) { ctx in
                ctx.setFillColor(UIColor(white: 0.22, alpha: 1).cgColor)
                ctx.fill(CGRect(x: 0, y: 0, width: px, height: px))
                let bh = px / 16
                let bw = px / 8
                for r in 0..<16 {
                    let off: CGFloat = r % 2 == 0 ? 0 : bw / 2
                    for c in -1..<9 {
                        let k = rng.range(0.75, 1.1)
                        ctx.setFillColor(UIColor(red: 0.42 * k, green: 0.19 * k, blue: 0.14 * k, alpha: 1).cgColor)
                        ctx.fill(CGRect(x: CGFloat(c) * bw + off + 2, y: CGFloat(r) * bh + 2, width: bw - 4, height: bh - 4))
                    }
                }
                drawFBM(ctx, size: px, rng: &rng, startCells: 3, octaves: 4, alpha: 0.25, blend: .overlay)
            }
        }
    }

    static func bloodSplat() -> UIImage {
        return cached("bloodSplat") {
            let n = 256
            let px = CGFloat(n)
            var rng = Rand(seed: 0xB100D)
            return renderImage(width: n, height: n, opaque: false) { ctx in
                let c = CGPoint(x: px / 2, y: px / 2)
                let red = UIColor(red: 0.32, green: 0.0, blue: 0.01, alpha: 0.95)
                ctx.setFillColor(red.cgColor)
                ctx.fillEllipse(in: CGRect(x: c.x - px * 0.28, y: c.y - px * 0.25, width: px * 0.56, height: px * 0.5))
                for _ in 0..<26 {
                    let a = rng.range(0, .pi * 2)
                    let d = rng.range(px * 0.15, px * 0.46)
                    let r = rng.range(2, 14)
                    ctx.fillEllipse(in: CGRect(x: c.x + cos(a) * d - r, y: c.y + sin(a) * d - r, width: r * 2, height: r * 2))
                }
            }
        }
    }
}
