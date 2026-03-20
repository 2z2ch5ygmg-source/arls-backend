import Foundation
import SentrixCore

public struct HQSSERealtimeAdapter: RealtimeAdapter {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func makeRealtimeStream(
        session authSession: AuthSessionDescriptor,
        environment: AppEnvironment
    ) -> AsyncThrowingStream<RealtimeStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard
                        let relativeURL = URL(string: "/api/notifications/stream", relativeTo: environment.baseURL),
                        var components = URLComponents(url: relativeURL, resolvingAgainstBaseURL: true)
                    else {
                        throw SentrixError.invalidBaseURL
                    }
                    components.queryItems = [URLQueryItem(name: "token", value: authSession.accessToken)]
                    guard let url = components.url else {
                        throw SentrixError.invalidBaseURL
                    }

                    var request = URLRequest(url: url)
                    request.httpMethod = HTTPMethod.get.rawValue
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.cachePolicy = .reloadIgnoringLocalCacheData

                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw SentrixError.transport(message: "Sentrix realtime returned a non-HTTP response.")
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        if http.statusCode == 401 {
                            throw SentrixError.unauthorized(message: "Stored HQ session is unauthorized for realtime.")
                        }
                        throw SentrixError.server(
                            statusCode: http.statusCode,
                            message: "Realtime connection failed with HTTP \(http.statusCode)."
                        )
                    }

                    let contentType = http.value(forHTTPHeaderField: "Content-Type") ?? ""
                    guard contentType.lowercased().contains("text/event-stream") else {
                        throw SentrixError.decoding(
                            message: "Realtime transport did not return text/event-stream."
                        )
                    }

                    continuation.yield(.opened(endpoint: url.absoluteString, contentType: contentType))
                    for try await line in bytes.lines {
                        if Task.isCancelled {
                            break
                        }
                        continuation.yield(.line(line))
                    }
                    continuation.yield(.closed)
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }
}
