package com.plantia.api.models

data class SubscriptionAllowance(val plan: String, val limit: Int, val remaining: Int)
data class SubscriptionState(val status: String, val cancel_pending: Boolean)
data class SubscriptionSummary(
    val usage: SubscriptionAllowance,
    val subscription: SubscriptionState?,
    val labels: Map<String, String>,
)
