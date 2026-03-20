import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct DiagnosticsView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        ScrollView {
            switch model.bootstrap.state {
            case .loaded(let snapshot):
                VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                    RuntimeNoticeGroupView(notices: model.runtimeNotices)

                    SectionCardView(
                        title: "Runtime Scope",
                        subtitle: "This screen separates public runtime, HQ-confirmed authenticated runtime, field-confirmed blocked or hidden behavior, and still-blocked universal behavior."
                    ) {
                        KeyValueRowView(key: "Confirmed Public Endpoints", value: "/health, /api/app-config, /api/build-info", monospaced: true)
                        KeyValueRowView(key: "Auth Boundary", value: "/api/bootstrap-config requires authenticated runtime capture", monospaced: true)
                        KeyValueRowView(key: "Service Worker Assumption", value: "Do not trust Azure-host PWA/runtime caching behavior in native.")
                    }

                    SectionCardView(
                        title: "Authenticated Scope",
                        subtitle: "HQ-confirmed and field-confirmed authenticated shell behavior are separated below. Unresolved role/runtime areas remain blocked."
                    ) {
                        KeyValueRowView(key: "Stored Session", value: sessionStatusLabel)
                        if let session = model.session.restoredSessionDescriptor {
                            KeyValueRowView(key: "Stored User", value: session.userLabel)
                            KeyValueRowView(key: "Persistence Source", value: session.persistenceSource.rawValue)
                            KeyValueRowView(key: "Storage Keys", value: session.storageKeys.joined(separator: ", "), monospaced: true)
                        }
                        KeyValueRowView(key: "Shell Scope", value: shellScopeLabel)
                        KeyValueRowView(key: "Runtime Access Scope", value: model.authenticatedShellScope?.runtimeAccessLabel ?? "none")
                        if model.hasHQAuthenticatedShell {
                            KeyValueRowView(key: "Authenticated Bootstrap", value: authenticatedBootstrapLabel)
                            KeyValueRowView(key: "Realtime Transport", value: model.realtime.snapshot.transport.rawValue.uppercased())
                            KeyValueRowView(key: "Realtime Status", value: realtimeStatusLabel(model.realtime.snapshot.status))
                            KeyValueRowView(key: "Realtime Endpoint", value: model.realtime.snapshot.endpoint.isEmpty ? "-" : model.realtime.snapshot.endpoint, monospaced: true)
                        } else if model.hasFieldObservedAuthenticatedShell {
                            KeyValueRowView(key: "Authenticated Bootstrap", value: "not_loaded: field bootstrap remains unresolved")
                            KeyValueRowView(key: "Realtime Transport", value: "not_started")
                            KeyValueRowView(key: "Realtime Status", value: "blocked outside HQ-safe shell")
                            KeyValueRowView(key: "Realtime Endpoint", value: "-")
                            KeyValueRowView(key: "Apple Weekly Navigation", value: "hidden")
                            KeyValueRowView(key: "Apple Weekly Direct Route", value: "blocked / redirected")
                        } else {
                            KeyValueRowView(key: "Authenticated Bootstrap", value: authenticatedBootstrapLabel)
                            KeyValueRowView(key: "Realtime Transport", value: model.realtime.snapshot.transport.rawValue.uppercased())
                            KeyValueRowView(key: "Realtime Status", value: realtimeStatusLabel(model.realtime.snapshot.status))
                            KeyValueRowView(key: "Realtime Endpoint", value: model.realtime.snapshot.endpoint.isEmpty ? "-" : model.realtime.snapshot.endpoint, monospaced: true)
                        }
                    }

                    SectionCardView(
                        title: "Still Runtime-Blocked",
                        subtitle: "These values remain unavailable until authenticated production evidence closes them without relying on HQ-only inference."
                    ) {
                        ForEach(RuntimeBlockedArea.allCases) { area in
                            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                                KeyValueRowView(key: area.title, value: area.blockerTag, monospaced: true)
                                Text(area.summary)
                                    .font(SentrixTheme.Typography.caption)
                                    .foregroundStyle(SentrixTheme.Palette.muted)
                                if area.id != RuntimeBlockedArea.allCases.last?.id {
                                    Divider()
                                }
                            }
                        }
                    }

                    SectionCardView(title: "Environment", subtitle: "Safe-to-freeze public runtime model") {
                        KeyValueRowView(key: "Environment", value: snapshot.environment.name)
                        KeyValueRowView(key: "Base URL", value: snapshot.environment.baseURL.absoluteString, monospaced: true)
                        KeyValueRowView(key: "Loaded At", value: snapshot.loadedAt.formatted(date: .numeric, time: .standard))
                        KeyValueRowView(key: "Server Time", value: snapshot.health.serverTime, monospaced: true)
                    }

                    SectionCardView(title: "Health", subtitle: "/health") {
                        KeyValueRowView(key: "Status", value: snapshot.health.status)
                        KeyValueRowView(key: "OK", value: snapshot.health.ok ? "true" : "false")
                        KeyValueRowView(key: "Read-Only", value: snapshot.health.readOnly ? "true" : "false")
                        KeyValueRowView(key: "Read-Only Reason", value: snapshot.health.readOnlyReason)
                        KeyValueRowView(key: "Timer Enabled", value: snapshot.health.featureTimerEnabled ? "true" : "false")
                        KeyValueRowView(key: "Legacy Admin Menu", value: snapshot.health.featureLegacyAdminMenuEnabled ? "true" : "false")
                        KeyValueRowView(key: "Data Dictionary", value: snapshot.health.featureDataDictionaryEnabled ? "true" : "false")
                    }

                    SectionCardView(title: "Public App Config", subtitle: "/api/app-config") {
                        KeyValueRowView(key: "Tenant", value: snapshot.appConfig.tenantID)
                        KeyValueRowView(key: "Site", value: snapshot.appConfig.siteID)
                        KeyValueRowView(key: "Read-Only", value: snapshot.appConfig.readOnly ? "true" : "false")
                        KeyValueRowView(key: "Master Data Read-Only", value: snapshot.appConfig.masterDataReadOnly ? "true" : "false")
                        KeyValueRowView(key: "Master Data Message", value: snapshot.appConfig.masterDataReadOnlyMessage)
                        KeyValueRowView(key: "Bootstrap Endpoint", value: snapshot.appConfig.endpoints.bootstrapConfig, monospaced: true)
                        KeyValueRowView(key: "Startup Errors", value: snapshot.appConfig.startupErrors.joined(separator: " | "))
                    }

                    SectionCardView(title: "Build Provenance", subtitle: "/api/build-info multi-field model preserved exactly; values below are public-runtime only") {
                        KeyValueRowView(key: "Backend Commit", value: snapshot.buildInfo.backendCommit, monospaced: true)
                        KeyValueRowView(key: "Backend Dirty", value: snapshot.buildInfo.backendDirty ? "true" : "false")
                        KeyValueRowView(key: "Deploy Mode", value: snapshot.buildInfo.deployMode)
                        KeyValueRowView(key: "Image Tag", value: snapshot.buildInfo.imageTag, monospaced: true)
                        KeyValueRowView(key: "Frontend Build ID", value: snapshot.buildInfo.frontendBuildID, monospaced: true)
                        KeyValueRowView(key: "Frontend UI Build ID", value: snapshot.buildInfo.frontendUIBuildID, monospaced: true)
                        KeyValueRowView(key: "Frontend Source", value: snapshot.buildInfo.frontendSource, monospaced: true)
                        KeyValueRowView(key: "Frontend Source Image", value: snapshot.buildInfo.frontendSourceImage, monospaced: true)
                        KeyValueRowView(key: "Deployed At UTC", value: snapshot.buildInfo.deployedAtUTC, monospaced: true)
                        KeyValueRowView(key: "Static Dir", value: snapshot.buildInfo.staticDirectory, monospaced: true)
                        KeyValueRowView(key: "Data Dir", value: snapshot.buildInfo.dataDirectory, monospaced: true)
                        KeyValueRowView(key: "DB Path", value: snapshot.buildInfo.databasePath, monospaced: true)
                    }
                }
                .padding(SentrixTheme.Spacing.md)
            default:
                EmptyStateView(
                    title: "Bootstrap Not Loaded",
                    message: "Diagnostics depend on the public bootstrap snapshot."
                )
                .padding(SentrixTheme.Spacing.md)
            }
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Diagnostics")
    }

    private var sessionStatusLabel: String {
        switch model.session.status {
        case .signedOut:
            return "signed_out"
        case .restoring:
            return "restoring"
        case .verifyingRestored:
            return "verifying_restored"
        case .signingIn:
            return "signing_in"
        case .unresolvedRestored(_, let message):
            return "unresolved_restored: \(message)"
        case .blocked(_, let message):
            return "blocked: \(message)"
        case .unauthorized(let message):
            return "unauthorized: \(message)"
        case .expired(let message):
            return "expired: \(message)"
        case .authenticated:
            return "authenticated"
        }
    }

    private var authenticatedBootstrapLabel: String {
        switch model.authenticatedShell.state {
        case .idle:
            return "idle"
        case .loading:
            return "loading"
        case .loaded(let snapshot):
            return "loaded: \(snapshot.user.fullName) / \(snapshot.user.role)"
        case .failed(let error):
            return "failed: \(error.errorDescription ?? "unknown")"
        }
    }

    private var shellScopeLabel: String {
        model.authenticatedShellScope?.diagnosticsLabel ?? "none"
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
