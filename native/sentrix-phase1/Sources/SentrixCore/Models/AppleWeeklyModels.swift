import Foundation

public struct AppleWeeklyContext: Equatable, Sendable {
    public let siteCode: String
    public let reportYear: String
    public let referenceDate: String

    public init(siteCode: String, reportYear: String, referenceDate: String) {
        self.siteCode = siteCode
        self.reportYear = reportYear
        self.referenceDate = referenceDate
    }
}

public struct AppleWeeklyMapping: Equatable, Sendable, Identifiable {
    public var id: String { "\(siteCode):\(reportYear)" }
    public let siteCode: String
    public let reportYear: String
    public let siteName: String
    public let spreadsheetID: String
    public let spreadsheetURL: String
    public let lastTestStatus: String
    public let lastTestMessage: String

    public init(
        siteCode: String,
        reportYear: String,
        siteName: String,
        spreadsheetID: String,
        spreadsheetURL: String,
        lastTestStatus: String,
        lastTestMessage: String
    ) {
        self.siteCode = siteCode
        self.reportYear = reportYear
        self.siteName = siteName
        self.spreadsheetID = spreadsheetID
        self.spreadsheetURL = spreadsheetURL
        self.lastTestStatus = lastTestStatus
        self.lastTestMessage = lastTestMessage
    }
}

public struct AppleWeeklyWeekDay: Equatable, Sendable, Identifiable {
    public var id: String { date }
    public let date: String
    public let monthTabName: String
    public let rowDay: Int
    public let rowNight: Int
    public let weekdayLabel: String

    public init(
        date: String,
        monthTabName: String,
        rowDay: Int,
        rowNight: Int,
        weekdayLabel: String
    ) {
        self.date = date
        self.monthTabName = monthTabName
        self.rowDay = rowDay
        self.rowNight = rowNight
        self.weekdayLabel = weekdayLabel
    }
}

public struct AppleWeeklyWeekRange: Equatable, Sendable {
    public let weekStart: String
    public let weekEnd: String
    public let referenceDate: String
    public let dates: [String]
    public let days: [AppleWeeklyWeekDay]

    public init(
        weekStart: String,
        weekEnd: String,
        referenceDate: String,
        dates: [String],
        days: [AppleWeeklyWeekDay]
    ) {
        self.weekStart = weekStart
        self.weekEnd = weekEnd
        self.referenceDate = referenceDate
        self.dates = dates
        self.days = days
    }
}

public struct AppleWeeklyInfoMessage: Equatable, Sendable, Identifiable {
    public var id: String { "\(kind):\(message)" }
    public let kind: String
    public let message: String

    public init(kind: String, message: String) {
        self.kind = kind
        self.message = message
    }
}

public struct AppleWeeklyReadiness: Equatable, Sendable {
    public let schemaVersion: String
    public let siteCode: String
    public let siteName: String
    public let reportYear: String
    public let referenceDate: String
    public let workbookReady: Bool
    public let templateReady: Bool
    public let baselineReady: Bool
    public let arlsTruthReady: Bool
    public let previewAllowed: Bool
    public let liveWriteAllowed: Bool
    public let rolloutStatus: String
    public let blockingIssues: [String]
    public let warnings: [String]
    public let overnightReconciliationStatus: String
    public let infoMessages: [AppleWeeklyInfoMessage]

    public init(
        schemaVersion: String,
        siteCode: String,
        siteName: String,
        reportYear: String,
        referenceDate: String,
        workbookReady: Bool,
        templateReady: Bool,
        baselineReady: Bool,
        arlsTruthReady: Bool,
        previewAllowed: Bool,
        liveWriteAllowed: Bool,
        rolloutStatus: String,
        blockingIssues: [String],
        warnings: [String],
        overnightReconciliationStatus: String,
        infoMessages: [AppleWeeklyInfoMessage]
    ) {
        self.schemaVersion = schemaVersion
        self.siteCode = siteCode
        self.siteName = siteName
        self.reportYear = reportYear
        self.referenceDate = referenceDate
        self.workbookReady = workbookReady
        self.templateReady = templateReady
        self.baselineReady = baselineReady
        self.arlsTruthReady = arlsTruthReady
        self.previewAllowed = previewAllowed
        self.liveWriteAllowed = liveWriteAllowed
        self.rolloutStatus = rolloutStatus
        self.blockingIssues = blockingIssues
        self.warnings = warnings
        self.overnightReconciliationStatus = overnightReconciliationStatus
        self.infoMessages = infoMessages
    }
}

