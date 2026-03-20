import Foundation
import SentrixCore

enum PublicBootstrapMapper {
    static func map(_ dto: HealthDTO) -> DeploymentHealth {
        DeploymentHealth(
            ok: dto.ok,
            status: dto.status,
            readOnly: dto.readOnly,
            readOnlyReason: dto.readOnlyReason,
            importantIncidentFeatureReason: dto.importantIncidentFeatureReason,
            incidentParticipantFeatureReason: dto.incidentParticipantFeatureReason,
            featureTimerEnabled: dto.featureTimerEnabled,
            featureLegacyAdminMenuEnabled: dto.featureLegacyAdminMenuEnabled,
            featureDataDictionaryEnabled: dto.featureDataDictionaryEnabled,
            serverTime: dto.time
        )
    }

    static func map(_ dto: AppConfigDTO) -> PublicAppConfig {
        let featureFlags = RuntimeFeatureFlags(
            timerEnabled: dto.featureFlags.timerEnabled ?? dto.featureTimerEnabled,
            legacyAdminMenuEnabled: dto.featureFlags.legacyAdminMenuEnabled ?? dto.featureLegacyAdminMenuEnabled,
            dataDictionaryEnabled: dto.featureFlags.dataDictionaryEnabled ?? false,
            websocketEnabled: dto.featureFlags.websocketEnabled ?? false,
            gpsEnabled: dto.featureFlags.gpsEnabled ?? false,
            importantIncidentEnabled: dto.importantIncidentFeatureEnabled,
            incidentParticipantEnabled: dto.incidentParticipantFeatureEnabled
        )

        let endpoints = RuntimeEndpoints(
            tenantConfig: dto.tenantConfigEndpoint,
            ticketTemplateConfig: dto.ticketTemplateConfigEndpoint,
            reportConfig: dto.reportConfigEndpoint,
            bootstrapConfig: dto.bootstrapConfigEndpoint
        )

        return PublicAppConfig(
            appBaseURL: dto.appBaseURL,
            tenantID: dto.tenantID,
            siteID: dto.siteID,
            readOnly: dto.readOnly,
            readOnlyReason: dto.readOnlyReason,
            masterDataReadOnly: dto.masterDataReadOnly,
            masterDataReadOnlyMessage: dto.masterDataReadOnlyMessage,
            features: featureFlags,
            endpoints: endpoints,
            uiLabels: dto.uiLabels,
            startupErrors: dto.startupErrors
        )
    }

    static func map(_ dto: BuildInfoDTO) -> BuildProvenance {
        BuildProvenance(
            appBaseURL: dto.appBaseURL,
            backendCommit: dto.backendCommit,
            backendDirty: dto.backendDirty,
            deployMode: dto.deployMode,
            imageTag: dto.imageTag,
            frontendBuildID: dto.frontendBuildID,
            frontendUIBuildID: dto.frontendUIBuildID,
            frontendSource: dto.frontendSource,
            frontendSourceImage: dto.frontendSourceImage,
            deployedAtUTC: dto.deployedAtUTC,
            staticDirectory: dto.staticDirectory,
            dataDirectory: dto.dataDirectory,
            databasePath: dto.databasePath
        )
    }
}
