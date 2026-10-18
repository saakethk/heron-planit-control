import CoreLocation
import Foundation
import Observation
import UIKit

enum AppTab: String, Hashable, Sendable {
    case dashboard, sites, alerts, report
}

struct SiteSheet: Identifiable, Hashable {
    let id: Int
}

/// Sites beyond the nearest group, bucketed by distance for the "More sites" list.
struct DistanceBand: Identifiable {
    let title: String
    let sites: [Site]

    var id: String { title }
}

/// Single source of truth for UI state. Views read from it through the environment.
/// All backend access goes through `HazardAPI` and `RealtimeService`, so switching
/// from mock to live data is a change in `makeDefault()`.
@MainActor
@Observable
final class AppStore {
    private(set) var sites: [Site] = []
    private(set) var alerts: [HazardAlert] = []
    private(set) var lightningHolds: [Int: LightningHold] = [:]
    private(set) var siteBriefings: [Int: SiteBriefing] = [:]
    private(set) var nextDayBriefing: DailyBriefing?
    private(set) var reports: [CrewReport] = []
    /// Small thumbnails of photos submitted from this device, so list rows never decode full-size images.
    private(set) var localReportThumbnails: [String: UIImage] = [:]
    private(set) var acknowledgedAlertIds: Set<String> = []
    private(set) var connection: ConnectionStatus = .offline
    private(set) var isLoading = false
    private(set) var lastUpdated: Date?
    /// Set to the site nearest `searchLocation` once sites load, unless the user picked one.
    private(set) var homeSiteId: Int = UserDefaults.standard.integer(forKey: StorageKey.homeSiteId)
    private(set) var searchLocation: SearchLocation = AppStore.storedLocation() ?? .gainesville
    /// Site IDs sorted nearest-first from `searchLocation`.
    private(set) var siteIdsByDistance: [Int] = []
    private(set) var distanceMiles: [Int: Double] = [:]
    var needsLocationChoice = !UserDefaults.standard.bool(forKey: StorageKey.hasChosenLocation)
    private(set) var notificationsAuthorized = false
    private(set) var dailyBriefingEnabled = true
    private(set) var fastAllClear = false
    private(set) var liveFeedEnabled = true
    var loadError: String?
    var lastSimulateMessage: String?
    var selectedTab: AppTab = .dashboard
    var presentedSite: SiteSheet?
    @ObservationIgnored var promptsForNotificationsOnStart = true

    let usesMockBackend: Bool

    @ObservationIgnored private let api: HazardAPI
    @ObservationIgnored private let realtime: RealtimeService
    @ObservationIgnored private let notifications: NotificationManager
    @ObservationIgnored private var realtimeTask: Task<Void, Never>?
    @ObservationIgnored private var holdMonitorTask: Task<Void, Never>?
    @ObservationIgnored private var hasStarted = false
    /// Position of each site in `sites`, so lookups by ID don't scan 300+ sites.
    @ObservationIgnored private var siteIndex: [Int: Int] = [:]
    @ObservationIgnored private var subscribedSiteIds: Set<Int> = []

    static let nearbyCount = 25
    /// The live feed runs for the whole demo; capping keeps lists and charts fast.
    private static let maxAlerts = 150
    private static let maxHistoryPoints = 120

    private enum StorageKey {
        static let homeSiteId = "homeSiteId"
        static let location = "searchLocation"
        static let hasChosenLocation = "hasChosenLocation"
    }

    private static func storedLocation() -> SearchLocation? {
        UserDefaults.standard.data(forKey: StorageKey.location)
            .flatMap { try? JSONDecoder().decode(SearchLocation.self, from: $0) }
    }

    init(api: HazardAPI, realtime: RealtimeService, notifications: NotificationManager, usesMockBackend: Bool) {
        self.api = api
        self.realtime = realtime
        self.notifications = notifications
        self.usesMockBackend = usesMockBackend
    }

    static func makeDefault() -> AppStore {
        if AppConfig.useMockBackend {
            return AppStore(
                api: MockHazardAPI(), realtime: MockRealtimeService(),
                notifications: .shared, usesMockBackend: true)
        }
        return AppStore(
            api: LiveHazardAPI(baseURL: AppConfig.apiBaseURL),
            realtime: WebSocketRealtimeService(url: AppConfig.realtimeURL),
            notifications: .shared, usesMockBackend: false)
    }

