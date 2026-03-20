import Foundation
import Combine
import SentrixCore

@MainActor
public final class AuthenticatedShellContainer: ObservableObject {
    private static let hqSafeRoleMarker = "HQ_ADMIN"

    public enum State: Equatable {
        case idle
        case loading
        case loaded(AuthenticatedBootstrapSnapshot)
        case failed(SentrixError)
    }

    @Published public private(set) var state: State = .idle

    private let repository: any AuthenticatedBootstrapRepository
    private let environment: AppEnvironment

    public init(
        repository: any AuthenticatedBootstrapRepository,
        environment: AppEnvironment
    ) {
        self.repository = repository
        self.environment = environment
    }

    @discardableResult
    public func load(session: AuthSessionDescriptor) async -> Bool {
        state = .loading
        do {
            let snapshot = try await repository.loadAuthenticatedBootstrap(
                session: session,
                environment: environment
            )
            guard snapshot.user.authenticatedShellScope == .hqSafe(role: Self.hqSafeRoleMarker) else {
                let error = SentrixError.runtimeBlocked(
                    area: .authenticatedBootstrap,
                    message: "Restored session role '\(snapshot.user.role)' is not proven HQ-safe for Phase 2B."
                )
                state = .failed(error)
                return false
            }
            state = .loaded(snapshot)
            return true
        } catch let error as SentrixError {
            state = .failed(error)
            return false
        } catch {
            state = .failed(.transport(message: "Authenticated bootstrap failed."))
            return false
        }
    }

    public func reset() {
        state = .idle
    }
}
