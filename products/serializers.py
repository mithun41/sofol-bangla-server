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
    # এই ফিল্ডগুলো রিড-অনলি হিসেবে থাকবে যা ফ্রন্টএন্ডে ডাটা দেখাবে
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    product_pv = serializers.ReadOnlyField(source='product.point_value')

    class Meta:
        model = Cart
        fields = ['id', 'product', 'product_name', 'product_price', 'product_image', 'product_pv', 'quantity']

    def get_product_image(self, obj):
        request = self.context.get('request')
        # যদি obj ডিকশনারি হয় তবে গেট ব্যবহার করো, নাহলে ডট
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        
        if product and product.image:
            if request:
                return request.build_absolute_uri(product.image.url)
            return product.image.url
        return None

    def get_product_price(self, obj):
        request = self.context.get('request')
        # ডিকশনারি কি না চেক করে প্রোডাক্ট বের করা
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        
        if not product:
            return 0.0

        base_price = float(product.price)
        
        if not request or not request.user.is_authenticated:
            return base_price

        user = request.user
        pv = float(product.point_value or 0)

        u_status = ""
        if hasattr(user, 'profile'):
            u_status = getattr(user.profile, 'status', '').lower()
        elif hasattr(user, 'status'):
            u_status = getattr(user, 'status', '').lower()

        if u_status == 'active':
            return base_price - pv
        return base_price