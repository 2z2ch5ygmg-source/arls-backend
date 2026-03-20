import Foundation
import SentrixCore

public struct Phase1StubAuthAdapter: AuthAdapter {
    public init() {}

    public func signIn(using draft: LoginDraft, environment: AppEnvironment) async throws -> AuthSessionDescriptor {
        // BLOCKED-BY-RUNTIME[productionAuthMode]
        throw SentrixError.runtimeBlocked(
            area: .productionAuthMode,
            message: RuntimeBlockedArea.productionAuthMode.phase1FailureMessage
        )
    }

    public func signOut(currentSession: AuthSessionDescriptor?) async {
        // No-op in Phase 1 foundation. Logout structure exists, live contract remains blocked.
    }
}

public struct Phase1StubAuthenticatedBootstrapAdapter: AuthenticatedBootstrapAdapter {
    public init() {}

    public func loadAuthenticatedBootstrap(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        // BLOCKED-BY-RUNTIME[authenticatedBootstrap]
        throw SentrixError.runtimeBlocked(
            area: .authenticatedBootstrap,
            message: RuntimeBlockedArea.authenticatedBootstrap.phase1FailureMessage
        )
    }
}

public struct Phase1StubRealtimeAdapter: RealtimeAdapter {
    public init() {}

    public func makeRealtimeStream(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            // BLOCKED-BY-RUNTIME[realtimeTransport]
            continuation.finish(
                throwing: SentrixError.runtimeBlocked(
                    area: .realtimeTransport,
                    message: RuntimeBlockedArea.realtimeTransport.phase1FailureMessage
                )
            )
        }
    }
}

public struct Phase1StubPushAdapter: PushAdapter {
    public init() {}

    public func preparePushRegistration(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        // BLOCKED-BY-RUNTIME[pushRegistration]
        throw SentrixError.runtimeBlocked(
            area: .pushRegistration,
            message: RuntimeBlockedArea.pushRegistration.phase1FailureMessage
        )
    }
}

public struct Phase1StubAppleWeeklyAdapter: AppleWeeklyAdapter {
    public init() {}

    public func prepareAppleWeeklyWorkspace(environment: AppEnvironment) async throws -> String {
        // BLOCKED-BY-RUNTIME[appleWeekly]
        throw SentrixError.runtimeBlocked(
            area: .appleWeekly,
            message: RuntimeBlockedArea.appleWeekly.phase1FailureMessage
        )
    }
}

public struct Phase1StubARLSBridgeAdapter: ARLSBridgeAdapter {
    public init() {}

    public func prepareBridgeWorkspace(environment: AppEnvironment) async throws -> String {
        // BLOCKED-BY-RUNTIME[arlsBridge]
        throw SentrixError.runtimeBlocked(
            area: .arlsBridge,
            message: RuntimeBlockedArea.arlsBridge.phase1FailureMessage
        )
    }
}
