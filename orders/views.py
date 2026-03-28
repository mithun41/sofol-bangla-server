from datetime import timedelta
from datetime import datetime
from django.db.models import Sum, Count, Value, DecimalField # এখানে Value আর DecimalField যোগ কর
from django.db.models.functions import Coalesce

from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Sum, F, DecimalField
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
                    
                    if is_active_user:
                        # একটিভ ইউজার: ডিসকাউন্ট পাবে, কিন্তু অর্ডারের রেকর্ডে PV থাকবে অফার হিসাবের জন্য
                        discount = unit_pv * 2
                        final_unit_price = base_price - discount
                        final_unit_pv = unit_pv # এখানে ০ দিও না, অরিজিনাল PV টা দাও
                    else:
                        # ইন-একটিভ ইউজার: ফুল প্রাইস এবং আইডি এক্টিভেশন PV
                        final_unit_price = base_price
                        final_unit_pv = unit_pv 

                    calculated_subtotal += (final_unit_price * qty)
                    total_pv += (final_unit_pv * qty) # এখন এখানে সঠিক ভ্যালু জমা হবে

                    

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
        
class AdminOrderAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filter_type = request.query_params.get('filter', '7days')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        today = timezone.now().date()

        # ১. ডেট সেট করা
        if start_date_str and end_date_str:
            start_date, end_date = start_date_str, end_date_str
        elif filter_type == '15days':
            start_date, end_date = today - timedelta(days=15), today
        elif filter_type == '1month':
            start_date, end_date = today - timedelta(days=30), today
        else:
            start_date, end_date = today - timedelta(days=7), today

        # ২. কুয়েরি (তোর মডেলের সঠিক ফিল্ড name: created_at এবং total_amount)
        # তোর মডেলে যদি Order থাকে, তবে নিশ্চিত করিস status টা 'completed' নাকি 'active'
        from orders.models import Order # তোর অর্ডারের সঠিক পাথ দিবি
        
        orders = Order.objects.filter(
            created_at__date__range=[start_date, end_date],
            status='completed' 
        )

        # total_price এর বদলে total_amount হবে তোর এরর অনুযায়ী
        income_data = orders.aggregate(total=Sum('total_amount'))
        total_income = income_data['total'] or 0
        total_orders_count = orders.count()

        # ৩. গ্রাফের জন্য ডেইলি ডেটা
        daily_stats = orders.values('created_at__date').annotate(
            income=Sum('total_amount'),
            count=Count('id')
        ).order_by('created_at__date')

        return Response({
            "summary": {
                "total_income": float(total_income),
                "total_orders": total_orders_count,
                "start_date": str(start_date),
                "end_date": str(end_date)
            },
            "daily_stats": list(daily_stats) # list এ কনভার্ট করলে ফ্রন্টএন্ড সহজে পায়
        })
        
class OrderSalesAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filter_type = request.query_params.get('filter', '7days')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        today = timezone.now().date()
        start_date = today
        end_date = today

        # ১. সকল লজিক এক জায়গায় (Single Logic Block)
        try:
            if filter_type == 'today':
                start_date = today
                end_date = today
            elif filter_type == 'custom' and start_date_str and end_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            elif filter_type == '15days':
                start_date = today - timedelta(days=15)
                end_date = today
            elif filter_type == '1month':
                start_date = today - timedelta(days=30)
                end_date = today
            else: # Default 7 days
                start_date = today - timedelta(days=7)
                end_date = today
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        # ২. ডাটা ফিল্টার করা (অবশ্যই status__iexact ব্যবহার করবি)
        orders_query = Order.objects.filter(
            created_at__date__range=[start_date, end_date],
            status__iexact='completed'
        )

        print(f"Total orders found for {filter_type}: {orders_query.count()}")

        # ৩. টোটাল ইনকাম এবং টোটাল অর্ডার সংখ্যা (Coalesce দিয়ে None হ্যান্ডেল করা)
        summary_data = orders_query.aggregate(
            total_income=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField())),
            total_orders=Count('id')
        )

        # ৪. ডেইলি স্ট্যাটিস্টিকস
        daily_breakdown = orders_query.values('created_at__date').annotate(
            income=Coalesce(Sum('total_amount'), Value(0, output_field=DecimalField())),
            order_count=Count('id')
        ).order_by('-created_at__date')

        return Response({
            "status": "success",
            "range": {
                "start": start_date,
                "end": end_date
            },
            "summary": {
                "total_income": float(summary_data['total_income']),
                "total_orders": summary_data['total_orders']
            },
            "daily_stats": list(daily_breakdown)
        })