import Charts
import SwiftUI

// MARK: Hazard Index

/// Minimalist 270° circular gauge for the 0-10 Hazard Index.
struct HazardGauge: View {
    let index: Double
    var size: CGFloat = 150

    var body: some View {
        let level = RiskLevel(index: index)
        let strokeWidth = size * 0.085
        let style = StrokeStyle(lineWidth: strokeWidth, lineCap: .round)

        ZStack {
            // Background track
            Circle()
                .trim(from: 0, to: 0.75)
                .stroke(Color.white.opacity(0.08), style: style)
                .rotationEffect(.degrees(135))

            // Animated progress arc
            Circle()
                .trim(from: 0, to: 0.75 * min(max(index / 10, 0), 1))
                .stroke(
                    LinearGradient(
                        colors: [level.color.opacity(0.8), level.color],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    ),
                    style: style
                )
                .rotationEffect(.degrees(135))

            VStack(spacing: 2) {
                Text(index.oneDecimal)
                    .font(.system(size: size * 0.32, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .contentTransition(.numericText(value: index))
                
                Text(level.label.uppercased())
                    .font(.system(size: max(10, size * 0.085), weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(level.color)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(level.color.opacity(0.12), in: Capsule())
            }
        }
        .frame(width: size, height: size)
        .animation(.spring(response: 0.5, dampingFraction: 0.8), value: index)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Hazard index \(index.oneDecimal) out of 10, \(level.label)")
    }
}

/// Minimalist 4-band risk bar with an active position marker.
struct RiskBandBar: View {
    let index: Double

    var body: some View {
        let current = RiskLevel(index: index)
        VStack(spacing: 6) {
            GeometryReader { geo in
                let width = geo.size.width
                ZStack(alignment: .leading) {
                    // Segmented gradient track
                    HStack(spacing: 3) {
                        ForEach(RiskLevel.allCases, id: \.self) { level in
                            Capsule()
                                .fill(level.color.opacity(level == current ? 1.0 : 0.22))
                                .frame(height: 5)
                        }
                    }

                    // Indicator marker
                    Circle()
                        .fill(Color.white)
                        .frame(width: 9, height: 9)
                        .shadow(color: .black.opacity(0.5), radius: 2, y: 1)
                        .offset(x: min(max(width * CGFloat(index / 10.0) - 4.5, 0), width - 9))
                }
            }
            .frame(height: 9)

            HStack {
                Text("LOW").font(.system(size: 9, weight: .semibold)).foregroundStyle(RiskLevel.low.color)
                Spacer()
                Text("MOD").font(.system(size: 9, weight: .semibold)).foregroundStyle(RiskLevel.moderate.color)
                Spacer()
                Text("HIGH").font(.system(size: 9, weight: .semibold)).foregroundStyle(RiskLevel.high.color)
                Spacer()
                Text("SEVERE").font(.system(size: 9, weight: .semibold)).foregroundStyle(RiskLevel.severe.color)
            }
        }
        .animation(.spring, value: index)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Hazard index \(index.oneDecimal) of 10")
    }
}

/// Sleek risk badge pill with colored dot indicator.
struct RiskBadge: View {
    let index: Double
    var large = false

    var body: some View {
        let level = RiskLevel(index: index)
        HStack(spacing: 5) {
            Circle()
                .fill(level.color)
                .frame(width: large ? 7 : 5, height: large ? 7 : 5)
            Text(index.oneDecimal)
                .font((large ? Font.body : .caption).monospacedDigit().weight(.bold))
                .foregroundStyle(.white)
        }
        .padding(.horizontal, large ? 10 : 8)
        .padding(.vertical, large ? 6 : 4)
        .background(level.color.opacity(0.18), in: Capsule())
        .overlay(Capsule().stroke(level.color.opacity(0.35), lineWidth: 1))
        .contentTransition(.numericText(value: index))
        .animation(.default, value: index)
    }
}

struct TrendLabel: View {
    let site: Site

    var body: some View {
        let driver = site.topFactor.map { " · \($0.type.shortName.lowercased())" } ?? ""
        Group {
            if let trend = site.trend, abs(trend) >= 0.05 {
                let arrow = Text(Image(systemName: trend > 0 ? "arrow.up.right" : "arrow.down.right"))
                    .foregroundStyle(trend > 0 ? RiskLevel.high.color : RiskLevel.low.color)
                let since = site.trendStart?.formatted(.dateTime.hour()) ?? "morning"
                Text("\(arrow) \(abs(trend).oneDecimal) since \(since)\(driver)")
            } else {
                Text("Steady today\(driver)")
            }
        }
        .font(.caption)
        .foregroundStyle(Palette.secondaryText)
    }
}

struct IndexSparkline: View {
    let points: [IndexPoint]
    let color: Color

    var body: some View {
        Chart {
            ForEach(points, id: \.time) { point in
                AreaMark(x: .value("Time", point.time), y: .value("Index", point.value))
                    .foregroundStyle(LinearGradient(
                        colors: [color.opacity(0.3), color.opacity(0.0)], startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.catmullRom)
                LineMark(x: .value("Time", point.time), y: .value("Index", point.value))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round))
                    .interpolationMethod(.catmullRom)
            }
        }
        .chartYScale(domain: 0...10)
        .chartYAxis {
            AxisMarks(values: [0, 5, 10]) { _ in
                AxisGridLine().foregroundStyle(Palette.stroke)
                AxisValueLabel().foregroundStyle(Palette.tertiaryText)
            }
        }
        .chartXAxis {
            AxisMarks(values: .stride(by: .hour, count: 2)) { _ in
                AxisValueLabel(format: .dateTime.hour()).foregroundStyle(Palette.tertiaryText)
            }
        }
    }
}

struct FactorRow: View {
    let factor: HazardFactor

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: factor.type.symbol)
                        .font(.footnote)
                        .foregroundStyle(factor.type.color)
                        .frame(width: 22, height: 22)
                        .background(factor.type.color.opacity(0.12), in: Circle())
                    Text(factor.type.displayName)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                }
                Spacer()
                Text(factor.score.oneDecimal)
                    .font(.subheadline.monospacedDigit().weight(.bold))
                    .foregroundStyle(RiskLevel(index: factor.score).color)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.06))
                    Capsule()
                        .fill(RiskLevel(index: factor.score).color.gradient)
                        .frame(width: geo.size.width * min(factor.score, 10) / 10)
                }
            }
            .frame(height: 5)
            .animation(.spring, value: factor.score)
            Text(factor.detail)
                .font(.caption)
                .foregroundStyle(Palette.secondaryText)
        }
    }
}

