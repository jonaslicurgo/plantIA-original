package com.plantia.ui.screens

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.plantia.R
import com.plantia.api.PlantIAClient
import com.plantia.api.models.PlantHealthHistory
import com.plantia.ui.components.ErrorBanner
import com.plantia.ui.components.PlantTopBar
import com.plantia.util.userMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream

private val observations = listOf("leaf_change", "spreading", "insects_seen")
private val moistureStates = listOf("unknown", "dry", "moist", "saturated")
private val trends = listOf("baseline", "improving", "stable", "worsening")
private val actions = listOf("observe", "inspect", "separate", "check_moisture", "specialist")

@Composable
fun PlantHealthScreen(id: Int, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val api = PlantIAClient.api(context)
    val failure = stringResource(R.string.health_unavailable)
    var history by remember(id) { mutableStateOf<PlantHealthHistory?>(null) }
    var error by remember(id) { mutableStateOf<String?>(null) }
    var revision by remember(id) { mutableStateOf(0) }
    var busy by remember(id) { mutableStateOf(false) }
    var assessment by remember(id) { mutableStateOf(true) }
    var upload by remember(id, assessment) { mutableStateOf<Uri?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { upload = it }
    var checks by remember(id) { mutableStateOf(setOf<String>()) }
    var moisture by remember(id) { mutableStateOf("unknown") }
    var trend by remember(id) { mutableStateOf("baseline") }
    var action by remember(id) { mutableStateOf("observe") }
    var note by remember(id) { mutableStateOf("") }

    LaunchedEffect(id, revision) {
        error = null
        try {
            history = api.healthHistory(id)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.userMessage(context, failure)
        }
    }
    val current = history
    fun tr(key: String) = current?.labels?.get("health.$key") ?: ""
    Scaffold(topBar = { PlantTopBar(title = stringResource(R.string.health_title), onBack = onBack) }) { padding ->
        LazyColumn(
            modifier = Modifier.padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (error != null) item { ErrorBanner(error.orEmpty(), onRetry = { revision++ }) }
            if (current != null) {
                item {
                    Text(current.name, style = MaterialTheme.typography.titleLarge)
                    Text(tr("notice"))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { assessment = true }, enabled = !busy && !assessment, modifier = Modifier.weight(1f)) { Text(tr("assess")) }
                        OutlinedButton(onClick = { assessment = false }, enabled = !busy && assessment, modifier = Modifier.weight(1f)) { Text(tr("follow")) }
                    }
                    if (assessment) {
                        observations.forEach { key ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(key in checks, { checks = if (it) checks + key else checks - key })
                                Text(tr(key))
                            }
                        }
                        HealthChoice("moisture", moistureStates, moisture, ::tr) { moisture = it }
                    } else {
                        HealthChoice("trend", trends, trend, ::tr) { trend = it }
                        HealthChoice("action", actions, action, ::tr) { action = it }
                        OutlinedTextField(note, { note = it.take(1000) }, label = { Text(tr("note")) }, modifier = Modifier.fillMaxWidth())
                    }
                    OutlinedButton(onClick = { picker.launch("image/*") }, enabled = !busy) {
                        Text((if (upload != null) "✓ " else "") + tr("photo"))
                    }
                    Button(enabled = !busy && (!assessment || upload != null), onClick = {
                        busy = true
                        error = null
                        scope.launch {
                            try {
                                val photo = upload?.let { prepareUpload(context, it) }
                                if (assessment && photo != null) {
                                    api.assessHealth(id, photo,
                                        ("leaf_change" in checks).toString().toRequestBody(),
                                        ("spreading" in checks).toString().toRequestBody(),
                                        ("insects_seen" in checks).toString().toRequestBody(),
                                        moisture.toRequestBody())
                                } else if (!assessment) {
                                    api.followHealth(id, trend.toRequestBody(), action.toRequestBody(), note.toRequestBody(), photo)
                                }
                                upload = null
                                note = ""
                                revision++
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                error = e.userMessage(context, failure)
                            } finally {
                                busy = false
                            }
                        }
                    }) { Text(tr(if (assessment) "assess" else "save")) }
                    Text(tr("history"), style = MaterialTheme.typography.titleLarge)
                    if (current.events.isEmpty()) Text(tr("empty"))
                }
                items(current.events, key = { it.id }) { event ->
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        if (event.kind == "triage") {
                            Text(tr("status.${event.data["status"]}"), style = MaterialTheme.typography.titleMedium)
                            Text(tr("concern.${event.data["concern"]}"))
                            for ((key, prefix) in listOf("signs" to "sign", "findings" to "finding")) {
                                (event.data[key] as? List<*>)?.filterIsInstance<String>()?.forEach { Text(tr("$prefix.$it")) }
                            }
                            event.actions.forEach { Text(tr("action.$it")) }
                        } else {
                            Text(tr("trend.${event.data["trend"]}"), style = MaterialTheme.typography.titleMedium)
                            Text(tr("action.${event.data["action"]}"))
                            (event.data["note"] as? String)?.takeIf(String::isNotBlank)?.let { Text(it) }
                        }
                        Text(event.date, style = MaterialTheme.typography.bodySmall)
                        if (event.has_photo) {
                            val url = PlantIAClient.baseUrl(context) + "api/plantas/$id/saude/fotos/${event.id}"
                            AsyncImage(PlantIAClient.imageRequest(context, url), tr("photo"), Modifier.fillMaxWidth().heightIn(max = 250.dp))
                        }
                    }
                }
                current.next_before?.let { before ->
                    item {
                        OutlinedButton(enabled = !busy, onClick = {
                            busy = true
                            scope.launch {
                                try {
                                    val older = api.healthHistory(id, before)
                                    history = current.copy(events = current.events + older.events, next_before = older.next_before)
                                } catch (e: CancellationException) {
                                    throw e
                                } catch (e: Exception) {
                                    error = e.userMessage(context, failure)
                                } finally {
                                    busy = false
                                }
                            }
                        }) { Text(tr("older")) }
                    }
                }
            }
        }
    }
}

@Composable
private fun HealthChoice(key: String, values: List<String>, selected: String, tr: (String) -> String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column {
        OutlinedButton(onClick = { expanded = true }) { Text(tr(key) + " · " + tr("$key.$selected")) }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            values.forEach { value ->
                DropdownMenuItem(text = { Text(tr("$key.$value")) }, onClick = {
                    onSelect(value)
                    expanded = false
                })
            }
        }
    }
}

private suspend fun prepareUpload(context: Context, uri: Uri): MultipartBody.Part = withContext(Dispatchers.IO) {
    val mime = context.contentResolver.getType(uri)
    require(mime in setOf("image/jpeg", "image/png", "image/webp"))
    val data = requireNotNull(context.contentResolver.openInputStream(uri)).use { input ->
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            require(output.size() + read <= 2 * 1024 * 1024)
            output.write(buffer, 0, read)
        }
        output.toByteArray()
    }
    MultipartBody.Part.createFormData("photo", "photo", data.toRequestBody(requireNotNull(mime).toMediaType()))
}
