import os
import django
from django.core.files.base import ContentFile
from django.conf import settings

# ১. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product, Category
from accounts.models import User

# সরাসরি ক্লাউডিনারির অফিশিয়াল আপলোডার ইমপোর্ট করা
import cloudinary
import cloudinary.uploader

# ক্লাউডিনারি কনফিগারেশন এবং কড়াভাবে প্রক্সি সেট করা
cloudinary.config(
    cloud_name="dolauolo2",
    api_key="366553971367551",
    api_secret="mze_qTBeLEByT_Yoa1fmwmOWdHc",
    api_proxy="http://proxy.server:3128",  # পাইথনঅ্যানিহোয়্যারের ফ্রি প্রক্সি গেটওয়ে
)


def start_migration(model_class, image_fields, label):
    print(f"\n=======================================================")
    print(f"🚀 Starting {label} Migration via Direct Cloudinary Uploader...")
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

            # যদি ইমেজ থাকে এবং ক্লাউডিনারি লিংক না হয়
            if image_field and not str(image_field).startswith("http"):
                try:
                    local_file_path = os.path.join(MEDIA_PATH, str(image_field.name))

                    if os.path.exists(local_file_path):
                        # ফোল্ডারের নাম ডাইনামিকালি বের করা (যেমন: categories, products)
                        folder_name = os.path.dirname(str(image_field.name))

                        # ড্যাঙ্গো স্টোরেজ বাইপাস করে সরাসরি ক্লাউডিনারি এপিআই-তে হিট করা
                        # এখানে প্রক্সি গ্যারান্টিসহ কাজ করবে
                        upload_result = cloudinary.uploader.upload(
                            local_file_path,
                            folder=folder_name,
                            use_filename=True,
                            unique_filename=False,
                        )

                        # ক্লাউডিনারি থেকে পাওয়া সিকিউর ইউআরএল ডাটাবেজে অ্যাসাইন করা
                        secure_url = upload_result.get("secure_url")
                        setattr(instance, field_name, secure_url)

                        updated = True
                        print(f"[{i}] Success: {field_name} uploaded -> {secure_url}")
                    else:
                        print(f"[{i}] Skip: File not found at {local_file_path}")
                except Exception as e:
                    print(f"[{i}] Error on {instance_name} ({field_name}): {e}")

        if updated:
            # শুধুমাত্র ইমেজ ফিল্ডটাই সেভ হবে যাতে অন্য লজিকে ইমপ্যাক্ট না পড়ে
            instance.save(update_fields=image_fields)

    print(f"✅ {label} Migration Completed!")


if __name__ == "__main__":
    # ১. শুধু ক্যাটাগরি আপলোড:
    start_migration(Category, ["image"], "Category")

    # ২. প্রোডাক্ট এবং বারকোড আপলোড (প্রয়োজন হলে আনকমেন্ট করিস মামা):
    # start_migration(Product, ["image", "barcode_image"], "Product/Barcode")

    # ৩. ইউজার প্রোফাইল পিকচার আপলোড:
    # start_migration(User, ["profile_picture"], "User Profile Picture")

    print("\n🎉 All migrations finished successfully!")
