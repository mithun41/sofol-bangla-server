from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from products.models import Product
from orders.models import Order, OrderItem
from .serializers import POSProductSerializer, POSCustomerSerializer
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class POSProductSearch(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q', '')
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(id__icontains=query),
            is_active=True
        )[:10]
        serializer = POSProductSerializer(products, many=True)
        return Response(serializer.data)

class POSCustomerSearch(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        query = request.query_params.get('q', '')
        customers = User.objects.filter(
            Q(username__icontains=query) | Q(phone__icontains=query)
        )[:5]
        serializer = POSCustomerSerializer(customers, many=True)
        return Response(serializer.data)

class POSOrderCreate(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        data = request.data
        customer_id = data.get('customer_id')
        items = data.get('items', []) # [{'product_id': 1, 'quantity': 2}]

        if not items:
            return Response({"error": "কার্ট খালি!"}, status=400)

        try:
            with transaction.atomic():
                # ১. কাস্টমার ডিটেকশন
                customer = User.objects.get(id=customer_id) if customer_id else None
                is_active = (getattr(customer, 'status', '').lower() == 'active') if customer else False

                total_amount = 0
                total_pv = 0
                order_items_to_create = []

                # ২. প্রোডাক্ট প্রসেসিং ও স্টক আপডেট
                for item in items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])

                    if product.stock < qty:
                        raise Exception(f"{product.name} আউট অফ স্টক!")

                    # ডিসকাউন্ট লজিক
                    price = float(product.price)
                    pv = float(product.point_value or 0)
                    
                    if is_active:
                        final_price = price - pv
                        final_pv = 0
                    else:
                        final_price = price
                        final_pv = pv

                    total_amount += (final_price * qty)
                    total_pv += (final_pv * qty)

                    # স্টক কমানো
                    product.stock -= qty
                    product.save()

                    order_items_to_create.append({
                        'product': product,
                        'qty': qty,
                        'price': final_price,
                        'pv': final_pv
                    })

                # ৩. অর্ডার সেভ করা
                order = Order.objects.create(
                    user=customer,
                    total_amount=total_amount,
                    total_pv=total_pv,
                    status='Completed', # POS অর্ডার সাধারণত সাথে সাথে কমপ্লিট হয়
                    payment_method=data.get('payment_method', 'Cash'),
                    name=customer.username if customer else "Walking Customer",
                )

                # ৪. আইটেম সেভ করা
                for oi in order_items_to_create:
                    OrderItem.objects.create(
                        order=order,
                        product=oi['product'],
                        quantity=oi['qty'],
                        price=oi['price'],
                        point_value=oi['pv']
                    )

                return Response({
                    "message": "বিক্রি সফল হয়েছে!",
                    "order_id": order.id,
                    "total": total_amount
                }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=400)