from decimal import Decimal
from django.db import transaction
from .models import BonusLog, User

def update_user_rank(user):
    matching = min(user.total_left, user.total_right)
    new_star = 0
    
    # র‍্যাঙ্ক নির্ধারণ
    if matching >= 1200: new_star = 8
    elif matching >= 500: new_star = 7
    elif matching >= 200: new_star = 6
    elif matching >= 50: new_star = 5
    elif matching >= 15: new_star = 4
    
    # যদি ইউজারের নতুন স্টার লেভেল বর্তমান লেভেলের চেয়ে বেশি হয়
    if new_star > user.star_level:
        # স্টার অনুযায়ী বোনাস নির্ধারণ
        star_bonuses = {
            4: 5000,
            5: 10000,
            6: 30000,
            7: 50000,
            8: 100000
        }
        
        # বর্তমান লেভেল থেকে নতুন লেভেল পর্যন্ত প্রতিটি লেভেলের বোনাস চেক করা
        # (যাতে কেউ যদি সরাসরি ৪ থেকে ৬ স্টার হয়, তবে যেন সব বোনাস পায়)
        total_rank_bonus = 0
        for level in range(user.star_level + 1, new_star + 1):
            if level in star_bonuses:
                bonus = star_bonuses[level]
                total_rank_bonus += bonus
                
                # বোনাস লগ তৈরি করা
                BonusLog.objects.create(
                    user=user,
                    amount=Decimal(bonus),
                    reason=f"Rank Achievement Bonus: {level} Star Level Up"
                )

        # ইউজারের ব্যালেন্স এবং লেভেল আপডেট
        user.balance += Decimal(total_rank_bonus)
        user.star_level = new_star
        user.save()

def distribute_binary_matching(child):
    current_node = child
    parent = child.placement_under

    while parent is not None:
        with transaction.atomic():
            # লাইফটাইম কাউন্ট আপডেট
            if current_node.position == 'left':
                parent.total_left += 1
                parent.left_count += 1
            else:
                parent.total_right += 1
                parent.right_count += 1
            
            # সরাসরি দুই চাইল্ড বের করা
            left_c = User.objects.filter(placement_under=parent, position='left').first()
            right_c = User.objects.filter(placement_under=parent, position='right').first()

            if left_c and right_c:
                effective_left = left_c.paid_matches + (1 if left_c.status == 'active' else 0)
                effective_right = right_c.paid_matches + (1 if right_c.status == 'active' else 0)
                
                total_eligible_matches = min(effective_left, effective_right)

                if total_eligible_matches > parent.paid_matches:
                    new_matches = total_eligible_matches - parent.paid_matches
                    bonus_amount = Decimal(new_matches * 400)
                    
                    parent.balance += bonus_amount
                    parent.paid_matches = total_eligible_matches
                    
                    BonusLog.objects.create(
                        user=parent, 
                        amount=bonus_amount,
                        reason=f"Binary bonus: Child pair {left_c.username} & {right_c.username} matched"
                    )

            # !!! গুরুত্বপূর্ণ: প্যারেন্টের কাউন্ট আপডেট হওয়ার পর তার র‍্যাঙ্ক চেক করা
            parent.save() # আগে সেভ করে নিতে হবে যাতে নতুন কাউন্ট ডাটাবেসে যায়
            update_user_rank(parent) 
            
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
    
from collections import deque

def find_auto_placement(referrer_node):
    """
    Breadth-First Search (BFS) ব্যবহার করে রেফারারের নিচে প্রথম ফাঁকা জায়গা খুঁজে বের করবে।
    """
    queue = deque([referrer_node])
    
    while queue:
        current = queue.popleft()
        
        # বাম পাশ চেক
        left_child = User.objects.filter(placement_under=current, position='left').first()
        if not left_child:
            return current, 'left'
        else:
            queue.append(left_child)
            
        # ডান পাশ চেক
        right_child = User.objects.filter(placement_under=current, position='right').first()
        if not right_child:
            return current, 'right'
        else:
            queue.append(right_child)
            
    return None, None