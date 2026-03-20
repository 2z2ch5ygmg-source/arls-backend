import XCTest
@testable import SentrixAPI
import SentrixCore

final class AppleWeeklyMapperTests: XCTestCase {
    func testDryRunMapperPreservesRequestedAndSelectedSectionsSeparately() throws {
        let payload = """
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
              "expected_target_count": 7,
              "planned_write_count": 3,
              "conflict_count": 0
            }
          }
        }
        """
        let dto = try JSONDecoder().decode(WeeklyDryRunResponseDTO.self, from: Data(payload.utf8))
        let dryRun = AppleWeeklyMapper.mapDryRun(dto, requestedSections: ["attendance", "overtime", "overnight_guards"])

        XCTAssertEqual(dryRun.requestedSections, ["attendance", "overtime", "overnight_guards"])
        XCTAssertEqual(dryRun.selectedSections, ["overnight_guards"])
        XCTAssertEqual(dryRun.writeValidation.status, "ready")
        XCTAssertEqual(dryRun.writeValidation.plannedWriteCount, 3)
    }

    func testReadinessMapperPreservesLiveWriteAndRollout() throws {
        let payload = """
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
            "info": [{"kind": "info", "message": "ok"}]
          }
        }
        """
        let dto = try JSONDecoder().decode(WeeklySiteReadinessResponseDTO.self, from: Data(payload.utf8))
        let readiness = AppleWeeklyMapper.mapReadiness(dto)

        XCTAssertTrue(readiness.liveWriteAllowed)
        XCTAssertEqual(readiness.rolloutStatus, "live")
        XCTAssertEqual(readiness.infoMessages.first?.message, "ok")
    }
}
