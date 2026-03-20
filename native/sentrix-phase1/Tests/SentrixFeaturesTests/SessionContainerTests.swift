import XCTest
@testable import SentrixFeatures
import SentrixCore

private struct AuthAdapterStub: AuthAdapter {
    let result: Result<AuthSessionDescriptor, SentrixError>

    func signIn(using draft: LoginDraft, environment: AppEnvironment) async throws -> AuthSessionDescriptor {
        try result.get()
    }

    func signOut(currentSession: AuthSessionDescriptor?) async {}
}

private final class StoredSessionRepositoryStub: StoredSessionRepository, @unchecked Sendable {
    var loadResult: Result<AuthSessionDescriptor?, SentrixError> = .success(nil)
    var persistedSession: AuthSessionDescriptor?
    var didClear = false

    func loadStoredSession() async throws -> AuthSessionDescriptor? {
        try loadResult.get()
    }

    func persistStoredSession(_ session: AuthSessionDescriptor) async throws {
        persistedSession = session
    }

    func clearStoredSession() async {
        didClear = true
    }
}

@MainActor
final class SessionContainerTests: XCTestCase {
    private let environment = AppEnvironment(name: "test", baseURL: URL(string: "https://example.com")!)

    func testSignInMapsRuntimeBlockedErrorToBlockedStatus() async {
        let storedSessionRepository = StoredSessionRepositoryStub()
        let container = SessionContainer(
            environment: environment,
            storedSessionRepository: storedSessionRepository,
            authAdapter: AuthAdapterStub(
                result: .failure(
                    .runtimeBlocked(
                        area: .productionAuthMode,
                        message: RuntimeBlockedArea.productionAuthMode.phase1FailureMessage
                    )
                )
            )
        )
        container.draft = LoginDraft(tenantCode: "srs", username: "mark", password: "pw")

        await container.signIn()

        XCTAssertEqual(
            container.status,
            .blocked(area: .productionAuthMode, message: RuntimeBlockedArea.productionAuthMode.phase1FailureMessage)
        )
    }

    func testSignInMapsUnauthorizedError() async {
        let storedSessionRepository = StoredSessionRepositoryStub()
        let container = SessionContainer(
            environment: environment,
            storedSessionRepository: storedSessionRepository,
            authAdapter: AuthAdapterStub(result: .failure(.unauthorized(message: "bad credentials")))
        )
        container.draft = LoginDraft(tenantCode: "srs", username: "mark", password: "pw")

        await container.signIn()

        XCTAssertEqual(container.status, .unauthorized(message: "bad credentials"))
    }

    func testSignInRequiresCompleteDraftBeforeCallingAdapter() async {
        let storedSessionRepository = StoredSessionRepositoryStub()
        let container = SessionContainer(
            environment: environment,
            storedSessionRepository: storedSessionRepository,
            authAdapter: AuthAdapterStub(
                result: .success(
                    sampleSession()
                )
            )
        )

        await container.signIn()

        XCTAssertEqual(
            container.status,
            .blocked(area: nil, message: "Tenant code, username, and password are required before sign-in can run.")
        )
    }

    func testRestoreStoredSessionPromotesStoredHQSession() async {
        let storedSessionRepository = StoredSessionRepositoryStub()
        storedSessionRepository.loadResult = .success(sampleSession())
        let container = SessionContainer(
            environment: environment,
            storedSessionRepository: storedSessionRepository,
            authAdapter: AuthAdapterStub(result: .failure(.runtimeBlocked(area: .productionAuthMode, message: "blocked")))
        )

        await container.restoreStoredSession()

        XCTAssertEqual(container.status, .verifyingRestored(sampleSession()))
        XCTAssertNil(container.currentSession)
        XCTAssertEqual(container.provisionalSession?.storageKeys, ["soc_token", "soc_user"])
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
