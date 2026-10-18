import MapKit
import SwiftUI

/// Map and list of sites. "Nearby" shows the closest sites to the chosen location, with
/// farther sites in collapsible distance groups; "Statewide" ranks every site by risk.
struct SitesView: View {
    enum Scope: String, CaseIterable {
        case nearby = "Nearby"
        case statewide = "Statewide"
    }

    enum Filter: Hashable {
        case all
        case hazard(HazardType)
    }

    enum Sort: String, CaseIterable {
        case distance = "Distance"
        case risk = "Hazard Index"
        case rising = "Rising fastest"
        case name = "Name"
    }

    private static let florida = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 28.5, longitude: -83.6),
        span: MKCoordinateSpan(latitudeDelta: 6.6, longitudeDelta: 6.6))
    private static let filterTypes: [HazardType] = [.lightning, .flood, .heat, .wildfire]
    /// Full pins at most; everything else is drawn as a small dot.
    private static let maxPins = 25

    @Environment(AppStore.self) private var store
    @State private var scope: Scope = .nearby
    @State private var filter: Filter = .all
    @State private var search = ""
    @State private var sort: Sort = .distance
    @State private var selectedId: Int?
    @State private var panelExpanded = false
    @State private var satellite = false
    @State private var camera: MapCameraPosition = .region(Self.florida)
    @State private var compactPins = true
    @State private var visibleRegion: MKCoordinateRegion?
    @State private var expandedBands: Set<String> = []
    @State private var hasFitCamera = false

    /// What the panel and map show for the current scope, filter, and search.
    private struct Listing {
        var title: String
        var primary: [Site]
        var bands: [DistanceBand]
        var pins: [Site]
        var dots: [Site]
    }

    private func matches(_ site: Site) -> Bool {
        let matchesFilter = switch filter {
        case .all: true
        case .hazard(.lightning): store.activeHold(for: site.id) != nil || (site.factor(.lightning)?.score ?? 0) >= 4
        case .hazard(let type): (site.factor(type)?.score ?? 0) >= 4
        }
        guard matchesFilter else { return false }
        return search.isEmpty
            || site.name.localizedCaseInsensitiveContains(search)
            || site.county.localizedCaseInsensitiveContains(search)
    }

    private func sorted(_ sites: [Site]) -> [Site] {
        switch sort {
        case .distance: sites.sorted { (store.distance(to: $0.id) ?? 0) < (store.distance(to: $1.id) ?? 0) }
        case .risk: sites.sorted { $0.hazardIndex > $1.hazardIndex }
        case .rising: sites.sorted { ($0.trend ?? 0) > ($1.trend ?? 0) }
        case .name: sites.sorted { $0.name < $1.name }
        }
    }

    private func makeListing() -> Listing {
        let byDistance = store.sitesByDistance.filter(matches)
        let primary: [Site]
        var bands: [DistanceBand] = []
        let title: String

        if !search.isEmpty {
            primary = sorted(byDistance)
            title = "\(primary.count) \(primary.count == 1 ? "match" : "matches")"
        } else if scope == .nearby {
            let nearbyIds = Set(store.siteIdsByDistance.prefix(AppStore.nearbyCount))
            primary = sorted(byDistance.filter { nearbyIds.contains($0.id) })
            bands = store.fartherBands(from: byDistance.filter { !nearbyIds.contains($0.id) })
            title = filter == .all ? "Nearest \(primary.count) sites" : "\(panelFilterName) near you"
        } else {
            primary = sorted(byDistance)
            title = filter == .all ? "All \(primary.count) sites" : "\(panelFilterName) statewide"
        }

        var pins = scope == .statewide && search.isEmpty
            ? Array(byDistance.sorted { $0.hazardIndex > $1.hazardIndex }.prefix(Self.maxPins))
            : Array(primary.prefix(Self.maxPins))
        if let selectedId, !pins.contains(where: { $0.id == selectedId }), let selected = store.site(id: selectedId) {
            pins.append(selected)
        }
        let pinIds = Set(pins.map(\.id))
        let dots = byDistance.filter { !pinIds.contains($0.id) && isOnScreen($0) }
        return Listing(title: title, primary: primary, bands: bands, pins: pins, dots: dots)
    }

    /// Dots outside the visible map (plus a margin) aren't drawn, which keeps panning smooth.
    private func isOnScreen(_ site: Site) -> Bool {
        guard let region = visibleRegion else { return true }
        let lat = region.span.latitudeDelta * 0.75
        let lon = region.span.longitudeDelta * 0.75
        return abs(site.latitude - region.center.latitude) <= lat && abs(site.longitude - region.center.longitude) <= lon
    }

    private var panelFilterName: String {
        if case .hazard(let type) = filter { return "\(type.displayName) risk" }
        return "Sites"
    }

    var body: some View {
        NavigationStack {
            let listing = makeListing()
            let holds = store.activeHolds().compactMap { store.site(id: $0.siteId) }
            ZStack(alignment: .bottom) {
                map(listing, holdSites: holds)
                    .ignoresSafeArea()
                VStack(spacing: 8) {
                    Spacer(minLength: 0)
                    mapFooter(showsRadius: !holds.isEmpty)
                        .padding(.horizontal, 14)
                    rankedPanel(listing)
                        .containerRelativeFrame(.vertical, alignment: .bottom) { height, _ in
                            panelHeight(for: height)
                        }
                }
                .ignoresSafeArea(edges: .bottom)
            }
            .safeAreaInset(edge: .top, spacing: 8) { topControls }
            .animation(.spring(duration: 0.32), value: panelExpanded)
            .background(Palette.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .onAppear { if !hasFitCamera { fitCamera(animated: false) } }
            .onChange(of: store.siteIdsByDistance.first) { _, _ in
                if !hasFitCamera { fitCamera(animated: false) }
            }
            .onChange(of: store.searchLocation) { _, _ in
                selectedId = nil
                expandedBands = []
                fitCamera(animated: true)
            }
            .onChange(of: scope) { _, newScope in
                sort = newScope == .nearby ? .distance : .risk
                selectedId = nil
                fitCamera(animated: true)
            }
        }
    }

    /// iOS 26's floating tab bar sits on top of content and does not grow the bottom safe area.
    private static var floatingTabClearance: CGFloat {
        if #available(iOS 26, *) { 52 } else { 0 }
    }

    /// Collapsed: a compact "Risk near you" card docked to the bottom.
    /// Expanded: about half the screen, with full list browsing.
    private func panelHeight(for available: CGFloat) -> CGFloat {
        panelExpanded ? min(available * 0.54, 520) : min(max(available * 0.28, 210), 240)
    }

    // MARK: Map

    private func map(_ listing: Listing, holdSites: [Site]) -> some View {
        Map(position: $camera) {
            ForEach(holdSites) { site in
                MapCircle(center: site.coordinate, radius: LightningPolicy.stopWorkRadiusMiles * Distance.metersPerMile)
                    .foregroundStyle(Palette.stopWork.opacity(0.13))
                    .stroke(Palette.stopWork.opacity(0.85), style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
                // The true 10 mi circle is smaller than a pin at state zoom, so add a fixed-size storm ring too.
                Annotation("", coordinate: site.coordinate, anchor: .center) {
                    StormRing()
                }
                .annotationTitles(.hidden)
            }
            ForEach(listing.dots) { site in
                Annotation(site.name, coordinate: site.coordinate, anchor: .center) {
                    SiteDot(level: site.riskLevel, onHold: store.activeHold(for: site.id) != nil) { select(site) }
                }
                .annotationTitles(.hidden)
            }
            // Centered pins overlap less at state zoom; the selected pin anchors at the
            // bottom so its callout sits above the coordinate.
            ForEach(listing.pins) { site in
                Annotation(site.name, coordinate: site.coordinate, anchor: selectedId == site.id ? .bottom : .center) {
                    SitePin(
                        site: site,
                        hold: store.activeHold(for: site.id),
                        distanceMiles: store.distance(to: site.id),
                        isSelected: selectedId == site.id,
                        compact: compactPins,
                        onSelect: { select(site) },
                        onOpen: { store.showSite(site.id) })
                }
                .annotationTitles(.hidden)
            }
            Annotation(store.searchLocation.name, coordinate: store.searchLocation.coordinate, anchor: .center) {
                LocationMarker()
            }
            .annotationTitles(.hidden)
            UserAnnotation()
        }
        .mapStyle(satellite
                  ? .hybrid(elevation: .flat, pointsOfInterest: .excludingAll)
                  : .standard(elevation: .flat, emphasis: .muted, pointsOfInterest: .excludingAll))
        .mapControlVisibility(.hidden)
        .onMapCameraChange(frequency: .onEnd) { context in
            visibleRegion = context.region
            let compact = context.region.span.latitudeDelta > 1.2
            if compact != compactPins { compactPins = compact }
        }
    }

    private var topControls: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                SiteSearchField(query: $search, siteCount: store.sites.count)
                Button { satellite.toggle() } label: {
                    Image(systemName: satellite ? "map.fill" : "square.3.layers.3d")
                        .font(.subheadline.weight(.semibold))
                        .frame(width: 40, height: 40)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(satellite ? "Standard map" : "Satellite map")
            }
            .padding(.horizontal, 14)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    LocationChip()
                    FilterChip(title: "All", isSelected: filter == .all) { filter = .all }
                    ForEach(Self.filterTypes) { type in
                        FilterChip(title: type.shortName, symbol: type.symbol, isSelected: filter == .hazard(type)) {
                            filter = filter == .hazard(type) ? .all : .hazard(type)
                        }
                    }
                }
                .padding(.horizontal, 14)
            }
        }
        .padding(.bottom, 4)
    }

    private func mapFooter(showsRadius: Bool) -> some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 5) {
                Text("HAZARD INDEX").font(.caption2.weight(.bold)).foregroundStyle(Palette.secondaryText)
                HStack(spacing: 6) {
                    LinearGradient(colors: RiskLevel.allCases.map(\.color), startPoint: .leading, endPoint: .trailing)
                        .frame(width: 90, height: 6)
                        .clipShape(Capsule())
                    Text("0-10").font(.caption2).foregroundStyle(Palette.secondaryText)
                }
                if showsRadius {
                    HStack(spacing: 5) {
                        Circle().stroke(Palette.stopWork, style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
                            .frame(width: 10, height: 10)
                        Text("10 mi lightning radius").font(.caption2).foregroundStyle(Palette.secondaryText)
                    }
                }
            }
            .padding(8)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            Spacer()

            Button {
                selectedId = nil
                fitCamera(animated: true)
            } label: {
                Image(systemName: "location.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Palette.accent)
                    .frame(width: 40, height: 40)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(scope == .nearby ? "Show nearby sites" : "Show all of Florida")
        }
    }

    // MARK: Ranked panel

    private func rankedPanel(_ listing: Listing) -> some View {
        VStack(spacing: 0) {
            panelHeader(listing)
            ScrollView {
                LazyVStack(spacing: 0) {
                    if listing.primary.isEmpty {
                        if store.isLoading && store.sites.isEmpty {
                            ProgressView()
                                .padding(.top, 28)
                        } else {
                            VStack(spacing: 8) {
                                Text(store.sites.isEmpty ? "No sites loaded" : "No sites match.")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(Palette.secondaryText)
                                if let error = store.loadError {
                                    Text(error)
                                        .font(.caption)
                                        .foregroundStyle(Palette.tertiaryText)
                                        .multilineTextAlignment(.center)
                                        .padding(.horizontal, 20)
                                    Button("Retry Connection") {
                                        Task { await store.refresh() }
                                    }
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(Palette.accent)
                                    .padding(.top, 4)
                                }
                            }
                            .padding(.top, 24)
                        }
                    }
                    siteRows(listing.primary, rankOffset: 0)
                    if panelExpanded, !listing.bands.isEmpty {
                        moreSites(listing.bands, rankOffset: listing.primary.count)
                    }
                }
                .padding(.bottom, Self.floatingTabClearance + 24)
                .animation(.default, value: listing.primary.map(\.id))
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .background(
            Palette.card,
            in: UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24, style: .continuous))
        .overlay(
            UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24, style: .continuous)
                .stroke(Palette.cardBorder, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.45), radius: 16, y: -4)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Risk near you")
    }

    private func panelHeader(_ listing: Listing) -> some View {
        VStack(spacing: 8) {
            Capsule()
                .fill(Color.white.opacity(0.28))
                .frame(width: 36, height: 4)
                .padding(.top, 8)
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(scope == .nearby && search.isEmpty ? "Risk near you" : listing.title)
                        .font(.headline)
                    Text(panelSubtitle(listing))
                        .font(.caption)
                        .foregroundStyle(Palette.secondaryText)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
                Spacer(minLength: 8)
                if panelExpanded {
                    Menu {
                        Picker("Sort by", selection: $sort) {
                            ForEach(Sort.allCases, id: \.self) { Text($0.rawValue) }
                        }
                    } label: {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .frame(width: 32, height: 32)
                            .background(Palette.raised, in: Circle())
                    }
                }
                Image(systemName: "chevron.down")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Palette.tertiaryText)
                    .rotationEffect(.degrees(panelExpanded ? 180 : 0))
            }
            .contentShape(Rectangle())
            .onTapGesture { panelExpanded.toggle() }
            .gesture(DragGesture(minimumDistance: 10).onEnded { value in
                if value.translation.height < -24 { panelExpanded = true }
                if value.translation.height > 24 { panelExpanded = false }
            })

            if panelExpanded {
                Picker("Scope", selection: $scope) {
                    ForEach(Scope.allCases, id: \.self) { Text($0.rawValue) }
                }
                .pickerStyle(.segmented)
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 4)
    }

    private func panelSubtitle(_ listing: Listing) -> String {
        let updated = "updated \(store.lastUpdated?.relativeShort ?? "–")"
        if scope == .nearby, search.isEmpty, let farthest = listing.primary.compactMap({ store.distance(to: $0.id) }).max() {
            return "Within \(Distance.label(farthest)) of \(store.searchLocation.name) · \(updated)"
        }
        return "By \(sort.rawValue.lowercased()) · \(updated)"
    }

    @ViewBuilder
    private func siteRows(_ sites: [Site], rankOffset: Int) -> some View {
        ForEach(Array(sites.enumerated()), id: \.element.id) { offset, site in
            Button {
                select(site)
                store.showSite(site.id)
            } label: {
                RankedSiteRow(
                    rank: rankOffset + offset + 1, site: site,
                    distanceMiles: store.distance(to: site.id), hold: store.activeHold(for: site.id))
            }
            .buttonStyle(.plain)
            if offset < sites.count - 1 {
                Divider().overlay(Palette.stroke).padding(.leading, 56)
            }
        }
    }

    /// Farther sites, collapsed by default so the list stays focused on nearby crews.
    private func moreSites(_ bands: [DistanceBand], rankOffset: Int) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("MORE SITES").font(.caption.weight(.bold)).foregroundStyle(Palette.secondaryText)
                Spacer()
                Text("\(bands.reduce(0) { $0 + $1.sites.count }) farther away")
                    .font(.caption)
                    .foregroundStyle(Palette.tertiaryText)
            }
            .padding(.horizontal, 18)
            .padding(.top, 18)
            .padding(.bottom, 8)

            ForEach(bands) { band in
                let expanded = expandedBands.contains(band.id)
                Button {
                    withAnimation(.snappy) {
                        if expanded { expandedBands.remove(band.id) } else { expandedBands.insert(band.id) }
                    }
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .rotationEffect(.degrees(expanded ? 90 : 0))
                            .foregroundStyle(Palette.tertiaryText)
                            .frame(width: 18)
                        Text(band.title).font(.subheadline.weight(.semibold)).foregroundStyle(.white)
                        Spacer()
                        let severe = band.sites.filter { $0.riskLevel == .high || $0.riskLevel == .severe }.count
                        if severe > 0 {
                            Text("\(severe) high risk")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(RiskLevel.high.color)
                        }
                        Text("\(band.sites.count)")
                            .font(.caption.weight(.semibold).monospacedDigit())
                            .foregroundStyle(Palette.secondaryText)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Palette.raised, in: Capsule())
                    }
                    .padding(.horizontal, 18)
                    .padding(.vertical, 12)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityValue(expanded ? "Expanded" : "Collapsed")

                if expanded {
                    siteRows(band.sites, rankOffset: rankOffset + bands.prefix { $0.id != band.id }.reduce(0) { $0 + $1.sites.count })
                }
                Divider().overlay(Palette.stroke)
            }
        }
    }

    /// Stop-work holds and severe sites outside the nearby group.
    @ViewBuilder
    private var severeElsewhereCard: some View {
        let sites = store.severeElsewhere()
        if !sites.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label("Severe elsewhere in Florida", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Palette.stopWork)
                ForEach(sites.prefix(3)) { site in
                    Button {
                        select(site)
                        store.showSite(site.id)
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: store.activeHold(for: site.id) != nil ? "cloud.bolt.fill" : "flame.fill")
                                .foregroundStyle(Palette.stopWork)
                                .frame(width: 18)
                            Text(site.name).font(.subheadline.weight(.semibold)).foregroundStyle(.white).lineLimit(1)
                            Text(store.distance(to: site.id).map(Distance.label) ?? "")
                                .font(.caption)
                                .foregroundStyle(Palette.secondaryText)
                            Spacer()
                            Text(store.activeHold(for: site.id) != nil ? "Stop work" : site.hazardIndex.oneDecimal)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(store.activeHold(for: site.id) != nil ? Palette.stopWork : site.riskLevel.color)
                        }
                    }
                    .buttonStyle(.plain)
                }
                if sites.count > 3 {
                    Button("Show all \(sites.count) in Statewide") { scope = .statewide }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Palette.accent)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.stopWork.opacity(0.1), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .padding(.horizontal, 14)
            .padding(.bottom, 6)
        }
    }

    // MARK: Camera

    private func select(_ site: Site) {
        selectedId = site.id
        withAnimation(.easeInOut) {
            camera = .region(MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: site.latitude - 0.12, longitude: site.longitude),
                span: MKCoordinateSpan(latitudeDelta: 0.9, longitudeDelta: 0.9)))
        }
    }

    /// Nearby: frame the location and its nearest sites. Statewide: all of Florida.
    private func fitCamera(animated: Bool) {
        let region: MKCoordinateRegion
        let nearby = store.nearbySites
        if scope == .nearby, !nearby.isEmpty {
            let lats = nearby.map(\.latitude) + [store.searchLocation.latitude]
            let lons = nearby.map(\.longitude) + [store.searchLocation.longitude]
            let (minLat, maxLat) = (lats.min()!, lats.max()!)
            let (minLon, maxLon) = (lons.min()!, lons.max()!)
            let span = max(maxLat - minLat, maxLon - minLon, 0.2) * 1.3
            region = MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2, longitude: (minLon + maxLon) / 2),
                span: MKCoordinateSpan(latitudeDelta: span, longitudeDelta: span))
        } else {
            region = Self.florida
        }
        hasFitCamera = !store.sites.isEmpty
        if animated {
            withAnimation(.easeInOut) { camera = .region(region) }
        } else {
            camera = .region(region)
        }
    }
}

