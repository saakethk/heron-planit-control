# Frontend Development Plan

This plan covers how to take the CrewSafe scaffold (`frontend/ios`) from dummy data to a working app once the hazard model and data pipeline are finalized. It also records the framework decision and the tools needed.

## 1. Framework decision: native Swift + SwiftUI, built in Xcode

**We will build the app natively with Swift and SwiftUI in Xcode**, rather than a cross-platform framework.

| | Native SwiftUI | React Native (Expo) | Flutter |
|---|---|---|---|
| Live Activity / Dynamic Island lightning countdown | Yes, first-class (ActivityKit + WidgetKit) | Needs a native Swift extension anyway | Needs a native Swift extension anyway |
| Time-sensitive and critical alerts, notification actions | Direct `UserNotifications` API | Through plugins | Through plugins |
| Background refresh (`BGTaskScheduler`) | Direct | Limited (`expo-background-fetch`) | Through plugins |
| MapKit, camera, location | Direct | Good libraries | Good libraries |
| Android support | No | Yes | Yes |
| Need Xcode anyway? | Yes | Yes (signing, simulator, native modules) | Yes |

Why native:

1. **The most important feature is an iOS-system feature.** The lightning stop-work alert, with a 30-minute all-clear countdown that resets on each strike, fits a **Live Activity** on the Lock Screen and Dynamic Island. Crews would see the countdown without unlocking their phones. Live Activities can only be written in Swift (WidgetKit extension), even in React Native or Flutter apps.
2. **Notifications are the product.** Time-sensitive interruption levels, critical alerts (which bypass silent mode), actionable notifications ("Acknowledge"), and `BGTaskScheduler` are all straightforward in Swift and awkward through bridges.
3. **Xcode is required either way.** Every iOS framework needs Xcode for code signing, the Simulator, and App Store or TestFlight builds. Native removes a layer instead of adding one.
4. **The scope is iOS only** (per the project README). If Android becomes a requirement later, the backend contract in section 4 is platform-neutral, so an Expo client could be added without backend changes.

Tradeoff: no Android build, and only one teammate writes Swift. For a hackathon-scale app with one frontend developer, this is acceptable.

## 2. Tools

### Required

| Tool | Purpose | Notes |
|---|---|---|
| **Xcode 26** | IDE, iOS 26 SDK, Simulator, Instruments, SwiftUI previews | Mac App Store. Not installed on this machine yet; only the Command Line Tools are. After installing, run `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`. |
| **Swift 6 / SwiftUI** | Language and UI framework | Ships with Xcode. The project currently compiles in Swift 5 language mode to avoid strict-concurrency friction during the hackathon. |
| **XcodeGen** (`brew install xcodegen`) | Generates `CrewSafe.xcodeproj` from `project.yml` | Avoids merge conflicts in `.pbxproj`. Capabilities and Info.plist keys live in `project.yml`. |
| **Apple ID** (free) | Simulator, local notifications, running on your own iPhone | Free provisioning profiles expire after 7 days. |
| **Figma** | Mockups before building screens | Use Apple's official "iOS 26 UI Kit" community file. |

### Required for real push notifications

| Tool | Purpose |
|---|---|
| **Apple Developer Program** ($99/yr) | Needed for the Push Notifications capability (APNs), TestFlight, the Time Sensitive Notifications capability, and requesting the Critical Alerts entitlement. Check whether UF or the sponsor (Sperry Tech) can supply a team. |
| **APNs auth key (`.p8`)** | Created in the developer portal. The backend uses it to sign push requests. |
| **Backend push library** | For a Python backend: `aioapns` or `httpx` with HTTP/2. Alternative: Firebase Cloud Messaging, which also helps if Android is ever added. |

### Helpful

- **SF Symbols app**: browse the icons used across the UI.
- **`xcrun simctl push`**: send fake APNs payloads to the Simulator without a developer account. Samples are in `ios/push-samples/`.
- **Proxyman** or **Charles**: inspect app-to-backend traffic.
- **Bruno** or **Postman**: exercise backend endpoints while building against them.
- **Swift Testing / XCTest** (built into Xcode): unit and UI tests.

