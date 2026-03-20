import Foundation

public enum SystemSurfaceKind: String, Equatable, Sendable {
    case info
    case warning
    case error
    case blocked
    case unauthorized
    case offline
}

public enum SystemSurfaceActionKind: String, Equatable, Sendable {
    case retry
    case returnToLogin

    public var title: String {
        switch self {
        case .retry:
            return "Retry"
        case .returnToLogin:
            return "Return To Login"
        }
    }
}

public struct SystemSurfaceModel: Equatable, Sendable {
    public let kind: SystemSurfaceKind
    public let title: String
    public let message: String
    public let actionKind: SystemSurfaceActionKind?
    public let footnote: String?

    public init(
        kind: SystemSurfaceKind,
        title: String,
        message: String,
        actionKind: SystemSurfaceActionKind? = nil,
        footnote: String? = nil
    ) {
        self.kind = kind
        self.title = title
        self.message = message
        self.actionKind = actionKind
        self.footnote = footnote
    }
}

public extension SentrixError {
    var recommendsRetry: Bool {
        switch self {
        case .transport, .decoding, .server:
            return true
        case .invalidBaseURL, .unauthorized, .sessionExpired, .runtimeBlocked:
            return false
        }
    }

    var systemSurface: SystemSurfaceModel {
        switch self {
        case .invalidBaseURL:
            return SystemSurfaceModel(
                kind: .error,
                title: "Invalid Base URL",
                message: errorDescription ?? "The configured Sentrix base URL is invalid."
            )
        case .transport(let message):
            return SystemSurfaceModel(
                kind: .offline,
                title: "Offline Placeholder",
                message: message,
                actionKind: .retry,
                footnote: "Phase 1 does not inherit web PWA or service-worker behavior into native."
            )
        case .decoding(let message):
            return SystemSurfaceModel(
                kind: .error,
                title: "Bootstrap Payload Drift",
                message: message,
                actionKind: .retry,
                footnote: "Public bootstrap tolerates minor schema drift, but incompatible payload changes still fail loudly."
            )
        case .server(_, let message):
            return SystemSurfaceModel(
                kind: .error,
                title: "Server Error",
                message: message,
                actionKind: .retry
            )
        case .unauthorized(let message):
            return SystemSurfaceModel(
                kind: .unauthorized,
                title: "Unauthorized",
                message: message,
                actionKind: .returnToLogin
            )
        case .sessionExpired(let message):
            return SystemSurfaceModel(
                kind: .error,
                title: "Session Expired",
                message: message,
                actionKind: .returnToLogin
            )
        case .runtimeBlocked(let area, let message):
            return SystemSurfaceModel(
                kind: .blocked,
                title: area.title,
                message: message,
                footnote: area.blockerTag
            )
        }
    }
}

public extension SessionStatus {
    var systemSurface: SystemSurfaceModel? {
        switch self {
        case .signedOut, .restoring, .verifyingRestored, .signingIn, .authenticated:
            return nil
        case .unresolvedRestored(_, let message):
            return SystemSurfaceModel(
                kind: .blocked,
                title: "Unresolved Restored Session",
                message: message,
                footnote: RuntimeBlockedArea.authenticatedBootstrap.blockerTag
            )
        case .blocked(let area, let message):
            return SystemSurfaceModel(
                kind: .blocked,
                title: area?.title ?? "Runtime-Blocked",
                message: message,
                footnote: area?.blockerTag
            )
        case .unauthorized(let message):
            return SystemSurfaceModel(
                kind: .unauthorized,
                title: "Unauthorized",
                message: message,
                actionKind: .returnToLogin
            )
        case .expired(let message):
            return SystemSurfaceModel(
                kind: .error,
                title: "Session Expired",
                message: message,
                actionKind: .returnToLogin
            )
        }
    }
}
