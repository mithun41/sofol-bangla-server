from .models import User
from decimal import Decimal
from django.db import transaction

def distribute_binary_matching(child):
    """
    লজিক: একজন ইউজার (প্যারেন্ট) তখনই বোনাস পাবে যখন তার বাম এবং ডান
    উভয় পাশের চাইল্ডরা তাদের নিজস্ব ম্যাচিং বোনাস (Pair) সম্পন্ন করবে।
    """
    # নোট: এখানে 'matching_bonus_earned' একটি কাল্পনিক ফিল্ড হিসেবে ধরা হয়েছে যা 
    # আমরা এই ফাংশনেই হ্যান্ডেল করছি।
    
    current_node = child
    parent = child.placement_under

    while parent is not None:
        with transaction.atomic():
            # ১. পজিশন অনুযায়ী প্যারেন্টের কাউন্ট আপডেট
            if current_node.position == 'left':
                parent.left_count += 1
            else:
                parent.right_count += 1
            
            # ২. বিশেষ শর্ত: মিথুন বোনাস পাবে তখনই যখন test6 এবং test7 
            # প্রত্যেকে ১টি করে ম্যাচিং (Pair) পূর্ণ করবে।
            # আমরা এখানে চেক করছি প্যারেন্টের বাম এবং ডানে কি সমপরিমাণ মেম্বার বেড়েছে?
            
            # আপনার শর্ত অনুযায়ী: test6 এবং test7 দুইজনেই বোনাস পেলে তবেই মিথুন পাবে।
            # এটি গাণিতিকভাবে: floor(left_count/2) এবং floor(right_count/2) এর ম্যাচিং।
            
            # যদি সরাসরি ১:১ ম্যাচিং না হয়ে 'পেয়ার অফ পেয়ার' ম্যাচিং হয়:
            left_pairs = parent.left_count // 2
            right_pairs = parent.right_count // 2
            
            # মিথুন অলরেডি কতবার বোনাস পেয়েছে সেটা ট্রাক করার জন্য একটি লজিক দরকার
            # যদি আমরা ধরি প্রতি ২ জন করে (১টি পেয়ার) নিচে বাড়লে প্যারেন্ট ১টি বোনাস পায়:
            if left_pairs >= 1 and right_pairs >= 1:
                # কতটি নতুন ম্যাচিং সেট তৈরি হয়েছে
                new_matches = min(left_pairs, right_pairs)
                
                # বোনাস প্রদান
                bonus_amount = new_matches * 400
                parent.balance += Decimal(bonus_amount)
                
                # কাউন্ট বিয়োগ (যেহেতু তারা পেয়ার হিসেবে ব্যবহৃত হয়েছে)
                # আপনার চাহিদা অনুযায়ী ২ জন করে ব্যবহার হলে ২ বিয়োগ হবে
                parent.left_count -= (new_matches * 2)
                parent.right_count -= (new_matches * 2)
                
                print(f"Strategic Bonus: {parent.username} earned {bonus_amount} TK")

            parent.save()
            
            # লুপ উপরে চলতে থাকবে
            current_node = parent
            parent = parent.placement_under

# accounts/services.py
def calculate_commission(user):
    if user.status == 'inactive': # user-ke active korar trigger
        user.status = 'active'
        user.save()

        # ১. Direct Referral Bonus (৫০০ টাকা সরাসরি রেফারারকে)
        if user.referred_by:
            referrer = user.referred_by
            referrer.balance += 500  # <--- Ekhane balance-e 500 taka add hobe
            referrer.save()

        # ২. Binary Matching Bonus
        distribute_binary_matching(user)

def distribute_binary_matching(child):
    parent = child.placement_under
    current_child = child

    while parent is not None:
        if current_child.position == 'left':
            parent.left_count += 1
        else:
            parent.right_count += 1
        
        if parent.left_count > 0 and parent.right_count > 0:
            parent.balance += 400  # <--- Matching bonus taka-e dile ekhane balance hobe
            parent.left_count -= 1 
            parent.right_count -= 1
            
        parent.save()
        current_child = parent
        parent = parent.placement_under