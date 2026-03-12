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
    
    price = serializers.SerializerMethodField()
    point_value = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'

    def get_price(self, obj):
        request = self.context.get('request')
        base_price = float(obj.price)
        pv = float(obj.point_value or 0)
        final_price = base_price

        if request and request.user.is_authenticated:
            if request.user.is_staff:
                final_price = base_price
            else:
                u_status = getattr(request.user, 'status', '').lower()
                if not u_status and hasattr(request.user, 'profile'):
                    u_status = getattr(request.user.profile, 'status', '').lower()

                if u_status == 'active':
                    final_price = base_price - (pv * 2)
        
        # ✅ float কে string এ রূপান্তর (২ দশমিক ঘর সহ)
        return "{:.2f}".format(final_price)

    def get_point_value(self, obj):
        request = self.context.get('request')
        # মডেলে IntegerField থাকায় সরাসরি ভ্যালু নিচ্ছি
        current_pv = obj.point_value or 0
        
        if request and request.user.is_authenticated:
            # অ্যাডমিন হলে অরিজিনাল পয়েন্ট নাম্বার হিসেবে যাবে
            if request.user.is_staff:
                return int(current_pv)

            # মেম্বার চেক
            u_status = getattr(request.user, 'status', '').lower()
            if not u_status and hasattr(request.user, 'profile'):
                u_status = getattr(request.user.profile, 'status', '').lower()

            # একটিভ মেম্বার হলে ০ (নাম্বার হিসেবে)
            if u_status == 'active':
                return 0 
        
        # ডিফল্টভাবে পূর্ণসংখ্যা (Number) হিসেবে রিটার্ন করবে
        return int(current_pv)

    def validate(self, data):
        """
        এই মেথডটি নিশ্চিত করে যে অ্যাডমিন থেকে ডাটা আপডেট করার সময় 
        অরিজিনাল ভ্যালুগুলোই সেভ হচ্ছে।
        """
        request = self.context.get('request')
        if request and request.method in ['POST', 'PUT', 'PATCH']:
            # ইনপুট ডাটা থেকে অরিজিনাল ভ্যালু সেট করা
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

    def get_product_price(self, obj):
        request = self.context.get('request')
        
        # মামা, এখানে ডিকশনারি এবং অবজেক্ট দুইটাই হ্যান্ডেল করা হয়েছে
        if isinstance(obj, dict):
            product = obj.get('product')
        else:
            product = getattr(obj, 'product', None)

        if not product:
            return 0

        base_price = float(product.price)
        pv = float(product.point_value or 0)

        if request and request.user.is_authenticated:
            user = request.user
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()

            if u_status == 'active':
                return base_price - (pv * 2) 
        return base_price

    def get_product_pv(self, obj):
        request = self.context.get('request')
        
        if isinstance(obj, dict):
            product = obj.get('product')
        else:
            product = getattr(obj, 'product', None)

        if not product:
            return 0

        if request and request.user.is_authenticated:
            user = request.user
            u_status = getattr(user, 'status', '').lower()
            if not u_status and hasattr(user, 'profile'):
                u_status = getattr(user.profile, 'status', '').lower()

            if u_status == 'active':
                return 0 
        return product.point_value

    def get_item_subtotal(self, obj):
        price = self.get_product_price(obj)
        quantity = obj.get('quantity') if isinstance(obj, dict) else getattr(obj, 'quantity', 0)
        return price * quantity

    def get_product_image(self, obj):
        request = self.context.get('request')
        
        if isinstance(obj, dict):
            product = obj.get('product')
        else:
            product = getattr(obj, 'product', None)

        if product and product.image:
            return request.build_absolute_uri(product.image.url) if request else product.image.url
        return None