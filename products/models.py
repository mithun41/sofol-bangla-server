import os
import sys
import time
import json
import random
import hashlib
import urllib.request
from io import BytesIO
from decimal import Decimal

from django.db import models
from django.utils.text import slugify
from django.conf import settings
from django.core.files.base import ContentFile

# বারকোড লাইব্রেরি ইম্পোর্ট
import barcode
from barcode.writer import ImageWriter


# =====================================================================
# 🚀 PYTHONANYWHERE CLOUDINARY PROXY UPLOADER HELPER
# =====================================================================
def upload_to_cloudinary_via_proxy(file_obj, folder_name):
    """
    পাইথনঅ্যানিহোয়্যারের ফ্রি অ্যাকাউন্টের প্রক্সি গেটওয়ে ব্যবহার করে
    সরাসরি ক্লাউডিনারি এপিআই-তে ইমেজ/ফাইল আপলোড করার একটি র-মেথড।
    """
    if not file_obj or str(file_obj).startswith("http"):
        return str(file_obj)

    CLOUD_NAME = "dolauolo2"
    API_KEY = "366553971367551"
    API_SECRET = "mze_qTBeLEByT_Yoa1fmwmOWdHc"

    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload"
    timestamp = str(int(time.time()))

    params_to_sign = f"folder={folder_name}&timestamp={timestamp}{API_SECRET}"
    signature = hashlib.sha1(params_to_sign.encode("utf-8")).hexdigest()

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = []

    fields = {
        "api_key": API_KEY,
        "timestamp": timestamp,
        "folder": folder_name,
        "signature": signature,
    }

    for key, value in fields.items():
        body.append(f"--{boundary}")
        body.append(f'Content-Disposition: form-data; name="{key}"')
        body.append("")
        body.append(value)

    # ফাইল অবজেক্ট রিড করা (সেটা মেমোরি ফাইল হোক বা ডিস্ক ফাইল)
    file_obj.open("rb")
    file_content = file_obj.read()
    file_obj.close()

    # ফাইলের আসল নাম বের করা
    filename = (
        os.path.basename(file_obj.name)
        if hasattr(file_obj, "name")
        else f"upload-{timestamp}.png"
    )

    body.append(f"--{boundary}")
    body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"')
    body.append("Content-Type: image/jpeg")
    body.append("")
    body.extend([file_content])
    body.append(f"--{boundary}--")
    body.append("")

    data = b""
    for item in body:
        if isinstance(item, str):
            data += (item + "\r\n").encode("utf-8")
        else:
            data += item + b"\r\n"

    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("secure_url")
    except Exception as e:
        print(f"❌ Cloudinary proxy upload error: {e}")
        return None


# =====================================================================
# 📁 CATEGORY MODEL
# =====================================================================
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, null=True, blank=True)
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories",
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        # 🛠️ ক্যাটাগরি ইমেজের জন্য প্রক্সি আপলোডার
        if self.image and not str(self.image).startswith("http"):
            live_url = upload_to_cloudinary_via_proxy(self.image, "categories")
            if live_url:
                self.image = live_url

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# =====================================================================
# 📦 PRODUCT MODEL
# =====================================================================
class Product(models.Model):
    UNIT_CHOICES = [
        ("piece", "Piece"),
        ("kg", "Kilogram"),
        ("gram", "Gram"),
        ("liter", "Liter"),
    ]

    category = models.ForeignKey(
        "Category",
        on_delete=models.SET_NULL,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)

    # প্রাইসিং ফিল্ডস
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    price = models.DecimalField(max_digits=12, decimal_places=2)  # Selling Price
    point_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # স্টক এবং ইউনিট
    unit_type = models.CharField(max_length=10, choices=UNIT_CHOICES, default="piece")
    stock = models.DecimalField(max_digits=12, decimal_places=3, default=0.000)

    image = models.ImageField(upload_to="products/", null=True, blank=True)
    barcode_number = models.CharField(max_length=255, unique=True, blank=True)
    barcode_image = models.ImageField(upload_to="barcodes/", blank=True, null=True)

    # স্ট্যাটাস ফিল্ডস
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # ১. অটোমেটিক স্লাগ জেনারেট করা
        if not self.slug:
            self.slug = slugify(self.name) + "-" + str(random.randint(1000, 9999))

        # ২. বারকোড লজিক (অটো জেনারেশন যদি ফাঁকা থাকে)
        if not self.barcode_number:
            number = "".join([str(random.randint(0, 9)) for _ in range(13)])
            while Product.objects.filter(barcode_number=number).exists():
                number = "".join([str(random.randint(0, 9)) for _ in range(13)])
            self.barcode_number = number

        # ৩. বারকোড ইমেজ জেনারেট লজিক
        if self.pk:
            try:
                old_product = Product.objects.get(pk=self.pk)
                if old_product.barcode_number != self.barcode_number:
                    self.generate_barcode_image()
            except Product.DoesNotExist:
                pass
        else:
            if not self.barcode_image:
                self.generate_barcode_image()

        # 🛠️ ৪. প্রোডাক্টের মেইন ইমেজ প্রক্সি আপলোডার (যদি নতুন ফাইল আপলোড করা হয়)
        if self.image and not str(self.image).startswith("http"):
            live_url = upload_to_cloudinary_via_proxy(self.image, "products")
            if live_url:
                self.image = live_url

        # 🛠️ ৫. বারকোড ইমেজ প্রক্সি আপলোডার (কারণ ড্যাঙ্গো সেভ হওয়ার সময় ফাইল সিস্টেম ওপেন করে)
        if self.barcode_image and not str(self.barcode_image).startswith("http"):
            live_barcode_url = upload_to_cloudinary_via_proxy(
                self.barcode_image, "barcodes"
            )
            if live_barcode_url:
                self.barcode_image = live_barcode_url

        super().save(*args, **kwargs)

    def generate_barcode_image(self):
        """বারকোড ইমেজ তৈরির ফিক্সড ফাংশন (Cloudinary Compatible)"""
        CODE128 = barcode.get_barcode_class("code128")
        code_img = CODE128(self.barcode_number, writer=ImageWriter())

        buffer = BytesIO()
        code_img.write(buffer)

        filename = f"barcode-{self.barcode_number}.png"
        buffer.seek(0)
        file_content = buffer.getvalue()

        # কন্টেন্ট ফাইল হিসেবে টেম্পোরারিভাবে অ্যাসাইন করা (save=False রাখা হয়েছে কারণ মেইন save() মেথড আপলোড সামাল দেবে)
        self.barcode_image.save(filename, ContentFile(file_content), save=False)

    def __str__(self):
        return self.name


# =====================================================================
# 🛒 CART MODEL
# =====================================================================
class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="in_carts"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.quantity})"


# =====================================================================
# 🖼️ BANNER MODEL
# =====================================================================
class Banner(models.Model):
    title = models.CharField(max_length=150, blank=True, null=True)
    image = models.ImageField(upload_to="banners/")
    link = models.URLField(
        blank=True, null=True, help_text="ব্যানারে ক্লিক করলে কোথায় যাবে (ঐচ্ছিক)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 🛠️ ব্যানার ইমেজের জন্য প্রক্সি আপলোডার
        if self.image and not str(self.image).startswith("http"):
            live_url = upload_to_cloudinary_via_proxy(self.image, "banners")
            if live_url:
                self.image = live_url
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title if self.title else f"Banner {self.id}"
