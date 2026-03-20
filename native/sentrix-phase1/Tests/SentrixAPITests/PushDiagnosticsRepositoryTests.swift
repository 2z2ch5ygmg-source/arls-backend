import XCTest
@testable import SentrixAPI
import SentrixCore

private final class PushDiagnosticsTransportSpy: HTTPTransport, @unchecked Sendable {
    var request: URLRequest?

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        self.request = request
        let url = try XCTUnwrap(request.url)
        let body = """
        {
          "title": "Sentrix Test Push",
          "body": "HQ runtime test",
          "registered_ios_devices": 1,
          "active_ios_devices": 1,
          "selected_ios_targets": 1,
          "registered_devices": [
            {
              "push_device_id": 77,
              "token": "token-77",
              "app_bundle": "com.sentrix.ios",
              "active": true,
              "selected_for_send": true,
              "updated_at": "2026-03-19T04:00:00Z",
              "last_seen_at": "2026-03-19T04:05:00Z"
            }
          ],
          "apns_config": {
            "enabled": true,
            "topic": "com.sentrix.ios",
            "use_sandbox": false,
            "endpoint_mode": "production",
            "endpoints": ["production"],
            "runtime_is_azure": true
          },
          "push_result": {
            "apns_enabled": true,
            "targets": 1,
            "success": 1,
            "failed": 0,
            "results": [
              {
                "user": "서성원",
                "push_device_id": 77,
                "token": "token-77",
                "ok": true,
                "attempts": [
                  {
                    "ok": true,
                    "endpoint": "production",
                    "status_code": 200,
                    "reason_code": "",
                    "reason": ""
                  }
                ]
              }
            ]
          }
        }
        """
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (Data(body.utf8), response)
    }
}

final class PushDiagnosticsRepositoryTests: XCTestCase {
    func testRepositoryMapsServerSidePushTestResult() async throws {
        let transport = PushDiagnosticsTransportSpy()
        let repository = LivePushDiagnosticsRepository(client: JSONAPIClient(transport: transport))
        let result = try await repository.runPushTest(
            session: sampleSession(),
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)
        )

        XCTAssertEqual(transport.request?.url?.path, "/api/push/test")
        XCTAssertEqual(transport.request?.httpMethod, "POST")
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Authorization"), "Bearer token")
        XCTAssertEqual(result.registeredIOSDevices, 1)
        XCTAssertEqual(result.apnsConfiguration.endpointMode, "production")
        XCTAssertEqual(result.pushResult.success, 1)
        XCTAssertEqual(result.registeredDevices.first?.token, "token-77")
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
