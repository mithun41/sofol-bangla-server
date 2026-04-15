from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.conf import settings
from decimal import Decimal


class User(AbstractUser):
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=False, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=False)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", null=True, blank=True
    )

    # আইডি এবং পজিশন (Unique constraint errors avoid করার জন্য লজিক নিচে আছে)
    reff_id = models.CharField(max_length=50, unique=True, blank=True)
    placement_id = models.CharField(max_length=50, unique=True, blank=True)
    position = models.CharField(
        max_length=10,
        choices=[("left", "Left"), ("right", "Right")],
        null=True,
        blank=True,
    )

    # লোকেশন এবং ওটিপি
    division = models.CharField(max_length=100, blank=True, null=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)

    # বাইনারি কাউন্ট (Active Users Only)
    left_count = models.IntegerField(default=0)
    right_count = models.IntegerField(default=0)

    # টোটাল টিম কাউন্ট (Active + Inactive)
    total_left = models.IntegerField(default=0)
    total_right = models.IntegerField(default=0)

    # বোনাস এবং ব্যালেন্স
    paid_matches = models.PositiveIntegerField(default=0)
    referral_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    matching_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    leadership_bonus = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )
    rank_reward_bonus = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # পয়েন্ট সিস্টেম
    points = models.IntegerField(default=0)
    total_offer_earned = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )
    lifetime_offer_points = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )

    # রিলেশনশিপ
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reff_users",
    )
    placement_under = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_users",
    )

    # স্ট্যাটাস এবং রোল
    status = models.CharField(
        max_length=10,
        choices=(("active", "Active"), ("inactive", "Inactive")),
        default="inactive",
    )
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("customer", "Customer"),
        ("posAdmin", "POS Admin"),
    ]
    star_level = models.IntegerField(default=0)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        # ১. ইউনিক আইডি হ্যান্ডেল করা
        if not self.reff_id:
            self.reff_id = self.username
        if not self.placement_id:
            self.placement_id = self.username

        is_new_activation = False

        # ২. একটিভেশন চেক (সবচেয়ে গুরুত্বপূর্ণ অংশ)
        if self.pk:
            # সরাসরি ডাটাবেজ থেকে বর্তমান স্ট্যাটাস চেক করা
            current_db_status = (
                User.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )

            # যদি আগে ইন-একটিভ থাকে এবং এখন পয়েন্ট ১০০০ বা তার বেশি হয়
            if current_db_status == "inactive" and self.points >= 1000:
                self.status = "active"
                is_new_activation = True
        else:
            if self.points >= 1000:
                self.status = "active"
                is_new_activation = True

        # ৩. মেইন সেভ কল করা
        super().save(*args, **kwargs)

        # ৪. যদি একটিভ হয়, তবে সার্ভিসগুলো ট্রিগার করা
        if is_new_activation:
            # মেমোরি ক্যাশ বা ট্রানজেকশন এরর এড়াতে এটি ব্যবহার করা হয়েছে
            try:
                from accounts.services import (
                    distribute_money_to_funds,
                    calculate_commission,
                )

                with transaction.atomic():
                    distribute_money_to_funds(self.points)
                    calculate_commission(self)

                    # ডাটাবেজে ফাইনাল পুশ (যাতে রিস্টার্ট না লাগে)
                    User.objects.filter(pk=self.pk).update(status="active")

                print(f"DEBUG: {self.username} activated instantly without restart!")
            except Exception as e:
                print(f"DEBUG ERROR: Activation failed: {e}")

    def __str__(self):
        return self.username


# --- বাকি মডেলগুলো নিচে যেমন ছিল ---


class GlobalFund(models.Model):
    referral_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    matching_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    rank_reward_fund = models.DecimalField(
        max_digits=15, decimal_places=2, default=0.00
    )
    tour_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    leadership_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    company_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Global Fund Balance"


class FundLog(models.Model):
    TRANSACTION_TYPES = (("inbound", "Money In"), ("outbound", "Money Out"))
    fund_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class BonusLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bonus_logs"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)


class WithdrawalRequest(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawals"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=50)
    account_number = models.CharField(
        max_length=50, default="", blank=True
    )  # এটি যোগ করুন
    account_details = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.amount} ({self.status})"
