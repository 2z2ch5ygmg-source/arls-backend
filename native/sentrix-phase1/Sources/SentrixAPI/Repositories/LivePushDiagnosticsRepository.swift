import Foundation
import SentrixCore

public struct LivePushDiagnosticsRepository: PushDiagnosticsRepository {
    private let client: JSONAPIClient

    public init(client: JSONAPIClient) {
        self.client = client
    }

    public func runPushTest(
        session: AuthSessionDescriptor,
        environment: AppEnvironment
    ) async throws -> PushTestResult {
        let dto: PushTestResponseDTO = try await client.send(
            Endpoint(
                path: "/api/push/test",
                method: .post,
                headers: ["Authorization": "Bearer \(session.accessToken)"],
                body: try JSONSerialization.data(withJSONObject: [:], options: [.sortedKeys])
            ),
            environment: environment
        )
        return PushDiagnosticsMapper.map(dto)
    }
}
