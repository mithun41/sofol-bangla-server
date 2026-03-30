from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.db.models import F, Q
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model

from products.models import Product
from orders.models import Order, OrderItem
from accounts.services import distribute_money_to_funds
from .serializers import POSProductSerializer, POSCustomerSerializer

User = get_user_model()

# ১. প্রোডাক্ট সার্চ (বারকোড নম্বর, নাম বা আইডি দিয়ে)
class POSProductSearch(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if query:
            # ✅ এখানে 'barcode' এর বদলে 'barcode_number' ব্যবহার করা হয়েছে
            products = Product.objects.filter(
                Q(barcode_number=query) | 
                Q(name__icontains=query) | 
                Q(id__icontains=query)
            ).filter(is_active=True)[:10]
        else:
            products = Product.objects.none()

        serializer = POSProductSerializer(products, many=True)
        return Response(serializer.data)

# ২. কাস্টমার সার্চ (ইউজারনেম বা ফোন দিয়ে)
class POSCustomerSearch(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q', '')
        customers = User.objects.filter(
            Q(username__icontains=query) | Q(phone__icontains=query)
        )[:5]
        serializer = POSCustomerSerializer(customers, many=True)
        return Response(serializer.data)

# ৩. অর্ডার তৈরি লজিক (মেম্বার ডিসকাউন্ট এবং পয়েন্ট ডিস্ট্রিবিউশন)
lass POSOrderCreate(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        data = request.data
        customer_id = data.get('customer_id')
        items = data.get('items', [])

        if not customer_id or not items:
            return Response({"error": "ডেটা ইনকমপ্লিট!"}, status=400)

        customer = User.objects.filter(id=customer_id).first()
        if not customer:
            return Response({"error": "কাস্টমার পাওয়া যায়নি!"}, status=404)

        try:
            with transaction.atomic():
                # মেম্বার স্ট্যাটাস চেক
                is_active = (str(getattr(customer, 'status', '')).lower().strip() == 'active')

                # ✅ ভুল এখানে ছিল: ০ এর বদলে Decimal('0.00') ব্যবহার করতে হবে
                total_amount = Decimal('0.00')
                total_pv = Decimal('0.00')
                order_items_data = []

                for item in items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    
                    # কোয়ান্টিটিকেও ডেসিমাল হিসেবে ট্রিট করা সেফ
                    qty = Decimal(str(item.get('quantity', 1)))
                    
                    if product.stock < int(qty):
                        raise Exception(f"{product.name} আউট অফ স্টক!")

                    # ডাটাবেস ভ্যালুগুলোকে ডেসিমাল করে নেওয়া
                    original_price = Decimal(str(product.price))
                    pv_unit = Decimal(str(product.point_value or '0.00'))
                    discount_rate = Decimal('2.00')

                    if is_active:
                        # একটিভ মেম্বার: ১ পয়েন্ট = ২ টাকা ছাড়, পয়েন্ট পাবে না
                        final_price = original_price - (pv_unit * discount_rate)
                        final_pv = Decimal('0.00')
                    else:
                        # ইন-একটিভ: ফুল প্রাইস, পয়েন্ট পাবে
                        final_price = original_price
                        final_pv = pv_unit

                    # এখন আর এরর আসবে না কারণ সবাই Decimal
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

                # মেইন অর্ডার তৈরি
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

                # আইটেমগুলো সেভ করা
                for oi in order_items_data:
                    OrderItem.objects.create(
                        order=order,
                        product_id=oi['product_id'],
                        product_name=oi['product_name'],
                        quantity=oi['quantity'],
                        price=oi['price'],
                        point_value=oi['point_value']
                    )

                # ফান্ড এবং পয়েন্ট আপডেট
                if total_pv > Decimal('0.00'):
                    distribute_money_to_funds(float(total_pv)) # ফান্ড ফাংশন ফ্লোট চাইলে সমস্যা নেই
                    
                    # পয়েন্ট আপডেট (Decimal + F expression compatibility fix)
                    User.objects.filter(id=customer.id).update(points=F('points') + total_pv)
                    
                    customer.refresh_from_db()
                    if Decimal(str(customer.points)) >= Decimal('1000.00') and customer.status != 'active':
                        customer.status = 'active'
                        customer.save()

                return Response({
                    "success": True,
                    "order_id": order.id,
                    "total": float(total_amount), # ফ্রন্টএন্ডে ফ্লোট পাঠানো সেফ
                    "added_points": float(total_pv),
                    "user_status": customer.status
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)