import Foundation

public struct SupportSubmissionContext: Equatable, Sendable {
    public let month: String
    public let siteCode: String

    public init(month: String, siteCode: String) {
        self.month = month
        self.siteCode = siteCode
    }
}

public struct SupportSubmissionOwnership: Equatable, Sendable {
    public let excelIngressOwner: String
    public let sentrixOwner: String

    public init(excelIngressOwner: String, sentrixOwner: String) {
        self.excelIngressOwner = excelIngressOwner
        self.sentrixOwner = sentrixOwner
    }
}

public struct SupportSubmissionHandoff: Equatable, Sendable {
    public let owner: String
    public let message: String
    public let guidance: String
    public let url: String

    public init(owner: String, message: String, guidance: String, url: String) {
        self.owner = owner
        self.message = message
        self.guidance = guidance
        self.url = url
    }
}

public struct SupportSubmissionBridgeStatus: Equatable, Sendable {
    public let connected: Bool
    public let degraded: Bool
    public let artifactLookupResult: String
    public let reviewAggregationResult: String

    public init(
        connected: Bool,
        degraded: Bool,
        artifactLookupResult: String,
        reviewAggregationResult: String
    ) {
        self.connected = connected
        self.degraded = degraded
        self.artifactLookupResult = artifactLookupResult
        self.reviewAggregationResult = reviewAggregationResult
    }
}

public struct SupportSubmissionWorkspace: Equatable, Sendable {
    public let month: String
    public let siteCode: String
    public let routeStatus: String
    public let workspaceOwner: String
    public let internalOnly: Bool
    public let artifactAvailable: Bool
    public let emptyReason: String
    public let disabledReasons: [String]
    public let ownership: SupportSubmissionOwnership
    public let handoff: SupportSubmissionHandoff
    public let bridgeStatus: SupportSubmissionBridgeStatus

    public init(
        month: String,
        siteCode: String,
        routeStatus: String,
        workspaceOwner: String,
        internalOnly: Bool,
        artifactAvailable: Bool,
        emptyReason: String,
        disabledReasons: [String],
        ownership: SupportSubmissionOwnership,
        handoff: SupportSubmissionHandoff,
        bridgeStatus: SupportSubmissionBridgeStatus
    ) {
        self.month = month
        self.siteCode = siteCode
        self.routeStatus = routeStatus
        self.workspaceOwner = workspaceOwner
        self.internalOnly = internalOnly
        self.artifactAvailable = artifactAvailable
        self.emptyReason = emptyReason
        self.disabledReasons = disabledReasons
        self.ownership = ownership
        self.handoff = handoff
        self.bridgeStatus = bridgeStatus
    }
}
