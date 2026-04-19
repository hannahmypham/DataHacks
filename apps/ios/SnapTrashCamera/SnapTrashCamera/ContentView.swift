import SwiftUI

struct ContentView: View {
    @StateObject private var vm = MonitorViewModel()

    var body: some View {
        ZStack {
            // Background
            Color(hex: "#0A0A0A").ignoresSafeArea()
            GridBackground().ignoresSafeArea()

            VStack(spacing: 0) {
                headerBar
                Divider().background(.white.opacity(0.06))

                cameraSection
                    .frame(maxHeight: 220)

                Divider().background(.white.opacity(0.06))

                controlSection

                Divider().background(.white.opacity(0.06))

                logSection

                Divider().background(.white.opacity(0.06))
                footerBar
            }
        }
    }

    // MARK: — Header

    private var headerBar: some View {
        HStack(spacing: 10) {
            Image(systemName: "trash.circle.fill")
                .font(.title2)
                .foregroundStyle(Color(hex: "#22C55E"))

            Text("SnapTrash Camera")
                .font(.system(.headline, design: .monospaced))
                .foregroundStyle(.white)

            Spacer()

            statusPill
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    private var statusPill: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(vm.isRunning ? Color(hex: "#22C55E") : .red)
                .frame(width: 7, height: 7)
                .overlay {
                    if vm.isRunning {
                        Circle()
                            .fill(Color(hex: "#22C55E").opacity(0.4))
                            .frame(width: 12, height: 12)
                            .animation(.easeInOut(duration: 1).repeatForever(autoreverses: true), value: vm.isRunning)
                    }
                }
            Text(vm.isRunning ? "LIVE" : "IDLE")
                .font(.system(.caption2, design: .monospaced))
                .fontWeight(.semibold)
                .foregroundStyle(vm.isRunning ? Color(hex: "#22C55E") : .red)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(.white.opacity(0.05))
        .clipShape(Capsule())
        .overlay(Capsule().strokeBorder(.white.opacity(0.08)))
    }

    // MARK: — Camera

    private var cameraSection: some View {
        ZStack {
            Color.black

            if vm.cameraManager.isAuthorized {
                CameraPreviewView(cameraManager: vm.cameraManager)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "camera.slash")
                        .font(.system(size: 32))
                        .foregroundStyle(.white.opacity(0.2))
                    Text("Camera access required")
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.3))
                }
            }

            // Corner brackets overlay
            CameraBracketOverlay()
        }
        .frame(maxWidth: .infinity, maxHeight: 220)
    }

    // MARK: — Control

    private var controlSection: some View {
        VStack(spacing: 20) {
            // Main button
            Button(action: vm.toggle) {
                HStack(spacing: 12) {
                    Image(systemName: vm.isRunning ? "stop.fill" : "play.fill")
                        .font(.system(size: 18, weight: .semibold))
                    Text(vm.isRunning ? "STOP MONITORING" : "START MONITORING")
                        .font(.system(.callout, design: .monospaced, weight: .semibold))
                        .tracking(1)
                }
                .foregroundStyle(vm.isRunning ? .black : .black)
                .padding(.horizontal, 32)
                .padding(.vertical, 16)
                .background(buttonColor)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .shadow(color: buttonColor.opacity(0.4), radius: 12, y: 4)
            }
            .buttonStyle(.plain)
            .padding(.top, 24)

            // Status + countdown
            VStack(spacing: 4) {
                Text(vm.statusText)
                    .font(.system(.subheadline, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.6))

                if vm.isRunning {
                    HStack(spacing: 4) {
                        Image(systemName: "timer")
                            .font(.caption2)
                        Text("Next capture in \(vm.countdown)s")
                            .font(.system(.caption, design: .monospaced))
                    }
                    .foregroundStyle(Color(hex: "#22C55E").opacity(0.9))
                }
            }
            .frame(height: 44)
            .padding(.bottom, 16)
        }
    }

    private var buttonColor: Color {
        vm.isRunning ? .red : Color(hex: "#22C55E")
    }

    // MARK: — Log

    private var logSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("ACTIVITY LOG")
                    .font(.system(.caption2, design: .monospaced))
                    .fontWeight(.semibold)
                    .foregroundStyle(.white.opacity(0.3))
                    .tracking(1.5)

                Spacer()

                if vm.captureCount > 0 {
                    Text("\(vm.captureCount) captures")
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(Color(hex: "#22C55E").opacity(0.7))
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 10)

            if vm.logs.isEmpty {
                Text("No activity yet — press START to begin")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.2))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 24)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(vm.logs) { entry in
                            LogRowView(entry: entry)
                                .padding(.horizontal, 20)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    // MARK: — Footer

    private var footerBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "internaldrive")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.25))
            Text("s3://\(Config.s3Bucket)")
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.white.opacity(0.25))
            Spacer()
            Text(Config.ingestionBaseURL)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.white.opacity(0.2))
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
    }
}

// MARK: — Camera bracket overlay

private struct CameraBracketOverlay: View {
    var body: some View {
        ZStack {
            // top-left
            BracketCorner().position(x: 24, y: 24)
            // top-right
            BracketCorner().rotationEffect(.degrees(90)).position(x: UIScreen.main.bounds.width - 24, y: 24)
            // bottom-left
            BracketCorner().rotationEffect(.degrees(270)).position(x: 24, y: 196)
            // bottom-right
            BracketCorner().rotationEffect(.degrees(180)).position(x: UIScreen.main.bounds.width - 24, y: 196)
        }
    }
}

private struct BracketCorner: View {
    var body: some View {
        Path { p in
            p.move(to: CGPoint(x: 0, y: 16))
            p.addLine(to: CGPoint(x: 0, y: 0))
            p.addLine(to: CGPoint(x: 16, y: 0))
        }
        .stroke(Color(hex: "#22C55E").opacity(0.5), lineWidth: 1.5)
        .frame(width: 16, height: 16)
    }
}

// MARK: — Grid background

private struct GridBackground: View {
    var body: some View {
        Canvas { ctx, size in
            let spacing: CGFloat = 40
            ctx.opacity = 0.03
            var path = Path()
            var x: CGFloat = 0
            while x <= size.width {
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
                x += spacing
            }
            var y: CGFloat = 0
            while y <= size.height {
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
                y += spacing
            }
            ctx.stroke(path, with: .color(.white), lineWidth: 0.5)
        }
    }
}

// MARK: — Color hex helper

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255
        let g = Double((int >> 8) & 0xFF) / 255
        let b = Double(int & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}
