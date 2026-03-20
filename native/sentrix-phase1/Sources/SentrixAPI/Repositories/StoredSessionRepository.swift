import Foundation
import SentrixCore

public struct UserDefaultsStoredSessionRepository: StoredSessionRepository, @unchecked Sendable {
    public let defaults: UserDefaults
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let now: @Sendable () -> Date

    public init(
        defaults: UserDefaults = .standard,
        decoder: JSONDecoder = JSONDecoder(),
        encoder: JSONEncoder = JSONEncoder(),
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.defaults = defaults
        self.decoder = decoder
        self.encoder = encoder
        self.now = now
    }

    public func loadStoredSession() async throws -> AuthSessionDescriptor? {
        let token = defaults.string(forKey: "soc_token")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let rawUser = defaults.string(forKey: "soc_user")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        guard !token.isEmpty, !rawUser.isEmpty else {
            return nil
        }

        guard let data = rawUser.data(using: .utf8) else {
            throw SentrixError.decoding(message: "Stored soc_user payload is not valid UTF-8.")
        }

        do {
            let dto = try decoder.decode(StoredSessionUserDTO.self, from: data)
            return AuthSessionDescriptor(
                accessToken: token,
                user: StoredSessionMapper.map(dto),
                issuedAt: now(),
                persistenceSource: .storedSocKeys,
                storageKeys: ["soc_token", "soc_user"]
            )
        } catch {
            throw SentrixError.decoding(message: "Stored soc_user payload could not be decoded.")
        }
    }

    public func persistStoredSession(_ session: AuthSessionDescriptor) async throws {
        let dto = StoredSessionMapper.map(session.user)
        let data = try encoder.encode(dto)
        guard let raw = String(data: data, encoding: .utf8) else {
            throw SentrixError.decoding(message: "Unable to encode stored soc_user payload.")
        }

        defaults.set(session.accessToken, forKey: "soc_token")
        defaults.set(raw, forKey: "soc_user")
    }

    public func clearStoredSession() async {
        defaults.removeObject(forKey: "soc_token")
        defaults.removeObject(forKey: "soc_user")
    }
}
