import Foundation
import UIKit
import simd

// =====================================================================
//  SILKSTRIKE – Mathe-Werkzeuge
//  Der EINZIGE Ort für diese globalen Funktionsnamen (siehe SPEC).
//
//  Konventionen im ganzen Spiel:
//  - Y zeigt nach oben, Figuren schauen lokal nach +Z.
//  - Yaw = Drehung um +Y (simdEulerAngles.y), alle Winkel in Radiant.
//  - Richtung aus Yaw: (sin yaw, 0, cos yaw)  ·  Yaw aus Richtung: atan2(x, z)
// =====================================================================

// MARK: - Skalare

/// Begrenzt v auf [lo, hi]. NaN wird zu lo.
func clampf(_ v: Float, _ lo: Float, _ hi: Float) -> Float {
    if v.isNaN { return lo }
    return Swift.min(Swift.max(v, lo), hi)
}

/// Lineare Interpolation (t wird NICHT begrenzt).
func lerpf(_ a: Float, _ b: Float, _ t: Float) -> Float {
    return a + (b - a) * t
}

/// Lineare Interpolation für Vektoren (t wird NICHT begrenzt).
func lerp3(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ t: Float) -> SIMD3<Float> {
    return a + (b - a) * t
}

/// Interner Faktor für bildratenunabhängiges Glätten: 1 - e^(-λ·dt), immer in [0, 1].
private func silkMathDampAlpha(_ lambda: Float, _ dt: Float) -> Float {
    let l = Swift.max(0, lambda)
    let d = Swift.max(0, dt)
    let a = 1 - expf(-l * d)
    if !a.isFinite { return 1 }
    return Swift.min(Swift.max(a, 0), 1)
}

/// Exponentielles Glätten, unabhängig von der Bildrate.
/// lambda ≈ Reaktionsgeschwindigkeit in 1/s (4 = weich, 10 = zügig, 25 = fast sofort).
func damp(_ current: Float, _ target: Float, lambda: Float, dt: Float) -> Float {
    return lerpf(current, target, silkMathDampAlpha(lambda, dt))
}

/// Exponentielles Glätten für Vektoren (Kamera, Positionen).
func damp3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, lambda: Float, dt: Float) -> SIMD3<Float> {
    return lerp3(current, target, silkMathDampAlpha(lambda, dt))
}

/// Wie damp, aber für Winkel: nimmt immer den kürzeren Weg über ±π. Ergebnis in (-π, π].
func dampAngle(_ current: Float, _ target: Float, lambda: Float, dt: Float) -> Float {
    let delta = wrapAngle(target - current)
    return wrapAngle(current + delta * silkMathDampAlpha(lambda, dt))
}

/// Normalisiert einen Winkel auf (-π, π].
func wrapAngle(_ a: Float) -> Float {
    guard a.isFinite else { return 0 }
    let twoPi = Float.pi * 2
    var r = (a + Float.pi).truncatingRemainder(dividingBy: twoPi)
    if r <= 0 { r += twoPi }
    return r - Float.pi
}

func deg2rad(_ d: Float) -> Float {
    return d * Float.pi / 180
}

func rad2deg(_ r: Float) -> Float {
    return r * 180 / Float.pi
}

/// Umkehrung von lerpf: liefert t, sodass lerpf(a, b, t) == v (nicht begrenzt). a == b → 0.
func inverseLerpf(_ a: Float, _ b: Float, _ v: Float) -> Float {
    let d = b - a
    if Swift.abs(d) < 1e-12 { return 0 }
    return (v - a) / d
}

/// Bildet v von [inLo, inHi] auf [outLo, outHi] ab und begrenzt das Ergebnis auf diesen Bereich.
func remapClampedf(_ v: Float, _ inLo: Float, _ inHi: Float, _ outLo: Float, _ outHi: Float) -> Float {
    let t = clampf(inverseLerpf(inLo, inHi, v), 0, 1)
    return lerpf(outLo, outHi, t)
}

/// Weiche S-Kurve (Hermite) zwischen edge0 und edge1, Ergebnis 0...1.
func smoothRampf(_ edge0: Float, _ edge1: Float, _ x: Float) -> Float {
    let t = clampf(inverseLerpf(edge0, edge1, x), 0, 1)
    return t * t * (3 - 2 * t)
}

