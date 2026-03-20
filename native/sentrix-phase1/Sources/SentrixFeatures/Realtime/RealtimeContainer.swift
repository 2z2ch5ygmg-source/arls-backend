import Foundation
import Combine
import SentrixCore

@MainActor
public final class RealtimeContainer: ObservableObject {
    @Published public private(set) var snapshot = RealtimeSnapshot(
        transport: .sse,
        endpoint: "",
        status: .idle,
        recentLines: []
    )

    private let adapter: any RealtimeAdapter
    private var listeningTask: Task<Void, Never>?

    public init(adapter: any RealtimeAdapter) {
        self.adapter = adapter
    }

    public func connect(session: AuthSessionDescriptor, environment: AppEnvironment) async {
        disconnect()
        snapshot = RealtimeSnapshot(transport: .sse, endpoint: "", status: .connecting, recentLines: [])

        let stream = adapter.makeRealtimeStream(session: session, environment: environment)
        listeningTask = Task {
            do {
                for try await event in stream {
                    handle(event)
                }
                if case .failed = snapshot.status {
                    return
                }
                snapshot = RealtimeSnapshot(
                    transport: snapshot.transport,
                    endpoint: snapshot.endpoint,
                    status: .disconnected,
                    recentLines: snapshot.recentLines
                )
            } catch let error as SentrixError {
                snapshot = RealtimeSnapshot(
                    transport: snapshot.transport,
                    endpoint: snapshot.endpoint,
                    status: .failed(error.errorDescription ?? "Realtime failed."),
                    recentLines: snapshot.recentLines
                )
            } catch {
                snapshot = RealtimeSnapshot(
                    transport: snapshot.transport,
                    endpoint: snapshot.endpoint,
                    status: .failed("Realtime failed."),
                    recentLines: snapshot.recentLines
                )
            }
        }
    }

    public func disconnect() {
        listeningTask?.cancel()
        listeningTask = nil
        if case .idle = snapshot.status {
            return
        }
        snapshot = RealtimeSnapshot(
            transport: snapshot.transport,
            endpoint: snapshot.endpoint,
            status: .disconnected,
            recentLines: snapshot.recentLines
        )
    }

    private func handle(_ event: RealtimeStreamEvent) {
        switch event {
        case .opened(let endpoint, _):
            snapshot = RealtimeSnapshot(
                transport: .sse,
                endpoint: endpoint,
                status: .connected,
                recentLines: snapshot.recentLines
            )
        case .line(let line):
            var lines = snapshot.recentLines
            if !line.isEmpty {
                lines.append(line)
            }
            if lines.count > 8 {
                lines.removeFirst(lines.count - 8)
            }
            snapshot = RealtimeSnapshot(
                transport: snapshot.transport,
                endpoint: snapshot.endpoint,
                status: snapshot.status,
                recentLines: lines
            )
        case .closed:
            snapshot = RealtimeSnapshot(
                transport: snapshot.transport,
                endpoint: snapshot.endpoint,
                status: .disconnected,
                recentLines: snapshot.recentLines
            )
        }
    }
}
