from django.utils import timezone
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import Order, OrderItem
from .serializers import OrderSerializer

# --- সাধারণ ভিউগুলো ---

class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class AdminOrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by("-created_at")
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]

class AdminOrderUpdateView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]

class UserOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by("-created_at")

# --- ড্যাশবোর্ড রিপোর্ট ভিউগুলো ---

class AdminDashboardReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ১. এই মাসের টোটাল সেলস
        monthly_sales = Order.objects.filter(
            status='Completed', 
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_amount'), 0, output_field=DecimalField())
        )['res']

        # ২. এই মাসের টোটাল বোনাস (models.F এর বদলে শুধু F ব্যবহার করা হয়েছে)
        total_bonus_points = OrderItem.objects.filter(
            order__status='Completed',
            order__created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum(F('point_value') * F('quantity')), 0)
        )['res']

        pending_orders = Order.objects.filter(status='Pending').count()

        return Response({
            "monthly_sales": float(monthly_sales),
            "monthly_bonus": int(total_bonus_points),
            "pending_orders": pending_orders,
            "month_name": now.strftime('%B')
        })

class UserDashboardReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ইউজারের এই মাসের কেনাকাটা
        user_monthly_spend = Order.objects.filter(
            user=user,
            status='Completed',
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_amount'), 0, output_field=DecimalField())
        )['res']

        # ইউজারের এই মাসের পয়েন্ট (এখানেও models.F ফিক্স করা হয়েছে)
        user_monthly_points = OrderItem.objects.filter(
            order__user=user,
            order__status='Completed',
            order__created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum(F('point_value') * F('quantity')), 0)
        )['res']

        total_orders = Order.objects.filter(
            user=user, 
            created_at__gte=first_day
        ).count()

        return Response({
            "monthly_spend": float(user_monthly_spend),
            "monthly_points": int(user_monthly_points),
            "total_orders": total_orders,
            "month_name": now.strftime('%B')
        })