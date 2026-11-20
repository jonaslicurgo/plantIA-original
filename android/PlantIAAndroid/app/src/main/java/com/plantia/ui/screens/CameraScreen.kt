package com.plantia.ui.screens

import androidx.compose.ui.res.stringResource
import com.plantia.R
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.plantia.ui.components.PlantTopBar
import com.plantia.util.identifyImageFile
import com.plantia.util.mimeTypeForFile
import com.plantia.util.uriToTempFile
import com.plantia.util.userMessage
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import kotlin.coroutines.resume

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CameraScreen(
    onIdentified: (Int) -> Unit,
    onCancel: () -> Unit,
    refinePlantName: String? = null,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val title = if (refinePlantName.isNullOrBlank()) stringResource(R.string.native_identificar) else stringResource(R.string.native_afinar_identificacion)

    var hasPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasPermission = granted }

    var imageCapture: ImageCapture? by remember { mutableStateOf(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            if (busy) return@launch
            busy = true
            error = null
            try {
                val file = uriToTempFile(context, uri)
                val planta = identifyImageFile(context, file, mimeTypeForFile(file))
                onIdentified(planta.id)
            } catch (e: Exception) {
                error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_identificar))
            } finally {
                busy = false
            }
        }
    }

    fun identifyFile(file: File) {
        if (busy) return
        busy = true
        error = null
        scope.launch {
            try {
                val planta = identifyImageFile(context, file, mimeTypeForFile(file))
                onIdentified(planta.id)
            } catch (e: Exception) {
                error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_identificar))
            } finally {
                busy = false
            }
        }
    }

    LaunchedEffect(Unit) {
        if (!hasPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    Scaffold(
        topBar = { PlantTopBar(title = title, onBack = onCancel) },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (!hasPermission) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        stringResource(R.string.ui_plantia_necesita_acceso_a_la_camara_para_identificar),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Button(
                        onClick = { permissionLauncher.launch(Manifest.permission.CAMERA) },
                        modifier = Modifier.padding(top = 16.dp),
                    ) {
                        Text(stringResource(R.string.ui_conceder_permiso))
                    }
                    OutlinedButton(
                        onClick = { if (!busy) galleryLauncher.launch("image/*") },
                        modifier = Modifier.padding(top = 10.dp),
                    ) {
                        Text(stringResource(R.string.ui_elegir_de_galeria))
                    }
                }
                return@Box
            }

            AndroidView(
                factory = { ctx ->
                    PreviewView(ctx).apply { scaleType = PreviewView.ScaleType.FILL_CENTER }
                },
                modifier = Modifier.fillMaxSize(),
                update = { previewView ->
                    if (imageCapture == null) {
                        scope.launch { imageCapture = bindCamera(context, previewView) }
                    }
                },
            )

            Surface(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 16.dp, start = 16.dp, end = 16.dp),
                shape = RoundedCornerShape(12.dp),
                color = Color.Black.copy(alpha = 0.55f),
            ) {
                Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                    Text(
                        if (refinePlantName.isNullOrBlank()) {
                            stringResource(R.string.native_centra_la_hoja_o_flor_en_el_encuadre_buena_luz_mejor_resultado)
                        } else {
                            stringResource(R.string.native_nueva_foto_para_afinar_planta_compara_el_resultado_con_tu_fich).replace("{planta}", refinePlantName.orEmpty())
                        },
                        color = Color.White,
                        style = MaterialTheme.typography.bodySmall,
                        textAlign = TextAlign.Center,
                    )
                }
            }

            if (busy) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.Black.copy(alpha = 0.55f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        CircularProgressIndicator(color = Color.White)
                        Text(stringResource(R.string.ui_analizando_con_gemini), color = Color.White, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }

            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (error != null) {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.errorContainer,
                    ) {
                        Text(
                            text = error!!,
                            modifier = Modifier.padding(12.dp),
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }

                OutlinedButton(
                    onClick = { if (!busy) galleryLauncher.launch("image/*") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !busy,
                ) {
                    Text(stringResource(R.string.ui_elegir_de_galeria))
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    OutlinedButton(
                        onClick = { if (!busy) onCancel() },
                        modifier = Modifier.weight(1f),
                        enabled = !busy,
                    ) {
                        Text(stringResource(R.string.ui_cancelar))
                    }

                    Button(
                        onClick = {
                            val cap = imageCapture ?: return@Button
                            scope.launch {
                                try {
                                    val file = captureToTempFile(context, cap)
                                    identifyFile(file)
                                } catch (e: Exception) {
                                    error = e.userMessage(context, context.getString(R.string.native_no_se_pudo_capturar))
                                    busy = false
                                }
                            }
                        },
                        modifier = Modifier.weight(1f),
                        enabled = !busy && imageCapture != null,
                    ) {
                        Text(stringResource(R.string.ui_capturar))
                    }
                }
            }
        }
    }
}

private suspend fun bindCamera(context: Context, previewView: PreviewView): ImageCapture {
    val cameraProvider = context.getCameraProvider()
    val preview = Preview.Builder().build().also {
        it.setSurfaceProvider(previewView.surfaceProvider)
    }
    val imageCapture = ImageCapture.Builder()
        .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
        .build()

    cameraProvider.unbindAll()
    cameraProvider.bindToLifecycle(
        context as androidx.lifecycle.LifecycleOwner,
        CameraSelector.DEFAULT_BACK_CAMERA,
        preview,
        imageCapture,
    )
    return imageCapture
}

private suspend fun Context.getCameraProvider(): ProcessCameraProvider =
    suspendCancellableCoroutine { cont ->
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({ cont.resume(future.get()) }, ContextCompat.getMainExecutor(this))
    }

private suspend fun captureToTempFile(context: Context, imageCapture: ImageCapture): File =
    suspendCancellableCoroutine { cont ->
        val file = File.createTempFile("plantia_", ".jpg", context.cacheDir)
        val output = ImageCapture.OutputFileOptions.Builder(file).build()
        imageCapture.takePicture(
            output,
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    cont.resume(file)
                }

                override fun onError(exception: ImageCaptureException) {
                    cont.resumeWith(Result.failure(exception))
                }
            },
        )
    }
