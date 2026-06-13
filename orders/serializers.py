from rest_framework import serializers
from .models import Order, OrderItem
from products.models import Product
from django.db import transaction


# =====================================================================
# 🛒 1. ORDER ITEM SERIALIZER (FIXED)
# =====================================================================
class OrderItemSerializer(serializers.ModelSerializer):
    product_image = serializers.SerializerMethodField()
    unit_type = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "product_id",
            "product_name",
            "product_image",
            "quantity",
            "purchase_price",
            "price",
            "profit",
            "point_value",
            "unit_type",
        ]
        # এই ফিল্ডগুলো শুধু দেখাবে, ইনপুট হিসেবে নিবে না
        read_only_fields = ["purchase_price", "profit"]

    def get_unit_type(self, obj):
        try:
            product = Product.objects.get(id=obj.product_id)
            return product.unit_type
        except Exception:
            return "piece"

    # 🔥 [FIXED] অর্ডারের ভেতরের প্রোডাক্ট ইমেজ ডাবল ইউআরএল ও লোকাল ডোমেইন জট ক্লিনআপ মেthod
    def get_product_image(self, obj):
        try:
            # ডাটাবেজ থেকে অর্ডার আইটেমের প্রোডাক্টটি খুঁজে বের করা
            product = Product.objects.get(id=obj.product_id)
            if product.image:
                url_str = str(product.image)

                # যদি ইমেজের ভেতরে ক্লাউডিনারির ডোমেইন থাকে, তবে লোকাল পাথ কেটে ফ্রেশ লিংক বানানো
                if "res.cloudinary.com" in url_str:
                    raw_cloudinary_part = url_str.split("res.cloudinary.com")[-1]
                    return "https://res.cloudinary.com" + raw_cloudinary_part.replace(
                        "%3A", ":"
                    )

                return url_str
        except Exception:
            return None
        return None


# =====================================================================
# 📄 2. ORDER SERIALIZER (FIXED)
# =====================================================================
class OrderSerializer(serializers.ModelSerializer):
    # অর্ডারের সাথে তার আইটেমগুলো দেখানোর জন্য
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "user",
            "name",
            "phone",
            "address",
            "city",
            "courier",
            "purchase_price",
            "subtotal",
            "total_amount",
            "total_pv",
            "payment_method",
            "sender_number",
            "transaction_id",
            "status",
            "created_at",
            "items",
        ]
        # এই ফিল্ডগুলো শুধু সার্ভার থেকে আসবে, ফ্রন্টএন্ড থেকে পাঠানোর দরকার নেই
        read_only_fields = ["id", "order_number", "created_at", "total_pv"]
