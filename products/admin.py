from django.contrib import admin
from .models import Product, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)} # নাম লিখলে অটো স্ল্যাগ তৈরি হবে

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'point_value', 'stock', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description')
    list_editable = ('price', 'stock', 'is_active') # লিস্ট থেকেই এডিট করা যাবে