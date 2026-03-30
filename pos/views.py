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

                # ✅ ফ্লোটের বদলে ডেসিমাল ব্যবহার
                total_amount = Decimal('0.00')
                total_pv = Decimal('0.00')
                order_items_data = []

                for item in items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    # কোয়ান্টিটিকে ডেসিমাল স্ট্রিং থেকে কনভার্ট করা সেফ
                    qty = Decimal(str(item.get('quantity', 1)))

                    if product.stock < qty:
                        raise Exception(f"{product.name} আউট অফ স্টক! আছে: {product.stock}")

                    # ✅ ডাটাবেস ভ্যালুগুলোকে Decimal হিসেবে ধরা
                    original_price = Decimal(str(product.price))
                    pv_unit = Decimal(str(product.point_value or '0.00'))
                    discount_multiplier = Decimal('2.00')
                    
                    if is_active:
                        # ডিসকাউন্ট লজিক: ১ পয়েন্ট = ২ টাকা অফ
                        final_price = original_price - (pv_unit * discount_multiplier)
                        final_pv = Decimal('0.00')
                    else:
                        final_price = original_price
                        final_pv = pv_unit

                    # টোটাল আপডেট (টাইপ সেফ ক্যালকুলেশন)
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
                    city="In-Store",
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

                # ফান্ড এবং পয়েন্ট ডিস্ট্রিবিউশন
                if total_pv > Decimal('0.00'):
                    # ফান্ড সার্ভিস যদি float চায় তবে float() এ কনভার্ট করে পাঠানো
                    distribute_money_to_funds(float(total_pv))
                    
                    # পয়েন্ট আপডেট (Decimal + F expression compatibility)
                    User.objects.filter(id=customer.id).update(points=F('points') + total_pv)
                    
                    customer.refresh_from_db() 
                    # কাস্টমার পয়েন্ট চেক করার সময়ও ডেসিমাল ব্যবহার
                    if Decimal(str(customer.points)) >= Decimal('1000.00') and customer.status != 'active':
                        customer.status = 'active'
                        customer.save()

                return Response({
                    "success": True,
                    "order_id": order.id,
                    "total": float(total_amount), # ফ্রন্টএন্ডে পাঠানোর সময় float করা যেতে পারে
                    "added_points": float(total_pv),
                    "user_status": customer.status
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # এররটা লগ করে রাখা ভালো
            print(f"POS Order Error: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)