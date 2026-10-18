import Foundation

/// Dummy data for building the UI before the backend exists. Every Florida plant in
/// EIA-860M is included (`Resources/florida_sites.json`, exported by
/// `scripts/export_sites.py`); hazard values, conditions, and events are made up.
enum MockData {
    /// John R Kelly, the plant closest to the default Gainesville location.
    static let gainesvilleSiteId = 664

    static let directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    // MARK: Sites

    private struct Plant: Decodable {
        let id: Int
        let name: String
        let county: String
        let latitude: Double
        let longitude: Double
        let capacityMw: Double
    }

    private static let plants: [Plant] = {
        guard let url = Bundle.main.url(forResource: "florida_sites", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let plants = try? JSONCoding.decoder.decode([Plant].self, from: data)
        else { return [] }
        return plants
    }()

    /// All plants: handcrafted demo sites keep their story, the rest get generated values.
    static var sites: [Site] {
        let crafted = Dictionary(uniqueKeysWithValues: handcraftedSites.map { ($0.id, $0) })
        guard !plants.isEmpty else { return handcraftedSites }
        return plants.map { crafted[$0.id] ?? generatedSite(for: $0) }
    }

    private static var handcraftedSites: [Site] {
        [
            site(664, "John R Kelly", "Alachua", 29.6461, -82.3208, 141.6,
                 index: 7.4, startIndex: 5.2,
                 conditions: .init(temperatureF: 92, heatIndexF: 104, windMph: 11, rain24hIn: 0.8, soilMoisturePct: 66, nearestStrikeMiles: 6.1),
                 factors: [
                    (.lightning, 8.4, "Storm cell 6.1 mi SW, moving NE at 12 mph"),
                    (.heat, 6.4, "Heat index 104°F by 3 PM"),
                    (.wildlife, 4.2, "Alligator at the cooling pond"),
                    (.soilSaturation, 3.0, "Soil 66% saturated"),
                 ]),
            site(617, "Port Everglades", "Broward", 26.0856, -80.1253, 1352.0,
                 index: 7.8, startIndex: 5.9,
                 conditions: .init(temperatureF: 93, heatIndexF: 108, windMph: 14, rain24hIn: 0.3, soilMoisturePct: 58, nearestStrikeMiles: 4.2),
                 factors: [
                    (.lightning, 8.9, "Storm cell 4.2 mi NE, moving SW at 15 mph"),
                    (.heat, 7.1, "Heat index 108°F by 2 PM"),
                    (.flood, 4.6, "King tide at 11:20 AM on the east dock"),
                    (.soilSaturation, 2.1, "Soil 58% saturated"),
                 ]),
            site(627, "Bayboro", "Pinellas", 27.758056, -82.63528, 170.1,
                 index: 6.9, startIndex: 6.2,
                 conditions: .init(temperatureF: 89, heatIndexF: 101, windMph: 9, rain24hIn: 2.9, soilMoisturePct: 94, nearestStrikeMiles: nil),
                 factors: [
                    (.flood, 8.1, "2.9 in. of rain overnight; Tampa Bay surge risk"),
                    (.soilSaturation, 7.4, "Soil 94% saturated, trench walls unstable"),
                    (.heat, 5.0, "Heat index 101°F"),
                 ]),
            site(54466, "Orlando Cogen LP", "Orange", 28.442623, -81.41234, 122.4,
                 index: 5.8, startIndex: 4.1,
                 conditions: .init(temperatureF: 96, heatIndexF: 111, windMph: 6, rain24hIn: 0, soilMoisturePct: 41, nearestStrikeMiles: 18),
                 factors: [
                    (.heat, 7.9, "Heat index 111°F, limit exposure to 45 min"),
                    (.lightning, 4.6, "Afternoon storms 40% likely"),
                    (.wildlife, 3.0, "Snake sighting near the cooling tower"),
                 ]),
            site(56518, "South Energy Center", "Alachua", 29.6383, -82.34, 11.5,
                 index: 4.7, startIndex: 3.9,
                 conditions: .init(temperatureF: 92, heatIndexF: 99, windMph: 7, rain24hIn: 0.2, soilMoisturePct: 52, nearestStrikeMiles: nil),
                 factors: [
                    (.wildlife, 6.2, "Alligator reported at the retention pond"),
                    (.heat, 5.5, "Heat index 99°F"),
                    (.lightning, 4.1, "Isolated storms after 4 PM"),
                 ]),
            site(619, "Riviera", "Palm Beach", 26.7653, -80.0525, 1295.0,
                 index: 4.1, startIndex: 4.6,
                 conditions: .init(temperatureF: 88, heatIndexF: 97, windMph: 12, rain24hIn: 0.6, soilMoisturePct: 61, nearestStrikeMiles: 22),
                 factors: [
                    (.flood, 5.0, "Minor coastal flooding at high tide"),
                    (.lightning, 4.4, "Storms moving offshore"),
                    (.heat, 4.0, "Heat index 97°F"),
                 ]),
            site(50875, "McKay Bay Facility", "Hillsborough", 27.949528, -82.42118, 22.1,
                 index: 3.6, startIndex: 3.0,
                 conditions: .init(temperatureF: 90, heatIndexF: 95, windMph: 8, rain24hIn: 1.1, soilMoisturePct: 71, nearestStrikeMiles: nil),
                 factors: [
                    (.soilSaturation, 4.8, "Soil 71% saturated"),
                    (.heat, 3.9, "Heat index 95°F"),
                 ]),
            site(136, "Seminole (FL)", "Putnam", 29.733056, -81.63278, 1897.8,
                 index: 2.8, startIndex: 2.6,
                 conditions: .init(temperatureF: 91, heatIndexF: 92, windMph: 10, rain24hIn: 0, soilMoisturePct: 33, nearestStrikeMiles: nil),
                 factors: [
                    (.wildfire, 3.8, "Dry fuels on the west buffer, KBDI 520"),
                    (.heat, 2.7, "Heat index 92°F"),
                 ]),
            site(64546, "Wynwood Energy Storage", "Miami Dade", 25.798978, -80.1971, 10.0,
                 index: 1.8, startIndex: 2.0,
                 conditions: .init(temperatureF: 87, heatIndexF: 90, windMph: 11, rain24hIn: 0.1, soilMoisturePct: 45, nearestStrikeMiles: 27),
                 factors: [
                    (.heat, 2.4, "Heat index 90°F"),
                    (.flood, 1.2, "No flood risk expected"),
                 ]),
        ]
    }

    /// Stable per-plant values (seeded by plant ID) with rough regional patterns:
    /// hotter in the south, more wildfire and lightning in the Panhandle.
    private static func generatedSite(for plant: Plant) -> Site {
        var rng = SeededGenerator(seed: UInt64(plant.id))
        let south = plant.latitude < 27
        let panhandle = plant.longitude < -84

        let temperature = (south ? 91 : 88) + Double(Int.random(in: 0...6, using: &rng))
        let heatIndex = temperature + Double(Int.random(in: 3...15, using: &rng))
        let rain = Double.random(in: 0...(south ? 2.2 : 1.4), using: &rng).rounded(toPlaces: 1)
        let soil = Double(Int.random(in: 30...92, using: &rng))
        let stormMiles = Double.random(in: 7...30, using: &rng).rounded(toPlaces: 1)

        func score(_ range: ClosedRange<Double>) -> Double {
            Double.random(in: range, using: &rng).rounded(toPlaces: 1)
        }
        /// Mostly low values with a long tail, so only a few sites end up high or severe.
        func skewed(_ range: ClosedRange<Double>) -> Double {
            let u = Double.random(in: 0...1, using: &rng)
            return (range.lowerBound + (range.upperBound - range.lowerBound) * u * u * u).rounded(toPlaces: 1)
        }
        var factors: [HazardFactor] = [
            HazardFactor(type: .heat, score: min(9, max(1, (heatIndex - 97) / 3.2)).rounded(toPlaces: 1),
                         detail: "Heat index \(Int(heatIndex))°F"),
            HazardFactor(type: .lightning, score: skewed(panhandle ? 1.5...9 : 1...9),
                         detail: "Storms within \(stormMiles.formatted()) mi"),
            HazardFactor(type: .flood, score: min(9, rain * 1.8 + skewed(0...5)).rounded(toPlaces: 1),
                         detail: "\(rain.formatted()) in. of rain in 24 hours"),
            HazardFactor(type: .soilSaturation, score: max(0.5, (soil - 45) / 11).rounded(toPlaces: 1),
                         detail: "Soil \(Int(soil))% saturated"),
        ]
        if Int.random(in: 0..<4, using: &rng) == 0 {
            factors.append(HazardFactor(type: .wildlife, score: score(2...6),
                                        detail: wildlifeSightings.randomElement(using: &rng)!))
        }
        if panhandle || Int.random(in: 0..<6, using: &rng) == 0 {
            factors.append(HazardFactor(type: .wildfire, score: skewed(1.5...8.5),
                                        detail: "Dry fuels nearby, KBDI \(Int.random(in: 380...620, using: &rng))"))
        }

        let sorted = factors.map(\.score).sorted(by: >)
        let index = min(9.6, sorted[0] * 0.78 + sorted[1] * 0.2 + score(-0.3...0.3)).rounded(toPlaces: 1)
        let lightning = factors.first { $0.type == .lightning }?.score ?? 0
        return Site(
            id: plant.id, name: plant.name, county: plant.county,
            latitude: plant.latitude, longitude: plant.longitude, capacityMw: plant.capacityMw,
            hazardIndex: max(0.5, index),
            factors: factors.sorted { $0.score > $1.score }.prefix(4).map { $0 },
            updatedAt: .now.addingTimeInterval(-Double(Int.random(in: 1...14, using: &rng)) * 60),
            conditions: SiteConditions(
                temperatureF: temperature, heatIndexF: heatIndex, windMph: Double(Int.random(in: 3...16, using: &rng)),
                rain24hIn: rain, soilMoisturePct: soil, nearestStrikeMiles: lightning >= 5 ? stormMiles : nil),
            history: history(siteId: plant.id, from: max(0.5, index + score(-1.6...0.8)), to: max(0.5, index)))
    }

    private static let wildlifeSightings = [
        "Alligator near the retention pond", "Snake reported near the switchyard",
        "Wild hogs along the fence line", "Black bear seen at the tree line", "Fire ants at the cable trench",
    ]

    // MARK: Lightning

    static var activeHolds: [LightningHold] {
        [
            LightningHold(
                siteId: 664, startedAt: .now.addingTimeInterval(-6 * 60), lastStrikeAt: .now.addingTimeInterval(-140),
                strikeCount: 2, closestMiles: 6.1, lastDistanceMiles: 6.1, lastDirection: "SW",
                allClearInterval: LightningPolicy.allClearInterval),
            LightningHold(
                siteId: 617, startedAt: .now.addingTimeInterval(-9 * 60), lastStrikeAt: .now.addingTimeInterval(-106),
                strikeCount: 3, closestMiles: 3.1, lastDistanceMiles: 4.2, lastDirection: "NE",
                allClearInterval: LightningPolicy.allClearInterval),
        ]
    }

    // MARK: Alerts

    static var alerts: [HazardAlert] {
        [
            HazardAlert(
                id: "seed-gnv-hold", siteId: 664, type: .lightning, severity: .stopWork,
                title: "Stop work: lightning 6.1 mi away",
                message: "Strike SW, moving NE. Shelter in trucks or the control room. All clear in 30:00 if there are no more strikes.",
                issuedAt: .now.addingTimeInterval(-140), acknowledged: false, source: "Lightning network"),
            HazardAlert(
                id: "seed-gnv-gator", siteId: 664, type: .wildlife, severity: .advisory,
                title: "Alligator at the cooling pond",
                message: "About 6 ft alligator on the south bank. Keep 30 ft away and use the north gate.",
                issuedAt: .now.addingTimeInterval(-55 * 60), acknowledged: true, source: "Crew report"),
            HazardAlert(
                id: "seed-hold-extended", siteId: 617, type: .lightning, severity: .stopWork,
                title: "Stop work: lightning 4.2 mi away",
                message: "Strike NE, moving SW. Shelter now. All clear in 30:00 if there are no more strikes.",
                issuedAt: .now.addingTimeInterval(-106), acknowledged: false, source: "Lightning network"),
            HazardAlert(
                id: "seed-hold-start", siteId: 617, type: .lightning, severity: .stopWork,
                title: "Stop work: lightning 6.8 mi away",
                message: "First strike within 10 mi. Stop work and move to trucks or the control building.",
                issuedAt: .now.addingTimeInterval(-9 * 60), acknowledged: false, source: "Lightning network"),
            HazardAlert(
                id: "seed-flood", siteId: 627, type: .flood, severity: .warning,
                title: "Flood risk after overnight rain",
                message: "2.9 in. fell overnight. Check trench walls before entry and avoid the north vault.",
                issuedAt: .now.addingTimeInterval(-2 * 3600), acknowledged: false, source: "NWS"),
            HazardAlert(
                id: "seed-heat", siteId: 54466, type: .heat, severity: .warning,
                title: "Extreme heat: mandatory rest cycles",
                message: "Heat index reaches 111°F at 2 PM. 15-minute shaded rest every 45 minutes.",
                issuedAt: .now.addingTimeInterval(-75 * 60), acknowledged: true, source: "Hazard model"),
            HazardAlert(
                id: "seed-gator", siteId: 56518, type: .wildlife, severity: .advisory,
                title: "Alligator sighting",
                message: "About 7 ft alligator near the retention pond fence. Keep 30 ft away.",
                issuedAt: .now.addingTimeInterval(-40 * 60), acknowledged: true, source: "Crew report"),
            HazardAlert(
                id: "seed-tide", siteId: 617, type: .flood, severity: .advisory,
                title: "King tide at 11:20 AM",
                message: "Move equipment off the east dock before high tide. Avoid low vaults.",
                issuedAt: .now.addingTimeInterval(-3.2 * 3600), acknowledged: true, source: "NOAA Tides"),
            HazardAlert(
                id: "seed-cleared", siteId: 617, type: .lightning, severity: .advisory,
                title: "Lightning hold cleared",
                message: "No strikes within 10 mi for 30 minutes. Work resumed.",
                issuedAt: .now.addingTimeInterval(-3.5 * 3600), acknowledged: true, source: "Lightning network"),
            HazardAlert(
                id: "seed-soil", siteId: 627, type: .soilSaturation, severity: .advisory,
                title: "Soil saturation high",
                message: "Soil moisture is 94%. Shore excavations deeper than 5 ft.",
                issuedAt: .now.addingTimeInterval(-4 * 3600), acknowledged: true, source: "Open-Meteo"),
            HazardAlert(
                id: "seed-smoke", siteId: 136, type: .wildfire, severity: .advisory,
                title: "Smoke advisory",
                message: "Prescribed burn 8 mi upwind. Expect reduced air quality until evening.",
                issuedAt: .now.addingTimeInterval(-26 * 3600), acknowledged: true, source: "Florida Forest Service"),
            HazardAlert(
                id: "seed-riviera-heat", siteId: 619, type: .heat, severity: .warning,
                title: "Heat advisory",
                message: "Heat index 104°F expected. Add a water break every 20 minutes.",
                issuedAt: .now.addingTimeInterval(-28 * 3600), acknowledged: true, source: "NWS"),
        ]
    }

    // MARK: Briefings

    static func siteBriefing(for site: Site) -> SiteBriefing {
        if site.id == gainesvilleSiteId {
            return SiteBriefing(
                siteId: site.id,
                headline: "Storms moving in from the southwest, then a hot afternoon.",
                sources: ["NWS", "lightning network", "crew reports"],
                updatedAt: clock(9, 40),
                events: [
                    .init(id: "gnv-lightning", type: .lightning, title: "Lightning 6.1 mi SW, moving NE",
                          detail: "Work is stopped. Shelter in trucks or the control room until the all-clear.",
                          time: .now, isActive: true),
                    .init(id: "gnv-gator", type: .wildlife, title: "Alligator at the cooling pond",
                          detail: "Use the north gate and keep 30 ft from the south bank.",
                          time: .now.addingTimeInterval(-55 * 60), isActive: false),
                    .init(id: "gnv-heat", type: .heat, title: "Heat index peaks at 104°F",
                          detail: "Rest 15 min in shade every 45 min. Drink water every 15-20 min.",
                          time: clock(15, 0), isActive: false),
                ],
                tomorrowOutlook: "storms 2-7 PM")
        }
        if site.id == 617 {
            return SiteBriefing(
                siteId: 617,
                headline: "Storms over the port this morning, extreme heat this afternoon.",
                sources: ["NWS", "lightning network", "crew reports"],
                updatedAt: clock(9, 15),
                events: [
                    .init(id: "pe-lightning", type: .lightning, title: "Lightning 4.2 mi NE, moving SW",
                          detail: "Work is stopped. Shelter in trucks until the all-clear, about 28 min.",
                          time: .now, isActive: true),
                    .init(id: "pe-tide", type: .flood, title: "King tide at the port",
                          detail: "Move equipment off the east dock before high tide. Avoid low vaults.",
                          time: clock(11, 20), isActive: false),
                    .init(id: "pe-heat", type: .heat, title: "Heat index peaks at 108°F",
                          detail: "Rest 15 min in shade every 45 min. Drink water every 15-20 min.",
                          time: clock(14, 0), isActive: false),
                ],
                tomorrowOutlook: "storms 1-6 PM")
        }

        let offsets: [TimeInterval] = [0, 2 * 3600, 4 * 3600]
        let events = site.sortedFactors.prefix(3).enumerated().map { offset, factor in
            SiteBriefing.Event(
                id: "\(site.id)-\(factor.type.rawValue)", type: factor.type, title: factor.detail,
                detail: guidance(for: factor.type),
                time: .now.addingTimeInterval(offsets[offset]),
                isActive: offset == 0 && factor.score >= 6)
        }
        let top = site.topFactor?.type.displayName.lowercased() ?? "conditions"
        return SiteBriefing(
            siteId: site.id,
            headline: "\(site.riskLevel.label) risk today, driven mostly by \(top).",
            sources: ["NWS", "Open-Meteo", "hazard model"],
            updatedAt: .now.addingTimeInterval(-20 * 60),
            events: events,
            tomorrowOutlook: briefing.items.first { $0.siteId == site.id }?.headline.lowercased() ?? "similar conditions")
    }

    static func guidance(for type: HazardType) -> String {
        switch type {
        case .lightning: "Stop work if strikes come within 10 mi. Know your nearest shelter."
        case .flood: "Avoid low-lying vaults and flooded access roads."
        case .heat: "Rest 15 min in shade every 45 min. Drink water every 15-20 min."
        case .wildfire: "Watch for smoke and keep vehicles off dry grass."
        case .wildlife: "Keep 30 ft from wildlife. Report sightings with a photo."
        case .soilSaturation: "Inspect trench walls before entry. Shore excavations over 5 ft."
        case .other: "Review site conditions with your supervisor."
        }
    }

    static var briefing: DailyBriefing {
        DailyBriefing(
            forDate: Calendar.current.date(byAdding: .day, value: 1, to: .now) ?? .now,
            summary: "Hot and stormy statewide. Heat index above 105°F in Central and South Florida, and afternoon lightning on the Atlantic coast. Plan outdoor work before 1 PM.",
            items: [
                .init(siteId: 664, forecastIndex: 7.0, headline: "Storms 2-7 PM; heat index 103°F"),
                .init(siteId: 617, forecastIndex: 8.2, headline: "Storms 1-6 PM; heat index 107°F"),
                .init(siteId: 627, forecastIndex: 6.5, headline: "Saturated soil; delay trenching"),
                .init(siteId: 54466, forecastIndex: 6.1, headline: "Heat index 110°F; start crews at 6 AM"),
                .init(siteId: 56518, forecastIndex: 4.4, headline: "Gator still near the pond; storms after 4 PM"),
                .init(siteId: 619, forecastIndex: 3.9, headline: "Breezy and drier"),
            ])
    }

    // MARK: Crew reports

    static var reports: [CrewReport] {
        [
            CrewReport(id: "rep-gnv", siteId: 664, type: .wildlife, notes: "About 6 ft alligator on the south bank of the cooling pond.",
                       reporter: "D. Nguyen", createdAt: .now.addingTimeInterval(-55 * 60)),
            CrewReport(id: "rep-1", siteId: 56518, type: .wildlife, notes: "About 7 ft alligator near the retention pond fence.",
                       reporter: "J. Alvarez", createdAt: .now.addingTimeInterval(-40 * 60)),
            CrewReport(id: "rep-2", siteId: 54466, type: .heat, notes: "Shade tent at the cooling tower blew over. Crew has no shade.",
                       reporter: "T. Brooks", createdAt: .now.addingTimeInterval(-62 * 60)),
            CrewReport(id: "rep-3", siteId: 627, type: .flood, notes: "Standing water about 8 in. deep at the north vault.",
                       reporter: "M. Chen", createdAt: .now.addingTimeInterval(-2.5 * 3600)),
            CrewReport(id: "rep-4", siteId: 617, type: .other, notes: "Fence panel down at the east dock gate.",
                       reporter: "R. Patel", createdAt: .now.addingTimeInterval(-5 * 3600)),
        ]
    }

    // MARK: Helpers

    private static func clock(_ hour: Int, _ minute: Int) -> Date {
        Calendar.current.date(bySettingHour: hour, minute: minute, second: 0, of: .now) ?? .now
    }

    /// Readings every 30 minutes from 6 AM (or the last 6 hours if it's early) up to now.
    private static func history(siteId: Int, from start: Double, to end: Double) -> [IndexPoint] {
        let now = Date.now
        var startTime = clock(6, 0)
        if now.timeIntervalSince(startTime) < 3 * 3600 { startTime = now.addingTimeInterval(-6 * 3600) }
        let steps = max(2, Int(now.timeIntervalSince(startTime) / 1800))
        return (0...steps).map { step in
            let progress = Double(step) / Double(steps)
            let wobble = (step == 0 || step == steps) ? 0 : sin(Double(step) * 1.7 + Double(siteId)) * 0.35
            let time = step == steps ? now : startTime.addingTimeInterval(Double(step) * 1800)
            let value = min(10, max(0, start + (end - start) * progress + wobble))
            return IndexPoint(time: time, value: value.rounded(toPlaces: 1))
        }
    }

    private static func site(
        _ id: Int, _ name: String, _ county: String, _ lat: Double, _ lon: Double, _ mw: Double,
        index: Double, startIndex: Double, conditions: SiteConditions,
        factors: [(HazardType, Double, String)]
    ) -> Site {
        Site(
            id: id, name: name, county: county, latitude: lat, longitude: lon, capacityMw: mw,
            hazardIndex: index,
            factors: factors.map { HazardFactor(type: $0.0, score: $0.1, detail: $0.2) },
            updatedAt: .now.addingTimeInterval(-2 * 60),
            conditions: conditions,
            history: history(siteId: id, from: startIndex, to: index))
    }
}

/// SplitMix64, so generated mock values are the same on every launch.
struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) { state = seed &+ 0x9E37_79B9_7F4A_7C15 }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
}

