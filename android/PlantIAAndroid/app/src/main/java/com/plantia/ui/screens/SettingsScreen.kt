package com.plantia.ui.screens

import androidx.compose.ui.res.stringResource
import com.plantia.R
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.plantia.api.PlantIAClient
import com.plantia.data.ServerPreferences
import com.plantia.data.ThemeMode
import com.plantia.ui.components.ErrorBanner
import com.plantia.ui.components.PlantTopBar
import com.plantia.util.userMessage
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    themeMode: ThemeMode = ThemeMode.SYSTEM,
    onThemeModeChange: (ThemeMode) -> Unit = {},
    onOpenAbout: () -> Unit,
) {
    val context = LocalContext.current
    val prefs = remember { ServerPreferences(context) }
    val scope = rememberCoroutineScope()

    val locales = mapOf("" to "Auto", "pt-BR" to "Português (Brasil)", "en" to "English",
        "es" to "Español", "fr" to "Français", "de" to "Deutsch", "it" to "Italiano",
        "hi" to "हिन्दी", "id" to "Bahasa Indonesia", "ar" to "العربية", "ja" to "日本語",
        "ko" to "한국어", "zh-Hans" to "简体中文")
    var languagesOpen by remember { mutableStateOf(false) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var signedIn by remember { mutableStateOf(PlantIAClient.accountScope(context) != null) }
    var serverUrl by remember { mutableStateOf(prefs.baseUrl) }
    var testing by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = { PlantTopBar(title = stringResource(R.string.ui_ajustes)) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(stringResource(R.string.ui_conexion_lan), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.ui_introduce_la_url_de_tu_servidor_plantia_ip_y_puerto),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = serverUrl,
                onValueChange = { serverUrl = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.ui_url_del_servidor)) },
                placeholder = { Text("http://192.168.1.96:8000/") },
                singleLine = true,
                supportingText = {
                    Text(stringResource(R.string.ui_ejemplo_http_192_168_1_96_8000), fontFamily = FontFamily.Monospace)
                },
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Button(
                    onClick = {
                        saving = true
                        error = null
                        result = null
                        scope.launch {
                            try {
                                val normalized = ServerPreferences.normalizeBaseUrl(serverUrl)
                                if (prefs.baseUrl != normalized) {
                                    PlantIAClient.setSession(context, null)
                                    signedIn = false
                                }
                                prefs.baseUrl = normalized
                                serverUrl = normalized
                                PlantIAClient.invalidate()
                                result = context.getString(R.string.native_servidor_guardado)
                            } catch (e: Exception) {
                                error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_guardar))
                            } finally {
                                saving = false
                            }
                        }
                    },
                    enabled = !saving && !testing,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(if (saving) R.string.planet_saving else R.string.planet_save_url))
                }

                Button(
                    onClick = {
                        testing = true
                        error = null
                        result = null
                        scope.launch {
                            try {
                                val normalized = ServerPreferences.normalizeBaseUrl(serverUrl)
                                if (prefs.baseUrl != normalized) {
                                    PlantIAClient.setSession(context, null)
                                    signedIn = false
                                }
                                prefs.baseUrl = normalized
                                PlantIAClient.invalidate()
                                serverUrl = normalized
                                val resp = PlantIAClient.api(context).listar(page = 1, pageSize = 1)
                                result = context.getString(R.string.native_conectado_count_planta_s).replace("{count}", resp.total.toString())
                            } catch (e: Exception) {
                                error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_conectar))
                            } finally {
                                testing = false
                            }
                        }
                    },
                    enabled = !saving && !testing,
                    modifier = Modifier.weight(1f),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (testing) {
                            CircularProgressIndicator(
                                strokeWidth = 2.dp,
                                modifier = Modifier
                                    .padding(end = 8.dp)
                                    .size(18.dp),
                            )
                        }
                        Text(if (testing) "…" else stringResource(R.string.planet_test_server))
                    }
                }
            }

            Box {
                Button(onClick = { languagesOpen = true }) { Text(locales[prefs.language] ?: "Auto") }
                DropdownMenu(expanded = languagesOpen, onDismissRequest = { languagesOpen = false }) {
                    locales.forEach { (tag, name) ->
                        DropdownMenuItem(text = { Text(name) }, onClick = {
                            prefs.language = tag
                            languagesOpen = false
                            (context as? android.app.Activity)?.recreate()
                        })
                    }
                }
            }
            if (!signedIn) {
                OutlinedTextField(value = email, onValueChange = { email = it }, singleLine = true,
                    label = { Text(stringResource(R.string.ui_correo_electronico)) }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = password, onValueChange = { password = it }, singleLine = true,
                    label = { Text(stringResource(R.string.ui_contrasena)) }, visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth())
            }
            Button(
                enabled = !saving && !testing && (signedIn || email.isNotBlank() && password.isNotBlank()),
                onClick = {
                    saving = true
                    error = null
                    result = null
                    scope.launch {
                        try {
                            if (signedIn) {
                                PlantIAClient.api(context).logout()
                                PlantIAClient.setSession(context, null)
                                signedIn = false
                            } else {
                                val url = ServerPreferences.normalizeBaseUrl(serverUrl)
                                require(url.startsWith("https://")) { context.getString(R.string.native_usa_la_url_https_de_planet_ia) }
                                prefs.baseUrl = url
                                PlantIAClient.setSession(context, null)
                                val session = PlantIAClient.api(context).login(email.trim(), password)
                                PlantIAClient.setSession(context, session)
                                signedIn = true
                                result = context.getString(R.string.native_sesion_iniciada)
                            }
                        } catch (e: Exception) {
                            error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_cambiar_la_sesion))
                        } finally {
                            password = ""
                            saving = false
                        }
                    }
                },
            ) { Text(stringResource(if (signedIn) R.string.planet_sign_out else R.string.planet_sign_in)) }
            if (!signedIn) Text(stringResource(R.string.ui_crea_o_recupera_tu_cuenta_desde_la_version_web))

            if (result != null) {
                Text(result!!, color = MaterialTheme.colorScheme.primary)
            }
            if (error != null) {
                ErrorBanner(message = error!!)
            }

            Text(stringResource(R.string.ui_apariencia), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.ui_elige_el_tema_de_la_app_sistema_sigue_la_configuraci),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectableGroup()
                        .padding(8.dp),
                ) {
                    ThemeMode.entries.forEach { mode ->
                        val label = when (mode) {
                            ThemeMode.SYSTEM -> stringResource(R.string.planet_system)
                            ThemeMode.LIGHT -> stringResource(R.string.planet_light)
                            ThemeMode.DARK -> stringResource(R.string.planet_dark)
                        }
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .selectable(
                                    selected = themeMode == mode,
                                    onClick = { onThemeModeChange(mode) },
                                    role = Role.RadioButton,
                                )
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(
                                selected = themeMode == mode,
                                onClick = null,
                            )
                            Text(label, modifier = Modifier.padding(start = 8.dp))
                        }
                    }
                }
            }

            OutlinedCard(
                onClick = onOpenAbout,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        androidx.compose.material3.Icon(Icons.Default.Info, contentDescription = null)
                        Column {
                            Text(stringResource(R.string.ui_acerca_de_plantia), style = MaterialTheme.typography.titleMedium)
                            Text(
                                stringResource(R.string.ui_informacion_y_codigo_fuente),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    androidx.compose.material3.Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null)
                }
            }
        }
    }
}
