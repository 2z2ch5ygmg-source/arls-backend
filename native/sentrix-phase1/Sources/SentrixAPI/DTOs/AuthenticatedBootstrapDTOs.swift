import Foundation

struct AuthenticatedBootstrapDTO: Decodable {
    struct UserDTO: Decodable {
        let id: Int
        let username: String
        let fullName: String
        let role: String
        let tenantID: String
        let siteID: String
        let location: String

        enum CodingKeys: String, CodingKey {
            case id
            case username
            case fullName = "full_name"
            case role
            case tenantID = "tenant_id"
            case siteID = "site_id"
            case location
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            id = container.decodeLossyInt(forKey: .id)
            username = container.decodeLossyString(forKey: .username)
            fullName = container.decodeLossyString(forKey: .fullName)
            role = container.decodeLossyString(forKey: .role)
            tenantID = container.decodeLossyString(forKey: .tenantID)
            siteID = container.decodeLossyString(forKey: .siteID)
            location = container.decodeLossyString(forKey: .location)
        }
    }

    struct FeaturesDTO: Decodable {
        let timerEnabled: Bool
        let legacyAdminMenuEnabled: Bool
        let dataDictionaryEnabled: Bool
        let websocketEnabled: Bool
        let gpsEnabled: Bool

        enum CodingKeys: String, CodingKey {
            case timerEnabled = "timer_enabled"
            case legacyAdminMenuEnabled = "legacy_admin_menu_enabled"
            case dataDictionaryEnabled = "data_dictionary_enabled"
            case websocketEnabled = "websocket_enabled"
            case gpsEnabled = "gps_enabled"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            timerEnabled = container.decodeLossyBool(forKey: .timerEnabled)
            legacyAdminMenuEnabled = container.decodeLossyBool(forKey: .legacyAdminMenuEnabled)
            dataDictionaryEnabled = container.decodeLossyBool(forKey: .dataDictionaryEnabled)
            websocketEnabled = container.decodeLossyBool(forKey: .websocketEnabled)
            gpsEnabled = container.decodeLossyBool(forKey: .gpsEnabled)
        }
    }

    struct TicketConfigDTO: Decodable {
        struct TemplateDTO: Decodable {
            let type: String

            init(from decoder: Decoder) throws {
                let container = try decoder.singleValueContainer()
                if let value = try? container.decode(String.self) {
                    type = value
                } else {
                    let keyed = try decoder.container(keyedBy: GenericCodingKey.self)
                    type = keyed.decodeLossyString(forKey: .init(stringValue: "type"))
                }
            }
        }

        let tenantID: String
        let siteID: String
        let ticketTemplates: [TemplateDTO]
        let source: String

        enum CodingKeys: String, CodingKey {
            case tenantID = "tenant_id"
            case siteID = "site_id"
            case ticketTemplates = "ticket_templates"
            case source
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            tenantID = container.decodeLossyString(forKey: .tenantID)
            siteID = container.decodeLossyString(forKey: .siteID)
            ticketTemplates = container.decodeLossyArray(forKey: .ticketTemplates)
            source = container.decodeLossyString(forKey: .source)
        }
    }

    struct ReportConfigDTO: Decodable {
        struct TemplateDTO: Decodable {
            struct FieldDTO: Decodable {
                let key: String
                let label: String
                let input: String
                let required: Bool

                enum CodingKeys: String, CodingKey {
                    case key
                    case label
                    case input
                    case required
                }

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    key = container.decodeLossyString(forKey: .key)
                    label = container.decodeLossyString(forKey: .label)
                    input = container.decodeLossyString(forKey: .input)
                    required = container.decodeLossyBool(forKey: .required)
                }
            }

            struct ValidationRuleDTO: Decodable {
                let type: String
                let field: String
                let message: String

                enum CodingKeys: String, CodingKey {
                    case type
                    case field
                    case message
                }

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    type = container.decodeLossyString(forKey: .type)
                    field = container.decodeLossyString(forKey: .field)
                    message = container.decodeLossyString(forKey: .message)
                }
            }

            let key: String
            let label: String
            let category: String
            let incidentTypes: [String]
            let fields: [FieldDTO]
            let validationRules: [ValidationRuleDTO]