/// Generates plausible realtime events for `MockRealtimeService`, tracking its own
/// copy of site state so consecutive updates drift smoothly. Most events target the
/// subscribed (nearby) sites, like a backend filtering by subscription would.
struct MockFeed {
    private var sites: [Site]
    private let focus: [Int]

    init(sites: [Site] = MockData.sites, focusSiteIds: [Int] = []) {
        self.sites = sites
        let wanted = Set(focusSiteIds)
        focus = sites.indices.filter { wanted.contains(sites[$0].id) }
    }

    private func randomIndex(preferFocus probability: Double) -> Int? {
        if !focus.isEmpty, Double.random(in: 0..<1) < probability { return focus.randomElement() }
        return sites.indices.randomElement()
    }

    private static let alertTemplates: [(HazardType, AlertSeverity, String, String, String)] = [
        (.heat, .warning, "Heat index rising", "Heat index is forecast above 105°F within the hour. Hydrate and rotate crews.", "Hazard model"),
        (.flood, .warning, "Flash flood warning", "NWS flash flood warning for the county. Move equipment off low ground.", "NWS"),
        (.wildlife, .advisory, "Wildlife reported nearby", "A crew reported a venomous snake near the switchyard.", "Crew report"),
        (.wildfire, .advisory, "Smoke advisory", "Prescribed burn 8 mi upwind. Expect reduced air quality.", "Florida Forest Service"),
        (.soilSaturation, .advisory, "Soil saturation high", "Soil moisture is above 90%. Inspect excavations before entry.", "Open-Meteo"),
    ]

