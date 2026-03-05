from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # 'display_barcode' কে লিস্টে যোগ করলাম যাতে সামনেই দেখা যায়
    list_display = ('display_barcode', 'name', 'category', 'price', 'point_value', 'stock', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description', 'barcode_number') # বারকোড নাম্বার দিয়েও এখন সার্চ করা যাবে
    list_editable = ('price', 'stock', 'is_active')
    
    # বারকোড ইমেজটি লিস্টে সুন্দর করে দেখানোর জন্য ফাংশন
    def display_barcode(self, obj):
        if obj.barcode_image:
            return format_html('<img src="{}" width="120" style="border: 1px solid #ddd; padding: 2px;" />', obj.barcode_image.url)
        return "No Barcode"
    
    display_barcode.short_description = 'Barcode' # কলামের নাম সেট করলাম

    # প্রোডাক্ট এডিট পেজে বারকোড ইমেজটি বড় করে দেখানোর জন্য
    readonly_fields = ('display_barcode_large', 'point_value')
    
    def display_barcode_large(self, obj):
        if obj.barcode_image:
            return format_html('<img src="{}" width="300" />', obj.barcode_image.url)
        return "No Barcode Available"
    
    display_barcode_large.short_description = 'Barcode Preview'