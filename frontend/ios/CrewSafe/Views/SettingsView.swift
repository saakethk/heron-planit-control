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
                    Button("Send test briefing notification") {
                        store.sendTestBriefing()
                    }
                } header: {
                    Text("Notifications")
                } footer: {
                    Text("Daily briefings notify at 6 PM. Tap 'Send test briefing notification' to preview the notification on your phone.")
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
}

#Preview {
    SettingsView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
