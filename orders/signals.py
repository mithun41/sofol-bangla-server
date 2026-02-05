from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from django.db import transaction

@receiver(post_save, sender=Order)
def handle_order_status_updates(sender, instance, created, **kwargs):
    print(f"DEBUG: Signal triggered for Order {instance.order_number}")
    print(f"DEBUG: Current Status: '{instance.status}'")

    if not created:  # যখন অর্ডার আপডেট করা হয়
        status = instance.status.strip().lower()
        
        if status == 'completed':
            print(f"DEBUG: Order is COMPLETED. Points to award: {instance.points_awarded}")
            
            if instance.user:
                try:
                    with transaction.atomic():
                        user = instance.user
                        points_to_add = int(instance.points_awarded)
                        
                        if points_to_add > 0:
                            user.points += points_to_add
                            user.save()
                            print(f"DEBUG: SUCCESS! {points_to_add} points added to {user.username}")
                        else:
                            print("DEBUG: No points to add (points_awarded is 0 or less)")
                except Exception as e:
                    print(f"DEBUG ERROR: {str(e)}")
            else:
                print("DEBUG: This order has no associated user.")