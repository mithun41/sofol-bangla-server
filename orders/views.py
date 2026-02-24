from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from products.models import Product # প্রোডাক্ট মডেল নিশ্চিত কর
from .models import Order, OrderItem
from .serializers import OrderSerializer

# --- ১. সিকিউর অর্ডার ক্রিয়েট ভিউ (Hack-Proof) ---
class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user = request.user
        items_data = data.get('items', [])

        if not items_data:
            return Response({"error": "আপনার কার্টটি খালি!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ট্রানজেকশন ব্যবহার করা হয়েছে যাতে এরর হলে ডাটাবেসে ভুল ডাটা না ঢুকে
            with transaction.atomic():
                calculated_subtotal = 0
                total_pv = 0
                processed_items = []

                for item in items_data:
                    # ডাটাবেস থেকে প্রোডাক্টের লেটেস্ট দাম ও পিভি নেওয়া হচ্ছে
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])
                    
                    # সিকিউরিটি চেক: ইউজার কি পাঠালো তা ম্যাটার করে না, ডাটাবেসের দামই ফাইনাল
                    actual_price = product.price
                    actual_pv = product.point_value or 0
                    
                    calculated_subtotal += actual_price * qty
                    total_pv += actual_pv * qty

                    processed_items.append({
                        'product': product,
                        'quantity': qty,
                        'price': actual_price,
                        'pv': actual_pv
                    })

                # শিপিং কস্ট লজিক (ঢাকার ভেতরে ৬০, বাইরে ১২০)
                shipping_cost = 60 if data.get('city') == 'Dhaka' else 120
                total_amount = calculated_subtotal + shipping_cost

                # মেইন অর্ডার সেভ
                order = Order.objects.create(
                    user=user,
                    name=data.get('name'),
                    phone=data.get('phone'),
                    address=data.get('address'),
                    city=data.get('city'),
                    subtotal=calculated_subtotal,
                    shipping_cost=shipping_cost,
                    total_amount=total_amount,
                    total_pv=total_pv, # এমএলএম এর জন্য ইম্পর্টেন্ট
                    payment_method=data.get('payment_method'),
                    transaction_id=data.get('transaction_id', ''),
                    sender_number=data.get('sender_number', ''),
                    status='Pending'
                )

                # অর্ডারের আইটেমগুলো লুপ চালিয়ে সেভ করা
                for p_item in processed_items:
                    OrderItem.objects.create(
                        order=order,
        product_id=p_item['product'].id, # তোর মডেলের ফিল্ড নাম 'product_id'
        product_name=p_item['product'].name, # তোর মডেলে এই ফিল্ডটাও আছে
        quantity=p_item['quantity'],
        price=p_item['price'],
        point_value=p_item['pv'] # তোর মডেল ফিল্ড অনুযায়ী
                    )

                return Response({
                    "success": True,
                    "message": "অর্ডারটি সফলভাবে গ্রহণ করা হয়েছে!",
                    "order_id": order.id
                }, status=status.HTTP_201_CREATED)

        except Product.DoesNotExist:
            return Response({"error": "প্রোডাক্ট খুঁজে পাওয়া যায়নি!"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# --- ২. সাধারণ ভিউগুলো ---

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

        user_monthly_spend = Order.objects.filter(
            user=user,
            status='Completed',
            created_at__gte=first_day
        ).aggregate(
            res=Coalesce(Sum('total_amount'), 0, output_field=DecimalField())
        )['res']

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