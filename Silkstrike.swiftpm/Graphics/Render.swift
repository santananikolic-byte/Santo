import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Render – Grundlage der Darstellung:
//  SCNView-Konfiguration (native Auflösung, MSAA, FPS), Kamera-Look
//  (HDR, Bloom, SSAO, Motion Blur, Filmlook), PBR-Materialien,
//  prozeduraler Himmel (Cube-Map) + IBL + Nebel, Lichter.
// =====================================================================

enum CameraStyle {
    case gameplay
    case kombat
    case cinematic
}

enum Render {

    // MARK: - View

    /// Native Auflösung (Ultra/Ausgewogen = volle Panel-Auflösung), MSAA, Bildrate, schwarzer Hintergrund.
    static func configure(view: SCNView, quality: QualityPreset) {
        let native = UIScreen.main.nativeScale
        switch quality {
        case .ultra, .balanced:
            view.contentScaleFactor = native
            view.antialiasingMode = .multisampling4X
        case .performance:
            // 120-FPS-Modus: auf 3x-Displays leicht reduziert, sonst nativ
            view.contentScaleFactor = Swift.min(native, 2.0)
            view.antialiasingMode = .multisampling2X
        }
        let maxFPS = Swift.max(30, UIScreen.main.maximumFramesPerSecond)
        view.preferredFramesPerSecond = quality == .performance ? maxFPS : Swift.min(60, maxFPS)
        view.rendersContinuously = true
        view.isJitteringEnabled = false
        view.backgroundColor = .black
        view.allowsCameraControl = false
        view.autoenablesDefaultLighting = false
        view.showsStatistics = false
        view.isPlaying = true
    }

    // MARK: - Kamera

    /// HDR, Bloom, SSAO, Motion Blur und Farbgebung (leicht entsättigtes Teal/Orange, Vignette).
    /// fieldOfView wird NICHT verändert (setzt der jeweilige Controller).
    static func configureCamera(_ camera: SCNCamera, quality: QualityPreset, style: CameraStyle) {
        camera.wantsHDR = true
        camera.automaticallyAdjustsZRange = false

        switch style {
        case .gameplay:
            camera.zNear = 0.1          // etwas größer als 0.05 → weniger Z-Fighting bei 2,5 km Sichtweite
            camera.zFar = 2500
        case .kombat:
            camera.zNear = 0.05
            camera.zFar = 1200
        case .cinematic:
            camera.zNear = 0.05
            camera.zFar = 2500
        }

        // Tonemapping / Belichtung
        camera.averageGray = 0.18
        camera.whitePoint = 1.0
        camera.exposureOffset = 0
        switch style {
        case .gameplay:
            camera.wantsExposureAdaptation = true
            camera.minimumExposure = -0.6
            camera.maximumExposure = 1.0
        case .kombat, .cinematic:
            camera.wantsExposureAdaptation = false
            camera.minimumExposure = -2
            camera.maximumExposure = 2
        }

        // Bloom
        let bloomScale: CGFloat = quality == .performance ? 0.7 : 1.0
        let hiRes = quality == .ultra
        switch style {
        case .gameplay:
            camera.bloomIntensity = 0.85 * bloomScale
            camera.bloomThreshold = 0.8
            camera.bloomBlurRadius = hiRes ? 12 : 8
        case .kombat:
            camera.bloomIntensity = 1.0 * bloomScale
            camera.bloomThreshold = 0.75
            camera.bloomBlurRadius = hiRes ? 12 : 9
        case .cinematic:
            camera.bloomIntensity = 1.35 * bloomScale
            camera.bloomThreshold = 0.65
            camera.bloomBlurRadius = hiRes ? 16 : 10
        }

        // SSAO (Radius in Metern: Stadt grob, Kampf fein)
        switch quality {
        case .ultra:
            camera.screenSpaceAmbientOcclusionIntensity = style == .gameplay ? 0.9 : 1.2
            camera.screenSpaceAmbientOcclusionRadius = style == .gameplay ? 1.2 : 0.45
        case .balanced:
            camera.screenSpaceAmbientOcclusionIntensity = style == .gameplay ? 0.7 : 0.9
            camera.screenSpaceAmbientOcclusionRadius = style == .gameplay ? 1.0 : 0.4
        case .performance:
            camera.screenSpaceAmbientOcclusionIntensity = 0
        }

        // Motion Blur (klein im Spiel, kaum im Kampf → Treffer bleiben knackig)
        switch (style, quality) {
        case (.gameplay, .ultra): camera.motionBlurIntensity = 0.18
        case (.gameplay, .balanced): camera.motionBlurIntensity = 0.12
        case (.kombat, .ultra): camera.motionBlurIntensity = 0.05
        case (.cinematic, .ultra): camera.motionBlurIntensity = 0.3
        case (.cinematic, .balanced): camera.motionBlurIntensity = 0.2
        default: camera.motionBlurIntensity = 0
        }

        // Filmischer Look
        switch style {
        case .gameplay:
            camera.saturation = 1.05
            camera.contrast = 0.1
            camera.vignettingPower = 0.45
            camera.vignettingIntensity = 0.9
            camera.colorFringeStrength = 0
        case .kombat:
            camera.saturation = 1.08
            camera.contrast = 0.14
            camera.vignettingPower = 0.6
            camera.vignettingIntensity = 1.0
            camera.colorFringeStrength = quality == .performance ? 0 : 0.2
        case .cinematic:
            camera.saturation = 0.98
            camera.contrast = 0.18
            camera.vignettingPower = 0.95
            camera.vignettingIntensity = 1.0
            camera.colorFringeStrength = quality == .performance ? 0 : 0.45
        }

        // Tiefenschärfe nur Ultra + Kino (focusDistance setzt die Cutscene)
        if style == .cinematic && quality == .ultra {
            camera.wantsDepthOfField = true
            camera.fStop = 1.8
            camera.focusDistance = 4
        } else {
            camera.wantsDepthOfField = false
        }
    }