/// Bewegt current höchstens um maxDelta in Richtung target (kein Überschießen).
func moveTowardf(_ current: Float, _ target: Float, maxDelta: Float) -> Float {
    let diff = target - current
    let step = Swift.max(0, maxDelta)
    if Swift.abs(diff) <= step { return target }
    return current + (diff > 0 ? step : -step)
}

/// Kritisch gedämpfte Feder (wie Unitys SmoothDamp). velocity wird mitgeführt.
/// smoothTime ≈ Zeit in Sekunden, um das Ziel ungefähr zu erreichen.
func smoothDampf(_ current: Float, _ target: Float, velocity: inout Float, smoothTime: Float, dt: Float) -> Float {
    guard dt > 0 else { return current }
    let st = Swift.max(0.0001, smoothTime)
    let omega = 2 / st
    let x = omega * dt
    let expo = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    let change = current - target
    let temp = (velocity + omega * change) * dt
    velocity = (velocity - omega * temp) * expo
    var output = target + (change + temp) * expo
    // Nicht über das Ziel hinausschießen
    if (target - current > 0) == (output > target) {
        output = target
        velocity = 0
    }
    if !output.isFinite || !velocity.isFinite {
        velocity = 0
        return target
    }
    return output
}

/// Federnder Pop-Effekt für UI/Kamera: 0 → 1 mit leichtem Überschwingen.
func easeOutBackf(_ t: Float) -> Float {
    let x = clampf(t, 0, 1)
    let c1: Float = 1.70158
    let c3: Float = c1 + 1
    let u = x - 1
    return 1 + c3 * u * u * u + c1 * u * u
}

/// Pulsiert zwischen 0 und 1 (z.B. leuchtende Details). frequency in Hz.
func pulse01(_ time: Float, frequency: Float) -> Float {
    return 0.5 + 0.5 * sinf(time * frequency * Float.pi * 2)
}

// MARK: - Vektoren

/// Länge in der XZ-Ebene (ignoriert Y).
func horizontalLength(_ v: SIMD3<Float>) -> Float {
    return (v.x * v.x + v.z * v.z).squareRoot()
}

/// Projiziert auf die Bodenebene (y = 0).
func flatten(_ v: SIMD3<Float>) -> SIMD3<Float> {
    return SIMD3<Float>(v.x, 0, v.z)
}

/// Normalisiert sicher; bei (fast) Nullvektor oder NaN wird fallback zurückgegeben.
func safeNormalize(_ v: SIMD3<Float>, fallback: SIMD3<Float> = SIMD3<Float>(0, 0, 1)) -> SIMD3<Float> {
    let len2 = simd_length_squared(v)
    if len2 > 1e-12 && len2.isFinite {
        return v / len2.squareRoot()
    }
    return fallback
}

/// 2D-Variante von safeNormalize (z.B. für Stick-Eingaben).
func safeNormalize2(_ v: SIMD2<Float>, fallback: SIMD2<Float> = SIMD2<Float>(0, 1)) -> SIMD2<Float> {
    let len2 = simd_length_squared(v)
    if len2 > 1e-12 && len2.isFinite {
        return v / len2.squareRoot()
    }
    return fallback
}

/// Bewegt einen Punkt höchstens um maxDelta Meter in Richtung target.
func moveToward3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, maxDelta: Float) -> SIMD3<Float> {
    let delta = target - current
    let dist = simd_length(delta)
    let step = Swift.max(0, maxDelta)
    if dist <= step || dist < 1e-6 || !dist.isFinite { return target }
    return current + delta * (step / dist)
}

/// Kritisch gedämpfte Feder für Vektoren (Kamera-Follow ohne Ruckeln).
func smoothDamp3(_ current: SIMD3<Float>, _ target: SIMD3<Float>, velocity: inout SIMD3<Float>, smoothTime: Float, dt: Float) -> SIMD3<Float> {
    guard dt > 0 else { return current }
    let st = Swift.max(0.0001, smoothTime)
    let omega = 2 / st
    let x = omega * dt
    let expo = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    let change = current - target
    let temp = (velocity + change * omega) * dt
    velocity = (velocity - temp * omega) * expo
    var output = target + (change + temp) * expo
    // Überschießen verhindern
    if simd_dot(target - current, output - target) > 0 {
        output = target
        velocity = SIMD3<Float>(0, 0, 0)
    }
    if !(output.x.isFinite && output.y.isFinite && output.z.isFinite) {
        velocity = SIMD3<Float>(0, 0, 0)
        return target
    }
    return output
}

