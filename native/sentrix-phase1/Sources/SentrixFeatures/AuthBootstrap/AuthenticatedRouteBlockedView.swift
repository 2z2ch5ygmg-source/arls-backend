import SentrixCore
import SentrixDesignSystem
import SwiftUI

public struct AuthenticatedRouteBlockedView: View {
    @ObservedObject private var model: Phase1AppModel
    private let target: AuthenticatedNavigationTarget

    public init(model: Phase1AppModel, target: AuthenticatedNavigationTarget) {
        self.model = model
        self.target = target
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
                SystemSurfaceView(
                    surface: SystemSurfaceModel(
                        kind: .blocked,
                        title: "\(target.title) Blocked",
                        message: target.fieldBlockedMessage,
                        footnote: target.unresolvedFootnote
                    )
                )

                Button("Return To Authenticated Home") {
                    model.returnToAuthenticatedHome()
                }
                .buttonStyle(.borderedProminent)
                .tint(SentrixTheme.Palette.accent)
            }
            .padding(SentrixTheme.Spacing.md)
        }
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
        .navigationTitle(target.title)
    }
}