// MARK: - Pins and rows

/// Owns the typed text so keystrokes only re-render the field; the map and list
/// update once typing pauses.
private struct SiteSearchField: View {
    @Binding var query: String
    let siteCount: Int
    @State private var text = ""

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(Palette.secondaryText)
            TextField("Search sites", text: $text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.search)
                .onSubmit { query = text }
                .accessibilityHint("Search \(siteCount) sites by name or county")
            if !text.isEmpty {
                Button {
                    text = ""
                    query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Palette.tertiaryText)
                }
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 40)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .task(id: text) {
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled, query != text else { return }
            query = text
        }
    }
}

/// Lightweight marker for sites outside the main group, so 300+ sites stay readable.
private struct SiteDot: View {
    let level: RiskLevel
    let onHold: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            Circle()
                .fill(onHold ? Palette.stopWork : level.color)
                .frame(width: 9, height: 9)
                .overlay(Circle().stroke(Color.black.opacity(0.5), lineWidth: 1))
                .frame(width: 22, height: 22)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }
}

private struct LocationMarker: View {
    var body: some View {
        ZStack {
            Circle().fill(Palette.accent.opacity(0.25)).frame(width: 30, height: 30)
            Image(systemName: "house.fill")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 18, height: 18)
                .background(Palette.accent, in: Circle())
                .overlay(Circle().stroke(.white, lineWidth: 1.5))
        }
        .allowsHitTesting(false)
    }
}

