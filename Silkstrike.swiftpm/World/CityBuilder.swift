import Foundation
import SceneKit
import UIKit
import simd

// =====================================================================
//  Neo-Haven – prozedurale Stadt (Kollision, Schwing-Ankerpunkte, Verkehr)
// =====================================================================

struct BuildingBox {
    let min: SIMD3<Float>
    let max: SIMD3<Float>
    var center: SIMD3<Float> { return (min + max) * 0.5 }
    var top: Float { return max.y }
}

struct CityCollision {
    var hitGround: Bool = false
    var onRoof: Bool = false
    var hitWall: Bool = false
    var wallNormal: SIMD3<Float> = .zero
}

final class City {
    let root: SCNNode
    let size: Float
    let buildings: [BuildingBox]
    let landmarks: [LandmarkID: SIMD3<Float>]
    let collectiblePositions: [SIMD3<Float>]
    let thugSpawnPoints: [SIMD3<Float>]

    private let gridCell: Float = 50
    private var grid: [Int: [Int]] = [:]
    private let bloodTowerNode: SCNNode
    private let bloodTowerBox: BuildingBox
    private var bloodTowerActive = false
    private let traffic: CityTraffic
    private let blinkMaterial: SCNMaterial
    private let neonMaterials: [SCNMaterial]
    private var time: Float = 0

    fileprivate init(root: SCNNode, size: Float, buildings: [BuildingBox], landmarks: [LandmarkID: SIMD3<Float>],
                     collectibles: [SIMD3<Float>], thugSpawns: [SIMD3<Float>], bloodTower: SCNNode,
                     bloodTowerBox: BuildingBox, traffic: CityTraffic, blinkMaterial: SCNMaterial, neon: [SCNMaterial]) {
        self.root = root
        self.size = size
        self.buildings = buildings
        self.landmarks = landmarks
        self.collectiblePositions = collectibles
        self.thugSpawnPoints = thugSpawns
        self.bloodTowerNode = bloodTower
        self.bloodTowerBox = bloodTowerBox
        self.traffic = traffic
        self.blinkMaterial = blinkMaterial
        self.neonMaterials = neon
        for (i, b) in buildings.enumerated() {
            let x0 = Int(floor(b.min.x / gridCell)), x1 = Int(floor(b.max.x / gridCell))
            let z0 = Int(floor(b.min.z / gridCell)), z1 = Int(floor(b.max.z / gridCell))
            for gx in x0...x1 {
                for gz in z0...z1 {
                    grid[cityGridKey(gx, gz), default: []].append(i)
                }
            }
        }
        bloodTower.isHidden = true
    }

    private func cityGridKey(_ x: Int, _ z: Int) -> Int {
        return (x + 1000) * 4000 + (z + 1000)
    }

    // MARK: Abfragen

    func buildingsNear(_ p: SIMD3<Float>, radius: Float) -> [BuildingBox] {
        let x0 = Int(floor((p.x - radius) / gridCell)), x1 = Int(floor((p.x + radius) / gridCell))
        let z0 = Int(floor((p.z - radius) / gridCell)), z1 = Int(floor((p.z + radius) / gridCell))
        var seen = Set<Int>()
        var result: [BuildingBox] = []
        if x1 >= x0 && z1 >= z0 && (x1 - x0) < 80 && (z1 - z0) < 80 {
            for gx in x0...x1 {
                for gz in z0...z1 {
                    guard let list = grid[cityGridKey(gx, gz)] else { continue }
                    for i in list where !seen.contains(i) {
                        seen.insert(i)
                        result.append(buildings[i])
                    }
                }
            }
        }
        if bloodTowerActive {
            let b = bloodTowerBox
            let dx = Swift.max(b.min.x - p.x, 0, p.x - b.max.x)
            let dz = Swift.max(b.min.z - p.z, 0, p.z - b.max.z)
            if dx * dx + dz * dz <= radius * radius { result.append(b) }
        }
        return result
    }

    func surfaceHeight(at p: SIMD3<Float>) -> Float {
        var best: Float = 0
        for b in buildingsNear(p, radius: 2) {
            if p.x >= b.min.x && p.x <= b.max.x && p.z >= b.min.z && p.z <= b.max.z && b.top <= p.y + 0.5 {
                best = Swift.max(best, b.top)
            }
        }
        return best
    }

    func resolveCollision(position: inout SIMD3<Float>, velocity: inout SIMD3<Float>, radius: Float, height: Float) -> CityCollision {
        var info = CityCollision()
        for b in buildingsNear(position, radius: radius + 4) {
            if position.y >= b.top - 0.001 { continue }
            if position.y + height <= b.min.y { continue }
            let cx = clampf(position.x, b.min.x, b.max.x)
            let cz = clampf(position.z, b.min.z, b.max.z)
            let dx = position.x - cx
            let dz = position.z - cz
            let d2 = dx * dx + dz * dz
            if d2 >= radius * radius { continue }
            // Dachlandung: knapp unter der Dachkante und fallend
            let depth = b.top - position.y
            if depth < 1.6 && velocity.y <= 0.5 {
                let insideXZ = position.x > b.min.x && position.x < b.max.x && position.z > b.min.z && position.z < b.max.z
                if insideXZ || depth < 0.6 {
                    position.y = b.top
                    if velocity.y < 0 { velocity.y = 0 }
                    info.hitGround = true
                    info.onRoof = true
                    continue
                }
            }
            var n = SIMD3<Float>(0, 0, 0)
            var push: Float = 0
            if d2 > 1e-8 {
                let d = d2.squareRoot()
                n = SIMD3<Float>(dx / d, 0, dz / d)
                push = radius - d
            } else {
                // Mittelpunkt steckt in der Box: kürzesten Weg nach außen nehmen
                let options: [(Float, SIMD3<Float>)] = [
                    (position.x - b.min.x, SIMD3<Float>(-1, 0, 0)),
                    (b.max.x - position.x, SIMD3<Float>(1, 0, 0)),
                    (position.z - b.min.z, SIMD3<Float>(0, 0, -1)),
                    (b.max.z - position.z, SIMD3<Float>(0, 0, 1))
                ]
                var best = options[0]
                for o in options where o.0 < best.0 { best = o }
                n = best.1
                push = best.0 + radius
            }
            position += n * push
            let vn = simd_dot(velocity, n)
            if vn < 0 { velocity -= n * vn }
            info.hitWall = true
            info.wallNormal = n
        }
        if position.y <= 0 {
            position.y = 0
            if velocity.y < 0 { velocity.y = 0 }
            info.hitGround = true
        }
        let limit = size * 0.5 + 180
        position.x = clampf(position.x, -limit, limit)
        position.z = clampf(position.z, -limit, limit)
        return info
    }