// MARK: Lightning

struct CountdownRing: View {
    let fraction: Double
    let label: String
    var size: CGFloat = 56

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.2), lineWidth: 3.5)
            Circle()
                .trim(from: 0, to: fraction)
                .stroke(Color.white, style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(label)
                .font(.system(size: size * 0.25, weight: .bold, design: .rounded).monospacedDigit())
                .foregroundStyle(.white)
        }
        .frame(width: size, height: size)
    }
}

/// High-impact, clean emergency stop-work banner.
struct StopWorkBanner: View {
    let hold: LightningHold
    var siteName: String? = nil

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let remaining = hold.remaining(at: context.date)
            HStack(spacing: 14) {
                // Warning badge
                Image(systemName: "bolt.fill")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.white)
                    .frame(width: 42, height: 42)
                    .background(Color.white.opacity(0.2), in: Circle())
                    .symbolEffect(.pulse)

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text("STOP WORK")
                            .font(.caption.weight(.heavy))
                            .tracking(0.6)
                        if let siteName {
                            Text("· \(siteName.uppercased())")
                                .font(.caption.weight(.bold))
                                .opacity(0.85)
                                .lineLimit(1)
                        }
                    }
                    Text("Strike \(hold.lastDistanceMiles.formatted()) mi away\(hold.lastDirection.map { " (\($0))" } ?? "")")
                        .font(.subheadline.weight(.bold))
                    Text("Mandatory shelter · 30-min countdown active")
                        .font(.caption2)
                        .opacity(0.88)
                }
                Spacer(minLength: 6)

                CountdownRing(fraction: remaining / hold.allClearInterval, label: remaining.countdown)
            }
            .foregroundStyle(.white)
            .padding(14)
            .background(
                LinearGradient(
                    colors: [Color(red: 0.95, green: 0.22, blue: 0.22), Color(red: 0.82, green: 0.12, blue: 0.15)],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.25), lineWidth: 1)
            )
            .shadow(color: Palette.stopWork.opacity(0.4), radius: 12, y: 4)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Stop work, lightning. \(remaining.countdown) until all clear.")
        }
    }
}

