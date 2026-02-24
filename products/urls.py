from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CartSyncView, ProductViewSet, CategoryViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'', ProductViewSet) 

urlpatterns = [
    # ১. কাস্টম পাথ সবসময় ওপরে দিবি
    path('sync-cart/', CartSyncView.as_view(), name='sync-cart'),
    
    # ২. রাউটার থাকবে নিচে
    path('', include(router.urls)),
]