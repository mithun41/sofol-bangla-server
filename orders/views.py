from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from products.models import Product 
from .models import Order, OrderItem
from .serializers import OrderSerializer

import logging

logger = logging.getLogger(__name__)

class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user = request.user
        items_data = data.get('items', [])

        if not items_data:
            return Response({"error": "আপনার কার্টটি খালি!"}, status=status.HTTP_400_BAD_REQUEST)

        # ১. ইউজার স্ট্যাটাস চেক
        raw_status = getattr(user, 'status', 'inactive')
        if not raw_status and hasattr(user, 'profile'):
            raw_status = getattr(user.profile, 'status', 'inactive')
        
        is_active_user = (str(raw_status).lower().strip() == 'active')

        try:
            with transaction.atomic():
                calculated_subtotal = 0
                total_pv = 0
                processed_items = []

                for item in items_data:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])
                    
                    if product.stock < qty:
                        raise Exception(f"{product.name} এর পর্যাপ্ত স্টক নেই!")

                    base_price = float(product.price)
                    unit_pv = float(product.point_value or 0)
                    
                    # অফার লজিক
                    if is_active_user:
                        discount = unit_pv * 2
                        final_unit_price = base_price - discount
                        final_unit_pv = 0 
                    else:
                        final_unit_price = base_price
                        final_unit_pv = unit_pv 

                    calculated_subtotal += (final_unit_price * qty)
                    total_pv += (final_unit_pv * qty)

                    # স্টক আপডেট
                    product.stock -= qty
                    product.save()

                    processed_items.append({
                        'product': product,
                        'quantity': qty,
                        'price': final_unit_price,
                        'pv': final_unit_pv
                    })

                # শিপিং কস্ট বাদ দেওয়া হয়েছে
                total_amount = calculated_subtotal 

                # ২. মেইন অর্ডার সেভ
                order = Order.objects.create(
                    user=user,
                    name=data.get('name'),
                    phone=data.get('phone'),
                    address=data.get('address'),
                    city=data.get('city', ''),
                    courier=data.get('courier', 'Sundarban'),
                    subtotal=calculated_subtotal,
                    total_amount=total_amount, # সাবটোটাল আর টোটাল এখন সমান
                    total_pv=total_pv,
                    payment_method=data.get('payment_method', 'cod'),
                    transaction_id=data.get('transaction_id', ''),
                    sender_number=data.get('sender_number', ''),
                    status='Pending'
                )

                # ৩. অর্ডার আইটেম সেভ
                for p_item in processed_items:
                    OrderItem.objects.create(
                        order=order,
                        product_id=p_item['product'].id,
                        product_name=p_item['product'].name,
                        quantity=p_item['quantity'],
                        price=p_item['price'],
                        point_value=p_item['pv']
                    )

                return Response({
                    "success": True,
                    "message": "অর্ডারটি সফলভাবে সম্পন্ন হয়েছে!",
                    "order_id": order.id,
                    "payable_amount": total_amount
                }, status=status.HTTP_201_CREATED)
    
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# --- বাকি অ্যাডমিন ও ইউজার ভিউগুলো একই থাকবে ---
class AdminOrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by("-created_at")
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]

class AdminOrderUpdateView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]

class UserOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by("-created_at")

# --- ৩. ড্যাশবোর্ড রিপোর্ট ভিউগুলো ---

class AdminDashboardReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        monthly_sales = Order.objects.filter(
            status='Completed', 
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_amount'), 0, output_field=DecimalField())
        )['res']

        # ফিক্স: সরাসরি Order টেবিলের total_pv ব্যবহার কর। 
        # কারণ অর্ডারের সময় মেম্বার হলে তুই অলরেডি এটা ০ সেভ করেছিস।
        total_bonus_points = Order.objects.filter(
            status='Completed',
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_pv'), 0)
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

        user_monthly_spend = Order.objects.filter(
            user=user,
            status='Completed',
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_amount'), 0, output_field=DecimalField())
        )['res']

        # ফিক্স: ইউজার ড্যাশবোর্ডের জন্যও সরাসরি Order.total_pv সাম কর।
        user_monthly_points = Order.objects.filter(
            user=user,
            status='Completed',
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_pv'), 0)
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