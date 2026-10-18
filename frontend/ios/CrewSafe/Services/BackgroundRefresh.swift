import BackgroundTasks
import Foundation

enum BackgroundRefresh {
    /// Must match `BGTaskSchedulerPermittedIdentifiers` in `project.yml`.
    static let identifier = "com.swamphacks.crewsafe.refresh"

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
