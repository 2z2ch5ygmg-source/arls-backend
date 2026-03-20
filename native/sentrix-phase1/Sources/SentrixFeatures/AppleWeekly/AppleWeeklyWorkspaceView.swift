import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct AppleWeeklyWorkspaceView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                switch model.appleWeekly.state {
                case .idle:
                    EmptyStateView(
                        title: "Apple Weekly Not Loaded",
                        message: "Load the HQ-confirmed Apple Weekly read-side workspace."
                    )
                    Button("Load Apple Weekly Workspace") {
                        Task { await model.loadAppleWeekly() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SentrixTheme.Palette.accent)
                case .loading:
                    LoadingStateView(
                        title: "Apple Weekly",
                        message: "Loading mappings, readiness, ops config, conflicts, and dry-run."
                    )
                    .frame(minHeight: 220)
                case .failed(let error):
                    SystemSurfaceView(surface: error.systemSurface) {
                        Task { await model.loadAppleWeekly() }
                    }
                case .loaded(let workspace):
                    SectionCardView(
                        title: "Context",
                        subtitle: "HQ-safe Apple Weekly read-side only"
                    ) {
                        KeyValueRowView(key: "Site", value: workspace.context.siteCode)
                        KeyValueRowView(key: "Report Year", value: workspace.context.reportYear)
                        KeyValueRowView(key: "Reference Date", value: workspace.context.referenceDate)
                        KeyValueRowView(key: "Service Account", value: workspace.serviceAccountEmail, monospaced: true)
                    }

                    SectionCardView(title: "Workbook Mapping") {
                        ForEach(workspace.mappings) { mapping in
                            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                                KeyValueRowView(key: "Site", value: mapping.siteCode)
                                KeyValueRowView(key: "Spreadsheet", value: mapping.spreadsheetID, monospaced: true)
                                KeyValueRowView(key: "Last Test", value: "\(mapping.lastTestStatus) · \(mapping.lastTestMessage)")
                            }
                            if mapping.id != workspace.mappings.last?.id {
                                Divider()
                            }
                        }
                    }

                    SectionCardView(title: "Readiness") {
                        KeyValueRowView(key: "Workbook Ready", value: boolLabel(workspace.readiness.workbookReady))
                        KeyValueRowView(key: "Template Ready", value: boolLabel(workspace.readiness.templateReady))
                        KeyValueRowView(key: "Baseline Ready", value: boolLabel(workspace.readiness.baselineReady))
                        KeyValueRowView(key: "ARLS Truth Ready", value: boolLabel(workspace.readiness.arlsTruthReady))
                        KeyValueRowView(key: "Preview Allowed", value: boolLabel(workspace.readiness.previewAllowed))
                        KeyValueRowView(key: "Live Write Allowed", value: boolLabel(workspace.readiness.liveWriteAllowed))
                        KeyValueRowView(key: "Rollout Status", value: workspace.readiness.rolloutStatus)
                        KeyValueRowView(key: "Overnight Reconciliation", value: workspace.readiness.overnightReconciliationStatus)
                    }

                    SectionCardView(title: "Week Range") {
                        KeyValueRowView(key: "Week Start", value: workspace.weekRange.weekStart)
                        KeyValueRowView(key: "Week End", value: workspace.weekRange.weekEnd)
                        KeyValueRowView(key: "Dates", value: workspace.weekRange.dates.joined(separator: ", "))
                    }

                    SectionCardView(title: "Dry Run") {
                        KeyValueRowView(key: "Operation", value: workspace.dryRun.operationKind)
                        KeyValueRowView(key: "Requested Sections", value: workspace.dryRun.requestedSections.joined(separator: ", "))
                        KeyValueRowView(key: "Selected Sections", value: workspace.dryRun.selectedSections.joined(separator: ", "))
                        KeyValueRowView(key: "Write Validation", value: "\(workspace.dryRun.writeValidation.status) · canWrite=\(boolLabel(workspace.dryRun.writeValidation.canWrite))")
                        KeyValueRowView(key: "Expected Targets", value: "\(workspace.dryRun.writeValidation.expectedTargetCount)")
                        KeyValueRowView(key: "Planned Writes", value: "\(workspace.dryRun.writeValidation.plannedWriteCount)")
                        KeyValueRowView(key: "Conflict Count", value: "\(workspace.dryRun.writeValidation.conflictCount)")
                    }

                    SectionCardView(title: "Ops Summary") {
                        KeyValueRowView(key: "Store", value: workspace.opsConfig.storeDisplayName)
                        KeyValueRowView(key: "Overtime Threshold", value: workspace.opsConfig.overtimeThresholdMinutes)
                        KeyValueRowView(key: "Phase2 State", value: workspace.opsConfig.phase2State)
                        KeyValueRowView(key: "Phase4 Rollout", value: workspace.opsConfig.phase4RolloutMode)
                        KeyValueRowView(key: "Phase4 Live Write", value: boolLabel(workspace.opsConfig.phase4LiveWriteAllowed))
                        KeyValueRowView(key: "Overtime Reasons", value: workspace.opsConfig.overtimeReasons.joined(separator: ", "))
                    }

                    SectionCardView(title: "Conflicts") {
                        KeyValueRowView(key: "Count", value: "\(workspace.conflicts.count)")
                    }

                    SystemSurfaceView(
                        surface: SystemSurfaceModel(
                            kind: .warning,
                            title: "Mutation Still Blocked",
                            message: "Phase 2B does not implement Apple Weekly apply, rollout, conflict resolution, or live write."
                        )
                    )
                }
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Apple Weekly")
    }

    private func boolLabel(_ value: Bool) -> String {
        value ? "true" : "false"
    }
}
