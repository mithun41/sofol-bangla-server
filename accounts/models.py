from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

class User(AbstractUser):
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    reff_id = models.CharField(max_length=12, unique=True, blank=True)
    placement_id = models.CharField(max_length=12, unique=True, blank=True)
    
    position = models.CharField(max_length=10, choices=[('left', 'Left'), ('right', 'Right')], null=True, blank=True)
    left_count = models.IntegerField(default=0)
    right_count = models.IntegerField(default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reff_users')
    placement_under = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='placement_users')
    
    # Binary Data
    position = models.CharField(max_length=10, choices=[('left', 'Left'), ('right', 'Right')], null=True, blank=True)
    left_count = models.IntegerField(default=0)
    right_count = models.IntegerField(default=0)

    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) 
    points = models.IntegerField(default=0) 
    
    status = models.CharField(max_length=10, choices=(('active', 'Active'), ('inactive', 'Inactive')), default='inactive')
    star_level = models.IntegerField(default=0)
    role = models.CharField(max_length=20, default='customer')
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.reff_id:
            self.reff_id = "REF" + str(uuid.uuid4().hex[:6].upper())
        if not self.placement_id:
            self.placement_id = "PLC" + str(uuid.uuid4().hex[:6].upper())
        if self.is_superuser:
            self.role = 'admin'
        super().save(*args, **kwargs)