// MARK: Alerts

// MARK: Alerts

struct SeverityTag: View {
    let severity: AlertSeverity

    var body: some View {
        Text(severity.label.uppercased())
            .font(.system(size: 9, weight: .bold))
            .tracking(0.5)
            .foregroundStyle(severity.color)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(severity.color.opacity(0.14), in: Capsule())
    }
}

struct AlertRow: View {
    let alert: HazardAlert
    let siteName: String
    var acknowledged = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: alert.type.symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(alert.severity == .stopWork ? .white : alert.type.color)
                .frame(width: 36, height: 36)
                .background(
                    alert.severity == .stopWork
                        ? AnyShapeStyle(Palette.stopWork.gradient)
                        : AnyShapeStyle(alert.type.color.opacity(0.14)),
                    in: RoundedRectangle(cornerRadius: 11, style: .continuous)
                )

            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if !acknowledged {
                        Circle()
                            .fill(Palette.accent)
                            .frame(width: 6, height: 6)
                    }
                    Text(alert.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    Spacer(minLength: 4)
                    Text(alert.issuedAt.relativeShort)
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)
                }

                Text(alert.message)
                    .font(.footnote)
                    .foregroundStyle(Palette.secondaryText)
                    .lineSpacing(2)

                HStack(spacing: 6) {
                    SeverityTag(severity: alert.severity)
                    Text("·")
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)
                    Text(siteName)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(Palette.secondaryText)
                    if let source = alert.source {
                        Text("· \(source)")
                            .font(.caption2)
                            .foregroundStyle(Palette.tertiaryText)
                    }
                }
                .padding(.top, 2)
            }
        }
        .opacity(acknowledged ? 0.55 : 1.0)
        .contentShape(Rectangle())
    }
}

// MARK: Misc

struct ConnectionPill: View {
    let status: ConnectionStatus
    let isMock: Bool

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(status.color)
                .frame(width: 6, height: 6)
                .shadow(color: status == .live ? status.color.opacity(0.8) : .clear, radius: 3)
            Text(status.label(isMock: isMock))
                .font(.system(size: 11, weight: .semibold))
        }
        .foregroundStyle(status.color)
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(status.color.opacity(0.12), in: Capsule())
        .overlay(Capsule().stroke(status.color.opacity(0.25), lineWidth: 1))
    }
}

struct ConditionTile: View {
    let symbol: String
    let value: String
    let label: String
    var tint: Color = .white

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: symbol)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                    .frame(width: 24, height: 24)
                    .background(tint.opacity(0.12), in: Circle())
                Spacer()
            }
            Text(value)
                .font(.system(size: 19, weight: .bold, design: .rounded).monospacedDigit())
                .foregroundStyle(.white)
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(Palette.secondaryText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(Palette.cardBorder, lineWidth: 1)
        )
    }
}

