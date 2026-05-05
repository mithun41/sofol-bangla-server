"""
accounts/reports/views.py
─────────────────────────
সব Admin Report APIs এক জায়গায়।

Available endpoints:
  GET  admin/reports/funds/                    → Fund Flow Report
  GET  admin/reports/fund-receivers/           → Fund Receiver Report  (?fund_type=referral|matching|leadership|rank_reward)
  GET  admin/reports/matching-bonus/           → Matching Bonus Report
  GET  admin/reports/referral-bonus/           → Referral Bonus Report
  GET  admin/reports/leadership-bonus/         → Leadership Bonus Report (generation wise)
  GET  admin/reports/rank-reward/              → Rank Reward Report
  GET  admin/reports/withdrawals/              → Withdrawal Report
  GET  admin/reports/activations/              → User Activation Report
  GET  admin/reports/star-levels/              → Star Level Distribution Report
  GET  admin/reports/monthly/                  → Monthly Summary Report  (?year=2025)
  GET  admin/reports/referral-chain/<username>/→ Referral Chain Report
  GET  admin/reports/top-earners/              → Top Earners Report
"""

from datetime import datetime
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import TruncMonth, TruncDate
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import BonusLog, FundLog, GlobalFund, User, WithdrawalRequest
from accounts.serializers import BonusLogSerializer, UserListSerializer


# ═══════════════════════════════════════════════════════
# ১. GLOBAL FUND FLOW REPORT
# ═══════════════════════════════════════════════════════
class FundReportView(APIView):
    """
    প্রতিটা fund এর:
    - current balance
    - total inflow (কত ঢুকেছে)
    - total outflow (কত বেরিয়েছে)
    - utilization % (কতটা ব্যবহার হয়েছে)
    """

    permission_classes = [IsAdminUser]

    FUND_LABELS = {
        "referral_fund": "Referral Fund",
        "matching_fund": "Matching Fund",
        "rank_reward_fund": "Rank Reward Fund",
        "tour_fund": "Tour Fund",
        "leadership_fund": "Leadership Fund",
        "company_fund": "Company Fund",
    }

    def get(self, request):
        fund = GlobalFund.objects.first()
        if not fund:
            return Response({"error": "Global Fund not initialized yet."}, status=404)

        # Optional date filter: ?from=2025-01-01&to=2025-12-31
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        report = []
        grand_inflow = Decimal("0")
        grand_outflow = Decimal("0")

        for field, label in self.FUND_LABELS.items():
            qs = FundLog.objects.filter(fund_type=field)
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)

            inflow = qs.filter(transaction_type="inbound").aggregate(t=Sum("amount"))[
                "t"
            ] or Decimal("0")
            outflow = qs.filter(transaction_type="outbound").aggregate(t=Sum("amount"))[
                "t"
            ] or Decimal("0")

            current_balance = Decimal(str(getattr(fund, field, 0) or 0))
            utilization = (
                round(float(outflow) / float(inflow) * 100, 2) if inflow else 0.0
            )

            report.append(
                {
                    "fund_key": field,
                    "fund_label": label,
                    "current_balance": float(current_balance),
                    "total_inflow": float(inflow),
                    "total_outflow": float(outflow),
                    "utilization_pct": utilization,
                }
            )

            grand_inflow += inflow
            grand_outflow += outflow

        return Response(
            {
                "filters": {"from": date_from, "to": date_to},
                "grand_summary": {
                    "total_inflow": float(grand_inflow),
                    "total_outflow": float(grand_outflow),
                    "net_balance": float(grand_inflow - grand_outflow),
                },
                "funds": report,
            }
        )