    func findSwingAnchor(from p: SIMD3<Float>, velocity: SIMD3<Float>, aim: SIMD3<Float>) -> SIMD3<Float>? {
        let flatAim = safeNormalize(flatten(aim), fallback: SIMD3<Float>(0, 0, -1))
        let flatVel = flatten(velocity)
        let dir = safeNormalize(flatAim * 0.65 + safeNormalize(flatVel, fallback: flatAim) * 0.35, fallback: flatAim)
        let probe = p + dir * 32
        var best: SIMD3<Float>? = nil
        var bestScore: Float = -Float.greatestFiniteMagnitude
        for b in buildingsNear(probe, radius: 60) {
            let y = Swift.min(b.top, p.y + 34)
            if y < p.y + 6 { continue }
            // nächster Punkt auf dem Gebäudeumriss zur Sonde, leicht außerhalb
            let cx = clampf(probe.x, b.min.x, b.max.x)
            let cz = clampf(probe.z, b.min.z, b.max.z)
            var c = SIMD3<Float>(cx, y, cz)
            let inside = probe.x > b.min.x && probe.x < b.max.x && probe.z > b.min.z && probe.z < b.max.z
            if inside {
                // Sonde steckt im Gebäude: Kante zum Spieler hin nehmen
                c.x = clampf(p.x, b.min.x, b.max.x)
                c.z = clampf(p.z, b.min.z, b.max.z)
            }
            let outward = safeNormalize(flatten(c - b.center), fallback: -dir)
            c += outward * 0.3
            let delta = c - p
            let dist = simd_length(delta)
            if dist < 12 || dist > 75 { continue }
            let fwd = simd_dot(safeNormalize(flatten(delta), fallback: dir), dir)
            if fwd < 0.15 { continue }
            let score = fwd * 2.2 - abs(dist - 34) / 30 + (c.y - p.y) / 45
            if score > bestScore {
                bestScore = score
                best = c
            }
        }
        return best
    }

    func raycast(from: SIMD3<Float>, direction: SIMD3<Float>, maxDistance: Float) -> SIMD3<Float>? {
        let d = safeNormalize(direction)
        var tBest = maxDistance
        var hit = false
        let mid = from + d * (maxDistance * 0.5)
        for b in buildingsNear(mid, radius: maxDistance * 0.5 + 5) {
            var tmin: Float = 0
            var tmax: Float = tBest
            var ok = true
            for axis in 0..<3 {
                let o = from[axis]
                let dir = d[axis]
                if abs(dir) < 1e-6 {
                    if o < b.min[axis] || o > b.max[axis] { ok = false; break }
                } else {
                    var t1 = (b.min[axis] - o) / dir
                    var t2 = (b.max[axis] - o) / dir
                    if t1 > t2 { swap(&t1, &t2) }
                    tmin = Swift.max(tmin, t1)
                    tmax = Swift.min(tmax, t2)
                    if tmin > tmax { ok = false; break }
                }
            }
            if ok && tmin > 0.01 && tmin < tBest {
                tBest = tmin
                hit = true
            }
        }
        if d.y < -1e-4 {
            let tg = -from.y / d.y
            if tg > 0 && tg < tBest {
                tBest = tg
                hit = true
            }
        }
        return hit ? from + d * tBest : nil
    }

    func setBloodTowerActive(_ active: Bool) {
        bloodTowerActive = active
        bloodTowerNode.isHidden = !active
    }

    func update(dt: Float, cameraPosition: SIMD3<Float>) {
        time += dt
        traffic.update(dt: dt)
        let blink = fmodf(time, 1.4) < 0.18
        blinkMaterial.emission.intensity = blink ? 6 : 0.2
        for (i, m) in neonMaterials.enumerated() {
            let flick = sinf(time * (7 + Float(i) * 3.1)) + sinf(time * 13.7 + Float(i))
            m.emission.intensity = CGFloat(flick > 1.75 ? 0.4 : 2.6)
        }
    }
}

// MARK: - Bauer

enum CityBuilder {

    private static let blockPitch: Float = 100
    private static let streetWidth: Float = 20
    private static let blocks = 9

    /// Sammelt Geometrie pro Material.
    private struct CityMeshSet {
        var facades: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var roofs = MeshBuilder()
        var metal = MeshBuilder()
        var stone = MeshBuilder()
        var sidewalks = MeshBuilder()
        var glow = MeshBuilder()
        var blink = MeshBuilder()
        var neon: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var trees = MeshBuilder()
        var trunks = MeshBuilder()
        var grass = MeshBuilder()
        var crimson = MeshBuilder()
    }

    private enum CityDistrict {
        case center, plaza, park, oldTown, industry, harbor, residential
    }

    private static func district(_ i: Int, _ j: Int) -> CityDistrict {
        if i == 4 && j == 4 { return .plaza }
        if (i == 6 || i == 7) && (j == 1 || j == 2) { return .park }
        if (3...5).contains(i) && (3...5).contains(j) { return .center }
        if i <= 2 && j <= 3 { return .oldTown }
        if i >= 6 && (5...7).contains(j) { return .industry }
        if j == 8 { return .harbor }
        return .residential
    }

    /// Blockgrenzen (x0, z0, x1, z1) ohne Straßen.
    private static func blockRect(_ i: Int, _ j: Int) -> (Float, Float, Float, Float) {
        let half = Float(blocks) * blockPitch * 0.5
        let x0 = -half + Float(i) * blockPitch + streetWidth * 0.5
        let z0 = -half + Float(j) * blockPitch + streetWidth * 0.5
        return (x0, z0, x0 + blockPitch - streetWidth, z0 + blockPitch - streetWidth)
    }

