from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CartSyncView, ProductViewSet, CategoryViewSet, CartViewSet # CartViewSet ইমপোর্ট করিস

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'cart', CartViewSet, basename='cart') # কার্ট রাউট যোগ হলো
router.register(r'', ProductViewSet) # এটি নিচে রাখা ভালো যাতে অন্যান্য রাউট আগে প্রায়োরিটি পায়

urlpatterns = [
    # ১. কাস্টম পাথ সবসময় ওপরে দিবি
    path('sync-cart/', CartSyncView.as_view(), name='sync-cart'),
    
    # ২. রাউটার থাকবে নিচে
    path('', include(router.urls)),
]