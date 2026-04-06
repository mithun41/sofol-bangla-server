from decimal import Decimal
from django.db import transaction
from collections import deque
from .models import BonusLog, User, GlobalFund, FundLog


# --- FUND MANAGEMENT UTILITIES ---
# accounts/services.py


from decimal import Decimal


from decimal import Decimal


def distribute_money_to_funds(amount_to_distribute=4000):
    """৪০০০ টাকা নির্ধারিত ফান্ডগুলোতে ভাগ করে দেয়"""
    total_money = Decimal(str(amount_to_distribute))

    with transaction.atomic():
        # ফান্ড অবজেক্ট লক করে আনা (ID 1 নিশ্চিত করা)
        fund, _ = GlobalFund.objects.select_for_update().get_or_create(id=1)

        # নির্ধারিত অ্যামাউন্ট (তোর চার্ট অনুযায়ী)
        ref_amt = Decimal("500.00")
        match_amt = Decimal("400.00")
        rank_amt = Decimal("500.00")
        tour_amt = Decimal("1000.00")
        lead_amt = Decimal("500.00")
        comp_amt = Decimal("1100.00")

        # ডাটাবেজ ফিল্ড float হলেও Decimal এ কনভার্ট করে যোগ করা
        fund.referral_fund = Decimal(str(fund.referral_fund)) + ref_amt
        fund.matching_fund = Decimal(str(fund.matching_fund)) + match_amt
        fund.rank_reward_fund = Decimal(str(fund.rank_reward_fund)) + rank_amt
        fund.tour_fund = Decimal(str(fund.tour_fund)) + tour_amt
        fund.leadership_fund = Decimal(str(fund.leadership_fund)) + lead_amt
        fund.company_fund = Decimal(str(fund.company_fund)) + comp_amt

        fund.save()

        # হিসেবের জন্য লগ রাখা
        FundLog.objects.create(
            fund_type="Global",
            amount=total_money,
            transaction_type="inbound",
            reason=f"Fixed 4000 TK Distribution: Ref 500, Match 400, Rank 500, Tour 1000, Lead 500, Comp 1100",
        )
    return True


def add_bonus_to_user(user, amount, bonus_type):
    """
    ইউজারের প্রোফাইলে নির্দিষ্ট বোনাস যোগ করে এবং মেইন ব্যালেন্স আপডেট করে।
    """
    if amount <= 0:
        return

    if bonus_type == "referral":
        user.referral_bonus += amount
    elif bonus_type == "matching":
        user.matching_bonus += amount
    elif bonus_type == "leadership":
        user.leadership_bonus += amount
    elif bonus_type == "rank_reward":
        user.rank_reward_bonus += amount

    user.balance += amount
    user.save()

    # বোনাস লগ তৈরি
    BonusLog.objects.create(user=user, amount=amount, bonus_type=bonus_type)


def deduct_from_fund(primary_fund_name, amount):
    fund, _ = GlobalFund.objects.get_or_create(id=1)
    primary_balance = getattr(fund, primary_fund_name)
    company_balance = fund.company_fund
    amount = Decimal(amount)

    with transaction.atomic():
        if primary_balance >= amount:
            setattr(fund, primary_fund_name, primary_balance - amount)
            FundLog.objects.create(
                fund_type=primary_fund_name,
                amount=amount,
                transaction_type="outbound",
                reason="Bonus distribution",
            )
        elif (primary_balance + company_balance) >= amount:
            remaining = amount - primary_balance
            setattr(fund, primary_fund_name, 0)
            fund.company_fund -= remaining
            FundLog.objects.create(
                fund_type=primary_fund_name,
                amount=primary_balance,
                transaction_type="outbound",
                reason="Partial bonus",
            )
            FundLog.objects.create(
                fund_type="company_fund",
                amount=remaining,
                transaction_type="outbound",
                reason="Bonus backup support",
            )
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
    max_generation = 5  # ৮ স্টার সর্বোচ্চ ৫ লেভেল পর্যন্ত পায়

    while current_upline and generation <= max_generation:
        with transaction.atomic():
            # ডাটাবেজ থেকে আপলাইনকে লক করে আনা হচ্ছে যাতে ব্যালেন্স মিস না হয়
            upline = User.objects.select_for_update().get(pk=current_upline.pk)

            # এলিজিবিলিটি চেক: ৪ স্টার=১ লেভেল, ৫ স্টার=২ লেভেল... ৮ স্টার=৫ লেভেল
            is_eligible = False
            if upline.star_level == 4 and generation <= 1:
                is_eligible = True
            elif upline.star_level == 5 and generation <= 2:
                is_eligible = True
            elif upline.star_level == 6 and generation <= 3:
                is_eligible = True
            elif upline.star_level == 7 and generation <= 4:
                is_eligible = True
            elif upline.star_level == 8 and generation <= 5:
                is_eligible = True

            # যদি ইউজার এলিজিবল এবং একটিভ থাকে
            if is_eligible and upline.status == "active":
                l_bonus = Decimal(bonus_amount) * Decimal("0.10")

                # ফান্ড থেকে টাকা কমানো সফল হলে বোনাস দেওয়া হবে
                if deduct_from_fund("leadership_fund", l_bonus):
                    upline.balance += l_bonus
                    upline.leadership_bonus += l_bonus  # প্রোফাইলের লিডারশিপ বোনাস আপডেট
                    upline.save()

                    # বোনাস লগ তৈরি
                    BonusLog.objects.create(
                        user=upline,
                        amount=l_bonus,
                        reason=f"Leadership Bonus: Gen {generation} from {earner_user.username}",
                    )

        # পরের জেনারেশনের (উপরিভাগের প্যারেন্ট) দিকে যাওয়া
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
            for pos in ["left", "right"]:
                if not User.objects.filter(
                    placement_under=div_node, position=pos
                ).exists():
                    return div_node, pos
    return find_auto_placement(referrer_node)


