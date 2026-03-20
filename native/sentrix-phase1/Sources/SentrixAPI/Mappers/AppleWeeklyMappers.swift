import Foundation
import SentrixCore

enum AppleWeeklyMapper {
    static func mapMappings(_ dto: GoogleSheetsMappingsDTO) -> (String, [AppleWeeklyMapping]) {
        (
            dto.serviceAccountEmail,
            dto.mappings.map {
                AppleWeeklyMapping(
                    siteCode: $0.siteCode,
                    reportYear: $0.reportYear,
                    siteName: $0.siteName,
                    spreadsheetID: $0.spreadsheetID,
                    spreadsheetURL: $0.spreadsheetURL,
                    lastTestStatus: $0.lastTestStatus,
                    lastTestMessage: $0.lastTestMessage
                )
            }
        )
    }

    static func mapWeekRange(_ dto: WeeklyWeekRangeDTO) -> AppleWeeklyWeekRange {
        AppleWeeklyWeekRange(
            weekStart: dto.weekStart,
            weekEnd: dto.weekEnd,
            referenceDate: dto.referenceDate,
            dates: dto.dates,
            days: dto.days.map {
                AppleWeeklyWeekDay(
                    date: $0.date,
                    monthTabName: $0.monthTabName,
                    rowDay: $0.rowDay,
                    rowNight: $0.rowNight,
                    weekdayLabel: $0.weekdayLabel
                )
            }
        )
    }

    static func mapReadiness(_ dto: WeeklySiteReadinessResponseDTO) -> AppleWeeklyReadiness {
        AppleWeeklyReadiness(
            schemaVersion: dto.readiness.schemaVersion,
            siteCode: dto.readiness.siteCode,
            siteName: dto.readiness.siteName,
            reportYear: dto.readiness.reportYear,
            referenceDate: dto.readiness.referenceDate,
            workbookReady: dto.readiness.workbookReady,
            templateReady: dto.readiness.templateReady,
            baselineReady: dto.readiness.baselineReady,
            arlsTruthReady: dto.readiness.arlsTruthReady,
            previewAllowed: dto.readiness.previewAllowed,
            liveWriteAllowed: dto.readiness.liveWriteAllowed,
            rolloutStatus: dto.readiness.rolloutStatus,
            blockingIssues: dto.readiness.blockingIssues,
            warnings: dto.readiness.warnings,
            overnightReconciliationStatus: dto.readiness.overnightReconciliationStatus,
            infoMessages: dto.readiness.info.map { AppleWeeklyInfoMessage(kind: $0.kind, message: $0.message) }
        )
    }

    static func mapOpsConfig(_ dto: WeeklyOpsConfigResponseDTO) -> AppleWeeklyOpsConfig {
        AppleWeeklyOpsConfig(
            siteCode: dto.config.siteCode,
            reportYear: dto.config.reportYear,
            storeDisplayName: dto.config.storeBaseline.storeDisplayName,
            overtimeThresholdMinutes: dto.config.overtimeRules.thresholdMinutes,
            overtimeReasons: dto.config.overtimeRules.reasons,
            phase2State: dto.config.phase2Readiness.state,
            phase4RolloutMode: dto.config.phase4Rollout.resolvedRolloutMode,
            phase4LiveWriteAllowed: dto.config.phase4Readiness.liveWriteAllowed
        )
    }

    static func mapConflicts(_ dto: WeeklyConflictsResponseDTO) -> [AppleWeeklyConflict] {
        dto.conflicts.map { AppleWeeklyConflict(id: $0.id, title: $0.id) }
    }

    static func mapDryRun(_ dto: WeeklyDryRunResponseDTO, requestedSections: [String]) -> AppleWeeklyDryRun {
        AppleWeeklyDryRun(
            operationKind: dto.operationKind,
            requestedSections: requestedSections,
            selectedSections: dto.package.selected.sections,
            writeValidation: AppleWeeklyWriteValidation(
                status: dto.package.writeValidation.status,
                canWrite: dto.package.writeValidation.canWrite,
                expectedTargetCount: dto.package.rangeValidation.expectedTargetCount,
                plannedWriteCount: dto.package.rangeValidation.plannedWriteCount,
                conflictCount: dto.package.rangeValidation.conflictCount
            )
        )
    }
}
