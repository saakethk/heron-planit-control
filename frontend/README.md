# Frontend
Contains the main code for the frontend of swamphacks.

The iOS app, **CrewSafe**, lives in [`ios/`](ios). It is native Swift and SwiftUI, targets iOS 17+, and is built with Xcode. The development roadmap and tooling decisions are in [`PLAN.md`](PLAN.md).

## Running the scaffold

1. Install **Xcode 26** from the Mac App Store, then point the command line tools at it:
   ```bash
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   ```
2. Install [XcodeGen](https://github.com/yonaskolb/XcodeGen) and generate the project:
   ```bash
   brew install xcodegen
   cd frontend/ios
   xcodegen generate
   open CrewSafe.xcodeproj
   ```
   The `.xcodeproj` is generated from `project.yml` and is git-ignored. Re-run `xcodegen generate` after adding or removing files.
3. Pick an iPhone simulator and press **Run** (⌘R). Allow notifications when prompted.

To use the backend in `backend/` instead of built-in data, start it (see `backend/README.md`; default is live Open-Meteo / NWS / GLM) and add the launch argument `-useLiveBackend YES`. On a phone, also add `-apiBaseURL http://<your-mac-name>.local:8000/api/v1/`. Settings → Backend should show **Live API** and the API URL. **Simulate** sends lightning, heat, and flood through the live pipeline so the index, alerts, and notifications update. Site detail shows the FEMA flood zone when the backend sends one.

Without that argument, the app runs entirely on built-in dummy data, matching the design in `design/crewsafe-mockup-preview.png`:
- On first launch it asks for a location, defaulting to Gainesville, FL. The home site becomes the nearest plant (John R Kelly, 0.4 mi), which starts with an active lightning hold.
- All 346 Florida plants from EIA-860M (`CrewSafe/Resources/florida_sites.json`, exported by `ios/scripts/export_sites.py`) are on the Sites tab. Nine have handcrafted stories; the rest get stable generated scores, conditions, and history.
- The Sites tab shows the 25 nearest sites, farther sites in collapsible distance groups, a "Severe elsewhere" card, and a Statewide ranking.
- Alerts, crew reports, and a next-day briefing.

A simulated live feed sends an event every 6 to 12 seconds, mostly for the 25 followed sites: index changes, statewide model-run batches, new alerts, and lightning strikes.

## Trying notifications and realtime updates

- **Settings (gear icon on the Today tab)**:
  - **Simulate**:
    - **Lightning strike**: starts or extends the stop-work hold, posts a notification, and updates the briefing.
    - **Flood warning**.
    - **Heat spike**: pushes the index into the severe band, which triggers an alert.
    - **6 PM briefing in 5 seconds**: go to the Home Screen (⇧⌘H) to see it arrive in the background.
    - **End lightning holds**: posts the all-clear.
  - **Demo mode**:
    - **Live simulated feed**: turn it off for a scripted demo with no surprise events.
    - **Fast all-clear**: shortens the 30-minute countdown to 60 seconds.
    - **Reset demo data**.
- **Debug launch arguments** (Xcode: Product > Scheme > Edit Scheme > Arguments): `-initialTab sites|alerts|report`, `-showSite 617`, `-skipNotificationPrompt YES`, `-chooseLocation YES|NO` (show or skip the first-launch location screen), `-location Miami` (any city from the location picker), `-useLiveBackend YES` (use the backend), `-apiBaseURL <url>`.
- **Simulated remote pushes** (no Apple Developer account needed):
  ```bash
  xcrun simctl push booted com.swamphacks.crewsafe ios/push-samples/lightning.apns
  ```
  You can also drag an `.apns` file onto the Simulator window.

## Layout

```
ios/
├── project.yml                 # XcodeGen spec (targets, Info.plist keys, capabilities)
├── push-samples/               # APNs payloads for `simctl push`
└── CrewSafe/
    ├── CrewSafeApp.swift       # App entry, AppDelegate (notification delegate, APNs token)
    ├── AppStore.swift          # Observable app state, realtime handling, lightning hold logic
    ├── Models/                 # Site, HazardAlert, LightningHold, DailyBriefing, RealtimeEvent, mock data
    ├── Services/               # HazardAPI (mock + live REST), RealtimeService (mock + WebSocket),
    │                           # NotificationManager, LocationManager, BackgroundRefresh
    └── Views/                  # Today, Sites (map + ranked list), Site detail, Alerts, Report, Settings
```
