import XCTest
@testable import SentrixCore

final class SystemSurfaceModelsTests: XCTestCase {
    func testTransportErrorMapsToOfflineSurface() {
        let surface = SentrixError.transport(message: "network down").systemSurface

        XCTAssertEqual(surface.kind, .offline)
        XCTAssertEqual(surface.title, "Offline Placeholder")
        XCTAssertEqual(surface.message, "network down")
        XCTAssertEqual(surface.actionKind, .retry)
    }

    func testRuntimeBlockedSessionPreservesAreaMarker() {
        let surface = SessionStatus.blocked(
            area: .productionAuthMode,
            message: "Auth blocked"
        ).systemSurface

        XCTAssertEqual(surface?.kind, .blocked)
        XCTAssertEqual(surface?.title, "Production Auth Mode")
        XCTAssertEqual(surface?.footnote, RuntimeBlockedArea.productionAuthMode.blockerTag)
    }

    func testAuthenticatedSessionDoesNotEmitSharedSurface() {
        let descriptor = AuthSessionDescriptor(
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

        let surface = SessionStatus.authenticated(descriptor).systemSurface

        XCTAssertNil(surface)
    }

    func testUnresolvedRestoredSessionMapsToExplicitBlockedSurface() {
        let descriptor = AuthSessionDescriptor(
            accessToken: "token",
            user: StoredSessionUserSummary(
                id: 21,
                username: "01059387659",
                loginID: "01059387659",
                fullName: "서성원",
                role: "OFFICER",
                group: "FIELD",
                siteID: "R738",
                siteCode: "R738",
                siteName: "Apple_가로수길",
                tenantID: "srs_korea",
                location: "R738",
                status: "active",
                linkedEmployeeID: 301,
                employeeID: 301
            ),
            issuedAt: Date(timeIntervalSince1970: 1),
            persistenceSource: .storedSocKeys,
            storageKeys: ["soc_token", "soc_user"]
        )

        let surface = SessionStatus.unresolvedRestored(
            descriptor,
            message: "Restored session role 'OFFICER' is unresolved for Phase 2B."
        ).systemSurface

        XCTAssertEqual(surface?.kind, .blocked)
        XCTAssertEqual(surface?.title, "Unresolved Restored Session")
        XCTAssertEqual(surface?.footnote, RuntimeBlockedArea.authenticatedBootstrap.blockerTag)
    }
}
