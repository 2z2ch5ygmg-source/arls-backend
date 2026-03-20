import XCTest
@testable import SentrixFeatures
import SentrixCore

private struct PublicBootstrapRepositoryPhase2BStub: PublicBootstrapRepository {
    let snapshot: PublicBootstrapSnapshot

    func loadPublicBootstrap(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot {
        snapshot
    }
}

private final class StoredSessionRepositoryPhase2BStub: StoredSessionRepository, @unchecked Sendable {
    let storedSession: AuthSessionDescriptor?

    init(storedSession: AuthSessionDescriptor?) {
        self.storedSession = storedSession
    }

    func loadStoredSession() async throws -> AuthSessionDescriptor? {
        storedSession
    }

    func persistStoredSession(_ session: AuthSessionDescriptor) async throws {}
    func clearStoredSession() async {}
}

private final class AuthenticatedBootstrapRepositoryPhase2BStub: AuthenticatedBootstrapRepository, @unchecked Sendable {
    var loadCount = 0
    let result: Result<AuthenticatedBootstrapSnapshot, SentrixError>

    init(result: Result<AuthenticatedBootstrapSnapshot, SentrixError>) {
        self.result = result
    }

    func loadAuthenticatedBootstrap(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> AuthenticatedBootstrapSnapshot {
        loadCount += 1
        return try result.get()
    }
}

private struct IdleAppleWeeklyRepositoryPhase2BStub: AppleWeeklyReadRepository {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: AppleWeeklyContext
    ) async throws -> AppleWeeklyWorkspace {
        throw SentrixError.transport(message: "Not expected in Phase 2B gating tests.")
    }
}

private struct IdleSupportSubmissionRepositoryPhase2BStub: SupportSubmissionRepository {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: SupportSubmissionContext
    ) async throws -> SupportSubmissionWorkspace {
        throw SentrixError.transport(message: "Not expected in Phase 2B gating tests.")
    }
}

private struct IdlePushDiagnosticsRepositoryPhase2BStub: PushDiagnosticsRepository {
    func runPushTest(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> PushTestResult {
        throw SentrixError.transport(message: "Not expected in Phase 2B gating tests.")
    }
}

private struct AuthAdapterPhase2BStub: AuthAdapter {
    func signIn(using draft: LoginDraft, environment: AppEnvironment) async throws -> AuthSessionDescriptor {
        throw SentrixError.runtimeBlocked(area: .productionAuthMode, message: RuntimeBlockedArea.productionAuthMode.phase1FailureMessage)
    }

    func signOut(currentSession: AuthSessionDescriptor?) async {}
}

private struct AuthenticatedBootstrapAdapterPhase2BStub: AuthenticatedBootstrapAdapter {
    func loadAuthenticatedBootstrap(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .authenticatedBootstrap, message: RuntimeBlockedArea.authenticatedBootstrap.phase1FailureMessage)
    }
}

private final class RealtimeAdapterPhase2BRecorder: RealtimeAdapter, @unchecked Sendable {
    var makeStreamCount = 0

    func makeRealtimeStream(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error> {
        makeStreamCount += 1
        return AsyncThrowingStream { continuation in
            continuation.yield(.closed)
            continuation.finish()
        }
    }
}

private struct PushAdapterPhase2BStub: PushAdapter {
    func preparePushRegistration(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .pushRegistration, message: RuntimeBlockedArea.pushRegistration.phase1FailureMessage)
    }
}

private struct AppleWeeklyAdapterPhase2BStub: AppleWeeklyAdapter {
    func prepareAppleWeeklyWorkspace(environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .appleWeekly, message: RuntimeBlockedArea.appleWeekly.phase1FailureMessage)
    }
}

private struct ARLSBridgeAdapterPhase2BStub: ARLSBridgeAdapter {
    func prepareBridgeWorkspace(environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .arlsBridge, message: RuntimeBlockedArea.arlsBridge.phase1FailureMessage)
    }
}

