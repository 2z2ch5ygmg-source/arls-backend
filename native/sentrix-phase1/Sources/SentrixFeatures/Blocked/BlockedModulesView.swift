import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct BlockedModulesView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                RuntimeNoticeGroupView(notices: model.runtimeNotices)

                SystemSurfaceView(
                    surface: SystemSurfaceModel(
                        kind: .blocked,
                        title: "Blocked By Runtime Evidence",
                        message: "This screen documents only the areas that remain blocked after Phase 2B opened the HQ-safe and field-observed role-aware shell slices.",
                        footnote: "Adapters below are still expected to change after field or universal runtime evidence closes their blockers."
                    )
                )

                SectionCardView(
                    title: "Open In Phase 2B",
                    subtitle: "These are implemented from HQ-confirmed or field-confirmed runtime evidence and are not represented as blocked here."
                ) {
                    KeyValueRowView(key: "Stored Session", value: "soc_token + soc_user continuation only", monospaced: true)
                    KeyValueRowView(key: "Authenticated Bootstrap", value: "HQ /api/bootstrap-config repository-backed integration only")
                    KeyValueRowView(key: "Realtime", value: "HQ SSE/EventSource transport only")
                    KeyValueRowView(key: "Apple Weekly", value: "HQ read/readiness/conflict/dry-run only")
                    KeyValueRowView(key: "Support Submission", value: "Sentrix operator-facing handoff workspace only")
                    KeyValueRowView(key: "Push Diagnostics", value: "Server-side push-test result only")
                    KeyValueRowView(key: "Field Shell", value: "Supervisor / Officer role-aware shell with HQ-only route hiding and blocking")
                }

                SectionCardView(
                    title: "Runtime-Blocked Modules",
                    subtitle: "These stay behind interfaces and stubs until authenticated production capture closes them beyond the HQ-safe slice."
                ) {
                    ForEach(RuntimeBlockedArea.allCases) { area in
                        VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                            Text(area.title)
                                .font(SentrixTheme.Typography.cardTitle)
                                .foregroundStyle(SentrixTheme.Palette.ink)
                            Text(area.summary)
                                .font(SentrixTheme.Typography.body)
                                .foregroundStyle(SentrixTheme.Palette.ink)
                            KeyValueRowView(key: "Runtime Blocker Marker", value: area.blockerTag, monospaced: true)
                            KeyValueRowView(key: "Current Native Behavior", value: area.phase1StubBehavior)
                            Text(area.sourceDocuments.joined(separator: "\n"))
                                .font(SentrixTheme.Typography.caption)
                                .foregroundStyle(SentrixTheme.Palette.muted)
                            if area.id != RuntimeBlockedArea.allCases.last?.id {
                                Divider()
                            }
                        }
                    }
                }

                SectionCardView(
                    title: "Remaining Adapter Boundaries",
                    subtitle: "These compile now without live production credentials"
                ) {
                    KeyValueRowView(key: "Auth Adapter", value: String(describing: type(of: model.dependencies.authAdapter)))
                    KeyValueRowView(key: "Post-Auth Bootstrap", value: String(describing: type(of: model.dependencies.authenticatedBootstrapAdapter)))
                    KeyValueRowView(key: "Realtime Adapter", value: String(describing: type(of: model.dependencies.realtimeAdapter)))
                    KeyValueRowView(key: "Push Adapter", value: String(describing: type(of: model.dependencies.pushAdapter)))
                    KeyValueRowView(key: "Apple Weekly Adapter", value: String(describing: type(of: model.dependencies.appleWeeklyAdapter)))
                    KeyValueRowView(key: "ARLS Bridge Adapter", value: String(describing: type(of: model.dependencies.arlsBridgeAdapter)))
                }
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Blocked Modules")
    }
}
