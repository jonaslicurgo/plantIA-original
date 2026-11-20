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
import androidx.compose.ui.platform.LocalUriHandler
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
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

private val observations = listOf("leaf_change", "spreading", "insects_seen")
private val conditions = linkedMapOf(
    "moisture" to listOf("unknown", "dry", "moist", "saturated"),
    "watering" to listOf("unknown", "daily", "weekly", "as_needed", "less_often"),
    "lighting" to listOf("unknown", "direct", "indirect", "low"),
    "location" to listOf("unknown", "inside", "outside", "greenhouse"),
    "soil" to listOf("unknown", "well_drained", "compacted", "standing_water"),
    "temperature" to listOf("unknown", "cold", "stable", "hot", "variable"),
)
private val trends = listOf("baseline", "improving", "stable", "worsening")
private val actions = listOf("observe", "inspect", "separate", "check_moisture", "specialist",
    "drain", "review_watering", "review_light", "stable_temperature", "review_soil", "prevention", "retake", "physical_removal")

@Composable
fun PlantHealthScreen(id: Int, onOpenBotany: () -> Unit, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val date = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(context.resources.configuration.locales[0]).withZone(ZoneId.systemDefault())
    val api = PlantIAClient.api(context)
    val failure = stringResource(R.string.health_unavailable)
    var history by remember(id) { mutableStateOf<PlantHealthHistory?>(null) }
    var error by remember(id) { mutableStateOf<String?>(null) }
    var revision by remember(id) { mutableStateOf(0) }
    var busy by remember(id) { mutableStateOf(false) }
    var mode by remember(id) { mutableStateOf("assess") }
    var upload by remember(id, mode) { mutableStateOf<Uri?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { upload = it }
    var checks by remember(id) { mutableStateOf(setOf<String>()) }
    var contextFields by remember(id) { mutableStateOf<Map<String, String>>(emptyMap()) }
    var symptoms by remember(id) { mutableStateOf("") }
    var environment by remember(id) { mutableStateOf("") }
    var confirmed by remember(id) { mutableStateOf("") }
    var question by remember(id) { mutableStateOf("") }
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
                    Text("${tr("usage")} ${current.usage.attempts} / ${current.usage.hourly_limit}")
                    OutlinedButton(onClick = onOpenBotany) { Text(tr("encyclopedia")) }
                    OutlinedButton(onClick = { mode = "assistant" }, enabled = !busy && mode != "assistant") { Text(tr("assistant")) }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { mode = "assess" }, enabled = !busy && mode != "assess", modifier = Modifier.weight(1f)) { Text(tr("assess")) }
                        OutlinedButton(onClick = { mode = "follow" }, enabled = !busy && mode != "follow", modifier = Modifier.weight(1f)) { Text(tr("follow")) }
                    }
                    if (mode == "assess") {
                        observations.forEach { key ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(key in checks, { checks = if (it) checks + key else checks - key })
                                Text(tr(key))
                            }
                        }
                        conditions.forEach { (key, options) ->
                            HealthChoice(key, options, contextFields[key] ?: "unknown", ::tr) {
                                contextFields = contextFields + (key to it)
                            }
                        }
                        OutlinedTextField(symptoms, { symptoms = it.take(300) }, label = { Text(tr("symptoms")) }, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(environment, { environment = it.take(300) }, label = { Text(tr("environment")) }, modifier = Modifier.fillMaxWidth())
                    } else if (mode == "follow") {
                        HealthChoice("trend", trends, trend, ::tr) { trend = it }
                        HealthChoice("action", actions, action, ::tr) { action = it }
                        OutlinedTextField(note, { note = it.take(1000) }, label = { Text(tr("note")) }, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(confirmed, { confirmed = it.take(300) }, label = { Text(tr("confirmed_input")) }, modifier = Modifier.fillMaxWidth())
                    } else {
                        OutlinedTextField(question, { question = it.take(400) }, label = { Text(tr("question")) }, modifier = Modifier.fillMaxWidth())
                    }
                    if (mode != "assistant") OutlinedButton(onClick = { picker.launch("image/*") }, enabled = !busy) {
                        Text((if (upload != null) "✓ " else "") + tr("photo"))
                    }
                    val valid = when (mode) {
                        "assess" -> upload != null
                        "assistant" -> question.isNotBlank()
                        else -> true
                    }
                    Button(enabled = !busy && valid, onClick = {
                        busy = true
                        error = null
                        val submittedMode = mode
                        val submittedPhoto = upload
                        val submittedQuestion = question
                        val submittedTrend = trend
                        val submittedAction = action
                        val submittedNote = note
                        val submittedConfirmation = confirmed
                        val fields = contextFields + observations.associateWith { (it in checks).toString() } +
                            mapOf("symptoms" to symptoms, "environment" to environment)
                        scope.launch {
                            try {
                                val photo = submittedPhoto?.let { prepareUpload(context, it) }
                                when (submittedMode) {
                                    "assess" -> api.assessHealth(id, requireNotNull(photo), fields.mapValues { it.value.toRequestBody() })
                                    "assistant" -> api.askHealth(id, submittedQuestion)
                                    else -> api.followHealth(id, submittedTrend.toRequestBody(), submittedAction.toRequestBody(),
                                        submittedNote.toRequestBody(), submittedConfirmation.toRequestBody(), photo)
                                }
                                upload = null
                                note = ""
                                confirmed = ""
                                question = ""
                                revision++
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                error = e.userMessage(context, failure)
                            } finally {
                                busy = false
                            }
                        }
                    }) { Text(tr(when (mode) { "assess" -> "assess"; "assistant" -> "ask"; else -> "save" })) }
                    if (current.comparison.assessments.size == 2 || current.comparison.photos.size == 2) {
                        HealthSection(tr("compare")) {
                            if (current.comparison.assessments.size == 2) {
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    current.comparison.assessments.forEachIndexed { index, event ->
                                        Column(Modifier.weight(1f)) {
                                            Text(tr(if (index == 0) "previous" else "current"))
                                            Text(tr("status.${event.data["status"]}"))
                                            Text(tr("concern.${event.data["concern"]}"))
                                            (event.data["findings"] as? List<*>)?.forEach { Text(tr("finding.$it")) }
                                        }
                                    }
                                }
                            }
                            if (current.comparison.photos.size == 2) {
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    current.comparison.photos.forEachIndexed { index, event ->
                                        Column(Modifier.weight(1f)) {
                                            Text(tr(if (index == 0) "previous" else "current"))
                                            val url = PlantIAClient.baseUrl(context) + "api/plantas/$id/saude/fotos/${event.id}"
                                            AsyncImage(PlantIAClient.imageRequest(context, url), tr("photo"), Modifier.fillMaxWidth().heightIn(max = 160.dp))
                                        }
                                    }
                                }
                            }
                        }
                    }
                    HealthSection(tr("sources")) {
                        current.sources.forEach { source ->
                            OutlinedButton(onClick = { uriHandler.openUri(source.url) }) { Text(source.name) }
                        }
                    }
                    Text(tr("history"), style = MaterialTheme.typography.titleLarge)
                    if (current.events.isEmpty()) Text(tr("empty"))
                }
                items(current.events, key = { it.id }) { event ->
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        if (event.kind == "triage") {
                            Text(tr("status.${event.data["status"]}"), style = MaterialTheme.typography.titleMedium)
                            Text(tr("concern.${event.data["concern"]}"))
                            for ((key, prefix, label) in listOf(Triple("signs", "sign", "signs"), Triple("findings", "finding", "causes"))) {
                                val values = event.data[key] as? List<*>
                                if (!values.isNullOrEmpty()) HealthSection(tr(label)) { values.forEach { Text(tr("$prefix.$it")) } }
                            }
                            HealthSection(tr("recovery"), initiallyOpen = true) {
                                event.actions.forEach { Text(tr("action.$it")) }
                                event.review_at?.let { Text(tr("review") + " " + date.format(Instant.ofEpochSecond(it))) }
                            }
                        } else if (event.kind == "assistant") {
                            Text(tr("assistant"), style = MaterialTheme.typography.titleMedium)
                            Text(event.data["question"] as? String ?: "")
                            Text(tr("assistant.${event.data["status"]}"))
                            event.actions.forEach { Text(tr("action.$it")) }
                        } else {
                            Text(tr("trend.${event.data["trend"]}"), style = MaterialTheme.typography.titleMedium)
                            Text(tr("action.${event.data["action"]}"))
                            (event.data["confirmed_by_specialist"] as? String)?.takeIf(String::isNotBlank)?.let { Text(tr("confirmed_label") + " · " + it) }
                            (event.data["note"] as? String)?.takeIf(String::isNotBlank)?.let { Text(it) }
                        }
                        Text(date.format(Instant.parse(event.date)), style = MaterialTheme.typography.bodySmall)
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
private fun HealthSection(title: String, initiallyOpen: Boolean = false, content: @Composable () -> Unit) {
    var expanded by remember { mutableStateOf(initiallyOpen) }
    Column {
        OutlinedButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
            Text(title + if (expanded) " −" else " +")
        }
        if (expanded) content()
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
