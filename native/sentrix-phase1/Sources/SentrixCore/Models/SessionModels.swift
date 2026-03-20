import Foundation

public struct LoginDraft: Equatable, Sendable {
    public var tenantCode: String
    public var username: String
    public var password: String

    public init(tenantCode: String = "", username: String = "", password: String = "") {
        self.tenantCode = tenantCode
        self.username = username
        self.password = password
    }

    public var isComplete: Bool {
        !tenantCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !password.isEmpty
    }
}

public struct AuthSessionDescriptor: Equatable, Sendable {
    public let accessToken: String
    public let user: StoredSessionUserSummary
    public let issuedAt: Date
    public let persistenceSource: SessionPersistenceSource
    public let storageKeys: [String]

    public init(
        accessToken: String,
        user: StoredSessionUserSummary,
        issuedAt: Date,
        persistenceSource: SessionPersistenceSource,
        storageKeys: [String]
    ) {
        self.accessToken = accessToken
        self.user = user
        self.issuedAt = issuedAt
        self.persistenceSource = persistenceSource
        self.storageKeys = storageKeys
    }

    public var userLabel: String {
        "\(user.fullName) (\(user.role))"
    }
}

public struct StoredSessionUserSummary: Equatable, Sendable {
    public let id: Int
    public let username: String
    public let loginID: String
    public let fullName: String
    public let role: String
    public let group: String
    public let siteID: String
    public let siteCode: String
    public let siteName: String
    public let tenantID: String
    public let location: String
    public let status: String
    public let linkedEmployeeID: Int
    public let employeeID: Int

    public init(
        id: Int,
        username: String,
        loginID: String,
        fullName: String,
        role: String,
        group: String,
        siteID: String,
        siteCode: String,
        siteName: String,
        tenantID: String,
        location: String,
        status: String,
        linkedEmployeeID: Int,
        employeeID: Int
    ) {
        self.id = id
        self.username = username
        self.loginID = loginID
        self.fullName = fullName
        self.role = role
        self.group = group
        self.siteID = siteID
        self.siteCode = siteCode
        self.siteName = siteName
        self.tenantID = tenantID
        self.location = location
        self.status = status
        self.linkedEmployeeID = linkedEmployeeID
        self.employeeID = employeeID
    }
}

public enum AuthenticatedShellScope: Equatable, Sendable {
    case hqSafe(role: String)
    case fieldObserved(role: String)

    public var role: String {
        switch self {
        case .hqSafe(let role), .fieldObserved(let role):
            return role
        }
    }

    public var title: String {
        switch self {
        case .hqSafe:
            return "HQ-Safe Authenticated Shell"
        case .fieldObserved:
            return "Field-Observed Authenticated Shell"
        }
    }

    public var diagnosticsLabel: String {
        switch self {
        case .hqSafe(let role):
            return "hq_safe: \(role)"
        case .fieldObserved(let role):
            return "field_observed: \(role)"
        }
    }

    public var runtimeAccessLabel: String {
        switch self {
        case .hqSafe:
            return "all_scoped"
        case .fieldObserved:
            return "site_scoped"
        }
    }

    public var isHQSafe: Bool {
        if case .hqSafe = self {
            return true
        }
        return false
    }

    public var isFieldObserved: Bool {
        if case .fieldObserved = self {
            return true
        }
        return false
    }
}

public enum AuthenticatedNavigationTarget: String, CaseIterable, Hashable, Identifiable, Sendable {
    case appleWeekly
    case supportSubmissions
    case pushDiagnostics

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .appleWeekly:
            return "Apple Weekly"
        case .supportSubmissions:
            return "Support Submission"
        case .pushDiagnostics:
            return "Push Diagnostics"
        }
    }

    public var fieldBlockedMessage: String {
        switch self {
        case .appleWeekly:
            return "Apple Weekly is hidden for runtime-confirmed field roles. Direct navigation to this HQ-only surface remains blocked."
        case .supportSubmissions:
            return "Support-submission behavior is not runtime-confirmed for field roles. This HQ-only handoff surface remains blocked."
        case .pushDiagnostics:
            return "Server-side push diagnostics are not runtime-confirmed for field roles. This HQ-only surface remains blocked."
        }
    }

    public var unresolvedFootnote: String {
        switch self {
        case .appleWeekly:
            return "HQ-confirmed only. Field Apple Weekly behavior remains unresolved."
        case .supportSubmissions:
            return "Field support-submission runtime remains unresolved."
        case .pushDiagnostics:
            return "Field push diagnostics/runtime behavior remains unresolved."
        }
    }
}

