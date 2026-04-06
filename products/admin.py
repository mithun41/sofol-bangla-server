from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # ১. লিস্ট ভিউতে যা যা দেখাবে (তোর আগের is_featured সহ)
    list_display = (
        "display_barcode",
        "name",
        "unit_type",
        "price",
        "point_value",
        "stock",
        "is_active",
        "is_featured",  # আগের এই ফিল্ডটা যোগ করলাম
    )

    # ২. ফিল্টার করার অপশন
    list_filter = ("category", "unit_type", "is_active", "is_featured")

    # ৩. সরাসরি লিস্ট থেকে এডিট করার অপশন (সবগুলো এক লাইনে)
    # মামা খেয়াল কর: এখানে point_value আছে, তাই এটা readonly_fields এ রাখা যাবে না।
    list_editable = (
        "price",
        "stock",
        "unit_type",
        "is_active",
        "is_featured",
        "point_value",
    )

    search_fields = ("name", "description", "barcode_number")

    # ৪. এডিট পেজে শুধু বারকোড ইমেজটি readonly থাকবে
    readonly_fields = ("display_barcode_large", "barcode_number")

    # ৫. বারকোড ডিসপ্লে মেথড
    def display_barcode(self, obj):
        if obj.barcode_image:
            return format_html(
                '<img src="{}" width="80" style="border: 1px solid #eee;" />',
                obj.barcode_image.url,
            )
        return "No Barcode"

    display_barcode.short_description = "Barcode"

    def display_barcode_large(self, obj):
        if obj.barcode_image:
            return format_html(
                '<div><img src="{}" width="250" style="border: 1px solid #ccc;" /><p><b>Number:</b> {}</p></div>',
                obj.barcode_image.url,
                obj.barcode_number,
            )
        return "No Barcode Available"

    display_barcode_large.short_description = "Barcode Preview"

    # ৬. ফিল্ডসেট (প্রোডাক্টের ভেতর ঢুকলে যেভাবে সাজানো থাকবে)
    fieldsets = (
        (
            "General Information",
            {
                "fields": (
                    "category",
                    "name",
                    "slug",
                    "description",
                    "image",
                    "is_active",
                    "is_featured",
                )
            },
        ),
        (
            "Pricing & Stock Management",
            {
                "fields": (
                    "purchase_price",
                    "price",
                    "point_value",
                    "unit_type",
                    "stock",
                )
            },
        ),
        (
            "Barcode Status",
            {
                "fields": ("display_barcode_large", "barcode_number"),
            },
        ),
    )

    prepopulated_fields = {"slug": ("name",)}
