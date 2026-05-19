import os
import django
import time
import json
import hashlib
import urllib.request
from django.core.files.base import ContentFile
from django.conf import settings

# ১. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product, Category
from accounts.models import User

# ক্লাউডিনারি ক্রেডেনশিয়ালস
CLOUD_NAME = "dolauolo2"
API_KEY = "366553971367551"
API_SECRET = "mze_qTBeLEByT_Yoa1fmwmOWdHc"


def upload_to_cloudinary_raw(file_path, folder_name):
    """
    কোনো থার্ড-পার্টি লাইব্রেরি ছাড়া সরাসরি পাইথনের বিল্ট-ইন urllib দিয়ে
    পাইথনঅ্যানিহোয়্যার প্রক্সি ব্যবহার করে ক্লাউডিনারিতে ছবি আপলোড করার ফাংশন।
    """
    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload"
    timestamp = str(int(time.time()))

    # ক্লাউডিনারি এপিআই সিগনেচার তৈরি (অথেনটিকেশন)
    params_to_sign = f"folder={folder_name}&timestamp={timestamp}{API_SECRET}"
    signature = hashlib.sha1(params_to_sign.encode("utf-8")).hexdigest()

    # মাল্টিপার্ট ফর্ম-ডাটা (Multipart/form-data) বাউন্ডারি তৈরি
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = []

    # ফর্ম ফিল্ডস যোগ করা
    fields = {
        "api_key": API_KEY,
        "timestamp": timestamp,
        "folder": folder_name,
        "signature": signature,
    }

    for key, value in fields.items():
        body.append(f"--{boundary}")
        body.append(f'Content-Disposition: form-data; name="{key}"')
        body.append("")
        body.append(value)

    # আসল ফাইল ডাটা যোগ করা
    with open(file_path, "rb") as f:
        file_content = f.read()

    filename = os.path.basename(file_path)
    body.append(f"--{boundary}")
    body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"')
    body.append("Content-Type: image/jpeg")  # জেনারেলাইজড ইমেজ টাইপ
    body.append("")
    body.extend([file_content])
    body.append(f"--{boundary}--")
    body.append("")

    # পুরো বডিকে বাইনারিতে রূপান্তর করা
    data = b""
    for item in body:
        if isinstance(item, str):
            data += (item + "\r\n").encode("utf-8")
        else:
            data += item + b"\r\n"

    # রিকোয়েস্ট তৈরি করা
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    # পাইথনঅ্যানিহোয়্যারের বিল্ট-ইন এনভায়রনমেন্ট প্রক্সি ব্যবহার করে রিকোয়েস্ট পাঠানো
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))
        return result.get("secure_url")


def start_migration(model_class, image_fields, label):
    print(f"\n=======================================================")
    print(f"🚀 Starting {label} Migration via Pure Python Urllib API...")
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

                        # র ফাংশন কল করা হলো
                        secure_url = upload_to_cloudinary_raw(
                            local_file_path, folder_name
                        )

                        if secure_url:
                            setattr(instance, field_name, secure_url)
                            updated = True
                            print(
                                f"[{i}] Success: {field_name} uploaded -> {secure_url}"
                            )
                        else:
                            print(f"[{i}] Failed to get URL from Cloudinary response.")
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

    # প্রয়োজন হলে নিচের মডিউলগুলো আনকমেন্ট করে নিতে পারিস মামা:
    # start_migration(Product, ["image", "barcode_image"], "Product/Barcode")
    # start_migration(User, ["profile_picture"], "User Profile Picture")

    print("\n🎉 All migrations finished successfully!")