# ═══════════════════════════════════════════════════════
# ২. FUND RECEIVER REPORT
# কোন fund থেকে কোন user কত পেয়েছে
# ═══════════════════════════════════════════════════════
class FundReceiverReportView(APIView):
    """
    Query param: ?fund_type=referral | matching | leadership | rank_reward
    সব fund type একসাথেও দেখা যাবে (fund_type না দিলে)
    """

    permission_classes = [IsAdminUser]

    REASON_MAP = {
        "referral": "Referral Bonus",
        "matching": "Matching Bonus",
        "leadership": "Leadership Bonus",
        "rank_reward": "Rank Reward",
    }

    def get(self, request):
        fund_type = request.query_params.get("fund_type")
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        qs = BonusLog.objects.all()

        if fund_type:
            keyword = self.REASON_MAP.get(fund_type)
            if not keyword:
                return Response(
                    {
                        "error": f"Invalid fund_type. Choose from: {list(self.REASON_MAP.keys())}"
                    },
                    status=400,
                )
            qs = qs.filter(reason__icontains=keyword)

        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        # Per user summary
        per_user = (
            qs.values("user__username", "user__name", "user__phone", "user__status")
            .annotate(
                total_received=Sum("amount"),
                transaction_count=Count("id"),
                last_received=Max("timestamp"),
            )
            .order_by("-total_received")
        )

        # Overall summary
        summary = qs.aggregate(
            grand_total=Sum("amount"),
            total_transactions=Count("id"),
            unique_receivers=Count("user", distinct=True),
        )

        return Response(
            {
                "filters": {"fund_type": fund_type, "from": date_from, "to": date_to},
                "summary": {
                    "grand_total": float(summary["grand_total"] or 0),
                    "total_transactions": summary["total_transactions"],
                    "unique_receivers": summary["unique_receivers"],
                },
                "receivers": list(per_user),
            }
        )


# ═══════════════════════════════════════════════════════
# ৩. MATCHING BONUS REPORT
# ═══════════════════════════════════════════════════════
class MatchingBonusReportView(APIView):
    """
    - Total matching bonus paid
    - Per user breakdown (কতটা pair, কত টাকা)
    - Recent 50 transactions
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        qs = BonusLog.objects.filter(reason__icontains="Matching Bonus")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        summary = qs.aggregate(
            total_paid=Sum("amount"),
            total_transactions=Count("id"),
            avg_per_transaction=Avg("amount"),
            unique_earners=Count("user", distinct=True),
        )

        per_user = (
            qs.values(
                "user__username",
                "user__name",
                "user__phone",
                "user__left_count",
                "user__right_count",
                "user__paid_matches",
            )
            .annotate(
                total_bonus=Sum("amount"),
                transaction_count=Count("id"),
                last_bonus=Max("timestamp"),
            )
            .order_by("-total_bonus")
        )

        # Daily trend
        daily = (
            qs.annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-date")[:30]
        )

        recent = qs.select_related("user").order_by("-timestamp")[:50]

        return Response(
            {
                "filters": {"from": date_from, "to": date_to},
                "summary": {
                    "total_paid": float(summary["total_paid"] or 0),
                    "total_transactions": summary["total_transactions"],
                    "avg_per_transaction": float(summary["avg_per_transaction"] or 0),
                    "unique_earners": summary["unique_earners"],
                },
                "per_user": list(per_user),
                "daily_trend": list(daily),
                "recent_transactions": BonusLogSerializer(recent, many=True).data,
            }
        )


# ═══════════════════════════════════════════════════════
# ৪. REFERRAL BONUS REPORT
# ═══════════════════════════════════════════════════════
class ReferralBonusReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        qs = BonusLog.objects.filter(reason__icontains="Referral Bonus")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        summary = qs.aggregate(
            total_paid=Sum("amount"),
            total_referrals=Count("id"),
            unique_earners=Count("user", distinct=True),
        )

        per_user = (
            qs.values("user__username", "user__name", "user__phone", "user__status")
            .annotate(
                total_bonus=Sum("amount"),
                referrals_converted=Count("id"),  # কতজন referral activate করেছে
                last_bonus=Max("timestamp"),
            )
            .order_by("-total_bonus")
        )

        # কারা কাকে refer করেছে — detail list
        detail = (
            qs.select_related("user")
            .order_by("-timestamp")
            .values("user__username", "user__name", "amount", "reason", "timestamp")[
                :100
            ]
        )

        return Response(
            {
                "filters": {"from": date_from, "to": date_to},
                "summary": {
                    "total_paid": float(summary["total_paid"] or 0),
                    "total_referrals": summary["total_referrals"],
                    "unique_earners": summary["unique_earners"],
                    "avg_per_referral": (
                        float(summary["total_paid"] or 0) / summary["total_referrals"]
                        if summary["total_referrals"]
                        else 0
                    ),
                },
                "per_user": list(per_user),
                "recent_details": list(detail),
            }
        )


# ═══════════════════════════════════════════════════════
# ৫. LEADERSHIP BONUS REPORT (Generation wise)
# ═══════════════════════════════════════════════════════
class LeadershipBonusReportView(APIView):
    """
    Generation 1-5 ভিত্তিক breakdown
    কোন generation এ কত টাকা গেছে, কারা পেয়েছে
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        qs = BonusLog.objects.filter(reason__icontains="Leadership Bonus")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        summary = qs.aggregate(
            total_paid=Sum("amount"),
            total_transactions=Count("id"),
            unique_earners=Count("user", distinct=True),
        )

        # Generation breakdown — reason এ "Gen 1", "Gen 2" etc আছে
        gen_breakdown = []
        for gen in range(1, 6):
            gen_qs = qs.filter(reason__icontains=f"Gen {gen}")
            gen_data = gen_qs.aggregate(
                total=Sum("amount"),
                count=Count("id"),
                earners=Count("user", distinct=True),
            )
            gen_breakdown.append(
                {
                    "generation": gen,
                    "total_paid": float(gen_data["total"] or 0),
                    "transactions": gen_data["count"],
                    "earners": gen_data["earners"],
                }
            )

        # Per user breakdown
        per_user = (
            qs.values(
                "user__username", "user__name", "user__star_level", "user__status"
            )
            .annotate(
                total_bonus=Sum("amount"),
                transaction_count=Count("id"),
                last_bonus=Max("timestamp"),
            )
            .order_by("-total_bonus")
        )

        return Response(
            {
                "filters": {"from": date_from, "to": date_to},
                "summary": {
                    "total_paid": float(summary["total_paid"] or 0),
                    "total_transactions": summary["total_transactions"],
                    "unique_earners": summary["unique_earners"],
                },
                "generation_breakdown": gen_breakdown,
                "per_user": list(per_user),
            }
        )