@MainActor
final class Phase2BRoleAwareShellTests: XCTestCase {
    private let environment = AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)

    func testSupervisorSessionEntersFieldObservedShellWithoutHQBootstrapOrRealtime() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let session = sampleSession(role: "SUPERVISOR", status: "active")
        let model = makeModel(storedSession: session, authBootstrap: authBootstrap, realtime: realtime)

        await model.start()

        XCTAssertTrue(model.hasAuthenticatedSession)
        XCTAssertEqual(model.session.status, .authenticated(session))
        XCTAssertEqual(model.authenticatedShellScope, .fieldObserved(role: "SUPERVISOR"))
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        XCTAssertEqual(model.authenticatedShell.state, .idle)
        XCTAssertFalse(model.canAccessAuthenticatedRoute(.appleWeekly))
    }

    func testOfficerSessionEntersFieldObservedShellWithoutHQBootstrapOrRealtime() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "OFFICER", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertTrue(model.hasAuthenticatedSession)
        XCTAssertEqual(model.authenticatedShellScope, .fieldObserved(role: "OFFICER"))
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        XCTAssertEqual(model.authenticatedShell.state, .idle)
    }

    func testFieldObservedRoleAppleWeeklyNavigationIsBlocked() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "SUPERVISOR", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()
        model.openAppleWeekly()

        XCTAssertEqual(model.path, [.roleBlocked(.appleWeekly)])
        XCTAssertEqual(model.appleWeekly.state, .idle)
    }

    func testFieldObservedRoleSupportSubmissionNavigationIsBlocked() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "SUPERVISOR", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()
        model.openSupportSubmissions()

        XCTAssertEqual(model.path, [.roleBlocked(.supportSubmissions)])
        XCTAssertEqual(model.supportSubmission.state, .idle)
    }

    func testHQRoleRetainsHQOnlyNavigation() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "HQ_ADMIN", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()
        model.openAppleWeekly()

        XCTAssertEqual(model.authenticatedShellScope, .hqSafe(role: "HQ_ADMIN"))
        XCTAssertEqual(model.path, [.appleWeekly])
        XCTAssertEqual(authBootstrap.loadCount, 1)
    }

    func testLowercasedStoredHQRoleStillEntersHQShellAfterBootstrapProof() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "hq_admin", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertTrue(model.hasAuthenticatedSession)
        XCTAssertEqual(model.authenticatedShellScope, .hqSafe(role: "HQ_ADMIN"))
        XCTAssertEqual(model.authenticatedShellScope?.runtimeAccessLabel, "all_scoped")
        XCTAssertEqual(authBootstrap.loadCount, 1)
        XCTAssertEqual(realtime.makeStreamCount, 1)
    }

    func testLowercasedStoredSupervisorRoleEntersFieldObservedShell() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryPhase2BStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterPhase2BRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "supervisor", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertTrue(model.hasAuthenticatedSession)
        XCTAssertEqual(model.authenticatedShellScope, .fieldObserved(role: "SUPERVISOR"))
        XCTAssertEqual(model.authenticatedShellScope?.runtimeAccessLabel, "site_scoped")
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
    }

    private func makeModel(
        storedSession: AuthSessionDescriptor?,
        authBootstrap: AuthenticatedBootstrapRepositoryPhase2BStub,
        realtime: RealtimeAdapterPhase2BRecorder
    ) -> Phase1AppModel {
        let dependencies = AppDependencies(
            environment: environment,
            publicBootstrapRepository: PublicBootstrapRepositoryPhase2BStub(snapshot: samplePublicBootstrapSnapshot()),
            storedSessionRepository: StoredSessionRepositoryPhase2BStub(storedSession: storedSession),
            authenticatedBootstrapRepository: authBootstrap,
            appleWeeklyReadRepository: IdleAppleWeeklyRepositoryPhase2BStub(),
            supportSubmissionRepository: IdleSupportSubmissionRepositoryPhase2BStub(),
            pushDiagnosticsRepository: IdlePushDiagnosticsRepositoryPhase2BStub(),
            authAdapter: AuthAdapterPhase2BStub(),
            authenticatedBootstrapAdapter: AuthenticatedBootstrapAdapterPhase2BStub(),
            realtimeAdapter: realtime,
            pushAdapter: PushAdapterPhase2BStub(),
            appleWeeklyAdapter: AppleWeeklyAdapterPhase2BStub(),
            arlsBridgeAdapter: ARLSBridgeAdapterPhase2BStub()
        )
        return Phase1AppModel(dependencies: dependencies)
    }

    private func sampleSession(role: String, status: String) -> AuthSessionDescriptor {
        AuthSessionDescriptor(
            accessToken: "token",
            user: StoredSessionUserSummary(
                id: 21,
                username: "field-user",
                loginID: "field-user",
                fullName: role == "HQ_ADMIN" ? "서성원" : "민경민",
                role: role,
                group: role == "HQ_ADMIN" ? "HQ" : "FIELD",
                siteID: role == "HQ_ADMIN" ? "R692" : "R738",
                siteCode: role == "HQ_ADMIN" ? "R692" : "R738",
                siteName: role == "HQ_ADMIN" ? "Apple_명동" : "Apple_가로수길",
                tenantID: "srs_korea",
                location: role == "HQ_ADMIN" ? "R692" : "R738",
                status: status,
                linkedEmployeeID: 201,
                employeeID: 201
            ),
            issuedAt: Date(timeIntervalSince1970: 1),
            persistenceSource: .storedSocKeys,
            storageKeys: ["soc_token", "soc_user"]
        )
    }

    private func sampleAuthenticatedSnapshot(role: String) -> AuthenticatedBootstrapSnapshot {
        AuthenticatedBootstrapSnapshot(
            user: AuthenticatedUserSummary(
                id: 21,
                username: "01059387659",
                fullName: "서성원",
                role: role,
                tenantID: "srs_korea",
                siteID: role == "HQ_ADMIN" ? "R692" : "R738",
                location: role == "HQ_ADMIN" ? "R692" : "R738"
            ),
            features: RuntimeFeatureFlags(
                timerEnabled: false,
                legacyAdminMenuEnabled: false,
                dataDictionaryEnabled: false,
                websocketEnabled: false,
                gpsEnabled: false,
                importantIncidentEnabled: false,
                incidentParticipantEnabled: false
            ),
            uiLabels: [:],
            ticketConfig: TicketConfigSummary(
                tenantID: "srs_korea",
                siteID: role == "HQ_ADMIN" ? "R692" : "R738",
                templates: [TicketTemplateSummary(type: "야간 지원 요청")],
                source: "runtime"
            ),
            reportConfig: ReportConfigSummary(
                tenantID: "srs_korea",
                siteID: role == "HQ_ADMIN" ? "R692" : "R738",
                templates: [],
                requiredMessage: "필수",
                source: "runtime"
            ),
            appBaseURL: "https://example.com",
            endpoints: RuntimeEndpoints(
                tenantConfig: "/api/tenant-config",
                ticketTemplateConfig: "/api/config/tickets",
                reportConfig: "/api/report-config",
                bootstrapConfig: "/api/bootstrap-config"
            ),
            readOnly: false,
            readOnlyReason: "",
            masterDataReadOnly: true,
            masterDataReadOnlyMessage: "HR only",
            loadedAt: Date(timeIntervalSince1970: 1)
        )
    }

    private func samplePublicBootstrapSnapshot() -> PublicBootstrapSnapshot {
        PublicBootstrapSnapshot(
            environment: environment,
            health: DeploymentHealth(
                ok: true,
                status: "ok",
                readOnly: false,
                readOnlyReason: "",
                importantIncidentFeatureReason: "",
                incidentParticipantFeatureReason: "",
                featureTimerEnabled: false,
                featureLegacyAdminMenuEnabled: false,
                featureDataDictionaryEnabled: false,
                serverTime: "2026-03-19T05:00:00Z"
            ),
            appConfig: PublicAppConfig(
                appBaseURL: environment.baseURL.absoluteString,
                tenantID: "srs_korea",
                siteID: "",
                readOnly: false,
                readOnlyReason: "",
                masterDataReadOnly: true,
                masterDataReadOnlyMessage: "HR only",
                features: RuntimeFeatureFlags(
                    timerEnabled: false,
                    legacyAdminMenuEnabled: false,
                    dataDictionaryEnabled: false,
                    websocketEnabled: false,
                    gpsEnabled: false,
                    importantIncidentEnabled: true,
                    incidentParticipantEnabled: true
                ),
                endpoints: RuntimeEndpoints(
                    tenantConfig: "/api/tenant-config",
                    ticketTemplateConfig: "/api/config/tickets",
                    reportConfig: "/api/report-config",
                    bootstrapConfig: "/api/bootstrap-config"
                ),
                uiLabels: [:],
                startupErrors: []
            ),
            buildInfo: BuildProvenance(
                appBaseURL: environment.baseURL.absoluteString,
                backendCommit: "457003b",
                backendDirty: true,
                deployMode: "full",
                imageTag: "v-tag",
                frontendBuildID: "frontend",
                frontendUIBuildID: "frontend-ui",
                frontendSource: "repo-static",
                frontendSourceImage: "acr/image",
                deployedAtUTC: "2026-03-19T04:48:39Z",
                staticDirectory: "/app/static",
                dataDirectory: "/home/site/data",
                databasePath: "/home/site/data/security_ops.db"
            ),
            loadedAt: Date(timeIntervalSince1970: 1)
        )
    }
}
