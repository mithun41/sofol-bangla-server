import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from products.models import Product
from django.db.models import F

def run():
    Product.objects.update(last_stock_added_at=F('created_at'))
    print("✅ last_stock_added_at field has been synced with created_at for all existing products.")

if __name__ == "__main__":
    run()
