import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct LoginContainerView: View {
    @ObservedObject private var model: Phase1AppModel

    public init(model: Phase1AppModel) {
        self.model = model
    }

    public var body: some View {
        SectionCardView(
            title: "Login Shell",
            subtitle: "Stored-session continuation is supported; fresh production login routing remains blocked."
        ) {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.sm) {
                Text("Phase 2B restores only previously stored runtime-confirmed HQ or field-observed sessions. This form still does not freeze local, HR, or hybrid production login behavior.")
                    .font(SentrixTheme.Typography.caption)
                    .foregroundStyle(SentrixTheme.Palette.muted)

                TextField("Tenant code", text: $model.session.draft.tenantCode)
                    .textFieldStyle(.roundedBorder)
                TextField("Username", text: $model.session.draft.username)
                    .textFieldStyle(.roundedBorder)
                SecureField("Password", text: $model.session.draft.password)
                    .textFieldStyle(.roundedBorder)

                if let surface = model.session.status.systemSurface {
                    SystemSurfaceView(surface: surface) {
                        model.session.logout()
                    }
                }

                Button {
                    Task { await model.session.signIn() }
                } label: {
                    if case .signingIn = model.session.status {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Attempt Fresh Sign-In (Blocked)")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(SentrixTheme.Palette.accent)

                Button("Clear Local Session Structure") {
                    model.session.logout()
                }
                .buttonStyle(.bordered)
            }
        }
    }
}
