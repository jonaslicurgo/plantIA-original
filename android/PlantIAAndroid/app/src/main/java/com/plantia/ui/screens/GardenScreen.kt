package com.plantia.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.plantia.R
import com.plantia.api.PlantIAClient
import com.plantia.api.models.GardenOverview
import com.plantia.api.models.GardenSpecimen
import com.plantia.reminders.WaterReminderStore
import com.plantia.ui.components.ErrorBanner
import com.plantia.ui.components.PlantTopBar
import com.plantia.util.userMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@Composable
fun GardenScreen(onPlant: (Int) -> Unit) {
    val context = LocalContext.current
    val scope = PlantIAClient.accountScope(context)
    val failure = stringResource(R.string.garden_error)
    val formatter = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(context.resources.configuration.locales[0])
    var overview by remember(scope) { mutableStateOf<GardenOverview?>(null) }
    var error by remember(scope) { mutableStateOf<String?>(null) }
    var location by remember(scope) { mutableStateOf("") }
    var done by remember(scope) { mutableStateOf(false) }
    var page by remember(scope) { mutableStateOf(1) }
    var agendaPage by remember(scope) { mutableStateOf(1) }
    var revision by remember(scope) { mutableStateOf(0) }

    LaunchedEffect(scope, location, done, page, agendaPage, revision) {
        error = null
        try {
            val result = PlantIAClient.api(context).garden(location, done, page, agendaPage)
            if (PlantIAClient.accountScope(context) != scope) return@LaunchedEffect
            val reminders = WaterReminderStore(context)
            result.plants.forEach { plant ->
                result.last_watered[plant.id.toString()]?.let {
                    reminders.syncWatered(plant.id, plant.name, Instant.parse(it).toEpochMilli(), scope)
                }
            }
            overview = result
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.userMessage(context, failure)
        }
    }
    val result = overview
    fun tr(key: String) = result?.labels?.get("garden.$key").orEmpty()
    Scaffold(topBar = { PlantTopBar(title = stringResource(R.string.garden_title)) }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (error != null) item { ErrorBanner(error.orEmpty(), onRetry = { revision++ }) }
            if (result == null && error == null) item { CircularProgressIndicator() }
            if (result != null) {
                item {
                    Text(tr("location"))
                    GardenChoice(location.ifEmpty { tr("all") }, listOf("" to tr("all")) + result.locations.map { it to it }) {
                        location = it
                        page = 1
                        agendaPage = 1
                    }
                    Text(tr("plants"), style = MaterialTheme.typography.titleLarge)
                    if (result.plants.isEmpty()) Text(tr("no_plants"))
                }
                items(result.plants, key = { it.id }) {
                    OutlinedButton(onClick = { onPlant(it.id) }, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.fillMaxWidth()) {
                            Text(it.nickname.ifEmpty { it.name })
                            Text(it.location.ifEmpty { tr("unassigned") })
                        }
                    }
                }
                item {
                    GardenPages(page, result.more, ::tr) { page = it }
                    Text(tr("agenda"), style = MaterialTheme.typography.titleLarge)
                    GardenChoice(tr(if (done) "done" else "pending"), listOf("false" to tr("pending"), "true" to tr("done"))) {
                        done = it == "true"
                        agendaPage = 1
                    }
                    if (result.tasks.isEmpty()) Text(tr("no_tasks"))
                }
                items(result.tasks, key = { "agenda-${it.id}" }) {
                    TextButton(onClick = { onPlant(it.plant_id) }) {
                        Text("${tr("kind.${it.kind}")} · ${it.name} · ${formatter.format(LocalDate.parse(it.due_on))}")
                    }
                }
                item { GardenPages(agendaPage, result.agenda_more, ::tr) { agendaPage = it } }
            }
        }
    }
}

