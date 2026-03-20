import SentrixAPI
import SentrixCore
import SentrixFeatures

@MainActor
enum Phase1CompositionRoot {
    static func makeAppModel(environment: AppEnvironment = .phase1Default()) -> Phase1AppModel {
        let client = JSONAPIClient(transport: URLSessionHTTPTransport())
        let storedSessionRepository = UserDefaultsStoredSessionRepository()
        let authenticatedBootstrapRepository = LiveAuthenticatedBootstrapRepository(client: client)
        let appleWeeklyReadRepository = LiveAppleWeeklyReadRepository(client: client)
        let supportSubmissionRepository = LiveSupportSubmissionRepository(client: client)
        let pushDiagnosticsRepository = LivePushDiagnosticsRepository(client: client)

        let dependencies = AppDependencies(
            environment: environment,
            publicBootstrapRepository: LivePublicBootstrapRepository(client: client),
            storedSessionRepository: storedSessionRepository,
            authenticatedBootstrapRepository: authenticatedBootstrapRepository,
            appleWeeklyReadRepository: appleWeeklyReadRepository,
            supportSubmissionRepository: supportSubmissionRepository,
            pushDiagnosticsRepository: pushDiagnosticsRepository,
            authAdapter: Phase1StubAuthAdapter(),
            authenticatedBootstrapAdapter: Phase1StubAuthenticatedBootstrapAdapter(),
            realtimeAdapter: HQSSERealtimeAdapter(),
            pushAdapter: Phase1StubPushAdapter(),
            appleWeeklyAdapter: Phase1StubAppleWeeklyAdapter(),
            arlsBridgeAdapter: Phase1StubARLSBridgeAdapter()
        )

        return Phase1AppModel(dependencies: dependencies)
    }
}