# ═══════════════════════════════════════════════════════
# ৬. RANK REWARD REPORT
# ═══════════════════════════════════════════════════════
class RankRewardReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = BonusLog.objects.filter(reason__icontains="Rank Reward")

        summary = qs.aggregate(
            total_paid=Sum("amount"),
            total_transactions=Count("id"),
        )

        # Star level breakdown
        star_breakdown = []
        star_amounts = {
            1: 0,
            2: 0,
            3: 0,
            4: 5000,
            5: 10000,
            6: 30000,
            7: 50000,
            8: 100000,
        }
        for level, reward in star_amounts.items():
            if reward == 0:
                continue
            star_qs = qs.filter(reason__icontains=f"{level} Star")
            star_data = star_qs.aggregate(total=Sum("amount"), count=Count("id"))
            star_breakdown.append(
                {
                    "star_level": level,
                    "reward_per_star": reward,
                    "total_distributed": float(star_data["total"] or 0),
                    "count": star_data["count"],
                }
            )

        per_user = (
            qs.values("user__username", "user__name", "user__star_level")
            .annotate(
                total_received=Sum("amount"),
                stars_achieved=Count("id"),
                last_reward=Max("timestamp"),
            )
            .order_by("-total_received")
        )

        return Response(
            {
                "summary": {
                    "total_paid": float(summary["total_paid"] or 0),
                    "total_transactions": summary["total_transactions"],
                },
                "star_breakdown": star_breakdown,
                "per_user": list(per_user),
            }
        )


# ═══════════════════════════════════════════════════════
# ৭. WITHDRAWAL REPORT
# ═══════════════════════════════════════════════════════
class WithdrawalReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        status_filter = request.query_params.get("status")  # pending|approved|rejected

        qs = WithdrawalRequest.objects.all()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if status_filter:
            qs = qs.filter(status=status_filter)

        # Status summary
        status_summary = (
            WithdrawalRequest.objects.values("status")
            .annotate(count=Count("id"), total=Sum("amount"))
            .order_by("status")
        )

        # Method breakdown (bKash, Nagad, etc.)
        method_summary = (
            qs.values("method")
            .annotate(count=Count("id"), total=Sum("amount"))
            .order_by("-total")
        )

        # Per user breakdown
        per_user = (
            qs.values("user__username", "user__name", "user__phone")
            .annotate(
                total_requested=Sum("amount"),
                total_approved=Sum("amount", filter=Q(status="approved")),
                total_rejected=Sum("amount", filter=Q(status="rejected")),
                request_count=Count("id"),
            )
            .order_by("-total_requested")
        )

        # Overall stats
        overall = qs.aggregate(
            total_requested=Sum("amount"),
            total_approved=Sum("amount", filter=Q(status="approved")),
            total_rejected=Sum("amount", filter=Q(status="rejected")),
            total_pending=Sum("amount", filter=Q(status="pending")),
            avg_amount=Avg("amount"),
            max_amount=Max("amount"),
            min_amount=Min("amount"),
        )

        # Daily trend
        daily = (
            qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-date")[:30]
        )

        return Response(
            {
                "filters": {"from": date_from, "to": date_to, "status": status_filter},
                "overall": {
                    k: float(v or 0) if isinstance(v, Decimal) else v
                    for k, v in overall.items()
                },
                "status_breakdown": list(status_summary),
                "method_breakdown": list(method_summary),
                "per_user": list(per_user),
                "daily_trend": list(daily),
            }
        )


