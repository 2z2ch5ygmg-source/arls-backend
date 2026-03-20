import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct SupportSubmissionWorkspaceView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                switch model.supportSubmission.state {
                case .idle:
                    EmptyStateView(
                        title: "Workspace Not Loaded",
                        message: "Load the Sentrix operator-facing support-submission handoff workspace."
                    )
                    Button("Load Workspace") {
                        Task { await model.loadSupportSubmissions() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SentrixTheme.Palette.accent)
                case .loading:
                    LoadingStateView(
                        title: "Support Submission",
                        message: "Loading handoff-only workspace state."
                    )
                    .frame(minHeight: 220)
                case .failed(let error):
                    SystemSurfaceView(surface: error.systemSurface) {
                        Task { await model.loadSupportSubmissions() }
                    }
                case .loaded(let workspace):
                    SectionCardView(title: "Workspace") {
                        KeyValueRowView(key: "Month", value: workspace.month)
                        KeyValueRowView(key: "Site", value: workspace.siteCode)
                        KeyValueRowView(key: "Route Status", value: workspace.routeStatus)
                        KeyValueRowView(key: "Workspace Owner", value: workspace.workspaceOwner)
                        KeyValueRowView(key: "Internal Only", value: workspace.internalOnly ? "true" : "false")
                    }

                    SectionCardView(title: "Handoff") {
                        KeyValueRowView(key: "Owner", value: workspace.handoff.owner)
                        KeyValueRowView(key: "Message", value: workspace.handoff.message)
                        KeyValueRowView(key: "Guidance", value: workspace.handoff.guidance)
                        KeyValueRowView(key: "URL", value: workspace.handoff.url, monospaced: true)
                    }

                    SectionCardView(title: "Ownership / Bridge") {
                        KeyValueRowView(key: "Excel Ingress Owner", value: workspace.ownership.excelIngressOwner)
                        KeyValueRowView(key: "Sentrix Owner", value: workspace.ownership.sentrixOwner)
                        KeyValueRowView(key: "Bridge Connected", value: workspace.bridgeStatus.connected ? "true" : "false")
                        KeyValueRowView(key: "Bridge Degraded", value: workspace.bridgeStatus.degraded ? "true" : "false")
                        KeyValueRowView(key: "Artifact Lookup", value: workspace.bridgeStatus.artifactLookupResult)
                        KeyValueRowView(key: "Review Aggregation", value: workspace.bridgeStatus.reviewAggregationResult)
                    }

                    SectionCardView(title: "Disabled Reasons") {
                        KeyValueRowView(key: "Reasons", value: workspace.disabledReasons.joined(separator: " | "))
                        KeyValueRowView(key: "Empty State", value: workspace.emptyReason)
                    }

                    SystemSurfaceView(
                        surface: SystemSurfaceModel(
                            kind: .warning,
                            title: "Handoff Only",
                            message: "Sentrix native shows operator-facing ARLS handoff only. Workbook upload, inspect, and apply remain outside Phase 2B."
                        )
                    )
                }
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Support Submission")
    }
}
