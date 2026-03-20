import XCTest
@testable import SentrixAPI
import SentrixCore

private final class URLProtocolStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: SentrixError.transport(message: "Missing URLProtocol handler"))
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class HQSSERealtimeAdapterTests: XCTestCase {
    func testAdapterUsesSSEEndpointAndYieldsOpenedLineClosed() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLProtocolStub.self]
        let urlSession = URLSession(configuration: config)
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
            XCTAssertEqual(request.url?.path, "/api/notifications/stream")
            XCTAssertEqual(URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems?.first?.name, "token")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream; charset=utf-8"]
            )!
            let body = "data: ping\n\n"
            return (response, Data(body.utf8))
        }

        let adapter = HQSSERealtimeAdapter(session: urlSession)
        let stream = adapter.makeRealtimeStream(
            session: sampleSession(),
            environment: AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)
        )

        var events: [RealtimeStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }

        XCTAssertEqual(events.count, 3)
        XCTAssertEqual(events[0], .opened(endpoint: "https://example.com/api/notifications/stream?token=token", contentType: "text/event-stream; charset=utf-8"))
        XCTAssertEqual(events[1], .line("data: ping"))
        XCTAssertEqual(events[2], .closed)
    }

    private func sampleSession() -> AuthSessionDescriptor {
        AuthSessionDescriptor(
            accessToken: "token",
            user: StoredSessionUserSummary(
                id: 21,
                username: "01059387659",
                loginID: "01059387659",
                fullName: "서성원",
                role: "HQ_ADMIN",
                group: "HQ",
                siteID: "R692",
                siteCode: "R692",
                siteName: "Apple_명동",
                tenantID: "srs_korea",
                location: "R692",
                status: "active",
                linkedEmployeeID: 201,
                employeeID: 201
            ),
            issuedAt: Date(timeIntervalSince1970: 1),
            persistenceSource: .storedSocKeys,
            storageKeys: ["soc_token", "soc_user"]
        )
    }
}