/// Yaw (Drehung um +Y), mit dem eine nach +Z schauende Figur in Richtung dir blickt.
func yawOfDirection(_ dir: SIMD3<Float>) -> Float {
    if Swift.abs(dir.x) < 1e-9 && Swift.abs(dir.z) < 1e-9 { return 0 }
    return atan2f(dir.x, dir.z)
}

/// Horizontale Blickrichtung zu einem Yaw (Gegenstück zu yawOfDirection).
func directionFromYaw(_ yaw: Float) -> SIMD3<Float> {
    return SIMD3<Float>(sinf(yaw), 0, cosf(yaw))
}

/// Dreht v um die Y-Achse (gleiche Richtung wie simdEulerAngles.y).
func rotateY3(_ v: SIMD3<Float>, _ angle: Float) -> SIMD3<Float> {
    let c = cosf(angle)
    let s = sinf(angle)
    return SIMD3<Float>(v.x * c + v.z * s, v.y, -v.x * s + v.z * c)
}

/// Quaternion für eine reine Yaw-Drehung (für simdOrientation).
func yawQuat(_ yaw: Float) -> simd_quatf {
    return simd_quatf(angle: yaw, axis: SIMD3<Float>(0, 1, 0))
}

/// Nächster Punkt auf der Strecke a–b zu p.
func closestPointOnSegment3(_ p: SIMD3<Float>, _ a: SIMD3<Float>, _ b: SIMD3<Float>) -> SIMD3<Float> {
    let ab = b - a
    let len2 = simd_length_squared(ab)
    if len2 < 1e-12 { return a }
    let t = clampf(simd_dot(p - a, ab) / len2, 0, 1)
    return a + ab * t
}

// MARK: - Zufall (System-Zufall, nicht deterministisch)

/// Gleichverteilte Zufallszahl in [lo, hi). Bei hi <= lo wird lo geliefert.
func randf(_ lo: Float, _ hi: Float) -> Float {
    if !lo.isFinite || !hi.isFinite { return lo.isFinite ? lo : 0 }
    if hi <= lo { return lo }
    return Float.random(in: lo..<hi)
}

/// Gleichverteilter Einheitsvektor auf der Kugel.
func randUnit3() -> SIMD3<Float> {
    let z = Float.random(in: -1...1)
    let phi = Float.random(in: 0..<(Float.pi * 2))
    let r = Swift.max(0, 1 - z * z).squareRoot()
    return SIMD3<Float>(r * cosf(phi), r * sinf(phi), z)
}

/// true mit Wahrscheinlichkeit p (0...1).
func randChance(_ p: Float) -> Bool {
    return Float.random(in: 0..<1) < p
}

/// Zufälliges Vorzeichen: -1 oder +1.
func randSignf() -> Float {
    return Bool.random() ? 1 : -1
}

/// Zufälliger Punkt auf einer Kreisscheibe in der XZ-Ebene (gleichmäßig verteilt, y = 0).
func randOnDiscXZ(_ radius: Float) -> SIMD3<Float> {
    let r = Swift.max(0, radius) * Float.random(in: 0...1).squareRoot()
    let a = Float.random(in: 0..<(Float.pi * 2))
    return SIMD3<Float>(r * cosf(a), 0, r * sinf(a))
}

// MARK: - Deterministischer Zufall

