/// Biometric Gate — requires FaceID or TouchID before reading sensitive emails.

import LocalAuthentication

enum BiometricGateError: Error {
    case denied
    case unavailable(String)
}

struct BiometricGate {
    static func authorise(reason: String = "Authenticate to read sensitive emails") async throws {
        let context = LAContext()
        var error: NSError?

        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            throw BiometricGateError.unavailable(error?.localizedDescription ?? "Biometrics unavailable")
        }

        let success = try await context.evaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            localizedReason: reason
        )

        if !success {
            throw BiometricGateError.denied
        }
    }
}
