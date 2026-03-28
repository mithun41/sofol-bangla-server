from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.conf import settings
from decimal import Decimal

class User(AbstractUser):
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=False, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=False)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    
    reff_id = models.CharField(max_length=50, unique=True, blank=True)
    placement_id = models.CharField(max_length=50, unique=True, blank=True)
    
    division = models.CharField(max_length=100, blank=True, null=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)
    
    position = models.CharField(max_length=10, choices=[('left', 'Left'), ('right', 'Right')], null=True, blank=True)
    left_count = models.IntegerField(default=0)
    right_count = models.IntegerField(default=0)
    total_left = models.IntegerField(default=0)
    total_right = models.IntegerField(default=0)
    
    paid_matches = models.PositiveIntegerField(default=0) 
    referral_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    matching_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    leadership_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    rank_reward_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) 
    points = models.IntegerField(default=0) 
    total_offer_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    lifetime_offer_points = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reff_users')
    placement_under = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='placement_users')
    
    status = models.CharField(max_length=10, choices=(('active', 'Active'), ('inactive', 'Inactive')), default='inactive')
    star_level = models.IntegerField(default=0)
    role = models.CharField(max_length=20, default='customer')
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.reff_id:
            self.reff_id = self.username
        if not self.placement_id:
            self.placement_id = self.username

        is_becoming_active = False
        added_points = 0

        if self.pk:
            old_user = User.objects.get(pk=self.pk)
            if self.points > old_user.points:
                added_points = self.points - old_user.points
            
            if old_user.status == 'inactive' and (self.points >= 1000 or self.status == 'active'):
                is_becoming_active = True
                self.status = 'active'
                self.points = 0
        else:
            added_points = self.points
            if self.points >= 1000 or self.status == 'active':
                is_becoming_active = True
                self.status = 'active'
                self.points = 0

        if self.is_superuser:
            self.role = 'admin'

        super().save(*args, **kwargs)

        # সার্ভিস ইমপোর্ট এখানে করা হয়েছে সার্কুলার ইমপোর্ট এড়াতে
        if added_points > 0:
            from .services import distribute_money_to_funds
            distribute_money_to_funds(added_points)

        if is_becoming_active:
            from .services import calculate_commission
            calculate_commission(self)

# --- Other Models (No changes needed) ---
class BonusLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bonus_logs')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

class GlobalFund(models.Model):
    referral_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    matching_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    rank_reward_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tour_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    leadership_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    company_fund = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Global Fund Balance"

class FundLog(models.Model):
    TRANSACTION_TYPES = (('inbound', 'Money In'), ('outbound', 'Money Out'))
    fund_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

class WithdrawalRequest(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=50) 
    account_number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)