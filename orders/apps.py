from django.apps import AppConfig

class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'

    def ready(self):
        # এই প্রিন্টটি দাও যাতে সার্ভার চালু হলেই বুঝতে পারো
        print("\n✅ ORDERS APP IS READY AND SIGNALS ARE LOADING...\n")
        import orders.signals