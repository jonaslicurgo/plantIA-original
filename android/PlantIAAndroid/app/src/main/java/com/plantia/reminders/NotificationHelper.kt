package com.plantia.reminders

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.plantia.MainActivity
import com.plantia.data.ServerPreferences
import com.plantia.R
import java.util.concurrent.TimeUnit

object NotificationHelper {
    const val CHANNEL_WATER = "plantia_water"
    private const val NOTIFICATION_ID_BASE = 4000

    fun ensureChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        val localized = ServerPreferences(context).localizedContext(context)
        val channel = NotificationChannel(
            CHANNEL_WATER,
            localized.getString(R.string.native_recordatorios_de_riego),
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = localized.getString(R.string.native_avisos_para_regar_tus_plantas)
        }
        manager.createNotificationChannel(channel)
    }

    fun showWaterReminder(context: Context, plantId: Int, plantName: String) {
        ensureChannels(context)
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_OPEN_PLANT_ID, plantId)
        }
        val pending = PendingIntent.getActivity(
            context,
            plantId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val localized = ServerPreferences(context).localizedContext(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_WATER)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(localized.getString(R.string.native_has_regado_planta).replace("{planta}", plantName))
            .setContentText(localized.getString(R.string.native_toca_para_abrir_el_cuaderno_de_la_planta))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID_BASE + plantId, notification)
    }

    fun dismissWaterReminder(context: Context, plantId: Int) {
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID_BASE + plantId)
    }

    fun daysSince(millis: Long): Long =
        TimeUnit.MILLISECONDS.toDays(System.currentTimeMillis() - millis)
}