# ═══════════════════════════════════════════════════════
# ৮. USER ACTIVATION REPORT
# ═══════════════════════════════════════════════════════
class ActivationReportView(APIView):
    """
    কোন দিনে কতজন active হয়েছে
    Division wise breakdown
    কত টাকা fund এ গেছে (activation এর কারণে)
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        active_qs = User.objects.filter(status="active")
        all_qs = User.objects.all()

        if date_from:
            active_qs = active_qs.filter(createdAt__date__gte=date_from)
            all_qs = all_qs.filter(createdAt__date__gte=date_from)
        if date_to:
            active_qs = active_qs.filter(createdAt__date__lte=date_to)
            all_qs = all_qs.filter(createdAt__date__lte=date_to)

        # Overall summary
        total_users = User.objects.count()
        active_users = User.objects.filter(status="active").count()
        inactive_users = total_users - active_users

        # Daily registration trend
        daily_reg = (
            all_qs.annotate(date=TruncDate("createdAt"))
            .values("date")
            .annotate(
                registered=Count("id"),
                activated=Count("id", filter=Q(status="active")),
            )
            .order_by("-date")[:30]
        )

        # Monthly activation trend
        monthly = (
            active_qs.annotate(month=TruncMonth("createdAt"))
            .values("month")
            .annotate(
                count=Count("id"),
                fund_generated=Count("id") * 4000,  # প্রতি activation এ ৪০০০ টাকা
            )
            .order_by("-month")
        )

        # Division wise breakdown
        division_breakdown = (
            User.objects.values("division")
            .annotate(
                total=Count("id"),
                active=Count("id", filter=Q(status="active")),
                inactive=Count("id", filter=Q(status="inactive")),
            )
            .order_by("-total")
        )

        # Recently activated users
        recent_activated = (
            User.objects.filter(status="active")
            .order_by("-createdAt")
            .values(
                "username",
                "name",
                "phone",
                "division",
                "referred_by__username",
                "createdAt",
            )[:20]
        )

        return Response(
            {
                "filters": {"from": date_from, "to": date_to},
                "summary": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "inactive_users": inactive_users,
                    "activation_rate": (
                        round(active_users / total_users * 100, 2) if total_users else 0
                    ),
                    "total_fund_generated": active_users * 4000,
                },
                "daily_trend": list(daily_reg),
                "monthly_trend": list(monthly),
                "division_breakdown": list(division_breakdown),
                "recent_activated": list(recent_activated),
            }
        )


# ═══════════════════════════════════════════════════════
# ৯. STAR LEVEL DISTRIBUTION REPORT
# ═══════════════════════════════════════════════════════
class StarLevelReportView(APIView):
    permission_classes = [IsAdminUser]

    STAR_THRESHOLDS = {
        0: "No Star (0 pairs)",
        1: "1 Star",
        2: "2 Star",
        3: "3 Star",
        4: "4 Star (15+ pairs)",
        5: "5 Star (50+ pairs)",
        6: "6 Star (200+ pairs)",
        7: "7 Star (500+ pairs)",
        8: "8 Star (1200+ pairs)",
    }

    STAR_REWARDS = {4: 5000, 5: 10000, 6: 30000, 7: 50000, 8: 100000}

    def get(self, request):
        star_data = (
            User.objects.values("star_level")
            .annotate(
                total_count=Count("id"),
                active_count=Count("id", filter=Q(status="active")),
                inactive_count=Count("id", filter=Q(status="inactive")),
                total_balance=Sum("balance"),
            )
            .order_by("star_level")
        )

        breakdown = []
        for item in star_data:
            level = item["star_level"]
            reward = self.STAR_REWARDS.get(level, 0)
            breakdown.append(
                {
                    "star_level": level,
                    "label": self.STAR_THRESHOLDS.get(level, f"{level} Star"),
                    "total_count": item["total_count"],
                    "active_count": item["active_count"],
                    "inactive_count": item["inactive_count"],
                    "rank_reward_each": reward,
                    "total_reward_paid": reward * item["active_count"],
                }
            )

        # Top performers per star level
        star_filter = request.query_params.get("star_level")
        top_users = []
        if star_filter:
            top_users = (
                User.objects.filter(star_level=star_filter, status="active")
                .order_by("-matching_bonus")
                .values(
                    "username",
                    "name",
                    "phone",
                    "division",
                    "star_level",
                    "left_count",
                    "right_count",
                    "matching_bonus",
                    "balance",
                )[:20]
            )

        total_rank_rewards = (
            BonusLog.objects.filter(reason__icontains="Rank Reward").aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        return Response(
            {
                "summary": {
                    "total_starred_users": User.objects.filter(
                        star_level__gte=4
                    ).count(),
                    "total_rank_rewards_paid": float(total_rank_rewards),
                },
                "star_breakdown": breakdown,
                "top_users_in_level": list(top_users),
            }
        )


# ═══════════════════════════════════════════════════════
# ১০. MONTHLY SUMMARY REPORT
# ═══════════════════════════════════════════════════════
class MonthlySummaryReportView(APIView):
    """
    ?year=2025 দিলে সেই বছরের প্রতি মাসের summary দেবে।
    না দিলে current year এর।
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        year = int(request.query_params.get("year", datetime.now().year))

        monthly_data = []

        for month in range(1, 13):
            # Fund inflow/outflow
            fund_inflow = FundLog.objects.filter(
                transaction_type="inbound",
                created_at__year=year,
                created_at__month=month,
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            fund_outflow = FundLog.objects.filter(
                transaction_type="outbound",
                created_at__year=year,
                created_at__month=month,
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            # Bonus distributed
            bonus_data = BonusLog.objects.filter(
                timestamp__year=year,
                timestamp__month=month,
            ).aggregate(
                total=Sum("amount"),
                count=Count("id"),
            )

            # Bonus breakdown by type
            referral_bonus = BonusLog.objects.filter(
                timestamp__year=year,
                timestamp__month=month,
                reason__icontains="Referral Bonus",
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            matching_bonus = BonusLog.objects.filter(
                timestamp__year=year,
                timestamp__month=month,
                reason__icontains="Matching Bonus",
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            leadership_bonus = BonusLog.objects.filter(
                timestamp__year=year,
                timestamp__month=month,
                reason__icontains="Leadership Bonus",
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            rank_bonus = BonusLog.objects.filter(
                timestamp__year=year,
                timestamp__month=month,
                reason__icontains="Rank Reward",
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

            # New registrations
            new_users = User.objects.filter(
                createdAt__year=year,
                createdAt__month=month,
            ).count()

            new_active = User.objects.filter(
                createdAt__year=year,
                createdAt__month=month,
                status="active",
            ).count()

            # Withdrawals
            withdrawal_data = WithdrawalRequest.objects.filter(
                created_at__year=year,
                created_at__month=month,
            ).aggregate(
                total_requested=Sum("amount"),
                total_approved=Sum("amount", filter=Q(status="approved")),
                count=Count("id"),
            )

            monthly_data.append(
                {
                    "year": year,
                    "month": month,
                    "month_name": datetime(year, month, 1).strftime("%B"),
                    "new_registrations": new_users,
                    "new_activations": new_active,
                    "fund_inflow": float(fund_inflow),
                    "fund_outflow": float(fund_outflow),
                    "net_fund": float(fund_inflow - fund_outflow),
                    "total_bonus_paid": float(bonus_data["total"] or 0),
                    "bonus_breakdown": {
                        "referral": float(referral_bonus),
                        "matching": float(matching_bonus),
                        "leadership": float(leadership_bonus),
                        "rank_reward": float(rank_bonus),
                    },
                    "withdrawals": {
                        "total_requested": float(
                            withdrawal_data["total_requested"] or 0
                        ),
                        "total_approved": float(withdrawal_data["total_approved"] or 0),
                        "count": withdrawal_data["count"],
                    },
                }
            )

        # Year totals
        year_total_inflow = sum(m["fund_inflow"] for m in monthly_data)
        year_total_outflow = sum(m["fund_outflow"] for m in monthly_data)
        year_total_bonus = sum(m["total_bonus_paid"] for m in monthly_data)
        year_new_users = sum(m["new_registrations"] for m in monthly_data)
        year_activations = sum(m["new_activations"] for m in monthly_data)

        return Response(
            {
                "year": year,
                "annual_summary": {
                    "total_inflow": year_total_inflow,
                    "total_outflow": year_total_outflow,
                    "net_fund": year_total_inflow - year_total_outflow,
                    "total_bonus_paid": year_total_bonus,
                    "new_users": year_new_users,
                    "new_activations": year_activations,
                },
                "monthly_data": monthly_data,
            }
        )


# ═══════════════════════════════════════════════════════
# ১১. REFERRAL CHAIN REPORT
# কোন user এর tree তে কতজন, কতজন active
# ═══════════════════════════════════════════════════════
class ReferralChainReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        # Direct referrals
        direct_refs = User.objects.filter(referred_by=user)
        direct_active = direct_refs.filter(status="active").count()
        direct_inactive = direct_refs.filter(status="inactive").count()

        # All downline (placement tree) — BFS
        all_downline = []
        queue = [user]
        while queue:
            current = queue.pop(0)
            children = User.objects.filter(placement_under=current).select_related(
                "referred_by", "placement_under"
            )
            for child in children:
                all_downline.append(child)
                queue.append(child)

        total_downline = len(all_downline)
        active_downline = sum(1 for u in all_downline if u.status == "active")

        # Bonus earned because of this user's network
        total_referral_earned = (
            BonusLog.objects.filter(
                user=user, reason__icontains="Referral Bonus"
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )

        total_matching_earned = (
            BonusLog.objects.filter(
                user=user, reason__icontains="Matching Bonus"
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )

        # Direct referral list
        ref_list = direct_refs.values(
            "username", "name", "phone", "status", "division", "createdAt", "points"
        ).order_by("-createdAt")

        return Response(
            {
                "user": {
                    "username": user.username,
                    "name": user.name,
                    "status": user.status,
                    "star_level": user.star_level,
                    "left_count": user.left_count,
                    "right_count": user.right_count,
                },
                "direct_referrals": {
                    "total": direct_refs.count(),
                    "active": direct_active,
                    "inactive": direct_inactive,
                    "conversion_rate": (
                        round(direct_active / direct_refs.count() * 100, 2)
                        if direct_refs.count()
                        else 0
                    ),
                    "list": list(ref_list),
                },
                "placement_downline": {
                    "total": total_downline,
                    "active": active_downline,
                    "inactive": total_downline - active_downline,
                    "activation_rate": (
                        round(active_downline / total_downline * 100, 2)
                        if total_downline
                        else 0
                    ),
                },
                "earnings_from_network": {
                    "referral_bonus": float(total_referral_earned),
                    "matching_bonus": float(total_matching_earned),
                    "total_earned": float(total_referral_earned)
                    + float(total_matching_earned),
                },
            }
        )


# ═══════════════════════════════════════════════════════
# ১২. TOP EARNERS REPORT
# ═══════════════════════════════════════════════════════
class TopEarnersReportView(APIView):
    """
    ?type=referral | matching | leadership | rank_reward | overall
    ?limit=10 (default 10)
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        bonus_type = request.query_params.get("type", "overall")
        limit = int(request.query_params.get("limit", 10))

        REASON_MAP = {
            "referral": "Referral Bonus",
            "matching": "Matching Bonus",
            "leadership": "Leadership Bonus",
            "rank_reward": "Rank Reward",
        }

        if bonus_type == "overall":
            top = (
                User.objects.filter(status="active")
                .order_by("-balance")
                .values(
                    "username",
                    "name",
                    "phone",
                    "division",
                    "star_level",
                    "balance",
                    "referral_bonus",
                    "matching_bonus",
                    "leadership_bonus",
                    "rank_reward_bonus",
                    "left_count",
                    "right_count",
                )[:limit]
            )
        else:
            keyword = REASON_MAP.get(bonus_type)
            if not keyword:
                return Response({"error": "Invalid type."}, status=400)

            top = (
                BonusLog.objects.filter(reason__icontains=keyword)
                .values(
                    "user__username",
                    "user__name",
                    "user__phone",
                    "user__star_level",
                    "user__status",
                    "user__division",
                )
                .annotate(total_earned=Sum("amount"), count=Count("id"))
                .order_by("-total_earned")[:limit]
            )

        return Response(
            {
                "type": bonus_type,
                "limit": limit,
                "result": list(top),
            }
        )
