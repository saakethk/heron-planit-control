import Foundation

enum AppConfig {
    /// Default to live backend unless explicitly overridden in UserDefaults.
    static var useMockBackend: Bool {
        if let mock = UserDefaults.standard.object(forKey: "useMockBackend") as? Bool {
            return mock
        }
        if let live = UserDefaults.standard.object(forKey: "useLiveBackend") as? Bool {
            return !live
        }
        return false
    }

    /// The simulator reaches the backend on `localhost`. On a phone, `localhost` is the
    /// phone itself, so Debug builds use the building Mac's IP address
    /// (`CREWSAFE_DEV_SERVER_HOST` in project.yml). `-apiBaseURL <url>` overrides both.
    static let apiBaseURL: URL = {
        if let override = UserDefaults.standard.string(forKey: "apiBaseURL").flatMap(URL.init(string:)) {
            return override
        }
        #if targetEnvironment(simulator)
        let host = "localhost"
        #else
        let host = UserDefaults.standard.string(forKey: "serverHost")
            ?? (Bundle.main.object(forInfoDictionaryKey: "CrewSafeDevServerHost") as? String)
            .flatMap { $0.isEmpty ? nil : $0 } ?? "10.136.45.252"
        #endif
        return URL(string: "http://\(host):8000/api/v1/")!
    }()

    static var realtimeURL: URL {
        var components = URLComponents(url: apiBaseURL.appending(path: "ws/updates"), resolvingAgainstBaseURL: false)!
        components.scheme = apiBaseURL.scheme == "https" ? "wss" : "ws"
        return components.url!
    }
}
