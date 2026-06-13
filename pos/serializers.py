from rest_framework import serializers
from products.models import Product
from django.contrib.auth import get_user_model
from decimal import Decimal # ✅ ডেসিমাল ইম্পোর্ট করুন

User = get_user_model()

from rest_framework import serializers
from products.models import Product
from decimal import Decimal


class POSProductSerializer(serializers.ModelSerializer):
    # ইমেজ দেখার জন্য এটা রাখা হয়েছে
    barcode_image = serializers.ImageField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "price",
            "stock",
            "unit_type",
            "image",
            "point_value",
            "barcode_number",
            "barcode_image",
        ]


class POSCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "phone", "status"]
