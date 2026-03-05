from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.db.models import F
from accounts.services import distribute_money_to_funds
from products.models import Product
from orders.models import Order, OrderItem
from .serializers import POSProductSerializer, POSCustomerSerializer
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework_simplejwt.authentication import JWTAuthentication

User = get_user_model()

# ১. প্রোডাক্ট সার্চ (নাম বা আইডি দিয়ে)
class POSProductSearch(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if query:
            products = Product.objects.filter(
                Q(name__icontains=query) | Q(id__icontains=query)
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

# ৩. অর্ডার তৈরি লজিক (দাম সবসময় ফুল থাকবে)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.db.models import F
from accounts.services import distribute_money_to_funds
from products.models import Product
from orders.models import Order, OrderItem
from .serializers import POSProductSerializer, POSCustomerSerializer
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework_simplejwt.authentication import JWTAuthentication

User = get_user_model()

# ৩. অর্ডার তৈরি লজিক (সংশোধিত)
class POSOrderCreate(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        data = request.data
        customer_id = data.get('customer_id')
        items = data.get('items', [])

        if not customer_id:
            return Response({"error": "অনুগ্রহ করে একজন কাস্টমার সিলেক্ট করুন।"}, status=400)

        customer = User.objects.filter(id=customer_id).first()
        if not customer:
            return Response({"error": "কাস্টমার খুঁজে পাওয়া যায়নি!"}, status=404)

        if not items:
            return Response({"error": "কার্ট খালি!"}, status=400)

        try:
            with transaction.atomic():
                # মেম্বার স্ট্যাটাস চেক
                raw_status = getattr(customer, 'status', 'inactive')
                is_active = (str(raw_status).lower().strip() == 'active')

                total_amount = 0
                total_pv = 0
                order_items_data = []

                for item in items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])

                    if product.stock < qty:
                        raise Exception(f"{product.name} আউট অফ স্টক! আছে: {product.stock}")

                    original_price = float(product.price)
                    pv_unit = float(product.point_value or 0)
                    
                    # ✅ ১ পয়েন্ট = ২ টাকা ডিসকাউন্ট লজিক ইমপ্লিমেন্টেশন
                    if is_active:
                        # একটিভ মেম্বার সরাসরি টাকা ডিসকাউন্ট পাবে (পয়েন্ট পাবে না)
                        final_price = original_price - (pv_unit * 2)
                        final_pv = 0
                    else:
                        # ইন-একটিভ মেম্বার ফুল MRP দিবে এবং পয়েন্ট পাবে (অ্যাক্টিভ হওয়ার জন্য)
                        final_price = original_price
                        final_pv = pv_unit

                    total_amount += (final_price * qty)
                    total_pv += (final_pv * qty)

                    # স্টক আপডেট
                    product.stock -= qty
                    product.save()

                    order_items_data.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'quantity': qty,
                        'price': final_price,
                        'point_value': final_pv
                    })

                # মেইন অর্ডার তৈরি
                order = Order.objects.create(
                    user=customer,
                    name=customer.username,
                    phone=getattr(customer, 'phone', ""),
                    address="POS Counter Sale",
                    city="In-Store",
                    subtotal=total_amount,
                    shipping_cost=0,
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

                # ফান্ড এবং পয়েন্ট ডিস্ট্রিবিউশন
                if total_pv > 0:
                    distribute_money_to_funds(total_pv)
                    # ইউজারের পয়েন্ট আপডেট (শুধুমাত্র যারা একটিভ না তারা পাবে)
                    User.objects.filter(id=customer.id).update(points=F('points') + total_pv)
                    
                    # অটো-অ্যাক্টিভেশন চেক
                    customer.refresh_from_db() 
                    if customer.points >= 1000 and customer.status != 'active':
                        customer.status = 'active'
                        customer.save()

                return Response({
                    "success": True,
                    "order_id": order.id,
                    "total": total_amount,
                    "added_points": total_pv,
                    "user_status": customer.status
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)