    // MARK: - Materialien

    /// Physikalisch basiertes Material mit Einzelwerten.
    static func pbr(_ color: UIColor, roughness: Float, metalness: Float,
                    emission: UIColor? = nil, emissionIntensity: Float = 1) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = color
        m.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, roughness)))
        m.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metalness)))
        if let e = emission {
            m.emission.contents = e
            m.emission.intensity = CGFloat(emissionIntensity)
        } else {
            m.emission.contents = UIColor.black
        }
        m.isLitPerPixel = true
        return m
    }

    /// Texturiertes PBR-Material. tileScale wiederholt alle Texturen (contentsTransform).
    /// Emission (z. B. Fenster-Leuchtkarte) bekommt Intensität 1.5 → leichter Bloom.
    static func texturedPBR(diffuse: UIImage, normal: UIImage? = nil, roughness: Float, metalness: Float,
                            emission: UIImage? = nil, tileScale: Float = 1) -> SCNMaterial {
        let m = SCNMaterial()
        m.lightingModel = .physicallyBased
        m.diffuse.contents = diffuse
        m.roughness.contents = NSNumber(value: Swift.max(0.02, Swift.min(1, roughness)))
        m.metalness.contents = NSNumber(value: Swift.max(0, Swift.min(1, metalness)))
        let transform = SCNMatrix4MakeScale(tileScale, tileScale, 1)
        setupTiling(m.diffuse, transform)
        if let n = normal {
            m.normal.contents = n
            m.normal.intensity = 1.0
            setupTiling(m.normal, transform)
        }
        if let e = emission {
            m.emission.contents = e
            m.emission.intensity = 1.5
            setupTiling(m.emission, transform)
        } else {
            m.emission.contents = UIColor.black
        }
        m.isLitPerPixel = true
        return m
    }

    /// Selbstleuchtendes Material (Neon, Lampen, Bildschirme) – Intensität > 1 erzeugt Bloom.
    static func emissive(_ color: UIColor, intensity: Float = 2) -> SCNMaterial {
        let m = pbr(UIColor(white: 0.02, alpha: 1), roughness: 0.5, metalness: 0,
                    emission: color, emissionIntensity: intensity)
        return m
    }

    private static func setupTiling(_ p: SCNMaterialProperty, _ transform: SCNMatrix4) {
        p.wrapS = .repeat
        p.wrapT = .repeat
        p.contentsTransform = transform
        p.minificationFilter = .linear
        p.magnificationFilter = .linear
        p.mipFilter = .linear
        p.maxAnisotropy = 8
    }

    // MARK: - Lichter

    /// Gerichtetes Mond-/Hauptlicht mit kaskadierten Schatten (Größe nach Qualität).
    /// direction = Richtung, in die das Licht scheint (z. B. (-0.4, -1, -0.3)).
    static func makeKeyLight(direction: SIMD3<Float>, color: UIColor, intensity: Float,
                             quality: QualityPreset, shadowExtent: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .directional
        light.color = color
        light.intensity = CGFloat(intensity)
        light.castsShadow = true
        light.shadowMode = .forward
        light.automaticallyAdjustsShadowProjection = true
        light.maximumShadowDistance = CGFloat(Swift.max(10, shadowExtent))
        light.shadowColor = UIColor(white: 0, alpha: 0.82)
        switch quality {
        case .ultra:
            light.shadowMapSize = CGSize(width: 2048, height: 2048)
            light.shadowCascadeCount = 4
            light.shadowSampleCount = 12
            light.shadowRadius = 1.5
        case .balanced:
            light.shadowMapSize = CGSize(width: 2048, height: 2048)
            light.shadowCascadeCount = 3
            light.shadowSampleCount = 6
            light.shadowRadius = 2.0
        case .performance:
            light.shadowMapSize = CGSize(width: 1024, height: 1024)
            light.shadowCascadeCount = 2
            light.shadowSampleCount = 2
            light.shadowRadius = 2.5
        }

        let node = SCNNode()
        node.name = "keyLight"
        node.light = light
        var dir = direction
        if simd_length_squared(dir) < 1e-8 { dir = SIMD3<Float>(-0.4, -1, -0.3) }
        dir = simd_normalize(dir)
        node.simdOrientation = simd_quatf(from: SIMD3<Float>(0, 0, -1), to: dir)
        node.simdPosition = -dir * 150
        return node
    }

    static func makeAmbient(color: UIColor, intensity: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .ambient
        light.color = color
        light.intensity = CGFloat(intensity)
        let node = SCNNode()
        node.name = "ambientLight"
        node.light = light
        return node
    }

    /// Punktlicht ohne Schatten, quadratischer Abfall bis `range` Meter.
    static func makePointLight(color: UIColor, intensity: Float, range: Float) -> SCNNode {
        let light = SCNLight()
        light.type = .omni
        light.color = color
        light.intensity = CGFloat(intensity)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.1, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = false
        let node = SCNNode()
        node.name = "pointLight"
        node.light = light
        return node
    }

    /// Spotlicht entlang lokal -Z. angle = äußerer Kegelwinkel in GRAD
    /// (Werte < 3.2 werden als Radiant interpretiert).
    static func makeSpotLight(color: UIColor, intensity: Float, angle: Float, range: Float, castsShadow: Bool) -> SCNNode {
        let light = SCNLight()
        light.type = .spot
        light.color = color
        light.intensity = CGFloat(intensity)
        var deg = angle
        if deg > 0 && deg < 3.2 { deg = deg * 180 / Float.pi }
        deg = Swift.max(1, Swift.min(170, deg))
        light.spotOuterAngle = CGFloat(deg)
        light.spotInnerAngle = CGFloat(deg * 0.55)
        light.attenuationStartDistance = 0
        light.attenuationEndDistance = CGFloat(Swift.max(0.1, range))
        light.attenuationFalloffExponent = 2
        light.castsShadow = castsShadow
        if castsShadow {
            light.shadowMode = .forward
            light.shadowMapSize = CGSize(width: 1024, height: 1024)
            light.shadowSampleCount = 8
            light.shadowRadius = 3
            light.shadowColor = UIColor(white: 0, alpha: 0.8)
            light.zNear = 0.1
            light.zFar = CGFloat(Swift.max(1, range))
        }
        let node = SCNNode()
        node.name = "spotLight"
        node.light = light
        return node
    }
}