    static func build(seed: UInt64, quality: QualityPreset, timeOfDay: TimeOfDay) -> City {
        var rng = SeededRandom(seed: seed)
        let root = SCNNode()
        root.name = "NeoHaven"
        let size = Float(blocks) * blockPitch
        var mesh = CityMeshSet()
        var boxes: [BuildingBox] = []
        var landmarks: [LandmarkID: SIMD3<Float>] = [:]
        var collectibles: [SIMD3<Float>] = []
        var thugSpawns: [SIMD3<Float>] = []
        var roofTops: [SIMD3<Float>] = []

        func addBuilding(_ lo: SIMD3<Float>, _ hi: SIMD3<Float>, style: Int, props: Bool) {
            guard hi.x - lo.x > 1, hi.z - lo.z > 1, hi.y - lo.y > 1 else { return }
            boxes.append(BuildingBox(min: lo, max: hi))
            let s = ((style % 4) + 4) % 4
            mesh.facades[s].addBox(min: lo, max: hi, uvScale: 1 / ProceduralTextures.facadeTileMeters)
            // Dachplatte + Brüstung
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 0.05, hi.z), uvScale: 0.12)
            let t: Float = 0.35
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 1.1, lo.z + t), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, hi.z - t), max: SIMD3<Float>(hi.x, hi.y + 1.1, hi.z), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(lo.x + t, hi.y + 1.1, hi.z), uvScale: 0.25)
            mesh.roofs.addBox(min: SIMD3<Float>(hi.x - t, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 1.1, hi.z), uvScale: 0.25)
            let top = SIMD3<Float>((lo.x + hi.x) * 0.5, hi.y, (lo.z + hi.z) * 0.5)
            roofTops.append(top)
            guard props else { return }
            let w = hi.x - lo.x
            let d = hi.z - lo.z
            // Klimageräte
            let acCount = rng.int(1, 4)
            for _ in 0..<acCount {
                let px = rng.float(lo.x + 2, Swift.max(lo.x + 2.1, hi.x - 4))
                let pz = rng.float(lo.z + 2, Swift.max(lo.z + 2.1, hi.z - 4))
                mesh.metal.addBox(min: SIMD3<Float>(px, hi.y, pz), max: SIMD3<Float>(px + 2.2, hi.y + 1.4, pz + 1.6), uvScale: 0.3)
            }
            // Wassertank
            if rng.chance(0.4) && w > 12 && d > 12 {
                let c = SIMD3<Float>(lo.x + w * 0.3, hi.y + 3, lo.z + d * 0.65)
                for k in 0..<4 {
                    let ox: Float = k % 2 == 0 ? -1.4 : 1.4
                    let oz: Float = k < 2 ? -1.4 : 1.4
                    mesh.metal.addBox(min: SIMD3<Float>(c.x + ox - 0.15, hi.y, c.z + oz - 0.15),
                                      max: SIMD3<Float>(c.x + ox + 0.15, hi.y + 3, c.z + oz + 0.15), uvScale: 0.3)
                }
                mesh.stone.addCylinder(center: c, radius: 2.1, height: 3.6, segments: quality == .performance ? 8 : 14, uvScale: 0.2)
                mesh.stone.addCone(center: c + SIMD3<Float>(0, 3.6, 0), radius: 2.3, height: 1.2, segments: quality == .performance ? 8 : 14)
            }
            // Antenne mit Blinklicht
            if hi.y > 60 && rng.chance(0.6) {
                let a = SIMD3<Float>(lo.x + w * 0.7, hi.y, lo.z + d * 0.3)
                let h = rng.float(6, 18)
                mesh.metal.addCylinder(center: a, radius: 0.15, height: h, segments: 6)
                mesh.blink.addBox(min: a + SIMD3<Float>(-0.35, h, -0.35), max: a + SIMD3<Float>(0.35, h + 0.7, 0.35), uvScale: 1)
            }
            // Leuchtreklame
            if rng.chance(0.25) {
                let ny = hi.y + 1.2
                let neonIndex = rng.int(0, 3)
                if rng.chance(0.5) {
                    mesh.metal.addBox(min: SIMD3<Float>(lo.x + 2, hi.y, lo.z + 0.4), max: SIMD3<Float>(lo.x + 2.3, ny + 4, lo.z + 0.7), uvScale: 0.3)
                    mesh.neon[neonIndex].addBox(min: SIMD3<Float>(lo.x + 1, ny, lo.z + 0.2), max: SIMD3<Float>(Swift.min(hi.x - 1, lo.x + 14), ny + 3.5, lo.z + 0.5), uvScale: 1)
                } else {
                    mesh.neon[neonIndex].addBox(min: SIMD3<Float>(hi.x + 0.05, hi.y * 0.55, lo.z + d * 0.4), max: SIMD3<Float>(hi.x + 0.6, hi.y * 0.55 + 9, lo.z + d * 0.4 + 2.5), uvScale: 1)
                }
            }
        }

        func addTower(x0: Float, z0: Float, x1: Float, z1: Float, height: Float, style: Int) {
            var h0: Float = 0
            var lo = SIMD3<Float>(x0, 0, z0)
            var hi = SIMD3<Float>(x1, 0, z1)
            let tiers = height > 90 ? (height > 160 ? 3 : 2) : 1
            for t in 0..<tiers {
                let frac: Float = tiers == 1 ? 1 : (t == tiers - 1 ? 1 : (t == 0 ? 0.55 : 0.82))
                let hTop = height * frac
                lo.y = h0
                hi.y = hTop
                addBuilding(lo, hi, style: style, props: t == tiers - 1)
                h0 = hTop
                let inset = Swift.min(hi.x - lo.x, hi.z - lo.z) * 0.12
                lo.x += inset; lo.z += inset; hi.x -= inset; hi.z -= inset
            }
        }

        // --- Bodenflächen -------------------------------------------------------
        let half = size * 0.5
        var ground = MeshBuilder()
        ground.addQuad(SIMD3<Float>(-half - 150, 0, -half - 150), SIMD3<Float>(-half - 150, 0, half + 10),
                       SIMD3<Float>(half + 150, 0, half + 10), SIMD3<Float>(half + 150, 0, -half - 150), uvScale: 0.125)
        var lanes = MeshBuilder()
        var lampPosts = MeshBuilder()
        var lampHeads = MeshBuilder()
        for k in 0...blocks {
            let c = -half + Float(k) * blockPitch
            var s: Float = -half
            while s < half {
                lanes.addBox(min: SIMD3<Float>(c - 0.12, 0.02, s), max: SIMD3<Float>(c + 0.12, 0.04, s + 3), uvScale: 1)
                lanes.addBox(min: SIMD3<Float>(s, 0.02, c - 0.12), max: SIMD3<Float>(s + 3, 0.04, c + 0.12), uvScale: 1)
                s += 8
            }
            var t: Float = -half + 20
            while t < half {
                for side: Float in [-1, 1] {
                    let p1 = SIMD3<Float>(c + side * 8.5, 0, t)
                    let p2 = SIMD3<Float>(t, 0, c + side * 8.5)
                    for p in [p1, p2] {
                        lampPosts.addCylinder(center: p, radius: 0.12, height: 7, segments: 6)
                        lampHeads.addBox(min: p + SIMD3<Float>(-0.4, 7, -0.4), max: p + SIMD3<Float>(0.4, 7.25, 0.4), uvScale: 1)
                    }
                }
                t += 50
            }
        }

        // --- Blöcke --------------------------------------------------------------
        for i in 0..<blocks {
            for j in 0..<blocks {
                let (x0, z0, x1, z1) = blockRect(i, j)
                let dist = district(i, j)
                if dist != .park {
                    mesh.sidewalks.addBox(min: SIMD3<Float>(x0 - 3, 0, z0 - 3), max: SIMD3<Float>(x1 + 3, 0.15, z1 + 3), uvScale: 0.25)
                }
                switch dist {
                case .plaza:
                    // Platz für den Blutturm (Sockel + Ziel am Boden)
                    mesh.stone.addBox(min: SIMD3<Float>(x0 + 10, 0.15, z0 + 10), max: SIMD3<Float>(x1 - 10, 0.6, z1 - 10), uvScale: 0.2)
                    landmarks[.bloodTower] = SIMD3<Float>((x0 + x1) * 0.5, 0.6, z1 - 6)
                case .park:
                    mesh.grass.addBox(min: SIMD3<Float>(x0 - 3, 0, z0 - 3), max: SIMD3<Float>(x1 + 3, 0.2, z1 + 3), uvScale: 0.1)
                    let treeCount = quality == .performance ? 10 : 22
                    for _ in 0..<treeCount {
                        let p = SIMD3<Float>(rng.float(x0, x1), 0.2, rng.float(z0, z1))
                        let h = rng.float(5, 10)
                        mesh.trunks.addCylinder(center: p, radius: 0.3, height: h * 0.45, segments: 6)
                        mesh.trees.addCone(center: p + SIMD3<Float>(0, h * 0.35, 0), radius: h * 0.32, height: h * 0.75, segments: 8, capBottom: true)
                    }
                default:
                    break
                }
                if dist == .plaza || dist == .park { continue }

                let isDom = (i == 1 && j == 1)
                let isFoundry = (i == 7 && j == 6)
                let isLab = (i == 5 && j == 2)
                let isHome = (i == 2 && j == 5)
                let isCrane = (i == 2 && j == 8)

                if isDom {
                    let cx = (x0 + x1) * 0.5
                    let cz = (z0 + z1) * 0.5
                    // Kirchenschiff
                    let nlo = SIMD3<Float>(cx - 14, 0, cz - 32), nhi = SIMD3<Float>(cx + 14, 30, cz + 30)
                    boxes.append(BuildingBox(min: nlo, max: nhi))
                    mesh.stone.addBox(min: nlo, max: nhi, uvScale: 0.15)
                    mesh.stone.addBox(min: SIMD3<Float>(cx - 15, 30, cz - 32), max: SIMD3<Float>(cx + 15, 31, cz + 30), uvScale: 0.15)
                    // Strebepfeiler
                    var zz = cz - 28
                    while zz < cz + 28 {
                        mesh.stone.addBox(min: SIMD3<Float>(cx - 17, 0, zz), max: SIMD3<Float>(cx - 14, 22, zz + 2), uvScale: 0.2)
                        mesh.stone.addBox(min: SIMD3<Float>(cx + 14, 0, zz), max: SIMD3<Float>(cx + 17, 22, zz + 2), uvScale: 0.2)
                        mesh.glow.addBox(min: SIMD3<Float>(cx - 14.05, 8, zz + 3), max: SIMD3<Float>(cx + 14.05, 20, zz + 5), uvScale: 1)
                        zz += 8
                    }
                    // Zwei Türme mit Spitzen
                    for side: Float in [-1, 1] {
                        let tlo = SIMD3<Float>(cx + side * 9 - 6, 0, cz + 30), thi = SIMD3<Float>(cx + side * 9 + 6, 72, cz + 42)
                        boxes.append(BuildingBox(min: tlo, max: thi))
                        mesh.stone.addBox(min: tlo, max: thi, uvScale: 0.15)
                        mesh.stone.addCone(center: SIMD3<Float>(cx + side * 9, 72, cz + 36), radius: 7, height: 34, segments: 4)
                        collectibles.append(SIMD3<Float>(cx + side * 9, 73.5, cz + 36))
                    }
                    // Rosettenfenster
                    mesh.glow.addCylinder(center: SIMD3<Float>(cx, 20, cz + 42.05), radius: 5, height: 0.2, segments: 16)
                    landmarks[.cathedral] = SIMD3<Float>(cx, 31, cz)
                    continue
                }
                if isFoundry {
                    let lo = SIMD3<Float>(x0 + 4, 0, z0 + 8), hi = SIMD3<Float>(x1 - 4, 22, z1 - 20)
                    boxes.append(BuildingBox(min: lo, max: hi))
                    mesh.metal.addBox(min: lo, max: hi, uvScale: 0.08)
                    mesh.glow.addBox(min: SIMD3<Float>(lo.x + 4, 6, hi.z + 0.02), max: SIMD3<Float>(hi.x - 4, 12, hi.z + 0.1), uvScale: 1)
                    for k in 0..<3 {
                        let c = SIMD3<Float>(lo.x + 12 + Float(k) * 22, 0, z1 - 10)
                        boxes.append(BuildingBox(min: c - SIMD3<Float>(3, 0, 3), max: c + SIMD3<Float>(3, 64, 3)))
                        mesh.stone.addCylinder(center: c, radius: 3, height: 64, segments: 12, uvScale: 0.1)
                        mesh.glow.addCylinder(center: c + SIMD3<Float>(0, 61, 0), radius: 3.1, height: 2.5, segments: 12)
                    }
                    landmarks[.foundry] = SIMD3<Float>((lo.x + hi.x) * 0.5, 22, (lo.z + hi.z) * 0.5)
                    continue
                }
                if isCrane {
                    // Lagerhalle + Hafenkran am Wasser
                    addBuilding(SIMD3<Float>(x0 + 2, 0, z0 + 2), SIMD3<Float>(x1 - 30, 14, z1 - 30), style: 2, props: true)
                    let base = SIMD3<Float>(x1 - 14, 0, z1 + 4)
                    let towerLo = base - SIMD3<Float>(4, 0, 4)
                    let towerHi = base + SIMD3<Float>(4, 52, 4)
                    boxes.append(BuildingBox(min: towerLo, max: towerHi))
                    for k in 0..<4 {
                        let ox: Float = k % 2 == 0 ? -3.6 : 3.6
                        let oz: Float = k < 2 ? -3.6 : 3.6
                        mesh.crimson.addBox(min: base + SIMD3<Float>(ox - 0.5, 0, oz - 0.5), max: base + SIMD3<Float>(ox + 0.5, 52, oz + 0.5), uvScale: 0.2)
                    }
                    mesh.crimson.addBox(min: base + SIMD3<Float>(-4, 50, -4), max: base + SIMD3<Float>(4, 53, 4), uvScale: 0.2)
                    mesh.crimson.addBox(min: base + SIMD3<Float>(-1.2, 53, -40), max: base + SIMD3<Float>(1.2, 55.5, 26), uvScale: 0.2)
                    mesh.blink.addBox(min: base + SIMD3<Float>(-0.4, 55.5, -40), max: base + SIMD3<Float>(0.4, 56.3, -39.2), uvScale: 1)
                    landmarks[.harborCrane] = base + SIMD3<Float>(0, 53, 0)
                    // Container
                    for k in 0..<10 {
                        let cxp = x0 + 4 + Float(k % 5) * 7
                        let czp = z1 - 24 + Float(k / 5) * 3.2
                        let stack = Float(1 + (k * 7) % 3)
                        let lo = SIMD3<Float>(cxp, 0, czp), hi = SIMD3<Float>(cxp + 6, 2.6 * stack, czp + 2.5)
                        boxes.append(BuildingBox(min: lo, max: hi))
                        mesh.neon[k % 3].addBox(min: lo, max: hi, uvScale: 0.3)
                    }
                    continue
                }

                // Normale Bebauung: 1–4 Grundstücke
                let w = x1 - x0
                let d = z1 - z0
                let splitX = rng.chance(0.6)
                let splitZ = rng.chance(0.6)
                let xs: [Float] = splitX ? [x0, x0 + w * rng.float(0.4, 0.6), x1] : [x0, x1]
                let zs: [Float] = splitZ ? [z0, z0 + d * rng.float(0.4, 0.6), z1] : [z0, z1]
                for a in 0..<(xs.count - 1) {
                    for b in 0..<(zs.count - 1) {
                        let lx0 = xs[a] + 1.5, lx1 = xs[a + 1] - 1.5
                        let lz0 = zs[b] + 1.5, lz1 = zs[b + 1] - 1.5
                        var height: Float
                        var style: Int
                        switch dist {
                        case .center: height = rng.float(90, 210); style = rng.chance(0.6) ? 0 : 3
                        case .oldTown: height = rng.float(16, 40); style = 1
                        case .industry: height = rng.float(12, 30); style = 2
                        case .harbor: height = rng.float(10, 22); style = 2
                        default: height = rng.float(25, 95); style = rng.int(0, 4)
                        }
                        if isLab && a == 0 && b == 0 {
                            addTower(x0: x0 + 6, z0: z0 + 6, x1: x1 - 6, z1: z1 - 6, height: 185, style: 0)
                            mesh.glow.addBox(min: SIMD3<Float>(x0 + 14, 185 * 0.82 + 2, z0 + 14), max: SIMD3<Float>(x1 - 14, 185 * 0.82 + 3, z1 - 14), uvScale: 1)
                            landmarks[.labTower] = SIMD3<Float>((x0 + x1) * 0.5, 185, (z0 + z1) * 0.5)
                            break
                        }
                        if isLab { continue }
                        if isHome && a == 0 && b == 0 {
                            height = 36
                            style = 1
                            addBuilding(SIMD3<Float>(lx0, 0, lz0), SIMD3<Float>(lx1, height, lz1), style: style, props: false)
                            landmarks[.heroApartment] = SIMD3<Float>((lx0 + lx1) * 0.5, height, (lz0 + lz1) * 0.5)
                            continue
                        }
                        addTower(x0: lx0, z0: lz0, x1: lx1, z1: lz1, height: height, style: style)
                    }
                }
            }
        }

        // U-Bahn-Eingang (Straßenniveau)
        do {
            let (x0, z0, _, _) = blockRect(3, 6)
            let p = SIMD3<Float>(x0 - 1, 0, z0 - 1)
            mesh.metal.addBox(min: p + SIMD3<Float>(-1.5, 0, -4), max: p + SIMD3<Float>(1.5, 3, 0), uvScale: 0.3)
            mesh.glow.addBox(min: p + SIMD3<Float>(-0.8, 3, -0.8), max: p + SIMD3<Float>(0.8, 4.6, 0.8), uvScale: 1)
            landmarks[.subwayEntrance] = p + SIMD3<Float>(-5, 0, 3)
        }
        // Rissherz über dem Stadtpark
        do {
            let (x0, z0, _, _) = blockRect(6, 1)
            let (_, _, x1, z1) = blockRect(7, 2)
            let c = SIMD3<Float>((x0 + x1) * 0.5, 0.2, (z0 + z1) * 0.5)
            landmarks[.riftCore] = c
            let rift = FX.makeRiftSwirl(color: UIColor(red: 0.9, green: 0.05, blue: 0.12, alpha: 1))
            rift.simdPosition = c + SIMD3<Float>(0, 70, 0)
            rift.simdScale = SIMD3<Float>(repeating: 7)
            root.addChildNode(rift)
        }

        // Fehlende Wahrzeichen absichern
        let fallback = roofTops.first ?? SIMD3<Float>(0, 0, 0)
        for id in LandmarkID.allCases where landmarks[id] == nil {
            landmarks[id] = fallback
        }

        // Sammelobjekte & Schläger-Spawns
        var tops = roofTops
        var shuffleRng = SeededRandom(seed: seed ^ 0x5EED)
        tops.shuffle(using: &shuffleRng)
        for t in tops.prefix(Swift.max(0, 40 - collectibles.count)) {
            collectibles.append(t + SIMD3<Float>(0, 1.4, 0))
        }
        for k in 0..<12 {
            let a = k % 8 + 1
            let b = (k * 5) % 8 + 1
            let x = -half + Float(a) * blockPitch
            let z = -half + Float(b) * blockPitch
            thugSpawns.append(SIMD3<Float>(x, 0, z))
        }
        for t in tops.suffix(4) { thugSpawns.append(t) }

        // --- Materialien & Nodes --------------------------------------------------
        let wet: Float = timeOfDay == .dusk ? 0.55 : 0.3
        let groundMat = Render.texturedPBR(diffuse: ProceduralTextures.asphalt(), normal: ProceduralTextures.asphaltNormal(),
                                           roughness: wet, metalness: 0.05)
        root.addChildNode(ground.buildNode(material: groundMat, name: "ground", castsShadow: false))
        root.addChildNode(lanes.buildNode(material: Render.pbr(UIColor(white: 0.8, alpha: 1), roughness: 0.5, metalness: 0,
                                                               emission: UIColor(white: 0.25, alpha: 1)), name: "lanes", castsShadow: false))
        let concreteMat = Render.texturedPBR(diffuse: ProceduralTextures.concrete(), roughness: 0.85, metalness: 0)
        root.addChildNode(mesh.sidewalks.buildNode(material: concreteMat, name: "sidewalks", castsShadow: false))
        root.addChildNode(lampPosts.buildNode(material: Render.pbr(UIColor(white: 0.15, alpha: 1), roughness: 0.4, metalness: 0.8), name: "lamps"))
        root.addChildNode(lampHeads.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.78, blue: 0.5, alpha: 1), intensity: 4), name: "lampHeads", castsShadow: false))

        for s in 0..<4 where !mesh.facades[s].isEmpty {
            let mat = Render.texturedPBR(diffuse: ProceduralTextures.facade(style: s, lit: false),
                                         roughness: s == 0 ? 0.25 : 0.7, metalness: s == 0 ? 0.5 : 0.05,
                                         emission: ProceduralTextures.facade(style: s, lit: true))
            mat.emission.intensity = timeOfDay == .dusk ? 0.9 : 1.6
            root.addChildNode(mesh.facades[s].buildNode(material: mat, name: "facade\(s)"))
        }
        root.addChildNode(mesh.roofs.buildNode(material: concreteMat, name: "roofs"))
        let metalMat = Render.texturedPBR(diffuse: ProceduralTextures.metalPanels(), roughness: 0.45, metalness: 0.7)
        root.addChildNode(mesh.metal.buildNode(material: metalMat, name: "metal"))
        let stoneMat = Render.texturedPBR(diffuse: ProceduralTextures.brick(), roughness: 0.8, metalness: 0, tileScale: 1)
        stoneMat.diffuse.contents = UIColor(red: 0.42, green: 0.40, blue: 0.38, alpha: 1)
        root.addChildNode(mesh.stone.buildNode(material: stoneMat, name: "stone"))
        root.addChildNode(mesh.glow.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.55, blue: 0.2, alpha: 1), intensity: 3), name: "glow", castsShadow: false))
        let blinkMat = Render.emissive(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 6)
        root.addChildNode(mesh.blink.buildNode(material: blinkMat, name: "blink", castsShadow: false))
        let neonColors: [UIColor] = [UIColor(red: 1, green: 0.1, blue: 0.45, alpha: 1),
                                     UIColor(red: 0.1, green: 0.85, blue: 1, alpha: 1),
                                     UIColor(red: 1, green: 0.6, blue: 0.1, alpha: 1)]
        var neonMats: [SCNMaterial] = []
        for k in 0..<3 {
            let m = Render.emissive(neonColors[k], intensity: 2.6)
            neonMats.append(m)
            if !mesh.neon[k].isEmpty {
                root.addChildNode(mesh.neon[k].buildNode(material: m, name: "neon\(k)", castsShadow: false))
            }
        }
        root.addChildNode(mesh.grass.buildNode(material: Render.pbr(UIColor(red: 0.07, green: 0.14, blue: 0.06, alpha: 1), roughness: 0.95, metalness: 0), name: "grass", castsShadow: false))
        root.addChildNode(mesh.trees.buildNode(material: Render.pbr(UIColor(red: 0.05, green: 0.16, blue: 0.07, alpha: 1), roughness: 0.9, metalness: 0), name: "trees"))
        root.addChildNode(mesh.trunks.buildNode(material: Render.pbr(UIColor(red: 0.16, green: 0.1, blue: 0.06, alpha: 1), roughness: 0.9, metalness: 0), name: "trunks"))
        root.addChildNode(mesh.crimson.buildNode(material: Render.pbr(UIColor(red: 0.75, green: 0.12, blue: 0.08, alpha: 1), roughness: 0.5, metalness: 0.6), name: "crane"))

        // Wasser (Hafen)
        var water = MeshBuilder()
        water.addQuad(SIMD3<Float>(-half - 400, -0.6, half + 10), SIMD3<Float>(-half - 400, -0.6, half + 700),
                      SIMD3<Float>(half + 400, -0.6, half + 700), SIMD3<Float>(half + 400, -0.6, half + 10), uvScale: 0.05)
        let waterMat = Render.pbr(UIColor(red: 0.01, green: 0.03, blue: 0.05, alpha: 1), roughness: 0.06, metalness: 0.85)
        root.addChildNode(water.buildNode(material: waterMat, name: "water", castsShadow: false))

        // Ein paar echte Lichter an Wahrzeichen
        let lightSpots: [(LandmarkID, UIColor)] = [(.cathedral, UIColor(red: 1, green: 0.6, blue: 0.3, alpha: 1)),
                                                   (.foundry, UIColor(red: 1, green: 0.4, blue: 0.1, alpha: 1)),
                                                   (.subwayEntrance, UIColor(red: 0.4, green: 0.7, blue: 1, alpha: 1))]
        for (id, color) in lightSpots {
            if let p = landmarks[id] {
                let l = Render.makePointLight(color: color, intensity: 2500, range: 60)
                l.simdPosition = p + SIMD3<Float>(0, 12, 0)
                root.addChildNode(l)
            }
        }

        // Blutturm (nur im Finale sichtbar)
        let towerBase = landmarks[.bloodTower] ?? SIMD3<Float>(0, 0, 0)
        let towerCenter = SIMD3<Float>(0, 0, towerBase.z - 34)
        let tower = makeBloodTower(at: towerCenter, quality: quality)
        root.addChildNode(tower)
        let towerBox = BuildingBox(min: towerCenter + SIMD3<Float>(-16, 0, -16), max: towerCenter + SIMD3<Float>(16, 300, 16))

        let traffic = CityTraffic(size: size, blockPitch: blockPitch, quality: quality, seed: seed)
        root.addChildNode(traffic.root)

        return City(root: root, size: size, buildings: boxes, landmarks: landmarks, collectibles: collectibles,
                    thugSpawns: thugSpawns, bloodTower: tower, bloodTowerBox: towerBox, traffic: traffic,
                    blinkMaterial: blinkMat, neon: neonMats)
    }

    private static func makeBloodTower(at c: SIMD3<Float>, quality: QualityPreset) -> SCNNode {
        let node = SCNNode()
        node.name = "Blutturm"
        var body = MeshBuilder()
        var veins = MeshBuilder()
        var y: Float = 0
        var r: Float = 16
        let segs = 10
        for k in 0..<segs {
            let h: Float = 32
            body.addBox(min: c + SIMD3<Float>(-r, y, -r), max: c + SIMD3<Float>(r, y + h, r), uvScale: 0.05)
            veins.addBox(min: c + SIMD3<Float>(-r - 0.1, y + h * 0.3, -0.6), max: c + SIMD3<Float>(r + 0.1, y + h * 0.75, 0.6), uvScale: 1)
            veins.addBox(min: c + SIMD3<Float>(-0.6, y + h * 0.3, -r - 0.1), max: c + SIMD3<Float>(0.6, y + h * 0.75, r + 0.1), uvScale: 1)
            if k % 2 == 0 {
                for sx: Float in [-1, 1] {
                    body.addCone(center: c + SIMD3<Float>(sx * (r + 2), y + h * 0.6, 0), radius: 2, height: 9, segments: 5)
                }
            }
            y += h
            r *= 0.86
        }
        body.addCone(center: c + SIMD3<Float>(0, y, 0), radius: r, height: 40, segments: 6)
        node.addChildNode(body.buildNode(material: Render.pbr(UIColor(red: 0.08, green: 0.01, blue: 0.015, alpha: 1), roughness: 0.3, metalness: 0.7), name: "towerBody"))
        node.addChildNode(veins.buildNode(material: Render.emissive(UIColor(red: 1, green: 0.04, blue: 0.08, alpha: 1), intensity: 5), name: "towerVeins", castsShadow: false))
        let rift = FX.makeRiftSwirl(color: UIColor(red: 1, green: 0.05, blue: 0.1, alpha: 1))
        rift.simdPosition = c + SIMD3<Float>(0, y + 60, 0)
        rift.simdScale = SIMD3<Float>(repeating: 9)
        node.addChildNode(rift)
        for k in 0..<3 {
            let l = Render.makePointLight(color: UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 6000, range: 160)
            l.simdPosition = c + SIMD3<Float>(0, 40 + Float(k) * 100, 26)
            node.addChildNode(l)
        }
        return node
    }

    // MARK: Kulisse für Cutscenes / Titel

    static func buildBackdrop(seed: UInt64, quality: QualityPreset, timeOfDay: TimeOfDay, clearRadius: Float) -> SCNNode {
        var rng = SeededRandom(seed: seed)
        let root = SCNNode()
        root.name = "Skyline"
        var facades: [MeshBuilder] = [MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()]
        var roofs = MeshBuilder()
        var blink = MeshBuilder()
        let count = quality == .performance ? 90 : (quality == .balanced ? 150 : 220)
        let groundY: Float = -60
        for _ in 0..<count {
            let ang = rng.float(0, Float.pi * 2)
            let dist = clearRadius + 12 + rng.float(0, 260) * rng.float(0.3, 1)
            let cx = cosf(ang) * dist
            let cz = sinf(ang) * dist
            let w = rng.float(10, 28)
            let d = rng.float(10, 28)
            let h = rng.float(30, dist > 150 ? 230 : 140)
            let lo = SIMD3<Float>(cx - w * 0.5, groundY, cz - d * 0.5)
            let hi = SIMD3<Float>(cx + w * 0.5, groundY + h, cz + d * 0.5)
            let s = rng.int(0, 4)
            facades[s].addBox(min: lo, max: hi, uvScale: 1 / ProceduralTextures.facadeTileMeters)
            roofs.addBox(min: SIMD3<Float>(lo.x, hi.y, lo.z), max: SIMD3<Float>(hi.x, hi.y + 0.6, hi.z), uvScale: 0.1)
            if h > 120 && rng.chance(0.5) {
                blink.addBox(min: SIMD3<Float>(cx - 0.4, hi.y + 4, cz - 0.4), max: SIMD3<Float>(cx + 0.4, hi.y + 4.8, cz + 0.4), uvScale: 1)
                roofs.addBox(min: SIMD3<Float>(cx - 0.1, hi.y, cz - 0.1), max: SIMD3<Float>(cx + 0.1, hi.y + 4, cz + 0.1), uvScale: 1)
            }
        }
        for s in 0..<4 where !facades[s].isEmpty {
            let mat = Render.texturedPBR(diffuse: ProceduralTextures.facade(style: s, lit: false),
                                         roughness: s == 0 ? 0.25 : 0.7, metalness: s == 0 ? 0.5 : 0.05,
                                         emission: ProceduralTextures.facade(style: s, lit: true))
            mat.emission.intensity = timeOfDay == .dusk ? 0.9 : 1.6
            root.addChildNode(facades[s].buildNode(material: mat, name: "bgFacade\(s)", castsShadow: false))
        }
        root.addChildNode(roofs.buildNode(material: Render.pbr(UIColor(white: 0.2, alpha: 1), roughness: 0.8, metalness: 0), name: "bgRoofs", castsShadow: false))
        let blinkMat = Render.emissive(UIColor(red: 1, green: 0.1, blue: 0.1, alpha: 1), intensity: 5)
        let pulse = CABasicAnimation(keyPath: "emission.intensity")
        pulse.fromValue = 0.2
        pulse.toValue = 6
        pulse.duration = 0.7
        pulse.autoreverses = true
        pulse.repeatCount = .infinity
        blinkMat.addAnimation(pulse, forKey: "blink")
        root.addChildNode(blink.buildNode(material: blinkMat, name: "bgBlink", castsShadow: false))
        var ground = MeshBuilder()
        let r = clearRadius + 600
        ground.addQuad(SIMD3<Float>(-r, groundY, -r), SIMD3<Float>(-r, groundY, r), SIMD3<Float>(r, groundY, r), SIMD3<Float>(r, groundY, -r), uvScale: 0.05)
        root.addChildNode(ground.buildNode(material: Render.texturedPBR(diffuse: ProceduralTextures.asphalt(), roughness: 0.35, metalness: 0.05),
                                           name: "bgGround", castsShadow: false))
        return root
    }
}

