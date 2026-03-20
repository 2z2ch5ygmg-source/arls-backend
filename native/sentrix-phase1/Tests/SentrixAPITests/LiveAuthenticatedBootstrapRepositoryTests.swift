import XCTest
@testable import SentrixAPI
import SentrixCore

private final class AuthenticatedBootstrapTransportSpy: HTTPTransport, @unchecked Sendable {
    var seenRequests: [URLRequest] = []

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        seenRequests.append(request)
        let url = try XCTUnwrap(request.url)
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        let body = """
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
          "ticket_config": {
            "tenant_id": "srs_korea",
            "site_id": "R692",
            "ticket_templates": ["야간 지원 요청"],
            "source": "runtime"
          },
          "report_config": {
            "tenant_id": "srs_korea",
            "site_id": "R692",
            "report_templates": [],
            "validation_rules": {"required_message": "필수"},
            "source": "runtime"
          },
          "app_base_url": "https://example.com",
          "tenant_config_endpoint": "/api/tenant-config",
          "ticket_template_config_endpoint": "/api/config/tickets",
          "report_config_endpoint": "/api/report-config",
          "bootstrap_config_endpoint": "/api/bootstrap-config",
          "read_only": false,
          "read_only_reason": "",
          "master_data_read_only": true,
          "master_data_read_only_message": "HR only"
        }
        """
        return (Data(body.utf8), response)
    }
}

final class LiveAuthenticatedBootstrapRepositoryTests: XCTestCase {
    func testRepositoryUsesBearerAuthAndMapsSnapshot() async throws {
        let transport = AuthenticatedBootstrapTransportSpy()
        let repository = LiveAuthenticatedBootstrapRepository(
            client: JSONAPIClient(transport: transport),
            now: { Date(timeIntervalSince1970: 789) }
        )
        let snapshot = try await repository.loadAuthenticatedBootstrap(
            session: sampleSession(),
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)
        )

        XCTAssertEqual(transport.seenRequests.count, 1)
        XCTAssertEqual(transport.seenRequests.first?.value(forHTTPHeaderField: "Authorization"), "Bearer token")
        XCTAssertEqual(transport.seenRequests.first?.url?.path, "/api/bootstrap-config")
        XCTAssertEqual(snapshot.user.role, "HQ_ADMIN")
        XCTAssertEqual(snapshot.ticketConfig.templates.first?.type, "야간 지원 요청")
        XCTAssertEqual(snapshot.loadedAt, Date(timeIntervalSince1970: 789))
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
}
