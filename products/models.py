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
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    # এখানে দাম এবং পয়েন্টের লজিক হবে
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # কেনা দাম
    price = models.DecimalField(max_digits=10, decimal_places=2) # বিক্রি দাম
    point_value = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0.00) # অটো ক্যালকুলেটেড
    
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # লাভ = বিক্রি দাম - কেনা দাম
        profit = float(self.price) - float(self.purchase_price)
        # ৪ টাকায় ১ পয়েন্ট লজিক
        if profit > 0:
            self.point_value = profit / 4
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