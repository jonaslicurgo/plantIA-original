package com.plantia.api.models

data class GardenPlant(
    val id: Int, val name: String, val scientific_name: String, val nickname: String, val location: String,
)
data class GardenTask(
    val id: Int, val plant_id: Int, val name: String, val kind: String, val due_on: String, val completed: Boolean,
)
data class GardenOverview(
    val plants: List<GardenPlant>, val tasks: List<GardenTask>, val locations: List<String>,
    val more: Boolean, val agenda_more: Boolean, val last_watered: Map<String, String>,
    val labels: Map<String, String>,
)
data class GardenSpecimen(
    val plant: GardenPlant, val tasks: List<GardenTask>, val kinds: List<String>, val more: Boolean,
    val selected_kind: String, val suggested_date: String, val last_watered: String?, val labels: Map<String, String>,
)
data class GardenCompletion(val kind: String, val completed_at: String)