private struct SitePin: View {
    let site: Site
    let hold: LightningHold?
    let distanceMiles: Double?
    let isSelected: Bool
    /// Smaller pins when zoomed out, where nearby sites overlap.
    let compact: Bool
    let onSelect: () -> Void
    let onOpen: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            if isSelected {
                Button(action: onOpen) { callout }
                    .buttonStyle(.plain)
                    .transition(.scale(scale: 0.8, anchor: .bottom).combined(with: .opacity))
            }
            Button(action: onSelect) { pin }
                .buttonStyle(.plain)
        }
        .animation(.spring(duration: 0.3), value: isSelected)
    }

    private var pin: some View {
        let level = site.riskLevel
        let size: CGFloat = isSelected ? 38 : compact ? 25 : 32
        return ZStack(alignment: .topTrailing) {
            Text(site.hazardIndex.oneDecimal)
                .font((compact && !isSelected ? Font.system(size: 10) : .caption).weight(.bold).monospacedDigit())
                .foregroundStyle(level == .severe ? Color.white : .black)
                .frame(width: size, height: size)
                .background(level.color.gradient, in: Circle())
                .overlay(Circle().stroke(isSelected ? Color.white : Color.black.opacity(0.35), lineWidth: isSelected ? 3 : 1.5))
                .shadow(color: .black.opacity(0.45), radius: 4, y: 2)
            if hold != nil {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 17, height: 17)
                    .background(Palette.stopWork, in: Circle())
                    .overlay(Circle().stroke(Palette.background, lineWidth: 1.5))
                    .offset(x: 6, y: -6)
                    .symbolEffect(.pulse)
            }
        }
        .animation(.spring, value: site.hazardIndex)
    }

    private var callout: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(site.name).font(.subheadline.weight(.bold)).foregroundStyle(.white)
            if let hold {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    Label("Stop work · \(hold.remaining(at: context.date).countdown)", systemImage: "circle.fill")
                        .labelStyle(DotLabelStyle(color: Palette.stopWork))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Palette.stopWork)
                }
            } else {
                Label("\(site.riskLevel.label) · \(site.topFactor?.type.shortName ?? "") \(site.topFactor?.score.oneDecimal ?? "")",
                      systemImage: "circle.fill")
                    .labelStyle(DotLabelStyle(color: site.riskLevel.color))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Palette.secondaryText)
            }
            Text([distanceMiles.map { "\(Distance.label($0)) away" }, "Tap for details"].compactMap { $0 }.joined(separator: " · "))
                .font(.caption2)
                .foregroundStyle(Palette.tertiaryText)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(Palette.card.opacity(0.96), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Palette.stroke))
        .shadow(color: .black.opacity(0.5), radius: 8, y: 3)
        .fixedSize()
    }
}

