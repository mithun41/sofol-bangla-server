from decimal import Decimal

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
    category_name = serializers.ReadOnlyField(source="category.name")
    unit_display = serializers.CharField(source="get_unit_type_display", read_only=True)

    # আগের ফরম্যাটের ক্যালকুলেটেড ফিল্ডস
    original_price = serializers.ReadOnlyField(source="price")
    discount_price = serializers.SerializerMethodField()
    display_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "slug",
            "description",
            "purchase_price",  # আগের ফিল্ড ফিরিয়ে আনা হলো
            "price",
            "unit_type",
            "unit_display",
            "stock",
            "point_value",
            "image",
            "barcode_number",
            "barcode_image",
            "is_active",
            "is_featured",  # আগের ফিল্ড ফিরিয়ে আনা হলো
            "original_price",
            "discount_price",
            "display_price",
            "created_at",
        ]
        extra_kwargs = {
            "is_active": {"read_only": True},
            "barcode_number": {"read_only": True},
            "barcode_image": {"read_only": True},
        }

    def get_discount_price(self, obj):
        """ইউজার একটিভ থাকলে ডিসকাউন্ট ক্যালকুলেট করা (Price - PV*2)"""
        request = self.context.get("request")
        try:
            base_price = Decimal(str(obj.price))
            pv = Decimal(str(obj.point_value or 0))

            if request and request.user.is_authenticated:
                u_status = getattr(request.user, "status", "").lower().strip()

                # একটিভ ইউজার হলে (কিন্তু অ্যাডমিন না হলে) ডিসকাউন্ট পাবে
                if u_status == "active" and not request.user.is_staff:
                    discounted = base_price - (pv * Decimal("2.0"))
                    return float(round(discounted, 2))
        except (ValueError, TypeError, Exception):
            pass
        return None

    def get_display_price(self, obj):
        """ফ্রন্টএন্ডে যেটা মেইন প্রাইস হিসেবে দেখাবে"""
        discount = self.get_discount_price(obj)
        return discount if discount is not None else float(obj.price)

    def validate(self, data):
        """
        স্টক যেন পজিটিভ থাকে তা নিশ্চিত করা এবং ইনপুট ভ্যালিডেশন।
        """
        # আপডেট বা ক্রিয়েট করার সময় স্টক চেক
        stock_val = data.get("stock", 0)
        try:
            if float(stock_val) < 0:
                raise serializers.ValidationError(
                    {"stock": "মামা, স্টক তো নেগেটিভ হইতে পারে না!"}
                )
        except (ValueError, TypeError):
            pass

        return data


class CartSerializer(serializers.ModelSerializer):
    unit_type = serializers.ReadOnlyField(source="product.unit_type")
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    product_pv = serializers.SerializerMethodField()
    item_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "product",
            "product_name",
            "product_price",
            "product_image",
            "product_pv",
            "unit_type",
            "quantity",
            "item_subtotal",
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
        price = float(obj.product.price)
        quantity = float(obj.quantity)

        return round(price * quantity, 2)  # ২ দশমিক ঘর পর্যন্ত রাউন্ড করে দিলাম

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
