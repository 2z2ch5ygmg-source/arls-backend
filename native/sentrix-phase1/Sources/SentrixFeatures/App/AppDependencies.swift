import Foundation
import SentrixCore

public struct AppDependencies: Sendable {
    public let environment: AppEnvironment
    public let publicBootstrapRepository: any PublicBootstrapRepository
    public let storedSessionRepository: any StoredSessionRepository
    public let authenticatedBootstrapRepository: any AuthenticatedBootstrapRepository
    public let appleWeeklyReadRepository: any AppleWeeklyReadRepository
    public let supportSubmissionRepository: any SupportSubmissionRepository
    public let pushDiagnosticsRepository: any PushDiagnosticsRepository
    public let authAdapter: any AuthAdapter
    public let authenticatedBootstrapAdapter: any AuthenticatedBootstrapAdapter
    public let realtimeAdapter: any RealtimeAdapter
    public let pushAdapter: any PushAdapter
    public let appleWeeklyAdapter: any AppleWeeklyAdapter
    public let arlsBridgeAdapter: any ARLSBridgeAdapter

    public init(
        environment: AppEnvironment,
        publicBootstrapRepository: any PublicBootstrapRepository,
        storedSessionRepository: any StoredSessionRepository,
        authenticatedBootstrapRepository: any AuthenticatedBootstrapRepository,
        appleWeeklyReadRepository: any AppleWeeklyReadRepository,
        supportSubmissionRepository: any SupportSubmissionRepository,
        pushDiagnosticsRepository: any PushDiagnosticsRepository,
        authAdapter: any AuthAdapter,
        authenticatedBootstrapAdapter: any AuthenticatedBootstrapAdapter,
        realtimeAdapter: any RealtimeAdapter,
        pushAdapter: any PushAdapter,
        appleWeeklyAdapter: any AppleWeeklyAdapter,
        arlsBridgeAdapter: any ARLSBridgeAdapter
    ) {
        self.environment = environment
        self.publicBootstrapRepository = publicBootstrapRepository
        self.storedSessionRepository = storedSessionRepository
        self.authenticatedBootstrapRepository = authenticatedBootstrapRepository
        self.appleWeeklyReadRepository = appleWeeklyReadRepository
        self.supportSubmissionRepository = supportSubmissionRepository
        self.pushDiagnosticsRepository = pushDiagnosticsRepository
        self.authAdapter = authAdapter
        self.authenticatedBootstrapAdapter = authenticatedBootstrapAdapter
        self.realtimeAdapter = realtimeAdapter
        self.pushAdapter = pushAdapter
        self.appleWeeklyAdapter = appleWeeklyAdapter
        self.arlsBridgeAdapter = arlsBridgeAdapter
    }
}
