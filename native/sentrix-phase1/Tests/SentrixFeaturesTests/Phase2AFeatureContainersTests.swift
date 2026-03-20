import XCTest
@testable import SentrixFeatures
import SentrixCore

private struct AuthenticatedBootstrapRepositoryStub: AuthenticatedBootstrapRepository {
    let snapshot: AuthenticatedBootstrapSnapshot

    func loadAuthenticatedBootstrap(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> AuthenticatedBootstrapSnapshot {
        snapshot
    }
}

private struct AppleWeeklyReadRepositoryStub: AppleWeeklyReadRepository {
    let workspace: AppleWeeklyWorkspace
    let onLoad: @Sendable (AppleWeeklyContext) -> Void

    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: AppleWeeklyContext
    ) async throws -> AppleWeeklyWorkspace {
        onLoad(context)
        return workspace
    }
}

private struct SupportSubmissionRepositoryStub: SupportSubmissionRepository {
    let workspace: SupportSubmissionWorkspace
    let onLoad: @Sendable (SupportSubmissionContext) -> Void

    func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: SupportSubmissionContext
    ) async throws -> SupportSubmissionWorkspace {
        onLoad(context)
        return workspace
    }
}

private struct PushDiagnosticsRepositoryStub: PushDiagnosticsRepository {
    let result: PushTestResult

    func runPushTest(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> PushTestResult {
        result
    }
}

private struct RealtimeAdapterStub: RealtimeAdapter {
    func makeRealtimeStream(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.yield(.opened(endpoint: "https://example.com/api/notifications/stream?token=token", contentType: "text/event-stream"))
            continuation.yield(.line("data: ping"))
            continuation.yield(.closed)
            continuation.finish()
        }
    }
}

private final class AppleWeeklyContextBox: @unchecked Sendable {
    var value: AppleWeeklyContext?
}

private final class SupportSubmissionContextBox: @unchecked Sendable {
    var value: SupportSubmissionContext?
}

