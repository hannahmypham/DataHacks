import SwiftUI

struct LogRowView: View {
    let entry: LogEntry

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
                .padding(.top, 5)

            Text(entry.message)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.white.opacity(0.75))
                .lineLimit(nil)

            Spacer(minLength: 0)

            Text(entry.formattedTime)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.white.opacity(0.35))
        }
        .padding(.vertical, 3)
    }

    private var dotColor: Color {
        switch entry.status {
        case .success: return Color(hex: "#22C55E")
        case .failure: return .red
        case .info:    return .white.opacity(0.4)
        }
    }
}
