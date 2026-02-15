from decimal import Decimal
from django.db import transaction
from collections import deque
from .models import BonusLog, User

def find_auto_placement_with_division(referrer_node, user_division):
    """ ১. নির্দিষ্ট ডিভিশনের মেম্বার খুঁজে বের করে তার নিচে প্লেসমেন্ট দেয়। """
    queue = deque([referrer_node])
    target_division_nodes = []
    while queue:
        current = queue.popleft()
        if current.division == user_division:
            target_division_nodes.append(current)
        children = User.objects.filter(placement_under=current)
        for child in children:
            queue.append(child)
    if target_division_nodes:
        for div_node in target_division_nodes:
            for pos in ['left', 'right']:
                if not User.objects.filter(placement_under=div_node, position=pos).exists():
                    return div_node, pos
    return find_auto_placement(referrer_node)

def find_auto_placement(referrer_node):
    queue = deque([referrer_node])
    while queue:
        current = queue.popleft()
        for pos in ['left', 'right']:
            child = User.objects.filter(placement_under=current, position=pos).first()
            if not child:
                return current, pos
            queue.append(child)
    return None, None

def update_user_rank(user):
    """ ম্যাচিং পয়েন্ট অনুযায়ী র‍্যাঙ্ক আপডেট এবং র‍্যাঙ্ক বোনাস প্রদান। """
    matching = min(user.total_left, user.total_right)
    new_star = 0
    if matching >= 1200: new_star = 8
    elif matching >= 500: new_star = 7
    elif matching >= 200: new_star = 6
    elif matching >= 50: new_star = 5
    elif matching >= 15: new_star = 4
    
    if new_star > user.star_level:
        star_bonuses = {4: 5000, 5: 10000, 6: 30000, 7: 50000, 8: 100000}
        total_rank_bonus = 0
        for level in range(user.star_level + 1, new_star + 1):
            if level in star_bonuses:
                bonus = star_bonuses[level]
                total_rank_bonus += bonus
                BonusLog.objects.create(
                    user=user, amount=Decimal(bonus),
                    reason=f"Rank Achievement Bonus: {level} Star Level Up"
                )
        user.balance += Decimal(total_rank_bonus)
        user.star_level = new_star
        user.save()

def distribute_binary_matching(child_node):
    """
    মামা, এখানে চাইল্ড একটিভ হলে +১ এবং চাইল্ড বোনাস পেলে আরও +১ হিসেবে প্যারেন্ট বোনাস পাবে।
    এটি রিকার্সিভলি একদম টপ প্যারেন্ট পর্যন্ত চেক করবে।
    """
    if not child_node or child_node.status != 'active':
        return

    current_node = child_node
    parent = child_node.placement_under
    
    while parent is not None:
        with transaction.atomic():
            # ডাটাবেস থেকে লেটেস্ট প্যারেন্ট ডাটা লক করে নেওয়া যাতে ক্যালকুলেশন মিস না হয়
            parent = User.objects.select_for_update().get(pk=parent.pk)
            
            # ধাপ ১: আপলাইন কাউন্ট আপডেট (সবসময় হবে র‍্যাঙ্ক লজিকের জন্য)
            if current_node.position == 'left':
                parent.total_left += 1
                parent.left_count += 1
            else:
                parent.total_right += 1
                parent.right_count += 1
            
            # ধাপ ২: বোনাস রিলিজ কন্ডিশন
            if parent.status == 'active':
                left_c = User.objects.filter(placement_under=parent, position='left').first()
                right_c = User.objects.filter(placement_under=parent, position='right').first()

                if left_c and right_c and left_c.status == 'active' and right_c.status == 'active':
                    # মামার লজিক: চাইল্ড একটিভ থাকলে ১, আর বোনাস পেলে আরও ১ (paid_matches)
                    eff_left = 1 + left_c.paid_matches
                    eff_right = 1 + right_c.paid_matches
                    
                    total_eligible = min(eff_left, eff_right)

                    # যদি নতুন এলিজিবিলিটি আগের পেইড বোনাসের চেয়ে বেশি হয়
                    if total_eligible > parent.paid_matches:
                        new_matches = total_eligible - parent.paid_matches
                        bonus_to_add = Decimal(new_matches * 400)
                        
                        parent.balance += bonus_to_add
                        parent.paid_matches = total_eligible
                        
                        BonusLog.objects.create(
                            user=parent, 
                            amount=bonus_to_add,
                            reason=f"Binary matching bonus: {new_matches} pair(s) matched (Chain release)"
                        )
            
            parent.save() 
            update_user_rank(parent) 
            
            # ধাপ ৩: চেইন ধরে উপরে (Root পর্যন্ত) উঠা
            current_node = parent
            parent = parent.placement_under

def calculate_commission(user):
    """ রেফারেল বোনাস এবং বাইনারি চেইন শুরু করা। """
    if user.referred_by:
        ref = user.referred_by
        with transaction.atomic():
            ref = User.objects.select_for_update().get(pk=ref.pk)
            ref.balance += Decimal(500)
            BonusLog.objects.create(user=ref, amount=Decimal(500), reason=f"Referral bonus: {user.username}")
            ref.save()
    
    # বাইনারি ম্যাচিং চেইন শুরু
    distribute_binary_matching(user)