def find_auto_placement(referrer_node):
    queue = deque([referrer_node])
    while queue:
        current = queue.popleft()
        for pos in ["left", "right"]:
            child = User.objects.filter(placement_under=current, position=pos).first()
            if not child:
                return current, pos
            queue.append(child)
    return None, None


# --- MLM CORE LOGIC ---


def update_user_rank(user):
    matching = min(user.left_count, user.right_count)
    new_star = 0

    if matching >= 1200:
        new_star = 8
    elif matching >= 500:
        new_star = 7
    elif matching >= 200:
        new_star = 6
    elif matching >= 50:
        new_star = 5
    elif matching >= 15:
        new_star = 4
    

    if new_star > user.star_level:
        star_bonuses = { 4: 5000, 5: 10000, 6: 30000, 7: 50000, 8: 100000}

        for level in range(user.star_level + 1, new_star + 1):
            if level in star_bonuses:
                bonus = Decimal(str(star_bonuses[level]))

                # এখানে deduct_from_fund ফাংশনটি কল হচ্ছে
                from .services import deduct_from_fund  # যদি প্রয়োজন হয়

                if deduct_from_fund("rank_reward_fund", bonus):
                    user.balance += bonus
                    user.rank_reward_bonus += bonus
                    user.star_level = level

                    # --- এই অংশটুকু খেয়াল করুন ---
                    # আপনার মডেলে 'bonus_type' নেই, তাই শুধু 'reason' ব্যবহার করছি
                    BonusLog.objects.create(
                        user=user, amount=bonus, reason=f"Rank Reward: {level} Star"
                    )
        user.save()


def distribute_binary_matching(child_node):
    if not child_node or child_node.status != "active":
        return

    current_node = child_node
    parent = child_node.placement_under

    while parent is not None:
        with transaction.atomic():
            parent = User.objects.select_for_update().get(pk=parent.pk)

            if current_node.position == "left":
                parent.total_left += 1
                parent.left_count += 1
            else:
                parent.total_right += 1
                parent.right_count += 1

            if parent.status == "active":
                left_c = User.objects.filter(
                    placement_under=parent, position="left"
                ).first()
                right_c = User.objects.filter(
                    placement_under=parent, position="right"
                ).first()

                if (
                    left_c
                    and right_c
                    and left_c.status == "active"
                    and right_c.status == "active"
                ):
                    eff_left = 1 + left_c.paid_matches
                    eff_right = 1 + right_c.paid_matches
                    total_eligible = min(eff_left, eff_right)

                    if total_eligible > parent.paid_matches:
                        new_matches = total_eligible - parent.paid_matches
                        bonus_to_add = Decimal(new_matches * 400)

                        if deduct_from_fund("matching_fund", bonus_to_add):
                            parent.balance += bonus_to_add
                            parent.paid_matches = total_eligible
                            parent.save()  # সেভ করা হলো যাতে জেনারেশন বোনাস ঠিকঠাক পায়
                            BonusLog.objects.create(
                                user=parent,
                                amount=bonus_to_add,
                                reason=f"Matching Bonus: {new_matches} pair(s)",
                            )
                            # লিডারশিপ বোনাস ডিস্ট্রিবিউশন
                            distribute_leadership_bonus(parent, bonus_to_add)

            parent.save()
            update_user_rank(parent)

            current_node = parent
            parent = parent.placement_under


