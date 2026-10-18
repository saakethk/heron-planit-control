import SwiftUI

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var showLocationPicker = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Location", value: store.searchLocation.name)
                    LabeledContent("Home site", value: store.homeSite?.name ?? "–")
                    LabeledContent("Following", value: "\(store.nearbySites.count) nearest of \(store.sites.count) sites")
                    Button("Change location") { showLocationPicker = true }
                } header: {
                    Text("Location")
                } footer: {
                    Text("Alerts and notifications cover your nearest sites. Stop-work and severe sites elsewhere still show on the Sites tab.")
                }

                Section {
                    LabeledContent("Permission", value: store.notificationsAuthorized ? "Allowed" : "Not allowed")
                    if !store.notificationsAuthorized {
                        Button("Enable notifications") {
                            Task { await store.requestNotificationPermission() }
                        }
                    }
                    Toggle("6 PM next-day briefing", isOn: Binding(
                        get: { store.dailyBriefingEnabled },
                        set: { store.setDailyBriefing(enabled: $0) }))
                } header: {
                    Text("Notifications")
                }

                Section {
                    demoButton("Lightning strike at my site", symbol: "bolt.fill", tint: Palette.stopWork) {
                        store.simulateLightningStrike()
                    }
                    demoButton("Heat spike (temperature rise)", symbol: "thermometer.sun.fill", tint: HazardType.heat.color) {
                        store.simulateHeatSpike()
                    }
                    demoButton("Flood / heavy rain", symbol: "drop.fill", tint: HazardType.flood.color) {
                        store.simulateFloodWarning()
                    }
                    demoButton("Next-day briefing", symbol: "sun.horizon.fill", tint: Palette.accent) {
                        store.sendTestBriefing()
                    }
                    demoButton("End lightning holds now", symbol: "checkmark.shield.fill", tint: Palette.live) {
                        store.clearLightningHolds()
                    }
                } header: {
                    Text("Simulate")
                } footer: {
                    Text(simulateFooter)
                }

                if store.usesMockBackend {
                    Section {
                        Toggle("Live simulated feed", isOn: Binding(
                            get: { store.liveFeedEnabled }, set: { store.setLiveFeed($0) }))
                        Toggle("Fast all-clear (60 seconds)", isOn: Binding(
                            get: { store.fastAllClear }, set: { store.setFastAllClear($0) }))
                        Button("Reset demo data", role: .destructive) {
                            Task { await store.resetDemo() }
                        }
                    } header: {
                        Text("Demo mode")
                    } footer: {
                        Text("Turn off the live feed for a scripted demo with no surprise events. Fast all-clear shortens the 30-minute lightning countdown so you can show the all-clear.")
                    }
                }

                Section("Backend") {
                    LabeledContent("Data source", value: store.usesMockBackend ? "Mock data" : "Live API")
                    LabeledContent("Realtime", value: store.connection.label(isMock: store.usesMockBackend))
                    LabeledContent("API", value: AppConfig.apiBaseURL.absoluteString)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Palette.background)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .sheet(isPresented: $showLocationPicker) { LocationPickerView().environment(store) }
        }
    }

    private var simulateFooter: String {
        if let message = store.lastSimulateMessage {
            return message
        }
        if store.usesMockBackend {
            return "Each event updates the screens and posts a notification. To see a notification arrive in the background, trigger the 6 PM briefing and then go to the Home Screen (⇧⌘H in the Simulator)."
        }
        return "These go through the live pipeline: the model rescores your site, alerts are issued, and this device gets a notification. Lightning holds all-clear in 60 seconds. Allow notifications if you have not already."
    }

    private func demoButton(_ title: String, symbol: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label {
                Text(title).foregroundStyle(.white)
            } icon: {
                Image(systemName: symbol).foregroundStyle(tint)
            }
        }
    }
}

#Preview {
    SettingsView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
