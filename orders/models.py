import string
import random
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings


def generate_order_id():
    date_str = timezone.now().strftime("%Y%m%d")
    random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SB-{date_str}-{random_str}"


class Order(models.Model):
    PAYMENT_METHODS = [
        ("cod", "Cash on Delivery"),
        ("bkash", "bKash"),
        ("nagad", "Nagad"),
    ]
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Processing", "Processing"),
        ("Shipping", "Shipping"),
        ("Completed", "Completed"),
        ("Cancelled", "Cancelled"),
    ]

    order_number = models.CharField(max_length=30, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    courier = models.CharField(max_length=100, default="Sundarban Courier")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=50)
    total_pv = models.PositiveIntegerField(default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    sender_number = models.CharField(max_length=15, null=True, blank=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="Pending")
    points_awarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            new_id = generate_order_id()
            while Order.objects.filter(order_number=new_id).exists():
                new_id = generate_order_id()
            self.order_number = new_id

        old_status = None
        if self.pk:
            old_status = (
                Order.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        super().save(*args, **kwargs)

        # স্টক রিস্টোর (Cancelled হলে)
        if old_status and old_status != "Cancelled" and self.status == "Cancelled":
            from products.models import Product

            with transaction.atomic():
                for item in self.items.all():
                    Product.objects.filter(id=item.product_id).update(
                        stock=models.F("stock") + item.quantity
                    )

        # বেনিফিট ডিস্ট্রিবিউশন লজিক
        if self.status == "Completed" and not self.points_awarded:
            with transaction.atomic():
                # ডাটাবেজ থেকে লেটেস্ট অবজেক্ট লক করে আনা
                order_to_process = Order.objects.select_for_update().get(pk=self.pk)

                if not order_to_process.points_awarded:
                    from accounts.services import calculate_and_apply_order_benefits

                    # আগে ফ্ল্যাগ আপডেট যাতে ডাবল বোনাস না যায়
                    Order.objects.filter(pk=self.pk).update(points_awarded=True)
                    self.points_awarded = True

                    success = calculate_and_apply_order_benefits(self)

                    if not success:
                        Order.objects.filter(pk=self.pk).update(points_awarded=False)
                        self.points_awarded = False
                    elif self.user:
                        self.user.refresh_from_db()

    def __str__(self):
        return f"{self.order_number} - {self.name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_id = models.IntegerField()
    product_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    point_value = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product_name} (x{self.quantity})"
