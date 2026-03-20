import XCTest
@testable import SentrixAPI
import SentrixCore

private final class SupportSubmissionTransportSpy: HTTPTransport, @unchecked Sendable {
    var request: URLRequest?

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        self.request = request
        let url = try XCTUnwrap(request.url)
        let body = """
        {
          "month": "2026-03",
          "selected_site": {"site_code": "R692"},
          "artifact_available": false,
          "empty_state": {"reason": "handoff_only"},
          "action_state": {"disabled_reasons": ["SUPPORT_SUBMISSION_OWNERSHIP_MOVED"]},
          "workspace_owner": "arls",
          "route_status": "handoff_only",
          "internal_only": true,
          "ownership": {
            "excel_ingress_owner": "arls",
            "sentrix_owner": "operator_handoff"
          },
          "handoff": {
            "owner": "ARLS",
            "message": "ARLS에서 계속 진행하세요.",
            "guidance": "Sentrix는 handoff만 제공합니다.",
            "url": "https://arls.example.com/support"
          },
          "bridge_status": {
            "connected": true,
            "degraded": false,
            "artifact_lookup_result": "present",
            "review_aggregation_result": "not_applicable"
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

final class SupportSubmissionRepositoryTests: XCTestCase {
    func testRepositoryMapsHandoffOnlyWorkspace() async throws {
        let transport = SupportSubmissionTransportSpy()
        let repository = LiveSupportSubmissionRepository(client: JSONAPIClient(transport: transport))
        let workspace = try await repository.loadWorkspace(
            session: sampleSession(),
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!),
            context: SupportSubmissionContext(month: "2026-03", siteCode: "R692")
        )

        XCTAssertEqual(transport.request?.url?.path, "/api/ops/support-submissions/workspace")
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Authorization"), "Bearer token")
        XCTAssertEqual(workspace.routeStatus, "handoff_only")
        XCTAssertEqual(workspace.handoff.owner, "ARLS")
        XCTAssertTrue(workspace.internalOnly)
        XCTAssertEqual(workspace.disabledReasons, ["SUPPORT_SUBMISSION_OWNERSHIP_MOVED"])
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
