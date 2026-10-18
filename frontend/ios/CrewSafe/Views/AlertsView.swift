import SwiftUI

struct AlertsView: View {
    enum Filter: String, CaseIterable {
        case all = "All"
        case unread = "Unread"
        case stopWork = "Stop work"
        case mySite = "My site"
    }

    @Environment(AppStore.self) private var store
    @State private var filter: Filter = .all

    private func matches(_ alert: HazardAlert, _ filter: Filter) -> Bool {
        switch filter {
        case .all: true
        case .unread: !store.isAcknowledged(alert)
        case .stopWork: alert.severity == .stopWork
        case .mySite: alert.siteId == store.homeSiteId
        }
    }

    private func sections(_ filtered: [HazardAlert]) -> [(title: String, alerts: [HazardAlert])] {
        let calendar = Calendar.current
        let today = filtered.filter { calendar.isDateInToday($0.issuedAt) }
        let earlier = filtered.filter { !calendar.isDateInToday($0.issuedAt) }
        return [("Today", today), ("Earlier", earlier)].filter { !$0.alerts.isEmpty }
    }

    var body: some View {
        let filtered = store.alerts.filter { matches($0, filter) }
        NavigationStack {
            List {
                Section {
                    header
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 4, trailing: 16))
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                }

                ForEach(sections(filtered), id: \.title) { section in
                    Section {
                        ForEach(section.alerts) { alert in
                            row(alert)
                        }
                    } header: {
                        Text(section.title.uppercased())
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Palette.secondaryText)
                    }
                }
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .background(Palette.background.ignoresSafeArea())
            .overlay {
                if filtered.isEmpty {
                    ContentUnavailableView(
                        "No alerts", systemImage: "bell.slash", description: Text("You're all caught up."))
                        .padding(.top, 140)
                }
            }
            .animation(.default, value: filtered.map(\.id))
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refresh() }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("Alerts").font(.title.weight(.bold))
                Spacer()
                Button("Mark all read") { store.acknowledgeAll() }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(store.unacknowledgedCount == 0 ? Palette.tertiaryText : Palette.accent)
                    .disabled(store.unacknowledgedCount == 0)
                    .buttonStyle(.plain)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Filter.allCases, id: \.self) { option in
                        let count = store.alerts.filter { matches($0, option) }.count
                        FilterChip(
                            title: option == .all ? option.rawValue : "\(option.rawValue) \(count)",
                            isSelected: filter == option
                        ) { filter = option }
                    }
                }
            }
        }
    }

    private func row(_ alert: HazardAlert) -> some View {
        let acknowledged = store.isAcknowledged(alert)
        return Button {
            store.acknowledge(alertId: alert.id)
            store.showSite(alert.siteId)
        } label: {
            AlertRow(alert: alert, siteName: store.siteName(for: alert.siteId), acknowledged: acknowledged)
                .padding(14)
                .background(
                    alert.severity == .stopWork && !acknowledged ? Palette.stopWork.opacity(0.1) : Palette.card,
                    in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(alignment: .leading) {
                    if !acknowledged {
                        UnevenRoundedRectangle(topLeadingRadius: 16, bottomLeadingRadius: 16, style: .continuous)
                            .fill(alert.severity.color)
                            .frame(width: 4)
                    }
                }
                .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Mark as read", systemImage: "checkmark") { store.acknowledge(alertId: alert.id) }
            Button("View site", systemImage: "mappin.and.ellipse") { store.showSite(alert.siteId) }
        }
        .swipeActions {
            if !acknowledged {
                Button("Read", systemImage: "checkmark") { store.acknowledge(alertId: alert.id) }
                    .tint(Palette.live)
            }
        }
        .listRowInsets(EdgeInsets(top: 5, leading: 16, bottom: 5, trailing: 16))
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
    }
}

#Preview {
    AlertsView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