public extension StoredSessionUserSummary {
    var normalizedRole: String {
        role.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var canonicalRoleMarker: String {
        normalizedRole
            .uppercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
    }

    var normalizedStatus: String {
        status.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var authenticatedShellScope: AuthenticatedShellScope? {
        switch canonicalRoleMarker {
        case "HQ_ADMIN":
            return .hqSafe(role: "HQ_ADMIN")
        case "SUPERVISOR", "OFFICER":
            return .fieldObserved(role: canonicalRoleMarker)
        default:
            return nil
        }
    }
}

public enum SessionPersistenceSource: String, Equatable, Sendable {
    case storedSocKeys
}

public enum SessionStatus: Equatable, Sendable {
    case signedOut
    case restoring
    case verifyingRestored(AuthSessionDescriptor)
    case signingIn
    case unresolvedRestored(AuthSessionDescriptor, message: String)
    case blocked(area: RuntimeBlockedArea?, message: String)
    case unauthorized(message: String)
    case expired(message: String)
    case authenticated(AuthSessionDescriptor)
}

public extension SessionStatus {
    var currentSession: AuthSessionDescriptor? {
        if case .authenticated(let descriptor) = self {
            return descriptor
        }
        return nil
    }

    var provisionalSession: AuthSessionDescriptor? {
        if case .verifyingRestored(let descriptor) = self {
            return descriptor
        }
        return nil
    }

    var restoredSessionDescriptor: AuthSessionDescriptor? {
        switch self {
        case .verifyingRestored(let descriptor):
            return descriptor
        case .unresolvedRestored(let descriptor, _):
            return descriptor
        case .authenticated(let descriptor):
            return descriptor
        default:
            return nil
        }
    }
}

public enum RuntimeBlockedArea: String, CaseIterable, Identifiable, Sendable {
    case productionAuthMode
    case authenticatedBootstrap
    case realtimeTransport
    case pushRegistration
    case appleWeekly
    case arlsBridge
    case startupRecovery

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .productionAuthMode:
            return "Production Auth Mode"
        case .authenticatedBootstrap:
            return "Authenticated Bootstrap"
        case .realtimeTransport:
            return "Realtime Transport"
        case .pushRegistration:
            return "Push Registration / Delivery"
        case .appleWeekly:
            return "Apple Weekly"
        case .arlsBridge:
            return "ARLS Bridge"
        case .startupRecovery:
            return "Startup Recovery / Read-Only"
        }
    }

    public var blockerTag: String {
        "BLOCKED-BY-RUNTIME[\(rawValue)]"
    }

    public var summary: String {
        switch self {
        case .productionAuthMode:
            return "Production auth branch is runtime-blocked until authenticated capture confirms local, HR, or hybrid behavior."
        case .authenticatedBootstrap:
            return "HQ stored-session bootstrap is open, but field and universal authenticated bootstrap overrides remain blocked."
        case .realtimeTransport:
            return "HQ SSE transport is open, but field/universal transport behavior and event ordering remain blocked."
        case .pushRegistration:
            return "Server-side push diagnostics are open, but native APNs registration and device receipt remain blocked."
        case .appleWeekly:
            return "HQ Apple Weekly read/readiness/conflict/dry-run is open, but mutation, rollout, and write flows remain blocked."
        case .arlsBridge:
            return "Sentrix operator handoff is open, but internal ARLS workbook ingress/apply behavior remains blocked."
        case .startupRecovery:
            return "Deployed startup recovery and operational read-only behavior must remain unfrozen until runtime restart evidence exists."
        }
    }

    public var phase1FailureMessage: String {
        switch self {
        case .productionAuthMode:
            return "Fresh sign-in remains blocked until production auth routing is captured in runtime."
        case .authenticatedBootstrap:
            return "Only HQ-safe authenticated bootstrap is open. Field and universal bootstrap behavior remains blocked."
        case .realtimeTransport:
            return "Only HQ SSE transport is open. Field/universal realtime behavior remains blocked."
        case .pushRegistration:
            return "Native push registration and APNs device delivery remain blocked."
        case .appleWeekly:
            return "Apple Weekly mutation, rollout, and live write remain blocked."
        case .arlsBridge:
            return "Internal ARLS bridge workbook behaviors remain blocked."
        case .startupRecovery:
            return "Startup recovery and degraded read-only operations remain blocked until deployed restart evidence exists."
        }
    }

    public var phase1StubBehavior: String {
        switch self {
        case .productionAuthMode:
            return "Fresh sign-in stays blocked. The app may continue only from a stored runtime-confirmed HQ or field-observed session."
        case .authenticatedBootstrap:
            return "Universal authenticated bootstrap remains blocked; only HQ-safe repository-backed bootstrap is implemented."
        case .realtimeTransport:
            return "HQ runtime uses SSE. Field/universal transport and event ordering remain blocked."
        case .pushRegistration:
            return "Server-side push diagnostics may run, but native token registration and device receipt remain blocked."
        case .appleWeekly:
            return "HQ read-side Apple Weekly is implemented; mutation/write paths remain blocked."
        case .arlsBridge:
            return "Operator handoff is implemented; internal ARLS workbook processing stays blocked."
        case .startupRecovery:
            return "Read-only recovery remains public-observed only and no startup repair workflow is implemented in native."
        }
    }

    public var sourceDocuments: [String] {
        [
            "sentrix_reverse_engineering_audit_closure_pass_1_2026-03-19.md",
            "sentrix_reverse_engineering_audit_public_runtime_addendum_2026-03-19.md",
            "sentrix_staged_native_implementation_design_2026-03-19.md",
        ]
    }
}

public enum SentrixError: Error, Equatable, Sendable {
    case invalidBaseURL
    case transport(message: String)
    case decoding(message: String)
    case server(statusCode: Int, message: String)
    case unauthorized(message: String)
    case sessionExpired(message: String)
    case runtimeBlocked(area: RuntimeBlockedArea, message: String)
}

extension SentrixError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "The configured Sentrix base URL is invalid."
        case .transport(let message):
            return message
        case .decoding(let message):
            return message
        case .server(_, let message):
            return message
        case .unauthorized(let message):
            return message
        case .sessionExpired(let message):
            return message
        case .runtimeBlocked(_, let message):
            return message
        }
    }
}
