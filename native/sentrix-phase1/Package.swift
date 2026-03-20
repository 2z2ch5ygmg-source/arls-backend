// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "SentrixPhase1",
    defaultLocalization: "en",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "SentrixCore", targets: ["SentrixCore"]),
        .library(name: "SentrixAPI", targets: ["SentrixAPI"]),
        .library(name: "SentrixDesignSystem", targets: ["SentrixDesignSystem"]),
        .library(name: "SentrixFeatures", targets: ["SentrixFeatures"]),
        .executable(name: "SentrixPhase1App", targets: ["SentrixPhase1App"]),
    ],
    targets: [
        .target(
            name: "SentrixCore"
        ),
        .target(
            name: "SentrixAPI",
            dependencies: ["SentrixCore"]
        ),
        .target(
            name: "SentrixDesignSystem",
            dependencies: ["SentrixCore"]
        ),
        .target(
            name: "SentrixFeatures",
            dependencies: ["SentrixCore", "SentrixDesignSystem"]
        ),
        .executableTarget(
            name: "SentrixPhase1App",
            dependencies: ["SentrixFeatures", "SentrixAPI", "SentrixCore"]
        ),
        .testTarget(
            name: "SentrixCoreTests",
            dependencies: ["SentrixCore"]
        ),
        .testTarget(
            name: "SentrixAPITests",
            dependencies: ["SentrixAPI", "SentrixCore"]
        ),
        .testTarget(
            name: "SentrixFeaturesTests",
            dependencies: ["SentrixFeatures", "SentrixCore"]
        ),
    ]
)
