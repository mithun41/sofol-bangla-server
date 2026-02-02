from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
from django.conf import settings

class User(AbstractUser):
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    reff_id = models.CharField(max_length=12, unique=True, blank=True)
    placement_id = models.CharField(max_length=12, unique=True, blank=True)
    
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
        # আইডি জেনারেশন
        if not self.reff_id:
            self.reff_id = "REF" + str(uuid.uuid4().hex[:6].upper())
        if not self.placement_id:
            self.placement_id = "PLC" + str(uuid.uuid4().hex[:6].upper())
        
        # অটো-অ্যাক্টিভেশন লজিক
        is_becoming_active = False
        # এখানে ডাটাবেস থেকে পুরনো স্ট্যাটাস চেক করা নিরাপদ
        if self.pk:
            old_user = User.objects.get(pk=self.pk)
            if old_user.status == 'inactive' and (self.points >= 1000 or self.status == 'active'):
                is_becoming_active = True
                self.status = 'active'
        elif self.status == 'active' or self.points >= 1000:
             is_becoming_active = True
             self.status = 'active'

        if self.is_superuser:
            self.role = 'admin'

        super().save(*args, **kwargs)

        # কমিশন শুধুমাত্র একবারই ট্রিগার হবে
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