import Foundation

struct GoogleSheetsMappingsDTO: Decodable {
    struct MappingDTO: Decodable {
        let siteCode: String
        let reportYear: String
        let siteName: String
        let spreadsheetID: String
        let spreadsheetURL: String
        let lastTestStatus: String
        let lastTestMessage: String

        enum CodingKeys: String, CodingKey {
            case siteCode = "site_code"
            case reportYear = "report_year"
            case siteName = "site_name"
            case spreadsheetID = "spreadsheet_id"
            case spreadsheetURL = "spreadsheet_url"
            case lastTestStatus = "last_test_status"
            case lastTestMessage = "last_test_message"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            siteCode = container.decodeLossyString(forKey: .siteCode)
            reportYear = container.decodeLossyString(forKey: .reportYear)
            siteName = container.decodeLossyString(forKey: .siteName)
            spreadsheetID = container.decodeLossyString(forKey: .spreadsheetID)
            spreadsheetURL = container.decodeLossyString(forKey: .spreadsheetURL)
            lastTestStatus = container.decodeLossyString(forKey: .lastTestStatus)
            lastTestMessage = container.decodeLossyString(forKey: .lastTestMessage)
        }
    }

    let serviceAccountEmail: String
    let mappings: [MappingDTO]

    enum CodingKeys: String, CodingKey {
        case serviceAccountEmail = "service_account_email"
        case mappings
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        serviceAccountEmail = container.decodeLossyString(forKey: .serviceAccountEmail)
        mappings = container.decodeLossyArray(forKey: .mappings)
    }
}

struct WeeklyWeekRangeDTO: Decodable {
    struct DayDTO: Decodable {
        let date: String
        let monthTabName: String
        let rowDay: Int
        let rowNight: Int
        let weekdayLabel: String

        enum CodingKeys: String, CodingKey {
            case date
            case monthTabName = "month_tab_name"
            case rowDay = "row_day"
            case rowNight = "row_night"
            case weekdayLabel = "weekday_label"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            date = container.decodeLossyString(forKey: .date)
            monthTabName = container.decodeLossyString(forKey: .monthTabName)
            rowDay = container.decodeLossyInt(forKey: .rowDay)
            rowNight = container.decodeLossyInt(forKey: .rowNight)
            weekdayLabel = container.decodeLossyString(forKey: .weekdayLabel)
        }
    }

    let weekStart: String
    let weekEnd: String
    let referenceDate: String
    let dates: [String]
    let days: [DayDTO]

    enum CodingKeys: String, CodingKey {
        case weekStart = "week_start"
        case weekEnd = "week_end"
        case referenceDate = "reference_date"
        case dates
        case days
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        weekStart = container.decodeLossyString(forKey: .weekStart)
        weekEnd = container.decodeLossyString(forKey: .weekEnd)
        referenceDate = container.decodeLossyString(forKey: .referenceDate)
        dates = container.decodeLossyStringArray(forKey: .dates)
        days = container.decodeLossyArray(forKey: .days)
    }
}

struct WeeklySiteReadinessResponseDTO: Decodable {
    struct ReadinessDTO: Decodable {
        struct InfoDTO: Decodable {
            let kind: String
            let message: String
        }

        let schemaVersion: String
        let siteCode: String
        let siteName: String
        let reportYear: String
        let referenceDate: String
        let workbookReady: Bool
        let templateReady: Bool
        let baselineReady: Bool
        let arlsTruthReady: Bool
        let previewAllowed: Bool
        let liveWriteAllowed: Bool
        let rolloutStatus: String
        let blockingIssues: [String]
        let warnings: [String]
        let overnightReconciliationStatus: String
        let info: [InfoDTO]

        enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version"
            case siteCode = "site_code"
            case siteName = "site_name"
            case reportYear = "report_year"
            case referenceDate = "reference_date"
            case workbookReady = "workbook_ready"
            case templateReady = "template_ready"
            case baselineReady = "baseline_ready"
            case arlsTruthReady = "arls_truth_ready"
            case previewAllowed = "preview_allowed"
            case liveWriteAllowed = "live_write_allowed"
            case rolloutStatus = "rollout_status"
            case blockingIssues = "blocking_issues"
            case warnings
            case overnightReconciliationStatus = "overnight_reconciliation_status"
            case info
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            schemaVersion = container.decodeLossyString(forKey: .schemaVersion)
            siteCode = container.decodeLossyString(forKey: .siteCode)
            siteName = container.decodeLossyString(forKey: .siteName)
            reportYear = container.decodeLossyString(forKey: .reportYear)
            referenceDate = container.decodeLossyString(forKey: .referenceDate)
            workbookReady = container.decodeLossyBool(forKey: .workbookReady)
            templateReady = container.decodeLossyBool(forKey: .templateReady)
            baselineReady = container.decodeLossyBool(forKey: .baselineReady)
            arlsTruthReady = container.decodeLossyBool(forKey: .arlsTruthReady)
            previewAllowed = container.decodeLossyBool(forKey: .previewAllowed)
            liveWriteAllowed = container.decodeLossyBool(forKey: .liveWriteAllowed)
            rolloutStatus = container.decodeLossyString(forKey: .rolloutStatus)
            blockingIssues = container.decodeLossyStringArray(forKey: .blockingIssues)
            warnings = container.decodeLossyStringArray(forKey: .warnings)
            overnightReconciliationStatus = container.decodeLossyString(forKey: .overnightReconciliationStatus)
            info = container.decodeLossyArray(forKey: .info)
        }
    }

    let readiness: ReadinessDTO
}

