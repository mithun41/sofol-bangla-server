from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    BonusLogListView,
    RegisterView, 
    UserListView, 
    UserProfileView, 
    UserUpdateView,     
    ActivateUserView,  
    BinaryTreeView,
    WithdrawalListCreateView,
    admin_approve_withdraw,
    admin_withdrawal_list
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
    path('users/<int:pk>/', UserUpdateView.as_view(), name='user-update'), 
    
    # Matching Bonus Testing API
    path('activate-test/<int:user_id>/', ActivateUserView.as_view(), name='activate_test'),
    path('tree/<str:username>/', BinaryTreeView.as_view(), name='tree-view'),
    path('bonus-logs/', BonusLogListView.as_view(), name='bonus-logs'),
    path('withdrawals/', WithdrawalListCreateView.as_view(), name='withdrawal-list-create'),
    path('withdraw-request/', WithdrawalListCreateView.as_view(), name='withdraw-request'),
    path('admin/withdrawals/', admin_withdrawal_list, name='admin-withdrawal-list'),
    path('admin/withdrawals/<int:pk>/handle/', admin_approve_withdraw, name='admin-withdrawal-handle'),
]