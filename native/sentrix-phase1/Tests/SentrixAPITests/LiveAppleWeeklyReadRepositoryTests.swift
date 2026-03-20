import XCTest
@testable import SentrixAPI
import SentrixCore

private actor AppleWeeklyRequestRecorder {
    private var requests: [URLRequest] = []

    func append(_ request: URLRequest) {
        requests.append(request)
    }

    func snapshot() -> [URLRequest] {
        requests
    }
}

private final class AppleWeeklyTransportSpy: HTTPTransport, @unchecked Sendable {
    private let recorder = AppleWeeklyRequestRecorder()

    func recordedRequests() async -> [URLRequest] {
        await recorder.snapshot()
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        await recorder.append(request)
        let url = try XCTUnwrap(request.url)
        let body: String
        switch url.path {
        case "/api/google-sheets/mappings":
            body = """
            {
              "service_account_email": "service-account@example.com",
              "mappings": [
                {
                  "site_code": "R692",
                  "report_year": "2026",
                  "site_name": "Apple_명동",
                  "spreadsheet_id": "sheet-1",
                  "spreadsheet_url": "https://docs.google.com/spreadsheets/d/sheet-1",
                  "last_test_status": "connected",
                  "last_test_message": "연결됨(편집 가능)"
                }
              ]
            }
            """
        case "/api/weekly-report/week-range":
            body = """
            {
              "week_start": "2026-03-16",
              "week_end": "2026-03-22",
              "reference_date": "2026-03-19",
              "dates": ["2026-03-16", "2026-03-17"],
              "days": [
                {
                  "date": "2026-03-16",
                  "month_tab_name": "03월",
                  "row_day": 12,
                  "row_night": 13,
                  "weekday_label": "월"
                }
              ]
            }
            """
        case "/api/weekly-report/site-readiness":
            body = """
            {
              "readiness": {
                "schema_version": "2026.03",
                "site_code": "R692",
                "site_name": "Apple_명동",
                "report_year": "2026",
                "reference_date": "2026-03-19",
                "workbook_ready": true,
                "template_ready": true,
                "baseline_ready": true,
                "arls_truth_ready": true,
                "preview_allowed": true,
                "live_write_allowed": true,
                "rollout_status": "live",
                "blocking_issues": [],
                "warnings": [],
                "overnight_reconciliation_status": "ready",
                "info": []
              }
            }
            """
        case "/api/weekly-report/ops-config":
            body = """
            {
              "config": {
                "site_code": "R692",
                "report_year": "2026",
                "overtime_rules": {
                  "threshold_minutes": "60",
                  "reasons": ["행사", "연장"]
                },
                "store_baseline": {
                  "store_display_name": "Apple_명동"
                },
                "phase2_readiness": {
                  "state": "ready"
                },
                "phase4_rollout": {
                  "resolved_rollout_mode": "live"
                },
                "phase4_readiness": {
                  "live_write_allowed": true
                }
              }
            }
            """
        case "/api/weekly-report/conflicts":
            body = """
            {
              "conflicts": ["conflict-1"]
            }
            """
        case "/api/weekly-report/dry-run":
            let requestBody = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
            XCTAssertTrue(requestBody.contains("\"sections\":[\"attendance\",\"overtime\",\"overnight_guards\"]"))
            XCTAssertTrue(requestBody.contains("\"target_dates\":[\"2026-03-16\",\"2026-03-17\"]"))
            body = """
            {
              "operation_kind": "sync_patch",
              "package": {
                "operation_kind": "sync_patch",
                "selected": {
                  "sections": ["overnight_guards"]
                },
                "write_validation": {
                  "status": "ready",
                  "can_write": true
                },
                "range_validation": {
                  "expected_target_count": 2,
                  "planned_write_count": 1,
                  "conflict_count": 0
                }
              }
            }
            """
        default:
            XCTFail("Unexpected path \(url.path)")
            body = "{}"
        }

        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        return (Data(body.utf8), response)
    }
}

final class LiveAppleWeeklyReadRepositoryTests: XCTestCase {
    func testRepositoryLoadsHQReadSideWorkspaceWithoutOpeningMutationFlows() async throws {
        let transport = AppleWeeklyTransportSpy()
        let repository = LiveAppleWeeklyReadRepository(client: JSONAPIClient(transport: transport))
        let workspace = try await repository.loadWorkspace(
            session: sampleSession(),
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!),
            context: AppleWeeklyContext(siteCode: "R692", reportYear: "2026", referenceDate: "2026-03-19")
        )
        let recordedRequests = await transport.recordedRequests()

        XCTAssertGreaterThanOrEqual(recordedRequests.count, 5)
        XCTAssertTrue(recordedRequests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer token" })
        let requestedPaths = Set(recordedRequests.compactMap { $0.url?.path })
        XCTAssertTrue(requestedPaths.contains("/api/google-sheets/mappings"))
        XCTAssertTrue(requestedPaths.contains("/api/weekly-report/week-range"))
        XCTAssertTrue(requestedPaths.contains("/api/weekly-report/site-readiness"))
        XCTAssertTrue(requestedPaths.contains("/api/weekly-report/ops-config"))
        XCTAssertTrue(requestedPaths.contains("/api/weekly-report/conflicts"))
        XCTAssertTrue(requestedPaths.contains("/api/weekly-report/dry-run"))
        XCTAssertEqual(workspace.serviceAccountEmail, "service-account@example.com")
        XCTAssertEqual(workspace.readiness.rolloutStatus, "live")
        XCTAssertEqual(workspace.dryRun.selectedSections, ["overnight_guards"])
        XCTAssertEqual(workspace.conflicts.map(\.id), ["conflict-1"])
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
