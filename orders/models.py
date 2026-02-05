import string
import random
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
def generate_order_id():
    """ইউনিক অর্ডার আইডি জেনারেট করার ফাংশন (যেমন: SB-20260205-A7B2)"""
    date_str = timezone.now().strftime('%Y%m%d')
    # ৪ অক্ষরের র‍্যান্ডম স্ট্রিং জেনারেট করবে
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

    # কাস্টম ইউনিক অর্ডার আইডি ফিল্ড
    order_number = models.CharField(max_length=30, unique=True, editable=False)
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=50)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    sender_number = models.CharField(max_length=15, null=True, blank=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Pending')
    points_awarded = models.BooleanField(default=False) 
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # ইউনিক অর্ডার আইডি জেনারেশন
        if not self.order_number:
            new_id = generate_order_id()
            while Order.objects.filter(order_number=new_id).exists():
                new_id = generate_order_id()
            self.order_number = new_id

        # পয়েন্ট অ্যাড এবং স্টক ম্যানেজমেন্ট লজিক
        if self.pk: # শুধুমাত্র আপডেট হওয়ার সময় (অর্ডার প্লেস করার সময় নয়)
            old_order = Order.objects.get(pk=self.pk)

            # ১. পয়েন্ট অ্যাড লজিক (Completed হলে)
            if old_order.status != 'Completed' and self.status == 'Completed':
                if self.user and not self.points_awarded:
                    # অর্ডারের সব আইটেম থেকে পয়েন্টের যোগফল বের করা
                    total_points = sum(item.point_value * item.quantity for item in self.items.all())
                    
                    if total_points > 0:
                        with transaction.atomic():
                            self.user.points += total_points
                            self.user.save()
                            self.points_awarded = True # যাতে একবারই পয়েন্ট অ্যাড হয়
                            print(f"DEBUG: {total_points} points added to {self.user.username}")

            # ২. স্টক রিস্টোর লজিক (Cancelled হলে)
            elif old_order.status != 'Cancelled' and self.status == 'Cancelled':
                from products.models import Product # সার্কুলার ইম্পোর্ট এড়াতে এখানে
                for item in self.items.all():
                    Product.objects.filter(id=item.product_id).update(
                        stock=models.F('stock') + item.quantity
                    )

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