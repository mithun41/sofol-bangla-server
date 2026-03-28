import string
import random
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings


def generate_order_id():
    """ইউনিক অর্ডার আইডি জেনারেট করার ফাংশন (যেমন: SB-20260205-A7B2)"""
    date_str = timezone.now().strftime('%Y%m%d')
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SB-{date_str}-{random_str}"

class Order(models.Model):
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad')
    ]
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Shipping', 'Shipping'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled')
    ]

    order_number = models.CharField(max_length=30, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    courier = models.CharField(max_length=100, default="Sundarban Courier")
    # Billing Info
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=50)
    total_pv = models.PositiveIntegerField(default=0)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Payment Info
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    sender_number = models.CharField(max_length=15, null=True, blank=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Pending')
    points_awarded = models.BooleanField(default=False) 
    created_at = models.DateTimeField(auto_now_add=True)

    def calculate_total_points(self):
        """অর্ডারের সব আইটেম থেকে টোটাল পয়েন্ট ক্যালকুলেট করা"""
        return sum(item.point_value * item.quantity for item in self.items.all())

    def save(self, *args, **kwargs):
        # ১. ইউনিক অর্ডার আইডি জেনারেশন (নতুন অর্ডারের জন্য)
        if not self.order_number:
            new_id = generate_order_id()
            while Order.objects.filter(order_number=new_id).exists():
                new_id = generate_order_id()
            self.order_number = new_id

        # ২. স্টক রিস্টোর লজিক (শুধুমাত্র আপডেট বা পুরনো অর্ডারের জন্য)
        if self.pk:
            try:
                # ডাটাবেস থেকে পুরনো অবজেক্টটি আনা হচ্ছে
                old_instance = Order.objects.get(pk=self.pk)
                
                # যদি স্ট্যাটাস আগে 'Cancelled' না থাকে কিন্তু এখন 'Cancelled' করা হয়
                if old_instance.status != 'Cancelled' and self.status == 'Cancelled':
                    from products.models import Product
                    with transaction.atomic():
                        for item in self.items.all():
                            Product.objects.filter(id=item.product_id).update(
                                stock=models.F('stock') + item.quantity
                            )
                            print(f"DEBUG: Stock restored for product {item.product_id}")
            except Order.DoesNotExist:
                pass

        # ৩. সুপার সেভ কল (পয়েন্ট ক্যালকুলেশন এখানে করবেন না, সিগন্যাল হ্যান্ডেল করবে)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} - {self.name}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product_id = models.IntegerField()
    product_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    point_value = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product_name} (x{self.quantity})"