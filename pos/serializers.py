from rest_framework import serializers
from products.models import Product
from django.contrib.auth import get_user_model

User = get_user_model()

class POSProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'point_value', 'stock', 'image']

class POSCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'status'] # ফোন ফিল্ড তোর মডেলে থাকলে দিবি