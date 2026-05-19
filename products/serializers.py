from decimal import Decimal

from rest_framework import serializers
from .models import Banner, Category, Product, Cart


class CategorySerializer(serializers.ModelSerializer):
    # 👇 ইমেজ ফিল্ডটিকে মেথড ফিল্ড করা হলো যাতে ডাবল লিংক ট্রিম করা যায়
    image = serializers.SerializerMethodField()

    # সাব-ক্যাটাগরির লিস্ট দেখানোর জন্য (Read Only)
    subcategories = serializers.SerializerMethodField()

    # প্যারেন্ট ক্যাটাগরির নাম দেখানোর জন্য (ঐচ্ছিক, ফ্রন্টএন্ডে সুবিধা হবে)
    parent_name = serializers.ReadOnlyField(source="parent.name")

    class Meta:
        model = Category
        # 'parent' ফিল্ডটি এখানে যোগ করা হয়েছে যাতে সাব-ক্যাটাগরি সেভ করা যায়
        fields = [
            "id",
            "name",
            "slug",
            "image",
            "parent",
            "parent_name",
            "subcategories",
        ]

    # 🔥 ক্যাটাগরি ইমেজ থেকে প্রিলিংক বা ডাবল লিংক বাদ দেওয়ার মেথড
    def get_image(self, obj):
        if obj.image:
            url_str = str(obj.image)
            # যদি লিংকে দুইবার https:// থাকে, তবে শেষের আসল অংশটুকু কেটে নেবে
            if url_str.count("https://") > 1:
                return "https://" + url_str.split("https://")[-1]
            return url_str
        return ""

    def get_subcategories(self, obj):
        # যদি এই ক্যাটাগরির আন্ডারে কোনো সাব-ক্যাটাগরি থাকে তবে সেগুলো দেখাবে
        serializer = CategorySerializer(
            obj.subcategories.all(),
            many=True,
            context={"request": self.context.get("request")},
        )
        return serializer.data


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source="category.name")
    unit_display = serializers.CharField(source="get_unit_type_display", read_only=True)

    # ক্যালকুলেটেড ফিল্ডস
    original_price = serializers.ReadOnlyField(source="price")
    discount_price = serializers.SerializerMethodField()
    display_price = serializers.SerializerMethodField()

    # 👇 [FIX] SerializerMethodField সরিয়ে নরমাল ইমেজ ফিল্ড রাখা হলো যাতে POST/PUT-এ ইমেজ ইনপুট নেয়
    image = serializers.ImageField(required=False, allow_null=True)
    barcode_image = serializers.ImageField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "slug",
            "description",
            "purchase_price",
            "price",
            "unit_type",
            "unit_display",
            "stock",
            "point_value",
            "image",
            "barcode_number",
            "barcode_image",
            "is_active",
            "is_featured",
            "original_price",
            "discount_price",
            "display_price",
            "created_at",
        ]
        extra_kwargs = {
            "is_active": {"read_only": True},
            "barcode_image": {"read_only": True},
        }

    # 🔥 [MAGIC METHOD] এপিআই যখন ফ্রন্টএন্ডে রেসপন্স (GET/POST Response) পাঠাবে,
    # তখন সে নিজে থেকেই ডাবল ক্লাউডিনারি লিংকের প্রথম অংশটুকু কেটে ফ্রেশ করে দেবে।
    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # ১. মেইন ইমেজ থেকে লোকাল ডোমেইন এবং ডাবল লিংক ক্লিনআপ
        if representation.get("image"):
            url_str = str(representation["image"])
            if "https" in url_str:
                # যদি লোকাল ডোমেইনের ভেতরে https লুকিয়ে থাকে, তবে শেষের আসল https থেকে কেটে নেবে
                # url_str.split("https")[-1] করলে পাবো: ://res.cloudinary.com/...
                # আমরা জাস্ট শুরুতে একটা ফ্রেশ https জুড়ে দেব এবং এনকোড হওয়া %3A বা কোলনের জটটা ক্লিন করব
                actual_url = "https" + url_str.split("https")[-1]
                representation["image"] = actual_url.replace("%3A", ":")

        # ২. বারকোড ইমেজ থেকে লোকাল ডোমেইন এবং ডাবল লিংক ক্লিনআপ
        if representation.get("barcode_image"):
            url_str = str(representation["barcode_image"])
            if "https" in url_str:
                actual_url = "https" + url_str.split("https")[-1]
                representation["barcode_image"] = actual_url.replace("%3A", ":")

        return representation

    def get_discount_price(self, obj):
        request = self.context.get("request")
        try:
            base_price = Decimal(str(obj.price))
            pv = Decimal(str(obj.point_value or 0))
            if request and request.user.is_authenticated:
                u_status = getattr(request.user, "status", "").lower().strip()
                if u_status == "active" and not request.user.is_staff:
                    discounted = base_price - (pv * Decimal("2.0"))
                    return float(round(discounted, 2))
        except (ValueError, TypeError, Exception):
            pass
        return None

    def get_display_price(self, obj):
        discount = self.get_discount_price(obj)
        return discount if discount is not None else float(obj.price)

    def validate(self, data):
        stock_val = data.get("stock", 0)
        try:
            if float(stock_val) < 0:
                raise serializers.ValidationError(
                    {"stock": "মামা, স্টক তো নেগেটিভ হইতে পারে না!"}
                )
        except (ValueError, TypeError):
            pass
        return data


