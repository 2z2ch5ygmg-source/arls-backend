import Foundation
import SentrixCore

enum SupportSubmissionMapper {
    static func map(_ dto: SupportSubmissionWorkspaceDTO) -> SupportSubmissionWorkspace {
        SupportSubmissionWorkspace(
            month: dto.month,
            siteCode: dto.selectedSite.siteCode,
            routeStatus: dto.routeStatus,
            workspaceOwner: dto.workspaceOwner,
            internalOnly: dto.internalOnly,
            artifactAvailable: dto.artifactAvailable,
            emptyReason: dto.emptyState.reason,
            disabledReasons: dto.actionState.disabledReasons,
            ownership: SupportSubmissionOwnership(
                excelIngressOwner: dto.ownership.excelIngressOwner,
                sentrixOwner: dto.ownership.sentrixOwner
            ),
            handoff: SupportSubmissionHandoff(
                owner: dto.handoff.owner,
                message: dto.handoff.message,
                guidance: dto.handoff.guidance,
                url: dto.handoff.url
            ),
            bridgeStatus: SupportSubmissionBridgeStatus(
                connected: dto.bridgeStatus.connected,
                degraded: dto.bridgeStatus.degraded,
                artifactLookupResult: dto.bridgeStatus.artifactLookupResult,
                reviewAggregationResult: dto.bridgeStatus.reviewAggregationResult
            )
        )
    }
}
