import SwiftUI

/// Crew-facing home screen: stop-work banner, the crew's site Hazard Index,
/// live conditions, today's briefing timeline, model drivers, and recent alerts.
struct DashboardView: View {
    @Environment(AppStore.self) private var store
    @State private var showSettings = false
    @State private var showSitePicker = false
    @State private var showNextDay = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header

                    if let site = store.homeSite {
                        lightningSection(site)
                        indexCard(site)
                        if let conditions = site.conditions {
                            ConditionsRow(conditions: conditions)
                        }
                        briefingSection
                        driversCard(site)
                    } else if store.isLoading {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
                    }

                    alertsSection

                    if let error = store.loadError {
                        Label(error, systemImage: "wifi.exclamationmark")
                            .font(.footnote)
                            .foregroundStyle(RiskLevel.high.color)
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
                .readableWidth()
            }
            .background(Palette.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refresh() }
            .sheet(isPresented: $showSettings) { SettingsView().environment(store) }
            .sheet(isPresented: $showSitePicker) { SitePickerSheet().environment(store) }
            .sheet(isPresented: $showNextDay) { NextDayBriefingSheet().environment(store) }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Date.now.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()).uppercased())
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Palette.secondaryText)
                Text("Today").font(.largeTitle.weight(.bold))
                Button { showSitePicker = true } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "mappin.circle.fill").foregroundStyle(Palette.accent)
                        Text(store.homeSite.map { "\($0.name) · \($0.county) Co." } ?? "Choose your site")
                            .foregroundStyle(Palette.secondaryText)
                        Image(systemName: "chevron.right").font(.caption2.weight(.bold)).foregroundStyle(Palette.tertiaryText)
                    }
                    .font(.subheadline)
                }
                .buttonStyle(.plain)
                LocationChip().padding(.top, 6)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 10) {
                ConnectionPill(status: store.connection, isMock: store.usesMockBackend)
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape.fill")
                        .font(.body)
                        .foregroundStyle(Palette.secondaryText)
                        .frame(width: 36, height: 36)
                        .background(Palette.card, in: Circle())
                }
                .accessibilityLabel("Settings")
            }
        }
        .padding(.top, 8)
    }

    // MARK: Lightning

    private func lightningSection(_ site: Site) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let holds = store.activeHolds(at: context.date)
            let mine = holds.first { $0.siteId == site.id }
            let others = holds.filter { $0.siteId != site.id && store.isNearby($0.siteId) }
            VStack(spacing: 10) {
                if let mine {
                    StopWorkBanner(hold: mine)
                        .onTapGesture { store.showSite(site.id) }
                }
                if !others.isEmpty {
                    otherHoldsRow(others, now: context.date)
                }
            }
            .animation(.spring, value: holds.map(\.id))
        }
    }

    private func otherHoldsRow(_ holds: [LightningHold], now: Date) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "cloud.bolt.fill").foregroundStyle(Palette.stopWork)
            let names = holds.map { "\(store.siteName(for: $0.siteId)) \($0.remaining(at: now).countdown)" }
            Text("Also on hold: \(Text(names.joined(separator: ", ")).foregroundStyle(.white))")
                .foregroundStyle(Palette.secondaryText)
        }
        .font(.footnote.weight(.medium))
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Palette.stopWork.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .onTapGesture { store.selectedTab = .sites }
    }

    // MARK: Index

    private func indexCard(_ site: Site) -> some View {
        Button { store.showSite(site.id) } label: {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center, spacing: 16) {
                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                        Text(site.hazardIndex.oneDecimal)
                            .font(.system(size: 50, weight: .bold, design: .rounded))
                            .foregroundStyle(site.riskLevel.color)
                            .contentTransition(.numericText(value: site.hazardIndex))
                        Text("/10").font(.title3.weight(.semibold)).foregroundStyle(Palette.tertiaryText)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(site.riskLevel.label) risk").font(.title3.weight(.bold))
                        TrendLabel(site: site)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.footnote.weight(.bold)).foregroundStyle(Palette.tertiaryText)
                }
                RiskBandBar(index: site.hazardIndex)
                Text("Hazard Index · updated \(site.updatedAt.relativeShort)")
                    .font(.caption2)
                    .foregroundStyle(Palette.tertiaryText)
            }
            .card()
        }
        .buttonStyle(.plain)
        .animation(.spring, value: site.hazardIndex)
    }

    // MARK: Briefing

    @ViewBuilder
    private var briefingSection: some View {
        if let briefing = store.homeBriefing {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Briefing") {
                    Text("Updated \(briefing.updatedAt.shortTime)").font(.caption).foregroundStyle(Palette.secondaryText)
                }
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(briefing.headline).font(.headline)
                        Text("From \(briefing.sources.joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(Palette.tertiaryText)
                    }
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(briefing.events.enumerated()), id: \.element.id) { offset, event in
                            BriefingEventRow(event: event, isLast: offset == briefing.events.count - 1)
                        }
                    }
                    Divider().overlay(Palette.stroke)
                    HStack {
                        Image(systemName: "cloud.bolt.rain.fill").foregroundStyle(Palette.secondaryText)
                        Text("Tomorrow: \(briefing.tomorrowOutlook)").font(.subheadline)
                        Spacer()
                        Button { showNextDay = true } label: {
                            HStack(spacing: 3) {
                                Text("6 PM report")
                                Image(systemName: "chevron.right").font(.caption.weight(.bold))
                            }
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Palette.accent)
                        }
                    }
                }
                .card()
                .animation(.default, value: briefing.events.map(\.id))
            }
        }
    }

    // MARK: Drivers

    private func driversCard(_ site: Site) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "What's driving the index") {
                Image(systemName: "sparkles").foregroundStyle(Palette.secondaryText)
            }
            VStack(alignment: .leading, spacing: 16) {
                ForEach(site.sortedFactors) { FactorRow(factor: $0) }
                Text("Factor scores are the model's per-hazard contributions (0-10).")
                    .font(.caption2)
                    .foregroundStyle(Palette.tertiaryText)
            }
            .card()
        }
    }

    // MARK: Alerts

    private var alertsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Recent alerts") {
                Button("See all") { store.selectedTab = .alerts }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Palette.accent)
            }
            VStack(alignment: .leading, spacing: 14) {
                if store.alerts.isEmpty {
                    Text("No alerts right now.").foregroundStyle(Palette.secondaryText)
                } else {
                    let recent = Array(store.alerts.prefix(4))
                    ForEach(recent) { alert in
                        AlertRow(
                            alert: alert, siteName: store.siteName(for: alert.siteId),
                            acknowledged: store.isAcknowledged(alert))
                        .onTapGesture { store.acknowledge(alertId: alert.id) }
                        if alert.id != recent.last?.id { Divider().overlay(Palette.stroke) }
                    }
                }
            }
            .card()
            .animation(.default, value: store.alerts.first?.id)
        }
    }
}

