"""
accounts/reports/urls.py
এই file টা accounts/urls.py তে include করো:

    from django.urls import path, include
    urlpatterns = [
        ...
        path('reports/', include('accounts.reports.urls')),
    ]
"""

from django.urls import path
from .views import (
    FundReportView,
    FundReceiverReportView,
    MatchingBonusReportView,
    ReferralBonusReportView,
    LeadershipBonusReportView,
    RankRewardReportView,
    WithdrawalReportView,
    ActivationReportView,
    StarLevelReportView,
    MonthlySummaryReportView,
    ReferralChainReportView,
    TopEarnersReportView,
)

urlpatterns = [
    # Fund Reports
    path("funds/", FundReportView.as_view(), name="report-funds"),
    path(
        "fund-receivers/",
        FundReceiverReportView.as_view(),
        name="report-fund-receivers",
    ),
    # Bonus Reports
    path("matching-bonus/", MatchingBonusReportView.as_view(), name="report-matching"),
    path("referral-bonus/", ReferralBonusReportView.as_view(), name="report-referral"),
    path(
        "leadership-bonus/",
        LeadershipBonusReportView.as_view(),
        name="report-leadership",
    ),
    path("rank-reward/", RankRewardReportView.as_view(), name="report-rank-reward"),
    # User Reports
    path("withdrawals/", WithdrawalReportView.as_view(), name="report-withdrawals"),
    path("activations/", ActivationReportView.as_view(), name="report-activations"),
    path("star-levels/", StarLevelReportView.as_view(), name="report-star-levels"),
    path("top-earners/", TopEarnersReportView.as_view(), name="report-top-earners"),
    path(
        "referral-chain/<str:username>/",
        ReferralChainReportView.as_view(),
        name="report-referral-chain",
    ),
    # Summary
    path("monthly/", MonthlySummaryReportView.as_view(), name="report-monthly"),
]
