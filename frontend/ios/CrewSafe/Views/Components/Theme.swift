import SwiftUI

/// Dark marsh palette for Heron: teal accent, high contrast for outdoor use.
enum Palette {
    static let background = Color(red: 0.035, green: 0.055, blue: 0.062)
    static let card = Color(red: 0.075, green: 0.110, blue: 0.122)
    static let raised = Color(red: 0.110, green: 0.155, blue: 0.168)
    static let stroke = Color.white.opacity(0.07)
    static let secondaryText = Color.white.opacity(0.62)
    static let tertiaryText = Color.white.opacity(0.42)
    static let accent = Color(red: 0.22, green: 0.62, blue: 0.62)
    static let live = Color(red: 0.35, green: 0.82, blue: 0.58)
    static let stopWork = Color(red: 0.96, green: 0.27, blue: 0.27)
}

extension RiskLevel {
    var color: Color {
        switch self {
        case .low: Color(red: 0.2, green: 0.8, blue: 0.4)
        case .moderate: Color(red: 0.98, green: 0.82, blue: 0.13)
        case .high: Color(red: 1.0, green: 0.62, blue: 0.04)
        case .severe: Color(red: 0.96, green: 0.27, blue: 0.27)
        }
    }
}

extension HazardType {
    var color: Color {
        switch self {
        case .lightning: Palette.stopWork
        case .flood: Color(red: 0.98, green: 0.78, blue: 0.2)
        case .heat: Color(red: 1.0, green: 0.6, blue: 0.2)
        case .wildfire: Color(red: 1.0, green: 0.42, blue: 0.2)
        case .wildlife: Color(red: 0.45, green: 0.85, blue: 0.45)
        case .soilSaturation: Color(red: 0.7, green: 0.55, blue: 0.4)
        case .other: Color(white: 0.7)
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
        case .live: isMock ? "Live · simulated" : "Live"
        case .connecting: "Connecting"
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
    func card(padding: CGFloat = 14) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Palette.stroke))
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
        if seconds < 60 { return "now" }
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
