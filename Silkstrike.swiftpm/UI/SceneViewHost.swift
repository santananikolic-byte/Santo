import SwiftUI
import SceneKit
import UIKit
import simd

// =====================================================================
//  SILKSTRIKE – SceneViewHost
//  SwiftUI-Hülle um eine SCNView. Tauscht Szene + Kamera, sobald sich
//  der aktive Controller ändert. Ziehen in der rechten Bildschirmhälfte
//  (nur dort, wo keine SwiftUI-Bedienelemente liegen) → input.addLook.
// =====================================================================

struct SceneViewHost: UIViewRepresentable {
    var controller: GameSceneController?
    var input: InputState
    var quality: QualityPreset
    var isPlaying: Bool
    var lookEnabled: Bool

    init(_ controller: GameSceneController?,
         input: InputState,
         quality: QualityPreset,
         isPlaying: Bool = true,
         lookEnabled: Bool = true) {
        self.controller = controller
        self.input = input
        self.quality = quality
        self.isPlaying = isPlaying
        self.lookEnabled = lookEnabled
    }

    // MARK: Coordinator

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var input: InputState
        /// Schwach gehalten: wird der alte Controller freigegeben, gilt der nächste sicher als „neu“
        /// (ObjectIdentifier allein könnte bei wiederverwendeter Speicheradresse täuschen).
        weak var attachedController: AnyObject?
        var attachedID: ObjectIdentifier?
        var appliedQuality: QualityPreset?
        var lookEnabled: Bool = true

        init(input: InputState) {
            self.input = input
            super.init()
        }

        @objc func handlePan(_ recognizer: UIPanGestureRecognizer) {
            guard let v = recognizer.view else { return }
            switch recognizer.state {
            case .began, .changed:
                let t = recognizer.translation(in: v)
                recognizer.setTranslation(CGPoint.zero, in: v)
                if lookEnabled && (t.x != 0 || t.y != 0) {
                    input.addLook(SIMD2<Float>(Float(t.x), Float(t.y)))
                }
            default:
                break
            }
        }

        func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
            guard lookEnabled, let v = gestureRecognizer.view else { return false }
            let p = gestureRecognizer.location(in: v)
            return p.x >= v.bounds.width * 0.45
        }

        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            return true
        }
    }

    func makeCoordinator() -> Coordinator {
        return Coordinator(input: input)
    }

    // MARK: UIViewRepresentable

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView(frame: CGRect(x: 0, y: 0, width: 100, height: 100), options: nil)
        Render.configure(view: view, quality: quality)
        view.rendersContinuously = true
        view.isPlaying = true
        view.allowsCameraControl = false
        view.isMultipleTouchEnabled = true
        view.backgroundColor = UIColor.black

        let coordinator = context.coordinator
        coordinator.appliedQuality = quality
        coordinator.lookEnabled = lookEnabled

        let pan = UIPanGestureRecognizer(target: coordinator, action: #selector(Coordinator.handlePan(_:)))
        pan.cancelsTouchesInView = false
        pan.delaysTouchesBegan = false
        pan.delaysTouchesEnded = false
        pan.maximumNumberOfTouches = 1
        pan.delegate = coordinator
        view.addGestureRecognizer(pan)

        SceneViewHost.attach(controller, to: view, coordinator: coordinator)
        view.isPlaying = isPlaying
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        let coordinator = context.coordinator
        coordinator.input = input
        coordinator.lookEnabled = lookEnabled

        if coordinator.appliedQuality != quality {
            coordinator.appliedQuality = quality
            Render.configure(view: view, quality: quality)
            view.rendersContinuously = true
        }

        SceneViewHost.attach(controller, to: view, coordinator: coordinator)

        if view.isPlaying != isPlaying {
            view.isPlaying = isPlaying
        }
    }

    static func dismantleUIView(_ uiView: SCNView, coordinator: Coordinator) {
        uiView.isPlaying = false
        coordinator.attachedController = nil
        coordinator.attachedID = nil
    }

    /// Setzt Szene + Kamera nur, wenn sich die Controller-Identität geändert hat.
    private static func attach(_ controller: GameSceneController?, to view: SCNView, coordinator: Coordinator) {
        let incoming: AnyObject? = controller.map { $0 as AnyObject }
        let current: AnyObject? = coordinator.attachedController
        if incoming === current { return }

        guard let c = controller else {
            coordinator.attachedController = nil
            coordinator.attachedID = nil
            view.scene = nil
            return
        }
        coordinator.attachedController = c as AnyObject
        coordinator.attachedID = ObjectIdentifier(c as AnyObject)
        view.scene = c.scene
        view.pointOfView = c.cameraNode
        view.isPlaying = true
        c.didAttach(to: view)
    }
}