@MainActor
final class Phase2AFeatureContainersTests: XCTestCase {
    private let environment = AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)

    func testAuthenticatedShellContainerLoadsHQSnapshot() async {
        let snapshot = sampleAuthenticatedSnapshot()
        let container = AuthenticatedShellContainer(
            repository: AuthenticatedBootstrapRepositoryStub(snapshot: snapshot),
            environment: environment
        )

        await container.load(session: sampleSession())

        XCTAssertEqual(container.state, .loaded(snapshot))
    }

    func testAuthenticatedShellContainerAcceptsCanonicalizedHQRoleMarker() async {
        let snapshot = sampleAuthenticatedSnapshot(role: "hq_admin")
        let container = AuthenticatedShellContainer(
            repository: AuthenticatedBootstrapRepositoryStub(snapshot: snapshot),
            environment: environment
        )

        await container.load(session: sampleSession())

        XCTAssertEqual(container.state, .loaded(snapshot))
    }

    func testAppleWeeklyContainerBuildsHQContextFromBootstrap() async {
        let box = AppleWeeklyContextBox()
        let workspace = sampleAppleWeeklyWorkspace()
        let container = AppleWeeklyContainer(
            repository: AppleWeeklyReadRepositoryStub(
                workspace: workspace,
                onLoad: { context in box.value = context }
            ),
            environment: environment,
            now: { Date(timeIntervalSince1970: 1_773_878_400) } // 2026-03-19 UTC
        )

        await container.load(session: sampleSession(), bootstrap: sampleAuthenticatedSnapshot())

        XCTAssertEqual(box.value, AppleWeeklyContext(siteCode: "R692", reportYear: "2026", referenceDate: "2026-03-19"))
        XCTAssertEqual(container.state, .loaded(workspace))
    }

    func testSupportSubmissionContainerBuildsMonthContext() async {
        let box = SupportSubmissionContextBox()
        let workspace = sampleSupportSubmissionWorkspace()
        let container = SupportSubmissionContainer(
            repository: SupportSubmissionRepositoryStub(
                workspace: workspace,
                onLoad: { context in box.value = context }
            ),
            environment: environment,
            now: { Date(timeIntervalSince1970: 1_773_878_400) }
        )

        await container.load(session: sampleSession(), bootstrap: sampleAuthenticatedSnapshot())

        XCTAssertEqual(box.value, SupportSubmissionContext(month: "2026-03", siteCode: "R692"))
        XCTAssertEqual(container.state, .loaded(workspace))
    }

    func testPushDiagnosticsContainerLoadsServerSideResult() async {
        let result = samplePushResult()
        let container = PushDiagnosticsContainer(
            repository: PushDiagnosticsRepositoryStub(result: result),
            environment: environment
        )

        await container.run(session: sampleSession())

        XCTAssertEqual(container.state, .loaded(result))
    }

    func testRealtimeContainerConsumesSSEEvents() async {
        let container = RealtimeContainer(adapter: RealtimeAdapterStub())

        await container.connect(session: sampleSession(), environment: environment)
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(container.snapshot.transport, .sse)
        XCTAssertEqual(container.snapshot.endpoint, "https://example.com/api/notifications/stream?token=token")
        XCTAssertEqual(container.snapshot.status, .disconnected)
        XCTAssertEqual(container.snapshot.recentLines, ["data: ping"])
    }

    private func sampleSession() -> AuthSessionDescriptor {
        AuthSessionDescriptor(
            accessToken: "token",
            user: StoredSessionUserSummary(
                id: 21,
                username: "01059387659",
                loginID: "01059387659",
                fullName: "서성원",
                role: "HQ_ADMIN",
                group: "HQ",
                siteID: "R692",
                siteCode: "R692",
                siteName: "Apple_명동",
                tenantID: "srs_korea",
                location: "R692",
                status: "active",
                linkedEmployeeID: 201,
                employeeID: 201
            ),
            issuedAt: Date(timeIntervalSince1970: 1),
            persistenceSource: .storedSocKeys,
            storageKeys: ["soc_token", "soc_user"]
        )
    }

    private func sampleAuthenticatedSnapshot(role: String = "HQ_ADMIN") -> AuthenticatedBootstrapSnapshot {
        AuthenticatedBootstrapSnapshot(
            user: AuthenticatedUserSummary(
                id: 21,
                username: "01059387659",
                fullName: "서성원",
                role: role,
                tenantID: "srs_korea",
                siteID: "R692",
                location: "R692"
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
                siteID: "R692",
                templates: [TicketTemplateSummary(type: "야간 지원 요청")],
                source: "runtime"
            ),
            reportConfig: ReportConfigSummary(
                tenantID: "srs_korea",
                siteID: "R692",
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

    private func sampleAppleWeeklyWorkspace() -> AppleWeeklyWorkspace {
        AppleWeeklyWorkspace(
            context: AppleWeeklyContext(siteCode: "R692", reportYear: "2026", referenceDate: "2026-03-19"),
            serviceAccountEmail: "service-account@example.com",
            mappings: [
                AppleWeeklyMapping(
                    siteCode: "R692",
                    reportYear: "2026",
                    siteName: "Apple_명동",
                    spreadsheetID: "sheet-1",
                    spreadsheetURL: "https://docs.google.com/spreadsheets/d/sheet-1",
                    lastTestStatus: "connected",
                    lastTestMessage: "연결됨(편집 가능)"
                )
            ],
            weekRange: AppleWeeklyWeekRange(
                weekStart: "2026-03-16",
                weekEnd: "2026-03-22",
                referenceDate: "2026-03-19",
                dates: ["2026-03-16"],
                days: []
            ),
            readiness: AppleWeeklyReadiness(
                schemaVersion: "2026.03",
                siteCode: "R692",
                siteName: "Apple_명동",
                reportYear: "2026",
                referenceDate: "2026-03-19",
                workbookReady: true,
                templateReady: true,
                baselineReady: true,
                arlsTruthReady: true,
                previewAllowed: true,
                liveWriteAllowed: true,
                rolloutStatus: "live",
                blockingIssues: [],
                warnings: [],
                overnightReconciliationStatus: "ready",
                infoMessages: []
            ),
            opsConfig: AppleWeeklyOpsConfig(
                siteCode: "R692",
                reportYear: "2026",
                storeDisplayName: "Apple_명동",
                overtimeThresholdMinutes: "60",
                overtimeReasons: ["행사"],
                phase2State: "ready",
                phase4RolloutMode: "live",
                phase4LiveWriteAllowed: true
            ),
            conflicts: [],
            dryRun: AppleWeeklyDryRun(
                operationKind: "sync_patch",
                requestedSections: ["attendance", "overtime", "overnight_guards"],
                selectedSections: ["overnight_guards"],
                writeValidation: AppleWeeklyWriteValidation(
                    status: "ready",
                    canWrite: true,
                    expectedTargetCount: 2,
                    plannedWriteCount: 1,
                    conflictCount: 0
                )
            )
        )
    }

    private func sampleSupportSubmissionWorkspace() -> SupportSubmissionWorkspace {
        SupportSubmissionWorkspace(
            month: "2026-03",
            siteCode: "R692",
            routeStatus: "handoff_only",
            workspaceOwner: "arls",
            internalOnly: true,
            artifactAvailable: false,
            emptyReason: "handoff_only",
            disabledReasons: ["SUPPORT_SUBMISSION_OWNERSHIP_MOVED"],
            ownership: SupportSubmissionOwnership(
                excelIngressOwner: "arls",
                sentrixOwner: "operator_handoff"
            ),
            handoff: SupportSubmissionHandoff(
                owner: "ARLS",
                message: "ARLS에서 계속 진행하세요.",
                guidance: "Sentrix는 handoff만 제공합니다.",
                url: "https://arls.example.com/support"
            ),
            bridgeStatus: SupportSubmissionBridgeStatus(
                connected: true,
                degraded: false,
                artifactLookupResult: "present",
                reviewAggregationResult: "not_applicable"
            )
        )
    }

    private func samplePushResult() -> PushTestResult {
        PushTestResult(
            title: "Sentrix Test Push",
            body: "HQ runtime test",
            registeredIOSDevices: 1,
            activeIOSDevices: 1,
            selectedIOSTargets: 1,
            registeredDevices: [
                PushRegisteredDevice(
                    id: 77,
                    token: "token-77",
                    appBundle: "com.sentrix.ios",
                    active: true,
                    selectedForSend: true,
                    updatedAt: "2026-03-19T04:00:00Z",
                    lastSeenAt: "2026-03-19T04:05:00Z"
                )
            ],
            apnsConfiguration: PushAPNSConfiguration(
                enabled: true,
                topic: "com.sentrix.ios",
                useSandbox: false,
                endpointMode: "production",
                endpoints: ["production"],
                runtimeIsAzure: true
            ),
            pushResult: PushTestSummary(
                apnsEnabled: true,
                targets: 1,
                success: 1,
                failed: 0,
                results: []
            )
        )
    }
}
