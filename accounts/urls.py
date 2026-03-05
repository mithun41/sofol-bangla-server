from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminDashboardStatsView,
    BonusLogListView,
    MyTokenObtainPairView,
    ProfileUpdateView,
    RegisterView, 
    UserListView, 
    UserProfileView, 
    UserUpdateView,     
    ActivateUserView,  
    BinaryTreeView,
    WithdrawalListCreateView,
    admin_approve_withdraw,
    admin_withdrawal_list,
    LogoutView,          # নতুন যোগ করা হয়েছে
    ChangePasswordView   # নতুন যোগ করা হয়েছে
)

urlpatterns = [
    # --- Authentication & Access ---
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', MyTokenObtainPairView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    
    # --- User Profile & Networking ---
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/update/', ProfileUpdateView.as_view(), name='profile-update'),
    path('tree/<str:username>/', BinaryTreeView.as_view(), name='tree-view'),
    path('bonus-logs/', BonusLogListView.as_view(), name='bonus-logs'),
    
    # --- Financials (User Side) ---
    path('withdrawals/', WithdrawalListCreateView.as_view(), name='withdrawal-list-create'),
    # 'withdraw-request' আর 'withdrawals' যেহেতু একই ভিউ কল করে, একটা রাখলেই হয়।
    
    # --- Admin Control Panel ---
    path('admin/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    path('all-users/', UserListView.as_view(), name='all-users'),
    path('users/<int:pk>/', UserUpdateView.as_view(), name='user-update'), 
    path('activate-test/<int:user_id>/', ActivateUserView.as_view(), name='activate-test'),
    path('admin/withdrawals/', admin_withdrawal_list, name='admin-withdrawal-list'),
    path('admin/withdrawals/<int:pk>/handle/', admin_approve_withdraw, name='admin-withdrawal-handle'),
]