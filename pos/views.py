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
from rest_framework import permissions


class IsPOSAdminOrAdmin(permissions.BasePermission):
    """
    ইউজার যদি 'admin' অথবা 'posAdmin' রোলের হয়, তবেই অ্যাক্সেস পাবে।
    """

    def has_permission(self, request, view):
        # ইউজারকে অবশ্যই লগইন করা থাকতে হবে
        if not request.user or not request.user.is_authenticated:
            return False

        # রোলের ভিত্তিতে পারমিশন চেক
        return request.user.role in ["admin", "posAdmin"]


# ১. প্রোডাক্ট সার্চ (বারকোড নম্বর, নাম বা আইডি দিয়ে)
class POSProductSearch(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPOSAdminOrAdmin]

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
    permission_classes = [IsPOSAdminOrAdmin]

    def get(self, request):
        query = request.query_params.get('q', '')
        customers = User.objects.filter(
            Q(username__icontains=query) | Q(phone__icontains=query)
        )[:5]
        serializer = POSCustomerSerializer(customers, many=True)
        return Response(serializer.data)

# ৩. অর্ডার তৈরি লজিক (মেম্বার ডিসকাউন্ট এবং পয়েন্ট ডিস্ট্রিবিউশন)

# pos/views.py এ POSOrderCreate class replace করো

class POSOrderCreate(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPOSAdminOrAdmin]

    def post(self, request):
        data        = request.data
        customer_id = data.get("customer_id")
        items       = data.get("items", [])
        discount    = Decimal(str(data.get("discount_amount", "0") or "0"))

        if not customer_id or not items:
            return Response({"error": "তথ্য অসম্পূর্ণ!"}, status=400)

        customer = User.objects.filter(id=customer_id).first()
        if not customer:
            return Response({"error": "কাস্টমার পাওয়া যায়নি!"}, status=404)

        try:
            with transaction.atomic():
                is_active = str(getattr(customer, "status", "")).lower().strip() == "active"

                total_amount  = Decimal("0.00")
                total_pv      = Decimal("0.00")
                order_items   = []

                for item in items:
                    product = Product.objects.select_for_update().get(id=item["product_id"])
                    qty     = Decimal(str(item.get("quantity", "1")))

                    if product.stock < int(qty):
                        raise Exception(f"{product.name} আউট অফ স্টক!")

                    original_price = Decimal(str(product.price))
                    pv_unit        = Decimal(str(product.point_value or "0"))

                    if is_active:
                        final_price = original_price - (pv_unit * Decimal("2"))
                        final_pv    = Decimal("0")
                    else:
                        final_price = original_price
                        final_pv    = pv_unit

                    total_amount += final_price * qty
                    total_pv     += final_pv * qty

                    order_items.append({
                        "product_id":    product.id,
                        "product_name":  product.name,
                        "quantity":      int(qty),
                        "price":         final_price,
                        "point_value":   final_pv,
                        "purchase_price": Decimal(str(product.purchase_price or "0")),
                    })

                # Apply discount
                discounted_total = max(total_amount - discount, Decimal("0"))

                order = Order.objects.create(
                    user=customer,
                    name=customer.name or customer.username,
                    phone=getattr(customer, "phone", ""),
                    address="POS Counter Sale",
                    subtotal=discounted_total,
                    total_amount=discounted_total,
                    total_pv=total_pv,
                    status="Completed",
                    payment_method=data.get("payment_method", "Cash"),
                )

                for oi in order_items:
                    OrderItem.objects.create(
                        order=order,
                        product_id=oi["product_id"],
                        product_name=oi["product_name"],
                        quantity=oi["quantity"],
                        price=oi["price"],
                        purchase_price=oi["purchase_price"],
                        point_value=oi["point_value"],
                    )

                if total_pv > Decimal("0"):
                    try:
                        distribute_money_to_funds(customer, float(total_pv))
                    except Exception as e:
                        print(f"Distribution Error: {e}")

                return Response({
                    "success":      True,
                    "order_id":     order.id,
                    "total":        float(discounted_total),
                    "discount":     float(discount),
                    "added_points": float(total_pv),
                    "user_status":  customer.status,
                }, status=201)

        except Exception as e:
            print(f"POS ERROR: {e}")
            return Response({"error": str(e)}, status=400)