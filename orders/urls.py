from django.urls import path
from .views import OrderCreateView, AdminOrderListView, AdminOrderUpdateView

urlpatterns = [
    path('place-order/', OrderCreateView.as_view(), name='place_order'),
    # অ্যাডমিন রুটস
    path('admin-list/', AdminOrderListView.as_view(), name='admin_order_list'),
    path('admin-update/<int:pk>/', AdminOrderUpdateView.as_view(), name='admin_order_update'),
]