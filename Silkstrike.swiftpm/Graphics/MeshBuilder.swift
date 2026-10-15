import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  MeshBuilder – sammelt viele Boxen / Quads / Zylinder in EINER
//  SCNGeometry (ein Draw-Call pro Material und Chunk).
//
//  Konventionen:
//  - Vorderseiten sind gegen den Uhrzeigersinn (CCW) gewunden (SceneKit-Standard).
//  - UVs in Welteinheiten: 1 Textur-Kachel = 1 / uvScale Meter.
//    (Fassaden: uvScale 0.1 → Kachel 10 m = 4 Stockwerke à 2,5 m x 4 Fensterachsen.)
//  - Seitenflächen von Boxen: u läuft horizontal von der linken Kante, v vertikal von unten.
//    Die Kachelzahl wird auf ganze Kacheln gerundet (Fenster werden an Ecken/Dachkante nicht
//    abgeschnitten) und pro Fläche um ein zufälliges Viertel versetzt (Fenstermuster
//    wiederholen sich nicht von Gebäude zu Gebäude).
//  - Ober-/Unterseiten: Welt-XZ-Projektion (nahtlose Dächer / Straßen).
//  - Texturkoordinate v = 0 ist der obere Bildrand (SceneKit / UIKit-Konvention).
// =====================================================================

struct MeshBuilder {
    private var positions: [SCNVector3] = []
    private var normals: [SCNVector3] = []
    private var uvs: [CGPoint] = []
    private var indices: [UInt32] = []

    /// Rundet die Kachelanzahl auf Seitenflächen auf ganze Kacheln (ab 0.75 Kacheln).
    var snapsTilesToFaces: Bool = true
    /// Versetzt jede Seitenfläche um ein zufälliges Viertel einer Kachel (deterministisch aus der Position).
    var variesFaceOffsets: Bool = true

    init() {}

    /// Optional: Speicher für ungefähr so viele Boxen vorab reservieren.
    init(reserveBoxes: Int) {
        let quads = Swift.max(0, reserveBoxes) * 6
        positions.reserveCapacity(quads * 4)
        normals.reserveCapacity(quads * 4)
        uvs.reserveCapacity(quads * 4)
        indices.reserveCapacity(quads * 6)
    }

    var isEmpty: Bool { return indices.isEmpty }
    var vertexCount: Int { return positions.count }
    var triangleCount: Int { return indices.count / 3 }

    mutating func removeAll() {
        positions.removeAll(keepingCapacity: true)
        normals.removeAll(keepingCapacity: true)
        uvs.removeAll(keepingCapacity: true)
        indices.removeAll(keepingCapacity: true)
    }

    // MARK: - Public shapes

    /// Achsenparallele Box. Ohne Unterseite (Gebäude stehen auf dem Boden), außer includeBottom.
    mutating func addBox(min lo: SIMD3<Float>, max hi: SIMD3<Float>, uvScale: Float = 0.1, includeBottom: Bool = false) {
        let a = simd_min(lo, hi)
        let b = simd_max(lo, hi)
        let d = b - a
        let up = MeshBuilder.axisY
        // +X (rechts = -Z)
        pushFace(origin: SIMD3<Float>(b.x, a.y, b.z), right: MeshBuilder.axisNegZ, up: up,
                 width: d.z, height: d.y, uvScale: uvScale, horizontal: false, salt: 11)
        // -X (rechts = +Z)
        pushFace(origin: SIMD3<Float>(a.x, a.y, a.z), right: MeshBuilder.axisZ, up: up,
                 width: d.z, height: d.y, uvScale: uvScale, horizontal: false, salt: 23)
        // +Z (rechts = +X)
        pushFace(origin: SIMD3<Float>(a.x, a.y, b.z), right: MeshBuilder.axisX, up: up,
                 width: d.x, height: d.y, uvScale: uvScale, horizontal: false, salt: 37)
        // -Z (rechts = -X)
        pushFace(origin: SIMD3<Float>(b.x, a.y, a.z), right: MeshBuilder.axisNegX, up: up,
                 width: d.x, height: d.y, uvScale: uvScale, horizontal: false, salt: 41)
        // Oberseite (Normal +Y)
        pushFace(origin: SIMD3<Float>(a.x, b.y, b.z), right: MeshBuilder.axisX, up: MeshBuilder.axisNegZ,
                 width: d.x, height: d.z, uvScale: uvScale, horizontal: true, salt: 53)
        if includeBottom {
            // Unterseite (Normal -Y)
            pushFace(origin: SIMD3<Float>(a.x, a.y, a.z), right: MeshBuilder.axisX, up: MeshBuilder.axisZ,
                     width: d.x, height: d.z, uvScale: uvScale, horizontal: true, salt: 67)
        }
    }

