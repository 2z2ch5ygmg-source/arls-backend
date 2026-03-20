import Foundation
import SentrixCore

enum AuthenticatedBootstrapMapper {
    static func map(_ dto: AuthenticatedBootstrapDTO, loadedAt: Date) -> AuthenticatedBootstrapSnapshot {
        let user = AuthenticatedUserSummary(
            id: dto.user.id,
            username: dto.user.username,
            fullName: dto.user.fullName,
            role: dto.user.role,
            tenantID: dto.user.tenantID,
            siteID: dto.user.siteID,
            location: dto.user.location
        )

        let features = RuntimeFeatureFlags(
            timerEnabled: dto.features.timerEnabled,
            legacyAdminMenuEnabled: dto.features.legacyAdminMenuEnabled,
            dataDictionaryEnabled: dto.features.dataDictionaryEnabled,
            websocketEnabled: dto.features.websocketEnabled,
            gpsEnabled: dto.features.gpsEnabled,
            importantIncidentEnabled: false,
            incidentParticipantEnabled: false
        )

        let endpoints = RuntimeEndpoints(
            tenantConfig: dto.tenantConfigEndpoint,
            ticketTemplateConfig: dto.ticketTemplateConfigEndpoint,
            reportConfig: dto.reportConfigEndpoint,
            bootstrapConfig: dto.bootstrapConfigEndpoint
        )

        let ticketConfig = TicketConfigSummary(
            tenantID: dto.ticketConfig.tenantID,
            siteID: dto.ticketConfig.siteID,
            templates: dto.ticketConfig.ticketTemplates.map { TicketTemplateSummary(type: $0.type) },
            source: dto.ticketConfig.source
        )

        let reportConfig = ReportConfigSummary(
            tenantID: dto.reportConfig.tenantID,
            siteID: dto.reportConfig.siteID,
            templates: dto.reportConfig.reportTemplates.map { template in
                ReportTemplateSummary(
                    key: template.key,
                    label: template.label,
                    category: template.category,
                    incidentTypes: template.incidentTypes,
                    fields: template.fields.map {
                        ReportFieldSummary(
                            key: $0.key,
                            label: $0.label,
                            input: $0.input,
                            required: $0.required
                        )
                    },
                    validationRules: template.validationRules.map {
                        ReportValidationRuleSummary(
                            type: $0.type,
                            field: $0.field,
                            message: $0.message
                        )
                    }
                )
            },
            requiredMessage: dto.reportConfig.validationRules["required_message"] ?? "",
            source: dto.reportConfig.source
        )

        return AuthenticatedBootstrapSnapshot(
            user: user,
            features: features,
            uiLabels: dto.uiLabels,
            ticketConfig: ticketConfig,
            reportConfig: reportConfig,
            appBaseURL: dto.appBaseURL,
            endpoints: endpoints,
            readOnly: dto.readOnly,
            readOnlyReason: dto.readOnlyReason,
            masterDataReadOnly: dto.masterDataReadOnly,
            masterDataReadOnlyMessage: dto.masterDataReadOnlyMessage,
            loadedAt: loadedAt
        )
    }
}
