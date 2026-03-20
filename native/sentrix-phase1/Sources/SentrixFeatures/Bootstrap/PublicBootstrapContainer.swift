import Foundation
import Combine
import SentrixCore

@MainActor
public final class PublicBootstrapContainer: ObservableObject {
    public enum State: Equatable {
        case idle
        case loading
        case loaded(PublicBootstrapSnapshot)
        case failed(SentrixError)
    }

    @Published public private(set) var state: State = .idle

    private let useCase: LoadPublicBootstrapUseCase
    private let environment: AppEnvironment

    public init(useCase: LoadPublicBootstrapUseCase, environment: AppEnvironment) {
        self.useCase = useCase
        self.environment = environment
    }

    public func load() async {
        state = .loading
        do {
            let snapshot = try await useCase.execute(environment: environment)
            state = .loaded(snapshot)
        } catch let error as SentrixError {
            state = .failed(error)
        } catch {
            state = .failed(.transport(message: "Unexpected bootstrap failure."))
        }
    }

    public func retry() async {
        await load()
    }
}
