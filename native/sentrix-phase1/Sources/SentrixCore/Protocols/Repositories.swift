import Foundation

public protocol PublicBootstrapRepository: Sendable {
    func loadPublicBootstrap(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot
}

public protocol HealthRepository: Sendable {
    func fetchHealth(environment: AppEnvironment) async throws -> DeploymentHealth
}

public protocol PublicAppConfigRepository: Sendable {
    func fetchPublicAppConfig(environment: AppEnvironment) async throws -> PublicAppConfig
}

public protocol BuildInfoRepository: Sendable {
    func fetchBuildInfo(environment: AppEnvironment) async throws -> BuildProvenance
}

public protocol StoredSessionRepository: Sendable {
    func loadStoredSession() async throws -> AuthSessionDescriptor?
    func persistStoredSession(_ session: AuthSessionDescriptor) async throws
    func clearStoredSession() async
}

public protocol AuthenticatedBootstrapRepository: Sendable {
    func loadAuthenticatedBootstrap(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> AuthenticatedBootstrapSnapshot
}

public protocol AppleWeeklyReadRepository: Sendable {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: AppleWeeklyContext
    ) async throws -> AppleWeeklyWorkspace
}

public protocol SupportSubmissionRepository: Sendable {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: SupportSubmissionContext
    ) async throws -> SupportSubmissionWorkspace
}

public protocol PushDiagnosticsRepository: Sendable {
    func runPushTest(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> PushTestResult
}
