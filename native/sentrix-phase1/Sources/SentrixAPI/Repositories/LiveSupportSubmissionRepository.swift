import Foundation
import SentrixCore

public struct LiveSupportSubmissionRepository: SupportSubmissionRepository {
    private let client: JSONAPIClient

    public init(client: JSONAPIClient) {
        self.client = client
    }

    public func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: SupportSubmissionContext
    ) async throws -> SupportSubmissionWorkspace {
        let dto: SupportSubmissionWorkspaceDTO = try await client.send(
            Endpoint(
                path: "/api/ops/support-submissions/workspace?month=\(context.month)&site_code=\(context.siteCode)",
                headers: ["Authorization": "Bearer \(session.accessToken)"]
            ),
            environment: environment
        )
        return SupportSubmissionMapper.map(dto)
    }
}
