package com.plantia.util

import android.content.Context
import com.plantia.R
import com.squareup.moshi.JsonClass
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import retrofit2.HttpException
import java.io.IOException

@JsonClass(generateAdapter = false)
data class ApiErrorBody(
    val detail: String? = null,
)

private val errorMoshi = Moshi.Builder()
    .add(KotlinJsonAdapterFactory())
    .build()

private val errorAdapter = errorMoshi.adapter(ApiErrorBody::class.java)

fun Throwable.userMessage(context: Context, default: String): String {
    return when (this) {
        is HttpException -> {
            val raw = response()?.errorBody()?.string()
            if (!raw.isNullOrBlank()) {
                runCatching { errorAdapter.fromJson(raw)?.detail }.getOrNull()
                    ?: default
            } else {
                default
            }
        }
        is IOException -> context.getString(R.string.native_sin_conexion_con_el_servidor_comprueba_la_red_wi_fi)
        else -> default
    }
}
