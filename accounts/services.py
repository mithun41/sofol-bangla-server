from .models import User
from decimal import Decimal
from django.db import transaction
from .models import BonusLog



def distribute_binary_matching(child):
    """
    একজন ইউজার তখনই বোনাস পাবে যখন তার বাম এবং ডান চাইল্ড 
    উভয়েই একটি করে নতুন পেয়ার (ম্যাচিং) সম্পন্ন করবে।
    """
    current_node = child
    parent = child.placement_under

    while parent is not None:
        with transaction.atomic():
            # ১. সরাসরি মেম্বার কাউন্ট না করে আমরা ট্র্যাক করছি কতগুলো 'পয়েন্ট' বা 'পেয়ার ইউনিট' বাড়ছে
            # এই লজিকে প্রতি ২ জন মেম্বার (১টি পেয়ার) = ১টি ইউনিট
            if current_node.position == 'left':
                parent.left_count += 1
            else:
                parent.right_count += 1
            
            # ২. আমাদের দরকার ১:১ ম্যাচিং (অর্থাৎ বামে ২ জন এবং ডানে ২ জন হলে ১টি ৪০০ টাকার ম্যাচিং)
            # এখানে // ২ ব্যবহার করলে ২ জন মেম্বারকে ১টি 'পেয়ার ইউনিট' হিসেবে ধরা হয়
            left_units = parent.left_count // 2
            right_units = parent.right_count // 2
            
            # ৩. যদি দুই পাশেই অন্তত ১টি করে পেয়ার ইউনিট থাকে
            if left_units >= 1 and right_units >= 1:
                # কতগুলো ম্যাচিং হচ্ছে (আপনার ক্ষেত্রে ১টিই হবে)
                matches = min(left_units, right_units)
                bonus_amount = Decimal(400) # নির্দিষ্ট ৪০০ টাকা
                
                # ব্যালেন্স আপডেট
                parent.balance += bonus_amount
                
                # বোনাস লগ (সঠিক কারণসহ)
                BonusLog.objects.create(
                    user=parent,
                    amount=bonus_amount,
                    reason=f"Level matching bonus triggered by {child.username}'s branch completion."
                )
                
                # ৪. সবথেকে গুরুত্বপূর্ণ: ব্যবহৃত ২ জন করে মেম্বারকে কাউন্ট থেকে বাদ দেওয়া
                # যাতে পরবর্তী ৪০০ টাকার জন্য আবার নতুন করে ২ জন ২ জন লাগে।
                parent.left_count -= (matches * 2)
                parent.right_count -= (matches * 2)
                
                print(f"Strategic Bonus: {parent.username} earned 400 TK")

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