// MARK: - Umgebung: prozeduraler Himmel (Cube-Map), IBL, Nebel

extension Render {

    private static var skyFaceCache: [String: [UIImage]] = [:]

    /// Richtung ZUM Mond (Himmelsposition) bzw. zur tiefstehenden Abendsonne.
    private static let moonSkyDirection: SIMD3<Float> = simd_normalize(SIMD3<Float>(-0.35, 0.42, -0.84))
    private static let sunSkyDirection: SIMD3<Float> = simd_normalize(SIMD3<Float>(-1.0, 0.035, 0.12))

    /// Himmel (Hintergrund) + Lichtumgebung (IBL) + Nebel.
    /// Der Nebel sollte zur Horizontfarbe passen (Hintergrund wird von SceneKit nicht vernebelt) –
    /// ohne fogColor wird eine passende Farbe gewählt.
    static func applyEnvironment(to scene: SCNScene, timeOfDay: TimeOfDay, quality: QualityPreset,
                                 fogStart: Float, fogEnd: Float, fogColor: UIColor? = nil) {
        let bgSize: Int
        let iblSize: Int
        switch quality {
        case .ultra:
            bgSize = 1024
            iblSize = 128
        case .balanced:
            bgSize = 768
            iblSize = 64
        case .performance:
            bgSize = 512
            iblSize = 64
        }
        let background = skyFaces(timeOfDay: timeOfDay, size: bgSize)
        let lighting = skyLightingFaces(timeOfDay: timeOfDay, size: iblSize)
        if background.count == 6 {
            scene.background.contents = background
        } else {
            scene.background.contents = defaultFogColor(timeOfDay)
        }
        scene.background.intensity = 1
        if lighting.count == 6 {
            scene.lightingEnvironment.contents = lighting
        }
        scene.lightingEnvironment.intensity = CGFloat(lightingIntensity(timeOfDay))

        let start = Swift.max(0, fogStart)
        let end = Swift.max(start + 1, fogEnd)
        scene.fogStartDistance = CGFloat(start)
        scene.fogEndDistance = CGFloat(end)
        scene.fogColor = fogColor ?? defaultFogColor(timeOfDay)
        scene.fogDensityExponent = 1.25
    }

