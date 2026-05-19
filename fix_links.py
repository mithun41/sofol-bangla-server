import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product


def clean_database_links():
    print("🔄 Scanning database for broken Cloudinary links...")
    products = Product.objects.all()
    count = 0

    for p in products:
        updated = False

        for field_name in ["image", "barcode_image"]:
            # ড্যাঙ্গোর প্রসেসিং এড়াতে সরাসরি ডাটাবেজের র ভ্যালু চেক করা
            raw_value = getattr(p, field_name).name if getattr(p, field_name) else ""

            if raw_value:
                # সিনারিও ১: যদি পাথের ভেতর 'https://res.cloudinary.com' টেক্সটটা লুকিয়ে থাকে
                if "https:/" in raw_value or "https://" in raw_value:
                    # আসল লিংকটুকু খুঁজে বের করা
                    if "https:/" in raw_value and "https://" not in raw_value:
                        actual_url = "https://" + raw_value.split("https:/")[-1].lstrip(
                            "/"
                        )
                    else:
                        actual_url = "https://" + raw_value.split("https://")[-1]

                    # ড্যাঙ্গোর স্টোরেজকে বাইপাস করে সরাসরি র স্ট্রিং সেট করা
                    setattr(p, field_name, actual_url)
                    updated = True

                # সিনারিо ২: যদি ডাবল মিডিয়া বা রিলেটিভ পাথ জট লেগে থাকে
                elif raw_value.startswith("media/http"):
                    actual_url = raw_value.replace("media/", "")
                    setattr(p, field_name, actual_url)
                    updated = True

        if updated:
            # শুধুমাত্র নির্দিষ্ট ফিল্ডগুলো সেভ করা হচ্ছে যাতে সেটিংসের স্টোরেজ মডিউল ডিস্টার্ব না করে
            p.save(update_fields=["image", "barcode_image"])
            count += 1
            print(f"✅ Successfully Fixed: {p.name}")

    print(f"\n🎉 Total {count} products fixed and cleaned in database!")


if __name__ == "__main__":
    clean_database_links()
