import CoreLocation
import Foundation

enum HazardType: String, Codable, CaseIterable, Identifiable, Sendable {
    case lightning
    case flood
    case heat
    case wildfire
    case wildlife
    case soilSaturation = "soil_saturation"
    case other

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .lightning: "Lightning"
        case .flood: "Flooding"
        case .heat: "Extreme Heat"
        case .wildfire: "Wildfire"
        case .wildlife: "Wildlife"
        case .soilSaturation: "Soil Saturation"
        case .other: "Other"
        }
    }

    var shortName: String {
        switch self {
        case .lightning: "Lightning"
        case .flood: "Flood"
        case .heat: "Heat"
        case .wildfire: "Fire"
        case .wildlife: "Wildlife"
        case .soilSaturation: "Soil"
        case .other: "Other"
        }
    }

    var symbol: String {
        switch self {
        case .lightning: "bolt.fill"
        case .flood: "drop.fill"
        case .heat: "thermometer.sun.fill"
        case .wildfire: "flame.fill"
        case .wildlife: "pawprint.fill"
        case .soilSaturation: "square.3.layers.3d.down.right"
        case .other: "exclamationmark.triangle.fill"
        }
    }
}

/// Display bands for the 0-10 Hazard Index. Thresholds are placeholders until
/// the hazard model publishes calibrated cut-offs.
enum RiskLevel: String, CaseIterable, Sendable {
    case low, moderate, high, severe

    init(index: Double) {
        switch index {
        case ..<3: self = .low
        case ..<5.5: self = .moderate
        case ..<8: self = .high
        default: self = .severe
        }
    }

    var label: String { rawValue.capitalized }

    var range: ClosedRange<Double> {
        switch self {
        case .low: 0...3
        case .moderate: 3...5.5
        case .high: 5.5...8
        case .severe: 8...10
        }
    }
}

struct HazardFactor: Codable, Hashable, Identifiable, Sendable {
    let type: HazardType
    /// Contribution of this factor on the same 0-10 scale as the Hazard Index.
    var score: Double
    var detail: String

    var id: HazardType { type }
}

struct IndexPoint: Codable, Hashable, Sendable {
    let time: Date
    let value: Double
}

struct SiteConditions: Codable, Hashable, Sendable {
    var temperatureF: Double
    var heatIndexF: Double
    var windMph: Double
    var rain24hIn: Double
    var soilMoisturePct: Double
    var nearestStrikeMiles: Double?
}

struct Site: Codable, Hashable, Identifiable, Sendable {
    /// EIA plant ID.
    let id: Int
    let name: String
    let county: String
    let latitude: Double
    let longitude: Double
    let capacityMw: Double
    var hazardIndex: Double
    var factors: [HazardFactor]
    var updatedAt: Date
    var conditions: SiteConditions?
    /// Today's index values, oldest first.
    var history: [IndexPoint]?

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var riskLevel: RiskLevel { RiskLevel(index: hazardIndex) }

    var topFactor: HazardFactor? { factors.max { $0.score < $1.score } }

    var sortedFactors: [HazardFactor] { factors.sorted { $0.score > $1.score } }

    /// Change since the first reading of the day.
    var trend: Double? {
        guard let first = history?.first else { return nil }
        return hazardIndex - first.value
    }

    var trendStart: Date? { history?.first?.time }

    func factor(_ type: HazardType) -> HazardFactor? { factors.first { $0.type == type } }
}

enum AlertSeverity: String, Codable, Comparable, Sendable {
    case advisory
    case warning
    case stopWork = "stop_work"

    private var rank: Int {
        switch self {
        case .advisory: 0
        case .warning: 1
        case .stopWork: 2
        }
    }

    var label: String {
        switch self {
        case .advisory: "Advisory"
        case .warning: "Warning"
        case .stopWork: "Stop Work"
        }
    }

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rank < rhs.rank }
}

struct HazardAlert: Codable, Hashable, Identifiable, Sendable {
    let id: String
    let siteId: Int
    let type: HazardType
    let severity: AlertSeverity
    let title: String
    let message: String
    let issuedAt: Date
    /// Per-user read state from the backend.
    var acknowledged: Bool?
    var source: String?
}

struct LightningStrike: Codable, Hashable, Sendable {
    let siteId: Int
    let distanceMiles: Double
    let occurredAt: Date
    /// Compass direction from the site to the strike, e.g. "NE".
    var direction: String?
}

enum LightningPolicy {
    static let stopWorkRadiusMiles = 10.0
    static let allClearInterval: TimeInterval = 30 * 60
    static let demoAllClearInterval: TimeInterval = 60
}

