import Foundation

public enum RealtimeTransportKind: String, Equatable, Sendable {
    case sse
}

public enum RealtimeConnectionStatus: Equatable, Sendable {
    case idle
    case connecting
    case connected
    case disconnected
    case failed(String)
}

public enum RealtimeStreamEvent: Equatable, Sendable {
    case opened(endpoint: String, contentType: String)
    case line(String)
    case closed
}

public struct RealtimeSnapshot: Equatable, Sendable {
    public let transport: RealtimeTransportKind
    public let endpoint: String
    public let status: RealtimeConnectionStatus
    public let recentLines: [String]

    public init(
        transport: RealtimeTransportKind,
        endpoint: String,
        status: RealtimeConnectionStatus,
        recentLines: [String]
    ) {
        self.transport = transport
        self.endpoint = endpoint
        self.status = status
        self.recentLines = recentLines
    }
}