    /// Nebelfarbe passend zum Horizont der Tageszeit.
    static func defaultFogColor(_ timeOfDay: TimeOfDay) -> UIColor {
        switch timeOfDay {
        case .night: return UIColor(red: 0.105, green: 0.085, blue: 0.11, alpha: 1)
        case .dusk: return UIColor(red: 0.50, green: 0.30, blue: 0.30, alpha: 1)
        case .stormNight: return UIColor(red: 0.085, green: 0.10, blue: 0.095, alpha: 1)
        }
    }

    /// Farbe des Himmels knapp über dem Horizont (für Silhouetten, Glows, Nebel).
    static func skyHorizonColor(_ timeOfDay: TimeOfDay) -> UIColor {
        let c = sampleSky(skyStops(timeOfDay), 0.02)
        return UIColor(red: CGFloat(c.x), green: CGFloat(c.y), blue: CGFloat(c.z), alpha: 1)
    }

    /// Richtung, in die das Haupt-/Mondlicht passend zum Himmel scheint (für makeKeyLight).
    static func skyLightDirection(_ timeOfDay: TimeOfDay) -> SIMD3<Float> {
        switch timeOfDay {
        case .night:
            return -moonSkyDirection
        case .dusk:
            return simd_normalize(SIMD3<Float>(1.0, -0.38, -0.12))
        case .stormNight:
            return simd_normalize(SIMD3<Float>(0.25, -1.0, 0.35))
        }
    }

    private static func lightingIntensity(_ timeOfDay: TimeOfDay) -> Float {
        switch timeOfDay {
        case .night: return 1.0
        case .dusk: return 1.2
        case .stormNight: return 0.75
        }
    }

    // MARK: Himmelsfarben (Höhe über Horizont → Farbe, sRGB)

    private static func skyStops(_ timeOfDay: TimeOfDay) -> [(Float, SIMD3<Float>)] {
        switch timeOfDay {
        case .night:
            return [
                (-1.0, SIMD3<Float>(0.010, 0.012, 0.018)),
                (-0.15, SIMD3<Float>(0.030, 0.030, 0.042)),
                (-0.02, SIMD3<Float>(0.110, 0.085, 0.095)),
                (0.0, SIMD3<Float>(0.260, 0.170, 0.150)),
                (0.04, SIMD3<Float>(0.180, 0.130, 0.160)),
                (0.12, SIMD3<Float>(0.075, 0.075, 0.130)),
                (0.35, SIMD3<Float>(0.028, 0.038, 0.080)),
                (1.0, SIMD3<Float>(0.008, 0.012, 0.035))
            ]
        case .dusk:
            return [
                (-1.0, SIMD3<Float>(0.030, 0.025, 0.035)),
                (-0.15, SIMD3<Float>(0.100, 0.060, 0.080)),
                (-0.02, SIMD3<Float>(0.450, 0.220, 0.160)),
                (0.0, SIMD3<Float>(0.980, 0.520, 0.220)),
                (0.05, SIMD3<Float>(0.950, 0.450, 0.280)),
                (0.15, SIMD3<Float>(0.620, 0.300, 0.420)),
                (0.35, SIMD3<Float>(0.300, 0.180, 0.420)),
                (0.65, SIMD3<Float>(0.130, 0.100, 0.300)),
                (1.0, SIMD3<Float>(0.060, 0.060, 0.180))
            ]
        case .stormNight:
            return [
                (-1.0, SIMD3<Float>(0.015, 0.018, 0.018)),
                (-0.10, SIMD3<Float>(0.040, 0.045, 0.045)),
                (0.0, SIMD3<Float>(0.150, 0.155, 0.130)),
                (0.06, SIMD3<Float>(0.110, 0.125, 0.115)),
                (0.25, SIMD3<Float>(0.060, 0.075, 0.070)),
                (1.0, SIMD3<Float>(0.030, 0.040, 0.040))
            ]
        }
    }

