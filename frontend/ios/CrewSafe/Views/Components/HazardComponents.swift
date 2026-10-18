import Charts
import SwiftUI

// MARK: Hazard Index

/// 270° gauge for the 0-10 Hazard Index.
struct HazardGauge: View {
    let index: Double
    var size: CGFloat = 150

    var body: some View {
        let level = RiskLevel(index: index)
        let style = StrokeStyle(lineWidth: size * 0.09, lineCap: .round)

        ZStack {
            Group {
                Circle()
                    .trim(from: 0, to: 0.75)
                    .stroke(Color.white.opacity(0.08), style: style)
                Circle()
                    .trim(from: 0, to: 0.75 * min(max(index / 10, 0), 1))
                    .stroke(level.color.gradient, style: style)
            }
            .rotationEffect(.degrees(135))
            VStack(spacing: 0) {
                Text(index.oneDecimal)
                    .font(.system(size: size * 0.28, weight: .bold, design: .rounded))
                    .contentTransition(.numericText(value: index))
                Text(level.label.uppercased())
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(level.color)
            }
        }
        .frame(width: size, height: size)
        .animation(.spring, value: index)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Hazard index \(index.oneDecimal) out of 10, \(level.label)")
    }
}

/// Four-band bar with a marker at the current index. Equal-width capsules stay
/// readable at any card width; the marker still tracks the 0–10 scale.
struct RiskBandBar: View {
    let index: Double

    var body: some View {
        let current = RiskLevel(index: index)
        ZStack(alignment: .leading) {
            HStack(spacing: 4) {
                ForEach(RiskLevel.allCases, id: \.self) { level in
                    Capsule()
                        .fill(level.color.opacity(level == current ? 1 : 0.28))
                        .frame(maxWidth: .infinity)
                        .frame(height: 6)
                }
            }
            GeometryReader { geo in
                Circle()
                    .fill(.white)
                    .frame(width: 10, height: 10)
                    .shadow(color: .black.opacity(0.45), radius: 1.5)
                    .offset(x: min(max(geo.size.width * index / 10 - 5, 0), max(geo.size.width - 10, 0)))
                    .frame(maxHeight: .infinity, alignment: .center)
            }
        }
        .frame(height: 12)
        .animation(.spring, value: index)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Hazard index \(index.oneDecimal) of 10")
    }
}

struct RiskBadge: View {
    let index: Double
    var large = false

    var body: some View {
        let color = RiskLevel(index: index).color
        Text(index.oneDecimal)
            .font((large ? Font.title3 : .subheadline).monospacedDigit().weight(.bold))
            .foregroundStyle(color)
            .frame(minWidth: large ? 52 : 40)
            .padding(.vertical, large ? 8 : 5)
            .padding(.horizontal, 8)
            .background(color.opacity(0.16), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(color.opacity(0.45)))
            .contentTransition(.numericText(value: index))
            .animation(.default, value: index)
    }
}

struct TrendLabel: View {
    let site: Site

    var body: some View {
        let driver = site.topFactor.map { " · \($0.type.shortName.lowercased())-driven" } ?? ""
        Group {
            if let trend = site.trend, abs(trend) >= 0.05 {
                let arrow = Text(Image(systemName: trend > 0 ? "arrow.up" : "arrow.down"))
                    .foregroundStyle(trend > 0 ? RiskLevel.high.color : RiskLevel.low.color)
                let since = site.trendStart?.formatted(.dateTime.hour()) ?? "this morning"
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
                        colors: [color.opacity(0.35), color.opacity(0.02)], startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.catmullRom)
                LineMark(x: .value("Time", point.time), y: .value("Index", point.value))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round))
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
                Image(systemName: factor.type.symbol)
                    .foregroundStyle(factor.type.color)
                    .frame(width: 20)
                Text(factor.type.displayName).font(.subheadline.weight(.medium))
                Spacer()
                Text(factor.score.oneDecimal)
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .foregroundStyle(RiskLevel(index: factor.score).color)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(RiskLevel(index: factor.score).color.gradient)
                        .frame(width: geo.size.width * min(factor.score, 10) / 10)
                }
            }
            .frame(height: 6)
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
    var size: CGFloat = 60

    var body: some View {
        ZStack {
            Circle().stroke(Color.white.opacity(0.25), lineWidth: 4)
            Circle()
                .trim(from: 0, to: fraction)
                .stroke(Color.white, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(label)
                .font(.system(size: size * 0.24, weight: .bold, design: .rounded).monospacedDigit())
        }
        .frame(width: size, height: size)
    }
}