// MARK: - Verkehr

final class CityTraffic {
    let root = SCNNode()

    private struct CityCar {
        let node: SCNNode
        let alongX: Bool
        let fixed: Float
        let dir: Float
        var s: Float
        let speed: Float
    }

    private var cars: [CityCar] = []
    private let half: Float

    init(size: Float, blockPitch: Float, quality: QualityPreset, seed: UInt64) {
        half = size * 0.5
        root.name = "Traffic"
        var rng = SeededRandom(seed: seed ^ 0xCA25)
        let count: Int
        switch quality {
        case .performance: count = 22
        case .balanced: count = 40
        case .ultra: count = 64
        }
        var body = MeshBuilder()
        body.addBox(min: SIMD3<Float>(-0.95, 0.3, -2.2), max: SIMD3<Float>(0.95, 1.05, 2.2), uvScale: 1)
        body.addBox(min: SIMD3<Float>(-0.85, 1.05, -1.1), max: SIMD3<Float>(0.85, 1.55, 1.0), uvScale: 1)
        var front = MeshBuilder()
        front.addBox(min: SIMD3<Float>(-0.85, 0.65, 2.2), max: SIMD3<Float>(-0.45, 0.85, 2.26), uvScale: 1)
        front.addBox(min: SIMD3<Float>(0.45, 0.65, 2.2), max: SIMD3<Float>(0.85, 0.85, 2.26), uvScale: 1)
        var rear = MeshBuilder()
        rear.addBox(min: SIMD3<Float>(-0.9, 0.7, -2.26), max: SIMD3<Float>(0.9, 0.85, -2.2), uvScale: 1)
        let paint: [UIColor] = [UIColor(white: 0.08, alpha: 1), UIColor(red: 0.5, green: 0.05, blue: 0.05, alpha: 1),
                                UIColor(white: 0.7, alpha: 1), UIColor(red: 0.05, green: 0.12, blue: 0.3, alpha: 1),
                                UIColor(red: 0.85, green: 0.65, blue: 0.1, alpha: 1)]
        let bodyGeos: [SCNGeometry] = paint.map { body.build(material: Render.pbr($0, roughness: 0.25, metalness: 0.8)) }
        let frontGeo = front.build(material: Render.emissive(UIColor(red: 1, green: 0.95, blue: 0.8, alpha: 1), intensity: 8))
        let rearGeo = rear.build(material: Render.emissive(UIColor(red: 1, green: 0.05, blue: 0.05, alpha: 1), intensity: 5))
        let streets = Int(size / blockPitch)
        for i in 0..<count {
            let alongX = i % 2 == 0
            let k = rng.int(0, streets + 1)
            let dir: Float = rng.chance(0.5) ? 1 : -1
            let fixed = -half + Float(k) * blockPitch + dir * 4
            let node = SCNNode()
            let b = SCNNode(geometry: bodyGeos[i % bodyGeos.count])
            node.addChildNode(b)
            node.addChildNode(SCNNode(geometry: frontGeo))
            node.addChildNode(SCNNode(geometry: rearGeo))
            // Fahrtrichtung: Modell schaut nach +Z
            if alongX {
                node.simdEulerAngles = SIMD3<Float>(0, dir > 0 ? Float.pi / 2 : -Float.pi / 2, 0)
            } else {
                node.simdEulerAngles = SIMD3<Float>(0, dir > 0 ? 0 : Float.pi, 0)
            }
            root.addChildNode(node)
            cars.append(CityCar(node: node, alongX: alongX, fixed: fixed, dir: dir,
                                s: rng.float(-half, half), speed: rng.float(10, 19)))
        }
    }

    func update(dt: Float) {
        for i in cars.indices {
            var c = cars[i]
            c.s += c.dir * c.speed * dt
            if c.s > half + 40 { c.s = -half - 40 }
            if c.s < -half - 40 { c.s = half + 40 }
            c.node.simdPosition = c.alongX ? SIMD3<Float>(c.s, 0, c.fixed) : SIMD3<Float>(c.fixed, 0, c.s)
            cars[i] = c
        }
    }
}
