import os
import django
from django.core.files.base import ContentFile
from django.conf import settings

# ১. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# 👇 ড্যাঙ্গো সেটআপের ঠিক নিচে এই অংশটুকু যোগ কর মামা
# এটি সরাসরি ক্লাউডিনারি লাইব্রেরির ভেতরে পাইথনঅ্যানিহোয়্যারের প্রক্সি পুশ করে দেবে
import cloudinary

cloudinary.config(api_proxy="http://proxy.server:3128")

from products.models import Product, Category
from accounts.models import User

def start_migration(model_class, image_fields, label):
    print(f"\n=======================================================")
    print(f"🚀 Starting {label} Migration...")
    print(f"=======================================================")

    queryset = model_class.objects.all()
    MEDIA_PATH = settings.MEDIA_ROOT  # পাইথনঅ্যানিহোয়্যারের নিজস্ব মিডিয়া পাথ

    for i, instance in enumerate(queryset, 1):
        updated = False
        instance_name = getattr(
            instance, "name", getattr(instance, "username", str(instance))
        )

        for field_name in image_fields:
            image_field = getattr(instance, field_name)

            # যদি ইমেজ থাকে এবং ক্লাউডিনারি লিংক না হয়
            if image_field and not str(image_field).startswith("http"):
                try:
                    local_file_path = os.path.join(MEDIA_PATH, str(image_field.name))

                    if os.path.exists(local_file_path):
                        with open(local_file_path, "rb") as f:
                            file_content = f.read()
                            file_name = os.path.basename(local_file_path)
                            new_file = ContentFile(file_content, name=file_name)

                            # সরাসরি ক্লাউডিনারিতে আপলোড হবে
                            image_field.save(file_name, new_file, save=False)
                        updated = True
                        print(
                            f"[{i}] Success: {field_name} uploaded for '{instance_name}'"
                        )
                    else:
                        print(f"[{i}] Skip: File not found at {local_file_path}")
                except Exception as e:
                    print(f"[{i}] Error on {instance_name} ({field_name}): {e}")

        if updated:
            # শুধু ইমেজ ফিল্ড সেভ হবে যাতে বোনাস বা বাইনারি কাউন্টে এফেক্ট না পড়ে
            instance.save(update_fields=image_fields)

    print(f"✅ {label} Migration Completed!")


if __name__ == "__main__":
    # মামা, তোর রিকোয়েস্ট অনুযায়ী আপাতত শুধু ক্যাটাগরি অন রাখলাম।
    # প্রোডাক্ট বা ইউজার আপলোড করতে চাইলে জাস্ট নিচের হ্যাশ (#) কমেন্ট তুলে দিবি।

    # ১. শুধু ক্যাটাগরি আপলোড:
    start_migration(Category, ["image"], "Category")

    # ২. প্রোডাক্ট এবং বারকোড আপলোড:
    # start_migration(Product, ["image", "barcode_image"], "Product/Barcode")

    # ৩. ইউজার প্রোফাইল পিকচার আপলোড:
    # start_migration(User, ["profile_picture"], "User Profile Picture")

    print("\n🎉 All migrations finished successfully!")
