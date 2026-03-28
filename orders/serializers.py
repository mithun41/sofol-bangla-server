from rest_framework import serializers
from .models import Order, OrderItem
from products.models import Product
from django.db import transaction

class OrderItemSerializer(serializers.ModelSerializer):
    # প্রোডাক্টের ইমেজ দেখানোর জন্য নতুন ফিল্ড
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'product_image', 'quantity', 'price', 'point_value']

    def get_product_image(self, obj):
        try:
            # OrderItem এ থাকা product_id দিয়ে Product অবজেক্ট খুঁজে বের করা
            product = Product.objects.get(id=obj.product_id)
            if product.image:
                request = self.context.get('request')
                if request:
                    # এটি ইমেজের পূর্ণ ইউআরএল (http://domain.com/media/...) তৈরি করবে
                    return request.build_absolute_uri(product.image.url)
                return product.image.url
        except Product.DoesNotExist:
            return None
        return None

class OrderSerializer(serializers.ModelSerializer):
    # অর্ডারের সাথে তার আইটেমগুলো দেখানোর জন্য
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 
            'order_number', 
            'user', 
            'name', 
            'phone', 
            'address', 
            'city', 
            'courier',
            'subtotal', 
            'total_amount', 
            'total_pv',
            'payment_method', 
            'sender_number', 
            'transaction_id', 
            'status', 
            'created_at', 
            'items'
        ]
        # এই ফিল্ডগুলো শুধু সার্ভার থেকে আসবে, ফ্রন্টএন্ড থেকে পাঠানোর দরকার নেই
        read_only_fields = ['id', 'order_number', 'created_at', 'total_pv']