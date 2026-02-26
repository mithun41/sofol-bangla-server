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

        # --- ১. ইউজার অ্যাক্টিভ কিনা চেক (তোর কাস্টম ইউজার মডেল অনুযায়ী) ---
        # তোর মডেলে status সরাসরি User এ আছে, profile এ নয়।
        raw_status = getattr(user, 'status', 'inactive')
        clean_status = str(raw_status).lower().strip()
        is_active_user = (clean_status == 'active')

        # ডিবাগ প্রিন্ট
        print(f"--- DEBUG ORDER START ---")
        print(f"User: {user.username} | DB Status: '{raw_status}' | Logic Active: {is_active_user}")

        try:
            with transaction.atomic():
                calculated_subtotal = 0
                total_pv = 0
                processed_items = []

                for item in items_data:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])
                    
                    base_price = float(product.price)
                    unit_pv = float(product.point_value or 0)
                    
                    if is_active_user:
                        # মেম্বার প্রাইস: ৩০০ - ৫০ = ২৫০ টাকা
                        final_unit_price = base_price - unit_pv 
                        final_unit_pv = 0 
                    else:
                        # সাধারণ প্রাইস: ৩০০ টাকা (ফুল) এবং পয়েন্ট পাবে ৫০
                        final_unit_price = base_price
                        final_unit_pv = unit_pv 

                    calculated_subtotal += (final_unit_price * qty)
                    total_pv += (final_unit_pv * qty)

                    processed_items.append({
                        'product': product,
                        'quantity': qty,
                        'price': final_unit_price,
                        'pv': final_unit_pv
                    })

                # শিপিং কস্ট
                city = data.get('city', 'Dhaka').strip()
                shipping_cost = 100 if city == 'Dhaka' else 150
                total_amount = calculated_subtotal + shipping_cost

                # ২. মেইন অর্ডার সেভ
                order = Order.objects.create(
                    user=user,
                    name=data.get('name'),
                    phone=data.get('phone'),
                    address=data.get('address'),
                    city=city,
                    subtotal=calculated_subtotal,
                    shipping_cost=shipping_cost,
                    total_amount=total_amount,
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

                print(f"Final Amount: {total_amount} | Total PV: {total_pv}")
                print(f"--- DEBUG ORDER END ---")

                return Response({
                    "success": True,
                    "message": "অর্ডারটি সফলভাবে গ্রহণ করা হয়েছে!",
                    "order_id": order.id,
                    "is_active_member": is_active_user,
                    "payable_amount": total_amount
                }, status=status.HTTP_201_CREATED)
    
        except Product.DoesNotExist:
            return Response({"error": "প্রোডাক্ট খুঁজে পাওয়া যায়নি!"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"সিস্টেম এরর: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

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