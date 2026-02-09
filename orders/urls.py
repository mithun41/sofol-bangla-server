from django.urls import path
from .views import AdminDashboardReportView, OrderCreateView, AdminOrderListView, AdminOrderUpdateView, UserDashboardReportView, UserOrderListView

urlpatterns = [
    path('place-order/', OrderCreateView.as_view(), name='place_order'),
    # অ্যাডমিন রুটস
    path('admin-list/', AdminOrderListView.as_view(), name='admin_order_list'),
    path('admin-update/<int:pk>/', AdminOrderUpdateView.as_view(), name='admin_order_update'),
    path('my-orders/', UserOrderListView.as_view(), name='user-order-list'),
    path('admin/report-summary/', AdminDashboardReportView.as_view(), name='admin-report'),
    path('user/report-summary/', UserDashboardReportView.as_view(), name='user-report'),
]