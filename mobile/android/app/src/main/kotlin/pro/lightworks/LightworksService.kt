package pro.lightworks

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Android foreground service — keeps Lightworks Pro alive in the background.
 * Displays a persistent notification (required by Android for foreground services).
 * The notification has no tappable UI; the app is driven entirely by voice.
 */
class LightworksService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var consent: ConsentEngine

    override fun onCreate() {
        super.onCreate()
        consent = ConsentEngine(this)
        startForeground(NOTIFICATION_ID, buildNotification())
        scope.launch { consent.speak("Lightworks Pro running in background.") }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_MUTE_GUARD -> scope.launch { handleMuteGuard() }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // MARK: - Mute Guard

    private suspend fun handleMuteGuard() {
        // Distinct haptic pattern for mute confirmation: two short pulses
        vibrate(longArrayOf(0, 80, 60, 80))
        consent.speak("Muted.")
    }

    private fun vibrate(pattern: LongArray) {
        val vibrator = getSystemService(VibratorManager::class.java)?.defaultVibrator
            ?: getSystemService(Vibrator::class.java)
        vibrator?.vibrate(VibrationEffect.createWaveform(pattern, -1))
    }

    // MARK: - Foreground Notification

    private fun buildNotification(): Notification {
        val channelId = "lightworks_pro_service"
        val channel = NotificationChannel(
            channelId,
            "Lightworks Pro",
            NotificationManager.IMPORTANCE_MIN
        ).apply { description = "Voice productivity assistant running" }

        getSystemService(NotificationManager::class.java)
            .createNotificationChannel(channel)

        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("Lightworks Pro")
            .setContentText("Voice assistant active")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()
    }

    companion object {
        const val NOTIFICATION_ID = 1001
        const val ACTION_MUTE_GUARD = "pro.lightworks.MUTE_GUARD"
    }
}