    mutating func next() -> RealtimeEvent? {
        switch Int.random(in: 0..<100) {
        case ..<45: indexUpdate()
        case ..<65: modelRun()
        case ..<88: alert()
        default: strike()
        }
    }

    private mutating func indexUpdate() -> RealtimeEvent? {
        guard let i = randomIndex(preferFocus: 0.8) else { return nil }
        let update = drift(i, by: -0.7...0.8)
        return .hazardIndexUpdated(siteId: update.siteId, hazardIndex: update.hazardIndex, factors: update.factors)
    }

    /// A statewide rescoring: small changes to many sites in one batched message.
    private mutating func modelRun() -> RealtimeEvent? {
        let count = min(sites.count, Int.random(in: 40...90))
        let picked = Set(sites.indices.shuffled().prefix(count)).union(focus.shuffled().prefix(5))
        return .hazardIndexBatch(picked.map { drift($0, by: -0.4...0.4) })
    }

    private mutating func drift(_ i: Int, by range: ClosedRange<Double>) -> HazardIndexUpdate {
        let old = sites[i].hazardIndex
        let new = min(10, max(0.5, old + Double.random(in: range))).rounded(toPlaces: 1)
        let ratio = old > 0 ? new / old : 1
        sites[i].hazardIndex = new
        sites[i].factors = sites[i].factors.map {
            HazardFactor(type: $0.type, score: min(10, $0.score * ratio).rounded(toPlaces: 1), detail: $0.detail)
        }
        return HazardIndexUpdate(siteId: sites[i].id, hazardIndex: new, factors: sites[i].factors)
    }

    private func alert() -> RealtimeEvent? {
        guard let i = randomIndex(preferFocus: 0.7),
              let (type, severity, title, message, source) = Self.alertTemplates.randomElement()
        else { return nil }
        let site = sites[i]
        return .alert(HazardAlert(
            id: UUID().uuidString, siteId: site.id, type: type, severity: severity,
            title: title, message: message, issuedAt: .now, acknowledged: false, source: source))
    }

    /// Strikes cluster around stormy sites, usually ones the user is subscribed to.
    private func strike() -> RealtimeEvent? {
        let pool = Bool.random() && !focus.isEmpty ? focus.map { sites[$0] } : sites
        let stormy = pool.filter { ($0.factor(.lightning)?.score ?? 0) >= 4 }
        guard let site = (stormy.isEmpty ? pool : stormy).randomElement() else { return nil }
        return .lightningStrike(LightningStrike(
            siteId: site.id,
            distanceMiles: Double.random(in: 1.5...13).rounded(toPlaces: 1),
            occurredAt: .now,
            direction: MockData.directions.randomElement()))
    }
}