public struct AppleWeeklyOpsConfig: Equatable, Sendable {
    public let siteCode: String
    public let reportYear: String
    public let storeDisplayName: String
    public let overtimeThresholdMinutes: String
    public let overtimeReasons: [String]
    public let phase2State: String
    public let phase4RolloutMode: String
    public let phase4LiveWriteAllowed: Bool

    public init(
        siteCode: String,
        reportYear: String,
        storeDisplayName: String,
        overtimeThresholdMinutes: String,
        overtimeReasons: [String],
        phase2State: String,
        phase4RolloutMode: String,
        phase4LiveWriteAllowed: Bool
    ) {
        self.siteCode = siteCode
        self.reportYear = reportYear
        self.storeDisplayName = storeDisplayName
        self.overtimeThresholdMinutes = overtimeThresholdMinutes
        self.overtimeReasons = overtimeReasons
        self.phase2State = phase2State
        self.phase4RolloutMode = phase4RolloutMode
        self.phase4LiveWriteAllowed = phase4LiveWriteAllowed
    }
}

public struct AppleWeeklyConflict: Equatable, Sendable, Identifiable {
    public let id: String
    public let title: String

    public init(id: String, title: String) {
        self.id = id
        self.title = title
    }
}

public struct AppleWeeklyWriteValidation: Equatable, Sendable {
    public let status: String
    public let canWrite: Bool
    public let expectedTargetCount: Int
    public let plannedWriteCount: Int
    public let conflictCount: Int

    public init(
        status: String,
        canWrite: Bool,
        expectedTargetCount: Int,
        plannedWriteCount: Int,
        conflictCount: Int
    ) {
        self.status = status
        self.canWrite = canWrite
        self.expectedTargetCount = expectedTargetCount
        self.plannedWriteCount = plannedWriteCount
        self.conflictCount = conflictCount
    }
}

public struct AppleWeeklyDryRun: Equatable, Sendable {
    public let operationKind: String
    public let requestedSections: [String]
    public let selectedSections: [String]
    public let writeValidation: AppleWeeklyWriteValidation

    public init(
        operationKind: String,
        requestedSections: [String],
        selectedSections: [String],
        writeValidation: AppleWeeklyWriteValidation
    ) {
        self.operationKind = operationKind
        self.requestedSections = requestedSections
        self.selectedSections = selectedSections
        self.writeValidation = writeValidation
    }
}

public struct AppleWeeklyWorkspace: Equatable, Sendable {
    public let context: AppleWeeklyContext
    public let serviceAccountEmail: String
    public let mappings: [AppleWeeklyMapping]
    public let weekRange: AppleWeeklyWeekRange
    public let readiness: AppleWeeklyReadiness
    public let opsConfig: AppleWeeklyOpsConfig
    public let conflicts: [AppleWeeklyConflict]
    public let dryRun: AppleWeeklyDryRun

    public init(
        context: AppleWeeklyContext,
        serviceAccountEmail: String,
        mappings: [AppleWeeklyMapping],
        weekRange: AppleWeeklyWeekRange,
        readiness: AppleWeeklyReadiness,
        opsConfig: AppleWeeklyOpsConfig,
        conflicts: [AppleWeeklyConflict],
        dryRun: AppleWeeklyDryRun
    ) {
        self.context = context
        self.serviceAccountEmail = serviceAccountEmail
        self.mappings = mappings
        self.weekRange = weekRange
        self.readiness = readiness
        self.opsConfig = opsConfig
        self.conflicts = conflicts
        self.dryRun = dryRun
    }
}
