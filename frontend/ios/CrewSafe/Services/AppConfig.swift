import Foundation

enum AppConfig {
    /// Mock data unless launched with `-useLiveBackend YES` (backend in `backend/`).
    static let useMockBackend = !UserDefaults.standard.bool(forKey: "useLiveBackend")

    /// The simulator reaches the backend on `localhost`. On a phone, `localhost` is the
    /// phone itself, so Debug builds use the building Mac's `<name>.local` address
    /// (`CREWSAFE_DEV_SERVER_HOST` in project.yml). `-apiBaseURL <url>` overrides both.
    static let apiBaseURL: URL = {
        if let override = UserDefaults.standard.string(forKey: "apiBaseURL").flatMap(URL.init(string:)) {
            return override
        }
        #if targetEnvironment(simulator)
        let host = "localhost"
        #else
        let host = (Bundle.main.object(forInfoDictionaryKey: "CrewSafeDevServerHost") as? String)
            .flatMap { $0.isEmpty ? nil : $0 } ?? "localhost"
        #endif
        return URL(string: "http://\(host):8000/api/v1/")!
    }()

    static var realtimeURL: URL {
        var components = URLComponents(url: apiBaseURL.appending(path: "ws/updates"), resolvingAgainstBaseURL: false)!
        components.scheme = apiBaseURL.scheme == "https" ? "wss" : "ws"
        return components.url!
    }
}
