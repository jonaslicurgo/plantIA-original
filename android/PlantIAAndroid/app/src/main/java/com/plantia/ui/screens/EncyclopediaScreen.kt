package com.plantia.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.heightIn
import coil.compose.AsyncImage
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
import androidx.compose.material3.TextButton
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
import com.plantia.R
import com.plantia.api.PlantIAClient
import com.plantia.api.models.BotanyFavorite
import com.plantia.api.models.LibraryList
import com.plantia.api.models.LibraryItem
import com.plantia.api.models.BotanyProfile
import com.plantia.ui.components.ErrorBanner
import com.plantia.ui.components.PlantTopBar
import com.plantia.util.userMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

private data class EncyclopediaQuery(val text: String = "", val category: String = "",
                                    val favorite: Boolean = false, val page: Int = 1)

@Composable
fun EncyclopediaScreen(onOpenPlant: (Int) -> Unit, onOpenSpecies: (String) -> Unit) {
    val context = LocalContext.current
    val api = PlantIAClient.api(context)
    var draft by remember { mutableStateOf(EncyclopediaQuery()) }
    var query by remember { mutableStateOf(EncyclopediaQuery()) }
    var retry by remember { mutableStateOf(0) }
    var personal by remember { mutableStateOf(false) }
    var personalLabel by remember { mutableStateOf("") }
    var catalogLabel by remember { mutableStateOf("") }
    var showCategories by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(true) }
    var results by remember { mutableStateOf<LibraryList?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(query, retry, personal) {
        loading = true
        error = null
        try {
            results = if (personal) {
                val old = api.encyclopedia(query.text, query.category, query.favorite, query.page)
                LibraryList(old.total, old.page, old.total_pages, old.categories, old.items.map {
                    LibraryItem(it.id.toString(), it.common_name, it.scientific_name, it.favorite)
                })
            } else {
                api.botanicalLibrary(query.text, query.category, query.favorite, query.page).also {
                    personalLabel = it.personal_label
                    catalogLabel = it.catalog_label
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            results = null
            error = e.userMessage(context, context.getString(R.string.botany_error))
        } finally {
            loading = false
        }
    }
    Scaffold(topBar = { PlantTopBar(title = stringResource(R.string.botany_title)) }) { padding ->
        LazyColumn(
            modifier = Modifier.padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                if (personalLabel.isNotBlank()) TextButton(onClick = {
                    personal = !personal
                    draft = EncyclopediaQuery()
                    query = draft
                }) { Text(if (personal) catalogLabel else personalLabel) }
                OutlinedTextField(
                    value = draft.text,
                    onValueChange = { draft = draft.copy(text = it.take(150)) },
                    label = { Text(stringResource(R.string.botany_search)) },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                OutlinedButton(onClick = { showCategories = true }) {
                    Text(results?.categories?.find { it.key == draft.category }?.label
                        ?: stringResource(R.string.botany_all))
                }
                DropdownMenu(expanded = showCategories, onDismissRequest = { showCategories = false }) {
                    DropdownMenuItem(text = { Text(stringResource(R.string.botany_all)) }, onClick = {
                        draft = draft.copy(category = "")
                        showCategories = false
                    })
                    results?.categories.orEmpty().forEach { category ->
                        DropdownMenuItem(text = { Text(category.label) }, onClick = {
                            draft = draft.copy(category = category.key)
                            showCategories = false
                        })
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = draft.favorite, onCheckedChange = { draft = draft.copy(favorite = it) })
                    Text(stringResource(R.string.botany_favorites))
                }
                Button(onClick = {
                    val next = draft.copy(text = draft.text.trim(), page = 1)
                    if (query == next) retry++ else query = next
                }) { Text(stringResource(R.string.botany_apply)) }
            }
            when {
                loading -> item { Text(stringResource(R.string.botany_loading)) }
                error != null -> item { ErrorBanner(error.orEmpty(), onRetry = { retry++ }) }
                results?.items.isNullOrEmpty() -> item { Text(stringResource(R.string.botany_empty)) }
                else -> {
                    items(results?.items.orEmpty(), key = { it.id }) { plant ->
                        OutlinedButton(onClick = { if (personal) onOpenPlant(plant.id.toInt()) else onOpenSpecies(plant.id) }, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth()) {
                                Text((if (plant.favorite) "★ " else "") + plant.common_name)
                                Text(plant.scientific_name, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                    val totalPages = results?.total_pages ?: 1
                    if (totalPages > 1) item {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            TextButton(enabled = query.page > 1, onClick = { query = query.copy(page = query.page - 1) }) {
                                Text(stringResource(R.string.botany_previous))
                            }
                            Text("${query.page} / $totalPages")
                            TextButton(enabled = query.page < totalPages, onClick = { query = query.copy(page = query.page + 1) }) {
                                Text(stringResource(R.string.botany_next))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun BotanicalProfileScreen(id: String, global: Boolean = false, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    val api = PlantIAClient.api(context)
    var profile by remember(id) { mutableStateOf<BotanyProfile?>(null) }
    var error by remember(id) { mutableStateOf<String?>(null) }
    var retry by remember(id) { mutableStateOf(0) }
    var saving by remember(id) { mutableStateOf(false) }
    LaunchedEffect(id, retry) {
        error = null
        try {
            profile = if (global) api.libraryProfile(id) else api.botanicalProfile(id.toInt())
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.userMessage(context, context.getString(R.string.botany_error))
        }
    }
    Scaffold(topBar = { PlantTopBar(title = stringResource(R.string.botany_title), onBack = onBack) }) { padding ->
        LazyColumn(
            modifier = Modifier.padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            val current = profile
            if (current == null && error == null) item { Text(stringResource(R.string.botany_loading)) }
            if (error != null) item { ErrorBanner(error.orEmpty(), onRetry = { retry++ }) }
            if (current != null) {
                item {
                    current.photo?.let { photo ->
                        AsyncImage(model = PlantIAClient.baseUrl(context) + photo.url.removePrefix("/"),
                            contentDescription = id.replace('-', ' '),
                            modifier = Modifier.fillMaxWidth().heightIn(max = 340.dp))
                        TextButton(onClick = { uri.openUri(photo.source) }) { Text(photo.author) }
                        TextButton(onClick = { uri.openUri(photo.license_url) }) { Text(photo.license) }
                    }
                    Button(enabled = !saving, onClick = {
                        saving = true
                        error = null
                        scope.launch {
                            try {
                                val update = BotanyFavorite(!current.favorite)
                                val result = if (global) api.libraryFavorite(id, update)
                                             else api.botanicalFavorite(id.toInt(), update)
                                profile = current.copy(favorite = result.favorite)
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                error = e.userMessage(context, context.getString(R.string.botany_error))
                            } finally {
                                saving = false
                            }
                        }
                    }) { Text(stringResource(if (current.favorite) R.string.botany_unfavorite else R.string.botany_favorite)) }
                    current.notices.forEach { Text(it, modifier = Modifier.padding(vertical = 4.dp)) }
                }
                items(current.groups, key = { it.key }) { group ->
                    var expanded by remember(id, group.key) { mutableStateOf(group.key == "taxonomy") }
                    OutlinedButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
                        Text(group.title + if (expanded) " −" else " +")
                    }
                    if (expanded) group.items.forEach { fact ->
                        Column(Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
                            Text(fact.label, style = MaterialTheme.typography.titleSmall)
                            Text(fact.value ?: fact.evidence)
                            if (fact.value != null) Text(fact.evidence, style = MaterialTheme.typography.bodySmall)
                            if (fact.source != null) {
                                TextButton(onClick = { uri.openUri(fact.source.url) }) { Text(fact.source.label) }
                            }
                        }
                    }
                }
            }
        }
    }
}