/// Deterministischer Zufallsgenerator (SplitMix64): gleiche Seed → gleiche Stadt / gleiche Texturen.
/// Ist auch ein RandomNumberGenerator, also nutzbar mit
/// `Int.random(in: 0...3, using: &rng)` oder `array.shuffled(using: &rng)`.
struct SeededRandom: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed ^ 0x2545_F491_4F6C_DD1D
        _ = silkNextRaw()
    }

    mutating func next() -> UInt64 {
        return silkNextRaw()
    }

    /// SplitMix64-Schritt (eindeutiger Name, damit es keine Überladungs-Mehrdeutigkeit
    /// mit den generischen next()-Varianten von RandomNumberGenerator gibt).
    private mutating func silkNextRaw() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    /// Gleichverteilt in [lo, hi).
    mutating func float(_ lo: Float, _ hi: Float) -> Float {
        let u = Float(silkNextRaw() >> 40) * (1.0 / 16_777_216.0)   // 24 Bit → [0, 1)
        return lo + (hi - lo) * u
    }

    /// Ganzzahl im HALBOFFENEN Bereich lo ..< hi (hi exklusiv – sicher für Array-Indizes:
    /// `items[rng.int(0, items.count)]`). Bei hi <= lo wird lo geliefert.
    /// Für inklusive Bereiche: `Int.random(in: a...b, using: &rng)`.
    mutating func int(_ lo: Int, _ hi: Int) -> Int {
        guard hi > lo else { return lo }
        let span = UInt64(bitPattern: Int64(hi &- lo))
        return lo &+ Int(truncatingIfNeeded: silkNextRaw() % span)
    }

    /// true mit Wahrscheinlichkeit p (0...1).
    mutating func chance(_ p: Float) -> Bool {
        return float(0, 1) < p
    }

    /// -1 oder +1.
    mutating func signf() -> Float {
        return (silkNextRaw() & 1) == 0 ? -1 : 1
    }

    /// Zufälliges Element oder nil bei leerem Array.
    mutating func pick<T>(_ items: [T]) -> T? {
        if items.isEmpty { return nil }
        return items[int(0, items.count)]
    }

    /// Gleichverteilter Einheitsvektor (deterministisch).
    mutating func unit3() -> SIMD3<Float> {
        let z = float(-1, 1)
        let phi = float(0, Float.pi * 2)
        let r = Swift.max(0, 1 - z * z).squareRoot()
        return SIMD3<Float>(r * cosf(phi), r * sinf(phi), z)
    }
}

// MARK: - Farben

extension UIColor {
    /// RGBA-Komponenten in jedem Farbraum (Graustufen, sRGB, erweitert). Nur intern.
    private func silkMathRGBA() -> (r: CGFloat, g: CGFloat, b: CGFloat, a: CGFloat) {
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 1
        if getRed(&r, green: &g, blue: &b, alpha: &a) {
            return (r, g, b, a)
        }
        var w: CGFloat = 0
        if getWhite(&w, alpha: &a) {
            return (w, w, w, a)
        }
        if let comps = cgColor.components, comps.count >= 3 {
            let alpha: CGFloat = comps.count >= 4 ? comps[3] : 1
            return (comps[0], comps[1], comps[2], alpha)
        }
        return (0, 0, 0, 1)
    }

    /// Mischt mit einer anderen Farbe. t = 0 → self, t = 1 → other.
    func blended(with other: UIColor, t: CGFloat) -> UIColor {
        let k = Swift.max(0, Swift.min(1, t))
        let c0 = silkMathRGBA()
        let c1 = other.silkMathRGBA()
        return UIColor(red: c0.r + (c1.r - c0.r) * k,
                       green: c0.g + (c1.g - c0.g) * k,
                       blue: c0.b + (c1.b - c0.b) * k,
                       alpha: c0.a + (c1.a - c0.a) * k)
    }

    /// Helligkeit multiplizieren (0.5 = halb so hell, 1.5 = heller).
    /// Wird die Farbe dabei "zu hell", wandert sie Richtung Weiß (gut für Leuchteffekte).
    func withBrightness(_ factor: CGFloat) -> UIColor {
        let f = Swift.max(0, factor)
        var h: CGFloat = 0
        var s: CGFloat = 0
        var br: CGFloat = 0
        var a: CGFloat = 1
        if getHue(&h, saturation: &s, brightness: &br, alpha: &a) {
            var nb = br * f
            var ns = s
            if nb > 1 {
                ns = s / nb
                nb = 1
            }
            return UIColor(hue: h,
                           saturation: Swift.max(0, Swift.min(1, ns)),
                           brightness: Swift.max(0, Swift.min(1, nb)),
                           alpha: a)
        }
        let c = silkMathRGBA()
        return UIColor(red: Swift.min(1, c.r * f),
                       green: Swift.min(1, c.g * f),
                       blue: Swift.min(1, c.b * f),
                       alpha: c.a)
    }

    /// Farbe aus Hex-Wert, z.B. `UIColor.hex(0xC8102E)`.
    static func hex(_ rgb: UInt32, alpha: CGFloat = 1) -> UIColor {
        let r = CGFloat((rgb >> 16) & 0xFF) / 255
        let g = CGFloat((rgb >> 8) & 0xFF) / 255
        let b = CGFloat(rgb & 0xFF) / 255
        return UIColor(red: r, green: g, blue: b, alpha: alpha)
    }
}
