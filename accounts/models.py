from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
from django.conf import settings

class User(AbstractUser):
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=False, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=False)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    reff_id = models.CharField(max_length=12, unique=True, blank=True)
    placement_id = models.CharField(max_length=12, unique=True, blank=True)
    division = models.CharField(max_length=100, blank=True, null=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)
    
    position = models.CharField(max_length=10, choices=[('left', 'Left'), ('right', 'Right')], null=True, blank=True)
    left_count = models.IntegerField(default=0)
    right_count = models.IntegerField(default=0)
    total_left = models.IntegerField(default=0)
    total_right = models.IntegerField(default=0)
    
    # এটি সবচেয়ে গুরুত্বপূর্ণ: এই ইউজার আগে কয়টি ম্যাচিংয়ের টাকা পেয়েছে তার হিসাব
    paid_matches = models.PositiveIntegerField(default=0) 
    
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) 
    points = models.IntegerField(default=0) 
    
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reff_users')
    placement_under = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='placement_users')
    
    status = models.CharField(max_length=10, choices=(('active', 'Active'), ('inactive', 'Inactive')), default='inactive')
    star_level = models.IntegerField(default=0)
    role = models.CharField(max_length=20, default='customer')
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        # আইডি জেনারেশন (আগের মতো)
        if not self.reff_id:
            self.reff_id = "REF" + str(uuid.uuid4().hex[:6].upper())
        if not self.placement_id:
            self.placement_id = "PLC" + str(uuid.uuid4().hex[:6].upper())

        is_becoming_active = False
        added_points = 0

        if self.pk:
            old_user = User.objects.get(pk=self.pk)
            
            # ১. নতুন পয়েন্ট যোগ হয়েছে কি না চেক (ফান্ডে টাকা পাঠানোর জন্য)
            if self.points > old_user.points:
                added_points = self.points - old_user.points
            
            # ২. অ্যাক্টিভেশন কন্ডিশন চেক
            # যদি আগে ইনাক্টিভ থাকে এবং এখন ১০০০ পয়েন্ট বা তার বেশি হয়
            if old_user.status == 'inactive' and (self.points >= 1000 or self.status == 'active'):
                is_becoming_active = True
                self.status = 'active'
                self.points = 0  # মামা, তোর রিকোয়ারমেন্ট: একটিভ হলে পয়েন্ট ০ হয়ে যাবে
        else:
            # নতুন ইউজার তৈরির সময় যদি পয়েন্ট থাকে
            added_points = self.points
            if self.points >= 1000 or self.status == 'active':
                is_becoming_active = True
                self.status = 'active'
                self.points = 0

        if self.is_superuser:
            self.role = 'admin'

        # মেইন সেভ কল
        super().save(*args, **kwargs)

        # ৩. ফান্ড ডিস্ট্রিবিউশন: ইউজার একটিভ হোক বা না হোক, পয়েন্ট বাড়লে টাকা ফান্ডে যাবে
        if added_points > 0:
            from accounts.services import distribute_money_to_funds
            distribute_money_to_funds(added_points)

        # ৪. বোনাস ডিস্ট্রিবিউশন: শুধুমাত্র যখন ইনাক্টিভ থেকে একটিভ হবে
        if is_becoming_active:
            from accounts.services import calculate_commission
            calculate_commission(self)

class BonusLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bonus_logs')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

class WithdrawalRequest(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=50) 
    account_number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
# models.py এ যোগ কর

class GlobalFund(models.Model):
    referral_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    matching_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    rank_reward_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tour_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    leadership_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    company_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Global Fund Balance"

    def __str__(self):
        return "Global Fund Balances"

class FundLog(models.Model):
    TRANSACTION_TYPES = (('inbound', 'Money In'), ('outbound', 'Money Out'))
    fund_type = models.CharField(max_length=50) # referral, matching, etc.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.fund_type}: {self.amount}"