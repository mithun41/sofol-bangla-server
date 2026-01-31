from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

# কাস্টম ইউজারকে অ্যাডমিন প্যানেলে দেখার জন্য রেজিস্ট্রেশন
class CustomUserAdmin(UserAdmin):
    # অ্যাডমিন প্যানেলের লিস্টে যে ফিল্ডগুলো দেখাবে
    list_display = ('username', 'email', 'phone', 'reff_id', 'placement_id', 'status', 'star_level')
    
    # ইউজার এডিট করার সময় যে ফিল্ডগুলো দেখাবে (Fieldsets)
    fieldsets = UserAdmin.fieldsets + (
        ('Networking Info', {'fields': ('phone', 'reff_id', 'placement_id', 'referred_by', 'placement_under', 'status', 'star_level', 'points')}),
    )
    
    # নতুন ইউজার বানানোর সময় যে ফিল্ডগুলো থাকবে
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Networking Info', {'fields': ('phone', 'email')}),
    )

admin.site.register(User, CustomUserAdmin)