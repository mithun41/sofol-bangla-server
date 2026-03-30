from rest_framework import serializers
from .models import Banner, Category, Product, Cart

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
    original_price = serializers.ReadOnlyField(source='price')
    discount_price = serializers.SerializerMethodField()
    display_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'
        # ✅ নিচের এই লাইনটি যোগ করুন
        extra_kwargs = {
            'is_active': {'read_only': True},
            'barcode_number': {'read_only': True}, # যেহেতু এটা অটো জেনারেট হয়
        } 

    def get_discount_price(self, obj):
        """ইউজার একটিভ থাকলে ডিসকাউন্ট ক্যালকুলেট করা"""
        request = self.context.get('request')
        try:
            # এখানে সরাসরি float না করে Decimal ব্যবহার করা সেফ, তবে তোর আগের লজিক অনুযায়ী float রাখা হলো
            base_price = float(obj.price)
            pv = float(obj.point_value or 0)

            if request and request.user.is_authenticated:
                u_status = getattr(request.user, 'status', '').lower()
                
                # যদি ইউজার একটিভ থাকে এবং অ্যাডমিন/স্টাফ না হয় তবেই ডিসকাউন্ট
                if u_status == 'active' and not request.user.is_staff:
                    # তোর লজিক: প্রাইস - (পয়েন্ট * ২)
                    return round(base_price - (pv * 2), 2)
        except (ValueError, TypeError):
            pass
        
        return None

    def get_display_price(self, obj):
        """ফ্রন্টএন্ডে যেটা মেইন প্রাইস হিসেবে দেখাবে"""
        discount = self.get_discount_price(obj)
        return discount if discount is not None else float(obj.price)

    def validate(self, data):
        """
        অ্যাডমিন প্যানেল থেকে ডাটা সেভ করার সময় ভ্যালিডেশন।
        একই মেথড একবার লিখলেই যথেষ্ট।
        """
        request = self.context.get('request')
        if request and request.method in ['POST', 'PUT', 'PATCH']:
            # ইনপুট থেকে সরাসরি ভ্যালু নিয়ে ডাটাতে সেট করা
            if 'price' in request.data:
                data['price'] = request.data['price']
            if 'point_value' in request.data:
                data['point_value'] = request.data['point_value']
        return data

class CartSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    product_pv = serializers.SerializerMethodField()
    item_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'product', 'product_name', 'product_price', 
            'product_image', 'product_pv', 'quantity', 'item_subtotal'
        ]

    def get_user_status(self, request):
        """ইউজার একটিভ কি না তা চেক করার কমন ফাংশন"""
        if not request or not request.user.is_authenticated:
            return None
        
        user = request.user
        # ইউজার মডেল বা প্রোফাইল মডেল চেক করা
        u_status = getattr(user, 'status', '').lower()
        if not u_status and hasattr(user, 'profile'):
            u_status = getattr(user.profile, 'status', '').lower()
        return u_status

    def get_product_price(self, obj):
        request = self.context.get('request')
        product = obj.product if hasattr(obj, 'product') else obj.get('product')
        
        if not product: return 0

        base_price = float(product.price)
        pv = float(product.point_value or 0)
        
        # একটিভ মেম্বার হলে ডিসকাউন্ট (Price - PV*2)
        if self.get_user_status(request) == 'active':
            return base_price - (pv * 2) 
        return base_price

    def get_product_pv(self, obj):
        request = self.context.get('request')
        product = obj.product if hasattr(obj, 'product') else obj.get('product')
        
        if not product: return 0

        # মামা, এখানে খেয়াল কর: একটিভ ইউজার কি আসলেই ০ পিভি পাবে? 
        # যদি তাই হয় তবে এই লজিক ঠিক আছে।
        if self.get_user_status(request) == 'active':
            return 0 
        return float(product.point_value or 0)

    def get_item_subtotal(self, obj):
        # প্রাইস ইনটু কোয়ান্টিটি
        price = self.get_product_price(obj)
        quantity = obj.quantity if hasattr(obj, 'quantity') else obj.get('quantity', 0)
        return round(price * quantity, 2) # ২ দশমিক ঘর পর্যন্ত রাউন্ড করে দিলাম

    def get_product_image(self, obj):
        request = self.context.get('request')
        product = obj.product if hasattr(obj, 'product') else obj.get('product')
        
        if product and product.image:
            return request.build_absolute_uri(product.image.url) if request else product.image.url
        return None

class BannerSerializer(serializers.ModelSerializer):
    # ইমেজ ফিল্ডকে সাধারণভাবেই রাখ যেন রিড/রাইট দুইটাই হয়
    # জ্যাঙ্গো নিজেই ফুল ইউআরএল হ্যান্ডেল করবে
    class Meta:
        model = Banner
        fields = ['id', 'title', 'image', 'link', 'is_active', 'created_at']