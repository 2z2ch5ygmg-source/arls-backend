import Foundation
import Combine
import SentrixCore

@MainActor
public final class Phase1AppModel: ObservableObject {
    public enum Route: Hashable {
        case diagnostics
        case blockedModules
        case appleWeekly
        case supportSubmissions
        case pushDiagnostics
        case roleBlocked(AuthenticatedNavigationTarget)
    }

    @Published public var path: [Route] = []

    public var bootstrap: PublicBootstrapContainer
    public var session: SessionContainer
    public var authenticatedShell: AuthenticatedShellContainer
    public var realtime: RealtimeContainer
    public var appleWeekly: AppleWeeklyContainer
    public var supportSubmission: SupportSubmissionContainer
    public var pushDiagnostics: PushDiagnosticsContainer
    public let dependencies: AppDependencies

    public init(dependencies: AppDependencies) {
        self.dependencies = dependencies
        self.bootstrap = PublicBootstrapContainer(
            useCase: LoadPublicBootstrapUseCase(repository: dependencies.publicBootstrapRepository),
            environment: dependencies.environment
        )
        self.session = SessionContainer(
            environment: dependencies.environment,
            storedSessionRepository: dependencies.storedSessionRepository,
            authAdapter: dependencies.authAdapter
        )
        self.authenticatedShell = AuthenticatedShellContainer(
            repository: dependencies.authenticatedBootstrapRepository,
            environment: dependencies.environment
        )
        self.realtime = RealtimeContainer(adapter: dependencies.realtimeAdapter)
        self.appleWeekly = AppleWeeklyContainer(
            repository: dependencies.appleWeeklyReadRepository,
            environment: dependencies.environment
        )
        self.supportSubmission = SupportSubmissionContainer(
            repository: dependencies.supportSubmissionRepository,
            environment: dependencies.environment
        )
        self.pushDiagnostics = PushDiagnosticsContainer(
            repository: dependencies.pushDiagnosticsRepository,
            environment: dependencies.environment
        )
    }

    public func start() async {
        await bootstrap.load()
        guard bootstrapSnapshot != nil else { return }
        await session.restoreStoredSession()
        guard session.provisionalSession != nil else { return }
        await verifyRestoredSessionForAuthenticatedShell()
    }

    public func openDiagnostics() {
        path.append(.diagnostics)
    }

    public func openBlockedModules() {
        path.append(.blockedModules)
    }

    public func openAppleWeekly() {
        if canAccessAuthenticatedRoute(.appleWeekly) {
            path.append(.appleWeekly)
        } else {
            path.append(.roleBlocked(.appleWeekly))
        }
    }

    public func openSupportSubmissions() {
        if canAccessAuthenticatedRoute(.supportSubmissions) {
            path.append(.supportSubmissions)
        } else {
            path.append(.roleBlocked(.supportSubmissions))
        }
    }

    public func openPushDiagnostics() {
        if canAccessAuthenticatedRoute(.pushDiagnostics) {
            path.append(.pushDiagnostics)
        } else {
            path.append(.roleBlocked(.pushDiagnostics))
        }
    }

    public func returnToAuthenticatedHome() {
        path.removeAll()
    }

    public var bootstrapSnapshot: PublicBootstrapSnapshot? {
        if case .loaded(let snapshot) = bootstrap.state {
            return snapshot
        }
        return nil
    }

    public var runtimeNotices: [RuntimeNotice] {
        bootstrapSnapshot?.notices ?? []
    }

    public var hasAuthenticatedSession: Bool {
        session.currentSession != nil
    }

    public var authenticatedShellScope: AuthenticatedShellScope? {
        guard let session = session.currentSession else { return nil }
        if case .loaded(let snapshot) = authenticatedShell.state,
           let scope = snapshot.user.authenticatedShellScope {
            return scope
        }
        return session.user.authenticatedShellScope
    }

    public var hasHQAuthenticatedShell: Bool {
        authenticatedShellScope?.isHQSafe == true
    }

