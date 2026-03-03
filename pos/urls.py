from django.urls import path
from .views import POSProductSearch, POSCustomerSearch, POSOrderCreate

urlpatterns = [
    path('search-product/', POSProductSearch.as_view(), name='pos-product-search'),
    path('search-customer/', POSCustomerSearch.as_view(), name='pos-customer-search'),
    path('create-order/', POSOrderCreate.as_view(), name='pos-order-create'),
]