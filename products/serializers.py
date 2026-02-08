from rest_framework import serializers
from .models import Product, Category

class CategorySerializer(serializers.ModelSerializer):
    # ইমেজ ফিল্ডটি যোগ করুন যাতে এটি মেথড অনুযায়ী URL রিটার্ন করে
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image']

class ProductSerializer(serializers.ModelSerializer):
    # ক্যাটাগরির নাম দেখানোর জন্য (ঐচ্ছিক)
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Product
        fields = '__all__'