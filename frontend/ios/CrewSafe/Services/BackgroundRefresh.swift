import BackgroundTasks
import Foundation

enum BackgroundRefresh {
    /// Must match `BGTaskSchedulerPermittedIdentifiers` in `Info.plist`.
    static let identifier: String = {
        let base = Bundle.main.bundleIdentifier ?? "com.swamphacks.crewsafe"
        return "\(base).refresh"
    }()

    /// iOS decides when the task actually runs; `earliestBeginDate` is only a lower bound.
    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("Could not schedule background refresh: \(error)")
        }
    }
}
