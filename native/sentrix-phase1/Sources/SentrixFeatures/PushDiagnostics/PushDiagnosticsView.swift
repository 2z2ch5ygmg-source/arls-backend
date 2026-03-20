import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct PushDiagnosticsView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                switch model.pushDiagnostics.state {
                case .idle:
                    EmptyStateView(
                        title: "Push Test Not Run",
                        message: "Phase 2B exposes only the server-side push-test response model. Native APNs registration remains blocked."
                    )
                    Button("Run Server-Side Push Test") {
                        Task { await model.runPushDiagnostics() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SentrixTheme.Palette.accent)
                case .running:
                    LoadingStateView(
                        title: "Push Diagnostics",
                        message: "Running /api/push/test using the stored HQ session."
                    )
                    .frame(minHeight: 220)
                case .failed(let error):
                    SystemSurfaceView(surface: error.systemSurface) {
                        Task { await model.runPushDiagnostics() }
                    }
                case .loaded(let result):
                    SectionCardView(title: "Push Test") {
                        KeyValueRowView(key: "Title", value: result.title)
                        KeyValueRowView(key: "Body", value: result.body)
                        KeyValueRowView(key: "Registered iOS Devices", value: "\(result.registeredIOSDevices)")
                        KeyValueRowView(key: "Active iOS Devices", value: "\(result.activeIOSDevices)")
                        KeyValueRowView(key: "Selected Targets", value: "\(result.selectedIOSTargets)")
                    }

                    SectionCardView(title: "APNs Configuration") {
                        KeyValueRowView(key: "Enabled", value: result.apnsConfiguration.enabled ? "true" : "false")
                        KeyValueRowView(key: "Topic", value: result.apnsConfiguration.topic, monospaced: true)
                        KeyValueRowView(key: "Endpoint Mode", value: result.apnsConfiguration.endpointMode)
                        KeyValueRowView(key: "Use Sandbox", value: result.apnsConfiguration.useSandbox ? "true" : "false")
                        KeyValueRowView(key: "Runtime Is Azure", value: result.apnsConfiguration.runtimeIsAzure ? "true" : "false")
                    }

                    SectionCardView(title: "Delivery Summary") {
                        KeyValueRowView(key: "Targets", value: "\(result.pushResult.targets)")
                        KeyValueRowView(key: "Success", value: "\(result.pushResult.success)")
                        KeyValueRowView(key: "Failed", value: "\(result.pushResult.failed)")
                    }

                    SectionCardView(title: "Registered Devices") {
                        ForEach(result.registeredDevices) { device in
                            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                                KeyValueRowView(key: "Bundle", value: device.appBundle)
                                KeyValueRowView(key: "Token", value: device.token, monospaced: true)
                                KeyValueRowView(key: "Selected", value: device.selectedForSend ? "true" : "false")
                            }
                            if device.id != result.registeredDevices.last?.id {
                                Divider()
                            }
                        }
                    }

                    SystemSurfaceView(
                        surface: SystemSurfaceModel(
                            kind: .warning,
                            title: "Native Push Still Blocked",
                            message: "This screen models only the server-side push-test result. Token registration and device receipt remain outside Phase 2B."
                        )
                    )
                }
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle("Push Diagnostics")
    }
}
