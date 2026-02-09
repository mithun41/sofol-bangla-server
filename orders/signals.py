from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order

@receiver(post_save, sender=Order)
def handle_order_status_updates(sender, instance, created, **kwargs):
    """অর্ডার কমপ্লিট হলে পয়েন্ট অ্যাড করার সিগন্যাল"""
    if not created:  # যখন অর্ডার আপডেট করা হয়
        # স্ট্যাটাস ক্লিন করা (যাতে স্পেস বা ক্যাপিটাল লেটারে ঝামেলা না হয়)
        current_status = instance.status.strip()

        if current_status == 'Completed' and not instance.points_awarded:
            if instance.user:
                try:
                    with transaction.atomic():
                        # ১. অর্ডারের সব আইটেমের পয়েন্ট যোগফল বের করা
                        total_points = instance.calculate_total_points()
                        
                        if total_points > 0:
                            # ২. ইউজারের একাউন্টে পয়েন্ট যোগ করা
                            user = instance.user
                            user.points += total_points
                            user.save()
                            
                            # ৩. পয়েন্ট যে দেওয়া হয়েছে তা মার্ক করা (যাতে ডাবল না হয়)
                            # আমরা সরাসরি আপডেট কুয়েরি চালাবো যাতে আবার সিগন্যাল লুপ না হয়
                            Order.objects.filter(pk=instance.pk).update(points_awarded=True)
                            
                            print(f"SUCCESS: {total_points} points added to {user.username}")
                except Exception as e:
                    print(f"ERROR adding points: {str(e)}")