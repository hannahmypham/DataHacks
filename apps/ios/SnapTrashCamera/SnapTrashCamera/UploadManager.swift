import UIKit
import Foundation

/// Handles uploading captured images to S3 raw bucket.
/// Uses presigned URLs so the Lambda detector can be triggered.
actor UploadManager {
    static let shared = UploadManager()
    private init() {}

    // MARK: - Public

    func uploadImage(_ image: UIImage) async throws -> String {
        return try await uploadToS3RawBucket(image)
    }

    // MARK: - Real S3 Upload (for Lambda detector pipeline)

    /// Two-step process: get presigned URL → upload directly to S3 raw bucket
    private func uploadToS3RawBucket(_ image: UIImage) async throws -> String {
        guard let imageData = image.jpegData(compressionQuality: 0.85) else {
            throw UploadError.encodingFailed
        }

        // Step 1: Get presigned upload URL from backend
        let presignURL = try await getPresignedUploadURL()

        // Step 2: Upload directly to S3 using presigned URL
        let success = try await uploadWithPresignedURL(imageData, url: presignURL)

        if success {
            return "upload-successful"
        } else {
            throw UploadError.uploadFailed
        }
    }

    private func getPresignedUploadURL() async throws -> URL {
        guard let url = URL(string: "\(Config.ingestionBaseURL)/scan/presign-upload") else {
            throw UploadError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = "restaurant_id=\(Config.restaurantID)&content_type=image/jpeg"
        request.httpBody = body.data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw UploadError.noResponse
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let uploadURLString = json["upload_url"] as? String,
              let uploadURL = URL(string: uploadURLString) else {
            throw UploadError.invalidResponse
        }

        return uploadURL
    }

    private func uploadWithPresignedURL(_ data: Data, url: URL) async throws -> Bool {
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")
        request.httpBody = data

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }
        guard let url = URL(string: "\(Config.ingestionBaseURL)/scan") else {
            throw UploadError.invalidURL
        }
        guard let imageData = image.jpegData(compressionQuality: 0.85) else {
            throw UploadError.encodingFailed
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        var body = Data()
        body.append(multipartFile("image", filename: "capture.jpg", mimeType: "image/jpeg", data: imageData, boundary: boundary))
        body.append(multipartField("restaurant_id", value: Config.restaurantID, boundary: boundary))
        body.append(multipartField("zip", value: Config.zip, boundary: boundary))
        body.append(multipartField("neighborhood", value: Config.neighborhood, boundary: boundary))
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse else { throw UploadError.noResponse }
        guard http.statusCode == 200 else {
            throw UploadError.serverError(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }

        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let scanID = json["scan_id"] as? String {
            return scanID
        }
        return UUID().uuidString
    }

    // MARK: - Errors

    enum UploadError: LocalizedError {
        case invalidURL
        case encodingFailed
        case noResponse
        case invalidResponse
        case uploadFailed

        var errorDescription: String? {
            switch self {
            case .invalidURL:       return "Invalid server URL"
            case .encodingFailed:   return "Image encoding failed"
            case .noResponse:       return "No response from server"
            case .invalidResponse:  return "Invalid response from presign endpoint"
            case .uploadFailed:     return "S3 upload failed"
            }
        }
    }
}

private extension String {
    var utf8Data: Data { Data(utf8) }
}
