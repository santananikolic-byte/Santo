// swift-tools-version: 5.9

// SILKSTRIKE – Blutturnier
// Diese Datei funktioniert in Swift Playgrounds (iPad/Mac) UND in Xcode.
// Nicht umbenennen, nicht verschieben.

import PackageDescription
import AppleProductTypes

let package = Package(
    name: "Silkstrike",
    platforms: [
        .iOS("17.0")
    ],
    products: [
        .iOSApplication(
            name: "Silkstrike",
            targets: ["AppModule"],
            bundleIdentifier: "com.santo.silkstrike",
            teamIdentifier: "",
            displayVersion: "1.0",
            bundleVersion: "1",
            appIcon: .placeholder(icon: .rocket),
            accentColor: .presetColor(.red),
            supportedDeviceFamilies: [
                .pad,
                .phone
            ],
            supportedInterfaceOrientations: [
                .landscapeRight,
                .landscapeLeft
            ]
        )
    ],
    targets: [
        .executableTarget(
            name: "AppModule",
            path: "."
        )
    ]
)
