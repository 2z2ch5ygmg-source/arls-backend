import XCTest
@testable import SentrixAPI
import SentrixCore

private struct HTTPTransportStub: HTTPTransport {
    let responses: [String: (status: Int, body: String)]

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let path = request.url?.path ?? ""
        guard let response = responses[path], let url = request.url else {
            throw SentrixError.transport(message: "Missing stub for \(path)")
        }

        let http = HTTPURLResponse(
            url: url,
            statusCode: response.status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!

        return (Data(response.body.utf8), http)
    }
}

final class LivePublicBootstrapRepositoryTests: XCTestCase {
    func testLoadPublicBootstrapHandlesPartialPayloads() async throws {
        let fixedDate = Date(timeIntervalSince1970: 123)
        let transport = HTTPTransportStub(
            responses: [
                "/health": (
                    200,
                    """
                    {
                      "ok": true,
                      "status": "ok"
                    }
                    """
                ),
                "/api/app-config": (
                    200,
                    """
                    {
                      "tenant_id": "srs_korea",
                      "important_incident_feature_enabled": true,
                      "incident_participant_feature_enabled": true,
                      "master_data_read_only": true
                    }
                    """
                ),
                "/api/build-info": (
                    200,
                    """
                    {
                      "backend_commit": "457003b",
                      "frontend_build_id": "frontend-build"
                    }
                    """
                ),
            ]
        )

        let repository = LivePublicBootstrapRepository(
            client: JSONAPIClient(transport: transport),
            now: { fixedDate }
        )

        let snapshot = try await repository.loadPublicBootstrap(
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)
        )

        XCTAssertEqual(snapshot.health.status, "ok")
        XCTAssertFalse(snapshot.health.readOnly)
        XCTAssertEqual(snapshot.appConfig.tenantID, "srs_korea")
        XCTAssertTrue(snapshot.appConfig.masterDataReadOnly)
        XCTAssertEqual(snapshot.appConfig.endpoints.bootstrapConfig, "")
        XCTAssertEqual(snapshot.buildInfo.backendCommit, "457003b")
        XCTAssertEqual(snapshot.buildInfo.frontendBuildID, "frontend-build")
        XCTAssertEqual(snapshot.buildInfo.frontendUIBuildID, "")
        XCTAssertEqual(snapshot.loadedAt, fixedDate)
    }
}