struct ConditionsRow: View {
    let conditions: SiteConditions

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { tiles }
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                tiles
            }
        }
    }

    @ViewBuilder
    private var tiles: some View {
        ConditionTile(
            symbol: "thermometer.sun.fill",
            value: "\(Int(conditions.heatIndexF))°",
            label: "Heat index",
            tint: conditions.heatIndexF >= 105 ? RiskLevel.high.color : Palette.accent
        )
        ConditionTile(
            symbol: "bolt.fill",
            value: conditions.nearestStrikeMiles.map { "\($0.formatted()) mi" } ?? "None",
            label: "Strike dist",
            tint: (conditions.nearestStrikeMiles ?? 99) <= LightningPolicy.stopWorkRadiusMiles ? Palette.stopWork : Palette.accent
        )
        ConditionTile(
            symbol: "cloud.rain.fill",
            value: "\(conditions.rain24hIn.formatted()) in",
            label: "Rain 24h",
            tint: conditions.rain24hIn >= 2 ? HazardType.flood.color : Palette.accent
        )
        ConditionTile(
            symbol: "wind",
            value: "\(Int(conditions.windMph)) mph",
            label: "Wind peak",
            tint: Palette.accent
        )
    }
}

struct FilterChip: View {
    let title: String
    var symbol: String?
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                if let symbol {
                    Image(systemName: symbol)
                        .font(.caption2.weight(.bold))
                }
                Text(title)
                    .font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(isSelected ? Color.black : Color.white)
            .padding(.horizontal, 13)
            .padding(.vertical, 7)
            .background(
                isSelected ? AnyShapeStyle(Color.white) : AnyShapeStyle(Palette.card),
                in: Capsule()
            )
            .overlay(
                Capsule()
                    .stroke(isSelected ? Color.clear : Palette.cardBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

struct BriefingEventRow: View {
    let event: SiteBriefing.Event
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 3) {
                Image(systemName: event.type.symbol)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(event.type.color)
                    .frame(width: 28, height: 28)
                    .background(event.type.color.opacity(0.14), in: Circle())
                if !isLast {
                    Rectangle()
                        .fill(Palette.stroke)
                        .frame(width: 1.5)
                        .frame(maxHeight: .infinity)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(event.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                    Spacer(minLength: 6)
                    if event.isActive {
                        Text("ACTIVE")
                            .font(.system(size: 9, weight: .heavy))
                            .tracking(0.5)
                            .foregroundStyle(Palette.stopWork)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Palette.stopWork.opacity(0.15), in: Capsule())
                    } else {
                        Text(event.time.shortTime)
                            .font(.caption)
                            .foregroundStyle(Palette.secondaryText)
                    }
                }
                Text(event.detail)
                    .font(.caption)
                    .foregroundStyle(Palette.secondaryText)
            }
            .padding(.bottom, isLast ? 0 : 12)
        }
    }
}

struct SectionHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title.uppercased())
                .font(.footnote.weight(.bold))
                .tracking(0.8)
                .foregroundStyle(Palette.secondaryText)
            Spacer()
            trailing
        }
        .padding(.horizontal, 2)
    }
}

extension SectionHeader where Trailing == EmptyView {
    init(title: String) {
        self.init(title: title) { EmptyView() }
    }
}

// MARK: - Weather Extensions & Cards

extension SiteConditions {
    var conditionSummary: String {
        if let strike = nearestStrikeMiles, strike <= 10 {
            return "Thunderstorms Near Site"
        } else if rain24hIn >= 1.5 {
            return "Heavy Rain & Standing Water"
        } else if rain24hIn > 0.05 {
            return "Scattered Rain Showers"
        } else if windMph >= 25 {
            return "High Wind Conditions"
        } else if heatIndexF >= 105 {
            return "Dangerous Extreme Heat"
        } else if heatIndexF >= 92 {
            return "High Heat & Humidity"
        } else if temperatureF < 45 {
            return "Cold & Brisk"
        } else if soilMoisturePct >= 65 {
            return "Overcast & Saturated Ground"
        } else {
            return "Clear & Mild"
        }
    }

    var conditionSymbol: String {
        if let strike = nearestStrikeMiles, strike <= 10 {
            return "cloud.bolt.rain.fill"
        } else if rain24hIn >= 1.5 {
            return "cloud.heavyrain.fill"
        } else if rain24hIn > 0.05 {
            return "cloud.rain.fill"
        } else if windMph >= 25 {
            return "wind"
        } else if heatIndexF >= 105 {
            return "sun.max.trianglebadge.exclamationmark.fill"
        } else if heatIndexF >= 92 {
            return "sun.max.fill"
        } else if temperatureF < 45 {
            return "snowflake"
        } else if soilMoisturePct >= 65 {
            return "cloud.fill"
        } else {
            return "cloud.sun.fill"
        }
    }

