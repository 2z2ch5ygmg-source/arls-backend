import Foundation

struct HealthDTO: Decodable {
    let ok: Bool
    let status: String
    let readOnly: Bool
    let readOnlyReason: String
    let importantIncidentFeatureEnabled: Bool
    let importantIncidentFeatureReason: String
    let incidentParticipantFeatureEnabled: Bool
    let incidentParticipantFeatureReason: String
    let featureTimerEnabled: Bool
    let featureLegacyAdminMenuEnabled: Bool
    let featureDataDictionaryEnabled: Bool
    let time: String

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case readOnly = "read_only"
        case readOnlyReason = "read_only_reason"
        case importantIncidentFeatureEnabled = "important_incident_feature_enabled"
        case importantIncidentFeatureReason = "important_incident_feature_reason"
        case incidentParticipantFeatureEnabled = "incident_participant_feature_enabled"
        case incidentParticipantFeatureReason = "incident_participant_feature_reason"
        case featureTimerEnabled = "feature_timer_enabled"
        case featureLegacyAdminMenuEnabled = "feature_legacy_admin_menu_enabled"
        case featureDataDictionaryEnabled = "feature_data_dictionary_enabled"
        case time
    }

    init(
        ok: Bool,
        status: String,
        readOnly: Bool,
        readOnlyReason: String,
        importantIncidentFeatureEnabled: Bool,
        importantIncidentFeatureReason: String,
        incidentParticipantFeatureEnabled: Bool,
        incidentParticipantFeatureReason: String,
        featureTimerEnabled: Bool,
        featureLegacyAdminMenuEnabled: Bool,
        featureDataDictionaryEnabled: Bool,
        time: String
    ) {
        self.ok = ok
        self.status = status
        self.readOnly = readOnly
        self.readOnlyReason = readOnlyReason
        self.importantIncidentFeatureEnabled = importantIncidentFeatureEnabled
        self.importantIncidentFeatureReason = importantIncidentFeatureReason
        self.incidentParticipantFeatureEnabled = incidentParticipantFeatureEnabled
        self.incidentParticipantFeatureReason = incidentParticipantFeatureReason
        self.featureTimerEnabled = featureTimerEnabled
        self.featureLegacyAdminMenuEnabled = featureLegacyAdminMenuEnabled
        self.featureDataDictionaryEnabled = featureDataDictionaryEnabled
        self.time = time
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ok = container.decodeLossyBool(forKey: .ok)
        status = container.decodeLossyString(forKey: .status)
        readOnly = container.decodeLossyBool(forKey: .readOnly)
        readOnlyReason = container.decodeLossyString(forKey: .readOnlyReason)
        importantIncidentFeatureEnabled = container.decodeLossyBool(forKey: .importantIncidentFeatureEnabled)
        importantIncidentFeatureReason = container.decodeLossyString(forKey: .importantIncidentFeatureReason)
        incidentParticipantFeatureEnabled = container.decodeLossyBool(forKey: .incidentParticipantFeatureEnabled)
        incidentParticipantFeatureReason = container.decodeLossyString(forKey: .incidentParticipantFeatureReason)
        featureTimerEnabled = container.decodeLossyBool(forKey: .featureTimerEnabled)
        featureLegacyAdminMenuEnabled = container.decodeLossyBool(forKey: .featureLegacyAdminMenuEnabled)
        featureDataDictionaryEnabled = container.decodeLossyBool(forKey: .featureDataDictionaryEnabled)
        time = container.decodeLossyString(forKey: .time)
    }
}

struct AppConfigDTO: Decodable {
    struct FeatureFlagsDTO: Decodable {
        let timerEnabled: Bool?
        let legacyAdminMenuEnabled: Bool?
        let dataDictionaryEnabled: Bool?
        let websocketEnabled: Bool?
        let gpsEnabled: Bool?

        enum CodingKeys: String, CodingKey {
            case timerEnabled = "timer_enabled"
            case legacyAdminMenuEnabled = "legacy_admin_menu_enabled"
            case dataDictionaryEnabled = "data_dictionary_enabled"
            case websocketEnabled = "websocket_enabled"
            case gpsEnabled = "gps_enabled"
        }

