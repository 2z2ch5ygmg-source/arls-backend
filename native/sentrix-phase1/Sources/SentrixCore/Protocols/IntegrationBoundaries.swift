import Foundation

public protocol AuthAdapter: Sendable {
    func signIn(using draft: LoginDraft, environment: AppEnvironment) async throws -> AuthSessionDescriptor
    func signOut(currentSession: AuthSessionDescriptor?) async
}

public protocol AuthenticatedBootstrapAdapter: Sendable {
    func loadAuthenticatedBootstrap(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> String
}

public protocol RealtimeAdapter: Sendable {
    func makeRealtimeStream(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error>
}

public protocol PushAdapter: Sendable {
    func preparePushRegistration(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> String
}

public protocol AppleWeeklyAdapter: Sendable {
    func prepareAppleWeeklyWorkspace(environment: AppEnvironment) async throws -> String
}

public protocol ARLSBridgeAdapter: Sendable {
    func prepareBridgeWorkspace(environment: AppEnvironment) async throws -> String
}