private struct DiagonalStripes: View {
    var body: some View {
        Canvas { context, size in
            var path = Path()
            var x: CGFloat = -size.height
            while x < size.width {
                path.move(to: CGPoint(x: x, y: size.height))
                path.addLine(to: CGPoint(x: x + size.height, y: 0))
                x += 14
            }
            context.stroke(path, with: .color(.white.opacity(0.07)), lineWidth: 5)
        }
    }
}

/// Red stop-work banner with a live countdown ring that resets on every strike.
struct StopWorkBanner: View {
    let hold: LightningHold
    var siteName: String?

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let remaining = hold.remaining(at: context.date)
            HStack(spacing: 14) {
                Image(systemName: "bolt.fill")
                    .font(.title2.weight(.bold))
                    .frame(width: 46, height: 46)
                    .background(Color.white.opacity(0.18), in: Circle())
                    .symbolEffect(.pulse)
                VStack(alignment: .leading, spacing: 3) {
                    Text(siteName.map { "STOP WORK · \($0.uppercased())" } ?? "STOP WORK · LIGHTNING")
                        .font(.caption.weight(.heavy))
                        .opacity(0.9)
                        .lineLimit(1)
                    Text("Strike \(hold.lastDistanceMiles.formatted()) mi\(hold.lastDirection.map { " \($0)" } ?? "") of site")
                        .font(.headline)
                    Text("Shelter now · resets on new strike")
                        .font(.caption)
                        .opacity(0.85)
                }
                Spacer(minLength: 8)
                CountdownRing(fraction: remaining / hold.allClearInterval, label: remaining.countdown)
            }
            .foregroundStyle(.white)
            .padding(16)
            .background {
                ZStack {
                    LinearGradient(
                        colors: [Color(red: 0.93, green: 0.2, blue: 0.24), Color(red: 0.98, green: 0.36, blue: 0.3)],
                        startPoint: .leading, endPoint: .trailing)
                    DiagonalStripes()
                }
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            }
            .shadow(color: Palette.stopWork.opacity(0.35), radius: 16, y: 6)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Stop work, lightning. \(remaining.countdown) until all clear.")
        }
    }
}

// MARK: Alerts

struct SeverityTag: View {
    let severity: AlertSeverity

    var body: some View {
        Text(severity.label.uppercased())
            .font(.caption2.weight(.bold))
            .foregroundStyle(severity.color)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(severity.color.opacity(0.15), in: Capsule())
    }
}

struct AlertRow: View {
    let alert: HazardAlert
    let siteName: String
    var acknowledged = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: alert.type.symbol)
                .font(.body.weight(.semibold))
                .foregroundStyle(alert.severity == .stopWork ? .white : alert.type.color)
                .frame(width: 36, height: 36)
                .background(
                    alert.severity == .stopWork ? AnyShapeStyle(Palette.stopWork.gradient) : AnyShapeStyle(alert.type.color.opacity(0.15)),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if !acknowledged {
                        Circle().fill(Palette.accent).frame(width: 7, height: 7)
                    }
                    Text(alert.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                    Spacer(minLength: 4)
                    Text(alert.issuedAt.relativeShort)
                        .font(.caption2)
                        .foregroundStyle(Palette.tertiaryText)
                }
                Text(alert.message)
                    .font(.footnote)
                    .foregroundStyle(Palette.secondaryText)
                HStack(spacing: 6) {
                    SeverityTag(severity: alert.severity)
                    Text(siteName).font(.caption2.weight(.medium)).foregroundStyle(Palette.secondaryText)
                    if let source = alert.source {
                        Text("· \(source)").font(.caption2).foregroundStyle(Palette.tertiaryText)
                    }
                }
            }
        }
        .opacity(acknowledged ? 0.62 : 1)
        .contentShape(Rectangle())
    }
}

