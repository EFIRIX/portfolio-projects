// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "LifeOS",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "LifeOS", targets: ["LifeOS"])
    ],
    targets: [
        .executableTarget(
            name: "LifeOS",
            path: "LifeOS",
            linkerSettings: [
                .linkedLibrary("sqlite3")
            ]
        )
    ]
)
