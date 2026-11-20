package com.plantia.api

import com.plantia.api.models.BotanyFavorite
import com.plantia.api.models.BotanyList
import com.plantia.api.models.BotanyProfile
import com.plantia.api.models.PlantaListResponse
import com.plantia.api.models.PlantaResponse
import com.plantia.api.models.PlantaUpdateRequest
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.Headers
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

data class AccountSession(val access_token: String, val account_id: Int)

interface PlantIAApi {
    @FormUrlEncoded
    @POST("api/auth/login")
    suspend fun login(@Field("email") email: String, @Field("password") password: String): AccountSession

    @POST("api/auth/logout")
    suspend fun logout()

    @GET("api/enciclopedia")
    suspend fun encyclopedia(
        @Query("q") query: String,
        @Query("category") category: String,
        @Query("favorite") favorite: Boolean,
        @Query("page") page: Int,
    ): BotanyList

    @GET("api/enciclopedia/{id}")
    suspend fun botanicalProfile(@Path("id") id: Int): BotanyProfile

    @PATCH("api/enciclopedia/{id}/favorito")
    suspend fun botanicalFavorite(@Path("id") id: Int, @Body favorite: BotanyFavorite): BotanyFavorite

    @Multipart
    @POST("api/plantas/identificar")
    suspend fun identificar(
        @Part file: MultipartBody.Part
    ): PlantaResponse

    @GET("api/plantas")
    suspend fun listar(
        @Query("q") q: String = "",
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 24,
        @Query("orden") orden: String = "recientes",
    ): PlantaListResponse

    @GET("api/plantas/{id}")
    suspend fun detalle(@Path("id") id: Int): PlantaResponse

    @PATCH("api/plantas/{id}")
    @Headers("Content-Type: application/json; charset=UTF-8")
    suspend fun actualizar(@Path("id") id: Int, @Body body: PlantaUpdateRequest): PlantaResponse

    @POST("api/plantas/{id}/notas")
    @Headers("Content-Type: application/json; charset=UTF-8")
    suspend fun guardarNotas(@Path("id") id: Int, @Body body: PlantaUpdateRequest): PlantaResponse

    @DELETE("api/plantas/{id}")
    suspend fun eliminar(@Path("id") id: Int)
}

