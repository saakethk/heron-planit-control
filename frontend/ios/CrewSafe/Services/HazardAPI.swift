import Foundation

/// REST surface the app expects from the backend. See `frontend/PLAN.md` for the
/// proposed endpoint contract.
protocol HazardAPI: Sendable {
    func fetchSites() async throws -> [Site]
    /// `siteIds` limits alerts to the sites the user follows; `nil` returns all.
    func fetchAlerts(siteIds: [Int]?) async throws -> [HazardAlert]
    func fetchActiveHolds() async throws -> [LightningHold]
    func fetchSiteBriefing(siteId: Int) async throws -> SiteBriefing
    func fetchNextDayBriefing() async throws -> DailyBriefing
    func fetchReports() async throws -> [CrewReport]
    func submitReport(_ report: HazardReport) async throws
    func acknowledgeAlert(id: String) async throws
    func registerDevice(apnsToken: String) async throws
    /// Tells the backend which sites this user follows, so pushes target only nearby crews.
    func updateSubscription(_ subscription: SiteSubscription) async throws
}

struct SiteSubscription: Codable, Hashable, Sendable {
    let location: SearchLocation
    let homeSiteId: Int
    let siteIds: [Int]
}

struct MockHazardAPI: HazardAPI {
    var latency: Duration = .milliseconds(250)

    func fetchSites() async throws -> [Site] {
        try await Task.sleep(for: latency)
        return MockData.sites
    }

    func fetchAlerts(siteIds: [Int]?) async throws -> [HazardAlert] {
        try await Task.sleep(for: latency)
        guard let siteIds else { return MockData.alerts }
        let wanted = Set(siteIds)
        return MockData.alerts.filter { wanted.contains($0.siteId) }
    }

    func fetchActiveHolds() async throws -> [LightningHold] {
        try await Task.sleep(for: latency)
        return MockData.activeHolds
    }

    func fetchSiteBriefing(siteId: Int) async throws -> SiteBriefing {
        try await Task.sleep(for: latency)
        guard let site = MockData.sites.first(where: { $0.id == siteId }) else { throw URLError(.fileDoesNotExist) }
        return MockData.siteBriefing(for: site)
    }

    func fetchNextDayBriefing() async throws -> DailyBriefing {
        try await Task.sleep(for: latency)
        return MockData.briefing
    }

    func fetchReports() async throws -> [CrewReport] {
        try await Task.sleep(for: latency)
        return MockData.reports
    }

    func submitReport(_ report: HazardReport) async throws {
        try await Task.sleep(for: .milliseconds(400))
    }

    func acknowledgeAlert(id: String) async throws {}

    func registerDevice(apnsToken: String) async throws {}

    func updateSubscription(_ subscription: SiteSubscription) async throws {}
}

struct LiveHazardAPI: HazardAPI {
    let baseURL: URL
    var session: URLSession = .shared

    func fetchSites() async throws -> [Site] { try await get("sites") }

    func fetchAlerts(siteIds: [Int]?) async throws -> [HazardAlert] {
        guard let siteIds else { return try await get("alerts") }
        return try await get("alerts", query: [URLQueryItem(name: "site_ids", value: siteIds.map(String.init).joined(separator: ","))])
    }

    func fetchActiveHolds() async throws -> [LightningHold] { try await get("lightning/holds") }

    func fetchSiteBriefing(siteId: Int) async throws -> SiteBriefing { try await get("sites/\(siteId)/briefing") }

    func fetchNextDayBriefing() async throws -> DailyBriefing { try await get("briefings/next-day") }

    func fetchReports() async throws -> [CrewReport] { try await get("reports") }

    func submitReport(_ report: HazardReport) async throws { try await send("reports", body: report) }

    func acknowledgeAlert(id: String) async throws { try await send("alerts/\(id)/ack", body: [String: String]()) }

    func registerDevice(apnsToken: String) async throws {
        try await send("devices", body: ["apns_token": apnsToken, "platform": "ios"])
    }

    func updateSubscription(_ subscription: SiteSubscription) async throws {
        try await send("me/subscription", body: subscription, method: "PUT")
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        var url = baseURL.appending(path: path)
        if !query.isEmpty { url.append(queryItems: query) }
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONCoding.decoder.decode(T.self, from: data)
    }

    private func send<Body: Encodable>(_ path: String, body: Body, method: String = "POST") async throws {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONCoding.encoder.encode(body)
        let (_, response) = try await session.data(for: request)
        try validate(response)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
