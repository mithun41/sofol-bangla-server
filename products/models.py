from django.db import models
from django.conf import settings
from django.utils.text import slugify

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
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    # কেনা দাম এবং বিক্রি দাম (টাকা-পয়সার জন্য DecimalField-ই সেরা)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    price = models.DecimalField(max_digits=10, decimal_places=2) 
    
    # পয়েন্ট ভ্যালু এখন Integer (পূর্ণসংখ্যা)
    point_value = models.IntegerField(default=0, editable=False) 
    
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # লাভ হিসাব: বিক্রি দাম - কেনা দাম
        # Decimal থেকে float-এ রূপান্তর করে হিসাব করা সহজ
        profit = float(self.price) - float(self.purchase_price)
        
        # ৪ টাকায় ১ পয়েন্ট লজিক
        if profit > 0:
            # math.floor দিলে ২৫.৯৯ হলেও সেটা ২৫ দেখাবে (পূর্ণসংখ্যা)
            self.point_value = math.floor(profit / 4)
        else:
            self.point_value = 0
            
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