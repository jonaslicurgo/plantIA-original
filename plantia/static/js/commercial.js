const billingLocale = document.documentElement.lang;
for (const node of document.querySelectorAll("[data-money][data-currency]")) {
    node.textContent = new Intl.NumberFormat(billingLocale, {
        style: "currency", currency: node.dataset.currency,
    }).format(Number(node.dataset.money));
}
for (const node of document.querySelectorAll("time.billing-date")) {
    node.textContent = new Intl.DateTimeFormat(billingLocale, {dateStyle: "medium"}).format(new Date(node.dateTime));
}
for (const node of document.querySelectorAll("[data-percent]")) {
    node.textContent = new Intl.NumberFormat(billingLocale, {
        style: "percent", maximumFractionDigits: 1,
    }).format(Number(node.dataset.percent));
}