    private static func sampleSky(_ stops: [(Float, SIMD3<Float>)], _ e: Float) -> SIMD3<Float> {
        guard let first = stops.first, let last = stops.last else { return SIMD3<Float>(0, 0, 0) }
        if e <= first.0 { return first.1 }
        if e >= last.0 { return last.1 }
        for i in 1..<stops.count {
            let a = stops[i - 1]
            let b = stops[i]
            if e <= b.0 {
                let span = b.0 - a.0
                let f = span > 1e-6 ? (e - a.0) / span : 0
                let sm = f * f * (3 - 2 * f)
                return a.1 + (b.1 - a.1) * sm
            }
        }
        return last.1
    }

    private static func skySmooth(_ a: Float, _ b: Float, _ x: Float) -> Float {
        let t = Swift.max(0, Swift.min(1, (x - a) / (b - a)))
        return t * t * (3 - 2 * t)
    }

    private static func skyByte(_ v: Float) -> UInt8 {
        let x = v * 255 + 0.5
        if !(x > 0) { return 0 }
        if x >= 255 { return 255 }
        return UInt8(x)
    }

    // MARK: Cube-Map-Geometrie (Reihenfolge +X, -X, +Y, -Y, +Z, -Z; s nach rechts, t nach unten, je -1...1)

    private static func skyDirection(face: Int, s: Float, t: Float) -> SIMD3<Float> {
        switch face {
        case 0: return SIMD3<Float>(1, -t, -s)
        case 1: return SIMD3<Float>(-1, -t, s)
        case 2: return SIMD3<Float>(s, 1, t)
        case 3: return SIMD3<Float>(s, -1, -t)
        case 4: return SIMD3<Float>(s, -t, 1)
        default: return SIMD3<Float>(-s, -t, -1)
        }
    }

    /// Projiziert eine Richtung auf eine Würfelfläche → (0...1, 0...1) Bildkoordinaten, nil wenn nicht auf dieser Fläche.
    private static func skyProject(_ d: SIMD3<Float>, face: Int) -> SIMD2<Float>? {
        let ax = abs(d.x)
        let ay = abs(d.y)
        let az = abs(d.z)
        var s: Float = 0
        var t: Float = 0
        switch face {
        case 0:
            guard d.x > 0, ax >= ay, ax >= az else { return nil }
            s = -d.z / ax
            t = -d.y / ax
        case 1:
            guard d.x < 0, ax >= ay, ax >= az else { return nil }
            s = d.z / ax
            t = -d.y / ax
        case 2:
            guard d.y > 0, ay >= ax, ay >= az else { return nil }
            s = d.x / ay
            t = d.z / ay
        case 3:
            guard d.y < 0, ay >= ax, ay >= az else { return nil }
            s = d.x / ay
            t = -d.z / ay
        case 4:
            guard d.z > 0, az >= ax, az >= ay else { return nil }
            s = d.x / az
            t = -d.y / az
        default:
            guard d.z < 0, az >= ax, az >= ay else { return nil }
            s = -d.x / az
            t = -d.y / az
        }
        return SIMD2<Float>((s + 1) * 0.5, (t + 1) * 0.5)
    }

