from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    """অর্ডারের ভেতর প্রোডাক্টের লিস্ট দেখানোর জন্য"""
    model = OrderItem
    extra = 0
    readonly_fields = ('product_id', 'product_name', 'quantity', 'price', 'point_value')
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # ড্যাশবোর্ডের মেইন লিস্টে যে কলামগুলো দেখা যাবে
    list_display = (
        'id', 'name', 'phone', 'total_amount', 
        'payment_method', 'status', 'points_awarded', 'created_at'
    )
    
    # যেগুলোর ওপর ভিত্তি করে অর্ডার ফিল্টার করা যাবে (ডান পাশে থাকবে)
    list_filter = ('status', 'payment_method', 'city', 'created_at', 'points_awarded')
    
    # সার্চ বক্সের মাধ্যমে যা যা দিয়ে অর্ডার খোঁজা যাবে
    search_fields = ('id', 'name', 'phone', 'transaction_id')
    
    # সরাসরি লিস্ট পেজ থেকেই স্ট্যাটাস পরিবর্তন করার সুবিধা
    list_editable = ('status',)
    
    # অর্ডারের ভেতরে ইনলাইন আইটেম যোগ করা
    inlines = [OrderItemInline]

    # ডাটা সুন্দরভাবে সাজিয়ে দেখানোর জন্য fieldsets
    fieldsets = (
        ('Customer Details', {
            'fields': ('user', 'name', 'phone', 'address', 'city')
        }),
        ('Payment Info', {
            'fields': ('payment_method', 'sender_number', 'transaction_id')
        }),
        ('Order Calculation', {
            'fields': ('subtotal',  'total_amount')
        }),
        ('Status & Points', {
            'fields': ('status', 'points_awarded')
        }),
    )

    readonly_fields = ('created_at', 'points_awarded')

    ordering = ('-created_at',)
