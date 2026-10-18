import MapKit
import SwiftUI

/// Chooses the location that sites are sorted around. Shown on first launch (with
/// Gainesville preselected) and from the location chip on the Today and Sites tabs.
struct LocationPickerView: View {
    static let presets: [SearchLocation] = [
        .gainesville,
        SearchLocation(name: "Jacksonville, FL", latitude: 30.3322, longitude: -81.6557),
        SearchLocation(name: "Tallahassee, FL", latitude: 30.4383, longitude: -84.2807),
        SearchLocation(name: "Pensacola, FL", latitude: 30.4213, longitude: -87.2169),
        SearchLocation(name: "Orlando, FL", latitude: 28.5384, longitude: -81.3789),
        SearchLocation(name: "Tampa, FL", latitude: 27.9506, longitude: -82.4572),
        SearchLocation(name: "Fort Myers, FL", latitude: 26.6406, longitude: -81.8723),
        SearchLocation(name: "West Palm Beach, FL", latitude: 26.7153, longitude: -80.0534),
        SearchLocation(name: "Miami, FL", latitude: 25.7617, longitude: -80.1918),
    ]

    var isOnboarding = false

    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var search = PlaceSearch()
    @State private var location = LocationManager()
    @State private var waitingForGPS = false

    var body: some View {
        @Bindable var search = search

        NavigationStack {
            List {
                if isOnboarding, search.query.isEmpty {
                    Section { onboardingHeader }
                        .listRowBackground(Color.clear)
                }

                if !search.query.isEmpty {
                    searchResults
                } else {
                    Section {
                        Button(action: useCurrentLocation) {
                            HStack {
                                Label("Use my current location", systemImage: "location.fill")
                                    .foregroundStyle(Palette.accent)
                                Spacer()
                                if waitingForGPS { ProgressView() }
                            }
                        }
                        if location.authorization == .denied {
                            Text("Location access is off. Turn it on in Settings, or pick a city below.")
                                .font(.caption)
                                .foregroundStyle(Palette.secondaryText)
                        }
                    }
                    .listRowBackground(Palette.card)

                    Section("Florida cities") {
                        ForEach(Self.presets, id: \.name) { preset in
                            Button { choose(preset) } label: { row(for: preset) }
                        }
                    }
                    .listRowBackground(Palette.card)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Palette.background)
            .searchable(text: $search.query, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: "City, ZIP code, or address")
            .navigationTitle(isOnboarding ? "Choose your location" : "Location")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !isOnboarding {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                }
            }
            .safeAreaInset(edge: .bottom) {
                if isOnboarding, search.query.isEmpty {
                    Button { choose(store.searchLocation) } label: {
                        Text("Continue with \(store.searchLocation.name)")
                            .font(.headline)
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity)
                            .frame(height: 54)
                            .background(Palette.accent.gradient, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal)
                    .padding(.vertical, 10)
                    .background(Palette.background.opacity(0.95))
                }
            }
            .onChange(of: location.location) { _, newLocation in
                guard waitingForGPS, let newLocation else { return }
                waitingForGPS = false
                choose(SearchLocation(
                    name: "My location", latitude: newLocation.coordinate.latitude,
                    longitude: newLocation.coordinate.longitude))
            }
        }
        .interactiveDismissDisabled(isOnboarding)
    }

    private var onboardingHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: "mappin.and.ellipse")
                .font(.largeTitle)
                .foregroundStyle(Palette.accent)
            Text("Where are your crews working?").font(.title2.weight(.bold))
            Text("Heron lists the \(AppStore.nearbyCount) sites closest to you and makes the nearest one your home site. Farther sites are one tap away, and you can change this anytime.")
                .font(.subheadline)
                .foregroundStyle(Palette.secondaryText)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var searchResults: some View {
        Section("Results") {
            if search.results.isEmpty {
                Text("No matches yet").foregroundStyle(Palette.secondaryText)
            }
            ForEach(search.results, id: \.self) { completion in
                Button {
                    Task {
                        if let place = await search.resolve(completion) { choose(place) }
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(completion.title).foregroundStyle(.white)
                        if !completion.subtitle.isEmpty {
                            Text(completion.subtitle).font(.caption).foregroundStyle(Palette.secondaryText)
                        }
                    }
                }
            }
        }
        .listRowBackground(Palette.card)
    }

    private func row(for preset: SearchLocation) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(preset.name).foregroundStyle(.white)
                if let nearest = store.nearestSite(to: preset) {
                    Text("Nearest: \(nearest.site.name) · \(Distance.label(nearest.miles))")
                        .font(.caption)
                        .foregroundStyle(Palette.secondaryText)
                }
            }
            Spacer()
            if preset.name == store.searchLocation.name {
                Image(systemName: "checkmark").foregroundStyle(Palette.accent)
            }
        }
    }

    private func useCurrentLocation() {
        waitingForGPS = true
        location.request()
    }

    private func choose(_ place: SearchLocation) {
        store.setLocation(place)
        dismiss()
    }
}

/// Button showing the current location; opens `LocationPickerView`.
struct LocationChip: View {
    @Environment(AppStore.self) private var store
    @State private var showPicker = false

    var body: some View {
        Button { showPicker = true } label: {
            HStack(spacing: 5) {
                Image(systemName: "location.fill").font(.caption2)
                Text(store.searchLocation.name).lineLimit(1)
                Image(systemName: "chevron.down").font(.caption2.weight(.bold))
            }
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .frame(height: 32)
            .background(.ultraThinMaterial, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Location: \(store.searchLocation.name). Change location")
        .sheet(isPresented: $showPicker) {
            LocationPickerView().environment(store)
        }
    }
}

/// Apple's on-device place search, limited to Florida, so no geocoding backend is needed.
@MainActor
@Observable
final class PlaceSearch: NSObject, MKLocalSearchCompleterDelegate {
    var query = "" {
        didSet { completer.queryFragment = query }
    }
    private(set) var results: [MKLocalSearchCompletion] = []

    @ObservationIgnored private let completer = MKLocalSearchCompleter()

    override init() {
        super.init()
        completer.delegate = self
        completer.resultTypes = [.address, .pointOfInterest]
        completer.region = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 27.8, longitude: -83.5),
            span: MKCoordinateSpan(latitudeDelta: 7.5, longitudeDelta: 8.5))
    }

    func resolve(_ completion: MKLocalSearchCompletion) async -> SearchLocation? {
        guard let item = try? await MKLocalSearch(request: MKLocalSearch.Request(completion: completion)).start().mapItems.first
        else { return nil }
        let coordinate: CLLocationCoordinate2D
        if #available(iOS 26, *) {
            coordinate = item.location.coordinate
        } else {
            coordinate = item.placemark.coordinate
        }
        return SearchLocation(name: completion.title, latitude: coordinate.latitude, longitude: coordinate.longitude)
    }

    nonisolated func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        MainActor.assumeIsolated { results = Array(completer.results.prefix(12)) }
    }

    nonisolated func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        MainActor.assumeIsolated { results = [] }
    }
}
