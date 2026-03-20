import Foundation

public struct PushRegisteredDevice: Equatable, Sendable, Identifiable {
    public let id: Int
    public let token: String
    public let appBundle: String
    public let active: Bool
    public let selectedForSend: Bool
    public let updatedAt: String
    public let lastSeenAt: String

    public init(
        id: Int,
        token: String,
        appBundle: String,
        active: Bool,
        selectedForSend: Bool,
        updatedAt: String,
        lastSeenAt: String
    ) {
        self.id = id
        self.token = token
        self.appBundle = appBundle
        self.active = active
        self.selectedForSend = selectedForSend
        self.updatedAt = updatedAt
        self.lastSeenAt = lastSeenAt
    }
}

public struct PushAttemptResult: Equatable, Sendable, Identifiable {
    public var id: String { "\(endpoint):\(statusCode)" }
    public let endpoint: String
    public let statusCode: Int
    public let ok: Bool
    public let reasonCode: String
    public let reason: String

    public init(
        endpoint: String,
        statusCode: Int,
        ok: Bool,
        reasonCode: String,
        reason: String
    ) {
        self.endpoint = endpoint
        self.statusCode = statusCode
        self.ok = ok
        self.reasonCode = reasonCode
        self.reason = reason
    }
}

public struct PushDeliveryResult: Equatable, Sendable, Identifiable {
    public let id: String
    public let user: String
    public let pushDeviceID: Int
    public let token: String
    public let ok: Bool
    public let attempts: [PushAttemptResult]

    public init(
        user: String,
        pushDeviceID: Int,
        token: String,
        ok: Bool,
        attempts: [PushAttemptResult]
    ) {
        self.id = "\(user):\(pushDeviceID)"
        self.user = user
        self.pushDeviceID = pushDeviceID
        self.token = token
        self.ok = ok
        self.attempts = attempts
    }
}

public struct PushAPNSConfiguration: Equatable, Sendable {
    public let enabled: Bool
    public let topic: String
    public let useSandbox: Bool
    public let endpointMode: String
    public let endpoints: [String]
    public let runtimeIsAzure: Bool

    public init(
        enabled: Bool,
        topic: String,
        useSandbox: Bool,
        endpointMode: String,
        endpoints: [String],
        runtimeIsAzure: Bool
    ) {
        self.enabled = enabled
        self.topic = topic
        self.useSandbox = useSandbox
        self.endpointMode = endpointMode
        self.endpoints = endpoints
        self.runtimeIsAzure = runtimeIsAzure
    }
}

public struct PushTestSummary: Equatable, Sendable {
    public let apnsEnabled: Bool
    public let targets: Int
    public let success: Int
    public let failed: Int
    public let results: [PushDeliveryResult]

    public init(
        apnsEnabled: Bool,
        targets: Int,
        success: Int,
        failed: Int,
        results: [PushDeliveryResult]
    ) {
        self.apnsEnabled = apnsEnabled
        self.targets = targets
        self.success = success
        self.failed = failed
        self.results = results
    }
}

public struct PushTestResult: Equatable, Sendable {
    public let title: String
    public let body: String
    public let registeredIOSDevices: Int
    public let activeIOSDevices: Int
    public let selectedIOSTargets: Int
    public let registeredDevices: [PushRegisteredDevice]
    public let apnsConfiguration: PushAPNSConfiguration
    public let pushResult: PushTestSummary

    public init(
        title: String,
        body: String,
        registeredIOSDevices: Int,
        activeIOSDevices: Int,
        selectedIOSTargets: Int,
        registeredDevices: [PushRegisteredDevice],
        apnsConfiguration: PushAPNSConfiguration,
        pushResult: PushTestSummary
    ) {
        self.title = title
        self.body = body
        self.registeredIOSDevices = registeredIOSDevices
        self.activeIOSDevices = activeIOSDevices
        self.selectedIOSTargets = selectedIOSTargets
        self.registeredDevices = registeredDevices
        self.apnsConfiguration = apnsConfiguration
        self.pushResult = pushResult
    }
}
