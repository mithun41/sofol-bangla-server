import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product


def clean_double_urls():
    products = Product.objects.all()
    count = 0

    for p in products:
        updated = False
        # image এবং barcode_image দুটি ফিল্ডই চেক করা হচ্ছে
        for field_name in ["image", "barcode_image"]:
            current_value = str(getattr(p, field_name))

            # যদি লিংকের ভেতর দুইবার http থাকে (ডাবল ইউআরএল)
            if current_value.count("http") > 1:
                # একদম শেষের 'https' থেকে শুরু করে বাকি আসল লিংকটুকু কেটে নেওয়া হচ্ছে
                actual_url = "https" + current_value.split("https")[-1]
                setattr(p, field_name, actual_url)
                updated = True

        if updated:
            p.save(update_fields=["image", "barcode_image"])
            count += 1
            print(f"✅ Fixed links for product: {p.name}")

    print(f"🎉 Total {count} products fixed!")


if __name__ == "__main__":
    clean_double_urls()
