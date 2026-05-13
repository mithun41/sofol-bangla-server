from django.urls import path
from .views import (
    AdminDashboardReportView,
    AdminOrderAnalyticsView,
    AdminOrderDelete,
    OrderCreateView,
    AdminOrderListView,
    AdminOrderUpdateView,
    OrderSalesAnalyticsView,
    UserDashboardReportView,
    UserOrderListView,
)
from .SalesReportView import SalesReportView  # আলাদা file থেকে

urlpatterns = [
    path("place-order/", OrderCreateView.as_view(), name="place_order"),
    path("admin-list/", AdminOrderListView.as_view(), name="admin_order_list"),
    path(
        "admin-update/<int:pk>/",
        AdminOrderUpdateView.as_view(),
        name="admin_order_update",
    ),
    path("my-orders/", UserOrderListView.as_view(), name="user-order-list"),
    path(
        "admin/report-summary/", AdminDashboardReportView.as_view(), name="admin-report"
    ),
    path("user/report-summary/", UserDashboardReportView.as_view(), name="user-report"),
    path(
        "admin/income-analytics/",
        AdminOrderAnalyticsView.as_view(),
        name="admin-income-analytics",
    ),
    path(
        "admin/sales-report/",
        OrderSalesAnalyticsView.as_view(),
        name="admin-sales-report",
    ),
    path(
        "admin/full-sales-report/",
        SalesReportView.as_view(),
        name="admin-full-sales-report",
    ),
    path("admin-delete/<int:pk>/", AdminOrderDelete.as_view()),
]