    var conditionColor: Color {
        if let strike = nearestStrikeMiles, strike <= 10 {
            return Palette.stopWork
        } else if heatIndexF >= 105 || windMph >= 25 || rain24hIn >= 1.5 {
            return RiskLevel.high.color
        } else if heatIndexF >= 92 || rain24hIn > 0.05 {
            return RiskLevel.moderate.color
        } else {
            return Palette.accent
        }
    }

    var operatingProtocol: (headline: String, detail: String, color: Color, symbol: String) {
        if let strike = nearestStrikeMiles, strike <= 10 {
            return (
                "Lightning Stand-Down Active",
                "Hold all outdoor operations. Seek substantial enclosed shelter until all-clear countdown expires.",
                Palette.stopWork,
                "bolt.trianglebadge.exclamationmark.fill"
            )
        } else if heatIndexF >= 105 {
            return (
                "Extreme Heat Safety Protocol",
                "Mandatory 15-minute shaded rest breaks every hour. Keep cold hydration accessible for all crew members.",
                RiskLevel.high.color,
                "thermometer.sun.fill"
            )
        } else if windMph >= 25 {
            return (
                "Elevated Wind Caution",
                "High wind speeds detected. Restrict bucket truck elevated work and crane hoisting per safety threshold.",
                RiskLevel.high.color,
                "wind"
            )
        } else if rain24hIn >= 1.5 {
            return (
                "Flooding & Soft Ground Advisory",
                "Significant precipitation recorded. Inspect substation access roads and watch for soft soil near trenches.",
                HazardType.flood.color,
                "water.waves"
            )
        } else {
            return (
                "Normal Operating Parameters",
                "Ambient temperature, wind, and ground conditions are within safe operational limits for outdoor work.",
                Palette.live,
                "checkmark.shield.fill"
            )
        }
    }
}

struct SiteWeatherCard: View {
    let site: Site
    let conditions: SiteConditions
    var showHeader: Bool = true

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if showHeader {
                HStack(alignment: .center) {
                    HStack(spacing: 6) {
                        Image(systemName: "cloud.sun.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Palette.accent)
                        Text("LIVE SITE WEATHER")
                            .font(.system(size: 11, weight: .bold))
                            .tracking(0.6)
                            .foregroundStyle(Palette.secondaryText)
                    }

                    Spacer()

                    HStack(spacing: 4) {
                        Circle()
                            .fill(Palette.live)
                            .frame(width: 6, height: 6)
                        Text("Open-Meteo · Live")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(Palette.live)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Palette.live.opacity(0.12), in: Capsule())
                }
            }

            // Main Weather Hero Block
            HStack(alignment: .center, spacing: 14) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("\(Int(conditions.temperatureF.rounded()))°")
                            .font(.system(size: 46, weight: .heavy, design: .rounded))
                            .foregroundStyle(.white)
                        Text("F")
                            .font(.title2.weight(.bold))
                            .foregroundStyle(Palette.secondaryText)
                    }

