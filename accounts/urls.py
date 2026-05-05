from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from .views import * # নিশ্চিত করো তোমার views.py এ সব ক্লাস ইমপোর্ট করা আছে


urlpatterns = [
    # Auth
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", MyTokenObtainPairView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Password Recovery
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    # Profile & Network
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("profile/update/", ProfileUpdateView.as_view(), name="profile-update"),
    path("my-network/", MyNetworkView.as_view(), name="my-network"),
    path("tree/<str:username>/", BinaryTreeView.as_view(), name="tree-view"),
    path("bonus-logs/", BonusLogListView.as_view(), name="bonus-logs"),
    # Financials
    path(
        "withdrawals/",
        WithdrawalListCreateView.as_view(),
        name="withdrawal-list-create",
    ),
    # Admin
    path("admin/stats/", AdminDashboardStatsView.as_view(), name="admin-stats"),
    path("all-users/", UserListView.as_view(), name="all-users"),
    path("users/<int:pk>/", UserUpdateView.as_view(), name="user-update"),
    path(
        "activate-test/<int:user_id>/", ActivateUserView.as_view(), name="activate-test"
    ),
    path("admin/withdrawals/", admin_withdrawal_list, name="admin-withdrawal-list"),
    path(
        "admin/withdrawals/<int:pk>/handle/",
        admin_approve_withdraw,
        name="admin-withdrawal-handle",
    ),
    path("reports/", include("accounts.reports.urls")),
]
