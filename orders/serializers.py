from rest_framework import serializers
from .models import Order, OrderItem
from products.models import Product
from django.db import transaction


class OrderItemSerializer(serializers.ModelSerializer):
    product_image = serializers.SerializerMethodField()

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
        ]
        # এই ফিল্ডগুলো শুধু দেখাবে, ইনপুট হিসেবে নিবে না
        read_only_fields = ["purchase_price", "profit"]

    def get_product_image(self, obj):
        try:
            # ইমেজ লজিক ঠিক আছে
            from products.models import Product

            product = Product.objects.get(id=obj.product_id)
            if product.image:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(product.image.url)
                return product.image.url
        except Exception:
            return None
        return None


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
        read_only_fields = ['id', 'order_number', 'created_at', 'total_pv']
