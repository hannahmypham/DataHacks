# SnapTrash Camera iOS

Prototype iOS app acting as a proxy for a waste bin IoT camera.

## Setup

1. Open `SnapTrashCamera.xcodeproj` in Xcode (create via File → New → Project, then replace files with these)
2. Set your development team in Signing & Capabilities
3. Update `Config.swift` with your ingestion server URL (use `http://your-mac.local:8000` when running on physical device)
4. Run on a physical device (camera required)

## Config

Edit `Config.swift`:
- `captureInterval` — seconds between captures (default 20)
- `ingestionBaseURL` — your backend URL
- `restaurantID`, `zip`, `neighborhood` — demo metadata sent with each scan

## Architecture

**Smart Pipeline (Phone → S3 → Lambda Detector → Grok)**

- Phone uploads directly to `snaptrash-raw-incoming` S3 bucket using presigned URLs
- S3 event triggers `lambda-detector` (Rekognition similarity check)
- Only meaningfully different images trigger full Grok analysis
- This avoids redundant analysis and saves costs

## File Structure

```
SnapTrashCamera/
├── SnapTrashCameraApp.swift     # App entry point
├── Config.swift                 # All configurable constants
├── CameraManager.swift          # Real camera + flash + 20s timer
├── UploadManager.swift          # Presigned URL → S3 upload
├── ContentView.swift            # Main UI
└── (supporting views and models)
```

## Backend Requirements

Make sure these are deployed:
- `/scan/presign-upload` endpoint (returns presigned S3 URL)
- Lambda detector triggered by S3 `snaptrash-raw-incoming` bucket
- DynamoDB table `snaptrash-last-analyzed`
```

This completes the full integration of the phone-to-Lambda pipeline.