        init(
            timerEnabled: Bool? = nil,
            legacyAdminMenuEnabled: Bool? = nil,
            dataDictionaryEnabled: Bool? = nil,
            websocketEnabled: Bool? = nil,
            gpsEnabled: Bool? = nil
        ) {
            self.timerEnabled = timerEnabled
            self.legacyAdminMenuEnabled = legacyAdminMenuEnabled
            self.dataDictionaryEnabled = dataDictionaryEnabled
            self.websocketEnabled = websocketEnabled
            self.gpsEnabled = gpsEnabled
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            timerEnabled = container.decodeLossyOptionalBool(forKey: .timerEnabled)
            legacyAdminMenuEnabled = container.decodeLossyOptionalBool(forKey: .legacyAdminMenuEnabled)
            dataDictionaryEnabled = container.decodeLossyOptionalBool(forKey: .dataDictionaryEnabled)
            websocketEnabled = container.decodeLossyOptionalBool(forKey: .websocketEnabled)
            gpsEnabled = container.decodeLossyOptionalBool(forKey: .gpsEnabled)
        }
    }

    let appBaseURL: String
    let tenantID: String
    let siteID: String
    let readOnly: Bool
    let readOnlyReason: String
    let importantIncidentFeatureEnabled: Bool
    let importantIncidentFeatureReason: String
    let incidentParticipantFeatureEnabled: Bool
    let incidentParticipantFeatureReason: String
    let featureTimerEnabled: Bool
    let featureLegacyAdminMenuEnabled: Bool
    let featureFlags: FeatureFlagsDTO
    let masterDataReadOnly: Bool
    let masterDataReadOnlyMessage: String
    let tenantConfigEndpoint: String
    let ticketTemplateConfigEndpoint: String
    let reportConfigEndpoint: String
    let bootstrapConfigEndpoint: String
    let uiLabels: [String: String]
    let startupErrors: [String]

    enum CodingKeys: String, CodingKey {
        case appBaseURL = "app_base_url"
        case tenantID = "tenant_id"
        case siteID = "site_id"
        case readOnly = "read_only"
        case readOnlyReason = "read_only_reason"
        case importantIncidentFeatureEnabled = "important_incident_feature_enabled"
        case importantIncidentFeatureReason = "important_incident_feature_reason"
        case incidentParticipantFeatureEnabled = "incident_participant_feature_enabled"
        case incidentParticipantFeatureReason = "incident_participant_feature_reason"
        case featureTimerEnabled = "feature_timer_enabled"
        case featureLegacyAdminMenuEnabled = "feature_legacy_admin_menu_enabled"
        case featureFlags = "feature_flags"
        case masterDataReadOnly = "master_data_read_only"
        case masterDataReadOnlyMessage = "master_data_read_only_message"
        case tenantConfigEndpoint = "tenant_config_endpoint"
        case ticketTemplateConfigEndpoint = "ticket_template_config_endpoint"
        case reportConfigEndpoint = "report_config_endpoint"
        case bootstrapConfigEndpoint = "bootstrap_config_endpoint"
        case uiLabels = "ui_labels"
        case startupErrors = "startup_errors"
    }