/// Active stop-work hold for a site. Each new strike inside the radius pushes
/// `endsAt` out by a full `allClearInterval`.
struct LightningHold: Codable, Hashable, Identifiable, Sendable {
    let siteId: Int
    let startedAt: Date
    var lastStrikeAt: Date
    var strikeCount: Int
    var closestMiles: Double
    var lastDistanceMiles: Double
    var lastDirection: String?
    var allClearInterval: TimeInterval

    var id: Int { siteId }
    var endsAt: Date { lastStrikeAt.addingTimeInterval(allClearInterval) }

    func remaining(at date: Date) -> TimeInterval { max(0, endsAt.timeIntervalSince(date)) }
}

/// Today's running briefing for one site: what is happening now and what is coming up.
struct SiteBriefing: Codable, Hashable, Sendable {
    struct Event: Codable, Hashable, Identifiable, Sendable {
        let id: String
        let type: HazardType
        let title: String
        let detail: String
        let time: Date
        var isActive: Bool
    }

    let siteId: Int
    var headline: String
    var sources: [String]
    var updatedAt: Date
    var events: [Event]
    var tomorrowOutlook: String
}

/// Next-day report sent at 6 PM.
struct DailyBriefing: Codable, Hashable, Sendable {
    struct Item: Codable, Hashable, Identifiable, Sendable {
        let siteId: Int
        let forecastIndex: Double
        let headline: String

        var id: Int { siteId }
    }

    let forDate: Date
    let summary: String
    let items: [Item]
}

struct HazardReport: Codable, Sendable {
    let id: String
    let siteId: Int?
    let type: HazardType
    let notes: String
    let latitude: Double?
    let longitude: Double?
    let createdAt: Date
    let photoJpeg: Data?
}

/// A submitted report as listed back by the backend.
struct CrewReport: Codable, Hashable, Identifiable, Sendable {
    let id: String
    let siteId: Int?
    let type: HazardType
    let notes: String
    let reporter: String
    let createdAt: Date
    var photoUrl: URL?
}

/// The place the crew is working from. Sites are listed by distance from it.
struct SearchLocation: Codable, Hashable, Sendable {
    var name: String
    var latitude: Double
    var longitude: Double

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var clLocation: CLLocation { CLLocation(latitude: latitude, longitude: longitude) }

    static let gainesville = SearchLocation(name: "Gainesville, FL", latitude: 29.6516, longitude: -82.3248)
}

enum Distance {
    static let metersPerMile = 1609.344

    /// Great-circle distance, not raw latitude/longitude differences: a degree of
    /// longitude in Florida is about 13% shorter than a degree of latitude.
    static func miles(from location: CLLocation, to site: Site) -> Double {
        location.distance(from: CLLocation(latitude: site.latitude, longitude: site.longitude)) / metersPerMile
    }

    static func label(_ miles: Double) -> String {
        miles < 10 ? "\(miles.oneDecimal) mi" : "\(Int(miles.rounded())) mi"
    }
}

struct HazardIndexUpdate: Codable, Hashable, Sendable {
    let siteId: Int
    let hazardIndex: Double
    var factors: [HazardFactor]?
}

/// Messages pushed by the backend over the realtime channel.
/// Wire format: `{"type": "<event_type>", "payload": {...}}`.
enum RealtimeEvent: Sendable {
    case hazardIndexUpdated(siteId: Int, hazardIndex: Double, factors: [HazardFactor]?)
    /// One message per model run, so rescoring every site doesn't send hundreds of messages.
    case hazardIndexBatch([HazardIndexUpdate])
    case alert(HazardAlert)
    case lightningStrike(LightningStrike)
}

extension RealtimeEvent: Decodable {
    private enum CodingKeys: String, CodingKey {
        case type, payload
    }

    private struct BatchPayload: Decodable {
        let updates: [HazardIndexUpdate]
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        switch try container.decode(String.self, forKey: .type) {
        case "hazard_index_updated":
            let update = try container.decode(HazardIndexUpdate.self, forKey: .payload)
            self = .hazardIndexUpdated(siteId: update.siteId, hazardIndex: update.hazardIndex, factors: update.factors)
        case "hazard_index_batch":
            self = .hazardIndexBatch(try container.decode(BatchPayload.self, forKey: .payload).updates)
        case "alert":
            self = .alert(try container.decode(HazardAlert.self, forKey: .payload))
        case "lightning_strike":
            self = .lightningStrike(try container.decode(LightningStrike.self, forKey: .payload))
        case let other:
            throw DecodingError.dataCorruptedError(
                forKey: .type, in: container, debugDescription: "Unknown realtime event type: \(other)")
        }
    }
}

enum JSONCoding {
    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

extension Double {
    func rounded(toPlaces places: Int) -> Double {
        let factor = pow(10, Double(places))
        return (self * factor).rounded() / factor
    }

    var oneDecimal: String { formatted(.number.precision(.fractionLength(1))) }
}