// MARK: - Sheets

/// Home site picker: nearest sites first, farther ones grouped by distance, all searchable.
struct SitePickerSheet: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    var body: some View {
        let all = store.sitesByDistance.filter {
            search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) || $0.county.localizedCaseInsensitiveContains(search)
        }
        let nearby = search.isEmpty ? Array(all.prefix(AppStore.nearbyCount)) : all
        NavigationStack {
            List {
                Section {
                    ForEach(nearby) { row($0) }
                } header: {
                    Text(search.isEmpty ? "Nearest to \(store.searchLocation.name)" : "\(all.count) matches")
                }
                if search.isEmpty {
                    ForEach(store.fartherBands(from: Array(all.dropFirst(AppStore.nearbyCount)))) { band in
                        Section(band.title) {
                            ForEach(band.sites) { row($0) }
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Palette.background)
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search sites")
            .navigationTitle("My site")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func row(_ site: Site) -> some View {
        Button {
            store.setHomeSite(site.id)
            dismiss()
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(site.name).font(.body.weight(.medium)).foregroundStyle(.white)
                    Text([store.distance(to: site.id).map(Distance.label), "\(site.county) County", "\(site.capacityMw.formatted()) MW"]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(.caption)
                        .foregroundStyle(Palette.secondaryText)
                }
                Spacer()
                if site.id == store.homeSiteId {
                    Image(systemName: "checkmark").foregroundStyle(Palette.accent)
                }
                RiskBadge(index: site.hazardIndex)
            }
        }
        .listRowBackground(Palette.card)
    }
}

struct NextDayBriefingSheet: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                if let briefing = store.nextDayBriefing {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(briefing.forDate.formatted(.dateTime.weekday(.wide).month(.wide).day()))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Palette.secondaryText)
                        Text(briefing.summary).font(.title3.weight(.semibold))
                        VStack(alignment: .leading, spacing: 14) {
                            Text("Highest forecast risk").font(.headline)
                            ForEach(briefing.items) { item in
                                HStack(spacing: 12) {
                                    RiskBadge(index: item.forecastIndex)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(store.siteName(for: item.siteId)).font(.subheadline.weight(.semibold))
                                        Text(item.headline).font(.caption).foregroundStyle(Palette.secondaryText)
                                    }
                                }
                            }
                        }
                        .card()
                        Label("Sent daily at 6 PM. Forecast index uses tomorrow's weather in the hazard model.",
                              systemImage: "clock")
                            .font(.caption)
                            .foregroundStyle(Palette.tertiaryText)
                    }
                    .padding()
                } else {
                    ProgressView().padding(.top, 60)
                }
            }
            .background(Palette.background)
            .navigationTitle("Tomorrow's briefing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

#Preview {
    DashboardView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
