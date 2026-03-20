import XCTest
@testable import SentrixAPI
import SentrixCore

final class AuthenticatedBootstrapMapperTests: XCTestCase {
    func testMapperBuildsHQAuthenticatedSnapshotFromRuntimeConfirmedShape() throws {
        let payload = """
        {
          "user": {
            "id": 21,
            "username": "01059387659",
            "full_name": "서성원",
            "role": "HQ_ADMIN",
            "tenant_id": "srs_korea",
            "site_id": "R692",
            "location": "R692"
          },
          "features": {
            "timer_enabled": false,
            "legacy_admin_menu_enabled": false,
            "data_dictionary_enabled": false,
            "websocket_enabled": false,
            "gps_enabled": false
          },
          "ui_labels": {
            "report": "보고하기"
          },
          "ticket_config": {
            "tenant_id": "srs_korea",
            "site_id": "R692",
            "ticket_templates": ["야간 지원 요청", "주간 지원 요청"],
            "source": "runtime"
          },
          "report_config": {
            "tenant_id": "srs_korea",
            "site_id": "R692",
            "report_templates": [
              {
                "key": "eci",
                "label": "ECI",
                "category": "incident",
                "incident_types": ["고객 Escalation"],
                "fields": [
                  {"key": "severity", "label": "Level", "input": "select", "required": true}
                ],
                "validation_rules": [
                  {"type": "required", "field": "severity", "message": "required"}
                ]
              }
            ],
            "validation_rules": {
              "required_message": "필수값입니다."
            },
            "source": "runtime"
          },
          "app_base_url": "https://sentrix.example.com",
          "tenant_config_endpoint": "/api/tenant-config",
          "ticket_template_config_endpoint": "/api/config/tickets",
          "report_config_endpoint": "/api/report-config",
          "bootstrap_config_endpoint": "/api/bootstrap-config",
          "read_only": false,
          "read_only_reason": "",
          "master_data_read_only": true,
          "master_data_read_only_message": "마스터 데이터는 HR에서만 수정 가능합니다."
        }
        """

        let dto = try JSONDecoder().decode(AuthenticatedBootstrapDTO.self, from: Data(payload.utf8))
        let loadedAt = Date(timeIntervalSince1970: 456)
        let snapshot = AuthenticatedBootstrapMapper.map(dto, loadedAt: loadedAt)

        XCTAssertEqual(snapshot.user.fullName, "서성원")
        XCTAssertEqual(snapshot.user.role, "HQ_ADMIN")
        XCTAssertEqual(snapshot.ticketConfig.templates.map(\.type), ["야간 지원 요청", "주간 지원 요청"])
        XCTAssertEqual(snapshot.reportConfig.templates.first?.fields.first?.key, "severity")
        XCTAssertEqual(snapshot.reportConfig.requiredMessage, "필수값입니다.")
        XCTAssertFalse(snapshot.features.websocketEnabled)
        XCTAssertTrue(snapshot.masterDataReadOnly)
        XCTAssertEqual(snapshot.loadedAt, loadedAt)
    }
}
