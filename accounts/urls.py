from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, 
    UserListView, 
    UserProfileView, 
    UserUpdateView,     # নতুন এডিট ভিউ
    ActivateUserView,   # টেস্ট অ্যাক্টিভেশন ভিউ
    BinaryTreeView
)

urlpatterns = [
    # Auth APIs
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # User Profile & Data
    path('profile/', UserProfileView.as_view(), name='profile'),
    
    # Admin Specific APIs
    path('all-users/', UserListView.as_view(), name='all_users'),
    path('users/<int:pk>/', UserUpdateView.as_view(), name='user-update'), # এখান থেকে ইউজার এডিট/একটিভ হবে
    
    # Matching Bonus Testing API
    path('activate-test/<int:user_id>/', ActivateUserView.as_view(), name='activate_test'),
    path('tree/<str:username>/', BinaryTreeView.as_view(), name='tree-view'),
]