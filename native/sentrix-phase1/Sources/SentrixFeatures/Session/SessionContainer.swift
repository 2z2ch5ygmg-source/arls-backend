import Foundation
import Combine
import SentrixCore

@MainActor
public final class SessionContainer: ObservableObject {
    @Published public var draft: LoginDraft = .init()
    @Published public private(set) var status: SessionStatus = .signedOut

    private let environment: AppEnvironment
    private let storedSessionRepository: any StoredSessionRepository
    private let authAdapter: any AuthAdapter

    public init(
        environment: AppEnvironment,
        storedSessionRepository: any StoredSessionRepository,
        authAdapter: any AuthAdapter
    ) {
        self.environment = environment
        self.storedSessionRepository = storedSessionRepository
        self.authAdapter = authAdapter
    }

    public var currentSession: AuthSessionDescriptor? {
        status.currentSession
    }

    public var provisionalSession: AuthSessionDescriptor? {
        status.provisionalSession
    }

    public var restoredSessionDescriptor: AuthSessionDescriptor? {
        status.restoredSessionDescriptor
    }

    public func restoreStoredSession() async {
        status = .restoring
        do {
            if let session = try await storedSessionRepository.loadStoredSession() {
                status = .verifyingRestored(session)
            } else {
                status = .signedOut
            }
        } catch let error as SentrixError {
            status = .blocked(area: nil, message: error.errorDescription ?? "Stored session could not be restored.")
        } catch {
            status = .blocked(area: nil, message: "Stored session could not be restored.")
        }
    }

    public func confirmRestoredSessionEligibility() {
        guard let session = provisionalSession else { return }
        status = .authenticated(session)
    }

    public func markRestoredSessionUnresolved(message: String) {
        if let session = restoredSessionDescriptor {
            status = .unresolvedRestored(session, message: message)
        } else {
            status = .blocked(area: .authenticatedBootstrap, message: message)
        }
    }

    public func signIn() async {
        guard draft.isComplete else {
            status = .blocked(area: nil, message: "Tenant code, username, and password are required before sign-in can run.")
            return
        }

        status = .signingIn
        do {
            let session = try await authAdapter.signIn(using: draft, environment: environment)
            try await storedSessionRepository.persistStoredSession(session)
            status = .authenticated(session)
        } catch let error as SentrixError {
            switch error {
            case .unauthorized(let message):
                status = .unauthorized(message: message)
            case .sessionExpired(let message):
                status = .expired(message: message)
            case .runtimeBlocked(let area, let message):
                status = .blocked(area: area, message: message)
            default:
                status = .blocked(area: nil, message: error.errorDescription ?? "Sign-in is unavailable in Phase 2B.")
            }
        } catch {
            status = .blocked(area: nil, message: "Sign-in is unavailable in Phase 2B.")
        }
    }

    public func logout() {
        Task {
            let currentSession = self.currentSession
            await storedSessionRepository.clearStoredSession()
            await authAdapter.signOut(currentSession: currentSession)
        }
        status = .signedOut
        draft.password = ""
    }

    public func markUnauthorized(message: String) {
        status = .unauthorized(message: message)
    }

    public func markExpired(message: String) {
        status = .expired(message: message)
    }
}