    // MARK: Lifecycle

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true

        notifications.onAcknowledge = { [weak self] id in self?.acknowledge(alertId: id) }
        notifications.onOpen = { [weak self] tab in self?.selectedTab = tab }

        // Load data before prompting: the permission dialog blocks until answered.
        await refresh()
        startRealtime()
        startHoldMonitor()
        if promptsForNotificationsOnStart {
            await requestNotificationPermission()
        }
    }

    /// Pulls a full snapshot and merges it with anything already received live.
    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let fetchedSites = api.fetchSites()
            async let fetchedAlerts = api.fetchAlerts(siteIds: siteIdsByDistance.isEmpty ? nil : followedSiteIds)
            async let fetchedHolds = api.fetchActiveHolds()
            async let fetchedBriefing = api.fetchNextDayBriefing()
            async let fetchedReports = api.fetchReports()
            let (newSites, newAlerts, newHolds, newBriefing, newReports) =
                try await (fetchedSites, fetchedAlerts, fetchedHolds, fetchedBriefing, fetchedReports)

            setSites(newSites)
            let followed = Set(followedSiteIds)
            alerts = merge(alerts, newAlerts)
                .filter { followed.contains($0.siteId) }
                .sorted { $0.issuedAt > $1.issuedAt }
            acknowledgedAlertIds.formUnion(newAlerts.filter { $0.acknowledged == true }.map(\.id))
            for hold in newHolds where hold.endsAt > .now {
                if let local = lightningHolds[hold.siteId], local.lastStrikeAt >= hold.lastStrikeAt { continue }
                lightningHolds[hold.siteId] = hold
            }
            nextDayBriefing = newBriefing
            reports = merge(reports, newReports).sorted { $0.createdAt > $1.createdAt }
            lastUpdated = .now
            loadError = nil
        } catch {
            loadError = "Couldn't reach the hazard service. Showing offline data."
            if sites.isEmpty {
                setSites(MockData.sites)
                alerts = MockData.alerts
                for hold in MockData.activeHolds {
                    lightningHolds[hold.siteId] = hold
                }
                nextDayBriefing = MockData.briefing
                reports = MockData.reports
                lastUpdated = .now
            }
        }
        await loadBriefing(siteId: homeSiteId)
    }

    private func setSites(_ newSites: [Site]) {
        sites = newSites
        siteIndex = Dictionary(newSites.enumerated().map { ($1.id, $0) }, uniquingKeysWith: { first, _ in first })
        updateDistances()
        if siteIndex[homeSiteId] == nil, let nearest = siteIdsByDistance.first {
            homeSiteId = nearest
        }
    }

    /// The nearest sites plus the home site: what alerts, the live feed, and pushes cover.
    private var followedSiteIds: [Int] {
        var ids = Array(siteIdsByDistance.prefix(Self.nearbyCount))
        if homeSiteId != 0, !ids.contains(homeSiteId) { ids.append(homeSiteId) }
        return ids
    }

    /// After a location change: drop alerts for sites no longer followed and fetch the new ones.
    private func reloadAlerts() async {
        let followed = followedSiteIds
        let wanted = Set(followed)
        let fetched = (try? await api.fetchAlerts(siteIds: followed)) ?? []
        alerts = merge(alerts.filter { wanted.contains($0.siteId) }, fetched)
            .filter { wanted.contains($0.siteId) }
            .sorted { $0.issuedAt > $1.issuedAt }
    }

    private func syncSubscription() {
        let subscription = SiteSubscription(location: searchLocation, homeSiteId: homeSiteId, siteIds: followedSiteIds)
        Task { [api] in try? await api.updateSubscription(subscription) }
    }

    private func updateDistances() {
        let origin = searchLocation.clLocation
        var distances: [Int: Double] = [:]
        distances.reserveCapacity(sites.count)
        for site in sites { distances[site.id] = Distance.miles(from: origin, to: site) }
        distanceMiles = distances
        siteIdsByDistance = sites.map(\.id).sorted { distances[$0, default: .infinity] < distances[$1, default: .infinity] }
    }

    func loadBriefing(siteId: Int) async {
        if let briefing = try? await api.fetchSiteBriefing(siteId: siteId) {
            siteBriefings[siteId] = briefing
        }
    }

    func performBackgroundRefresh() async {
        await refresh()
        if dailyBriefingEnabled {
            notifications.scheduleDailyBriefing(summary: nextDayBriefing?.summary)
        }
        BackgroundRefresh.schedule()
    }

    func registerDevice(apnsToken: String) async {
        do {
            try await api.registerDevice(apnsToken: apnsToken)
        } catch {
            print("Device registration failed: \(error)")
        }
    }

    private func startRealtime() {
        realtimeTask?.cancel()
        let siteIds = followedSiteIds
        subscribedSiteIds = Set(siteIds)
        syncSubscription()
        realtimeTask = Task { [weak self, realtime] in
            for await update in realtime.updates(subscribedTo: siteIds) {
                guard let self else { return }
                switch update {
                case .connection(let status): connection = status
                case .event(let event): handle(event)
                }
            }
        }
    }

    private func stopRealtime() {
        realtimeTask?.cancel()
        realtimeTask = nil
        connection = .offline
    }

    private func startHoldMonitor() {
        holdMonitorTask?.cancel()
        holdMonitorTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                self?.expireHolds()
            }
        }
    }

    // MARK: Realtime events

    func handle(_ event: RealtimeEvent) {
        switch event {
        case let .hazardIndexUpdated(siteId, hazardIndex, factors):
            applyIndexUpdate(HazardIndexUpdate(siteId: siteId, hazardIndex: hazardIndex, factors: factors))
            lastUpdated = .now

        case .hazardIndexBatch(let updates):
            var updated = sites
            for update in updates { applyIndexUpdate(update, to: &updated) }
            sites = updated
            lastUpdated = .now

        case .alert(let alert):
            receive(alert)

        case .lightningStrike(let strike):
            handleLightning(strike)
        }
    }

    private func applyIndexUpdate(_ update: HazardIndexUpdate) {
        var updated = sites
        applyIndexUpdate(update, to: &updated)
        sites = updated
    }

    /// Works on a copy so a batch of 300+ updates triggers one UI refresh, not one per site.
    private func applyIndexUpdate(_ update: HazardIndexUpdate, to sites: inout [Site]) {
        guard let i = siteIndex[update.siteId], sites.indices.contains(i) else { return }
        let previous = sites[i].riskLevel
        sites[i].hazardIndex = update.hazardIndex
        if let factors = update.factors { sites[i].factors = factors }
        sites[i].updatedAt = .now
        sites[i].history = Array(((sites[i].history ?? []) + [IndexPoint(time: .now, value: update.hazardIndex)])
            .suffix(Self.maxHistoryPoints))
        if previous != .severe, sites[i].riskLevel == .severe, isSubscribed(update.siteId) {
            let site = sites[i]
            receive(HazardAlert(
                id: UUID().uuidString, siteId: site.id,
                type: site.topFactor?.type ?? .other, severity: .warning,
                title: "Hazard index is now severe",
                message: "\(site.name) rose to \(update.hazardIndex.oneDecimal), driven by \(site.topFactor?.type.displayName.lowercased() ?? "multiple factors"). Review conditions before continuing work.",
                issuedAt: .now, source: "Hazard model"))
        }
    }

    /// Notifications go only to the user's own sites; statewide events stay in the app.
    private func isSubscribed(_ siteId: Int) -> Bool {
        siteId == homeSiteId || subscribedSiteIds.contains(siteId)
    }

    private func receive(_ alert: HazardAlert) {
        guard isSubscribed(alert.siteId), !alerts.contains(where: { $0.id == alert.id }) else { return }
        insertAlert(alert)
        if alert.severity >= .warning || alert.siteId == homeSiteId {
            notifications.post(alert: alert, siteName: siteName(for: alert.siteId))
        }
    }

    /// Any strike within the radius starts a stop-work hold. Each later strike resets
    /// the all-clear countdown.
    private func handleLightning(_ strike: LightningStrike) {
        if let i = siteIndex[strike.siteId] {
            sites[i].conditions?.nearestStrikeMiles = strike.distanceMiles
        }
        guard strike.distanceMiles <= LightningPolicy.stopWorkRadiusMiles else { return }

        let existing = activeHold(for: strike.siteId)
        var hold = existing ?? LightningHold(
            siteId: strike.siteId, startedAt: strike.occurredAt, lastStrikeAt: strike.occurredAt,
            strikeCount: 0, closestMiles: strike.distanceMiles, lastDistanceMiles: strike.distanceMiles,
            lastDirection: strike.direction, allClearInterval: currentAllClearInterval)
        hold.lastStrikeAt = strike.occurredAt
        hold.strikeCount += 1
        hold.closestMiles = min(hold.closestMiles, strike.distanceMiles)
        hold.lastDistanceMiles = strike.distanceMiles
        hold.lastDirection = strike.direction
        lightningHolds[strike.siteId] = hold
        updateBriefingForStrike(strike)

        // Holds anywhere show on the map; alerts and notifications are for the user's sites.
        // The live backend sends its own stop-work alerts for holds.
        guard usesMockBackend, isSubscribed(strike.siteId) else { return }
        let location = "\(strike.distanceMiles.formatted()) mi\(strike.direction.map { " \($0)" } ?? "")"
        let alert = HazardAlert(
            id: UUID().uuidString, siteId: strike.siteId, type: .lightning, severity: .stopWork,
            title: existing == nil ? "Stop work: lightning \(location)" : "Lightning hold extended: \(location)",
            message: "Shelter now. The all-clear countdown restarts with every strike within 10 mi.",
            issuedAt: strike.occurredAt, acknowledged: false, source: "Lightning network")
        insertAlert(alert)
        notifications.postLightningHold(
            alertId: alert.id, siteId: strike.siteId, siteName: siteName(for: strike.siteId),
            strike: strike, endsAt: hold.endsAt, isReset: existing != nil)
    }

    private func expireHolds() {
        let now = Date.now
        for hold in lightningHolds.values where hold.endsAt <= now {
            lightningHolds[hold.siteId] = nil
            markLightningCleared(siteId: hold.siteId)
            guard usesMockBackend, isSubscribed(hold.siteId) else { continue }
            insertAlert(HazardAlert(
                id: UUID().uuidString, siteId: hold.siteId, type: .lightning, severity: .advisory,
                title: "All clear: work may resume",
                message: "No strikes within 10 mi since \(hold.lastStrikeAt.formatted(date: .omitted, time: .shortened)). \(hold.strikeCount) strikes during this hold.",
                issuedAt: now, acknowledged: false, source: "Lightning network"))
        }
    }

    private func insertAlert(_ alert: HazardAlert) {
        alerts.insert(alert, at: 0)
        if alerts.count > Self.maxAlerts {
            alerts.removeLast(alerts.count - Self.maxAlerts)
        }
    }

    private func updateBriefingForStrike(_ strike: LightningStrike) {
        guard var briefing = siteBriefings[strike.siteId] else { return }
        briefing.events.removeAll { $0.type == .lightning && $0.isActive }
        briefing.events.insert(SiteBriefing.Event(
            id: "live-lightning-\(strike.siteId)", type: .lightning,
            title: "Lightning \(strike.distanceMiles.formatted()) mi\(strike.direction.map { " \($0)" } ?? "")",
            detail: "Work is stopped. Shelter until the all-clear; the countdown restarts with each strike.",
            time: strike.occurredAt, isActive: true), at: 0)
        briefing.updatedAt = .now
        siteBriefings[strike.siteId] = briefing
    }

    private func markLightningCleared(siteId: Int) {
        if let i = siteIndex[siteId] {
            sites[i].conditions?.nearestStrikeMiles = nil
        }
        guard var briefing = siteBriefings[siteId] else { return }
        briefing.events = briefing.events.map { event in
            guard event.type == .lightning, event.isActive else { return event }
            return SiteBriefing.Event(
                id: event.id, type: .lightning, title: "Lightning cleared",
                detail: "No strikes within 10 mi. Work resumed.", time: .now, isActive: false)
        }
        siteBriefings[siteId] = briefing
    }

    // MARK: User actions

    func setHomeSite(_ id: Int) {
        homeSiteId = id
        UserDefaults.standard.set(id, forKey: StorageKey.homeSiteId)
        if !subscribedSiteIds.contains(id), liveFeedEnabled { startRealtime() } else { syncSubscription() }
        Task { await loadBriefing(siteId: id) }
    }

    /// Re-sorts sites around the new location, makes the nearest one the home site,
    /// and re-subscribes the live feed to the new nearby sites.
    func setLocation(_ location: SearchLocation) {
        searchLocation = location
        needsLocationChoice = false
        let defaults = UserDefaults.standard
        defaults.set(try? JSONEncoder().encode(location), forKey: StorageKey.location)
        defaults.set(true, forKey: StorageKey.hasChosenLocation)
        updateDistances()
        if let nearest = siteIdsByDistance.first {
            homeSiteId = nearest
            defaults.set(nearest, forKey: StorageKey.homeSiteId)
            Task { await loadBriefing(siteId: nearest) }
        } else {
            // Sites haven't loaded yet; `setSites` picks the nearest one when they do.
            homeSiteId = 0
            defaults.removeObject(forKey: StorageKey.homeSiteId)
        }
        guard hasStarted else { return }
        Task { await reloadAlerts() }
        if liveFeedEnabled { startRealtime() } else { syncSubscription() }
    }

    /// Nearest site to a location, for previews in the location picker.
    func nearestSite(to location: SearchLocation) -> (site: Site, miles: Double)? {
        let origin = location.clLocation
        return sites
            .map { ($0, Distance.miles(from: origin, to: $0)) }
            .min { $0.1 < $1.1 }
    }

    func showSite(_ id: Int) {
        presentedSite = SiteSheet(id: id)
        if siteBriefings[id] == nil {
            Task { await loadBriefing(siteId: id) }
        }
    }

    func acknowledge(alertId: String) {
        acknowledgedAlertIds.insert(alertId)
        Task { [api] in try? await api.acknowledgeAlert(id: alertId) }
    }

    func acknowledgeAll() {
        acknowledgedAlertIds.formUnion(alerts.map(\.id))
    }

    func requestNotificationPermission() async {
        notificationsAuthorized = await notifications.requestAuthorization()
        if notificationsAuthorized, dailyBriefingEnabled {
            notifications.scheduleDailyBriefing(summary: nextDayBriefing?.summary)
        }
    }

    func setDailyBriefing(enabled: Bool) {
        dailyBriefingEnabled = enabled
        if enabled {
            notifications.scheduleDailyBriefing(summary: nextDayBriefing?.summary)
        } else {
            notifications.cancelDailyBriefing()
        }
    }

    func submitReport(
        type: HazardType, siteId: Int?, notes: String, photoJpeg: Data?, thumbnail: UIImage?,
        coordinate: CLLocationCoordinate2D?
    ) async throws {
        let report = HazardReport(
            id: UUID().uuidString, siteId: siteId, type: type, notes: notes,
            latitude: coordinate?.latitude, longitude: coordinate?.longitude,
            createdAt: .now, photoJpeg: photoJpeg)
        try await api.submitReport(report)

        reports.insert(CrewReport(
            id: report.id, siteId: siteId, type: type,
            notes: notes.isEmpty ? "No details added." : notes,
            reporter: "You", createdAt: report.createdAt), at: 0)
        localReportThumbnails[report.id] = thumbnail

        if let siteId {
            receive(HazardAlert(
                id: report.id, siteId: siteId, type: type, severity: .advisory,
                title: "\(type.displayName) reported by crew",
                message: notes.isEmpty ? "A crew member submitted a hazard report." : notes,
                issuedAt: report.createdAt, acknowledged: true, source: "Crew report"))
        }
    }

    // MARK: Demo controls

    private var currentAllClearInterval: TimeInterval {
        fastAllClear ? LightningPolicy.demoAllClearInterval : LightningPolicy.allClearInterval
    }

    func simulateLightningStrike(siteId: Int? = nil) {
        let target = siteId ?? homeSiteId
        if usesMockBackend {
            handle(.lightningStrike(LightningStrike(
                siteId: target,
                distanceMiles: Double.random(in: 2...9).rounded(toPlaces: 1),
                occurredAt: .now,
                direction: MockData.directions.randomElement())))
            return
        }
        Task { await runLiveSimulation(kind: "lightning", siteId: target, miles: 4) }
    }

    func simulateFloodWarning() {
        if usesMockBackend {
            handle(.alert(HazardAlert(
                id: UUID().uuidString, siteId: homeSiteId, type: .flood, severity: .warning,
                title: "Flood risk after heavy rain",
                message: "3.1 in. of rain in 12 hours. Low-lying access roads may be impassable.",
                issuedAt: .now, acknowledged: false, source: "NWS")))
            return
        }
        Task { await runLiveSimulation(kind: "flood", siteId: homeSiteId) }
    }

    func simulateHeatSpike() {
        if usesMockBackend {
            guard let site = homeSite else { return }
            var factors = site.factors.filter { $0.type != .heat }
            factors.append(HazardFactor(type: .heat, score: 9.3, detail: "Heat index 113°F. Stop strenuous work."))
            if let i = siteIndex[site.id] {
                sites[i].conditions?.heatIndexF = 113
            }
            handle(.hazardIndexUpdated(siteId: site.id, hazardIndex: max(site.hazardIndex, 8.7), factors: factors))
            return
        }
        Task { await runLiveSimulation(kind: "heat", siteId: homeSiteId) }
    }

    /// Sends the event through the backend pipeline so scores, alerts, and
    /// notifications update the same way a real Open-Meteo / GLM observation would.
    @discardableResult
    func runLiveSimulation(kind: String, siteId: Int?, miles: Double? = nil) async -> Bool {
        do {
            let result = try await api.simulate(kind: kind, siteId: siteId, miles: miles)
            lastSimulateMessage = result.detail
            await refresh()
            if let holds = try? await api.fetchActiveHolds() {
                for hold in holds { lightningHolds[hold.siteId] = hold }
                let active = Set(holds.map(\.siteId))
                for siteId in lightningHolds.keys where !active.contains(siteId) {
                    lightningHolds[siteId] = nil
                    markLightningCleared(siteId: siteId)
                }
            }
            if let siteId, kind == "lightning" || kind == "clear" {
                await loadBriefing(siteId: siteId)
            }
            return true
        } catch {
            lastSimulateMessage = "Couldn't send the simulated event. Is the backend running?"
            return false
        }
    }

    func sendTestBriefing() {
        if usesMockBackend {
            notifications.sendTestBriefing(summary: nextDayBriefing?.summary)
            return
        }
        Task {
            if await runLiveSimulation(kind: "briefing", siteId: homeSiteId) {
                await refresh()
            }
        }
    }

    /// Ends every hold on the next monitor tick, which posts the all-clear alerts.
    func clearLightningHolds() {
        if !usesMockBackend {
            Task { await runLiveSimulation(kind: "clear", siteId: nil) }
            return
        }
        for (siteId, var hold) in lightningHolds {
            notifications.cancelAllClear(siteId: siteId)
            hold.lastStrikeAt = .now.addingTimeInterval(-hold.allClearInterval)
            lightningHolds[siteId] = hold
        }
    }

    func setFastAllClear(_ enabled: Bool) {
        fastAllClear = enabled
        for (siteId, var hold) in lightningHolds {
            hold.allClearInterval = currentAllClearInterval
            lightningHolds[siteId] = hold
            notifications.scheduleAllClear(siteId: siteId, siteName: siteName(for: siteId), at: hold.endsAt)
        }
    }

    func setLiveFeed(_ enabled: Bool) {
        liveFeedEnabled = enabled
        if enabled {
            startRealtime()
        } else {
            stopRealtime()
        }
    }

    func resetDemo() async {
        for siteId in lightningHolds.keys { notifications.cancelAllClear(siteId: siteId) }
        alerts = []
        reports = []
        lightningHolds = [:]
        siteBriefings = [:]
        acknowledgedAlertIds = []
        localReportThumbnails = [:]
        homeSiteId = 0
        UserDefaults.standard.removeObject(forKey: StorageKey.homeSiteId)
        await refresh()
        if liveFeedEnabled { startRealtime() }
    }

    // MARK: Derived state

    var homeSite: Site? { site(id: homeSiteId) }

    var homeBriefing: SiteBriefing? { siteBriefings[homeSiteId] }

    var rankedSites: [Site] { sites.sorted { $0.hazardIndex > $1.hazardIndex } }

    var unacknowledgedCount: Int { alerts.filter { !acknowledgedAlertIds.contains($0.id) }.count }

    func site(id: Int) -> Site? {
        guard let i = siteIndex[id], sites.indices.contains(i) else { return nil }
        return sites[i]
    }

    func distance(to siteId: Int) -> Double? { distanceMiles[siteId] }

    /// Every site, nearest first from `searchLocation`.
    var sitesByDistance: [Site] { siteIdsByDistance.compactMap(site(id:)) }

    /// The sites the crew follows: the closest `nearbyCount` to their location.
    var nearbySites: [Site] { siteIdsByDistance.prefix(Self.nearbyCount).compactMap(site(id:)) }

    func isNearby(_ siteId: Int) -> Bool {
        siteIdsByDistance.prefix(Self.nearbyCount).contains(siteId)
    }

    /// Sites past the nearest group, grouped for the collapsible "More sites" list.
    func fartherBands(from sites: [Site]) -> [DistanceBand] {
        let bands: [(String, Range<Double>)] = [
            ("Within 50 mi", 0..<50), ("50-100 mi", 50..<100), ("100-200 mi", 100..<200), ("Over 200 mi", 200..<Double.infinity),
        ]
        return bands.compactMap { title, range in
            let matching = sites.filter { range.contains(distanceMiles[$0.id] ?? .infinity) }
            return matching.isEmpty ? nil : DistanceBand(title: title, sites: matching)
        }
    }

    /// Stop-work or severe sites outside the nearby group, so distance never hides danger.
    func severeElsewhere(at date: Date = .now) -> [Site] {
        let nearby = Set(siteIdsByDistance.prefix(Self.nearbyCount))
        let held = Set(activeHolds(at: date).map(\.siteId))
        return sites
            .filter { !nearby.contains($0.id) && (held.contains($0.id) || $0.riskLevel == .severe) }
            .sorted { lhs, rhs in
                let (l, r) = (held.contains(lhs.id), held.contains(rhs.id))
                return l != r ? l : lhs.hazardIndex > rhs.hazardIndex
            }
    }

    func siteName(for id: Int?) -> String {
        guard let id else { return "No site" }
        return site(id: id)?.name ?? "Site \(id)"
    }

    func alerts(for siteId: Int) -> [HazardAlert] { alerts.filter { $0.siteId == siteId } }

    func reports(for siteId: Int) -> [CrewReport] { reports.filter { $0.siteId == siteId } }

    func isAcknowledged(_ alert: HazardAlert) -> Bool { acknowledgedAlertIds.contains(alert.id) }

    /// Holds expire based on time, so views showing them should wrap in a `TimelineView`.
    func activeHold(for siteId: Int, at date: Date = .now) -> LightningHold? {
        guard let hold = lightningHolds[siteId], hold.endsAt > date else { return nil }
        return hold
    }

    func activeHolds(at date: Date = .now) -> [LightningHold] {
        lightningHolds.values.filter { $0.endsAt > date }.sorted { $0.endsAt < $1.endsAt }
    }

    func nearestSite(to location: CLLocation, within meters: CLLocationDistance = 5_000) -> Site? {
        sites
            .map { ($0, location.distance(from: CLLocation(latitude: $0.latitude, longitude: $0.longitude))) }
            .filter { $0.1 <= meters }
            .min { $0.1 < $1.1 }?.0
    }

    private func merge<T: Identifiable>(_ existing: [T], _ incoming: [T]) -> [T] {
        let incomingIds = Set(incoming.map(\.id))
        return incoming + existing.filter { !incomingIds.contains($0.id) }
    }
}
