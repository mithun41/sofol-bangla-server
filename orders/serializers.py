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
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user', 'name', 'phone', 'address', 'city', 'courier',
            'subtotal', 'shipping_cost', 'total_amount', 
            'payment_method', 'sender_number', 'transaction_id', 
            'status', 'points_awarded', 'created_at', 'items'
        ]
        read_only_fields = ['order_number', 'points_awarded', 'created_at']

    def create(self, validated_data):
        items_data = self.context.get('request').data.get('items', [])
        
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            
            for item in items_data:
                try:
                    product = Product.objects.get(id=item['product_id'])
                except Product.DoesNotExist:
                    raise serializers.ValidationError(f"Product ID {item['product_id']} not found.")

                qty = int(item['quantity'])
                
                if product.stock < qty:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product.name}. Available: {product.stock}"
                    )
                
                product.stock -= qty
                product.save()
                
                OrderItem.objects.create(
                    order=order,
                    product_id=item['product_id'],
                    product_name=item['product_name'],
                    quantity=qty,
                    price=item['price'],
                    point_value=item.get('point_value', 0)
                )
            
            return order