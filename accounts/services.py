from .models import User

def distribute_binary_matching(child):
    """চাইল্ড একটিভ হলে তার উপরের চেইনে আনলিমিটেড ডেপথ পর্যন্ত ম্যাচিং চেক করা"""
    parent = child.placement_under
    current_child = child

    while parent is not None:
        # পজিশন অনুযায়ী প্যারেন্টের কাউন্ট বাড়ানো
        if current_child.position == 'left':
            parent.left_count += 1
        else:
            parent.right_count += 1
        
        # ১:১ ম্যাচিং চেক (উভয় পাশে অন্তত ১ জন করে থাকলে)
        if parent.left_count > 0 and parent.right_count > 0:
            parent.points += 400  # ৪০০ পয়েন্ট বোনাস
            parent.left_count -= 1 # পেয়ার ম্যাচ হয়ে গেল
            parent.right_count -= 1
            
        parent.save()
        
        # লুপ উপরে চলতে থাকবে (যতক্ষণ উপরে প্যারেন্ট আছে)
        current_child = parent
        parent = parent.placement_under
# accounts/services.py

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