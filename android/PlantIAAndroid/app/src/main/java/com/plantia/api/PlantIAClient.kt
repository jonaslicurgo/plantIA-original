package com.plantia.api

import android.content.Context
import com.plantia.data.ServerPreferences
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import coil.request.CachePolicy
import coil.request.ImageRequest
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

object PlantIAClient {
    private data class BoundSession(val url: String, val value: AccountSession)
    @Volatile private var session: BoundSession? = null

    fun setSession(context: Context, value: AccountSession?) {
        val url = baseUrl(context)
        session = value?.let { BoundSession(url, it) }
        ServerPreferences(context).reminderOwner = value?.let { "$url#${it.account_id}" }
        val notifications = context.getSystemService(android.app.NotificationManager::class.java)
        notifications?.cancelAll()
    }

    fun accountScope(context: Context): String? =
        session?.takeIf { it.url == baseUrl(context) }?.let { "${it.url}#${it.value.account_id}" }

    fun imageRequest(context: Context, url: String): ImageRequest {
        val builder = ImageRequest.Builder(context).data(url)
            .diskCachePolicy(CachePolicy.DISABLED)
            .memoryCachePolicy(CachePolicy.DISABLED)
        session?.takeIf { url.startsWith(it.url + "uploads/") || url.startsWith(it.url + "api/plantas/") }?.let {
            builder.addHeader("Authorization", "Bearer ${it.value.access_token}")
        }
        return builder.build()
    }

    private val moshi: Moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val okHttp: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val request = chain.request()
            val builder = request.newBuilder()
            val current = session
            val base = current?.url?.toHttpUrlOrNull()
            if (current != null && base != null && request.url.isHttps && request.url.host == base.host &&
                request.url.port == base.port && request.url.encodedPath.startsWith(base.encodedPath) &&
                !request.url.encodedPath.endsWith("/api/auth/login")) {
                builder.header("Authorization", "Bearer ${current.value.access_token}")
            }
            chain.proceed(builder.build())
        }
        .addInterceptor(
            HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            }
        )
        .build()

    @Volatile
    private var cachedBaseUrl: String? = null

    @Volatile
    private var cachedApi: PlantIAApi? = null

    fun baseUrl(context: Context): String = ServerPreferences(context).baseUrl

    fun api(context: Context): PlantIAApi {
        val preferences = ServerPreferences(context)
        val url = preferences.baseUrl
        val current = cachedApi
        if (current != null && cachedBaseUrl == url) return current
        synchronized(this) {
            if (cachedApi != null && cachedBaseUrl == url) return cachedApi!!
            val retrofit = Retrofit.Builder()
                .baseUrl(url)
                .client(okHttp.newBuilder().addInterceptor { chain ->
                    chain.proceed(chain.request().newBuilder()
                        .header("Accept-Language", preferences.languageTag()).build())
                }.build())
                .addConverterFactory(MoshiConverterFactory.create(moshi))
                .build()
            cachedBaseUrl = url
            cachedApi = retrofit.create(PlantIAApi::class.java)
            return cachedApi!!
        }
    }

    fun invalidate() {
        synchronized(this) {
            cachedBaseUrl = null
            cachedApi = null
        }
    }
}
