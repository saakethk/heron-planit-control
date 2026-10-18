import Foundation
import UserNotifications

/// Wraps local notification scheduling and handles taps and actions on notifications.
/// Remote (APNs) pushes from the backend use the same categories and `userInfo` keys,
/// so they are handled by the same delegate code.
@MainActor
final class NotificationManager: NSObject {
    static let shared = NotificationManager()

    enum Category {
        static let hazardAlert = "HAZARD_ALERT"
        static let lightningHold = "LIGHTNING_HOLD"
        static let dailyBriefing = "DAILY_BRIEFING"
    }

    enum Action {
        static let acknowledge = "ACKNOWLEDGE"
    }

    enum Identifier {
        static let dailyBriefing = "daily-briefing"
        static func allClear(siteId: Int) -> String { "lightning-all-clear-\(siteId)" }
    }

    var onAcknowledge: ((String) -> Void)?
    var onOpen: ((AppTab) -> Void)?

    private let center = UNUserNotificationCenter.current()

    /// Must run in `application(_:didFinishLaunchingWithOptions:)` so a tap that
    /// launches the app is delivered to the delegate.
    func configure() {
        center.delegate = self
        let acknowledge = UNNotificationAction(
            identifier: Action.acknowledge, title: "Acknowledge", options: [.authenticationRequired])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: Category.hazardAlert, actions: [acknowledge], intentIdentifiers: []),
            UNNotificationCategory(identifier: Category.lightningHold, actions: [acknowledge], intentIdentifiers: []),
            UNNotificationCategory(identifier: Category.dailyBriefing, actions: [], intentIdentifiers: []),
        ])
    }

    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    func post(alert: HazardAlert, siteName: String) {
        let content = UNMutableNotificationContent()
        content.title = alert.title
        content.subtitle = siteName
        content.body = alert.message
        content.sound = .default
        content.categoryIdentifier = Category.hazardAlert
        content.threadIdentifier = "site-\(alert.siteId)"
        content.interruptionLevel = alert.severity >= .warning ? .timeSensitive : .active
        content.userInfo = ["alert_id": alert.id, "site_id": alert.siteId]
        add(id: alert.id, content: content, trigger: nil)
    }

    /// Posts the stop-work notification and (re)schedules the all-clear. Reusing the
    /// all-clear identifier replaces the pending request, which restarts the countdown.
    func postLightningHold(alertId: String, siteId: Int, siteName: String, strike: LightningStrike, endsAt: Date, isReset: Bool) {
        let allClearTime = endsAt.formatted(date: .omitted, time: .shortened)

        let hold = UNMutableNotificationContent()
        hold.title = isReset ? "Lightning hold extended" : "STOP WORK: Lightning"
        hold.subtitle = siteName
        let direction = strike.direction.map { " \($0)" } ?? ""
        hold.body = "Strike \(strike.distanceMiles.formatted()) mi\(direction) of site. Shelter now. All clear at \(allClearTime) if there are no more strikes."
        hold.sound = .default
        hold.categoryIdentifier = Category.lightningHold
        hold.threadIdentifier = "site-\(siteId)"
        hold.interruptionLevel = .timeSensitive
        hold.userInfo = ["alert_id": alertId, "site_id": siteId]
        add(id: "lightning-\(siteId)-\(Int(strike.occurredAt.timeIntervalSince1970))", content: hold, trigger: nil)

        scheduleAllClear(siteId: siteId, siteName: siteName, at: endsAt)
    }

    func scheduleAllClear(siteId: Int, siteName: String, at endsAt: Date) {
        let allClear = UNMutableNotificationContent()
        allClear.title = "All clear: \(siteName)"
        allClear.body = "No lightning within \(Int(LightningPolicy.stopWorkRadiusMiles)) mi since the last strike. Work may resume."
        allClear.sound = .default
        allClear.threadIdentifier = "site-\(siteId)"
        allClear.interruptionLevel = .timeSensitive
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: max(1, endsAt.timeIntervalSinceNow), repeats: false)
        add(id: Identifier.allClear(siteId: siteId), content: allClear, trigger: trigger)
    }

    func cancelAllClear(siteId: Int) {
        center.removePendingNotificationRequests(withIdentifiers: [Identifier.allClear(siteId: siteId)])
    }

    /// Repeating local notification at 18:00. The backend can send the same briefing
    /// as a push; this local version keeps working when the device is offline.
    func scheduleDailyBriefing(summary: String?, hour: Int = 18) {
        var components = DateComponents()
        components.hour = hour
        components.minute = 0
        add(
            id: Identifier.dailyBriefing,
            content: briefingContent(summary: summary),
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: true))
    }

    func cancelDailyBriefing() {
        center.removePendingNotificationRequests(withIdentifiers: [Identifier.dailyBriefing])
    }

    func sendTestBriefing(summary: String?, after seconds: TimeInterval = 5) {
        add(
            id: "test-briefing-\(UUID().uuidString)",
            content: briefingContent(summary: summary),
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: seconds, repeats: false))
    }

    private func briefingContent(summary: String?) -> UNMutableNotificationContent {
        let content = UNMutableNotificationContent()
        content.title = "Tomorrow's safety briefing"
        content.body = summary ?? "Your next-day hazard outlook is ready. Review site risks before tomorrow's shift."
        content.sound = .default
        content.categoryIdentifier = Category.dailyBriefing
        return content
    }

    private func add(id: String, content: UNNotificationContent, trigger: UNNotificationTrigger?) {
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger)) { error in
            if let error { print("Failed to schedule notification \(id): \(error)") }
        }
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse
    ) async {
        let content = response.notification.request.content
        let action = response.actionIdentifier
        let category = content.categoryIdentifier
        let alertId = content.userInfo["alert_id"] as? String

        await MainActor.run {
            if action == Action.acknowledge, let alertId {
                onAcknowledge?(alertId)
            } else if category == Category.dailyBriefing {
                onOpen?(.dashboard)
            } else {
                onOpen?(.alerts)
            }
        }
    }
}