            enum CodingKeys: String, CodingKey {
                case key
                case label
                case category
                case incidentTypes = "incident_types"
                case fields
                case validationRules = "validation_rules"
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                key = container.decodeLossyString(forKey: .key)
                label = container.decodeLossyString(forKey: .label)
                category = container.decodeLossyString(forKey: .category)
                incidentTypes = container.decodeLossyStringArray(forKey: .incidentTypes)
                fields = container.decodeLossyArray(forKey: .fields)
                validationRules = container.decodeLossyArray(forKey: .validationRules)
            }
        }

        let tenantID: String
        let siteID: String
        let reportTemplates: [TemplateDTO]
        let validationRules: [String: String]
        let source: String

        enum CodingKeys: String, CodingKey {
            case tenantID = "tenant_id"
            case siteID = "site_id"
            case reportTemplates = "report_templates"
            case validationRules = "validation_rules"
            case source
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            tenantID = container.decodeLossyString(forKey: .tenantID)
            siteID = container.decodeLossyString(forKey: .siteID)
            reportTemplates = container.decodeLossyArray(forKey: .reportTemplates)
            validationRules = container.decodeLossyStringDictionary(forKey: .validationRules)
            source = container.decodeLossyString(forKey: .source)
        }
    }

    let user: UserDTO
    let features: FeaturesDTO
    let uiLabels: [String: String]
    let ticketConfig: TicketConfigDTO
    let reportConfig: ReportConfigDTO
    let appBaseURL: String
    let tenantConfigEndpoint: String
    let ticketTemplateConfigEndpoint: String
    let reportConfigEndpoint: String
    let bootstrapConfigEndpoint: String
    let readOnly: Bool
    let readOnlyReason: String
    let masterDataReadOnly: Bool
    let masterDataReadOnlyMessage: String

    enum CodingKeys: String, CodingKey {
        case user
        case features
        case uiLabels = "ui_labels"
        case ticketConfig = "ticket_config"
        case reportConfig = "report_config"
        case appBaseURL = "app_base_url"
        case tenantConfigEndpoint = "tenant_config_endpoint"
        case ticketTemplateConfigEndpoint = "ticket_template_config_endpoint"
        case reportConfigEndpoint = "report_config_endpoint"
        case bootstrapConfigEndpoint = "bootstrap_config_endpoint"
        case readOnly = "read_only"
        case readOnlyReason = "read_only_reason"
        case masterDataReadOnly = "master_data_read_only"
        case masterDataReadOnlyMessage = "master_data_read_only_message"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        user = container.decodeLossyObject(
            forKey: .user,
            default: try UserDTO(from: EmptyDecoder())
        )
        features = container.decodeLossyObject(
            forKey: .features,
            default: try FeaturesDTO(from: EmptyDecoder())
        )
        uiLabels = container.decodeLossyStringDictionary(forKey: .uiLabels)
        ticketConfig = container.decodeLossyObject(
            forKey: .ticketConfig,
            default: try TicketConfigDTO(from: EmptyDecoder())
        )
        reportConfig = container.decodeLossyObject(
            forKey: .reportConfig,
            default: try ReportConfigDTO(from: EmptyDecoder())
        )
        appBaseURL = container.decodeLossyString(forKey: .appBaseURL)
        tenantConfigEndpoint = container.decodeLossyString(forKey: .tenantConfigEndpoint)
        ticketTemplateConfigEndpoint = container.decodeLossyString(forKey: .ticketTemplateConfigEndpoint)
        reportConfigEndpoint = container.decodeLossyString(forKey: .reportConfigEndpoint)
        bootstrapConfigEndpoint = container.decodeLossyString(forKey: .bootstrapConfigEndpoint)
        readOnly = container.decodeLossyBool(forKey: .readOnly)
        readOnlyReason = container.decodeLossyString(forKey: .readOnlyReason)
        masterDataReadOnly = container.decodeLossyBool(forKey: .masterDataReadOnly)
        masterDataReadOnlyMessage = container.decodeLossyString(forKey: .masterDataReadOnlyMessage)
    }
}

private struct EmptyDecoder: Decoder {
    var codingPath: [CodingKey] { [] }
    var userInfo: [CodingUserInfoKey: Any] { [:] }

    func container<Key>(keyedBy type: Key.Type) throws -> KeyedDecodingContainer<Key> where Key : CodingKey {
        let container = EmptyKeyedDecodingContainer<Key>()
        return KeyedDecodingContainer(container)
    }

    func unkeyedContainer() throws -> UnkeyedDecodingContainer {
        EmptyUnkeyedDecodingContainer()
    }

    func singleValueContainer() throws -> SingleValueDecodingContainer {
        EmptySingleValueDecodingContainer()
    }
}

