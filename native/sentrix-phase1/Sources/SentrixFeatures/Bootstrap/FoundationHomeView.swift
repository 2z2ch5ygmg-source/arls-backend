import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct FoundationHomeView: View {
    @ObservedObject private var model: Phase1AppModel
    private let snapshot: PublicBootstrapSnapshot

    public init(model: Phase1AppModel, snapshot: PublicBootstrapSnapshot) {
        self.model = model
        self.snapshot = snapshot
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                header

                RuntimeNoticeGroupView(notices: snapshot.notices)

                SectionCardView(
                    title: "Public Bootstrap",
                    subtitle: "Safe-to-freeze runtime contract confirmed in production"
                ) {
                    KeyValueRowView(key: "Base URL", value: snapshot.environment.baseURL.absoluteString, monospaced: true)
                    KeyValueRowView(key: "Tenant", value: snapshot.appConfig.tenantID)
                    KeyValueRowView(key: "Read-Only", value: snapshot.appConfig.readOnly ? "Enabled" : "Disabled")
                    KeyValueRowView(key: "Master Data Read-Only", value: snapshot.appConfig.masterDataReadOnly ? "Enabled" : "Disabled")
                    KeyValueRowView(key: "Bootstrap Endpoint", value: snapshot.appConfig.endpoints.bootstrapConfig, monospaced: true)
                }

                SectionCardView(
                    title: "Confirmed Public Feature Flags",
                    subtitle: "Consumed only from runtime-confirmed public sources in the current native foundation"
                ) {
                    featureRow("Important Incident", enabled: snapshot.appConfig.features.importantIncidentEnabled)
                    featureRow("Incident Participant", enabled: snapshot.appConfig.features.incidentParticipantEnabled)
                    featureRow("Timer", enabled: snapshot.appConfig.features.timerEnabled)
                    featureRow("Legacy Admin Menu", enabled: snapshot.appConfig.features.legacyAdminMenuEnabled)
                    featureRow("Data Dictionary", enabled: snapshot.appConfig.features.dataDictionaryEnabled)
                    featureRow("WebSocket", enabled: snapshot.appConfig.features.websocketEnabled)
                    featureRow("GPS", enabled: snapshot.appConfig.features.gpsEnabled)
                }

                LoginContainerView(model: model)

                SectionCardView(
                    title: "Foundation Navigation",
                    subtitle: "Public diagnostics stay open here. Authenticated shells open only after stored-session role gating succeeds."
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
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Sentrix Phase 2B")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xs) {
            Text("Sentrix Native Phase 2B")
                .font(SentrixTheme.Typography.pageTitle)
                .foregroundStyle(SentrixTheme.Palette.ink)
            Text("Public bootstrap stays live, runtime-confirmed HQ or field-observed stored-session restoration is allowed, and unresolved field or universal behavior remains explicitly blocked.")
                .font(SentrixTheme.Typography.body)
                .foregroundStyle(SentrixTheme.Palette.muted)
        }
    }

    private func featureRow(_ label: String, enabled: Bool) -> some View {
        HStack {
            Text(label)
                .font(SentrixTheme.Typography.body)
                .foregroundStyle(SentrixTheme.Palette.ink)
            Spacer()
            Text(enabled ? "Enabled" : "Disabled")
                .font(SentrixTheme.Typography.caption)
                .foregroundStyle(enabled ? SentrixTheme.Palette.success : SentrixTheme.Palette.muted)
        }
    }
}