    /// Beliebiges (planares) Viereck. a→b→c→d gegen den Uhrzeigersinn von der Vorderseite gesehen.
    /// UVs: waagerechte Flächen → Welt-XZ, senkrechte Flächen → (horizontale Weltachse, Höhe).
    mutating func addQuad(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>, _ d: SIMD3<Float>, uvScale: Float = 0.1) {
        var n = simd_cross(b - a, c - a)
        if simd_length_squared(n) < 1e-12 { n = simd_cross(c - a, d - a) }
        if simd_length_squared(n) < 1e-12 { return }
        n = simd_normalize(n)
        let t0 = MeshBuilder.planarUV(a, normal: n, scale: uvScale)
        let t1 = MeshBuilder.planarUV(b, normal: n, scale: uvScale)
        let t2 = MeshBuilder.planarUV(c, normal: n, scale: uvScale)
        let t3 = MeshBuilder.planarUV(d, normal: n, scale: uvScale)
        pushQuad(a, b, c, d, normal: n, t0, t1, t2, t3)
    }

    /// Dreieck a→b→c gegen den Uhrzeigersinn von der Vorderseite gesehen.
    mutating func addTriangle(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>, uvScale: Float = 0.1) {
        let raw = simd_cross(b - a, c - a)
        if simd_length_squared(raw) < 1e-12 { return }
        let n = simd_normalize(raw)
        let base = UInt32(positions.count)
        let ta = MeshBuilder.planarUV(a, normal: n, scale: uvScale)
        let tb = MeshBuilder.planarUV(b, normal: n, scale: uvScale)
        let tc = MeshBuilder.planarUV(c, normal: n, scale: uvScale)
        pushVertex(a, n, ta)
        pushVertex(b, n, tb)
        pushVertex(c, n, tc)
        indices.append(base)
        indices.append(base + 1)
        indices.append(base + 2)
    }

    /// Senkrechter Zylinder. `center` = Mittelpunkt der GRUNDFLÄCHE, wächst nach +Y um `height`.
    /// Glatte Normalen, Deckel oben (optional unten).
    mutating func addCylinder(center: SIMD3<Float>, radius: Float, height: Float, segments: Int = 12,
                              uvScale: Float = 0.1, capTop: Bool = true, capBottom: Bool = false) {
        guard radius > 0.0001, height > 0.0001 else { return }
        let segs = Swift.max(3, Swift.min(128, segments))
        let circumference = 2 * Float.pi * radius
        var tilesU = circumference * uvScale
        if snapsTilesToFaces && tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
        let vBottom = height * uvScale
        let base = UInt32(positions.count)

        // Mantel: (segs + 1) Spalten (UV-Naht), je 2 Vertices (unten, oben)
        for i in 0...segs {
            let f = Float(i) / Float(segs)
            let ang = f * 2 * Float.pi
            let s = sin(ang)
            let c = cos(ang)
            let n = SIMD3<Float>(s, 0, c)
            let bottom = center + SIMD3<Float>(s * radius, 0, c * radius)
            let top = bottom + SIMD3<Float>(0, height, 0)
            pushVertex(bottom, n, SIMD2<Float>(f * tilesU, vBottom))
            pushVertex(top, n, SIMD2<Float>(f * tilesU, 0))
        }
        for i in 0..<segs {
            let b0 = base + UInt32(i * 2)
            let t0 = b0 + 1
            let b1 = b0 + 2
            let t1 = b0 + 3
            // (b0, b1, t1), (b0, t1, t0) – CCW von außen
            indices.append(b0); indices.append(b1); indices.append(t1)
            indices.append(b0); indices.append(t1); indices.append(t0)
        }

        if capTop {
            let topY = center.y + height
            let up = MeshBuilder.axisY
            let cIndex = UInt32(positions.count)
            let cTop = SIMD3<Float>(center.x, topY, center.z)
            pushVertex(cTop, up, SIMD2<Float>(cTop.x * uvScale, cTop.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, topY, center.z + cos(ang) * radius)
                pushVertex(p, up, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 1 + UInt32(i))
                indices.append(cIndex + 2 + UInt32(i))
            }
        }
        if capBottom {
            let down = SIMD3<Float>(0, -1, 0)
            let cIndex = UInt32(positions.count)
            pushVertex(center, down, SIMD2<Float>(center.x * uvScale, center.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, center.y, center.z + cos(ang) * radius)
                pushVertex(p, down, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 2 + UInt32(i))
                indices.append(cIndex + 1 + UInt32(i))
            }
        }
    }

