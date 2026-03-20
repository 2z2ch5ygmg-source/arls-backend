import Foundation
import SentrixCore

public struct LiveAuthenticatedBootstrapRepository: AuthenticatedBootstrapRepository {
    private let client: JSONAPIClient
    private let now: @Sendable () -> Date

    public init(
        client: JSONAPIClient,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.client = client
        self.now = now
    }

    public func loadAuthenticatedBootstrap(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> AuthenticatedBootstrapSnapshot {
        let dto: AuthenticatedBootstrapDTO = try await client.send(
            Endpoint(
                path: "/api/bootstrap-config",
                headers: ["Authorization": "Bearer \(session.accessToken)"]
            ),
            environment: environment
        )
        return AuthenticatedBootstrapMapper.map(dto, loadedAt: now())
    }
}