@Composable
fun GardenPlantScreen(
    id: Int,
    reviewDate: String?,
    onBack: () -> Unit,
    onRecord: () -> Unit,
    onHealth: () -> Unit,
    onBotany: () -> Unit,
) {
    val context = LocalContext.current
    val account = PlantIAClient.accountScope(context)
    val api = PlantIAClient.api(context)
    val coroutine = rememberCoroutineScope()
    val reminders = remember(context) { WaterReminderStore(context) }
    val failure = stringResource(R.string.garden_error)
    val formatter = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(context.resources.configuration.locales[0])
    var data by remember(id, account) { mutableStateOf<GardenSpecimen?>(null) }
    var error by remember(id, account) { mutableStateOf<String?>(null) }
    var page by remember(id, account) { mutableStateOf(1) }
    var revision by remember(id, account) { mutableStateOf(0) }
    var busy by remember(id, account) { mutableStateOf(false) }
    var nickname by remember(id, account) { mutableStateOf("") }
    var location by remember(id, account) { mutableStateOf("") }
    var kind by remember(id, reviewDate, account) { mutableStateOf(if (reviewDate == null) "water" else "review") }
    var due by remember(id, reviewDate, account) { mutableStateOf(reviewDate?.let(LocalDate::parse)) }
    var editingDateFor by remember(id, account) { mutableStateOf<Int?>(null) }

    LaunchedEffect(id, account, page, revision) {
        error = null
        try {
            val result = api.gardenPlant(id, page, if (reviewDate == null) "water" else "review", reviewDate)
            if (PlantIAClient.accountScope(context) != account) return@LaunchedEffect
            if (data?.plant != result.plant) {
                nickname = result.plant.nickname
                location = result.plant.location
            }
            result.last_watered?.let { reminders.syncWatered(id, result.plant.name, Instant.parse(it).toEpochMilli(), account) }
            data = result
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.userMessage(context, failure)
        }
    }

    fun save(action: suspend () -> Unit) {
        if (busy) return
        busy = true
        error = null
        coroutine.launch {
            try {
                action()
                revision++
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = e.userMessage(context, failure)
            } finally {
                busy = false
            }
        }
    }

    val result = data
    fun tr(key: String) = result?.labels?.get("garden.$key").orEmpty()
    Scaffold(topBar = { PlantTopBar(title = stringResource(R.string.garden_title), onBack = onBack) }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            if (error != null) item { ErrorBanner(error.orEmpty(), onRetry = { revision++ }) }
            if (result == null && error == null) item { CircularProgressIndicator() }
            if (result != null) {
                item {
                    Text(result.plant.nickname.ifEmpty { result.plant.name }, style = MaterialTheme.typography.titleLarge)
                    if (result.plant.scientific_name.isNotEmpty()) Text(result.plant.scientific_name)
                    TextButton(onClick = onRecord) { Text(stringResource(R.string.planet_detail)) }
                    TextButton(onClick = onHealth) { Text(stringResource(R.string.health_title)) }
                    TextButton(onClick = onBotany) { Text(stringResource(R.string.botany_open)) }
                    OutlinedTextField(nickname, { nickname = it.take(80) }, label = { Text(tr("nickname")) }, enabled = !busy, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(location, { location = it.take(80) }, label = { Text(tr("location")) }, enabled = !busy, modifier = Modifier.fillMaxWidth())
                    Button(onClick = { save { api.gardenProfile(id, nickname, location) } }, enabled = !busy) { Text(tr("save")) }
                    Text(tr("schedule"), style = MaterialTheme.typography.titleMedium)
                    GardenChoice(tr("kind.$kind"), result.kinds.map { it to tr("kind.$it") }, enabled = !busy) { kind = it }
                    OutlinedButton(onClick = { editingDateFor = 0 }, enabled = !busy) { Text(due?.let(formatter::format) ?: tr("date")) }
                    Button(onClick = { val date = due; if (date != null) save { api.gardenAddTask(id, kind, date.toString()) } },
                        enabled = !busy && due != null) { Text(tr("schedule")) }
                    Text(tr("agenda"), style = MaterialTheme.typography.titleLarge)
                    if (result.tasks.isEmpty()) Text(tr("no_tasks"))
                }
                items(result.tasks, key = { it.id }) { task ->
                    Column {
                        Text("${tr("kind.${task.kind}")} · ${formatter.format(LocalDate.parse(task.due_on))}")
                        if (task.completed) {
                            Text(tr("done"))
                        } else {
                            TextButton(enabled = !busy, onClick = {
                                save {
                                    val receipt = api.gardenCompleteTask(id, task.id)
                                    if (receipt.kind == "water") {
                                        reminders.syncWatered(id, result.plant.name, Instant.parse(receipt.completed_at).toEpochMilli(), account)
                                    }
                                }
                            }) { Text(tr("complete")) }
                            TextButton(enabled = !busy, onClick = { editingDateFor = task.id }) { Text(tr("reschedule")) }
                        }
                    }
                }
                item { GardenPages(page, result.more, ::tr) { page = it } }
            }
        }
    }
    editingDateFor?.let { taskId ->
        val initial = if (taskId == 0) due else result?.tasks?.find { it.id == taskId }?.due_on?.let(LocalDate::parse)
        GardenDateDialog(initial, onDismiss = { editingDateFor = null }) { date ->
            editingDateFor = null
            if (taskId == 0) due = date else save { api.gardenRescheduleTask(id, taskId, date.toString()) }
        }
    }
}

@Composable
private fun GardenChoice(label: String, options: List<Pair<String, String>>, enabled: Boolean = true,
                         onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        OutlinedButton(onClick = { open = true }, enabled = enabled) { Text(label) }
        DropdownMenu(open, { open = false }) {
            options.forEach { (value, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onSelect(value) })
            }
        }
    }
}

@Composable
private fun GardenPages(page: Int, more: Boolean, tr: (String) -> String, onPage: (Int) -> Unit) {
    if (page == 1 && !more) return
    Row {
        if (page > 1) TextButton(onClick = { onPage(page - 1) }) { Text(tr("previous")) }
        if (more) TextButton(onClick = { onPage(page + 1) }) { Text(tr("next")) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GardenDateDialog(initial: LocalDate?, onDismiss: () -> Unit, onDate: (LocalDate) -> Unit) {
    val initialMillis = initial?.takeIf { it.year in 1900..2100 }?.atStartOfDay(ZoneOffset.UTC)?.toInstant()?.toEpochMilli()
    val state = rememberDatePickerState(initialSelectedDateMillis = initialMillis)
    DatePickerDialog(onDismissRequest = onDismiss, confirmButton = {
        TextButton(enabled = state.selectedDateMillis != null, onClick = {
            state.selectedDateMillis?.let { onDate(Instant.ofEpochMilli(it).atOffset(ZoneOffset.UTC).toLocalDate()) }
        }) { Text(stringResource(android.R.string.ok)) }
    }, dismissButton = {
        TextButton(onClick = onDismiss) { Text(stringResource(R.string.ui_cancelar)) }
    }) { DatePicker(state) }
}
