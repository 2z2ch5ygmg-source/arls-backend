import Foundation

public struct AuthenticatedUserSummary: Equatable, Sendable {
    public let id: Int
    public let username: String
    public let fullName: String
    public let role: String
    public let tenantID: String
    public let siteID: String
    public let location: String

    public init(
        id: Int,
        username: String,
        fullName: String,
        role: String,
        tenantID: String,
        siteID: String,
        location: String
    ) {
        self.id = id
        self.username = username
        self.fullName = fullName
        self.role = role
        self.tenantID = tenantID
        self.siteID = siteID
        self.location = location
    }
}

public struct TicketTemplateSummary: Equatable, Sendable, Identifiable {
    public var id: String { type }
    public let type: String

    public init(type: String) {
        self.type = type
    }
}

public struct ReportFieldSummary: Equatable, Sendable, Identifiable {
    public var id: String { key }
    public let key: String
    public let label: String
    public let input: String
    public let required: Bool

    public init(key: String, label: String, input: String, required: Bool) {
        self.key = key
        self.label = label
        self.input = input
        self.required = required
    }
}

public struct ReportValidationRuleSummary: Equatable, Sendable, Identifiable {
    public var id: String { "\(type):\(field):\(message)" }
    public let type: String
    public let field: String
    public let message: String

    public init(type: String, field: String, message: String) {
        self.type = type
        self.field = field
        self.message = message
    }
}

public struct ReportTemplateSummary: Equatable, Sendable, Identifiable {
    public var id: String { key }
    public let key: String
    public let label: String
    public let category: String
    public let incidentTypes: [String]
    public let fields: [ReportFieldSummary]
    public let validationRules: [ReportValidationRuleSummary]

    public init(
        key: String,
        label: String,
        category: String,
        incidentTypes: [String],
        fields: [ReportFieldSummary],
        validationRules: [ReportValidationRuleSummary]
    ) {
        self.key = key
        self.label = label
        self.category = category
        self.incidentTypes = incidentTypes
        self.fields = fields
        self.validationRules = validationRules
    }
}

public struct TicketConfigSummary: Equatable, Sendable {
    public let tenantID: String
    public let siteID: String
    public let templates: [TicketTemplateSummary]
    public let source: String

    public init(
        tenantID: String,
        siteID: String,
        templates: [TicketTemplateSummary],
        source: String
    ) {
        self.tenantID = tenantID
        self.siteID = siteID
        self.templates = templates
        self.source = source
    }
}

public struct ReportConfigSummary: Equatable, Sendable {
    public let tenantID: String
    public let siteID: String
    public let templates: [ReportTemplateSummary]
    public let requiredMessage: String
    public let source: String

    public init(
        tenantID: String,
        siteID: String,
        templates: [ReportTemplateSummary],
        requiredMessage: String,
        source: String
    ) {
        self.tenantID = tenantID
        self.siteID = siteID
        self.templates = templates
        self.requiredMessage = requiredMessage
        self.source = source
    }
}

public struct AuthenticatedBootstrapSnapshot: Equatable, Sendable {
    public let user: AuthenticatedUserSummary
    public let features: RuntimeFeatureFlags
    public let uiLabels: [String: String]
    public let ticketConfig: TicketConfigSummary
    public let reportConfig: ReportConfigSummary
    public let appBaseURL: String
    public let endpoints: RuntimeEndpoints
    public let readOnly: Bool
    public let readOnlyReason: String
    public let masterDataReadOnly: Bool
    public let masterDataReadOnlyMessage: String
    public let loadedAt: Date

    public init(
        user: AuthenticatedUserSummary,
        features: RuntimeFeatureFlags,
        uiLabels: [String: String],
        ticketConfig: TicketConfigSummary,
        reportConfig: ReportConfigSummary,
        appBaseURL: String,
        endpoints: RuntimeEndpoints,
        readOnly: Bool,
        readOnlyReason: String,
        masterDataReadOnly: Bool,
        masterDataReadOnlyMessage: String,
        loadedAt: Date
    ) {
        self.user = user
        self.features = features
        self.uiLabels = uiLabels
        self.ticketConfig = ticketConfig
        self.reportConfig = reportConfig
        self.appBaseURL = appBaseURL
        self.endpoints = endpoints
        self.readOnly = readOnly
        self.readOnlyReason = readOnlyReason
        self.masterDataReadOnly = masterDataReadOnly
        self.masterDataReadOnlyMessage = masterDataReadOnlyMessage
        self.loadedAt = loadedAt
    }
}

public extension AuthenticatedUserSummary {
    var normalizedRole: String {
        role.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var canonicalRoleMarker: String {
        normalizedRole
            .uppercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
    }

    var authenticatedShellScope: AuthenticatedShellScope? {
        if canonicalRoleMarker == "HQ_ADMIN" {
            return .hqSafe(role: "HQ_ADMIN")
        }
        return nil
    }
}