    /// Kegel (Baumkronen, Turmspitzen). `center` = Mittelpunkt der Grundfläche, Spitze bei center + (0, height, 0).
    mutating func addCone(center: SIMD3<Float>, radius: Float, height: Float, segments: Int = 12,
                          uvScale: Float = 0.1, capBottom: Bool = false) {
        guard radius > 0.0001, height > 0.0001 else { return }
        let segs = Swift.max(3, Swift.min(128, segments))
        let apex = center + SIMD3<Float>(0, height, 0)
        let slant = sqrt(radius * radius + height * height)
        var tilesU = 2 * Float.pi * radius * uvScale
        if snapsTilesToFaces && tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
        let vBottom = slant * uvScale
        for i in 0..<segs {
            let f0 = Float(i) / Float(segs)
            let f1 = Float(i + 1) / Float(segs)
            let a0 = f0 * 2 * Float.pi
            let a1 = f1 * 2 * Float.pi
            let am = (a0 + a1) * 0.5
            let n0 = simd_normalize(SIMD3<Float>(sin(a0) * height, radius, cos(a0) * height))
            let n1 = simd_normalize(SIMD3<Float>(sin(a1) * height, radius, cos(a1) * height))
            let nm = simd_normalize(SIMD3<Float>(sin(am) * height, radius, cos(am) * height))
            let p0 = center + SIMD3<Float>(sin(a0) * radius, 0, cos(a0) * radius)
            let p1 = center + SIMD3<Float>(sin(a1) * radius, 0, cos(a1) * radius)
            let base = UInt32(positions.count)
            pushVertex(p0, n0, SIMD2<Float>(f0 * tilesU, vBottom))
            pushVertex(p1, n1, SIMD2<Float>(f1 * tilesU, vBottom))
            pushVertex(apex, nm, SIMD2<Float>((f0 + f1) * 0.5 * tilesU, 0))
            indices.append(base); indices.append(base + 1); indices.append(base + 2)
        }
        if capBottom {
            let down = SIMD3<Float>(0, -1, 0)
            let cIndex = UInt32(positions.count)
            pushVertex(center, down, SIMD2<Float>(center.x * uvScale, center.z * uvScale))
            for i in 0...segs {
                let ang = Float(i) / Float(segs) * 2 * Float.pi
                let p = SIMD3<Float>(center.x + sin(ang) * radius, center.y, center.z + cos(ang) * radius)
                pushVertex(p, down, SIMD2<Float>(p.x * uvScale, p.z * uvScale))
            }
            for i in 0..<segs {
                indices.append(cIndex)
                indices.append(cIndex + 2 + UInt32(i))
                indices.append(cIndex + 1 + UInt32(i))
            }
        }
    }

    /// Hängt einen anderen Builder an (z. B. Chunks zusammenführen).
    mutating func append(_ other: MeshBuilder) {
        if other.isEmpty { return }
        let offset = UInt32(positions.count)
        positions.append(contentsOf: other.positions)
        normals.append(contentsOf: other.normals)
        uvs.append(contentsOf: other.uvs)
        indices.reserveCapacity(indices.count + other.indices.count)
        for i in other.indices { indices.append(i + offset) }
    }

    // MARK: - Build

    func build(material: SCNMaterial) -> SCNGeometry {
        guard !indices.isEmpty, !positions.isEmpty else {
            let empty = SCNGeometry()
            empty.materials = [material]
            return empty
        }
        let vertexSource = SCNGeometrySource(vertices: positions)
        let normalSource = SCNGeometrySource(normals: normals)
        let uvSource = SCNGeometrySource(textureCoordinates: uvs)
        let element: SCNGeometryElement
        if positions.count <= 65_535 {
            let small: [UInt16] = indices.map { UInt16(truncatingIfNeeded: $0) }
            element = SCNGeometryElement(indices: small, primitiveType: .triangles)
        } else {
            element = SCNGeometryElement(indices: indices, primitiveType: .triangles)
        }
        let geometry = SCNGeometry(sources: [vertexSource, normalSource, uvSource], elements: [element])
        geometry.materials = [material]
        return geometry
    }

    /// Bequemlichkeit: fertiger Node mit der Geometrie.
    func buildNode(material: SCNMaterial, name: String? = nil, castsShadow: Bool = true) -> SCNNode {
        let node = SCNNode(geometry: build(material: material))
        node.name = name
        node.castsShadow = castsShadow
        return node
    }

    // MARK: - Internals

    private static let axisX = SIMD3<Float>(1, 0, 0)
    private static let axisNegX = SIMD3<Float>(-1, 0, 0)
    private static let axisY = SIMD3<Float>(0, 1, 0)
    private static let axisZ = SIMD3<Float>(0, 0, 1)
    private static let axisNegZ = SIMD3<Float>(0, 0, -1)