private struct EmptyKeyedDecodingContainer<Key: CodingKey>: KeyedDecodingContainerProtocol {
    var codingPath: [CodingKey] { [] }
    var allKeys: [Key] { [] }
    func contains(_ key: Key) -> Bool { false }
    func decodeNil(forKey key: Key) throws -> Bool { true }
    func decode(_ type: Bool.Type, forKey key: Key) throws -> Bool { false }
    func decode(_ type: String.Type, forKey key: Key) throws -> String { "" }
    func decode(_ type: Double.Type, forKey key: Key) throws -> Double { 0 }
    func decode(_ type: Float.Type, forKey key: Key) throws -> Float { 0 }
    func decode(_ type: Int.Type, forKey key: Key) throws -> Int { 0 }
    func decode(_ type: Int8.Type, forKey key: Key) throws -> Int8 { 0 }
    func decode(_ type: Int16.Type, forKey key: Key) throws -> Int16 { 0 }
    func decode(_ type: Int32.Type, forKey key: Key) throws -> Int32 { 0 }
    func decode(_ type: Int64.Type, forKey key: Key) throws -> Int64 { 0 }
    func decode(_ type: UInt.Type, forKey key: Key) throws -> UInt { 0 }
    func decode(_ type: UInt8.Type, forKey key: Key) throws -> UInt8 { 0 }
    func decode(_ type: UInt16.Type, forKey key: Key) throws -> UInt16 { 0 }
    func decode(_ type: UInt32.Type, forKey key: Key) throws -> UInt32 { 0 }
    func decode(_ type: UInt64.Type, forKey key: Key) throws -> UInt64 { 0 }
    func decode<T>(_ type: T.Type, forKey key: Key) throws -> T where T : Decodable { try T(from: EmptyDecoder()) }
    func nestedContainer<NestedKey>(keyedBy type: NestedKey.Type, forKey key: Key) throws -> KeyedDecodingContainer<NestedKey> where NestedKey : CodingKey { try EmptyDecoder().container(keyedBy: type) }
    func nestedUnkeyedContainer(forKey key: Key) throws -> UnkeyedDecodingContainer { EmptyUnkeyedDecodingContainer() }
    func superDecoder() throws -> Decoder { EmptyDecoder() }
    func superDecoder(forKey key: Key) throws -> Decoder { EmptyDecoder() }
}

private struct EmptyUnkeyedDecodingContainer: UnkeyedDecodingContainer {
    var codingPath: [CodingKey] { [] }
    var count: Int? { 0 }
    var isAtEnd: Bool { true }
    var currentIndex: Int { 0 }
    mutating func decodeNil() throws -> Bool { true }
    mutating func decode(_ type: Bool.Type) throws -> Bool { false }
    mutating func decode(_ type: String.Type) throws -> String { "" }
    mutating func decode(_ type: Double.Type) throws -> Double { 0 }
    mutating func decode(_ type: Float.Type) throws -> Float { 0 }
    mutating func decode(_ type: Int.Type) throws -> Int { 0 }
    mutating func decode(_ type: Int8.Type) throws -> Int8 { 0 }
    mutating func decode(_ type: Int16.Type) throws -> Int16 { 0 }
    mutating func decode(_ type: Int32.Type) throws -> Int32 { 0 }
    mutating func decode(_ type: Int64.Type) throws -> Int64 { 0 }
    mutating func decode(_ type: UInt.Type) throws -> UInt { 0 }
    mutating func decode(_ type: UInt8.Type) throws -> UInt8 { 0 }
    mutating func decode(_ type: UInt16.Type) throws -> UInt16 { 0 }
    mutating func decode(_ type: UInt32.Type) throws -> UInt32 { 0 }
    mutating func decode(_ type: UInt64.Type) throws -> UInt64 { 0 }
    mutating func decode<T>(_ type: T.Type) throws -> T where T : Decodable { try T(from: EmptyDecoder()) }
    mutating func nestedContainer<NestedKey>(keyedBy type: NestedKey.Type) throws -> KeyedDecodingContainer<NestedKey> where NestedKey : CodingKey { try EmptyDecoder().container(keyedBy: type) }
    mutating func nestedUnkeyedContainer() throws -> UnkeyedDecodingContainer { self }
    mutating func superDecoder() throws -> Decoder { EmptyDecoder() }
}

private struct EmptySingleValueDecodingContainer: SingleValueDecodingContainer {
    var codingPath: [CodingKey] { [] }
    func decodeNil() -> Bool { true }
    func decode(_ type: Bool.Type) throws -> Bool { false }
    func decode(_ type: String.Type) throws -> String { "" }
    func decode(_ type: Double.Type) throws -> Double { 0 }
    func decode(_ type: Float.Type) throws -> Float { 0 }
    func decode(_ type: Int.Type) throws -> Int { 0 }
    func decode(_ type: Int8.Type) throws -> Int8 { 0 }
    func decode(_ type: Int16.Type) throws -> Int16 { 0 }
    func decode(_ type: Int32.Type) throws -> Int32 { 0 }
    func decode(_ type: Int64.Type) throws -> Int64 { 0 }
    func decode(_ type: UInt.Type) throws -> UInt { 0 }
    func decode(_ type: UInt8.Type) throws -> UInt8 { 0 }
    func decode(_ type: UInt16.Type) throws -> UInt16 { 0 }
    func decode(_ type: UInt32.Type) throws -> UInt32 { 0 }
    func decode(_ type: UInt64.Type) throws -> UInt64 { 0 }
    func decode<T>(_ type: T.Type) throws -> T where T : Decodable { try T(from: EmptyDecoder()) }
}
