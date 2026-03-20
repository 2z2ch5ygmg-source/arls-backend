import XCTest
@testable import SentrixCore

private struct PublicBootstrapRepositorySpy: PublicBootstrapRepository {
    var snapshot: PublicBootstrapSnapshot

    func loadPublicBootstrap(environment: AppEnvironment) async throws -> PublicBootstrapSnapshot {
        snapshot
    }
}

final class PublicBootstrapUseCasesTests: XCTestCase {
    func testLoadPublicBootstrapReturnsRepositorySnapshot() async throws {
        let snapshot = PublicBootstrapSnapshot(
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!),
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
                appBaseURL: "https://example.com",
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
                appBaseURL: "https://example.com",
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

        let useCase = LoadPublicBootstrapUseCase(repository: PublicBootstrapRepositorySpy(snapshot: snapshot))
        let result = try await useCase.execute(environment: snapshot.environment)

        XCTAssertEqual(result, snapshot)
    }

    func testRuntimeNoticesKeepReadOnlyAndMasterDataReadOnlySeparate() {
        let snapshot = PublicBootstrapSnapshot(
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!),
            health: DeploymentHealth(
                ok: true,
                status: "ok",
                readOnly: true,
                readOnlyReason: "maintenance",
                importantIncidentFeatureReason: "",
                incidentParticipantFeatureReason: "",
                featureTimerEnabled: false,
                featureLegacyAdminMenuEnabled: false,
                featureDataDictionaryEnabled: false,
                serverTime: "2026-03-19T05:00:00Z"
            ),
            appConfig: PublicAppConfig(
                appBaseURL: "https://example.com",
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
                startupErrors: ["db recovered"]
            ),
            buildInfo: BuildProvenance(
                appBaseURL: "https://example.com",
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

        XCTAssertEqual(snapshot.notices.count, 2)
        XCTAssertEqual(snapshot.notices.first?.kind, .readOnly)
        XCTAssertEqual(snapshot.notices.first?.message, "maintenance (db recovered)")
        XCTAssertEqual(snapshot.notices.last?.kind, .masterDataReadOnly)
        XCTAssertEqual(snapshot.notices.last?.message, "HR only")
    }
}