    /// Glatter Grundverlauf einer Würfelfläche, Pixel für Pixel aus der Blickrichtung berechnet.
    private static func skyBaseFace(face: Int, size: Int, timeOfDay: TimeOfDay, gain: Float) -> CGImage? {
        let n = Swift.max(4, size)
        let stops = Render.skyStops(timeOfDay)
        var bytes = [UInt8](repeating: 255, count: n * n * 4)
        let inv = 2 / Float(n)
        bytes.withUnsafeMutableBufferPointer { buf in
            for y in 0..<n {
                let t = (Float(y) + 0.5) * inv - 1
                for x in 0..<n {
                    let s = (Float(x) + 0.5) * inv - 1
                    let d = simd_normalize(Render.skyDirection(face: face, s: s, t: t))
                    let c = Render.sampleSky(stops, d.y) * gain
                    let i = (y * n + x) * 4
                    buf[i] = Render.skyByte(c.x)
                    buf[i + 1] = Render.skyByte(c.y)
                    buf[i + 2] = Render.skyByte(c.z)
                    buf[i + 3] = 255
                }
            }
        }
        return ProceduralTextures.makeCGImage(rgba: bytes, width: n, height: n)
    }

    /// 6 Hintergrund-Flächen (gecacht): Verlauf + Wolken + Sterne + Mond/Sonne + Dithering gegen Banding.
    static func skyFaces(timeOfDay: TimeOfDay, size: Int) -> [UIImage] {
        let px = Swift.max(64, Swift.min(2048, size))
        let key = "bg-\(timeOfDay.rawValue)-\(px)"
        if let cached = skyFaceCache[key] { return cached }
        let dither = ProceduralTextures.ditherOverlay()
        var faces: [UIImage] = []
        for face in 0..<6 {
            let base = skyBaseFace(face: face, size: 128, timeOfDay: timeOfDay, gain: 1)
            let image = ProceduralTextures.renderImage(width: px, height: px, opaque: true) { ctx in
                let rect = CGRect(x: 0, y: 0, width: px, height: px)
                ctx.interpolationQuality = .high
                if let b = base {
                    UIImage(cgImage: b).draw(in: rect)
                } else {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(rect)
                }
                Render.drawSkyDetails(ctx, face: face, size: CGFloat(px), timeOfDay: timeOfDay)
                ctx.interpolationQuality = .none
                dither.draw(in: rect, blendMode: .softLight, alpha: 0.18)
            }
            faces.append(image)
        }
        skyFaceCache[key] = faces
        return faces
    }

    /// 6 kleine, aufgehellte Flächen für die bildbasierte Beleuchtung (inkl. Mond-/Sonnen-Glanzpunkt).
    static func skyLightingFaces(timeOfDay: TimeOfDay, size: Int) -> [UIImage] {
        let px = Swift.max(16, Swift.min(512, size))
        let key = "ibl-\(timeOfDay.rawValue)-\(px)"
        if let cached = skyFaceCache[key] { return cached }
        var faces: [UIImage] = []
        for face in 0..<6 {
            let base = skyBaseFace(face: face, size: px, timeOfDay: timeOfDay, gain: 1.8)
            let image = ProceduralTextures.renderImage(width: px, height: px, opaque: true) { ctx in
                let rect = CGRect(x: 0, y: 0, width: px, height: px)
                let sz = CGFloat(px)
                if let b = base {
                    UIImage(cgImage: b).draw(in: rect)
                } else {
                    ctx.setFillColor(UIColor.black.cgColor)
                    ctx.fill(rect)
                }
                switch timeOfDay {
                case .night:
                    if let uv = Render.skyProject(Render.moonSkyDirection, face: face) {
                        let p = CGPoint(x: CGFloat(uv.x) * sz, y: CGFloat(uv.y) * sz)
                        ProceduralTextures.drawRadial(ctx, center: p, radius: sz * 0.12,
                                                      colors: [UIColor(white: 1, alpha: 0.95),
                                                               UIColor(red: 0.7, green: 0.8, blue: 1, alpha: 0.25),
                                                               UIColor(red: 0.6, green: 0.7, blue: 1, alpha: 0)],
                                                      locations: [0, 0.3, 1])
                    }
                case .dusk:
                    if let uv = Render.skyProject(Render.sunSkyDirection, face: face) {
                        let p = CGPoint(x: CGFloat(uv.x) * sz, y: CGFloat(uv.y) * sz)
                        ProceduralTextures.drawRadial(ctx, center: p, radius: sz * 0.3,
                                                      colors: [UIColor(red: 1, green: 0.85, blue: 0.6, alpha: 1),
                                                               UIColor(red: 1, green: 0.55, blue: 0.25, alpha: 0.45),
                                                               UIColor(red: 1, green: 0.45, blue: 0.2, alpha: 0)],
                                                      locations: [0, 0.25, 1])
                    }
                case .stormNight:
                    break
                }
            }
            faces.append(image)
        }
        skyFaceCache[key] = faces
        return faces
    }

