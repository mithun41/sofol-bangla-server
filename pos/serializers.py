from rest_framework import serializers
from products.models import Product
from django.contrib.auth import get_user_model

User = get_user_model()

class POSProductSerializer(serializers.ModelSerializer):
    # মেম্বারদের জন্য ক্যালকুলেটেড প্রাইস দেখানোর জন্য অতিরিক্ত ফিল্ড
    member_price = serializers.SerializerMethodField()
    potential_discount = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'price', 'stock', 
            'point_value', 'barcode_number', 
            'member_price', 'potential_discount'
        ]

    def get_member_price(self, obj):
        # ✅ ১ পয়েন্ট = ২ টাকা অফার অনুযায়ী মেম্বার প্রাইস
        price = float(obj.price or 0)
        pv = float(obj.point_value or 0)
        return price - (pv * 2)

    def get_potential_discount(self, obj):
        # কত টাকা ছাড় পাবে সেটা দেখানোর জন্য
        pv = float(obj.point_value or 0)
        return pv * 2

class POSCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'status']