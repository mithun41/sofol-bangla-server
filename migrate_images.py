import os
import django
from django.core.files.base import ContentFile
from django.conf import settings

# ১. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product


def start_migration():
    all_products = Product.objects.all()
    total = all_products.count()
    print(f"--- Migration Started on PythonAnywhere: {total} products found ---")

    # PythonAnywhere এর সরাসরি পাথ (যদি সেটিংস থেকে না পায়)
    PA_MEDIA_PATH = "/home/mithun41/sofol-bangla-server/media"

    for i, p in enumerate(all_products, 1):
        image_fields = ["image", "barcode_image"]
        updated = False

        for field_name in image_fields:
            image_field = getattr(p, field_name)

            if image_field and not str(image_field).startswith("http"):
                try:
                    # প্রথমে সেটিংস এর MEDIA_ROOT দিয়ে চেক করবে
                    local_file_path = os.path.join(
                        settings.MEDIA_ROOT, str(image_field.name)
                    )

                    # যদি না পায় তবে সরাসরি PythonAnywhere পাথ দিয়ে চেক করবে
                    if not os.path.exists(local_file_path):
                        local_file_path = os.path.join(
                            PA_MEDIA_PATH, str(image_field.name)
                        )

                    if os.path.exists(local_file_path):
                        with open(local_file_path, "rb") as f:
                            file_content = f.read()
                            file_name = os.path.basename(local_file_path)

                            new_file = ContentFile(file_content, name=file_name)
                            image_field.save(file_name, new_file, save=False)

                        updated = True
                        print(
                            f"[{i}/{total}] Success: {field_name} uploaded for '{p.name}'"
                        )
                    else:
                        print(
                            f"[{i}/{total}] Skip: File not found at {local_file_path}"
                        )
                except Exception as e:
                    print(f"[{i}/{total}] Error on {p.name} ({field_name}): {e}")

        if updated:
            p.save()

    print("--- Migration Completed on PythonAnywhere! ---")


if __name__ == "__main__":
    start_migration()
