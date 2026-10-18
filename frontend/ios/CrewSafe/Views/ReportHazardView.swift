import PhotosUI
import SwiftUI
import UIKit

/// Crew hazard reporting: type, site, photo, notes, and GPS location.
struct ReportHazardView: View {
    private static let reportableTypes: [HazardType] = [.wildlife, .flood, .heat, .wildfire, .soilSaturation, .other]

    @Environment(AppStore.self) private var store
    @State private var location = LocationManager()
    @State private var hazardType: HazardType = .wildlife
    @State private var siteId: Int?
    @State private var notes = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var cameraImage: UIImage?
    @State private var photo: PreparedPhoto?
    @State private var isPreparingPhoto = false
    @State private var showCamera = false
    @State private var isSubmitting = false
    @State private var showSubmitted = false
    @State private var errorMessage: String?

    private var cameraAvailable: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }

    /// Nearby sites only; a menu of 300+ sites isn't usable. Keeps the current pick if it's farther.
    private var reportableSites: [Site] {
        var sites = store.nearbySites
        if let siteId, !sites.contains(where: { $0.id == siteId }), let current = store.site(id: siteId) {
            sites.insert(current, at: 0)
        }
        return sites
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Report hazard").font(.largeTitle.weight(.bold))
                        Text("Supervisors and crews at the site are notified right away.")
                            .font(.subheadline)
                            .foregroundStyle(Palette.secondaryText)
                    }
                    .padding(.top, 8)

                    typeGrid
                    siteAndLocation
                    photoSection
                    notesSection
                    submitButton
                    RecentReportsCard()
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
                .readableWidth()
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Palette.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .onAppear {
                if siteId == nil { siteId = store.homeSiteId }
                location.request()
            }
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                Task {
                    isPreparingPhoto = true
                    defer { isPreparingPhoto = false }
                    if let data = try? await item.loadTransferable(type: Data.self) {
                        photo = await PreparedPhoto.make(from: data)
                    }
                }
            }
            .onChange(of: cameraImage) { _, image in
                guard let image else { return }
                cameraImage = nil
                Task {
                    isPreparingPhoto = true
                    defer { isPreparingPhoto = false }
                    photo = await PreparedPhoto.make(from: image)
                }
            }
            .onChange(of: location.location) { _, newLocation in
                if let newLocation, let nearest = store.nearestSite(to: newLocation) {
                    siteId = nearest.id
                }
            }
            .fullScreenCover(isPresented: $showCamera) {
                CameraPicker(image: $cameraImage).ignoresSafeArea()
            }
            .alert("Report submitted", isPresented: $showSubmitted) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("Thanks. Supervisors and nearby crews have been notified.")
            }
            .alert("Couldn't submit report", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
            ) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "")
            }
        }
    }

    // MARK: Sections

    private var typeGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
            ForEach(Self.reportableTypes) { type in
                let selected = hazardType == type
                Button { hazardType = type } label: {
                    VStack(spacing: 8) {
                        Image(systemName: type.symbol)
                            .font(.title2)
                            .foregroundStyle(selected ? .black : type.color)
                        Text(type.shortName)
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(selected ? .black : .white)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(selected ? type.color : Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(selected ? .clear : Palette.stroke))
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
    }

    private var siteAndLocation: some View {
        VStack(spacing: 0) {
            HStack {
                Label("Site", systemImage: "building.2.fill").foregroundStyle(Palette.secondaryText)
                Spacer()
                Menu {
                    Picker("Site", selection: $siteId) {
                        Text("Not at a site").tag(Int?.none)
                        ForEach(reportableSites) { site in
                            Text("\(site.name) · \(store.distance(to: site.id).map(Distance.label) ?? "")")
                                .tag(Int?.some(site.id))
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(store.siteName(for: siteId)).foregroundStyle(.white)
                        Image(systemName: "chevron.up.chevron.down").font(.caption).foregroundStyle(Palette.tertiaryText)
                    }
                }
            }
            .padding(.vertical, 12)
            Divider().overlay(Palette.stroke)
            HStack {
                Label("Location", systemImage: "location.fill").foregroundStyle(Palette.secondaryText)
                Spacer()
                Text(locationText).font(.subheadline.monospacedDigit()).foregroundStyle(.white)
            }
            .padding(.vertical, 12)
        }
        .font(.subheadline)
        .padding(.horizontal, 16)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Palette.stroke))
    }

    @ViewBuilder
    private var photoSection: some View {
        if isPreparingPhoto {
            ProgressView()
                .frame(maxWidth: .infinity)
                .frame(height: 96)
                .background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        } else if let photo {
            ZStack(alignment: .topTrailing) {
                Image(uiImage: photo.preview)
                    .resizable()
                    .scaledToFill()
                    .frame(height: 220)
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                Button {
                    self.photo = nil
                    photoItem = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .frame(width: 30, height: 30)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .padding(10)
                .accessibilityLabel("Remove photo")
            }
        } else {
            HStack(spacing: 10) {
                if cameraAvailable {
                    Button { showCamera = true } label: {
                        photoTile(symbol: "camera.fill", title: "Take photo")
                    }
                    .buttonStyle(.plain)
                }
                PhotosPicker(selection: $photoItem, matching: .images) {
                    photoTile(symbol: "photo.on.rectangle", title: cameraAvailable ? "Library" : "Add photo")
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func photoTile(symbol: String, title: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: symbol).font(.title2).foregroundStyle(Palette.accent)
            Text(title).font(.footnote.weight(.semibold))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 22)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Palette.accent.opacity(0.4), style: StrokeStyle(lineWidth: 1.5, dash: [6, 4])))
    }

    private var notesSection: some View {
        TextField("What did you see? e.g. 6 ft alligator near the substation gate",
                  text: $notes, axis: .vertical)
            .lineLimit(3...6)
            .padding(14)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Palette.stroke))
    }

    private var submitButton: some View {
        Button {
            Task { await submit() }
        } label: {
            HStack(spacing: 8) {
                if isSubmitting {
                    ProgressView().tint(.white)
                } else {
                    Image(systemName: "paperplane.fill")
                    Text("Submit \(hazardType.shortName.lowercased()) report")
                }
            }
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Palette.accent.gradient, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(isSubmitting || isPreparingPhoto)
    }

    // MARK: Actions

    private var locationText: String {
        guard let coordinate = location.location?.coordinate else {
            return location.authorization == .denied ? "Permission denied" : "Locating…"
        }
        return "\(coordinate.latitude.rounded(toPlaces: 4)), \(coordinate.longitude.rounded(toPlaces: 4))"
    }

    private func submit() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            try await store.submitReport(
                type: hazardType, siteId: siteId, notes: notes,
                photoJpeg: photo?.jpeg, thumbnail: photo?.thumbnail,
                coordinate: location.location?.coordinate)
            notes = ""
            photo = nil
            photoItem = nil
            showSubmitted = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// A picked photo, resized off the main thread once so the form never handles the full-size original.
struct PreparedPhoto {
    let preview: UIImage
    let thumbnail: UIImage
    let jpeg: Data?

    static func make(from data: Data) async -> PreparedPhoto? {
        await Task.detached(priority: .userInitiated) {
            UIImage(data: data).map(prepare)
        }.value
    }

    static func make(from image: UIImage) async -> PreparedPhoto {
        await Task.detached(priority: .userInitiated) { prepare(image) }.value
    }

    private static func prepare(_ image: UIImage) -> PreparedPhoto {
        let preview = resized(image, maxDimension: 1600)
        return PreparedPhoto(
            preview: preview,
            thumbnail: resized(image, maxDimension: 132),
            jpeg: preview.jpegData(compressionQuality: 0.6))
    }

    private static func resized(_ image: UIImage, maxDimension: CGFloat) -> UIImage {
        let longest = max(image.size.width, image.size.height)
        guard longest > maxDimension else { return image }
        let scale = maxDimension / longest
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

/// Separate view so typing in the report form doesn't re-render the list.
private struct RecentReportsCard: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Recent crew reports")
            VStack(alignment: .leading, spacing: 14) {
                ForEach(store.reports) { report in
                    CrewReportRow(report: report, siteName: store.siteName(for: report.siteId),
                                  photo: store.localReportThumbnails[report.id])
                    if report.id != store.reports.last?.id { Divider().overlay(Palette.stroke) }
                }
            }
            .card()
            .animation(.default, value: store.reports.map(\.id))
        }
        .padding(.top, 6)
    }
}

struct CrewReportRow: View {
    let report: CrewReport
    let siteName: String?
    let photo: UIImage?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Group {
                if let photo {
                    Image(uiImage: photo).resizable().scaledToFill()
                } else {
                    Image(systemName: report.type.symbol)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(report.type.color)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(report.type.color.opacity(0.15))
                }
            }
            .frame(width: 44, height: 44)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(report.type.displayName).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(report.createdAt.relativeShort).font(.caption2).foregroundStyle(Palette.tertiaryText)
                }
                Text(report.notes).font(.footnote).foregroundStyle(Palette.secondaryText)
                Text([report.reporter, siteName].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption2)
                    .foregroundStyle(Palette.tertiaryText)
            }
        }
    }
}

#Preview {
    ReportHazardView()
        .environment(AppStore.makeDefault())
        .preferredColorScheme(.dark)
}
