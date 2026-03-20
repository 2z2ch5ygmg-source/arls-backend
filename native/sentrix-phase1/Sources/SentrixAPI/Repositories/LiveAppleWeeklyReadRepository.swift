import Foundation
import SentrixCore

public struct LiveAppleWeeklyReadRepository: AppleWeeklyReadRepository {
    private let client: JSONAPIClient

    public init(client: JSONAPIClient) {
        self.client = client
    }

    public func loadWorkspace(
        session: AuthSessionDescriptor,
        environment: AppEnvironment,
        context: AppleWeeklyContext
    ) async throws -> AppleWeeklyWorkspace {
        let headers = authHeaders(session)

        async let mappingsDTO: GoogleSheetsMappingsDTO = client.send(
            Endpoint(path: "/api/google-sheets/mappings", headers: headers),
            environment: environment
        )
        async let weekRangeDTO: WeeklyWeekRangeDTO = client.send(
            Endpoint(
                path: "/api/weekly-report/week-range",
                method: .post,
                headers: headers,
                body: try jsonBody([
                    "reference_date": context.referenceDate,
                    "site_code": context.siteCode,
                ])
            ),
            environment: environment
        )
        async let readinessDTO: WeeklySiteReadinessResponseDTO = client.send(
            Endpoint(
                path: "/api/weekly-report/site-readiness?site_code=\(context.siteCode)&report_year=\(context.reportYear)&reference_date=\(context.referenceDate)",
                headers: headers
            ),
            environment: environment
        )
        async let opsConfigDTO: WeeklyOpsConfigResponseDTO = client.send(
            Endpoint(
                path: "/api/weekly-report/ops-config?site_code=\(context.siteCode)&report_year=\(context.reportYear)&reference_date=\(context.referenceDate)",
                headers: headers
            ),
            environment: environment
        )
        async let conflictsDTO: WeeklyConflictsResponseDTO = client.send(
            Endpoint(
                path: "/api/weekly-report/conflicts?site_code=\(context.siteCode)&report_year=\(context.reportYear)&status=pending",
                headers: headers
            ),
            environment: environment
        )

        let weekRange = try await weekRangeDTO
        let requestedSections = ["attendance", "overtime", "overnight_guards"]

        let dryRunDTO: WeeklyDryRunResponseDTO = try await client.send(
            Endpoint(
                path: "/api/weekly-report/dry-run",
                method: .post,
                headers: headers,
                body: try jsonBody([
                    "operation_kind": "sync_patch",
                    "site_code": context.siteCode,
                    "report_year": context.reportYear,
                    "reference_date": context.referenceDate,
                    "target_dates": AppleWeeklyMapper.mapWeekRange(weekRange).dates,
                    "sections": requestedSections,
                ])
            ),
            environment: environment
        )

        let mappings = try await mappingsDTO
        let readiness = try await readinessDTO
        let opsConfig = try await opsConfigDTO
        let conflicts = try await conflictsDTO
        let dryRun = dryRunDTO

        let (serviceAccountEmail, mappingItems) = AppleWeeklyMapper.mapMappings(mappings)
        return AppleWeeklyWorkspace(
            context: context,
            serviceAccountEmail: serviceAccountEmail,
            mappings: mappingItems,
            weekRange: AppleWeeklyMapper.mapWeekRange(weekRange),
            readiness: AppleWeeklyMapper.mapReadiness(readiness),
            opsConfig: AppleWeeklyMapper.mapOpsConfig(opsConfig),
            conflicts: AppleWeeklyMapper.mapConflicts(conflicts),
            dryRun: AppleWeeklyMapper.mapDryRun(dryRun, requestedSections: requestedSections)
        )
    }

    private func authHeaders(_ session: AuthSessionDescriptor) -> [String: String] {
        ["Authorization": "Bearer \(session.accessToken)"]
    }

    private func jsonBody(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }
}