    init(
        appBaseURL: String,
        tenantID: String,
        siteID: String,
        readOnly: Bool,
        readOnlyReason: String,
        importantIncidentFeatureEnabled: Bool,
        importantIncidentFeatureReason: String,
        incidentParticipantFeatureEnabled: Bool,
        incidentParticipantFeatureReason: String,
        featureTimerEnabled: Bool,
        featureLegacyAdminMenuEnabled: Bool,
        featureFlags: FeatureFlagsDTO,
        masterDataReadOnly: Bool,
        masterDataReadOnlyMessage: String,
        tenantConfigEndpoint: String,
        ticketTemplateConfigEndpoint: String,
        reportConfigEndpoint: String,
        bootstrapConfigEndpoint: String,
        uiLabels: [String: String],
        startupErrors: [String]
    ) {
        self.appBaseURL = appBaseURL
        self.tenantID = tenantID
        self.siteID = siteID
        self.readOnly = readOnly
        self.readOnlyReason = readOnlyReason
        self.importantIncidentFeatureEnabled = importantIncidentFeatureEnabled
        self.importantIncidentFeatureReason = importantIncidentFeatureReason
        self.incidentParticipantFeatureEnabled = incidentParticipantFeatureEnabled
        self.incidentParticipantFeatureReason = incidentParticipantFeatureReason
        self.featureTimerEnabled = featureTimerEnabled
        self.featureLegacyAdminMenuEnabled = featureLegacyAdminMenuEnabled
        self.featureFlags = featureFlags
        self.masterDataReadOnly = masterDataReadOnly
        self.masterDataReadOnlyMessage = masterDataReadOnlyMessage
        self.tenantConfigEndpoint = tenantConfigEndpoint
        self.ticketTemplateConfigEndpoint = ticketTemplateConfigEndpoint
        self.reportConfigEndpoint = reportConfigEndpoint
        self.bootstrapConfigEndpoint = bootstrapConfigEndpoint
        self.uiLabels = uiLabels
        self.startupErrors = startupErrors
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        appBaseURL = container.decodeLossyString(forKey: .appBaseURL)
        tenantID = container.decodeLossyString(forKey: .tenantID)
        siteID = container.decodeLossyString(forKey: .siteID)
        readOnly = container.decodeLossyBool(forKey: .readOnly)
        readOnlyReason = container.decodeLossyString(forKey: .readOnlyReason)
        importantIncidentFeatureEnabled = container.decodeLossyBool(forKey: .importantIncidentFeatureEnabled)
        importantIncidentFeatureReason = container.decodeLossyString(forKey: .importantIncidentFeatureReason)
        incidentParticipantFeatureEnabled = container.decodeLossyBool(forKey: .incidentParticipantFeatureEnabled)
        incidentParticipantFeatureReason = container.decodeLossyString(forKey: .incidentParticipantFeatureReason)
        featureTimerEnabled = container.decodeLossyBool(forKey: .featureTimerEnabled)
        featureLegacyAdminMenuEnabled = container.decodeLossyBool(forKey: .featureLegacyAdminMenuEnabled)
        featureFlags = container.decodeLossyObject(forKey: .featureFlags, default: .init())
        masterDataReadOnly = container.decodeLossyBool(forKey: .masterDataReadOnly)
        masterDataReadOnlyMessage = container.decodeLossyString(forKey: .masterDataReadOnlyMessage)
        tenantConfigEndpoint = container.decodeLossyString(forKey: .tenantConfigEndpoint)
        ticketTemplateConfigEndpoint = container.decodeLossyString(forKey: .ticketTemplateConfigEndpoint)
        reportConfigEndpoint = container.decodeLossyString(forKey: .reportConfigEndpoint)
        bootstrapConfigEndpoint = container.decodeLossyString(forKey: .bootstrapConfigEndpoint)
        uiLabels = container.decodeLossyStringDictionary(forKey: .uiLabels)
        startupErrors = container.decodeLossyStringArray(forKey: .startupErrors)
    }
}

struct BuildInfoDTO: Decodable {
    let appBaseURL: String
    let backendCommit: String
    let backendDirty: Bool
    let deployMode: String
    let imageTag: String
    let frontendBuildID: String
    let frontendUIBuildID: String
    let frontendSource: String
    let frontendSourceImage: String
    let deployedAtUTC: String
    let staticDirectory: String
    let dataDirectory: String
    let databasePath: String

    enum CodingKeys: String, CodingKey {
        case appBaseURL = "app_base_url"
        case backendCommit = "backend_commit"
        case backendDirty = "backend_dirty"
        case deployMode = "deploy_mode"
        case imageTag = "image_tag"
        case frontendBuildID = "frontend_build_id"
        case frontendUIBuildID = "frontend_ui_build_id"
        case frontendSource = "frontend_source"
        case frontendSourceImage = "frontend_source_image"
        case deployedAtUTC = "deployed_at_utc"
        case staticDirectory = "static_dir"
        case dataDirectory = "data_dir"
        case databasePath = "db_path"
    }

    init(
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

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        appBaseURL = container.decodeLossyString(forKey: .appBaseURL)
        backendCommit = container.decodeLossyString(forKey: .backendCommit)
        backendDirty = container.decodeLossyBool(forKey: .backendDirty)
        deployMode = container.decodeLossyString(forKey: .deployMode)
        imageTag = container.decodeLossyString(forKey: .imageTag)
        frontendBuildID = container.decodeLossyString(forKey: .frontendBuildID)
        frontendUIBuildID = container.decodeLossyString(forKey: .frontendUIBuildID)
        frontendSource = container.decodeLossyString(forKey: .frontendSource)
        frontendSourceImage = container.decodeLossyString(forKey: .frontendSourceImage)
        deployedAtUTC = container.decodeLossyString(forKey: .deployedAtUTC)
        staticDirectory = container.decodeLossyString(forKey: .staticDirectory)
        dataDirectory = container.decodeLossyString(forKey: .dataDirectory)
        databasePath = container.decodeLossyString(forKey: .databasePath)
    }
}
