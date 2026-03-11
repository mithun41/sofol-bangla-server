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
        serializer = CategorySerializer(
            obj.subcategories.all(), 
            many=True, 
            context={'request': self.context.get('request')}
        )
        return serializer.data

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    # নাম আগের মতোই রাখলাম, শুধু এগুলোকে মেথড ফিল্ড বানালাম
    price = serializers.SerializerMethodField()
    point_value = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category_name', 'price', 
            'point_value', 'stock', 'image', 'barcode_number', 
            'is_active', 'created_at'
        ]

    def get_user_status(self, request):
        if request and request.user.is_authenticated:
            user = request.user
            if user.is_staff: return "inactive" 
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()
            return u_status.strip()
        return "inactive"

    def get_price(self, obj):
        request = self.context.get('request')
        status = self.get_user_status(request)
        base_price = float(obj.price)
        
        if status == 'active':
            pv = float(obj.point_value or 0)
            return max(0, base_price - (pv * 2)) # ২ টাকা ডিসকাউন্ট
        return base_price

    def get_point_value(self, obj):
        request = self.context.get('request')
        status = self.get_user_status(request)
        
        if status == 'active':
            return 0 # একটিভ হলে পয়েন্ট ০
        return obj.point_value


class CartSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    
    # product_pv এখন MethodField হবে যাতে আমরা কন্ডিশন বসাতে পারি
    product_pv = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    item_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'product', 'product_name', 'product_price', 
            'product_image', 'product_pv', 'quantity', 'item_subtotal'
        ]

    def get_product_pv(self, obj):
        """ইউজার একটিভ হলে পয়েন্ট ০ দেখাবে, ইন-একটিভ হলে ফুল পয়েন্ট"""
        request = self.context.get('request')
        product = obj.product if not isinstance(obj, dict) else obj.get('product')
        
        if not product: return 0

        # ইউজার স্ট্যাটাস চেক
        if request and request.user.is_authenticated:
            user = request.user
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()
            
            if u_status == 'active':
                return 0 # ✅ একটিভ মেম্বার ডিসকাউন্ট পায় তাই পয়েন্ট ০
        
        return product.point_value # ✅ ইন-একটিভ মেম্বার ফুল পয়েন্ট পাবে

    def get_product_image(self, obj):
        request = self.context.get('request')
        product = obj.product if not isinstance(obj, dict) else obj.get('product')
        if product and product.image:
            if request:
                return request.build_absolute_uri(product.image.url)
            return product.image.url
        return None

    def get_product_price(self, obj):
        request = self.context.get('request')
        product = obj.product if not isinstance(obj, dict) else obj.get('product')
        if not product: return 0.0

        base_price = float(product.price)
        
        if request and request.user.is_authenticated:
            if request.user.is_staff: return base_price
            
            user = request.user
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()

            if u_status == 'active':
                pv = float(product.point_value or 0)
                return base_price - (pv * 2) # ১ পয়েন্ট = ২ টাকা ছাড়
                
        return base_price

    def get_item_subtotal(self, obj):
        price = self.get_product_price(obj)
        qty = obj.quantity if not isinstance(obj, dict) else obj.get('quantity', 0)
        return float(price) * int(qty)