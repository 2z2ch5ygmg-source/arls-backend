import Foundation

public struct AppEnvironment: Equatable, Sendable {
    public let name: String
    public let baseURL: URL

    public init(name: String, baseURL: URL) {
        self.name = name
        self.baseURL = baseURL
    }

    public static func phase1Default() -> AppEnvironment {
        if
            let raw = ProcessInfo.processInfo.environment["SENTRIX_BASE_URL"],
            let url = URL(string: raw),
            !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        {
            return AppEnvironment(name: "override", baseURL: url)
        }

        return AppEnvironment(
            name: "production-public",
            baseURL: URL(string: "https://security-ops-center-prod-002-260227135557.azurewebsites.net")!
        )
    }
}

public struct RuntimeFeatureFlags: Equatable, Sendable {
    public let timerEnabled: Bool
    public let legacyAdminMenuEnabled: Bool
    public let dataDictionaryEnabled: Bool
    public let websocketEnabled: Bool
    public let gpsEnabled: Bool
    public let importantIncidentEnabled: Bool
    public let incidentParticipantEnabled: Bool

    public init(
        timerEnabled: Bool,
        legacyAdminMenuEnabled: Bool,
        dataDictionaryEnabled: Bool,
        websocketEnabled: Bool,
        gpsEnabled: Bool,
        importantIncidentEnabled: Bool,
        incidentParticipantEnabled: Bool
    ) {
        self.timerEnabled = timerEnabled
        self.legacyAdminMenuEnabled = legacyAdminMenuEnabled
        self.dataDictionaryEnabled = dataDictionaryEnabled
        self.websocketEnabled = websocketEnabled
        self.gpsEnabled = gpsEnabled
        self.importantIncidentEnabled = importantIncidentEnabled
        self.incidentParticipantEnabled = incidentParticipantEnabled
    }
}

public struct RuntimeEndpoints: Equatable, Sendable {
    public let tenantConfig: String
    public let ticketTemplateConfig: String
    public let reportConfig: String
    public let bootstrapConfig: String

    public init(
        tenantConfig: String,
        ticketTemplateConfig: String,
        reportConfig: String,
        bootstrapConfig: String
    ) {
        self.tenantConfig = tenantConfig
        self.ticketTemplateConfig = ticketTemplateConfig
        self.reportConfig = reportConfig
        self.bootstrapConfig = bootstrapConfig
    }
}

public struct DeploymentHealth: Equatable, Sendable {
    public let ok: Bool
    public let status: String
    public let readOnly: Bool
    public let readOnlyReason: String
    public let importantIncidentFeatureReason: String
    public let incidentParticipantFeatureReason: String
    public let featureTimerEnabled: Bool
    public let featureLegacyAdminMenuEnabled: Bool
    public let featureDataDictionaryEnabled: Bool
    public let serverTime: String

    public init(
        ok: Bool,
        status: String,
        readOnly: Bool,
        readOnlyReason: String,
        importantIncidentFeatureReason: String,
        incidentParticipantFeatureReason: String,
        featureTimerEnabled: Bool,
        featureLegacyAdminMenuEnabled: Bool,
        featureDataDictionaryEnabled: Bool,
        serverTime: String
    ) {
        self.ok = ok
        self.status = status
        self.readOnly = readOnly
        self.readOnlyReason = readOnlyReason
        self.importantIncidentFeatureReason = importantIncidentFeatureReason
        self.incidentParticipantFeatureReason = incidentParticipantFeatureReason
        self.featureTimerEnabled = featureTimerEnabled
        self.featureLegacyAdminMenuEnabled = featureLegacyAdminMenuEnabled
        self.featureDataDictionaryEnabled = featureDataDictionaryEnabled
        self.serverTime = serverTime
    }
}

public struct PublicAppConfig: Equatable, Sendable {
    public let appBaseURL: String
    public let tenantID: String
    public let siteID: String
    public let readOnly: Bool
    public let readOnlyReason: String
    public let masterDataReadOnly: Bool
    public let masterDataReadOnlyMessage: String
    public let features: RuntimeFeatureFlags
    public let endpoints: RuntimeEndpoints
    public let uiLabels: [String: String]
    public let startupErrors: [String]

