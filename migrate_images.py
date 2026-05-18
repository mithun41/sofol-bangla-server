import os
import django
from django.core.files.base import ContentFile
from django.conf import settings

# ১. ড্যাঙ্গো সেটআপ
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product


def start_migration(offset=0, limit=100):
    # offset মানে শুরু (যেমন ০ থেকে), limit মানে কয়টা (যেমন ১০০ টা)
    all_products = Product.objects.all()[offset : offset + limit]
    total_in_batch = all_products.count()

    if total_in_batch == 0:
        print("--- No more products to migrate in this batch! ---")
        return

    print(
        f"--- Batch Started: {offset} to {offset+limit} (Total: {total_in_batch}) ---"
    )

    PA_MEDIA_PATH = "/home/mithun41/sofol-bangla-server/media"

    for i, p in enumerate(all_products, offset + 1):
        image_fields = ["image", "barcode_image"]
        updated = False

        for field_name in image_fields:
            image_field = getattr(p, field_name)

            if image_field and not str(image_field).startswith("http"):
                try:
                    local_file_path = os.path.join(
                        settings.MEDIA_ROOT, str(image_field.name)
                    )
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
                        print(f"[{i}] Success: {field_name} for '{p.name}'")
                    else:
                        print(f"[{i}] Skip: File not found at {local_file_path}")
                except Exception as e:
                    print(f"[{i}] Error on {p.name} ({field_name}): {e}")

        if updated:
            p.save()

    print(f"--- Batch {offset} to {offset+limit} Completed! ---")


if __name__ == "__main__":
    # মামা, এখানে তুই কন্ট্রোল করবি:
    # প্রথমবার রান করতে: offset=0, limit=100
    # পরেরবার রান করতে: offset=100, limit=100
    # তার পরেরবার: offset=200, limit=100 ... এভাবে।

    start_migration(offset=0, limit=100)
