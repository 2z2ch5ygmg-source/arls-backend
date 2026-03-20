import XCTest
@testable import SentrixAPI
import SentrixCore

final class Phase1BlockedAdaptersTests: XCTestCase {
    private let environment = AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)
    private let session = AuthSessionDescriptor(
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

    func testAuthAdapterFailsLoudly() async {
        let adapter = Phase1StubAuthAdapter()

        await assertRuntimeBlocked(area: .productionAuthMode) {
            _ = try await adapter.signIn(
                using: LoginDraft(tenantCode: "srs", username: "mark", password: "pw"),
                environment: environment
            )
        }
    }

    func testAuthenticatedBootstrapAdapterFailsLoudly() async {
        let adapter = Phase1StubAuthenticatedBootstrapAdapter()

        await assertRuntimeBlocked(area: .authenticatedBootstrap) {
            _ = try await adapter.loadAuthenticatedBootstrap(session: session, environment: environment)
        }
    }

    func testRealtimeAdapterFailsLoudly() async {
        let adapter = Phase1StubRealtimeAdapter()

        do {
            let stream = adapter.makeRealtimeStream(session: session, environment: environment)
            for try await _ in stream {
                XCTFail("Realtime stub should not emit successful events.")
            }
            XCTFail("Expected runtimeBlocked for realtime stream")
        } catch let error as SentrixError {
            guard case .runtimeBlocked(let area, let message) = error else {
                return XCTFail("Unexpected SentrixError: \(error)")
            }
            XCTAssertEqual(area, .realtimeTransport)
            XCTAssertEqual(message, RuntimeBlockedArea.realtimeTransport.phase1FailureMessage)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testPushAdapterFailsLoudly() async {
        let adapter = Phase1StubPushAdapter()

        await assertRuntimeBlocked(area: .pushRegistration) {
            _ = try await adapter.preparePushRegistration(session: session, environment: environment)
        }
    }

    func testAppleWeeklyAdapterFailsLoudly() async {
        let adapter = Phase1StubAppleWeeklyAdapter()

        await assertRuntimeBlocked(area: .appleWeekly) {
            _ = try await adapter.prepareAppleWeeklyWorkspace(environment: environment)
        }
    }

    func testARLSBridgeAdapterFailsLoudly() async {
        let adapter = Phase1StubARLSBridgeAdapter()

        await assertRuntimeBlocked(area: .arlsBridge) {
            _ = try await adapter.prepareBridgeWorkspace(environment: environment)
        }
    }

    private func assertRuntimeBlocked<T>(
        area expectedArea: RuntimeBlockedArea,
        operation: () async throws -> T
    ) async {
        do {
            _ = try await operation()
            XCTFail("Expected runtimeBlocked for \(expectedArea.rawValue)")
        } catch let error as SentrixError {
            guard case .runtimeBlocked(let area, let message) = error else {
                return XCTFail("Unexpected SentrixError: \(error)")
            }

            XCTAssertEqual(area, expectedArea)
            XCTAssertEqual(message, expectedArea.phase1FailureMessage)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
