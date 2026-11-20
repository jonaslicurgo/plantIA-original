package com.plantia.api.models

data class PlantHealthHistory(
    val name: String,
    val events: List<PlantHealthEvent>,
    val next_before: Int?,
    val usage: PlantHealthUsage,
    val comparison: PlantHealthComparison,
    val sources: List<PlantHealthSource>,
    val labels: Map<String, String>,
)

data class PlantHealthEvent(
    val id: Int,
    val date: String,
    val kind: String,
    val has_photo: Boolean,
    val data: Map<String, Any?>,
    val actions: List<String>,
    val review_at: Long? = null,
)


data class PlantHealthUsage(val attempts: Int, val hourly_limit: Int)
data class PlantHealthComparison(val assessments: List<PlantHealthEvent>, val photos: List<PlantHealthEvent>)
data class PlantHealthSource(val name: String, val url: String)
