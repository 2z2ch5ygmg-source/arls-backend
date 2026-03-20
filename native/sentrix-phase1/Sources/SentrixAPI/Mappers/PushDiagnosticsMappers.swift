import Foundation
import SentrixCore

enum PushDiagnosticsMapper {
    static func map(_ dto: PushTestResponseDTO) -> PushTestResult {
        PushTestResult(
            title: dto.title,
            body: dto.body,
            registeredIOSDevices: dto.registeredIOSDevices,
            activeIOSDevices: dto.activeIOSDevices,
            selectedIOSTargets: dto.selectedIOSTargets,
            registeredDevices: dto.registeredDevices.map {
                PushRegisteredDevice(
                    id: $0.pushDeviceID,
                    token: $0.token,
                    appBundle: $0.appBundle,
                    active: $0.active,
                    selectedForSend: $0.selectedForSend,
                    updatedAt: $0.updatedAt,
                    lastSeenAt: $0.lastSeenAt
                )
            },
            apnsConfiguration: PushAPNSConfiguration(
                enabled: dto.apnsConfig.enabled,
                topic: dto.apnsConfig.topic,
                useSandbox: dto.apnsConfig.useSandbox,
                endpointMode: dto.apnsConfig.endpointMode,
                endpoints: dto.apnsConfig.endpoints,
                runtimeIsAzure: dto.apnsConfig.runtimeIsAzure
            ),
            pushResult: PushTestSummary(
                apnsEnabled: dto.pushResult.apnsEnabled,
                targets: dto.pushResult.targets,
                success: dto.pushResult.success,
                failed: dto.pushResult.failed,
                results: dto.pushResult.results.map { result in
                    PushDeliveryResult(
                        user: result.user,
                        pushDeviceID: result.pushDeviceID,
                        token: result.token,
                        ok: result.ok,
                        attempts: result.attempts.map {
                            PushAttemptResult(
                                endpoint: $0.endpoint,
                                statusCode: $0.statusCode,
                                ok: $0.ok,
                                reasonCode: $0.reasonCode,
                                reason: $0.reason
                            )
                        }
                    )
                }
            )
        )
    }
}