    private mutating func pushVertex(_ p: SIMD3<Float>, _ n: SIMD3<Float>, _ uv: SIMD2<Float>) {
        positions.append(SCNVector3(x: p.x, y: p.y, z: p.z))
        normals.append(SCNVector3(x: n.x, y: n.y, z: n.z))
        uvs.append(CGPoint(x: CGFloat(uv.x), y: CGFloat(uv.y)))
    }

    /// p0..p3 gegen den Uhrzeigersinn von vorne gesehen.
    private mutating func pushQuad(_ p0: SIMD3<Float>, _ p1: SIMD3<Float>, _ p2: SIMD3<Float>, _ p3: SIMD3<Float>,
                                   normal n: SIMD3<Float>,
                                   _ t0: SIMD2<Float>, _ t1: SIMD2<Float>, _ t2: SIMD2<Float>, _ t3: SIMD2<Float>) {
        let base = UInt32(positions.count)
        pushVertex(p0, n, t0)
        pushVertex(p1, n, t1)
        pushVertex(p2, n, t2)
        pushVertex(p3, n, t3)
        indices.append(base); indices.append(base + 1); indices.append(base + 2)
        indices.append(base); indices.append(base + 2); indices.append(base + 3)
    }

    /// Rechteck: origin = unten links (von außen gesehen), right/up = Einheitsachsen,
    /// Außennormale = cross(right, up).
    private mutating func pushFace(origin o: SIMD3<Float>, right r: SIMD3<Float>, up u: SIMD3<Float>,
                                   width w: Float, height h: Float, uvScale s: Float,
                                   horizontal: Bool, salt: UInt64) {
        guard w > 0.0001, h > 0.0001 else { return }
        let n = simd_normalize(simd_cross(r, u))
        let p0 = o
        let p1 = o + r * w
        let p2 = o + r * w + u * h
        let p3 = o + u * h
        if horizontal {
            pushQuad(p0, p1, p2, p3, normal: n,
                     SIMD2<Float>(p0.x * s, p0.z * s), SIMD2<Float>(p1.x * s, p1.z * s),
                     SIMD2<Float>(p2.x * s, p2.z * s), SIMD2<Float>(p3.x * s, p3.z * s))
            return
        }
        var tilesU = w * s
        var tilesV = h * s
        if snapsTilesToFaces {
            if tilesU >= 0.75 { tilesU = Swift.max(1, tilesU.rounded()) }
            if tilesV >= 0.75 { tilesV = Swift.max(1, tilesV.rounded()) }
        }
        var offU: Float = 0
        var offV: Float = 0
        if variesFaceOffsets {
            let hsh = MeshBuilder.hashPoint(o, salt: salt)
            offU = Float(hsh & 3) * 0.25
            offV = Float((hsh >> 2) & 3) * 0.25
        }
        // v = 0 oben im Bild → unten an der Fläche liegt v = tilesV (ganze Kachel-Grenze)
        pushQuad(p0, p1, p2, p3, normal: n,
                 SIMD2<Float>(offU, offV + tilesV),
                 SIMD2<Float>(offU + tilesU, offV + tilesV),
                 SIMD2<Float>(offU + tilesU, offV),
                 SIMD2<Float>(offU, offV))
    }

    private static func planarUV(_ p: SIMD3<Float>, normal n: SIMD3<Float>, scale s: Float) -> SIMD2<Float> {
        if abs(n.y) > 0.7 {
            return SIMD2<Float>(p.x * s, p.z * s)
        }
        let rightRaw = simd_cross(axisY, n)
        let len = simd_length(rightRaw)
        let right = len > 1e-5 ? rightRaw / len : axisX
        return SIMD2<Float>(simd_dot(p, right) * s, -p.y * s)
    }

    /// Deterministischer Hash einer Position (ohne Überlauf-Traps).
    private static func hashPoint(_ p: SIMD3<Float>, salt: UInt64) -> UInt64 {
        var h: UInt64 = 0xcbf2_9ce4_8422_2325 ^ salt
        let parts: [UInt32] = [p.x.bitPattern, p.y.bitPattern, p.z.bitPattern]
        for part in parts {
            h ^= UInt64(part)
            h = h &* 0x0000_0100_0000_01b3
            h ^= h >> 29
        }
        // splitmix64 finalizer
        h = (h ^ (h >> 30)) &* 0xbf58_476d_1ce4_e5b9
        h = (h ^ (h >> 27)) &* 0x94d0_49bb_1331_11eb
        h = h ^ (h >> 31)
        return h
    }
}
