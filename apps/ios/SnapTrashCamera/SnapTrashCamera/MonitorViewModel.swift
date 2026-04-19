import SwiftUI
import Combine

@MainActor
final class MonitorViewModel: ObservableObject {
    @Published var isRunning = false
    @Published var countdown: Int = Int(Config.captureInterval)
    @Published var statusText = "Ready to monitor"
    @Published var logs: [LogEntry] = []
    @Published var captureCount = 0

    private var countdownTimer: Timer?
    private var captureTask: Task<Void, Never>?

    let cameraManager = CameraManager()

    // MARK: - Control

    func toggle() {
        isRunning ? stop() : start()
    }

    func start() {
        isRunning = true
        countdown = Int(Config.captureInterval)
        statusText = "Monitoring"
        addLog("Session started", status: .info)
        scheduleCountdown()
        // Capture immediately on start
        Task { await captureAndUpload() }
    }

    func stop() {
        isRunning = false
        countdownTimer?.invalidate()
        countdownTimer = nil
        captureTask?.cancel()
        captureTask = nil
        statusText = "Stopped"
        countdown = Int(Config.captureInterval)
        addLog("Session stopped", status: .info)
    }

    // MARK: - Timer

    private func scheduleCountdown() {
        countdownTimer?.invalidate()
        countdown = Int(Config.captureInterval)

        countdownTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.isRunning else { return }
                self.countdown -= 1
                if self.countdown <= 0 {
                    self.countdown = Int(Config.captureInterval)
                    await self.captureAndUpload()
                }
            }
        }
    }

    // MARK: - Capture + Upload

    private func captureAndUpload() async {
        statusText = "Capturing..."

        let image = await withCheckedContinuation { continuation in
            cameraManager.capturePhoto { img in
                continuation.resume(returning: img)
            }
        }

        guard let image else {
            addLog("Capture failed — no image", status: .failure)
            statusText = "Monitoring"
            return
        }

        statusText = "Uploading..."

        do {
            let scanID = try await UploadManager.shared.uploadImage(image)
            captureCount += 1
            addLog("Uploaded — scan \(String(scanID.prefix(8)))", status: .success)
            statusText = "Monitoring"
        } catch {
            let detail = (error as? UploadManager.UploadError)?.errorDescription ?? error.localizedDescription
            addLog("Upload failed — \(detail)", status: .failure)
            statusText = "Upload failed"
        }
    }

    // MARK: - Logs

    private func addLog(_ message: String, status: LogEntry.EntryStatus) {
        let entry = LogEntry(timestamp: Date(), message: message, status: status)
        logs.insert(entry, at: 0)
        if logs.count > 50 { logs = Array(logs.prefix(50)) }
    }
}