from rest_framework import serializers


class CartSerializer(serializers.ModelSerializer):
    unit_type = serializers.ReadOnlyField(source="product.unit_type")
    product_name = serializers.ReadOnlyField(source="product.name")
    # ফ্রন্টএন্ডে স্টক দেখার জন্য এটি যোগ করলাম (অপশনাল)
    available_stock = serializers.ReadOnlyField(source="product.stock")

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
            "available_stock",  # ইউজার কতটুকু স্টক আছে তা দেখতে পারবে
            "item_subtotal",
        ]

    # ✅ স্টক ভ্যালিডেশন লজিক
    def validate(self, data):
        """
        মডেল চেঞ্জ না করে সিরিয়ালাইজার থেকে স্টক চেক করা
        """
        # ডাটা থেকে প্রোডাক্ট এবং কোয়ান্টিটি বের করা
        product = data.get("product")
        quantity = data.get("quantity")

        # যদি এডিট (update) করা হয়, তবে ডাটাবেজে থাকা কার্ট অবজেক্ট থেকে প্রোডাক্ট নিতে হবে
        if not product and self.instance:
            product = self.instance.product

        # স্টকের সাথে তুলনা করা
        if product and quantity:
            if quantity > product.stock:
                raise serializers.ValidationError(
                    {
                        "quantity": f"মামা, স্টকের বেশি অর্ডার দেওয়া সম্ভব না! বর্তমানে স্টক আছে {product.stock} {product.get_unit_type_display()}."
                    }
                )

        # কোয়ান্টিটি ০ বা তার কম কি না চেক করা
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                {"quantity": "মামা, অন্তত কিছু তো কিনতে হবে! পরিমাণ ০ হতে পারে না।"}
            )

        return data

    def get_user_status(self, request):
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        u_status = getattr(user, "status", "").lower()
        if not u_status and hasattr(user, "profile"):
            u_status = getattr(user.profile, "status", "").lower()
        return u_status

    def get_product_price(self, obj):
        request = self.context.get("request")
        product = obj.product if hasattr(obj, "product") else obj.get("product")
        if not product:
            return 0
        base_price = float(product.price)
        pv = float(product.point_value or 0)
        if self.get_user_status(request) == "active":
            return base_price - (pv * 2)
        return base_price

    def get_product_pv(self, obj):
        request = self.context.get("request")
        product = obj.product if hasattr(obj, "product") else obj.get("product")
        if not product:
            return 0
        if self.get_user_status(request) == "active":
            return 0
        return float(product.point_value or 0)

    def get_item_subtotal(self, obj):
        # আপনার বিদ্যমান লজিক
        try:
            if isinstance(obj, dict):
                product_data = obj.get("product")
                quantity = float(obj.get("quantity", 0))
            else:
                product_data = getattr(obj, "product", None)
                quantity = float(getattr(obj, "quantity", 0))

            price = self.get_product_price(obj)  # সরাসরি এই মেথড ব্যবহার করা নিরাপদ
            return round(price * quantity, 2)
        except:
            return 0.0

    def get_product_image(self, obj):
        request = self.context.get("request")
        product = obj.product if hasattr(obj, "product") else obj.get("product")
        if product and product.image:
            return (
                request.build_absolute_uri(product.image.url)
                if request
                else product.image.url
            )
        return None


class BannerSerializer(serializers.ModelSerializer):
    # ইমেজ ফিল্ডকে সাধারণভাবেই রাখ যেন রিড/রাইট দুইটাই হয়
    # জ্যাঙ্গো নিজেই ফুল ইউআরএল হ্যান্ডেল করবে
    class Meta:
        model = Banner
        fields = ['id', 'title', 'image', 'link', 'is_active', 'created_at']
