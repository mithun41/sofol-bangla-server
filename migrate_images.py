import os
import django
from django.core.files.base import ContentFile
from django.conf import settings

# =====================================================================
# 🚨 PYTHONANYWHERE PROXY MONKEY-PATCH (সবচেয়ে শক্তিশালী নেটওয়ার্ক হ্যাক)
# =====================================================================
# ক্লাউডিনারি বা উরলিব ব্যাকগ্রাউন্ডে যাই ব্যবহার করুক, এই প্যাচটি পাইথনের গ্লোবাল
# HTTPSConnectionPool-কে বাধ্য করবে পাইথনঅ্যানিহোয়্যারের প্রক্সি দিয়ে ডেটা পাঠাতে।

import urllib3

proxy_url = "http://proxy.server:3128"
urllib3.util.PROXY_SCHEME_TO_POOL_MANAGER["https"] = urllib3.ProxyManager(proxy_url)
urllib3.util.PROXY_SCHEME_TO_POOL_MANAGER["http"] = urllib3.ProxyManager(proxy_url)

# গ্লোবাল এনভায়রনমেন্টও কঠোরভাবে লক করা হলো
os.environ["http_proxy"] = proxy_url
os.environ["https_proxy"] = proxy_url
os.environ["HTTP_PROXY"] = proxy_url
os.environ["HTTPS_PROXY"] = proxy_url

# ২. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product, Category
from accounts.models import User
import cloudinary
import cloudinary.uploader

# ক্লাউডিনারি কনফিগ
cloudinary.config(
    cloud_name="dolauolo2",
    api_key="366553971367551",
    api_secret="mze_qTBeLEByT_Yoa1fmwmOWdHc",
    api_proxy=proxy_url,
)


def start_migration(model_class, image_fields, label):
    print(f"\n=======================================================")
    print(f"🚀 Starting {label} Migration via Global Proxy Tunnel...")
    print(f"=======================================================")

    queryset = model_class.objects.all()
    MEDIA_PATH = settings.MEDIA_ROOT

    for i, instance in enumerate(queryset, 1):
        updated = False
        instance_name = getattr(
            instance, "name", getattr(instance, "username", str(instance))
        )

        for field_name in image_fields:
            image_field = getattr(instance, field_name)

            if image_field and not str(image_field).startswith("http"):
                try:
                    local_file_path = os.path.join(MEDIA_PATH, str(image_field.name))

                    if os.path.exists(local_file_path):
                        folder_name = os.path.dirname(str(image_field.name))

                        # সরাসরি আপলোড মেথড
                        upload_result = cloudinary.uploader.upload(
                            local_file_path,
                            folder=folder_name,
                            use_filename=True,
                            unique_filename=False,
                        )

                        secure_url = upload_result.get("secure_url")
                        setattr(instance, field_name, secure_url)

                        updated = True
                        print(f"[{i}] Success: {field_name} uploaded -> {secure_url}")
                    else:
                        print(f"[{i}] Skip: File not found at {local_file_path}")
                except Exception as e:
                    print(f"[{i}] Error on {instance_name} ({field_name}): {e}")

        if updated:
            instance.save(update_fields=image_fields)

    print(f"✅ {label} Migration Completed!")


if __name__ == "__main__":
    # ১. শুধু ক্যাটাগরি আপলোড:
    start_migration(Category, ["image"], "Category")

    # দরকার হলে নিচেরগুলো আনকমেন্ট করিস মামা:
    # start_migration(Product, ["image", "barcode_image"], "Product/Barcode")
    # start_migration(User, ["profile_picture"], "User Profile Picture")

    print("\n🎉 All migrations finished successfully!")
