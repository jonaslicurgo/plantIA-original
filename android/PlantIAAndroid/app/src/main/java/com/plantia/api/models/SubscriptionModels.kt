package com.plantia.api.models

data class SubscriptionAllowance(val plan: String, val limit: Int?, val remaining: Int?, val credits: Int = 0, val used: Int = 0,
    val benefits: Map<String, Boolean> = emptyMap(),
)
data class SubscriptionState(val status: String, val cancel_pending: Boolean)
data class SubscriptionSummary(
    val usage: SubscriptionAllowance,
    val subscription: SubscriptionState?,
    val labels: Map<String, String>,
)