## 3. What the scaffold already does

These features were on the "test if possible" list; each one is implemented here with dummy data:

| Feature | Where | Status |
|---|---|---|
| Sending notifications | `Services/NotificationManager.swift` | Local notifications with categories, an Acknowledge action, time-sensitive level, and tap routing. The APNs token is registered in `CrewSafeApp.swift`. |
| Real-time updates | `Services/RealtimeService.swift`, `AppStore.handle(_:)` | Mock feed plus a WebSocket client with reconnect and backoff. Updates animate the gauge, map pins, and ranked list. |
| Lightning stop-work and 30-minute all-clear | `AppStore.handleLightning(_:)`, `LightningHoldBanner` | Any strike within 10 mi starts or extends the hold. The all-clear notification is rescheduled on every strike. |
| 6 PM daily briefing | `NotificationManager.scheduleDailyBriefing` | Repeating local notification at 18:00. Background refresh updates its text. |
| Background tasks | `Services/BackgroundRefresh.swift`, `.backgroundTask(.appRefresh)` | Registered and scheduled when the app goes to the background. |
| Map of sites | `Views/SitesView.swift` | All 346 EIA-860M Florida plants. "Nearby" shows the 25 closest to the chosen location as pins and in a list, with farther sites in collapsible distance groups and a "Severe elsewhere" card. "Statewide" ranks every site. Sites outside the main group are small dots, culled to the visible map. |
| Location-first setup | `Views/LocationPickerView.swift`, `AppStore.setLocation(_:)` | First launch asks for a location (default Gainesville, FL; GPS; Apple place search; city presets). The nearest site becomes the home site. Distances use great-circle miles. |
| Taking pictures | `Views/ReportHazardView.swift`, `CameraPicker.swift` | Camera on a device, photo library in the Simulator, with GPS tagging and nearest-site detection. |

Architecture: views read a single `@Observable` `AppStore` from the environment. The store talks only to two protocols, `HazardAPI` (REST) and `RealtimeService` (stream). Each has a mock and a live implementation, so switching to the real backend is the launch argument `-useLiveBackend YES` (plus `-apiBaseURL` on a phone). The backend scaffold in `backend/` already serves the contract below with dummy data; `backend/README.md` explains it.

## 4. Proposed backend contract (agree on this with the backend first)

JSON uses `snake_case` and ISO-8601 dates. The Swift models in `Models/Models.swift` already decode this shape, so the backend can return these fields and it will work as-is.

### REST (`/api/v1`)

| Method | Path | Returns | Backed by |
|---|---|---|---|
| GET | `/sites` | `[Site]` summaries for all ~346 plants: id, name, county, lat/lon, `capacity_mw`, `hazard_index`, `factors[]`, `updated_at`. About 100 KB; support `ETag`/`If-None-Match`. | Hazard model output per EIA plant |
| GET | `/sites/{id}` | One `Site` with `conditions` and today's `history[]` | Weather feeds plus model history |
| GET | `/sites/nearby?lat=&lon=&limit=25&offset=` | Optional. `[Site]` nearest first, with `distance_miles`. The app sorts locally today, so this is only needed if the site count grows a lot. | PostGIS or a haversine query |
| GET | `/sites/{id}/briefing` | `SiteBriefing`: headline, sources, timeline `events[]`, `tomorrow_outlook` | Alert rules plus the forecast |
| GET | `/lightning/holds` | `[LightningHold]` currently active, statewide | Lightning engine (server-side 30-minute timer) |
| GET | `/alerts?since=&site_ids=617,664,…` | `[HazardAlert]` for the followed sites, with per-user `acknowledged` | Alert engine |
| POST | `/alerts/{id}/ack` | `204` | Read state |
| GET | `/briefings/next-day?site_id=` | `DailyBriefing` | 6 PM job |
| GET | `/reports` | `[CrewReport]` | Crew reports |
| POST | `/reports` | `201`. Send photos as multipart or via a pre-signed upload URL, not base64 in JSON. | Crew reports. Also a new wildlife and hazard data source for the model. |
| POST | `/devices` | `201` | `{apns_token, platform}` |
| PUT | `/me/subscription` | `204` | `{location: {name, latitude, longitude}, home_site_id, site_ids}`: the 25 nearest sites plus the home site. Targets pushes and filters alerts. Sent on launch and whenever the location or home site changes (`AppStore.syncSubscription`). |