    public var hasFieldObservedAuthenticatedShell: Bool {
        authenticatedShellScope?.isFieldObserved == true
    }

    public func canAccessAuthenticatedRoute(_ target: AuthenticatedNavigationTarget) -> Bool {
        switch target {
        case .appleWeekly, .supportSubmissions, .pushDiagnostics:
            return hasHQAuthenticatedShell
        }
    }

    public var isRestoringAuthenticatedShell: Bool {
        if case .restoring = session.status {
            return true
        }
        if case .verifyingRestored = session.status {
            return true
        }
        if case .loading = authenticatedShell.state {
            return true
        }
        return false
    }

    public func retryAuthenticatedShell() async {
        if session.provisionalSession != nil {
            await verifyRestoredSessionForAuthenticatedShell()
            return
        }

        guard let session = session.currentSession else { return }
        guard hasHQAuthenticatedShell || session.user.authenticatedShellScope?.isHQSafe == true else {
            return
        }
        let didLoad = await authenticatedShell.load(session: session)
        if didLoad {
            await realtime.connect(session: session, environment: dependencies.environment)
        }
    }

    public func logout() {
        realtime.disconnect()
        authenticatedShell.reset()
        appleWeekly.reset()
        supportSubmission.reset()
        pushDiagnostics.reset()
        session.logout()
    }

    public func loadAppleWeekly() async {
        guard
            hasHQAuthenticatedShell,
            let session = session.currentSession,
            case .loaded(let snapshot) = authenticatedShell.state
        else { return }
        await appleWeekly.load(session: session, bootstrap: snapshot)
    }

    public func loadSupportSubmissions() async {
        guard
            hasHQAuthenticatedShell,
            let session = session.currentSession,
            case .loaded(let snapshot) = authenticatedShell.state
        else { return }
        await supportSubmission.load(session: session, bootstrap: snapshot)
    }

    public func runPushDiagnostics() async {
        guard hasHQAuthenticatedShell else { return }
        guard let session = session.currentSession else { return }
        await pushDiagnostics.run(session: session)
    }

    private func verifyRestoredSessionForAuthenticatedShell() async {
        guard let session = session.provisionalSession else { return }
        let user = session.user

        guard user.normalizedStatus.caseInsensitiveCompare("active") == .orderedSame else {
            authenticatedShell.reset()
            realtime.disconnect()
            self.session.markRestoredSessionUnresolved(
                message: "Restored session account status '\(user.normalizedStatus.isEmpty ? "<empty>" : user.normalizedStatus)' is unresolved for Phase 2B. Only active runtime-confirmed roles may continue."
            )
            return
        }

        guard let scope = user.authenticatedShellScope else {
            authenticatedShell.reset()
            realtime.disconnect()
            self.session.markRestoredSessionUnresolved(
                message: "Restored session role '\(user.normalizedRole.isEmpty ? "<empty>" : user.normalizedRole)' is unresolved for Phase 2B. Only runtime-confirmed HQ_ADMIN, SUPERVISOR, and OFFICER roles may continue."
            )
            return
        }

        switch scope {
        case .hqSafe:
            let didLoad = await authenticatedShell.load(session: session)
            guard didLoad else {
                realtime.disconnect()
                let message: String
                if case .failed(let error) = authenticatedShell.state {
                    message = error.errorDescription ?? "Restored session could not be proven HQ-safe for Phase 2B."
                } else {
                    message = "Restored session could not be proven HQ-safe for Phase 2B."
                }
                self.session.markRestoredSessionUnresolved(message: message)
                return
            }

            self.session.confirmRestoredSessionEligibility()
            await realtime.connect(session: session, environment: dependencies.environment)

        case .fieldObserved:
            authenticatedShell.reset()
            realtime.disconnect()
            appleWeekly.reset()
            supportSubmission.reset()
            pushDiagnostics.reset()
            self.session.confirmRestoredSessionEligibility()
        }
    }
}
