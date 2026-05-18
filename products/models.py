import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
import random
from django.db import models
from django.utils.text import slugify
from django.conf import settings


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
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


import random
from io import BytesIO
from django.db import models
from django.utils.text import slugify
from django.core.files.base import ContentFile  # এটি যোগ করা হয়েছে

# বারকোড লাইব্রেরি ইম্পোর্ট (নিশ্চিত করিস এগুলো ইন্সটল আছে)
import barcode
from barcode.writer import ImageWriter


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
    created_at = models.DateTimeField(auto_now_add=True)

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

        super().save(*args, **kwargs)

    def generate_barcode_image(self):
        """বারকোড ইমেজ তৈরির ফিক্সড ফাংশন (Cloudinary Compatible)"""
        CODE128 = barcode.get_barcode_class("code128")
        code_img = CODE128(self.barcode_number, writer=ImageWriter())

        # বাফারে ইমেজ রাইট করা
        buffer = BytesIO()
        code_img.write(buffer)

        # ফাইল নাম তৈরি
        filename = f"barcode-{self.barcode_number}.png"

        # --- ফিক্স: বাফারের পজিশন শুরুতে নিয়ে আসা এবং ContentFile ব্যবহার করা ---
        buffer.seek(0)
        file_content = buffer.getvalue()  # বাফার থেকে ডাটা নেওয়া

        # ক্লাউডিনারিতে সরাসরি বাইনারি কন্টেন্ট পাঠানো
        self.barcode_image.save(filename, ContentFile(file_content), save=False)

    def __str__(self):
        return self.name


class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="in_carts"
    )
    # PositiveIntegerField পরিবর্তন করে DecimalField দিলাম
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.quantity})"


class Banner(models.Model):
    title = models.CharField(max_length=150, blank=True, null=True)
    image = models.ImageField(upload_to='banners/')
    link = models.URLField(blank=True, null=True, help_text="ব্যানারে ক্লিক করলে কোথায় যাবে (ঐচ্ছিক)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title if self.title else f"Banner {self.id}"
