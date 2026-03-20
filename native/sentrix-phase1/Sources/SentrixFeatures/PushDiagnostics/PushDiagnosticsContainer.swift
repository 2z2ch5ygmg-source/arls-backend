import Foundation
import Combine
import SentrixCore

@MainActor
public final class PushDiagnosticsContainer: ObservableObject {
    public enum State: Equatable {
        case idle
        case running
        case loaded(PushTestResult)
        case failed(SentrixError)
    }

    @Published public private(set) var state: State = .idle

    private let repository: any PushDiagnosticsRepository
    private let environment: AppEnvironment

    public init(
        repository: any PushDiagnosticsRepository,
        environment: AppEnvironment
    ) {
        self.repository = repository
        self.environment = environment
    }

    public func run(session: AuthSessionDescriptor) async {
        state = .running
        do {
            let result = try await repository.runPushTest(session: session, environment: environment)
            state = .loaded(result)
        } catch let error as SentrixError {
            state = .failed(error)
        } catch {
            state = .failed(.transport(message: "Push diagnostics request failed."))
        }
    }

    public func reset() {
        state = .idle
    }
}