    // MARK: Himmelsdetails

    private static func drawSkyDetails(_ ctx: CGContext, face: Int, size: CGFloat, timeOfDay: TimeOfDay) {
        switch timeOfDay {
        case .night:
            drawSkyClouds(ctx, face: face, size: size, seed: 0xC10D,
                          dark: UIColor(red: 0.025, green: 0.035, blue: 0.065, alpha: 1),
                          light: UIColor(red: 0.17, green: 0.14, blue: 0.20, alpha: 1),
                          count: 5, alpha: 0.32)
            drawSkyStars(ctx, face: face, size: size, density: 1.0, seed: 0x57A8)
            if let uv = skyProject(moonSkyDirection, face: face) {
                drawMoon(ctx, at: CGPoint(x: CGFloat(uv.x) * size, y: CGFloat(uv.y) * size), size: size)
            }
        case .dusk:
            drawSkyStars(ctx, face: face, size: size, density: 0.15, seed: 0x57A9)
            drawSkyClouds(ctx, face: face, size: size, seed: 0xD05C,
                          dark: UIColor(red: 0.26, green: 0.12, blue: 0.22, alpha: 1),
                          light: UIColor(red: 0.95, green: 0.50, blue: 0.40, alpha: 1),
                          count: 6, alpha: 0.38)
            if let uv = skyProject(sunSkyDirection, face: face) {
                drawSun(ctx, at: CGPoint(x: CGFloat(uv.x) * size, y: CGFloat(uv.y) * size), size: size)
            }
        case .stormNight:
            drawSkyClouds(ctx, face: face, size: size, seed: 0x5707,
                          dark: UIColor(red: 0.012, green: 0.018, blue: 0.018, alpha: 1),
                          light: UIColor(red: 0.20, green: 0.24, blue: 0.22, alpha: 1),
                          count: 10, alpha: 0.6)
            // von Blitzen angeleuchtete Wolkenränder
            drawSkyClouds(ctx, face: face, size: size, seed: 0xB117,
                          dark: UIColor(red: 0.45, green: 0.55, blue: 0.62, alpha: 1),
                          light: UIColor(red: 0.62, green: 0.72, blue: 0.78, alpha: 1),
                          count: 2, alpha: 0.16)
        }
    }

    /// Weiche Wolkenballen – bleiben vollständig innerhalb der Fläche (keine sichtbaren Nähte).
    private static func drawSkyClouds(_ ctx: CGContext, face: Int, size: CGFloat, seed: UInt64,
                                      dark: UIColor, light: UIColor, count: Int, alpha: CGFloat) {
        if face == 3 || count <= 0 { return }
        var rng = ProceduralTextures.Rand(seed: seed &+ UInt64(face) &* 0x9E37_79B9)
        let isTop = face == 2
        for _ in 0..<count {
            let cx = rng.range(0.25, 0.75) * size
            let cy = isTop ? rng.range(0.25, 0.75) * size : rng.range(0.2, 0.44) * size
            let stretch: CGFloat = isTop ? rng.range(1.0, 1.8) : rng.range(1.8, 3.2)
            var r = rng.range(0.06, 0.17) * size
            let maxRX = Swift.min(cx, size - cx) * 0.92
            let maxRY = isTop ? Swift.min(cy, size - cy) * 0.92 : Swift.min(cy, size * 0.53 - cy) * 0.92
            r = Swift.min(r, maxRX / stretch, maxRY)
            if r < 2 { continue }
            let col = rng.chance(0.65) ? dark : light
            let a = alpha * rng.range(0.6, 1.0)
            ctx.saveGState()
            ctx.translateBy(x: cx, y: cy)
            ctx.scaleBy(x: stretch, y: 1)
            ProceduralTextures.drawRadial(ctx, center: CGPoint.zero, radius: r,
                                          colors: [col.withAlphaComponent(a),
                                                   col.withAlphaComponent(a * 0.55),
                                                   col.withAlphaComponent(0)],
                                          locations: [0, 0.5, 1])
            ctx.restoreGState()
        }
    }

