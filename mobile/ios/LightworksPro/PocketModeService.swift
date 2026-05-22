/// Pocket Mode — allows the user to join meetings and hear email summaries via
/// a Bluetooth headset while the phone is in their pocket (screen off).
/// Runs as a background audio session so iOS doesn't suspend the app.

import AVFoundation
import UIKit

final class PocketModeService {

    private let consent: ConsentEngine
    private var isActive = false

    init(consent: ConsentEngine) {
        self.consent = consent
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    // MARK: - Activation

    func activate() {
        guard !isActive else { return }
        isActive = true
        configureForBackground()
    }

    func deactivate() {
        isActive = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: - Headset detection

    @objc private func handleRouteChange(notification: Notification) {
        guard let reason = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let changeReason = AVAudioSession.RouteChangeReason(rawValue: reason) else { return }

        switch changeReason {
        case .newDeviceAvailable:
            let outputs = AVAudioSession.sharedInstance().currentRoute.outputs
            if outputs.contains(where: { $0.portType == .bluetoothHFP || $0.portType == .headphones }) {
                Task { @MainActor in
                    await consent.speak("Bluetooth headset connected. Pocket mode ready.")
                }
            }
        case .oldDeviceUnavailable:
            Task { @MainActor in
                await consent.speak("Headset disconnected.")
            }
        default:
            break
        }
    }

    // MARK: - Background audio

    private func configureForBackground() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(
            .playAndRecord,
            mode: .spokenAudio,
            options: [.allowBluetooth, .duckOthers, .defaultToSpeaker]
        )
        try? session.setActive(true)
    }
}
