package com.plantia.api.models

data class BotanyList(
    val total: Int,
    val page: Int,
    val total_pages: Int,
    val categories: List<BotanyCategory>,
    val items: List<BotanyListItem>,
)

data class BotanyCategory(val key: String, val label: String)
data class BotanyListItem(val id: Int, val common_name: String, val scientific_name: String, val favorite: Boolean)
data class BotanyFavorite(val favorite: Boolean)
data class BotanyProfile(
    val id: Int,
    val favorite: Boolean,
    val notices: List<String>,
    val groups: List<BotanyGroup>,
)

data class BotanyGroup(val key: String, val title: String, val items: List<BotanyFact>)
data class BotanyFact(val key: String, val label: String, val value: String?, val evidence: String, val source: BotanySource?)
data class BotanySource(val label: String, val url: String)
