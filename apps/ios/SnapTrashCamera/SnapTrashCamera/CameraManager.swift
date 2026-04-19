import AVFoundation
import UIKit
import Combine

@MainActor
final class CameraManager: NSObject, ObservableObject {
    @Published var isAuthorized = false
    @Published var captureError: String?

    private let session = AVCaptureSession()
    private var photoOutput = AVCapturePhotoOutput()
    private var captureCompletion: ((UIImage?) -> Void)?

    var previewLayer: AVCaptureVideoPreviewLayer?

    override init() {
        super.init()
        Task { await checkAuthorization() }
    }

    func checkAuthorization() async {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            isAuthorized = true
            setupSession()
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            isAuthorized = granted
            if granted { setupSession() }
        default:
            isAuthorized = false
        }
    }

    private func setupSession() {
        session.beginConfiguration()
        session.sessionPreset = .photo

        guard
            let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
            let input = try? AVCaptureDeviceInput(device: device),
            session.canAddInput(input)
        else {
            captureError = "Camera unavailable"
            session.commitConfiguration()
            return
        }

        session.addInput(input)

        if session.canAddOutput(photoOutput) {
            session.addOutput(photoOutput)
        }

        session.commitConfiguration()

        previewLayer = AVCaptureVideoPreviewLayer(session: session)
        previewLayer?.videoGravity = .resizeAspectFill

        Task.detached { [weak self] in
            self?.session.startRunning()
        }
    }

    func capturePhoto(completion: @escaping (UIImage?) -> Void) {
        guard session.isRunning else {
            completion(nil)
            return
        }

        captureCompletion = completion

        var settings = AVCapturePhotoSettings()

        // Enable flash
        if photoOutput.supportedFlashModes.contains(.on) {
            settings.flashMode = .on
        }

        photoOutput.capturePhoto(with: settings, delegate: self)
    }

    func stopSession() {
        Task.detached { [weak self] in
            self?.session.stopRunning()
        }
    }
}

extension CameraManager: AVCapturePhotoCaptureDelegate {
    nonisolated func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        guard error == nil,
              let data = photo.fileDataRepresentation(),
              let image = UIImage(data: data)
        else {
            Task { @MainActor [weak self] in
                self?.captureCompletion?(nil)
                self?.captureCompletion = nil
            }
            return
        }

        Task { @MainActor [weak self] in
            self?.captureCompletion?(image)
            self?.captureCompletion = nil
        }
    }
}
