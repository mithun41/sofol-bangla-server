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
    # নতুন একটা ফিল্ড যোগ করছি যা ফ্রন্টএন্ডে ডিসকাউন্ট প্রাইস দেখাবে
    discounted_price = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = Product
        # '__all__' এর বদলে সব ফিল্ড স্পেসিফিক করে দেওয়া ভালো অথবা এভাবেই থাক
        fields = '__all__'

    def get_discounted_price(self, obj):
        request = self.context.get('request')
        base_price = float(obj.price)
        
        # ১. চেক করো ইউজার লগইন আছে কি না
        if request and request.user.is_authenticated:
            # ২. অ্যাডমিন বা স্টাফ হলে ডিসকাউন্ট দেখানোর দরকার নেই
            if request.user.is_staff:
                return base_price
            
            user = request.user
            u_status = ""
            
            # ৩. ইউজারের স্ট্যাটাস বের করা
            if hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()
            elif hasattr(user, 'status'):
                u_status = getattr(user, 'status', '').lower()

            # ৪. যদি একটিভ মেম্বার হয়, তবে ২ গুণ পয়েন্ট ডিসকাউন্ট
            if u_status == 'active':
                pv = float(obj.point_value or 0)
                return base_price - (pv * 2)

        # লগইন না থাকলে বা একটিভ না হলে রেগুলার প্রাইস
        return base_price
        





class CartSerializer(serializers.ModelSerializer):
    # রিড-অনলি ফিল্ড যা সরাসরি মডেল থেকে ডাটা আনবে
    product_name = serializers.ReadOnlyField(source='product.name')
    product_pv = serializers.ReadOnlyField(source='product.point_value')
    
    # মেথড ফিল্ড যা লজিক্যালি ক্যালকুলেট হবে
    product_image = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    item_subtotal = serializers.SerializerMethodField() # ব্যাকএন্ড থেকে পাঠানো সাবটোটাল

    class Meta:
        model = Cart
        fields = [
            'id', 
            'product', 
            'product_name', 
            'product_price', 
            'product_image', 
            'product_pv', 
            'quantity', 
            'item_subtotal'
        ]

    def get_product_image(self, obj):
        request = self.context.get('request')
        # ডিকশনারি বা অবজেক্ট হ্যান্ডেল করার জন্য সেফ চেক
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        
        if product and product.image:
            if request:
                return request.build_absolute_uri(product.image.url)
            return product.image.url
        return None

    def get_product_price(self, obj):
        request = self.context.get('request')
        product = obj.get('product') if isinstance(obj, dict) else obj.product
        
        if not product:
            return 0.0

        base_price = float(product.price)
        
        # ইউজার লগইন থাকলে এবং স্ট্যাটাস Active হলে PV মাইনাস হবে (ডিসকাউন্ট)
        if request and request.user.is_authenticated:
            if request.user.is_staff: 
             return float(product.price)
            user = request.user
            u_status = ""
            if hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()
            elif hasattr(user, 'status'):
                u_status = getattr(user, 'status', '').lower()

            if u_status == 'active':
                pv = float(product.point_value or 0)
                return base_price - (pv * 2)
                
        return base_price

    def get_item_subtotal(self, obj):
        """
        এখানে সরাসরি এপিআই থেকে (Price * Quantity) ক্যালকুলেট করে পাঠানো হচ্ছে।
        """
        price = self.get_product_price(obj)
        qty = obj.quantity if not isinstance(obj, dict) else obj.get('quantity', 0)
        return float(price) * int(qty)