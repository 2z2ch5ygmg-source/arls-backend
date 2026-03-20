import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct Phase1RootView: View {
    @StateObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        _model = StateObject(wrappedValue: model)
    }

    public var body: some View {
        NavigationStack(path: $model.path) {
            rootContent
                .navigationDestination(for: Phase1AppModel.Route.self) { route in
                    switch route {
                    case .diagnostics:
                        DiagnosticsView(model: model)
                    case .blockedModules:
                        BlockedModulesView(model: model)
                    case .appleWeekly:
                        if model.canAccessAuthenticatedRoute(.appleWeekly) {
                            AppleWeeklyWorkspaceView(model: model)
                        } else {
                            AuthenticatedRouteBlockedView(model: model, target: .appleWeekly)
                        }
                    case .supportSubmissions:
                        if model.canAccessAuthenticatedRoute(.supportSubmissions) {
                            SupportSubmissionWorkspaceView(model: model)
                        } else {
                            AuthenticatedRouteBlockedView(model: model, target: .supportSubmissions)
                        }
                    case .pushDiagnostics:
                        if model.canAccessAuthenticatedRoute(.pushDiagnostics) {
                            PushDiagnosticsView(model: model)
                        } else {
                            AuthenticatedRouteBlockedView(model: model, target: .pushDiagnostics)
                        }
                    case .roleBlocked(let target):
                        AuthenticatedRouteBlockedView(model: model, target: target)
                    }
                }
                .task {
                    if case .idle = model.bootstrap.state {
                        await model.start()
                    }
                }
        }
    }

    @ViewBuilder
    private var rootContent: some View {
        switch model.bootstrap.state {
        case .idle, .loading:
            LoadingStateView(message: "Fetching /health, /api/app-config, and /api/build-info.")
        case .failed(let error):
            SystemSurfaceView(
                surface: error.systemSurface,
                action: error.recommendsRetry ? {
                    Task { await model.bootstrap.retry() }
                } : nil
            )
        case .loaded(let snapshot):
            if let scope = model.authenticatedShellScope {
                switch scope {
                case .hqSafe:
                    AuthenticatedHomeView(model: model, publicSnapshot: snapshot)
                case .fieldObserved(let role):
                    FieldAuthenticatedHomeView(model: model, publicSnapshot: snapshot, role: role)
                }
            } else if model.hasAuthenticatedSession {
                SystemSurfaceView(
                    surface: SystemSurfaceModel(
                        kind: .blocked,
                        title: "Unresolved Authenticated Shell",
                        message: "An authenticated session exists, but no runtime-confirmed HQ or field-observed shell classification is available."
                    ),
                    action: {
                        model.logout()
                    }
                )
            } else if model.isRestoringAuthenticatedShell {
                LoadingStateView(
                    title: "Restoring Session",
                    message: "Checking for a stored authenticated session and verifying whether HQ-safe or field-observed shell access is allowed."
                )
            } else {
                FoundationHomeView(model: model, snapshot: snapshot)
            }
        }
    }
}
