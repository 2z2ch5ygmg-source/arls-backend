import Foundation

struct PushTestResponseDTO: Decodable {
    struct RegisteredDeviceDTO: Decodable {
        let pushDeviceID: Int
        let token: String
        let appBundle: String
        let active: Bool
        let selectedForSend: Bool
        let updatedAt: String
        let lastSeenAt: String

        enum CodingKeys: String, CodingKey {
            case pushDeviceID = "push_device_id"
            case token
            case appBundle = "app_bundle"
            case active
            case selectedForSend = "selected_for_send"
            case updatedAt = "updated_at"
            case lastSeenAt = "last_seen_at"
        }
    }

    struct APNSConfigDTO: Decodable {
        let enabled: Bool
        let topic: String
        let useSandbox: Bool
        let endpointMode: String
        let endpoints: [String]
        let runtimeIsAzure: Bool

        enum CodingKeys: String, CodingKey {
            case enabled
            case topic
            case useSandbox = "use_sandbox"
            case endpointMode = "endpoint_mode"
            case endpoints
            case runtimeIsAzure = "runtime_is_azure"
        }
    }

    struct PushResultDTO: Decodable {
        struct DeliveryResultDTO: Decodable {
            struct AttemptDTO: Decodable {
                let ok: Bool
                let endpoint: String
                let statusCode: Int
                let reasonCode: String
                let reason: String

                enum CodingKeys: String, CodingKey {
                    case ok
                    case endpoint
                    case statusCode = "status_code"
                    case reasonCode = "reason_code"
                    case reason
                }
            }

            let user: String
            let pushDeviceID: Int
            let token: String
            let ok: Bool
            let attempts: [AttemptDTO]

            enum CodingKeys: String, CodingKey {
                case user
                case pushDeviceID = "push_device_id"
                case token
                case ok
                case attempts
            }
        }

        let apnsEnabled: Bool
        let targets: Int
        let success: Int
        let failed: Int
        let results: [DeliveryResultDTO]

        enum CodingKeys: String, CodingKey {
            case apnsEnabled = "apns_enabled"
            case targets
            case success
            case failed
            case results
        }
    }

    let title: String
    let body: String
    let registeredIOSDevices: Int
    let activeIOSDevices: Int
    let selectedIOSTargets: Int
    let registeredDevices: [RegisteredDeviceDTO]
    let apnsConfig: APNSConfigDTO
    let pushResult: PushResultDTO

    enum CodingKeys: String, CodingKey {
        case title
        case body
        case registeredIOSDevices = "registered_ios_devices"
        case activeIOSDevices = "active_ios_devices"
        case selectedIOSTargets = "selected_ios_targets"
        case registeredDevices = "registered_devices"
        case apnsConfig = "apns_config"
        case pushResult = "push_result"
    }
}
