from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.db.models import F, Q
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model
from decimal import Decimal  # ✅ ডেসিমাল ইম্পোর্ট করা হয়েছে

from products.models import Product
from orders.models import Order, OrderItem
from accounts.services import distribute_money_to_funds
from .serializers import POSProductSerializer, POSCustomerSerializer

User = get_user_model()

# ১. প্রোডাক্ট সার্চ (বারকোড নম্বর, নাম বা আইডি দিয়ে)
from decimal import Decimal

class POSOrderCreate(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        data = request.data
        customer_id = data.get('customer_id')
        items = data.get('items', [])

        # ১. বেসিক ভ্যালিডেশন
        if not customer_id or not items:
            return Response({"error": "কাস্টমার বা আইটেম মিসিং!"}, status=400)

        customer = User.objects.filter(id=customer_id).first()
        if not customer:
            return Response({"error": "কাস্টমার পাওয়া যায়নি!"}, status=404)

        try:
            with transaction.atomic():
                # মেম্বার স্ট্যাটাস চেক
                is_active = (str(getattr(customer, 'status', '')).lower().strip() == 'active')

                total_amount = Decimal('0.00')
                total_pv = Decimal('0.00')
                order_items_data = []

                for item in items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    
                    # ✅ সেফ কনভারশন: সব কিছুকে Decimal(str()) করে নেওয়া
                    qty = Decimal(str(item.get('quantity', 1)))
                    
                    if product.stock < qty:
                        raise Exception(f"{product.name} আউট অফ স্টক!")

                    # ডাটাবেস থেকে আসা ভ্যালুগুলোকেও স্ট্রিং করে ডেসিমাল করা
                    original_price = Decimal(str(product.price))
                    pv_unit = Decimal(str(product.point_value or '0.00'))
                    discount_multiplier = Decimal('2.00')

                    if is_active:
                        # একটিভ মেম্বার: ডিসকাউন্ট পাবে, পয়েন্ট ০
                        final_price = original_price - (pv_unit * discount_multiplier)
                        final_pv = Decimal('0.00')
                    else:
                        # ইন-একটিভ: ফুল প্রাইস, পয়েন্ট পাবে
                        final_price = original_price
                        final_pv = pv_unit

                    # আইটেম টোটাল ক্যালকুলেশন
                    total_amount += (final_price * qty)
                    total_pv += (final_pv * qty)

                    # স্টক আপডেট
                    product.stock -= int(qty)
                    product.save()

                    order_items_data.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'quantity': int(qty),
                        'price': final_price,
                        'point_value': final_pv
                    })

                # ২. অর্ডার অবজেক্ট তৈরি
                order = Order.objects.create(
                    user=customer,
                    name=customer.username,
                    phone=getattr(customer, 'phone', ""),
                    address="POS Counter Sale",
                    subtotal=total_amount,
                    total_amount=total_amount,
                    total_pv=total_pv,
                    status='Completed',
                    payment_method=data.get('payment_method', 'Cash')
                )

                # ৩. অর্ডার আইটেম তৈরি
                for oi in order_items_data:
                    OrderItem.objects.create(
                        order=order,
                        product_id=oi['product_id'],
                        product_name=oi['product_name'],
                        quantity=oi['quantity'],
                        price=oi['price'],
                        point_value=oi['point_value']
                    )

                # ৪. ফান্ড ডিস্ট্রিবিউশন এবং পয়েন্ট আপডেট
                if total_pv > Decimal('0.00'):
                    # ✅ এখানে ট্রিক: ফান্ড ডিস্ট্রিবিউশন ফাংশন যদি float চায় তবে float(total_pv) পাঠান
                    try:
                        distribute_money_to_funds(float(total_pv))
                    except:
                        pass # যদি ফান্ড ফাংশনে সমস্যা হয় তবে অর্ডার যেন আটকে না যায়
                    
                    # পয়েন্ট আপডেট (Decimal compatibility fixed)
                    User.objects.filter(id=customer.id).update(points=F('points') + total_pv)
                    
                    # কাস্টমার স্ট্যাটাস চেক (নতুন পয়েন্ট রিফ্রেশ করে)
                    customer.refresh_from_db()
                    if Decimal(str(customer.points)) >= Decimal('1000.00') and customer.status != 'active':
                        customer.status = 'active'
                        customer.save()

                return Response({
                    "success": True,
                    "order_id": order.id,
                    "total": float(total_amount), # ফ্রন্টএন্ডের জন্য float সেফ
                    "user_status": customer.status
                }, status=201)

        except Exception as e:
            # আসল এরর মেসেজটা প্রিন্ট করুন যাতে লগে দেখা যায়
            import traceback
            print(traceback.format_exc()) 
            return Response({"error": str(e)}, status=400)