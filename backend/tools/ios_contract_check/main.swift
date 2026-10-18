// Decodes live backend responses with the app's own Swift models
// (frontend/ios/CrewSafe/Models/Models.swift). Run against a local server:
//
//   tools/ios_contract_check/run.sh [base-url]
//
// Exits non-zero if any response the app reads fails to decode.

import Foundation

let base = URL(string: CommandLine.arguments.dropFirst().first ?? "http://localhost:8000/api/v1/")!
var failures = 0

@MainActor func check<T: Decodable>(_ path: String, as type: T.Type, describe: (T) -> String) async {
    do {
        let (data, response) = try await URLSession.shared.data(from: URL(string: path, relativeTo: base)!)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let value = try JSONCoding.decoder.decode(T.self, from: data)
        print("OK   \(status) \(path): \(describe(value))")
    } catch {
        failures += 1
        print("FAIL \(path): \(error)")
    }
}

await check("sites", as: [Site].self) { sites in
    let first = sites.first { $0.conditions != nil }
    return "\(sites.count) sites; first with conditions: \(first?.name ?? "-") rain \(first?.conditions?.rain24hIn ?? -1) in."
}
await check("sites/664", as: Site.self) { "\($0.name) top factor: \($0.topFactor?.detail ?? "-")" }
await check("alerts?site_ids=664,56518,627", as: [HazardAlert].self) { "\($0.count) alerts, newest: \($0.first?.title ?? "-")" }
await check("lightning/holds", as: [LightningHold].self) { holds in
    "\(holds.count) holds; longest remaining \(Int(holds.map { $0.remaining(at: .now) }.max() ?? 0)) s"
}
await check("sites/664/briefing", as: SiteBriefing.self) { "\($0.headline) (\($0.events.count) events)" }
await check("briefings/next-day", as: DailyBriefing.self) { "\($0.items.count) items; \($0.summary)" }
await check("reports", as: [CrewReport].self) { "\($0.count) reports" }

// Encode a report exactly as the app does and post it.
let report = HazardReport(id: UUID().uuidString, siteId: 664, type: .wildlife, notes: "Contract check",
                          latitude: 29.6461, longitude: -82.3208, createdAt: .now,
                          photoJpeg: Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00]))
var request = URLRequest(url: base.appending(path: "reports"))
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try JSONCoding.encoder.encode(report)
let (_, postResponse) = try await URLSession.shared.data(for: request)
let postStatus = (postResponse as? HTTPURLResponse)?.statusCode ?? 0
print(postStatus == 201 ? "OK   201 POST reports" : "FAIL POST reports: \(postStatus)")
if postStatus != 201 { failures += 1 }

// WebSocket: subscribe like the app and decode what arrives for 20 seconds.
var wsComponents = URLComponents(url: base.appending(path: "ws/updates"), resolvingAgainstBaseURL: false)!
wsComponents.scheme = base.scheme == "https" ? "wss" : "ws"
let socket = URLSession.shared.webSocketTask(with: wsComponents.url!)
socket.resume()
try await socket.send(.string(#"{"type":"subscribe","payload":{"site_ids":[664,56518,617],"include_severe_statewide":true}}"#))
let appEvents: Set = ["hazard_index_updated", "hazard_index_batch", "alert", "lightning_strike"]
var counts: [String: Int] = [:]
let deadline = Date.now.addingTimeInterval(20)
while Date.now < deadline {
    guard case .string(let text) = try await socket.receive() else { continue }
    let data = Data(text.utf8)
    let type = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["type"] as? String ?? "?"
    if (try? JSONCoding.decoder.decode(RealtimeEvent.self, from: data)) != nil {
        counts["\(type) (decoded)", default: 0] += 1
    } else if appEvents.contains(type) {
        failures += 1
        print("FAIL decoding \(text.prefix(300))")
    } else {
        counts["\(type) (not read by the app)", default: 0] += 1
    }
}
socket.cancel(with: .normalClosure, reason: nil)
for (kind, n) in counts.sorted(by: { $0.key < $1.key }) { print("WS   \(n) x \(kind)") }
print(failures == 0 ? "ALL DECODED" : "\(failures) FAILURES")
exit(failures == 0 ? 0 : 1)
