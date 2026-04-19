import Foundation

struct LogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let message: String
    let status: EntryStatus

    enum EntryStatus {
        case success, failure, info
    }

    var formattedTime: String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: timestamp)
    }
}
