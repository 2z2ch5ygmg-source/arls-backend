import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct FieldAuthenticatedHomeView: View {
    @ObservedObject private var model: Phase1AppModel
    private let publicSnapshot: PublicBootstrapSnapshot
    private let role: String

    public init(model: Phase1AppModel, publicSnapshot: PublicBootstrapSnapshot, role: String) {
        self.model = model
        self.publicSnapshot = publicSnapshot
        self.role = role
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                RuntimeNoticeGroupView(notices: publicSnapshot.notices)

                header
                fieldGatingSection
                navigationSection
                unresolvedFootnote
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Sentrix Phase 2B")
    }

    private var header: some View {
        SectionCardView(
            title: "Field-Observed Authenticated Shell",
            subtitle: "Supervisor and Officer login success is runtime-confirmed. HQ-only authenticated features stay hidden or blocked here."
        ) {
            KeyValueRowView(key: "Observed Role", value: role)
            KeyValueRowView(key: "Runtime Scope", value: model.authenticatedShellScope?.runtimeAccessLabel ?? "-")
            KeyValueRowView(key: "User", value: model.session.currentSession?.user.fullName ?? "-")
            KeyValueRowView(key: "Site", value: model.session.currentSession?.user.siteID ?? "-")
            KeyValueRowView(key: "Stored Session Keys", value: model.session.currentSession?.storageKeys.joined(separator: ", ") ?? "-")

            Button("Logout Stored Session") {
                model.logout()
            }
            .buttonStyle(.bordered)
        }
    }

    private var fieldGatingSection: some View {
        SectionCardView(
            title: "Confirmed Field Gating",
            subtitle: "Only field-observed navigation differences proven at runtime are represented in Phase 2B."
        ) {
            KeyValueRowView(key: "Apple Weekly Menu", value: "hidden")
            KeyValueRowView(key: "Apple Weekly Direct Route", value: "blocked / redirected")
            KeyValueRowView(key: "HQ Bootstrap Contract", value: "not assumed for field")
            KeyValueRowView(key: "Support Submission", value: "still unresolved for field")
            KeyValueRowView(key: "Push Diagnostics", value: "still unresolved for field")
        }
    }

    private var navigationSection: some View {
        SectionCardView(
            title: "Field-Observed Navigation",
            subtitle: "Diagnostics stay open. HQ-only authenticated routes remain blocked."
        ) {
            Button("Open Diagnostics") {
                model.openDiagnostics()
            }
            .buttonStyle(.borderedProminent)
            .tint(SentrixTheme.Palette.accent)

            Button("Open Blocked Modules") {
                model.openBlockedModules()
            }
            .buttonStyle(.bordered)
        }
    }

    private var unresolvedFootnote: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(
                kind: .warning,
                title: "Still Unresolved",
                message: "Field /api/bootstrap-config, field support-submission behavior, disabled/HR-linked accounts, and universal permission rules remain blocked outside this shell."
            )
        )
    }
}
