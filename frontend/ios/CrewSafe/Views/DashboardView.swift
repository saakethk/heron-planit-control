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
                        briefingSection
                        indexCard(site)
                        if let conditions = site.conditions {
                            SiteWeatherCard(site: site, conditions: conditions)
                        }
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
                .padding(.bottom, 28)
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
        VStack(spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Date.now.formatted(.dateTime.weekday(.wide).month(.abbreviated).day()).uppercased())
                        .font(.system(size: 11, weight: .bold))
                        .tracking(0.8)
                        .foregroundStyle(Palette.secondaryText)
                    Text("Jobsite Safety")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(.white)
                }

                Spacer()

                HStack(spacing: 8) {
                    ConnectionPill(status: store.connection, isMock: store.usesMockBackend)

                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.85))
                            .frame(width: 34, height: 34)
                            .background(Palette.card, in: Circle())
                            .overlay(Circle().stroke(Palette.cardBorder, lineWidth: 1))
                    }
                    .accessibilityLabel("Settings")
                }
            }

            // Location Bar Pill
            Button { showSitePicker = true } label: {
                HStack(spacing: 8) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Palette.accent)

                    Text(store.homeSite.map { "\($0.name) · \($0.county) Co." } ?? "Select Monitored Jobsite")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white)
                        .lineLimit(1)

                    Spacer(minLength: 4)

                    Text("Change")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Palette.accent)

                    Image(systemName: "chevron.right")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Palette.tertiaryText)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Palette.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Palette.cardBorder, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
        .padding(.top, 4)
    }

    // MARK: Lightning

    private func lightningSection(_ site: Site) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let holds = store.activeHolds(at: context.date)
            let mine = holds.first { $0.siteId == site.id }
            let others = holds.filter { $0.siteId != site.id && store.isNearby($0.siteId) }
            VStack(spacing: 10) {
                if let mine {
                    StopWorkBanner(hold: mine, siteName: site.name)
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
        HStack(spacing: 10) {
            Image(systemName: "cloud.bolt.fill")
                .foregroundStyle(Palette.stopWork)
            let shown = Array(holds.prefix(2))
            let names = shown.map { "\(store.siteName(for: $0.siteId)) \($0.remaining(at: now).countdown)" }
            let extra = holds.count > 2 ? " +\(holds.count - 2) more" : ""
            Text("Also on hold: \(Text(names.joined(separator: ", ")).foregroundStyle(.white))\(extra)")
                .foregroundStyle(Palette.secondaryText)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption2.weight(.bold))
                .foregroundStyle(Palette.tertiaryText)
        }
        .font(.footnote.weight(.medium))
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(Palette.stopWork.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Palette.stopWork.opacity(0.25), lineWidth: 1)
        )
        .onTapGesture { store.selectedTab = .sites }
    }

    // MARK: Index

    private func indexCard(_ site: Site) -> some View {
        Button { store.showSite(site.id) } label: {
            VStack(alignment: .leading, spacing: 16) {
                // Top row: Label + Status Pill
                HStack(alignment: .center) {
                    HStack(spacing: 6) {
                        Image(systemName: "gauge.with.dots.needle.67percent")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(site.riskLevel.color)
                        Text("COMPOSITE HAZARD INDEX")
                            .font(.system(size: 11, weight: .bold))
                            .tracking(0.6)
                            .foregroundStyle(Palette.secondaryText)
                    }

                    Spacer()

                    RiskBadge(index: site.hazardIndex, large: false)
                }

                // Middle Hero Number & Status
                HStack(alignment: .center, spacing: 16) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(site.hazardIndex.oneDecimal)
                            .font(.system(size: 54, weight: .heavy, design: .rounded))
                            .foregroundStyle(site.riskLevel.color)
                            .contentTransition(.numericText(value: site.hazardIndex))
                        Text("/ 10")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(Palette.tertiaryText)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(site.riskLevel.label) Hazard")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(.white)
                        TrendLabel(site: site)
                    }

                    Spacer(minLength: 0)

                    Image(systemName: "chevron.right")
                        .font(.footnote.weight(.bold))
                        .foregroundStyle(Palette.tertiaryText)
                }

                // Visual progress bar
                RiskBandBar(index: site.hazardIndex)

                // Footer metadata
                HStack {
                    Label("Model inference · updated \(site.updatedAt.relativeShort)", systemImage: "clock")
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)

                    Spacer()

                    Text("View Site Details →")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Palette.accent)
                }
            }
            .card(padding: 18, cornerRadius: 20)
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
                        let events = Array(briefing.events.prefix(3))
                        ForEach(Array(events.enumerated()), id: \.element.id) { offset, event in
                            BriefingEventRow(event: event, isLast: offset == events.count - 1)
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
            SectionHeader(title: "Drivers") {
                Image(systemName: "sparkles").foregroundStyle(Palette.secondaryText)
            }
            VStack(alignment: .leading, spacing: 14) {
                ForEach(Array(site.sortedFactors.prefix(3))) { FactorRow(factor: $0) }
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
                    let recent = Array(store.alerts.prefix(3))
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
