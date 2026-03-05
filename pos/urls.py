from django.urls import path
from .views import POSProductSearch, POSCustomerSearch, POSOrderCreate

urlpatterns = [
    path('products/search/', POSProductSearch.as_view(), name='pos-product-search'),
    path('customers/search/', POSCustomerSearch.as_view(), name='pos-customer-search'),
    path('order/create/', POSOrderCreate.as_view(), name='pos-order-create'),
]