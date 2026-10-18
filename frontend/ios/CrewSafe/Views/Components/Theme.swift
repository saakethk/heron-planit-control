import SwiftUI

/// Modernized, high-contrast dark palette for PlanIT / CrewSafe:
/// Clean OLED background, distinct zinc cards, accessible safety tints, and electric cyan accent.
enum Palette {
    static let background = Color(red: 0.04, green: 0.045, blue: 0.055)
    static let card = Color(red: 0.085, green: 0.09, blue: 0.105)
    static let cardBorder = Color.white.opacity(0.08)
    static let raised = Color(red: 0.13, green: 0.135, blue: 0.155)
    static let stroke = Color.white.opacity(0.08)
    static let text = Color.white
    static let secondaryText = Color.white.opacity(0.68)
    static let tertiaryText = Color.white.opacity(0.42)
    static let accent = Color(red: 0.05, green: 0.65, blue: 0.95)
    static let accentGradient = LinearGradient(
        colors: [Color(red: 0.05, green: 0.65, blue: 0.95), Color(red: 0.0, green: 0.50, blue: 0.85)],
        startPoint: .topLeading, endPoint: .bottomTrailing)
    static let live = Color(red: 0.20, green: 0.84, blue: 0.55)
    static let stopWork = Color(red: 0.98, green: 0.28, blue: 0.28)
}

extension RiskLevel {
    var color: Color {
        switch self {
        case .low: Color(red: 0.20, green: 0.84, blue: 0.55)
        case .moderate: Color(red: 0.98, green: 0.78, blue: 0.15)
        case .high: Color(red: 1.0, green: 0.55, blue: 0.10)
        case .severe: Color(red: 0.98, green: 0.28, blue: 0.28)
        }
    }
}

extension HazardType {
    var color: Color {
        switch self {
        case .lightning: Palette.stopWork
        case .flood: Color(red: 0.25, green: 0.65, blue: 0.98)
        case .heat: Color(red: 1.0, green: 0.55, blue: 0.10)
        case .wildfire: Color(red: 1.0, green: 0.38, blue: 0.18)
        case .wildlife: Color(red: 0.35, green: 0.85, blue: 0.45)
        case .soilSaturation: Color(red: 0.75, green: 0.60, blue: 0.45)
        case .other: Color(white: 0.75)
        }
    }
}

extension AlertSeverity {
    var color: Color {
        switch self {
        case .advisory: Palette.accent
        case .warning: RiskLevel.high.color
        case .stopWork: Palette.stopWork
        }
    }
}

extension ConnectionStatus {
    func label(isMock: Bool) -> String {
        switch self {
        case .live: isMock ? "Live · simulated" : "Live Stream"
        case .connecting: "Connecting…"
        case .offline: "Offline"
        }
    }

    var color: Color {
        switch self {
        case .live: Palette.live
        case .connecting: RiskLevel.moderate.color
        case .offline: Color.gray
        }
    }
}

extension View {
    func card(padding: CGFloat = 16, cornerRadius: CGFloat = 18) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(Palette.cardBorder, lineWidth: 1)
            )
    }

    /// Caps line length on wide screens (iPhone Duo unfolded, iPad).
    func readableWidth() -> some View {
        frame(maxWidth: 640).frame(maxWidth: .infinity)
    }
}

extension Date {
    var shortTime: String { formatted(date: .omitted, time: .shortened) }

    var relativeShort: String {
        let seconds = Date.now.timeIntervalSince(self)
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(Int(seconds / 60))m ago" }
        if seconds < 86_400 { return "\(Int(seconds / 3600))h ago" }
        return formatted(.dateTime.weekday(.abbreviated))
    }
}

extension TimeInterval {
    /// `mm:ss` for countdowns.
    var countdown: String {
        let total = Int(self.rounded(.up))
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}

