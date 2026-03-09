import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
import random
from django.db import models
from django.conf import settings
from django.utils.text import slugify
import math

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='subcategories'
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(Category, self).save(*args, **kwargs)

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    class Meta:
        verbose_name_plural = "Categories"

class Product(models.Model):
    category = models.ForeignKey(
    Category, 
    on_delete=models.SET_NULL,  
    related_name='products',
    null=True,                  
    blank=True                  
)
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    # কেনা দাম এবং বিক্রি দাম
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    price = models.DecimalField(max_digits=10, decimal_places=2) 
    
    # পয়েন্ট ভ্যালু (অটো ক্যালকুলেটেড)
    point_value = models.IntegerField(default=0, editable=False) 
    
    # বারকোড ফিল্ড (১৩ ডিজিট সেভ করার জন্য)
    barcode_number = models.CharField(max_length=13, unique=True, blank=True, null=True)
    barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True, editable=False)

    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # ১. প্রফিট এবং পয়েন্ট ভ্যালু হিসাব (৪ টাকায় ১ পয়েন্ট)
        profit = float(self.price) - float(self.purchase_price)
        if profit > 0:
            self.point_value = math.floor(profit / 4)
        else:
            self.point_value = 0

        # ২. বারকোড নাম্বার জেনারেশন (চেকসামসহ ১৩ ডিজিট)
        if not self.barcode_number:
            while True:
                # প্রথমে ১২ ডিজিট র‍্যান্ডম জেনারেট করি
                temp_number = "".join([str(random.randint(0, 9)) for _ in range(12)])
                # EAN13 অবজেক্ট তৈরি করে ফুল কোড (১৩ ডিজিট) বের করি
                ean = barcode.get('ean13', temp_number)
                full_code = ean.get_fullcode() 
                
                if not Product.objects.filter(barcode_number=full_code).exists():
                    self.barcode_number = full_code
                    break

        
        # ৩. বারকোড ইমেজ জেনারেশন
        if self.barcode_number:
            # ইমেজের নামটা কেমন হওয়া উচিত তা চেক করার জন্য
            expected_file_name = f'barcode-{self.barcode_number}.png'
            
            # যদি ইমেজ না থাকে অথবা ইমেজের নামের সাথে বর্তমান নাম্বারের মিল না থাকে (অর্থাৎ নাম্বার বদলেছে)
            if not self.barcode_image or expected_file_name not in self.barcode_image.name:
                EAN_GEN = barcode.get('ean13', self.barcode_number, writer=ImageWriter())
                buffer = BytesIO()
                EAN_GEN.write(buffer)
                
                # আগের পুরানো ইমেজ ফাইলটা ডিলিট করে দিচ্ছি যাতে গারবেজ জমা না হয়
                if self.barcode_image:
                    self.barcode_image.delete(save=False)

                # নতুন ১৩ ডিজিটের বারকোড ইমেজ সেভ করছি
                self.barcode_image.save(expected_file_name, File(buffer), save=False)
            
        super(Product, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='cart_items'
    )
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='in_carts'
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.quantity})"