    private static func drawSkyStars(_ ctx: CGContext, face: Int, size: CGFloat, density: CGFloat, seed: UInt64) {
        if face == 3 { return }
        var rng = ProceduralTextures.Rand(seed: seed &+ UInt64(face) &* 7919)
        let scale = size / 1024
        let count = Int(950 * density * scale * scale)
        if count <= 0 { return }
        let tints: [UIColor] = [
            UIColor.white,
            UIColor(red: 0.80, green: 0.88, blue: 1.00, alpha: 1),
            UIColor(red: 1.00, green: 0.90, blue: 0.78, alpha: 1),
            UIColor(red: 0.90, green: 0.93, blue: 1.00, alpha: 1)
        ]
        let sizeFactor = Swift.max(0.6, scale)
        for _ in 0..<count {
            let ux = rng.unit()
            let uy = rng.unit()
            let d = simd_normalize(skyDirection(face: face, s: Float(ux) * 2 - 1, t: Float(uy) * 2 - 1))
            if d.y < 0.03 { continue }
            let fade = CGFloat(skySmooth(0.03, 0.3, d.y))
            let u3 = rng.unit()
            let mag = u3 * u3 * u3
            let r = (0.45 + mag * 1.5) * sizeFactor
            let a = (0.2 + 0.8 * mag) * fade
            let tint = tints[rng.int(tints.count)]
            let p = CGPoint(x: ux * size, y: uy * size)
            if mag > 0.8 {
                ProceduralTextures.drawRadial(ctx, center: p, radius: r * 5,
                                              colors: [tint.withAlphaComponent(0.25 * a), tint.withAlphaComponent(0)],
                                              locations: [0, 1])
            }
            ctx.setFillColor(tint.withAlphaComponent(a).cgColor)
            ctx.fillEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2))
        }
    }

    private static func drawMoon(_ ctx: CGContext, at p: CGPoint, size: CGFloat) {
        let r = size * 0.028
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 7,
                                      colors: [UIColor(red: 0.70, green: 0.78, blue: 1.0, alpha: 0.22),
                                               UIColor(red: 0.55, green: 0.65, blue: 0.95, alpha: 0.07),
                                               UIColor(red: 0.50, green: 0.60, blue: 0.90, alpha: 0)],
                                      locations: [0, 0.35, 1])
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 2,
                                      colors: [UIColor(white: 1, alpha: 0.4), UIColor(white: 1, alpha: 0)],
                                      locations: [0, 1])
        let disc = CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2)
        ctx.saveGState()
        ctx.addEllipse(in: disc)
        ctx.clip()
        ProceduralTextures.drawRadial(ctx, center: CGPoint(x: p.x - r * 0.3, y: p.y - r * 0.3), radius: r * 1.6,
                                      colors: [UIColor(red: 1.0, green: 0.98, blue: 0.93, alpha: 1),
                                               UIColor(red: 0.86, green: 0.86, blue: 0.84, alpha: 1),
                                               UIColor(red: 0.70, green: 0.72, blue: 0.74, alpha: 1)],
                                      locations: [0, 0.55, 1], extend: true)
        var rng = ProceduralTextures.Rand(seed: 0x300D)
        for _ in 0..<14 {
            let mr = r * rng.range(0.08, 0.32)
            let mx = p.x + rng.range(-0.75, 0.75) * r
            let my = p.y + rng.range(-0.75, 0.75) * r
            ctx.setFillColor(UIColor(red: 0.52, green: 0.53, blue: 0.58, alpha: rng.range(0.12, 0.3)).cgColor)
            ctx.fillEllipse(in: CGRect(x: mx - mr, y: my - mr, width: mr * 2, height: mr * 2))
        }
        ctx.restoreGState()
    }

    private static func drawSun(_ ctx: CGContext, at p: CGPoint, size: CGFloat) {
        let r = size * 0.024
        ProceduralTextures.drawRadial(ctx, center: p, radius: size * 0.36,
                                      colors: [UIColor(red: 1.0, green: 0.62, blue: 0.28, alpha: 0.55),
                                               UIColor(red: 1.0, green: 0.48, blue: 0.22, alpha: 0.2),
                                               UIColor(red: 0.9, green: 0.35, blue: 0.25, alpha: 0)],
                                      locations: [0, 0.3, 1])
        ProceduralTextures.drawRadial(ctx, center: p, radius: r * 3.5,
                                      colors: [UIColor(red: 1.0, green: 0.85, blue: 0.6, alpha: 0.85),
                                               UIColor(red: 1.0, green: 0.7, blue: 0.4, alpha: 0)],
                                      locations: [0, 1])
        ctx.setFillColor(UIColor(red: 1.0, green: 0.93, blue: 0.78, alpha: 1).cgColor)
        ctx.fillEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2))
    }
}