def calculate_commission(new_active_user):
    """
    ইউজার এক্টিভ হওয়ার পর বাইনারি ট্রি-তে ওপরের দিকে ম্যাচিং বোনাস ডিস্ট্রিবিউট করে।
    লজিক: ২ জন চাইল্ড এক্টিভ হলে ১ম ম্যাচিং, এরপর চাইল্ডরা ম্যাচিং পেলে আপলাইন আবার ম্যাচিং পাবে।
    """
    with transaction.atomic():
        activation_amount = Decimal("4000.00")
        matching_bonus_amt = Decimal("400.00")

        # ১. রেফারেল বোনাস (৫০০ টাকা)
        referrer = new_active_user.referred_by
        if referrer and referrer.status == "active":
            ref_bonus = activation_amount * Decimal("0.125")
            if deduct_from_fund("referral_fund", ref_bonus):
                referrer.balance += ref_bonus
                referrer.referral_bonus += ref_bonus
                referrer.save()
                BonusLog.objects.create(
                    user=referrer,
                    amount=ref_bonus,
                    reason=f"Referral Bonus: {new_active_user.username}",
                )

        # ২. বাইনারি ম্যাচিং লজিক
        child_node = new_active_user
        parent = new_active_user.placement_under

        while parent:
            # ডাটাবেজ থেকে লেটেস্ট প্যারেন্ট ডাটা লক করে আনা
            parent = User.objects.select_for_update().get(pk=parent.pk)

            # কাউন্ট আপডেট (Active মেম্বার হিসেবে)
            if child_node.position == "left":
                parent.left_count += 1
                parent.total_left += 1
            else:
                parent.right_count += 1
                parent.total_right += 1

            # ম্যাচিং চেক (যদি প্যারেন্ট একটিভ থাকে)
            if parent.status == "active":
                # বাম ও ডানের চাইল্ড অবজেক্ট আনা
                left_child = User.objects.filter(
                    placement_under=parent, position="left"
                ).first()
                right_child = User.objects.filter(
                    placement_under=parent, position="right"
                ).first()

                if (
                    left_child
                    and right_child
                    and left_child.status == "active"
                    and right_child.status == "active"
                ):
                    # --- স্পেশাল লজিক ---
                    # চাইল্ডরা নিজেরা কয়টা ম্যাচিং খেয়েছে (paid_matches) + তারা নিজেরা এক্টিভ কি না (+1)
                    # এটা নিশ্চিত করে যে চাইল্ডরা বোনাস পেলে আপলাইন আবার বোনাস পাবে।
                    eligible_left = 1 + left_child.paid_matches
                    eligible_right = 1 + right_child.paid_matches

                    total_potential_matches = min(eligible_left, eligible_right)

                    # যদি নতুন কোনো ম্যাচিং তৈরি হয়
                    if total_potential_matches > parent.paid_matches:
                        new_pairs = total_potential_matches - parent.paid_matches
                        total_bonus = new_pairs * matching_bonus_amt

                        if deduct_from_fund("matching_fund", total_bonus):
                            parent.balance += total_bonus
                            parent.matching_bonus += total_bonus
                            parent.paid_matches = (
                                total_potential_matches  # ম্যাচিং কাউন্ট আপডেট
                            )

                            BonusLog.objects.create(
                                user=parent,
                                amount=total_bonus,
                                reason=f"Recursive Matching Bonus ({new_pairs} pair)",
                            )
                            # লিডারশিপ বোনাস পাঠানো
                            distribute_leadership_bonus(parent, total_bonus)

            # র‍্যাঙ্ক এবং সেভ
            update_user_rank(parent)
            parent.save()

            # উপরে উঠার লজিক
            child_node = parent
            parent = parent.placement_under


def calculate_and_apply_order_benefits(order):
    """অর্ডার কমপ্লিট হলে পয়েন্ট এবং এক্টিভেশন লজিক চালায়"""
    user = order.user
    if not user:
        return False

    order_pv_int = int(order.total_pv or 0)
    order_pv_decimal = Decimal(str(order.total_pv or 0))

    with transaction.atomic():
        # ইউজারকে লক করে আনা যাতে ডাবল এন্ট্রি না হয়
        user = User.objects.select_for_update().get(pk=user.pk)

        # পয়েন্ট যোগ করা
        current_points = user.points or 0
        user.points = current_points + order_pv_int

        # স্ট্যাটাস চেক (Case insensitive)
        current_status = str(user.status).strip().lower()

        if current_status == "active":
            # --- একটিভ ইউজার: ২ গুণ ক্যাশব্যাক ---
            offer_amount = order_pv_decimal * Decimal("2.0")
            user.lifetime_offer_points += order_pv_decimal
            user.total_offer_earned += offer_amount
            user.balance += offer_amount
            user.save()

            BonusLog.objects.create(
                user=user,
                amount=offer_amount,
                reason=f"Order Cashback for #{order.order_number}",
            )
        else:
            # --- ইন-একটিভ ইউজার: এক্টিভেশন চেক ---
            if user.points >= 1000:
                user.status = "active"
                user.save()  # স্ট্যাটাস আগে সেভ
                print(f"DEBUG: {user.username} is now ACTIVE!")

                # কমিশন লজিক (Try-Except যাতে এরর আসলে রোলব্যাক না হয়)
                try:
                    # এখানে যদি তোর কমিশন ফাংশন থাকে তবে কল করবি
                    # from .mlm_logic import calculate_commission
                    # calculate_commission(user)
                    pass
                except Exception as e:
                    print(f"MLM/Commission Error: {e}")
            else:
                user.save()  # শুধু পয়েন্ট আপডেট

    user.refresh_from_db()
    return True
