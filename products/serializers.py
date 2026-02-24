from rest_framework import serializers
from .models import Category, Product, Cart

class CategorySerializer(serializers.ModelSerializer):
    # ইমেজ ফিল্ডটি আগের মতোই থাকল
    image = serializers.ImageField(required=False, allow_null=True)
    
    # সাব-ক্যাটাগরির লিস্ট দেখানোর জন্য (Read Only)
    subcategories = serializers.SerializerMethodField()
    
    # প্যারেন্ট ক্যাটাগরির নাম দেখানোর জন্য (ঐচ্ছিক, ফ্রন্টএন্ডে সুবিধা হবে)
    parent_name = serializers.ReadOnlyField(source='parent.name')

    class Meta:
        model = Category
        # 'parent' ফিল্ডটি এখানে যোগ করা হয়েছে যাতে সাব-ক্যাটাগরি সেভ করা যায়
        fields = ['id', 'name', 'slug', 'image', 'parent', 'parent_name', 'subcategories']

    def get_subcategories(self, obj):
        # যদি এই ক্যাটাগরির আন্ডারে কোনো সাব-ক্যাটাগরি থাকে তবে সেগুলো দেখাবে
        serializer = CategorySerializer(obj.subcategories.all(), many=True)
        return serializer.data

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Product
        fields = '__all__'
        
class CartSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_price = serializers.ReadOnlyField(source='product.price')
    product_pv = serializers.ReadOnlyField(source='product.point_value')
    product_image = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'product', 'product_name', 'product_price', 
            'product_pv', 'product_image', 'quantity', 'subtotal'
        ]
        read_only_fields = ['user']

    def get_product_image(self, obj):
        # এরর ফিক্স: obj যদি ডিকশনারি হয় (POST রিকোয়েস্টের সময়)
        product = obj['product'] if isinstance(obj, dict) else obj.product
        
        request = self.context.get('request')
        if product and product.image:
            if request:
                return request.build_absolute_uri(product.image.url)
            return product.image.url
        return None

    def get_subtotal(self, obj):
        # এরর ফিক্স: obj যদি ডিকশনারি হয়
        if isinstance(obj, dict):
            product = obj['product']
            quantity = obj['quantity']
        else:
            product = obj.product
            quantity = obj.quantity
            
        return product.price * quantity