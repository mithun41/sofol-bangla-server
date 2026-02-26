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
    # তোর ফ্রন্টএন্ড এই নামটা খুঁজছে, তাই আমরা এটাই পাঠাবো
    product_price = serializers.SerializerMethodField() 
    product_pv = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'product', 'product_name', 'product_price', 
            'product_pv', 'product_image', 'quantity', 'subtotal'
        ]
        read_only_fields = ['user']

    def get_product_price(self, obj):
     product = obj.product
     request = self.context.get('request')
    
     price = float(product.price or 0)
     pv = float(product.point_value or 0)
    
     if request and request.user.is_authenticated:
        # প্রোফাইল থেকে স্ট্যাটাস চেক করা
        user_status = ""
        if hasattr(request.user, 'profile'):
            # সরাসরি স্ট্যাটাস ফিল্ড থেকে ভ্যালু নেওয়া (active/inactive)
            user_status = getattr(request.user.profile, 'status', '').lower()
        elif hasattr(request.user, 'status'):
            user_status = getattr(request.user, 'status', '').lower()
            
        # যদি স্ট্যাটাস ঠিক 'active' হয়, তবেই ডিসকাউন্ট পাবে
        if user_status == 'active':
            return price - pv
            
     return price

    def get_product_pv(self, obj):
        return float(obj.product.point_value or 0)

    def get_subtotal(self, obj):
        # ডাইনামিক প্রাইস * কোয়ান্টিটি
        price = self.get_product_price(obj)
        return price * obj.quantity

    def get_product_image(self, obj):
        product = obj.product
        request = self.context.get('request')
        if product.image:
            # ফুল URL জেনারেট করা যেন ফ্রন্টএন্ডে ইমেজ শো করে
            return request.build_absolute_uri(product.image.url) if request else product.image.url
        return None