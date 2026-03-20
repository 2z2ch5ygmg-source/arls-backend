import Foundation
import Combine
import SentrixCore

@MainActor
public final class AppleWeeklyContainer: ObservableObject {
    public enum State: Equatable {
        case idle
        case loading
        case loaded(AppleWeeklyWorkspace)
        case failed(SentrixError)
    }

    @Published public private(set) var state: State = .idle

    private let repository: any AppleWeeklyReadRepository
    private let environment: AppEnvironment
    private let now: @Sendable () -> Date

    public init(
        repository: any AppleWeeklyReadRepository,
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
            let context = makeContext(session: session, bootstrap: bootstrap)
            let workspace = try await repository.loadWorkspace(
                session: session,
                environment: environment,
                context: context
            )
            state = .loaded(workspace)
        } catch let error as SentrixError {
            state = .failed(error)
        } catch {
            state = .failed(.transport(message: "Apple Weekly workspace failed to load."))
        }
    }

    public func reset() {
        state = .idle
    }

    private func makeContext(
        session: AuthSessionDescriptor,
        bootstrap: AuthenticatedBootstrapSnapshot
    ) -> AppleWeeklyContext {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"

        let calendar = Calendar(identifier: .gregorian)
        let reportYear = String(calendar.component(.year, from: now()))
        let siteCode = bootstrap.user.siteID.isEmpty ? session.user.siteID : bootstrap.user.siteID
        return AppleWeeklyContext(
            siteCode: siteCode,
            reportYear: reportYear,
            referenceDate: formatter.string(from: now())
        )
    }
}
