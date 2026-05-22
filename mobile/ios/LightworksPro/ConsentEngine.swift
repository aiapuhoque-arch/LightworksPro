/// Consent FSM — mirrors the Python core logic for the iOS context.
/// Runs on the main actor to keep UI and speech synthesis on the main thread.

import AVFoundation
import Speech

// MARK: - State

enum ConsentState {
    case idle
    case notification
    case query
    case listening
    case confirmed
    case rejected
    case executing
    case completed
}

private let affirmatives: Set<String> = ["yes", "yeah", "ok", "okay", "sure",
                                          "join", "send", "start", "go", "confirm"]
private let negatives: Set<String> = ["no", "nope", "cancel", "stop", "skip", "abort"]

// MARK: - Engine

@MainActor
final class ConsentEngine: NSObject {
    private let synthesiser = AVSpeechSynthesizer()
    private var state: ConsentState = .idle
    private var continuationStore: CheckedContinuation<Bool, Error>?

    private let speechRecogniser = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()

    // MARK: - Public API

    /// Run the full Notification → Query → Consent → Execution loop.
    func request(notification: String, query: String, action: @escaping () async throws -> Void) async throws -> Bool {
        state = .notification
        await speak(notification)

        state = .query
        await speak(query)

        state = .listening
        guard let utterance = try? await listenOnce(timeout: 12) else {
            state = .rejected
            await speak("No response. Cancelling.")
            return false
        }

        let words = utterance.lowercased().split(separator: " ").map(String.init)
        if words.contains(where: { affirmatives.contains($0) }) {
            state = .confirmed
            state = .executing
            try await action()
            state = .completed
            return true
        }

        state = .rejected
        await speak("Understood. Cancelling.")
        return false
    }

    // MARK: - TTS

    func speak(_ text: String) async {
        configureAudioSession()
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = 0.52
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            synthesiser.delegate = SpeechDelegate(onFinish: { continuation.resume() })
            synthesiser.speak(utterance)
        }
    }

    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(
            .playback,
            mode: .spokenAudio,
            options: [.duckOthers]           // audio ducking built into AVAudioSession
        )
        try? session.setActive(true)
    }

    // MARK: - STT

    private func listenOnce(timeout: TimeInterval) async throws -> String? {
        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let request = recognitionRequest else { return nil }
        request.shouldReportPartialResults = false

        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }

        try audioEngine.start()

        return try await withThrowingTaskGroup(of: String?.self) { group in
            group.addTask {
                try await Task.sleep(for: .seconds(timeout))
                return nil
            }
            group.addTask { [weak self] in
                guard let self else { return nil }
                return try await withCheckedThrowingContinuation { continuation in
                    self.recognitionTask = self.speechRecogniser?.recognitionTask(with: request) { result, error in
                        if let result, result.isFinal {
                            continuation.resume(returning: result.bestTranscription.formattedString)
                        } else if let error {
                            continuation.resume(throwing: error)
                        }
                    }
                }
            }
            let result = try await group.next()
            group.cancelAll()
            return result ?? nil
        }
    }
}

// MARK: - Helpers

private final class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    private let onFinish: () -> Void
    init(onFinish: @escaping () -> Void) { self.onFinish = onFinish }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        onFinish()
    }
}
