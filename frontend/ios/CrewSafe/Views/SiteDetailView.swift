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
        VStack(alignment: .leading, spacing: 18) {
            // Hero Gauge Card
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .center, spacing: 18) {
                    HazardGauge(index: site.hazardIndex, size: 92)

                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 6) {
                            Text("\(site.riskLevel.label) Hazard")
                                .font(.title3.weight(.bold))
                                .foregroundStyle(.white)
                            if store.homeSiteId == site.id {
                                Image(systemName: "checkmark.seal.fill")
                                    .font(.subheadline)
                                    .foregroundStyle(Palette.accent)
                            }
                        }

                        TrendLabel(site: site)

                        Text(siteLine(site))
                            .font(.caption)
                            .foregroundStyle(Palette.secondaryText)
                    }
                    Spacer()
                }

                RiskBandBar(index: site.hazardIndex)
            }
            .card(padding: 18, cornerRadius: 20)
            .padding(.top, 4)

            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let hold = store.activeHold(for: site.id, at: context.date) {
                    StopWorkBanner(hold: hold, siteName: site.name)
                }
            }

            if let history = site.history, history.count > 1 {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Today's Trend") {
                        Text("Hourly Inference").font(.caption).foregroundStyle(Palette.secondaryText)
                    }
                    IndexSparkline(points: history, color: site.riskLevel.color)
                        .frame(height: 112)
                        .card()
                }
            }

            if let conditions = site.conditions {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Live Meteorological Telemetry")
                    ConditionsRow(conditions: conditions)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Model Risk Factors")
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(Array(site.sortedFactors.prefix(4))) { FactorRow(factor: $0) }
                }
                .card()
            }

            if let briefing = store.siteBriefings[site.id] {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeader(title: "Site Briefing") {
                        Text("Updated \(briefing.updatedAt.shortTime)").font(.caption).foregroundStyle(Palette.secondaryText)
                    }
                    VStack(alignment: .leading, spacing: 14) {
                        Text(briefing.headline)
                            .font(.headline)
                            .foregroundStyle(.white)
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
                SectionHeader(title: "Site Alerts") {
                    Text("\(alerts.count)").font(.subheadline).foregroundStyle(Palette.secondaryText)
                }
                VStack(alignment: .leading, spacing: 14) {
                    if alerts.isEmpty {
                        Text("No active alerts for this facility.")
                            .font(.footnote)
                            .foregroundStyle(Palette.secondaryText)
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
                    SectionHeader(title: "Crew Incident Reports")
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(reports) { CrewReportRow(report: $0, siteName: nil, photo: store.localReportThumbnails[$0.id]) }
                    }
                    .card()
                }
            }

            VStack(spacing: 12) {
                if store.homeSiteId != site.id {
                    Button {
                        store.setHomeSite(site.id)
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "mappin.and.ellipse")
                            Text("Set as My Primary Site")
                        }
                        .font(.headline)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Palette.accentGradient, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                    }
                    .buttonStyle(.plain)
                }

                Button {
                    store.simulateLightningStrike(siteId: site.id)
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "bolt.fill")
                        Text("Simulate Lightning (Stop Work)")
                    }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Palette.stopWork)
                    .frame(maxWidth: .infinity)
                    .frame(height: 48)
                    .background(Palette.stopWork.opacity(0.12), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 15, style: .continuous)
                            .stroke(Palette.stopWork.opacity(0.3), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 4)

            Text("EIA Plant ID \(site.id) · \(site.latitude.rounded(toPlaces: 4)), \(site.longitude.rounded(toPlaces: 4))")
                .font(.caption2)
                .foregroundStyle(Palette.tertiaryText)
                .frame(maxWidth: .infinity)
                .padding(.top, 4)
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