// MARK: Misc

struct ConnectionPill: View {
    let status: ConnectionStatus
    let isMock: Bool

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(status.color)
                .frame(width: 7, height: 7)
                .shadow(color: status.color, radius: status == .live ? 4 : 0)
            Text(status.label(isMock: isMock)).font(.caption.weight(.semibold))
        }
        .foregroundStyle(status.color)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(status.color.opacity(0.14), in: Capsule())
    }
}

struct ConditionTile: View {
    let symbol: String
    let value: String
    let label: String
    var tint: Color = .white

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol).font(.subheadline).foregroundStyle(tint)
            Text(value).font(.headline.monospacedDigit())
            Text(label).font(.caption2).foregroundStyle(Palette.secondaryText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Palette.stroke))
    }
}

struct ConditionsRow: View {
    let conditions: SiteConditions

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { tiles }
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                tiles
            }
        }
    }

    @ViewBuilder
    private var tiles: some View {
        ConditionTile(
            symbol: "thermometer.sun.fill", value: "\(Int(conditions.heatIndexF))°", label: "Heat index",
            tint: conditions.heatIndexF >= 105 ? RiskLevel.high.color : .white)
        ConditionTile(
            symbol: "bolt.fill",
            value: conditions.nearestStrikeMiles.map { "\($0.formatted()) mi" } ?? "None",
            label: "Nearest strike",
            tint: (conditions.nearestStrikeMiles ?? 99) <= LightningPolicy.stopWorkRadiusMiles ? Palette.stopWork : .white)
        ConditionTile(
            symbol: "cloud.rain.fill", value: "\(conditions.rain24hIn.formatted()) in", label: "Rain 24h",
            tint: conditions.rain24hIn >= 2 ? HazardType.flood.color : .white)
        ConditionTile(symbol: "wind", value: "\(Int(conditions.windMph)) mph", label: "Wind")
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
                if let symbol { Image(systemName: symbol).font(.caption) }
                Text(title).font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(isSelected ? Color.black : .white)
            .padding(.horizontal, 11)
            .padding(.vertical, 6)
            .background(isSelected ? AnyShapeStyle(Color.white) : AnyShapeStyle(.ultraThinMaterial), in: Capsule())
            .overlay(Capsule().stroke(Palette.stroke))
        }
        .buttonStyle(.plain)
    }
}

struct BriefingEventRow: View {
    let event: SiteBriefing.Event
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 4) {
                Image(systemName: event.type.symbol)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(event.type.color)
                    .frame(width: 30, height: 30)
                    .background(event.type.color.opacity(0.16), in: Circle())
                if !isLast {
                    Rectangle().fill(Palette.stroke).frame(width: 2).frame(maxHeight: .infinity)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(event.title).font(.subheadline.weight(.semibold))
                    Spacer(minLength: 6)
                    if event.isActive {
                        Text("NOW")
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(Palette.stopWork)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Palette.stopWork.opacity(0.16), in: Capsule())
                    } else {
                        Text(event.time.shortTime).font(.caption).foregroundStyle(Palette.secondaryText)
                    }
                }
                Text(event.detail).font(.caption).foregroundStyle(Palette.secondaryText)
            }
            .padding(.bottom, isLast ? 0 : 14)
        }
    }
}

struct SectionHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.headline)
            Spacer()
            trailing
        }
    }
}

extension SectionHeader where Trailing == EmptyView {
    init(title: String) {
        self.init(title: title) { EmptyView() }
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
