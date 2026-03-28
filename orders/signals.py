from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction, models
from decimal import Decimal
from django.apps import apps
from django.db.models import F # যোগফল (Addition) করার জন্য এটি জরুরি

@receiver(post_save, sender='orders.Order')
def handle_order_status_updates(sender, instance, created, **kwargs):
    if not created:
        raw_status = str(instance.status).strip().lower()
        
        # ১. চেক: স্ট্যাটাস 'completed' এবং আগে কি এই অর্ডারের পয়েন্ট দেওয়া হয়েছে?
        if raw_status == 'completed' and not instance.points_awarded:
            if instance.user:
                User = apps.get_model('accounts', 'User')
                order_pv = Decimal(str(instance.total_pv or 0))
                
                if order_pv > 0:
                    with transaction.atomic():
                        # ২. ইউজার যদি অলরেডি একটিভ থাকে
                        if str(instance.user.status).lower() == 'active':
                            offer_amount = order_pv * Decimal('2.0') # ৫ PV = ১০ টাকা
                            
                            # এখানে balance আপডেট করা বাদ দেওয়া হয়েছে
                            User.objects.filter(pk=instance.user.pk).update(
                                total_offer_earned=F('total_offer_earned') + offer_amount,
                                lifetime_offer_points=F('lifetime_offer_points') + order_pv
                            )
                            print(f"✅ Added {offer_amount} TK to total_offer_earned (NOT in main balance)")
                        
                        # ৩. ইউজার যদি ইন-একটিভ থাকে (আইডি একটিভ করার পয়েন্ট)
                        else:
                            User.objects.filter(pk=instance.user.pk).update(
                                points=F('points') + order_pv
                            )
                            print(f"✅ Added {order_pv} points to activation balance")

                        # ৪. অর্ডারটি মার্ক করা যাতে ডাবল বোনাস না পায়
                        sender.objects.filter(pk=instance.pk).update(points_awarded=True)