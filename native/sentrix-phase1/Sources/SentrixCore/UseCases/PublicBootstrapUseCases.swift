import Foundation

public struct LoadPublicBootstrapUseCase: Sendable {
    private let repository: any PublicBootstrapRepository

    public init(repository: any PublicBootstrapRepository) {
        self.repository = repository
    }

    public func execute(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot {
        try await repository.loadPublicBootstrap(environment: environment)
    }
}
