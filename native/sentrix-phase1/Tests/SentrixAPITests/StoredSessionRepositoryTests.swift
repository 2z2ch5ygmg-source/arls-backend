import XCTest
@testable import SentrixAPI
import SentrixCore

final class StoredSessionRepositoryTests: XCTestCase {
    func testPersistAndLoadStoredSessionRoundTripsSocKeys() async throws {
        let suiteName = "sentrix.phase2a.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        let fixedDate = Date(timeIntervalSince1970: 123)
        let repository = UserDefaultsStoredSessionRepository(defaults: defaults, now: { fixedDate })
        let session = sampleSession()

        try await repository.persistStoredSession(session)
        let loaded = try await repository.loadStoredSession()

        XCTAssertEqual(loaded?.accessToken, "token")
        XCTAssertEqual(loaded?.user.fullName, "서성원")
        XCTAssertEqual(loaded?.persistenceSource, .storedSocKeys)
        XCTAssertEqual(loaded?.storageKeys, ["soc_token", "soc_user"])
        XCTAssertEqual(loaded?.issuedAt, fixedDate)
    }

    func testLoadStoredSessionFailsLoudlyOnInvalidSocUserPayload() async {
        let suiteName = "sentrix.phase2a.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        defaults.set("token", forKey: "soc_token")
        defaults.set("{not-json", forKey: "soc_user")
        let repository = UserDefaultsStoredSessionRepository(defaults: defaults)

        do {
            _ = try await repository.loadStoredSession()
            XCTFail("Expected decode failure")
        } catch let error as SentrixError {
            XCTAssertEqual(error, .decoding(message: "Stored soc_user payload could not be decoded."))
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
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
