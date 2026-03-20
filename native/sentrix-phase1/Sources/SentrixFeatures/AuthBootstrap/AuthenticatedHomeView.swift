import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct AuthenticatedHomeView: View {
    @ObservedObject private var model: Phase1AppModel
    private let publicSnapshot: PublicBootstrapSnapshot

    public init(model: Phase1AppModel, publicSnapshot: PublicBootstrapSnapshot) {
        self.model = model
        self.publicSnapshot = publicSnapshot
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                RuntimeNoticeGroupView(notices: publicSnapshot.notices)

                switch model.authenticatedShell.state {
                case .idle, .loading:
                    LoadingStateView(
                        title: "HQ Authenticated Shell",
                        message: "Restoring stored HQ session and loading runtime-confirmed HQ authenticated bootstrap."
                    )
                    .frame(minHeight: 220)
                case .failed(let error):
                    SystemSurfaceView(surface: error.systemSurface) {
                        Task { await model.retryAuthenticatedShell() }
                    }

                    Button("Logout Stored Session") {
                        model.logout()
                    }
                    .buttonStyle(.bordered)
                case .loaded(let snapshot):
                    header(snapshot: snapshot)
                    realtimeSection
                    navigationSection
                    blockedFootnote
                }
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Sentrix Phase 2B")
    }

    private func header(snapshot: AuthenticatedBootstrapSnapshot) -> some View {
        SectionCardView(
            title: "HQ Authenticated Shell",
            subtitle: "Stored-session continuation only. This remains the HQ-safe authenticated slice."
        ) {
            KeyValueRowView(key: "User", value: snapshot.user.fullName)
            KeyValueRowView(key: "Role", value: snapshot.user.role)
            KeyValueRowView(key: "Runtime Scope", value: model.authenticatedShellScope?.runtimeAccessLabel ?? "-")
            KeyValueRowView(key: "Tenant", value: snapshot.user.tenantID)
            KeyValueRowView(key: "Site", value: snapshot.user.siteID)
            KeyValueRowView(key: "Stored Session Keys", value: model.session.currentSession?.storageKeys.joined(separator: ", ") ?? "-")
            KeyValueRowView(key: "Ticket Templates", value: "\(snapshot.ticketConfig.templates.count)")
            KeyValueRowView(key: "Report Templates", value: "\(snapshot.reportConfig.templates.count)")
            Button("Logout Stored Session") {
                model.logout()
            }
            .buttonStyle(.bordered)
        }
    }

    private var realtimeSection: some View {
        SectionCardView(
            title: "Realtime",
            subtitle: "HQ-confirmed runtime currently uses SSE/EventSource. Ordering remains blocked."
        ) {
            KeyValueRowView(key: "Transport", value: model.realtime.snapshot.transport.rawValue.uppercased())
            KeyValueRowView(key: "Status", value: realtimeStatusLabel(model.realtime.snapshot.status))
            KeyValueRowView(key: "Endpoint", value: model.realtime.snapshot.endpoint, monospaced: true)
            if !model.realtime.snapshot.recentLines.isEmpty {
                KeyValueRowView(key: "Recent Frames", value: model.realtime.snapshot.recentLines.joined(separator: " | "))
            }
        }
    }

    private var navigationSection: some View {
        SectionCardView(
            title: "HQ-Safe Authenticated Surfaces",
            subtitle: "Only runtime-confirmed HQ slices are open in Phase 2B."
        ) {
            Button("Open Diagnostics") {
                model.openDiagnostics()
            }
            .buttonStyle(.borderedProminent)
            .tint(SentrixTheme.Palette.accent)

            Button("Open Apple Weekly") {
                model.openAppleWeekly()
            }
            .buttonStyle(.bordered)

            Button("Open Support Submission Handoff") {
                model.openSupportSubmissions()
            }
            .buttonStyle(.bordered)

            Button("Open Push Diagnostics") {
                model.openPushDiagnostics()
            }
            .buttonStyle(.bordered)

            Button("Open Blocked Modules") {
                model.openBlockedModules()
            }
            .buttonStyle(.bordered)
        }
    }

    private var blockedFootnote: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(
                kind: .warning,
                title: "Still Unresolved",
                message: "Field role parity beyond hidden/blocked HQ navigation, disabled/HR-linked auth behavior, realtime ordering, Apple Weekly mutation/write, Google Sheets write, and native APNs registration remain blocked outside Phase 2B."
            )
        )
    }

    private func realtimeStatusLabel(_ status: RealtimeConnectionStatus) -> String {
        switch status {
        case .idle:
            return "idle"
        case .connecting:
            return "connecting"
        case .connected:
            return "connected"
        case .disconnected:
            return "disconnected"
        case .failed(let message):
            return "failed: \(message)"
        }
    }
}
