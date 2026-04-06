from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order


@receiver(post_save, sender=Order)
def handle_order_status_updates(sender, instance, created, **kwargs):
    """
    অর্ডার আপডেট হলে এই সিগন্যালটি চেক করবে স্ট্যাটাস 'Completed' কি না।
    সব মেইন লজিক accounts/services.py এ হ্যান্ডেল করা হবে।
    """
    if not created:
        raw_status = str(instance.status).strip().lower()

        # ১. চেক: স্ট্যাটাস 'completed' এবং আগে কি এই অর্ডারের পয়েন্ট দেওয়া হয়েছে?
        if raw_status == "completed" and not instance.points_awarded:
            if instance.user:
                # ট্রানজেকশন ব্লক যাতে ডাটাবেজ সেফ থাকে
                with transaction.atomic():
                    # ২. অর্ডারের points_awarded আগে True করা (ডাবল বোনাস ঠেকানোর জন্য)
                    # আমরা select_for_update ব্যবহার করছি যাতে অন্য কোনো প্রসেস এটা ধরতে না পারে
                    order = Order.objects.select_for_update().get(pk=instance.pk)

                    if not order.points_awarded:
                        from accounts.services import calculate_and_apply_order_benefits

                        # ৩. প্রথমে ডাটাবেজে মার্ক করে দেওয়া
                        Order.objects.filter(pk=instance.pk).update(points_awarded=True)

                        # ৪. সার্ভিস ফাংশন কল করা (যা ইউজারকে একটিভ করবে এবং পয়েন্ট দিবে)
                        success = calculate_and_apply_order_benefits(order)

                        if success:
                            print(
                                f"✅ Benefits applied for Order: {order.order_number}"
                            )
                        else:
                            # যদি কোনো কারণে ফেইল করে, তবে ফ্ল্যাগ আবার False করা (যাতে পরে আবার ট্রাই করা যায়)
                            Order.objects.filter(pk=instance.pk).update(
                                points_awarded=False
                            )
                            print(
                                f"❌ Failed to apply benefits for Order: {order.order_number}"
                            )
