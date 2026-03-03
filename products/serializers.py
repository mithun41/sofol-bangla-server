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
        # obj.product না থাকলে বা ইমেজ না থাকলে সেফলি হ্যান্ডেল করা
        if obj.product and obj.product.image:
            if request:
                return request.build_absolute_uri(obj.product.image.url)
            return obj.product.image.url
        return None

    def get_product_price(self, obj):
        request = self.context.get('request')
        base_price = float(obj.product.price)
        
        # যদি রিকোয়েস্ট না থাকে বা ইউজার লগইন না থাকে, তবে নরমাল দাম দেখাবে
        if not request or not request.user.is_authenticated:
            return base_price

        user = request.user
        pv = float(obj.product.point_value or 0)

        # ইউজার অ্যাক্টিভ কি না চেক করে ডিসকাউন্ট লজিক
        u_status = ""
        if hasattr(user, 'profile'):
            u_status = getattr(user.profile, 'status', '').lower()
        elif hasattr(user, 'status'):
            u_status = getattr(user, 'status', '').lower()

        if u_status == 'active':
            return base_price - pv
        return base_price