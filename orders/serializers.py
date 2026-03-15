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
            'subtotal', 'total_amount', 'total_pv',
            'payment_method', 'sender_number', 'transaction_id', 
            'status', 'created_at', 'items'
        ]
        read_only_fields = ['order_number', 'total_pv', 'created_at', 'total_amount']

    def create(self, validated_data):
        request = self.context.get('request')
        items_data = request.data.get('items', [])
        user = request.user
        
        # ইউজার স্ট্যাটাস চেক (অফার লজিকের জন্য)
        is_active = False
        if user.is_authenticated:
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()
            is_active = (u_status == 'active')

        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            total_points = 0
            
            for item in items_data:
                try:
                    product = Product.objects.get(id=item['product_id'])
                except Product.DoesNotExist:
                    raise serializers.ValidationError(f"Product ID {item['product_id']} not found.")

                qty = int(item['quantity'])
                if product.stock < qty:
                    raise serializers.ValidationError(f"Insufficient stock for {product.name}.")

                # স্টক কমানো
                product.stock -= qty
                product.save()

                # ✅ অফার লজিক প্রয়োগ: 
                # ইউজার একটিভ হলে পয়েন্ট ০, নতুবা মডেলে যা আছে তাই।
                current_pv = 0 if is_active else product.point_value
                
                # ইন-একটিভ ইউজারের জন্য পয়েন্ট যোগ করা (অর্ডারের মোট পয়েন্টের জন্য)
                total_points += (current_pv * qty)

                OrderItem.objects.create(
                    order=order,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=qty,
                    price=item['price'], # ফ্রন্টএন্ড থেকে আসা ক্যালকুলেটেড প্রাইস
                    point_value=current_pv
                )
            
            # অর্ডারে মোট কত পয়েন্ট পেল তা সেভ করা
            order.points_awarded = total_points
            order.save()
            
            return order