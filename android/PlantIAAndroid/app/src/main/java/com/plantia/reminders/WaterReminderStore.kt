package com.plantia.reminders

import android.content.Context
import com.plantia.data.ServerPreferences
import org.json.JSONObject
import java.util.Calendar

data class WaterReminder(
    val plantId: Int,
    val plantName: String,
    val intervalDays: Int,
    val lastWateredMillis: Long,
    val enabled: Boolean,
    val hourOfDay: Int = 9,
)

class WaterReminderStore(private val context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun get(plantId: Int): WaterReminder? {
        val raw = prefs.getString(key(plantId), null) ?: return null
        return runCatching { decode(raw) }.getOrNull()
    }

    fun save(reminder: WaterReminder) {
        prefs.edit().putString(key(reminder.plantId), encode(reminder)).apply()
    }

    fun delete(plantId: Int) {
        prefs.edit().remove(key(plantId)).apply()
    }

    private val prefix: String
        get() {
            val server = ServerPreferences(context)
            val scope = server.reminderOwner?.takeIf { it.startsWith(server.baseUrl + "#") }
            return if (scope != null) "account_${scope}_"
                else if (server.baseUrl.startsWith("https://")) "signed_out_" else PREFIX
        }

    fun allEnabled(): List<WaterReminder> =
        prefs.all.mapNotNull { (k, v) ->
            if (!k.startsWith(prefix)) return@mapNotNull null
            runCatching { decode(v as String) }.getOrNull()?.takeIf { it.enabled }
        }

    fun dueToday(): List<WaterReminder> =
        allEnabled().filter { isDue(it) }

    fun isDue(reminder: WaterReminder): Boolean {
        val days = NotificationHelper.daysSince(reminder.lastWateredMillis)
        return days >= reminder.intervalDays
    }

    fun markWatered(plantId: Int, plantName: String, millis: Long = System.currentTimeMillis()) {
        val current = get(plantId)
        if (current != null) {
            save(current.copy(lastWateredMillis = millis, plantName = plantName))
        }
    }

    // Replayed completions must not move an existing reminder backward.
    fun syncWatered(plantId: Int, plantName: String, millis: Long, expectedScope: String?) {
        if (expectedScope == null || ServerPreferences(context).reminderOwner != expectedScope) return
        val current = get(plantId) ?: return
        if (millis > current.lastWateredMillis) {
            val updated = current.copy(lastWateredMillis = millis, plantName = plantName)
            save(updated)
            if (!isDue(updated)) NotificationHelper.dismissWaterReminder(context, plantId)
        }
    }

    fun shouldNotifyNow(reminder: WaterReminder): Boolean {
        if (!isDue(reminder)) return false
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        return hour >= reminder.hourOfDay
    }

    private fun key(plantId: Int) = "$prefix$plantId"

    private fun encode(r: WaterReminder): String =
        JSONObject()
            .put("plantId", r.plantId)
            .put("plantName", r.plantName)
            .put("intervalDays", r.intervalDays)
            .put("lastWateredMillis", r.lastWateredMillis)
            .put("enabled", r.enabled)
            .put("hourOfDay", r.hourOfDay)
            .toString()

    private fun decode(raw: String): WaterReminder {
        val o = JSONObject(raw)
        return WaterReminder(
            plantId = o.getInt("plantId"),
            plantName = o.getString("plantName"),
            intervalDays = o.getInt("intervalDays"),
            lastWateredMillis = o.getLong("lastWateredMillis"),
            enabled = o.getBoolean("enabled"),
            hourOfDay = o.optInt("hourOfDay", 9),
        )
    }

    companion object {
        private const val PREFS_NAME = "plantia_water_reminders"
        private const val PREFIX = "plant_"

    }
}
