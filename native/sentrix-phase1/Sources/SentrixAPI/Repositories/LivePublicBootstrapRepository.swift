import Foundation
import SentrixCore

public struct LivePublicBootstrapRepository: PublicBootstrapRepository, HealthRepository, PublicAppConfigRepository, BuildInfoRepository {
    private let client: JSONAPIClient
    private let now: @Sendable () -> Date

    public init(client: JSONAPIClient, now: @escaping @Sendable () -> Date = Date.init) {
        self.client = client
        self.now = now
    }

    public func loadPublicBootstrap(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot {
        async let health = fetchHealth(environment: environment)
        async let appConfig = fetchPublicAppConfig(environment: environment)
        async let buildInfo = fetchBuildInfo(environment: environment)

        let resolvedHealth = try await health
        let resolvedAppConfig = try await appConfig
        let resolvedBuildInfo = try await buildInfo

        return PublicBootstrapSnapshot(
            environment: environment,
            health: resolvedHealth,
            appConfig: resolvedAppConfig,
            buildInfo: resolvedBuildInfo,
            loadedAt: now()
        )
    }

    public func fetchHealth(environment: AppEnvironment) async throws -> DeploymentHealth {
        let dto: HealthDTO = try await client.send(Endpoint(path: "/health"), environment: environment)
        return PublicBootstrapMapper.map(dto)
    }

    public func fetchPublicAppConfig(environment: AppEnvironment) async throws -> PublicAppConfig {
        let dto: AppConfigDTO = try await client.send(Endpoint(path: "/api/app-config"), environment: environment)
        return PublicBootstrapMapper.map(dto)
    }

    public func fetchBuildInfo(environment: AppEnvironment) async throws -> BuildProvenance {
        let dto: BuildInfoDTO = try await client.send(Endpoint(path: "/api/build-info"), environment: environment)
        return PublicBootstrapMapper.map(dto)
    }
}
