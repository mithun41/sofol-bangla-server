from decimal import Decimal
from django.db import transaction
from .models import BonusLog, User

def update_user_rank(user):
    matching = min(user.total_left, user.total_right)
    new_star = 0
    if matching >= 1200: new_star = 8
    elif matching >= 500: new_star = 7
    elif matching >= 200: new_star = 6
    elif matching >= 50: new_star = 5
    elif matching >= 15: new_star = 4
    
    if new_star > user.star_level:
        user.star_level = new_star
        user.save()

from decimal import Decimal
from django.db import transaction
from .models import BonusLog, User

def distribute_binary_matching(child):
    """
    শর্ত ১: সরাসরি ২ জন চাইল্ড একটিভ হলে প্যারেন্ট ৪০০ পাবে।
    শর্ত ২: এরপর ২ জন চাইল্ড বোনাস পেলে প্যারেন্ট ৪০০ পাবে।
    """
    current_node = child
    parent = child.placement_under

    while parent is not None:
        with transaction.atomic():
            # লাইফটাইম কাউন্ট আপডেট (সবসময় হবে)
            if current_node.position == 'left':
                parent.total_left += 1
                parent.left_count += 1
            else:
                parent.total_right += 1
                parent.right_count += 1
            
            # প্যারেন্টের সরাসরি দুই চাইল্ড বের করা
            left_c = User.objects.filter(placement_under=parent, position='left').first()
            right_c = User.objects.filter(placement_under=parent, position='right').first()

            if left_c and right_c:
                # ১. চেক করা চাইল্ডরা নিজেরা বোনাস পেয়েছে কি না (অথবা তারা কি প্রথম জোড়া?)
                # paid_matches হলো কয়টি জোড়া তারা মিলিয়েছে তার সংখ্যা
                left_bonus_count = left_c.paid_matches
                right_bonus_count = right_c.paid_matches
                
                # যদি উভয় চাইল্ডই নতুন একটিভ হয় (paid_matches ০) অথবা 
                # তারা নিজেরা নতুন বোনাস পায়, তবে প্যারেন্টের 'টোটাল পসিবল ম্যাচ' বাড়বে।
                # আমরা চেক করব দুই চাইল্ডের ন্যূনতম ম্যাচিং কত।
                
                # প্রথমবার একটিভ হওয়ার জন্য আমরা +১ ধরি যাতে প্রথম ৪০০ টাকা পায়।
                effective_left = left_bonus_count + (1 if left_c.status == 'active' else 0)
                effective_right = right_bonus_count + (1 if right_c.status == 'active' else 0)
                
                total_eligible_matches = min(effective_left, effective_right)

                # ২. যদি প্যারেন্ট আগে এই জোড়ার টাকা না পেয়ে থাকে
                if total_eligible_matches > parent.paid_matches:
                    new_matches = total_eligible_matches - parent.paid_matches
                    bonus_amount = Decimal(new_matches * 400)
                    
                    parent.balance += bonus_amount
                    parent.paid_matches = total_eligible_matches # ম্যাচ কাউন্ট আপডেট
                    parent.save()

                    BonusLog.objects.create(
                        user=parent, 
                        amount=bonus_amount,
                        reason=f"Binary bonus: Child pair {left_c.username} & {right_c.username} matched/active"
                    )

            parent.save()
            # লুপ উপরের দিকে যাবে
            current_node = parent
            parent = parent.placement_under

def calculate_commission(user):
    if user.referred_by:
        ref = user.referred_by
        ref.balance += Decimal(500)
        BonusLog.objects.create(
            user=ref, amount=500, 
            reason=f"Referral bonus: {user.username}"
        )
        ref.save()
    
    distribute_binary_matching(user)