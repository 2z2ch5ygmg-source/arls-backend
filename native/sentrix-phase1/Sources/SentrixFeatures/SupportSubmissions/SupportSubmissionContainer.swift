import Foundation
import Combine
import SentrixCore

@MainActor
public final class SupportSubmissionContainer: ObservableObject {
    public enum State: Equatable {
        case idle
        case loading
        case loaded(SupportSubmissionWorkspace)
        case failed(SentrixError)
    }

    @Published public private(set) var state: State = .idle

    private let repository: any SupportSubmissionRepository
    private let environment: AppEnvironment
    private let now: @Sendable () -> Date

    public init(
        repository: any SupportSubmissionRepository,
        environment: AppEnvironment,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.repository = repository
        self.environment = environment
        self.now = now
    }

    public func load(
        session: AuthSessionDescriptor,
        bootstrap: AuthenticatedBootstrapSnapshot
    ) async {
        state = .loading
        do {
            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.dateFormat = "yyyy-MM"
            let context = SupportSubmissionContext(
                month: formatter.string(from: now()),
                siteCode: bootstrap.user.siteID.isEmpty ? session.user.siteID : bootstrap.user.siteID
            )
            let workspace = try await repository.loadWorkspace(
                session: session,
                environment: environment,
                context: context
            )
            state = .loaded(workspace)
        } catch let error as SentrixError {
            state = .failed(error)
        } catch {
            state = .failed(.transport(message: "Support submission workspace failed to load."))
        }
    }

    public func reset() {
        state = .idle
    }
}
