import SwiftUI
import AVFoundation

struct CameraPreviewView: UIViewRepresentable {
    let cameraManager: CameraManager

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.backgroundColor = .black
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {
        if let layer = cameraManager.previewLayer {
            uiView.setPreviewLayer(layer)
        }
    }
}

final class PreviewUIView: UIView {
    private var previewLayer: AVCaptureVideoPreviewLayer?

    func setPreviewLayer(_ layer: AVCaptureVideoPreviewLayer) {
        previewLayer?.removeFromSuperlayer()
        previewLayer = layer
        layer.frame = bounds
        self.layer.insertSublayer(layer, at: 0)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        previewLayer?.frame = bounds
    }
}
