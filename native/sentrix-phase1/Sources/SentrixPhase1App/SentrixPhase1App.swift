import SentrixFeatures
import SwiftUI

@main
struct SentrixPhase1App: App {
    @StateObject private var model: Phase1AppModel

    init() {
        _model = StateObject(wrappedValue: Phase1CompositionRoot.makeAppModel())
    }

    var body: some Scene {
        WindowGroup {
            Phase1RootView(model: model)
        }
    }
}
