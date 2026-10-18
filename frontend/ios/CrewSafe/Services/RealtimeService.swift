import Foundation

enum ConnectionStatus: Sendable {
    case connecting, live, offline
}

enum RealtimeUpdate: Sendable {
    case connection(ConnectionStatus)
    case event(RealtimeEvent)
}

/// A long-lived stream of updates from the backend. It only runs while the app
/// is in the foreground. Background delivery goes through APNs.
protocol RealtimeService: Sendable {
    /// `siteIds` are the sites the user follows (their nearest sites). The backend sends
    /// updates for those, plus stop-work and severe events anywhere in the state.
    func updates(subscribedTo siteIds: [Int]) -> AsyncStream<RealtimeUpdate>
}

/// Emits a dummy event every few seconds, starting shortly after connecting.
struct MockRealtimeService: RealtimeService {
    var interval: ClosedRange<Double> = 6...12

    func updates(subscribedTo siteIds: [Int]) -> AsyncStream<RealtimeUpdate> {
        AsyncStream { continuation in
            let task = Task.detached(priority: .utility) {
                var feed = MockFeed(focusSiteIds: siteIds)
                continuation.yield(.connection(.connecting))
                try? await Task.sleep(for: .milliseconds(600))
                continuation.yield(.connection(.live))
                try? await Task.sleep(for: .seconds(3))
                while !Task.isCancelled {
                    if let event = feed.next() {
                        continuation.yield(.event(event))
                    }
                    try? await Task.sleep(for: .seconds(Double.random(in: interval)))
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

/// WebSocket client for the backend's realtime channel. Reconnects with exponential backoff.
struct WebSocketRealtimeService: RealtimeService {
    let url: URL
    var session: URLSession = .shared

    func updates(subscribedTo siteIds: [Int]) -> AsyncStream<RealtimeUpdate> {
        AsyncStream { continuation in
            let task = Task {
                var backoff: Double = 1
                var lastSeq: Int?
                while !Task.isCancelled {
                    continuation.yield(.connection(.connecting))
                    let socket = session.webSocketTask(with: url)
                    socket.resume()
                    await withTaskCancellationHandler {
                        do {
                            try await socket.send(.string(Self.subscribeMessage(siteIds: siteIds, lastSeq: lastSeq)))
                            while true {
                                let message = try await socket.receive()
                                backoff = 1
                                continuation.yield(.connection(.live))
                                let data = Self.data(of: message)
                                if let seq = data.flatMap({ try? JSONCoding.decoder.decode(Envelope.self, from: $0) })?.seq {
                                    lastSeq = seq
                                }
                                if let data, let event = try? JSONCoding.decoder.decode(RealtimeEvent.self, from: data) {
                                    continuation.yield(.event(event))
                                }
                            }
                        } catch {
                            socket.cancel(with: .goingAway, reason: nil)
                        }
                    } onCancel: {
                        socket.cancel(with: .goingAway, reason: nil)
                    }
                    continuation.yield(.connection(.offline))
                    try? await Task.sleep(for: .seconds(backoff))
                    backoff = min(backoff * 2, 30)
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Server messages carry an increasing `seq` so a reconnect can resume without a full reload.
    private struct Envelope: Decodable {
        let seq: Int?
    }

    private struct Subscribe: Encodable {
        let type = "subscribe"
        let payload: Payload

        struct Payload: Encodable {
            let siteIds: [Int]
            let includeSevereStatewide: Bool
            let lastSeq: Int?
        }
    }

    private static func subscribeMessage(siteIds: [Int], lastSeq: Int?) -> String {
        let message = Subscribe(payload: .init(siteIds: siteIds, includeSevereStatewide: true, lastSeq: lastSeq))
        let data = (try? JSONCoding.encoder.encode(message)) ?? Data()
        return String(decoding: data, as: UTF8.self)
    }

    private static func data(of message: URLSessionWebSocketTask.Message) -> Data? {
        switch message {
        case .data(let payload): payload
        case .string(let text): Data(text.utf8)
        @unknown default: nil
        }
    }
}
