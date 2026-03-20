import Foundation
import SentrixCore

public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
}

public struct Endpoint<Response: Decodable>: Sendable {
    public let path: String
    public let method: HTTPMethod
    public let headers: [String: String]
    public let body: Data?

    public init(
        path: String,
        method: HTTPMethod = .get,
        headers: [String: String] = [:],
        body: Data? = nil
    ) {
        self.path = path
        self.method = method
        self.headers = headers
        self.body = body
    }
}

public protocol HTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionHTTPTransport: HTTPTransport {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw SentrixError.transport(message: "Sentrix returned a non-HTTP response.")
        }
        return (data, http)
    }
}

public struct JSONAPIClient: Sendable {
    private let transport: HTTPTransport
    private let decoder: JSONDecoder

    public init(
        transport: HTTPTransport,
        decoder: JSONDecoder = JSONDecoder()
    ) {
        self.transport = transport
        self.decoder = decoder
    }

    public func send<Response: Decodable>(
        _ endpoint: Endpoint<Response>,
        environment: AppEnvironment
    ) async throws -> Response {
        guard let url = URL(string: endpoint.path, relativeTo: environment.baseURL) else {
            throw SentrixError.invalidBaseURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if endpoint.body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.httpBody = endpoint.body
        endpoint.headers.forEach { key, value in
            request.setValue(value, forHTTPHeaderField: key)
        }

        let (data, response) = try await execute(request)

        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401 {
                throw SentrixError.unauthorized(message: Self.errorMessage(from: data) ?? "Unauthorized request.")
            }
            throw SentrixError.server(
                statusCode: response.statusCode,
                message: Self.errorMessage(from: data) ?? "Sentrix returned HTTP \(response.statusCode)."
            )
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw SentrixError.decoding(message: "Sentrix returned an unexpected JSON payload for \(endpoint.path).")
        }
    }

    private func execute(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            return try await transport.data(for: request)
        } catch let error as SentrixError {
            throw error
        } catch {
            throw SentrixError.transport(message: "Unable to reach Sentrix. Check network connectivity and retry.")
        }
    }

    private static func errorMessage(from data: Data) -> String? {
        guard
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }

        let message = (object["message"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let error = (object["error"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return [message, error].compactMap { $0 }.first(where: { !$0.isEmpty })
    }
}