    public init(
        appBaseURL: String,
        tenantID: String,
        siteID: String,
        readOnly: Bool,
        readOnlyReason: String,
        masterDataReadOnly: Bool,
        masterDataReadOnlyMessage: String,
        features: RuntimeFeatureFlags,
        endpoints: RuntimeEndpoints,
        uiLabels: [String: String],
        startupErrors: [String]
    ) {
        self.appBaseURL = appBaseURL
        self.tenantID = tenantID
        self.siteID = siteID
        self.readOnly = readOnly
        self.readOnlyReason = readOnlyReason
        self.masterDataReadOnly = masterDataReadOnly
        self.masterDataReadOnlyMessage = masterDataReadOnlyMessage
        self.features = features
        self.endpoints = endpoints
        self.uiLabels = uiLabels
        self.startupErrors = startupErrors
    }
}

public struct BuildProvenance: Equatable, Sendable {
    public let appBaseURL: String
    public let backendCommit: String
    public let backendDirty: Bool
    public let deployMode: String
    public let imageTag: String
    public let frontendBuildID: String
    public let frontendUIBuildID: String
    public let frontendSource: String
    public let frontendSourceImage: String
    public let deployedAtUTC: String
    public let staticDirectory: String
    public let dataDirectory: String
    public let databasePath: String

    public init(
        appBaseURL: String,
        backendCommit: String,
        backendDirty: Bool,
        deployMode: String,
        imageTag: String,
        frontendBuildID: String,
        frontendUIBuildID: String,
        frontendSource: String,
        frontendSourceImage: String,
        deployedAtUTC: String,
        staticDirectory: String,
        dataDirectory: String,
        databasePath: String
    ) {
        self.appBaseURL = appBaseURL
        self.backendCommit = backendCommit
        self.backendDirty = backendDirty
        self.deployMode = deployMode
        self.imageTag = imageTag
        self.frontendBuildID = frontendBuildID
        self.frontendUIBuildID = frontendUIBuildID
        self.frontendSource = frontendSource
        self.frontendSourceImage = frontendSourceImage
        self.deployedAtUTC = deployedAtUTC
        self.staticDirectory = staticDirectory
        self.dataDirectory = dataDirectory
        self.databasePath = databasePath
    }
}

public struct PublicBootstrapSnapshot: Equatable, Sendable {
    public let environment: AppEnvironment
    public let health: DeploymentHealth
    public let appConfig: PublicAppConfig
    public let buildInfo: BuildProvenance
    public let loadedAt: Date

    public init(
        environment: AppEnvironment,
        health: DeploymentHealth,
        appConfig: PublicAppConfig,
        buildInfo: BuildProvenance,
        loadedAt: Date
    ) {
        self.environment = environment
        self.health = health
        self.appConfig = appConfig
        self.buildInfo = buildInfo
        self.loadedAt = loadedAt
    }
}

public struct RuntimeNotice: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable {
        case readOnly
        case masterDataReadOnly
    }

    public let id: String
    public let kind: Kind
    public let title: String
    public let message: String

    public init(kind: Kind, title: String, message: String) {
        self.id = "\(kind.rawValue):\(message)"
        self.kind = kind
        self.title = title
        self.message = message
    }
}

public extension PublicBootstrapSnapshot {
    var notices: [RuntimeNotice] {
        var items: [RuntimeNotice] = []
        if health.readOnly || appConfig.readOnly {
            let reason = appConfig.readOnlyReason.isEmpty ? health.readOnlyReason : appConfig.readOnlyReason
            let fallback = "Read-only mode is enabled by runtime state."
            let latestStartupError = appConfig.startupErrors.last?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let message = latestStartupError.isEmpty ? (reason.isEmpty ? fallback : reason) : "\(reason.isEmpty ? fallback : reason) (\(latestStartupError))"
            items.append(RuntimeNotice(kind: .readOnly, title: "Read-Only Mode", message: message))
        }
        if appConfig.masterDataReadOnly {
            items.append(
                RuntimeNotice(
                    kind: .masterDataReadOnly,
                    title: "Master Data Read-Only",
                    message: appConfig.masterDataReadOnlyMessage
                )
            )
        }
        return items
    }
}