`conditions` is `{temperature_f, heat_index_f, wind_mph, rain24h_in, soil_moisture_pct, nearest_strike_miles}` (`rain24h_in`, not `rain_24h_in`: Swift's `convertFromSnakeCase` turns the latter into `rain24HIn`), and `history` is today's `[{time, value}]` index readings. Both are optional; the UI hides those sections when they are missing. Today `/sites` may still include them; at 300+ sites, move them to `/sites/{id}`.

The plant list the app uses for mock data is exported from the EIA workbook by `ios/scripts/export_sites.py`, so IDs match what the model scores.

Example `Site`:

```json
{
  "id": 617, "name": "Port Everglades", "county": "Broward",
  "latitude": 26.0856, "longitude": -80.1253, "capacity_mw": 1352.0,
  "hazard_index": 7.8,
  "factors": [{"type": "lightning", "score": 8.9, "detail": "Storm cell 6 mi NE"}],
  "updated_at": "2026-10-17T15:04:00Z"
}
```

### Realtime (`wss://…/api/v1/ws/updates`)

Every message is `{"type": ..., "seq": <int>, "payload": ...}`. `seq` increases per connection stream so a reconnect can resume.

App to server, sent right after connecting and again on every reconnect (`WebSocketRealtimeService`):

- `subscribe`: `{site_ids: [...], include_severe_statewide: true, last_seq: <int or null>}`. The server replays missed messages after `last_seq`, or sends `resync_required`.

Server to app:

- `hazard_index_updated`: `{site_id, hazard_index, factors?}` for one followed site.
- `hazard_index_batch`: `{updates: [{site_id, hazard_index, factors?}, ...]}`. One message per model run, with only scores that changed by at least 0.1. The app applies a batch as a single UI update.
- `alert`: a `HazardAlert` for a followed site.
- `lightning_strike`: `{site_id, distance_miles, occurred_at, direction}`. `direction` is the compass direction from the site, such as `"NE"`. Send strikes for followed sites, plus any strike that starts a stop-work hold elsewhere when `include_severe_statewide` is set.
- Planned: `lightning_hold_updated` / `lightning_hold_cleared` (server-owned countdown), `conditions_updated`, `briefing_updated`, `report_created`, `resync_required`.

Filtering happens on the server: each connection only gets its subscribed sites plus statewide stop-work and severe events. Statewide events update the map and the "Severe elsewhere" card; only followed sites produce alerts and notifications.

The WebSocket only runs while the app is open. **Anything safety-critical must also be sent as an APNs push**, because iOS suspends apps in the background.

### Push payloads

Use the same `category` values (`HAZARD_ALERT`, `LIGHTNING_HOLD`, `DAILY_BRIEFING`) and custom keys (`alert_id`, `site_id`) as the local notifications, so the existing delegate code handles them. See `ios/push-samples/`.

## 5. Development phases (after the model and pipeline are finalized)

### Phase 0: Now, in parallel with backend work
- [x] Scaffold with dummy data, notifications, realtime, map, camera, background tasks
- [ ] Figma mockup of the four tabs plus Live Activity. Research similar apps: Weatherbug Spark lightning alerts, Zello, SafetyCulture, the Field Operations dashboard in ArcGIS.
- [ ] Agree on the section 4 contract with the backend. Backend publishes sample JSON fixtures; frontend adds decode tests against them.

### Phase 1: Connect live data (about half a day)
1. Implement or confirm the backend endpoints (the `backend/` scaffold already serves them on dummy data), then launch with `-useLiveBackend YES` and the real URL (use an `.xcconfig` per environment for release builds).
2. Handle loading, empty, error, and stale-data states. Show "Updated x min ago" and grey out data older than the pipeline's refresh interval.
3. Cache the last good response (Codable file cache or SwiftData) so crews in low-signal areas still see the most recent index.
4. Unit-test the `RealtimeEvent` decoding and the lightning-hold rules (`LightningPolicy`).

### Phase 2: Real push notifications (about 1 day; needs the paid developer account)
1. Add the **Push Notifications** and **Time Sensitive Notifications** capabilities in `project.yml` (`entitlements:`), then set `DEVELOPMENT_TEAM`.
2. Send the APNs token to `POST /devices` along with the user's assigned sites. This is already wired through `AppStore.registerDevice`.
3. Backend sends pushes for lightning strikes within 10 mi, flood and other warnings, and the 6 PM briefing.
4. Make the lightning all-clear authoritative on the server: the backend sends the all-clear push. Keep the local all-clear as a fallback.
5. Optional: apply for the **Critical Alerts** entitlement, so stop-work alerts sound even in silent mode. Apple reviews these requests; a worker-safety use case is a strong fit.

### Phase 3: Lightning Live Activity (about 1 day; the standout demo feature)
1. Add a Widget Extension target in `project.yml` with an `ActivityAttributes` model (site, strike count, closest distance, `endsAt`).
2. Start the activity on the first strike, and update `endsAt` on each new strike. Show the countdown with `Text(timerInterval:)` on the Lock Screen and Dynamic Island.
3. Use **push-to-update** tokens so the backend can extend or end the activity while the app is suspended.

### Phase 4: Hazard Index explainability (strengthens the AI/ML track)
1. Have the model return per-factor contributions (for example SHAP values) in `factors[]`. The UI already renders factor bars, so this needs no new screens.
2. Add a "Why is this 7.8?" sheet with factor contributions, the model version, and the confidence or uncertainty band.
3. Add a 24-hour sparkline of the index per site using Swift Charts, backed by `GET /sites/{id}` history.
4. Replace the placeholder `RiskLevel` thresholds with the model's calibrated bands.

### Phase 5: Crew hazard reporting, production version
1. Upload photos with a presigned S3/GCS URL or multipart instead of base64 JSON, compressed to about 1600 px.
2. Keep an offline queue: save reports locally and retry when the device is back online.
3. Feed reports back into the pipeline as wildlife and hazard observations, which is one of the data sources listed in `model/data/README.md`.

### Phase 6: Supervisor dashboard and roles
1. Add simple roles (crew or supervisor) and site assignments.
2. Supervisor view: filter by county, risk, or hazard type; cluster pins once all ~343 Florida plants are loaded; show active holds and open reports per site.
3. Optional: an iPad layout using `NavigationSplitView`, which SwiftUI supports with little extra work.

### Phase 7: Polish, test, ship
- Accessibility (Dynamic Type, VoiceOver labels; several are already in place) and Dark Mode check.
- UI tests for the main flows. Use Instruments to check battery use of the WebSocket and location.
- Distribute through **TestFlight** for judges and testers. Record a demo with `simctl push` lightning bursts.

### Hackathon priority if time is short
Do Phase 1, then Phase 2 using simulated pushes, then Phase 4 items 1 and 2, then Phase 3. Explainability scores directly on the AI track. The Live Activity is the most memorable demo.

## 6. Risks and open questions

- **Paid Apple Developer account**: without it there are no real pushes on devices and no TestFlight. Simulated pushes cover the demo.
- **Backend realtime transport**: WebSocket is assumed. Server-Sent Events would also work with a small change to `WebSocketRealtimeService`.
- **Lightning data source and latency**: the 10-mile radius and 30-minute rule only help if strikes arrive within seconds. Confirm which feed the backend uses (for example Xweather or WeatherAPI alerts) and its delay.
- **Time zones**: the 6 PM briefing should use the site's local time. All Florida sites are Eastern, apart from the western Panhandle.
- **Site assignment**: decide whether a crew picks its site (as the scaffold does now) or the backend assigns one.
