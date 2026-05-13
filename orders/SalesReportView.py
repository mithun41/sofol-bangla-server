from django.db.models import Sum, Count, Avg, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncDate, TruncMonth, Coalesce, TruncYear
from django.db.models import Value
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from .models import Order, OrderItem


class SalesReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filter_type = request.query_params.get("filter", "7days")
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        today = timezone.now().date()

        try:
            if filter_type == "today":
                start, end = today, today
            elif filter_type == "7days":
                start, end = today - timedelta(days=6), today
            elif filter_type == "15days":
                start, end = today - timedelta(days=14), today
            elif filter_type == "1month":
                start, end = today - timedelta(days=29), today
            elif filter_type == "3months":
                start, end = today - timedelta(days=89), today
            elif filter_type == "custom" and from_str and to_str:
                start = datetime.strptime(from_str, "%Y-%m-%d").date()
                end = datetime.strptime(to_str, "%Y-%m-%d").date()
            else:
                start, end = today - timedelta(days=6), today
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=400
            )

        orders_qs = Order.objects.filter(
            created_at__date__range=[start, end],
            status__iexact="completed",
        )
        items_qs = OrderItem.objects.filter(
            order__created_at__date__range=[start, end],
            order__status__iexact="completed",
        )
        all_orders_qs = Order.objects.filter(created_at__date__range=[start, end])

        # ── Summary ──────────────────────────────────────────────────────────
        revenue = orders_qs.aggregate(
            t=Coalesce(Sum("total_amount"), Value(0, output_field=DecimalField()))
        )["t"]
        cost = items_qs.aggregate(
            t=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("purchase_price") * F("quantity"), output_field=DecimalField()
                    )
                ),
                Value(0, output_field=DecimalField()),
            )
        )["t"]
        profit = revenue - cost
        profit_margin = (
            round(float(profit) / float(revenue) * 100, 1) if revenue else 0.0
        )

        total_orders = all_orders_qs.count()
        completed_orders = orders_qs.count()
        pending_orders = all_orders_qs.filter(status__iexact="pending").count()
        cancelled_orders = all_orders_qs.filter(status__iexact="cancelled").count()
        total_items_sold = items_qs.aggregate(
            t=Coalesce(Sum("quantity"), Value(0, output_field=DecimalField()))
        )["t"]
        avg_order_value = orders_qs.aggregate(t=Avg("total_amount"))["t"] or 0

        # ── Daily breakdown ──────────────────────────────────────────────────
        daily = (
            orders_qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                revenue=Coalesce(
                    Sum("total_amount"), Value(0, output_field=DecimalField())
                ),
                orders=Count("id"),
            )
            .order_by("date")
        )
        daily_cost_map = {}
        daily_items = (
            items_qs.annotate(date=TruncDate("order__created_at"))
            .values("date")
            .annotate(
                cost=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("purchase_price") * F("quantity"),
                            output_field=DecimalField(),
                        )
                    ),
                    Value(0, output_field=DecimalField()),
                )
            )
        )
        for row in daily_items:
            daily_cost_map[str(row["date"])] = float(row["cost"])

        daily_data = []
        for row in daily:
            rev = float(row["revenue"])
            cost_ = daily_cost_map.get(str(row["date"]), 0)
            daily_data.append(
                {
                    "date": str(row["date"]),
                    "revenue": rev,
                    "cost": cost_,
                    "profit": round(rev - cost_, 2),
                    "orders": row["orders"],
                }
            )

        # ── Monthly breakdown ────────────────────────────────────────────────
        monthly = (
            Order.objects.filter(status__iexact="completed")
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                revenue=Coalesce(
                    Sum("total_amount"), Value(0, output_field=DecimalField())
                ),
                orders=Count("id"),
            )
            .order_by("-month")[:12]
        )
        monthly_cost_map = {}
        monthly_items = (
            OrderItem.objects.filter(order__status__iexact="completed")
            .annotate(month=TruncMonth("order__created_at"))
            .values("month")
            .annotate(
                cost=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("purchase_price") * F("quantity"),
                            output_field=DecimalField(),
                        )
                    ),
                    Value(0, output_field=DecimalField()),
                )
            )
        )
        for row in monthly_items:
            monthly_cost_map[str(row["month"])[:7]] = float(row["cost"])

        monthly_data = []
        for row in monthly:
            rev = float(row["revenue"])
            cost_ = monthly_cost_map.get(str(row["month"])[:7], 0)
            monthly_data.append(
                {
                    "month": str(row["month"])[:7],
                    "month_label": (
                        row["month"].strftime("%b %Y") if row["month"] else ""
                    ),
                    "revenue": rev,
                    "cost": cost_,
                    "profit": round(rev - cost_, 2),
                    "orders": row["orders"],
                }
            )

        # ── Top products ─────────────────────────────────────────────────────
        top_products = (
            items_qs.values("product_name")
            .annotate(
                qty_sold=Coalesce(
                    Sum("quantity"), Value(0, output_field=DecimalField())
                ),
                revenue=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("price") * F("quantity"), output_field=DecimalField()
                        )
                    ),
                    Value(0, output_field=DecimalField()),
                ),
                profit=Coalesce(Sum("profit"), Value(0, output_field=DecimalField())),
            )
            .order_by("-revenue")[:10]
        )

        # ── Status breakdown ─────────────────────────────────────────────────
        status_breakdown = (
            all_orders_qs.values("status")
            .annotate(
                count=Count("id"),
                total=Coalesce(
                    Sum("total_amount"), Value(0, output_field=DecimalField())
                ),
            )
            .order_by("-count")
        )

        # ── All-time totals ───────────────────────────────────────────────────
        alltime_revenue = Order.objects.filter(status__iexact="completed").aggregate(
            t=Coalesce(Sum("total_amount"), Value(0, output_field=DecimalField()))
        )["t"]
        alltime_profit = OrderItem.objects.filter(
            order__status__iexact="completed"
        ).aggregate(t=Coalesce(Sum("profit"), Value(0, output_field=DecimalField())))[
            "t"
        ]
        alltime_orders = Order.objects.filter(status__iexact="completed").count()

        # ── Filtered orders list ──────────────────────────────────────────────
        filtered_orders = all_orders_qs.values(
            "id",
            "name",
            "phone",
            "address",
            "total_amount",
            "status",
            "created_at",
            "payment_method",
        ).order_by("-created_at")
        filtered_orders_data = [
            {
                "id": o["id"],
                "name": o["name"],
                "phone": o["phone"],
                "address": o["address"],
                "amount": float(o["total_amount"]),
                "status": o["status"],
                "payment_method": o["payment_method"],
                "date": o["created_at"].strftime("%d %b %Y"),
                "time": o["created_at"].strftime("%I:%M %p"),
            }
            for o in filtered_orders
        ]

        return Response(
            {
                "filter": {"type": filter_type, "start": str(start), "end": str(end)},
                "summary": {
                    "revenue": float(revenue),
                    "cost": float(cost),
                    "profit": float(profit),
                    "profit_margin": profit_margin,
                    "total_orders": total_orders,
                    "completed_orders": completed_orders,
                    "pending_orders": pending_orders,
                    "cancelled_orders": cancelled_orders,
                    "total_items_sold": float(total_items_sold),
                    "avg_order_value": float(avg_order_value),
                },
                "alltime": {
                    "revenue": float(alltime_revenue),
                    "profit": float(alltime_profit),
                    "orders": alltime_orders,
                },
                "daily_data": daily_data,
                "monthly_data": monthly_data,
                "top_products": list(top_products),
                "status_breakdown": list(status_breakdown),
                "orders_list": filtered_orders_data,
            }
        )
