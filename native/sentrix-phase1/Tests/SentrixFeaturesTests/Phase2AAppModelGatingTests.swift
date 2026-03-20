import XCTest
@testable import SentrixFeatures
import SentrixCore

private struct PublicBootstrapRepositoryStub: PublicBootstrapRepository {
    let snapshot: PublicBootstrapSnapshot

    func loadPublicBootstrap(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot {
        snapshot
    }
}

private final class StoredSessionRepositoryGateStub: StoredSessionRepository, @unchecked Sendable {
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

private final class AuthenticatedBootstrapRepositoryGateStub: AuthenticatedBootstrapRepository, @unchecked Sendable {
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

private struct IdleAppleWeeklyRepositoryStub: AppleWeeklyReadRepository {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: AppleWeeklyContext
    ) async throws -> AppleWeeklyWorkspace {
        throw SentrixError.transport(message: "Not expected in gating tests.")
    }
}

private struct IdleSupportSubmissionRepositoryStub: SupportSubmissionRepository {
    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: SupportSubmissionContext
    ) async throws -> SupportSubmissionWorkspace {
        throw SentrixError.transport(message: "Not expected in gating tests.")
    }
}

private struct IdlePushDiagnosticsRepositoryStub: PushDiagnosticsRepository {
    func runPushTest(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> PushTestResult {
        throw SentrixError.transport(message: "Not expected in gating tests.")
    }
}

private struct AuthAdapterGateStub: AuthAdapter {
    func signIn(using draft: LoginDraft, environment: AppEnvironment) async throws -> AuthSessionDescriptor {
        throw SentrixError.runtimeBlocked(area: .productionAuthMode, message: RuntimeBlockedArea.productionAuthMode.phase1FailureMessage)
    }

    func signOut(currentSession: AuthSessionDescriptor?) async {}
}

private struct AuthenticatedBootstrapAdapterGateStub: AuthenticatedBootstrapAdapter {
    func loadAuthenticatedBootstrap(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .authenticatedBootstrap, message: RuntimeBlockedArea.authenticatedBootstrap.phase1FailureMessage)
    }
}

private final class RealtimeAdapterRecorder: RealtimeAdapter, @unchecked Sendable {
    var makeStreamCount = 0

    func makeRealtimeStream(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error> {
        makeStreamCount += 1
        return AsyncThrowingStream { continuation in
            continuation.yield(.opened(endpoint: "https://example.com/api/notifications/stream?token=\(session.accessToken)", contentType: "text/event-stream"))
            continuation.yield(.closed)
            continuation.finish()
        }
    }
}

private struct PushAdapterGateStub: PushAdapter {
    func preparePushRegistration(session: AuthSessionDescriptor, environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .pushRegistration, message: RuntimeBlockedArea.pushRegistration.phase1FailureMessage)
    }
}

private struct AppleWeeklyAdapterGateStub: AppleWeeklyAdapter {
    func prepareAppleWeeklyWorkspace(environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .appleWeekly, message: RuntimeBlockedArea.appleWeekly.phase1FailureMessage)
    }
}

private struct ARLSBridgeAdapterGateStub: ARLSBridgeAdapter {
    func prepareBridgeWorkspace(environment: AppEnvironment) async throws -> String {
        throw SentrixError.runtimeBlocked(area: .arlsBridge, message: RuntimeBlockedArea.arlsBridge.phase1FailureMessage)
    }
}

