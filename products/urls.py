from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'', ProductViewSet) # এটি /api/products/ এ কাজ করবে

urlpatterns = [
    path('', include(router.urls)),
]