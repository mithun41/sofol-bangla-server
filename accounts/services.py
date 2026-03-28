from decimal import Decimal
from django.db import transaction
from collections import deque
from .models import BonusLog, User, GlobalFund, FundLog

# --- FUND MANAGEMENT UTILITIES ---


def distribute_money_to_funds(points):
    total_money = Decimal(points) * 4
    # Singleton pattern for GlobalFund
    fund, _ = GlobalFund.objects.get_or_create(id=1)
    
    distributions = {
        'referral_fund': total_money * Decimal('0.125'),
        'matching_fund': total_money * Decimal('0.10'),
        'rank_reward_fund': total_money * Decimal('0.125'),
        'tour_fund': total_money * Decimal('0.25'),
        'leadership_fund': total_money * Decimal('0.125'),
        'company_fund': total_money * Decimal('0.275'),
    }

    with transaction.atomic():
        for field, amount in distributions.items():
            current_val = getattr(fund, field)
            setattr(fund, field, current_val + amount)
            FundLog.objects.create(
                fund_type=field, amount=amount, 
                transaction_type='inbound', reason=f"Distribution from {points} points"
            )
        fund.save()
def add_bonus_to_user(user, amount, bonus_type):
    """
    bonus_type হতে পারে: 'referral', 'matching', 'leadership', 'rank'
    """
    amount = Decimal(amount)
    with transaction.atomic():
        if bonus_type == 'referral':
            user.referral_bonus += amount
        elif bonus_type == 'matching':
            user.matching_bonus += amount
        elif bonus_type == 'leadership':
            user.leadership_bonus += amount
        elif bonus_type == 'rank':
            user.rank_reward_bonus += amount
            
        # মেইন ব্যালেন্সেও টাকা যোগ হবে যেন সে উইথড্র করতে পারে
        user.balance += amount
        user.save()
        
        # লগ রাখা
        BonusLog.objects.create(user=user, amount=amount, reason=f"{bonus_type.capitalize()} Bonus Received")
def deduct_from_fund(primary_fund_name, amount):
    fund, _ = GlobalFund.objects.get_or_create(id=1)
    primary_balance = getattr(fund, primary_fund_name)
    company_balance = fund.company_fund
    amount = Decimal(amount)

    with transaction.atomic():
        if primary_balance >= amount:
            setattr(fund, primary_fund_name, primary_balance - amount)
            FundLog.objects.create(fund_type=primary_fund_name, amount=amount, transaction_type='outbound', reason="Bonus distribution")
        elif (primary_balance + company_balance) >= amount:
            remaining = amount - primary_balance
            setattr(fund, primary_fund_name, 0)
            fund.company_fund -= remaining
            FundLog.objects.create(fund_type=primary_fund_name, amount=primary_balance, transaction_type='outbound', reason="Partial bonus")
            FundLog.objects.create(fund_type='company_fund', amount=remaining, transaction_type='outbound', reason="Bonus backup support")
        else:
            return False 
        fund.save()
        return True
# --- LEADERSHIP BONUS LOGIC (NEW) ---

def distribute_leadership_bonus(earner_user, bonus_amount):
    """
    যখনই কেউ বোনাস পাবে, তার আপলাইনরা তাদের স্টার লেভেল অনুযায়ী 
    জেনারেশন বোনাস (১০%) পাবে লিডারশিপ ফান্ড থেকে।
    """
    current_upline = earner_user.placement_under
    generation = 1
    max_generation = 5  # ৮ স্টার সর্বোচ্চ ৫ লেভেল পর্যন্ত পায়

    while current_upline and generation <= max_generation:
        with transaction.atomic():
            upline = User.objects.select_for_update().get(pk=current_upline.pk)
            
            # এলিজিবিলিটি চেক: ৪ স্টার=১ লেভেল, ৫ স্টার=২ লেভেল... ৮ স্টার=৫ লেভেল
            is_eligible = False
            if upline.star_level == 4 and generation <= 1: is_eligible = True
            elif upline.star_level == 5 and generation <= 2: is_eligible = True
            elif upline.star_level == 6 and generation <= 3: is_eligible = True
            elif upline.star_level == 7 and generation <= 4: is_eligible = True
            elif upline.star_level == 8 and generation <= 5: is_eligible = True

            if is_eligible and upline.status == 'active':
                l_bonus = Decimal(bonus_amount) * Decimal('0.10')
                
                if deduct_from_fund('leadership_fund', l_bonus):
                    upline.balance += l_bonus
                    upline.save()
                    BonusLog.objects.create(
                        user=upline, amount=l_bonus,
                        reason=f"Leadership Bonus: Gen {generation} from {earner_user.username}"
                    )
        
        current_upline = upline.placement_under
        generation += 1

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
                            parent.save() # সেভ করা হলো যাতে জেনারেশন বোনাস ঠিকঠাক পায়
                            BonusLog.objects.create(
                                user=parent, amount=bonus_to_add,
                                reason=f"Matching Bonus: {new_matches} pair(s)"
                            )
                            # লিডারশিপ বোনাস ডিস্ট্রিবিউশন
                            distribute_leadership_bonus(parent, bonus_to_add)
            
            parent.save() 
            update_user_rank(parent) 
            
            current_node = parent
            parent = parent.placement_under