private struct StormRing: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            Circle()
                .fill(Palette.stopWork.opacity(pulse ? 0.05 : 0.22))
                .frame(width: 96, height: 96)
                .scaleEffect(pulse ? 1.15 : 0.9)
            Circle()
                .stroke(Palette.stopWork.opacity(0.9), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
                .frame(width: 84, height: 84)
        }
        .allowsHitTesting(false)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { pulse = true }
        }
    }
}

private struct DotLabelStyle: LabelStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 6, height: 6)
            configuration.title
        }
    }
}

private struct RankedSiteRow: View {
    let rank: Int
    let site: Site
    let distanceMiles: Double?
    let hold: LightningHold?

    var body: some View {
        HStack(spacing: 12) {
            Text("\(rank)")
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(Palette.tertiaryText)
                .frame(width: 22)

            RoundedRectangle(cornerRadius: 2)
                .fill(site.riskLevel.color)
                .frame(width: 3.5, height: 36)

            VStack(alignment: .leading, spacing: 3) {
                Text(site.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)

                HStack(spacing: 5) {
                    if let top = site.topFactor {
                        Image(systemName: top.type.symbol)
                            .font(.caption2)
                            .foregroundStyle(top.type.color)
                    }
                    Text(detail)
                        .lineLimit(1)
                }
                .font(.caption)
                .foregroundStyle(Palette.secondaryText)
            }

            Spacer(minLength: 6)

            if hold != nil {
                Image(systemName: "bolt.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(Palette.stopWork, in: Circle())
                    .accessibilityLabel("Lightning hold active")
            }

            RiskBadge(index: site.hazardIndex)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }

    private var detail: String {
        var parts: [String] = []
        if let distanceMiles { parts.append(Distance.label(distanceMiles)) }
        parts.append(site.county)
        if let top = site.topFactor { parts.append("\(top.type.shortName) \(top.score.oneDecimal)") }
        return parts.joined(separator: " · ")
    }
}

#Preview {
    SitesView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
