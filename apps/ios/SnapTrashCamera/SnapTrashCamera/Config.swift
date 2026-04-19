import Foundation

enum Config {
    static let captureInterval: TimeInterval = 20

    // S3 bucket (backend handles upload, this is display only)
    static let s3Bucket = "snaptrash-bins"

    // Your Mac's local IP — iPhone must be on same WiFi network
    // Run `ipconfig getifaddr en0` in Terminal to get this
    static let ingestionBaseURL = "http://kriss-macbook-air.local:8000"

    // Demo metadata sent with every scan
    static let restaurantID = "demo-restaurant-001"
    static let zip = "94102"
    static let neighborhood = "SoMa"
}