def calculate_commission(new_active_user):
    """
    নতুন ইউজার একটিভ হলে আপলাইনদের বাইনারি ম্যাচিং চেক।
    লজিক: ২য় বার থেকে চাইল্ডরা বোনাস পেলেই কেবল প্যারেন্ট বোনাস পাবে।
    """
    with transaction.atomic():
        activation_amount = Decimal('4000.00')
        matching_bonus_amt = activation_amount * Decimal('0.10') # ৪০০ টাকা

        # --- ১. রেফারেল বোনাস ---
        referrer = new_active_user.referred_by
        if referrer and referrer.status == 'active':
            ref_bonus = activation_amount * Decimal('0.125') # ৫০০ টাকা
            if deduct_from_fund('referral_fund', ref_bonus):
                referrer.referral_bonus += ref_bonus
                referrer.balance += ref_bonus
                referrer.save()
                BonusLog.objects.create(user=referrer, amount=ref_bonus, reason=f"Referral Bonus from {new_active_user.username}")

        # --- ২. বাইনারি ম্যাচিং লজিক (Recursive Logic) ---
        current_node = new_active_user.placement_under
        child_node = new_active_user

        while current_node:
            # শুধু কাউন্ট বাড়ানো (ট্রি ভিউ এর জন্য)
            if child_node.position == 'left':
                current_node.total_left += 1
            else:
                current_node.total_right += 1

            # ম্যাচিং এলিজিবিলিটি চেক
            if current_node.status == 'active':
                left_child = User.objects.filter(placement_under=current_node, position='left').first()
                right_child = User.objects.filter(placement_under=current_node, position='right').first()

                if left_child and right_child and left_child.status == 'active' and right_child.status == 'active':
                    # current_node এপর্যন্ত কতবার বোনাস পেয়েছে তা হলো current_node.paid_matches
                    # চাইল্ডরা কতবার বোনাস পেয়েছে (অথবা নতুন একটিভ হয়েছে কি না) তার চেক
                    # প্রথমবার: চাইল্ড একটিভ হলেই হবে (paid_matches ০ হলেও চলে)
                    # ২য় বার থেকে: চাইল্ডের paid_matches ১ বা তার বেশি হতে হবে
                    
                    left_eligible_matches = 1 + left_child.paid_matches
                    right_eligible_matches = 1 + right_child.paid_matches
                    
                    total_eligible_now = min(left_eligible_matches, right_eligible_matches)

                    # যদি বর্তমান এলিজিবিলিটি আগের পেইড ম্যাচের চেয়ে বেশি হয়
                    if total_eligible_now > current_node.paid_matches:
                        new_matches_to_pay = total_eligible_now - current_node.paid_matches
                        total_bonus = new_matches_to_pay * matching_bonus_amt

                        if deduct_from_fund('matching_fund', total_bonus):
                            current_node.matching_bonus += total_bonus
                            current_node.balance += total_bonus
                            current_node.paid_matches = total_eligible_now
                            
                            BonusLog.objects.create(
                                user=current_node, 
                                amount=total_bonus, 
                                reason=f"Binary Matching Bonus ({new_matches_to_pay} pair)"
                            )
                            # লিডারশিপ বোনাস ডিস্ট্রিবিউশন
                            distribute_leadership_bonus(current_node, total_bonus)

            # র‍্যাঙ্ক আপডেট ও সেভ
            update_user_rank(current_node)
            current_node.save()

            # উপরে উঠার লজিক
            child_node = current_node
            current_node = current_node.placement_under
            


def calculate_and_apply_order_benefits(order):
    user = order.user
    # অর্ডারের PV নিশ্চিত করা
    order_pv = Decimal(str(order.total_pv or 0))
    
    print(f"DEBUG SERVICE: Order PV: {order_pv} | User Status: '{user.status}'")

    if order_pv <= 0:
        print("DEBUG SERVICE: No PV found in order.")
        return False

    with transaction.atomic():
        # ইউজারের স্ট্যাটাস ছোট হাতের করে চেক করা (যাতে 'Active' বা 'active' দুইটাই কাজ করে)
        user_status = str(user.status).strip().lower()

        if user_status == 'active':
            # একটিভ ইউজার: ২ গুণ টাকা অফার পাবে
            offer_amount = order_pv * Decimal('2.0')
            
            user.lifetime_offer_points += order_pv
            user.total_offer_earned += offer_amount
            user.balance += offer_amount # সরাসরি মেইন ব্যালেন্সে যোগ
            user.save()
            
            # বোনাস লগ রাখা
            from accounts.models import BonusLog
            BonusLog.objects.create(
                user=user,
                amount=offer_amount,
                reason=f"Order Offer (2x PV) for Order #{order.id}"
            )
            print(f"DEBUG SERVICE: SUCCESS! Added {offer_amount} TK to balance.")
            return True
        else:
            # ইন-একটিভ ইউজার: শুধু পয়েন্ট পাবে (আইডি এক্টিভেশনের জন্য)
            user.points += order_pv
            user.save()
            print(f"DEBUG SERVICE: User inactive. Added {order_pv} points only.")
            return True