@MainActor
final class Phase2AAppModelGatingTests: XCTestCase {
    private let environment = AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)

    func testRestoredUnverifiedRoleDoesNotEnterAuthenticatedShell() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryGateStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "VICE_SUPERVISOR", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertFalse(model.hasAuthenticatedSession)
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        XCTAssertEqual(model.appleWeekly.state, .idle)
        XCTAssertEqual(model.supportSubmission.state, .idle)
        XCTAssertEqual(model.pushDiagnostics.state, .idle)
        guard case .unresolvedRestored(_, let message) = model.session.status else {
            return XCTFail("Expected unresolved restored session")
        }
        XCTAssertTrue(message.contains("VICE_SUPERVISOR"))
    }

    func testRestoredUnknownRoleStoredSessionDoesNotEnterHQShell() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryGateStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertFalse(model.hasAuthenticatedSession)
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        guard case .unresolvedRestored(_, let message) = model.session.status else {
            return XCTFail("Expected unresolved restored session")
        }
        XCTAssertTrue(message.contains("<empty>"))
    }

    func testRestoredDisabledStoredSessionDoesNotEnterHQShell() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryGateStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "HQ_ADMIN", status: "disabled"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertFalse(model.hasAuthenticatedSession)
        XCTAssertEqual(authBootstrap.loadCount, 0)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        guard case .unresolvedRestored(_, let message) = model.session.status else {
            return XCTFail("Expected unresolved restored session")
        }
        XCTAssertTrue(message.contains("disabled"))
    }

    func testRestoredHQStoredSessionEntersHQShellAfterBootstrapProof() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryGateStub(result: .success(sampleAuthenticatedSnapshot(role: "HQ_ADMIN")))
        let realtime = RealtimeAdapterRecorder()
        let session = sampleSession(role: "HQ_ADMIN", status: "active")
        let model = makeModel(
            storedSession: session,
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertTrue(model.hasAuthenticatedSession)
        XCTAssertEqual(model.session.status, .authenticated(session))
        XCTAssertEqual(authBootstrap.loadCount, 1)
        XCTAssertEqual(realtime.makeStreamCount, 1)
        guard case .loaded(let snapshot) = model.authenticatedShell.state else {
            return XCTFail("Expected loaded authenticated shell")
        }
        XCTAssertEqual(snapshot.user.role, "HQ_ADMIN")
    }

    func testBootstrapRoleMismatchBlocksRestoredSessionBeforeRealtimeStarts() async {
        let authBootstrap = AuthenticatedBootstrapRepositoryGateStub(result: .success(sampleAuthenticatedSnapshot(role: "SUPERVISOR")))
        let realtime = RealtimeAdapterRecorder()
        let model = makeModel(
            storedSession: sampleSession(role: "HQ_ADMIN", status: "active"),
            authBootstrap: authBootstrap,
            realtime: realtime
        )

        await model.start()

        XCTAssertFalse(model.hasAuthenticatedSession)
        XCTAssertEqual(authBootstrap.loadCount, 1)
        XCTAssertEqual(realtime.makeStreamCount, 0)
        XCTAssertEqual(model.appleWeekly.state, .idle)
        XCTAssertEqual(model.supportSubmission.state, .idle)
        XCTAssertEqual(model.pushDiagnostics.state, .idle)
        guard case .unresolvedRestored(_, let message) = model.session.status else {
            return XCTFail("Expected unresolved restored session")
        }
        XCTAssertTrue(message.contains("SUPERVISOR"))
    }

    private func makeModel(
        storedSession: AuthSessionDescriptor?,
        authBootstrap: AuthenticatedBootstrapRepositoryGateStub,
        realtime: RealtimeAdapterRecorder
    ) -> Phase1AppModel {
        let dependencies = AppDependencies(
            environment: environment,
            publicBootstrapRepository: PublicBootstrapRepositoryStub(snapshot: samplePublicBootstrapSnapshot()),
            storedSessionRepository: StoredSessionRepositoryGateStub(storedSession: storedSession),
            authenticatedBootstrapRepository: authBootstrap,
            appleWeeklyReadRepository: IdleAppleWeeklyRepositoryStub(),
            supportSubmissionRepository: IdleSupportSubmissionRepositoryStub(),
            pushDiagnosticsRepository: IdlePushDiagnosticsRepositoryStub(),
            authAdapter: AuthAdapterGateStub(),
            authenticatedBootstrapAdapter: AuthenticatedBootstrapAdapterGateStub(),
            realtimeAdapter: realtime,
            pushAdapter: PushAdapterGateStub(),
            appleWeeklyAdapter: AppleWeeklyAdapterGateStub(),
            arlsBridgeAdapter: ARLSBridgeAdapterGateStub()
        )
        return Phase1AppModel(dependencies: dependencies)
    }

    private func sampleSession(role: String, status: String) -> AuthSessionDescriptor {
        AuthSessionDescriptor(
            accessToken: "token",
            user: StoredSessionUserSummary(
                id: 21,
                username: "01059387659",
                loginID: "01059387659",
                fullName: "서성원",
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
