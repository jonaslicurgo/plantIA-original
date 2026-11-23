package com.plantia.api

import com.plantia.api.models.BotanyFavorite
import com.plantia.api.models.BotanyList
import com.plantia.api.models.BotanyProfile
import com.plantia.api.models.GardenCompletion
import com.plantia.api.models.GardenOverview
import com.plantia.api.models.GardenPlant
import com.plantia.api.models.GardenSpecimen
import com.plantia.api.models.GardenTask
import com.plantia.api.models.PlantHealthEvent
import com.plantia.api.models.PlantHealthHistory
import com.plantia.api.models.PlantaListResponse
import com.plantia.api.models.PlantaResponse
import com.plantia.api.models.PlantaUpdateRequest
import com.plantia.api.models.SubscriptionSummary
import okhttp3.MultipartBody
import okhttp3.RequestBody
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
import retrofit2.http.PartMap
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

    @GET("api/assinatura")
    suspend fun subscriptionSummary(): SubscriptionSummary

    @GET("api/jardim")
    suspend fun garden(
        @Query("location") location: String, @Query("done") done: Boolean,
        @Query("page") page: Int, @Query("agenda_page") agendaPage: Int,
    ): GardenOverview

    @GET("api/jardim/{id}")
    suspend fun gardenPlant(
        @Path("id") id: Int, @Query("page") page: Int,
        @Query("kind") kind: String, @Query("due_on") dueDate: String?,
    ): GardenSpecimen

    @FormUrlEncoded
    @POST("api/jardim/{id}/perfil")
    suspend fun gardenProfile(@Path("id") id: Int, @Field("nickname") nickname: String,
        @Field("location") location: String): GardenPlant

    @FormUrlEncoded
    @POST("api/jardim/{id}/tarefas")
    suspend fun gardenAddTask(@Path("id") id: Int, @Field("kind") kind: String,
        @Field("due_on") dueDate: String): GardenTask

    @POST("api/jardim/{id}/tarefas/{task}/concluir")
    suspend fun gardenCompleteTask(@Path("id") id: Int, @Path("task") task: Int): GardenCompletion

    @FormUrlEncoded
    @POST("api/jardim/{id}/tarefas/{task}/reagendar")
    suspend fun gardenRescheduleTask(@Path("id") id: Int, @Path("task") task: Int,
        @Field("due_on") dueDate: String): GardenTask

    @GET("api/plantas/{id}/saude")
    suspend fun healthHistory(@Path("id") id: Int, @Query("before") before: Int? = null): PlantHealthHistory

    @Multipart
    @POST("api/plantas/{id}/saude/avaliar")
    suspend fun assessHealth(
        @Path("id") id: Int,
        @Part photo: MultipartBody.Part,
        @PartMap fields: Map<String, @JvmSuppressWildcards RequestBody>,
    ): PlantHealthEvent

    @Multipart
    @POST("api/plantas/{id}/saude/acompanhar")
    suspend fun followHealth(
        @Path("id") id: Int,
        @Part("trend") trend: RequestBody,
        @Part("action") action: RequestBody,
        @Part("note") note: RequestBody,
        @Part("confirmed_by_specialist") confirmed: RequestBody,
        @Part photo: MultipartBody.Part?,
    ): PlantHealthEvent

    @FormUrlEncoded
    @POST("api/plantas/{id}/saude/assistente")
    suspend fun askHealth(@Path("id") id: Int, @Field("question") question: String): PlantHealthEvent

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

