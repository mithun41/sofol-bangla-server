from decimal import Decimal
from django.db import transaction
from collections import deque
from .models import BonusLog, User, GlobalFund, FundLog

# --- FUND MANAGEMENT UTILITIES ---

def distribute_money_to_funds(points):
    """
    অর্ডার কমপ্লিট হলে সাথে সাথে কল হবে (ইউজার একটিভ হোক বা না হোক)।
    পয়েন্ট থেকে ৬টি ফান্ডে টাকা জমা করবে।
    """
    total_money = Decimal(points) * 4
    fund, created = GlobalFund.objects.get_or_create(id=1)
    
    distributions = {
        'referral_fund': total_money * Decimal('0.125'),   # 12.5%
        'matching_fund': total_money * Decimal('0.10'),    # 10.0%
        'rank_reward_fund': total_money * Decimal('0.125'), # 12.5%
        'tour_fund': total_money * Decimal('0.25'),        # 25.0%
        'leadership_fund': total_money * Decimal('0.125'),  # 12.5%
        'company_fund': total_money * Decimal('0.275'),     # 27.5%
    }

    with transaction.atomic():
        for field, amount in distributions.items():
            current_val = getattr(fund, field)
            setattr(fund, field, current_val + amount)
            FundLog.objects.create(
                fund_type=field, amount=amount, 
                transaction_type='inbound', 
                reason=f"Point Inflow: {points} pts"
            )
        fund.save()

def deduct_from_fund(primary_fund_name, amount):
    """বোনাস দেওয়ার আগে ফান্ড চেক করবে। না থাকলে কোম্পানি ফান্ড থেকে নিবে।"""
    fund, created = GlobalFund.objects.get_or_create(id=1)
    primary_balance = getattr(fund, primary_fund_name)
    company_balance = fund.company_fund
    amount = Decimal(amount)

    if primary_balance >= amount:
        setattr(fund, primary_fund_name, primary_balance - amount)
        FundLog.objects.create(fund_type=primary_fund_name, amount=amount, transaction_type='outbound', reason="Bonus Payout")
    elif (primary_balance + company_balance) >= amount:
        remaining = amount - primary_balance
        setattr(fund, primary_fund_name, 0)
        fund.company_fund -= remaining
        FundLog.objects.create(fund_type=primary_fund_name, amount=primary_balance, transaction_type='outbound', reason="Primary Fund Depleted")
        FundLog.objects.create(fund_type='company_fund', amount=remaining, transaction_type='outbound', reason="Covered by Company Fund")
    else:
        # ব্যালেন্স না থাকলে বোনাস ট্রানজ্যাকশন হবে না
        return False
    
    fund.save()
    return True

# --- PLACEMENT LOGIC ---

def find_auto_placement_with_division(referrer_node, user_division):
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

# --- MLM CORE LOGIC ---

def update_user_rank(user):
    """র‍্যাঙ্ক বোনাস এখন rank_reward_fund থেকে কাটা হবে।"""
    matching = min(user.total_left, user.total_right)
    new_star = 0
    if matching >= 1200: new_star = 8
    elif matching >= 500: new_star = 7
    elif matching >= 200: new_star = 6
    elif matching >= 50: new_star = 5
    elif matching >= 15: new_star = 4
    
    if new_star > user.star_level:
        star_bonuses = {4: 5000, 5: 10000, 6: 30000, 7: 50000, 8: 100000}
        for level in range(user.star_level + 1, new_star + 1):
            if level in star_bonuses:
                bonus = Decimal(star_bonuses[level])
                if deduct_from_fund('rank_reward_fund', bonus):
                    user.balance += bonus
                    user.star_level = level 
                    BonusLog.objects.create(
                        user=user, amount=bonus,
                        reason=f"Rank Reward: {level} Star"
                    )
        user.save()

def distribute_binary_matching(child_node):
    """ম্যাচিং বোনাস এখন matching_fund থেকে কাটা হবে।"""
    if not child_node or child_node.status != 'active':
        return

    current_node = child_node
    parent = child_node.placement_under
    
    while parent is not None:
        with transaction.atomic():
            parent = User.objects.select_for_update().get(pk=parent.pk)
            
            if current_node.position == 'left':
                parent.total_left += 1
                parent.left_count += 1
            else:
                parent.total_right += 1
                parent.right_count += 1
            
            if parent.status == 'active':
                left_c = User.objects.filter(placement_under=parent, position='left').first()
                right_c = User.objects.filter(placement_under=parent, position='right').first()

                if left_c and right_c and left_c.status == 'active' and right_c.status == 'active':
                    eff_left = 1 + left_c.paid_matches
                    eff_right = 1 + right_c.paid_matches
                    total_eligible = min(eff_left, eff_right)

                    if total_eligible > parent.paid_matches:
                        new_matches = total_eligible - parent.paid_matches
                        bonus_to_add = Decimal(new_matches * 400)
                        
                        if deduct_from_fund('matching_fund', bonus_to_add):
                            parent.balance += bonus_to_add
                            parent.paid_matches = total_eligible
                            BonusLog.objects.create(
                                user=parent, 
                                amount=bonus_to_add,
                                reason=f"Matching Bonus: {new_matches} pair(s)"
                            )
            
            parent.save() 
            update_user_rank(parent) 
            
            current_node = parent
            parent = parent.placement_under

def calculate_commission(user):
    """
    ইউজার ১০০০ পয়েন্টে একটিভ হওয়ার পর এই ফাংশন কল হয়।
    পয়েন্ট থেকে ফান্ডের ডিস্ট্রিবিউশন এখন মডেলের save() মেথড থেকে সরাসরি হয়।
    এখানে শুধু রেফারেল এবং বাইনারি চেইন প্রসেস হবে।
    """
    if user.referred_by:
        ref = user.referred_by
        bonus_amount = Decimal(500)
        
        if deduct_from_fund('referral_fund', bonus_amount):
            with transaction.atomic():
                ref = User.objects.select_for_update().get(pk=ref.pk)
                ref.balance += bonus_amount
                BonusLog.objects.create(
                    user=ref, 
                    amount=bonus_amount, 
                    reason=f"Direct Referral: {user.username}"
                )
                ref.save()
    
    # বাইনারি ডিস্ট্রিবিউশন শুরু
    distribute_binary_matching(user)