                    HStack(spacing: 6) {
                        Image(systemName: conditions.conditionSymbol)
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(conditions.conditionColor)
                        Text(conditions.conditionSummary)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.white)
                    }

                    Text("Feels like \(Int(conditions.heatIndexF.rounded()))°F · Wind \(Int(conditions.windMph.rounded())) mph")
                        .font(.caption)
                        .foregroundStyle(Palette.secondaryText)
                }

                Spacer()

                // Hero condition visual plate
                ZStack {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(conditions.conditionColor.opacity(0.12))
                        .frame(width: 68, height: 68)
                        .overlay(
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .stroke(conditions.conditionColor.opacity(0.25), lineWidth: 1)
                        )
                    Image(systemName: conditions.conditionSymbol)
                        .font(.system(size: 32, weight: .semibold))
                        .foregroundStyle(conditions.conditionColor)
                }
            }

            Divider().overlay(Palette.stroke)

            // Comprehensive Weather Metrics
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                ConditionTile(
                    symbol: "thermometer.medium",
                    value: "\(Int(conditions.temperatureF.rounded()))°F",
                    label: "Ambient Air",
                    tint: Palette.accent
                )
                ConditionTile(
                    symbol: "thermometer.sun.fill",
                    value: "\(Int(conditions.heatIndexF.rounded()))°F",
                    label: "Heat Index",
                    tint: conditions.heatIndexF >= 95 ? RiskLevel.high.color : Palette.accent
                )
                ConditionTile(
                    symbol: "wind",
                    value: "\(Int(conditions.windMph.rounded())) mph",
                    label: "Wind Peak",
                    tint: conditions.windMph >= 20 ? RiskLevel.high.color : Palette.accent
                )
                ConditionTile(
                    symbol: "cloud.rain.fill",
                    value: "\(conditions.rain24hIn.formatted()) in",
                    label: "24h Rainfall",
                    tint: conditions.rain24hIn >= 1.0 ? HazardType.flood.color : Palette.accent
                )
                ConditionTile(
                    symbol: "drop.degreesign.fill",
                    value: "\(Int(conditions.soilMoisturePct.rounded()))%",
                    label: "Soil Saturation",
                    tint: conditions.soilMoisturePct >= 60 ? HazardType.soilSaturation.color : Palette.accent
                )
                ConditionTile(
                    symbol: "bolt.fill",
                    value: conditions.nearestStrikeMiles.map { "\($0.formatted()) mi" } ?? "None",
                    label: "Strike Distance",
                    tint: (conditions.nearestStrikeMiles ?? 99) <= LightningPolicy.stopWorkRadiusMiles ? Palette.stopWork : Palette.accent
                )
            }

            // Safety Operating Protocol Banner
            let protocolInfo = conditions.operatingProtocol
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: protocolInfo.symbol)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(protocolInfo.color)
                    .frame(width: 20)
                    .padding(.top, 1)

                VStack(alignment: .leading, spacing: 3) {
                    Text(protocolInfo.headline)
                        .font(.footnote.weight(.bold))
                        .foregroundStyle(protocolInfo.color)
                    Text(protocolInfo.detail)
                        .font(.caption2)
                        .foregroundStyle(Palette.secondaryText)
                        .lineSpacing(2)
                }

                Spacer(minLength: 0)
            }
            .padding(12)
            .background(protocolInfo.color.opacity(0.10), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(protocolInfo.color.opacity(0.22), lineWidth: 1)
            )

            // FEMA Flood Zone Footer if present
            if let zone = site.floodZone, !zone.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Palette.secondaryText)
                    Text("FEMA Flood Zone \(zone)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Palette.secondaryText)
                    Text("·")
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)
                    Text(floodZoneDescription(zone))
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)
                    Spacer()
                }
                .padding(.top, 2)
            }
        }
        .card(padding: 16, cornerRadius: 20)
    }

    private func floodZoneDescription(_ zone: String) -> String {
        switch zone.uppercased() {
        case "A", "AE", "AH", "AO", "AR", "A99":
            return "100-Year Special Flood Hazard Area"
        case "V", "VE":
            return "Coastal High Hazard Area"
        case "X":
            return "Minimal / Moderate Flood Risk"
        case "D":
            return "Undetermined Flood Risk"
        default:
            return "Designated Risk Zone"
        }
    }
}

#Preview {
    VStack(spacing: 20) {
        StopWorkBanner(hold: MockData.activeHolds[0])
        RiskBandBar(index: 7.8)
        HStack { RiskBadge(index: 2.1); RiskBadge(index: 4.8); RiskBadge(index: 6.7); RiskBadge(index: 9.2) }
        ConditionsRow(conditions: MockData.sites[0].conditions!)
    }
    .padding()
    .background(Palette.background)
    .preferredColorScheme(.dark)
}
