import SwiftUI

struct SiteDetailView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let siteId: Int

    var body: some View {
        NavigationStack {
            ScrollView {
                if let site = store.site(id: siteId) {
                    content(site)
                        .padding(.horizontal)
                        .padding(.bottom, 24)
                        .readableWidth()
                } else {
                    ContentUnavailableView("Site not found", systemImage: "mappin.slash")
                }
            }
            .background(Palette.background)
            .navigationTitle(store.siteName(for: siteId))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .task { await store.loadBriefing(siteId: siteId) }
        }
        .presentationDetents([.large])
    }

    @ViewBuilder
    private func content(_ site: Site) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 18) {
                HazardGauge(index: site.hazardIndex, size: 96)
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(site.riskLevel.label) risk").font(.title2.weight(.bold))
                    TrendLabel(site: site)
                    Text(siteLine(site))
                        .font(.caption)
                        .foregroundStyle(Palette.tertiaryText)
                    if store.homeSiteId == site.id {
                        Label("My site", systemImage: "checkmark.circle.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Palette.accent)
                    }
                }
            }
            .padding(.top, 8)

            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let hold = store.activeHold(for: site.id, at: context.date) {
                    StopWorkBanner(hold: hold)
                }
            }

            if let history = site.history, history.count > 1 {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Today") {
                        Text("Hazard Index").font(.caption).foregroundStyle(Palette.secondaryText)
                    }
                    IndexSparkline(points: history, color: site.riskLevel.color)
                        .frame(height: 112)
                        .card()
                }
            }

            if let conditions = site.conditions {
                ConditionsRow(conditions: conditions)
            }

            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Model factors")
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(Array(site.sortedFactors.prefix(4))) { FactorRow(factor: $0) }
                }
                .card()
            }

            if let briefing = store.siteBriefings[site.id] {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Briefing") {
                        Text("Updated \(briefing.updatedAt.shortTime)").font(.caption).foregroundStyle(Palette.secondaryText)
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        Text(briefing.headline).font(.headline)
                        VStack(alignment: .leading, spacing: 0) {
                            let events = Array(briefing.events.prefix(3))
                            ForEach(Array(events.enumerated()), id: \.element.id) { offset, event in
                                BriefingEventRow(event: event, isLast: offset == events.count - 1)
                            }
                        }
                    }
                    .card()
                }
            }

            let alerts = store.alerts(for: site.id)
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Alerts") {
                    Text("\(alerts.count)").font(.subheadline).foregroundStyle(Palette.secondaryText)
                }
                VStack(alignment: .leading, spacing: 14) {
                    if alerts.isEmpty {
                        Text("No alerts for this site.").foregroundStyle(Palette.secondaryText)
                    }
                    ForEach(alerts.prefix(3)) { alert in
                        AlertRow(alert: alert, siteName: site.name, acknowledged: store.isAcknowledged(alert))
                    }
                }
                .card()
            }

            let reports = store.reports(for: site.id)
            if !reports.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Crew reports")
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(reports) { CrewReportRow(report: $0, siteName: nil, photo: store.localReportThumbnails[$0.id]) }
                    }
                    .card()
                }
            }

            VStack(spacing: 10) {
                if store.homeSiteId != site.id {
                    Button {
                        store.setHomeSite(site.id)
                    } label: {
                        Label("Set as my site", systemImage: "mappin.and.ellipse").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
                Button {
                    store.simulateLightningStrike(siteId: site.id)
                } label: {
                    Label("Simulate lightning strike", systemImage: "bolt.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(Palette.stopWork)
                .controlSize(.large)
            }

            Text("EIA plant \(site.id) · \(site.latitude.formatted()), \(site.longitude.formatted())")
                .font(.caption2)
                .foregroundStyle(Palette.tertiaryText)
                .frame(maxWidth: .infinity)
        }
    }

    private func siteLine(_ site: Site) -> String {
        var parts = ["\(site.county) County", "\(site.capacityMw.formatted()) MW"]
        if let zone = site.floodZone, !zone.isEmpty {
            parts.append("FEMA \(zone)")
        }
        return parts.joined(separator: " · ")
    }
}

#Preview {
    let store = AppStore.makeDefault()
    return SiteDetailView(siteId: MockData.gainesvilleSiteId)
        .environment(store)
        .task { await store.refresh() }
        .preferredColorScheme(.dark)
}
