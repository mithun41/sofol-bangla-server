from rest_framework import serializers
from products.models import Product
from django.contrib.auth import get_user_model
from decimal import Decimal # ✅ ডেসিমাল ইম্পোর্ট করুন

User = get_user_model()

class POSProductSerializer(serializers.ModelSerializer):
    member_price = serializers.SerializerMethodField()
    potential_discount = serializers.SerializerMethodField()
    # আগেরবার যেটা বলেছিলাম, ইমেজ দেখার জন্য এটা যোগ করে নিন
    barcode_image = serializers.ImageField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'price', 'stock', 'image',
            'point_value', 'barcode_number', 'barcode_image',
            'member_price', 'potential_discount'
        ]

    def get_member_price(self, obj):
        # ✅ ১ পয়েন্ট = ২ টাকা অফার অনুযায়ী মেম্বার প্রাইস
        # Decimal এর সাথে float মেশানো যাবে না, তাই সব Decimal এ রাখা হলো
        price = obj.price or Decimal('0.00')
        pv = Decimal(str(obj.point_value or 0))
        discount_rate = Decimal('2.00')
        
        return price - (pv * discount_rate)

    def get_potential_discount(self, obj):
        # ✅ কত টাকা ছাড় পাবে
        pv = Decimal(str(obj.point_value or 0))
        discount_rate = Decimal('2.00')
        return pv * discount_rate

class POSCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'status']