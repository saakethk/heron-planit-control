import SwiftUI
import UIKit

@main
struct CrewSafeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var store = AppStore.makeDefault()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .preferredColorScheme(.dark)
                .task {
                    #if DEBUG
                    // Launch arguments for demos and screenshots:
                    // `-initialTab sites`, `-showSite 617`, `-skipNotificationPrompt YES`,
                    // `-chooseLocation YES` (show first-launch location setup) or `-chooseLocation NO`,
                    // `-location Miami` (any city in the location picker).
                    let defaults = UserDefaults.standard
                    if let city = defaults.string(forKey: "location"),
                       let preset = LocationPickerView.presets.first(where: { $0.name.hasPrefix(city) }) {
                        store.setLocation(preset)
                    }
                    if defaults.bool(forKey: "skipNotificationPrompt") {
                        store.promptsForNotificationsOnStart = false
                    }
                    if defaults.object(forKey: "chooseLocation") != nil {
                        store.needsLocationChoice = defaults.bool(forKey: "chooseLocation")
                    }
                    if let tab = defaults.string(forKey: "initialTab").flatMap(AppTab.init(rawValue:)) {
                        store.selectedTab = tab
                    }
                    if defaults.integer(forKey: "showSite") != 0 {
                        let siteId = defaults.integer(forKey: "showSite")
                        Task {
                            try? await Task.sleep(for: .seconds(1))
                            store.showSite(siteId)
                        }
                    }
                    #endif
                    appDelegate.onDeviceToken = { [store] token in
                        Task { await store.registerDevice(apnsToken: token) }
                    }
                    await store.start()
                }
        }
        .backgroundTask(.appRefresh(BackgroundRefresh.identifier)) { [store] in
            await store.performBackgroundRefresh()
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    var onDeviceToken: ((String) -> Void)?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        NotificationManager.shared.configure()
        // Fails until the Push Notifications capability is added (requires a paid
        // Apple Developer account). Local notifications work either way.
        application.registerForRemoteNotifications()
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        print("APNs token: \(token)")
        onDeviceToken?(token)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("APNs registration unavailable: \(error.localizedDescription)")
    }
}
