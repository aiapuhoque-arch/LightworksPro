package pro.lightworks

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.util.Locale

private val AFFIRMATIVES = setOf(
    "yes", "yeah", "ok", "okay", "sure",
    "join", "send", "start", "go", "confirm"
)

/**
 * Consent FSM — Notification → Query → Consent → Execution.
 * Uses Android system TTS (QUEUE_ADD for sequential delivery) and offline SpeechRecognizer.
 *
 * Fixes applied:
 *  1. Wrong intent (ACTION_RECOGNIZE_SPEECH, not getVoiceDetailsIntent)
 *  2. SpeechRecognizer created/destroyed on Dispatchers.Main (Android requirement)
 *  3. AudioFocus acquired and abandoned symmetrically
 *  4. TTS engine has shutdown() for Service.onDestroy()
 *  5. QUEUE_ADD so notification and query play sequentially without cutting off
 *  6. STT error code logged for AT-device mic routing diagnostics
 */
class ConsentEngine(private val context: Context) {

    private val tts = TtsWrapper(context)
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var audioFocusRequest: AudioFocusRequest? = null

    // MARK: - Consent loop

    suspend fun request(
        notification: String,
        query: String,
        action: suspend () -> Unit,
    ): Boolean {
        speak(notification)
        speak(query)

        val utterance = listenOnce(timeoutMs = 12_000) ?: run {
            speak("No response. Cancelling.")
            return false
        }

        val words = utterance.lowercase().split(" ")
        return if (words.any { it in AFFIRMATIVES }) {
            action()
            true
        } else {
            speak("Understood. Cancelling.")
            false
        }
    }

    suspend fun speak(text: String) = tts.speak(text)

    fun shutdown() = tts.shutdown()

    // MARK: - STT

    private suspend fun listenOnce(timeoutMs: Long): String? {
        val result = CompletableDeferred<String?>()

        // Fix 2: SpeechRecognizer must be created on the main thread.
        val recogniser = withContext(Dispatchers.Main) {
            SpeechRecognizer.createSpeechRecognizer(context)
        }

        withContext(Dispatchers.Main) {
            recogniser.setRecognitionListener(object : RecognitionListener {
                override fun onResults(bundle: Bundle?) {
                    val matches = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    result.complete(matches?.firstOrNull())
                    recogniser.destroy()
                }

                override fun onError(code: Int) {
                    // Fix 6: log error code for AT-device mic routing diagnostics.
                    Log.w("ConsentEngine", "STT error code: $code")
                    result.complete(null)
                    recogniser.destroy()
                }

                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onPartialResults(partialResults: Bundle?) {}
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
        }

        requestAudioFocus()

        // Fix 1: ACTION_RECOGNIZE_SPEECH is the correct intent for a recognition session.
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        }

        withContext(Dispatchers.Main) { recogniser.startListening(intent) }

        return try {
            withTimeout(timeoutMs) { result.await() }
        } catch (_: Exception) {
            withContext(Dispatchers.Main) { recogniser.destroy() }
            null
        } finally {
            // Fix 3: abandon audio focus after every listen attempt.
            abandonAudioFocus()
        }
    }

    // MARK: - Audio focus

    private fun requestAudioFocus() {
        val req = AudioFocusRequest
            .Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .build()
        audioManager.requestAudioFocus(req)
        audioFocusRequest = req
    }

    private fun abandonAudioFocus() {
        audioFocusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
        audioFocusRequest = null
    }
}

// MARK: - TTS wrapper

/** Wraps TextToSpeech as a suspend function. */
private class TtsWrapper(context: Context) {
    private val ready = CompletableDeferred<Unit>()
    private val engine = TextToSpeech(context) { status ->
        if (status == TextToSpeech.SUCCESS) ready.complete(Unit)
    }

    suspend fun speak(text: String) {
        ready.await()
        val done = CompletableDeferred<Unit>()
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onDone(utteranceId: String?) { done.complete(Unit) }
            override fun onError(utteranceId: String?) { done.complete(Unit) }
            override fun onStart(utteranceId: String?) {}
        })
        // Fix 5: QUEUE_ADD so sequential speak() calls don't cut each other off.
        engine.speak(text, TextToSpeech.QUEUE_ADD, null, "lw-${System.nanoTime()}")
        done.await()
    }

    // Fix 4: release the TTS service connection when the service stops.
    fun shutdown() = engine.shutdown()
}
