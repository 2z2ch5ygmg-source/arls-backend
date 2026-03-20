import Foundation

struct SupportSubmissionWorkspaceDTO: Decodable {
    struct EmptyStateDTO: Decodable {
        let reason: String
    }

    struct ActionStateDTO: Decodable {
        let disabledReasons: [String]

        enum CodingKeys: String, CodingKey {
            case disabledReasons = "disabled_reasons"
        }
    }

    struct OwnershipDTO: Decodable {
        let excelIngressOwner: String
        let sentrixOwner: String

        enum CodingKeys: String, CodingKey {
            case excelIngressOwner = "excel_ingress_owner"
            case sentrixOwner = "sentrix_owner"
        }
    }

    struct HandoffDTO: Decodable {
        let owner: String
        let message: String
        let guidance: String
        let url: String
    }

    struct BridgeStatusDTO: Decodable {
        let connected: Bool
        let degraded: Bool
        let artifactLookupResult: String
        let reviewAggregationResult: String

        enum CodingKeys: String, CodingKey {
            case connected
            case degraded
            case artifactLookupResult = "artifact_lookup_result"
            case reviewAggregationResult = "review_aggregation_result"
        }
    }

    let month: String
    let selectedSite: SelectedSiteDTO
    let artifactAvailable: Bool
    let emptyState: EmptyStateDTO
    let actionState: ActionStateDTO
    let workspaceOwner: String
    let routeStatus: String
    let internalOnly: Bool
    let ownership: OwnershipDTO
    let handoff: HandoffDTO
    let bridgeStatus: BridgeStatusDTO

    struct SelectedSiteDTO: Decodable {
        let siteCode: String

        enum CodingKeys: String, CodingKey {
            case siteCode = "site_code"
        }
    }

    enum CodingKeys: String, CodingKey {
        case month
        case selectedSite = "selected_site"
        case artifactAvailable = "artifact_available"
        case emptyState = "empty_state"
        case actionState = "action_state"
        case workspaceOwner = "workspace_owner"
        case routeStatus = "route_status"
        case internalOnly = "internal_only"
        case ownership
        case handoff
        case bridgeStatus = "bridge_status"
    }
}