struct WeeklyOpsConfigResponseDTO: Decodable {
    struct ConfigDTO: Decodable {
        struct OvertimeRulesDTO: Decodable {
            let thresholdMinutes: String
            let reasons: [String]

            enum CodingKeys: String, CodingKey {
                case thresholdMinutes = "threshold_minutes"
                case reasons
            }

            init(thresholdMinutes: String, reasons: [String]) {
                self.thresholdMinutes = thresholdMinutes
                self.reasons = reasons
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                thresholdMinutes = container.decodeLossyString(forKey: .thresholdMinutes)
                reasons = container.decodeLossyStringArray(forKey: .reasons)
            }
        }

        struct StoreBaselineDTO: Decodable {
            let storeDisplayName: String

            enum CodingKeys: String, CodingKey {
                case storeDisplayName = "store_display_name"
            }

            init(storeDisplayName: String) {
                self.storeDisplayName = storeDisplayName
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                storeDisplayName = container.decodeLossyString(forKey: .storeDisplayName)
            }
        }

        struct Phase2ReadinessDTO: Decodable {
            let state: String

            init(state: String) {
                self.state = state
            }
        }

        struct Phase4RolloutDTO: Decodable {
            let resolvedRolloutMode: String

            enum CodingKeys: String, CodingKey {
                case resolvedRolloutMode = "resolved_rollout_mode"
            }

            init(resolvedRolloutMode: String) {
                self.resolvedRolloutMode = resolvedRolloutMode
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                resolvedRolloutMode = container.decodeLossyString(forKey: .resolvedRolloutMode)
            }
        }

        struct Phase4ReadinessDTO: Decodable {
            let liveWriteAllowed: Bool

            enum CodingKeys: String, CodingKey {
                case liveWriteAllowed = "live_write_allowed"
            }

            init(liveWriteAllowed: Bool) {
                self.liveWriteAllowed = liveWriteAllowed
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                liveWriteAllowed = container.decodeLossyBool(forKey: .liveWriteAllowed)
            }
        }

        let siteCode: String
        let reportYear: String
        let overtimeRules: OvertimeRulesDTO
        let storeBaseline: StoreBaselineDTO
        let phase2Readiness: Phase2ReadinessDTO
        let phase4Rollout: Phase4RolloutDTO
        let phase4Readiness: Phase4ReadinessDTO

        enum CodingKeys: String, CodingKey {
            case siteCode = "site_code"
            case reportYear = "report_year"
            case overtimeRules = "overtime_rules"
            case storeBaseline = "store_baseline"
            case phase2Readiness = "phase2_readiness"
            case phase4Rollout = "phase4_rollout"
            case phase4Readiness = "phase4_readiness"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            siteCode = container.decodeLossyString(forKey: .siteCode)
            reportYear = container.decodeLossyString(forKey: .reportYear)
            overtimeRules = container.decodeLossyObject(forKey: .overtimeRules, default: .init(thresholdMinutes: "", reasons: []))
            storeBaseline = container.decodeLossyObject(forKey: .storeBaseline, default: .init(storeDisplayName: ""))
            phase2Readiness = container.decodeLossyObject(forKey: .phase2Readiness, default: .init(state: ""))
            phase4Rollout = container.decodeLossyObject(forKey: .phase4Rollout, default: .init(resolvedRolloutMode: ""))
            phase4Readiness = container.decodeLossyObject(forKey: .phase4Readiness, default: .init(liveWriteAllowed: false))
        }
    }

    let config: ConfigDTO
}

struct WeeklyConflictsResponseDTO: Decodable {
    let conflicts: [ConflictDTO]

    struct ConflictDTO: Decodable {
        let id: String

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let value = try? container.decode(String.self) {
                id = value
            } else if let value = try? container.decode(Int.self) {
                id = String(value)
            } else {
                let keyed = try decoder.container(keyedBy: GenericCodingKey.self)
                id = keyed.decodeLossyString(forKey: .init(stringValue: "id"))
            }
        }
    }
}

struct WeeklyDryRunResponseDTO: Decodable {
    struct PackageDTO: Decodable {
        struct SelectedDTO: Decodable {
            let sections: [String]
        }

        struct WriteValidationDTO: Decodable {
            let status: String
            let canWrite: Bool

            enum CodingKeys: String, CodingKey {
                case status
                case canWrite = "can_write"
            }
        }

        struct RangeValidationDTO: Decodable {
            let expectedTargetCount: Int
            let plannedWriteCount: Int
            let conflictCount: Int

            enum CodingKeys: String, CodingKey {
                case expectedTargetCount = "expected_target_count"
                case plannedWriteCount = "planned_write_count"
                case conflictCount = "conflict_count"
            }
        }

        let operationKind: String
        let selected: SelectedDTO
        let writeValidation: WriteValidationDTO
        let rangeValidation: RangeValidationDTO

        enum CodingKeys: String, CodingKey {
            case operationKind = "operation_kind"
            case selected
            case writeValidation = "write_validation"
            case rangeValidation = "range_validation"
        }
    }

    let operationKind: String
    let package: PackageDTO

    enum CodingKeys: String, CodingKey {
        case operationKind = "operation_kind"
        case package
    }
}
