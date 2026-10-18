import SwiftUI

struct RootView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        @Bindable var store = store

        TabView(selection: $store.selectedTab) {
            DashboardView()
                .tabItem { Label("Today", systemImage: "gauge.with.dots.needle.67percent") }
                .tag(AppTab.dashboard)

            SitesView()
                .tabItem { Label("Sites", systemImage: "map.fill") }
                .tag(AppTab.sites)

            AlertsView()
                .tabItem { Label("Alerts", systemImage: "bell.fill") }
                .badge(store.unacknowledgedCount)
                .tag(AppTab.alerts)

            ReportHazardView()
                .tabItem { Label("Report", systemImage: "camera.fill") }
                .tag(AppTab.report)
        }
        .tint(Palette.accent)
        .sheet(item: $store.presentedSite) { sheet in
            SiteDetailView(siteId: sheet.id).environment(store)
        }
        .sheet(isPresented: $store.needsLocationChoice) {
            LocationPickerView(isOnboarding: true).environment(store)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { BackgroundRefresh.schedule() }
        }
    }
}

#Preview {
    RootView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
