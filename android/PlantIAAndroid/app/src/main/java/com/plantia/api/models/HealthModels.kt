package com.plantia.api.models

data class PlantHealthHistory(
    val name: String,
    val events: List<PlantHealthEvent>,
    val next_before: Int?,
    val labels: Map<String, String>,
)

data class PlantHealthEvent(
    val id: Int,
    val date: String,
    val kind: String,
    val has_photo: Boolean,
    val data: Map<String, Any?>,
    val actions: List<String>,
)
