import SwiftUI

@main
struct LifeOSApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var store = LifeOSStore()

    var body: some Scene {
        WindowGroup {
            RootView(store: store)
                .preferredColorScheme(.dark)
                .frame(minWidth: 1240, minHeight: 820)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
    }
}
