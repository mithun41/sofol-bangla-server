from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, BonusLog, WithdrawalRequest, GlobalFund, FundLog

# ১. কাস্টম ইউজার অ্যাডমিন
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'phone', 'reff_id', 'status', 'points', 'balance', 'star_level')
    list_filter = ('status', 'star_level', 'role')
    
    # এডিট করার সময় সব দরকারি ফিল্ড
    fieldsets = UserAdmin.fieldsets + (
        ('Networking & MLM Info', {'fields': (
            'phone', 'name', 'division', 'reff_id', 'placement_id', 
            'referred_by', 'placement_under', 'position', 'status'
        )}),
        ('Financials', {'fields': ('points', 'balance', 'paid_matches', 'star_level', 'role')}),
        ('Binary Tree Stats', {'fields': ('left_count', 'right_count', 'total_left', 'total_right')}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Personal Info', {'fields': ('email', 'phone', 'name', 'division')}),
    )

# ২. গ্লোবাল ফান্ড অ্যাডমিন (যাতে অ্যাডমিন ব্যালেন্স দেখতে পারে)
@admin.register(GlobalFund)
class GlobalFundAdmin(admin.ModelAdmin):
    list_display = (
        'referral_fund', 'matching_fund', 'rank_reward_fund', 
        'tour_fund', 'leadership_fund', 'company_fund'
    )
    # যেহেতু একটাই রো থাকবে, তাই ডিলিট বা অ্যাড অপশন অফ রাখা ভালো
    def has_add_permission(self, request):
        return not GlobalFund.objects.exists()

# ৩. ফান্ড লগ অ্যাডমিন (মান্থলি ইনকাম-আউটকাম দেখার জন্য)
@admin.register(FundLog)
class FundLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'fund_type', 'amount', 'transaction_type', 'reason')
    list_filter = ('fund_type', 'transaction_type', 'created_at')
    search_fields = ('reason', 'fund_type')

# ৪. বোনাস এবং উইথড্রয়াল
@admin.register(BonusLog)
class BonusLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'reason', 'timestamp')
    search_fields = ('user__username', 'reason')

@admin.register(WithdrawalRequest)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'method', 'status', 'created_at')
    list_editable = ('status',) # সরাসরি লিস্ট থেকে স্ট্যাটাস চেঞ্জ করা যাবে

admin.site.register(User, CustomUserAdmin)