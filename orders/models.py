from decimal import Decimal
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
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
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

        # স্টক রিস্টোর লজিক (Cancelled হলে) - কেজি/গ্রাম সাপোর্টসহ
        if old_status and old_status != "Cancelled" and self.status == "Cancelled":
            from products.models import Product

            with transaction.atomic():
                for item in self.items.all():
                    product = (
                        Product.objects.select_for_update()
                        .filter(id=item.product_id)
                        .first()
                    )
                    if product:
                        qty = Decimal(str(item.quantity))
                        if product.unit_type == "gram":
                            product.stock += qty / Decimal("1000.0")
                        else:
                            product.stock += qty
                        product.save()

        # বেনিফিট ডিস্ট্রিবিউশন (Completed হলে)
        if self.status == "Completed" and not self.points_awarded:
            with transaction.atomic():
                order_to_process = Order.objects.select_for_update().get(pk=self.pk)
                if not order_to_process.points_awarded:
                    from accounts.services import calculate_and_apply_order_benefits

                    Order.objects.filter(pk=self.pk).update(points_awarded=True)
                    self.points_awarded = True
                    success = calculate_and_apply_order_benefits(self)
                    if not success:
                        Order.objects.filter(pk=self.pk).update(points_awarded=False)
                        self.points_awarded = False

    def __str__(self):
        return f"{self.order_number} - {self.name}"


from django.db import models, transaction
from decimal import Decimal


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_id = models.IntegerField()
    product_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # নতুন ফিল্ড
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    profit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    point_value = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # ১. পারচেজ প্রাইস সেট করার লজিক
        if not self.purchase_price or self.purchase_price == Decimal("0.00"):
            from products.models import Product

            try:
                # product_id দিয়ে ডাটাবেজ থেকে সরাসরি প্রোডাক্ট আনা
                product_obj = Product.objects.get(id=self.product_id)
                self.purchase_price = product_obj.purchase_price
                print(
                    f"DEBUG: Product Found! Name: {product_obj.name}, P_Price: {product_obj.purchase_price}"
                )
            except Product.DoesNotExist:
                print(f"DEBUG: Product NOT Found for ID: {self.product_id}")
                self.purchase_price = Decimal("0.00")
            except Exception as e:
                print(f"DEBUG: General Error: {str(e)}")

        # ২. লাভ ক্যালকুলেট করা (Decimal এ কনভার্ট করে নিচ্ছি যাতে ভুল না হয়)
        qty = Decimal(str(self.quantity))
        price_sold = Decimal(str(self.price))
        buy_price = Decimal(str(self.purchase_price or 0))

        self.profit = (price_sold - buy_price) * qty

        # টার্মিনালে চেক করার জন্য প্রিন্ট (সার্ভার লগ চেক করিস মামা)
        print(
            f"DEBUG: Final Calculation -> Qty: {qty}, Sold: {price_sold}, Buy: {buy_price}, Profit: {self.profit}"
        )

        # ৩. ডাটা সেভ করা
        super().save(*args, **kwargs)

        # ৪. স্টক কমানোর লজিক (তোর আগের কোড)
        if is_new:
            from products.models import Product

            with transaction.atomic():
                product = (
                    Product.objects.select_for_update()
                    .filter(id=self.product_id)
                    .first()
                )
                if product:
                    if product.unit_type == "gram":
                        product.stock -= qty / Decimal("1000.0")
                    else:
                        product.stock -= qty
                    product.save()

    def __str__(self):
        return f"{self.product_name} (x{self.quantity})"
