import XCTest
@testable import SentrixAPI
import SentrixCore

final class PublicBootstrapMapperTests: XCTestCase {
    func testAppConfigMapperPreservesConfirmedPublicFlags() {
        let dto = AppConfigDTO(
            appBaseURL: "https://security-ops.example",
            tenantID: "srs_korea",
            siteID: "",
            readOnly: false,
            readOnlyReason: "",
            importantIncidentFeatureEnabled: true,
            importantIncidentFeatureReason: "",
            incidentParticipantFeatureEnabled: true,
            incidentParticipantFeatureReason: "",
            featureTimerEnabled: false,
            featureLegacyAdminMenuEnabled: false,
            featureFlags: .init(
                timerEnabled: false,
                legacyAdminMenuEnabled: false,
                dataDictionaryEnabled: false,
                websocketEnabled: false,
                gpsEnabled: false
            ),
            masterDataReadOnly: true,
            masterDataReadOnlyMessage: "HR only",
            tenantConfigEndpoint: "/api/tenant-config",
            ticketTemplateConfigEndpoint: "/api/config/tickets",
            reportConfigEndpoint: "/api/report-config",
            bootstrapConfigEndpoint: "/api/bootstrap-config",
            uiLabels: ["report_templates_label": "Data Download"],
            startupErrors: []
        )

        let result = PublicBootstrapMapper.map(dto)

        XCTAssertEqual(result.tenantID, "srs_korea")
        XCTAssertFalse(result.features.timerEnabled)
        XCTAssertFalse(result.features.websocketEnabled)
        XCTAssertTrue(result.features.importantIncidentEnabled)
        XCTAssertTrue(result.features.incidentParticipantEnabled)
        XCTAssertTrue(result.masterDataReadOnly)
        XCTAssertEqual(result.endpoints.bootstrapConfig, "/api/bootstrap-config")
    }

    func testHealthDTODecodesLossyBoolValues() throws {
        let payload = """
        {
          "ok": "true",
          "status": "ok",
          "read_only": "1",
          "read_only_reason": "maintenance",
          "important_incident_feature_enabled": "true",
          "important_incident_feature_reason": "",
          "incident_participant_feature_enabled": "false",
          "incident_participant_feature_reason": "",
          "feature_timer_enabled": "0",
          "feature_legacy_admin_menu_enabled": false,
          "feature_data_dictionary_enabled": "no",
          "time": "2026-03-19T04:48:39Z"
        }
        """

        let dto = try JSONDecoder().decode(HealthDTO.self, from: Data(payload.utf8))
        let result = PublicBootstrapMapper.map(dto)

        XCTAssertTrue(result.ok)
        XCTAssertTrue(result.readOnly)
        XCTAssertFalse(result.featureTimerEnabled)
        XCTAssertFalse(result.featureDataDictionaryEnabled)
    }

    func testAppConfigDTODecodesWithMissingOptionalFields() throws {
        let payload = """
        {
          "tenant_id": "srs_korea",
          "important_incident_feature_enabled": true,
          "incident_participant_feature_enabled": true,
          "master_data_read_only": true
        }
        """

        let dto = try JSONDecoder().decode(AppConfigDTO.self, from: Data(payload.utf8))
        let result = PublicBootstrapMapper.map(dto)

        XCTAssertEqual(result.tenantID, "srs_korea")
        XCTAssertEqual(result.appBaseURL, "")
        XCTAssertEqual(result.endpoints.bootstrapConfig, "")
        XCTAssertEqual(result.uiLabels, [:])
        XCTAssertEqual(result.startupErrors, [])
        XCTAssertTrue(result.masterDataReadOnly)
        XCTAssertFalse(result.features.websocketEnabled)
    }

    func testBuildInfoMapperPreservesMultiFieldProvenanceSeparately() {
        let dto = BuildInfoDTO(
            appBaseURL: "https://security-ops.example",
            backendCommit: "457003b",
            backendDirty: true,
            deployMode: "full",
            imageTag: "image-tag",
            frontendBuildID: "frontend-build",
            frontendUIBuildID: "frontend-ui-build",
            frontendSource: "repo-static:457003b",
            frontendSourceImage: "acr/source-image",
            deployedAtUTC: "2026-03-19T04:48:39Z",
            staticDirectory: "/app/static",
            dataDirectory: "/home/site/data",
            databasePath: "/home/site/data/security_ops.db"
        )

        let result = PublicBootstrapMapper.map(dto)

        XCTAssertEqual(result.backendCommit, "457003b")
        XCTAssertEqual(result.imageTag, "image-tag")
        XCTAssertEqual(result.frontendBuildID, "frontend-build")
        XCTAssertEqual(result.frontendUIBuildID, "frontend-ui-build")
        XCTAssertEqual(result.frontendSource, "repo-static:457003b")
        XCTAssertEqual(result.frontendSourceImage, "acr/source-image")
    }
}
