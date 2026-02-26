from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order

@receiver(post_save, sender=Order)
def handle_order_status_updates(sender, instance, created, **kwargs):
    """অর্ডার কমপ্লিট হলে পয়েন্ট অ্যাড করার সিগন্যাল"""
    if not created:  # যখন অর্ডার আপডেট করা হয়
        # ডাটাবেস থেকে লেটেস্ট স্ট্যাটাস চেক করা ভালো
        current_status = instance.status.strip()

        if current_status == 'Completed' and not instance.points_awarded:
            if instance.user:
                try:
                    with transaction.atomic():
                        # ১. সরাসরি অর্ডারের total_pv ফিল্ড ব্যবহার করা (তোর ভিউতে এটা অলরেডি ক্যালকুলেটেড)
                        # মেম্বারদের জন্য এটা ০ থাকবে, নতুনদের জন্য ৫০/১০০ থাকবে।
                        points_to_add = instance.total_pv
                        
                        if points_to_add > 0:
                            user = instance.user
                            
                            # ২. সিলেক্টিভ আপডেট (যাতে অন্য ডেটা লস না হয়)
                            # আমরা ইউজারের পয়েন্ট বাড়াচ্ছি। User model-এর save() এর ভেতরের লজিক অটো কাজ করবে।
                            user.points += points_to_add
                            user.save() 
                            
                            # ৩. পয়েন্ট যে দেওয়া হয়েছে তা মার্ক করা
                            # update() ব্যবহার করায় আবার এই সিগন্যালটা রান করবে না।
                            Order.objects.filter(pk=instance.pk).update(points_awarded=True)
                            
                            print(f"SUCCESS: {points_to_add} points added to {user.username}. Current Total: {user.points}")
                        else:
                            # যদি পয়েন্ট ০ হয় (যেমন একটিভ মেম্বারদের ক্ষেত্রে), শুধু award মার্ক করে দাও
                            Order.objects.filter(pk=instance.pk).update(points_awarded=True)
                            print(f"INFO: Active member order, no points added for order {instance.id}")

                except Exception as e:
                    print(f"ERROR adding points for Order {instance.id}: {str(e)}")