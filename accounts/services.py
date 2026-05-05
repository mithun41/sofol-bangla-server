from decimal import Decimal
from django.db import transaction
from collections import deque
from .models import BonusLog, User, GlobalFund, FundLog


def distribute_money_to_funds(amount_to_distribute=4000, *args, **kwargs):
    """৪০০০ টাকা নির্ধারিত ফান্ডগুলোতে ভাগ করে দেয়"""
    total_money = Decimal(str(amount_to_distribute or "0.00"))

    with transaction.atomic():
        # ফান্ড অবজেক্ট লক করে আনা (ID 1 নিশ্চিত করা)
        fund, _ = GlobalFund.objects.select_for_update().get_or_create(id=1)

        # নির্ধারিত অ্যামাউন্ট
        ref_amt = Decimal("500.00")
        match_amt = Decimal("400.00")
        rank_amt = Decimal("500.00")
        tour_amt = Decimal("1000.00")
        lead_amt = Decimal("500.00")
        comp_amt = Decimal("1100.00")

        # ডাটাবেজ ফিল্ড None থাকলে সেটাকে "0.00" ধরে হিসাব করা (Fixes ConversionSyntax Error)
        fund.referral_fund = Decimal(str(fund.referral_fund or "0.00")) + ref_amt
        fund.matching_fund = Decimal(str(fund.matching_fund or "0.00")) + match_amt
        fund.rank_reward_fund = Decimal(str(fund.rank_reward_fund or "0.00")) + rank_amt
        fund.tour_fund = Decimal(str(fund.tour_fund or "0.00")) + tour_amt
        fund.leadership_fund = Decimal(str(fund.leadership_fund or "0.00")) + lead_amt
        fund.company_fund = Decimal(str(fund.company_fund or "0.00")) + comp_amt

        fund.save()

        # হিসেবের জন্য লগ রাখা
        logs = [
            FundLog(
                fund_type="referral_fund",
                amount=Decimal("500.00"),
                transaction_type="inbound",
                reason="Activation: Referral Fund share",
            ),
            FundLog(
                fund_type="matching_fund",
                amount=Decimal("400.00"),
                transaction_type="inbound",
                reason="Activation: Matching Fund share",
            ),
            FundLog(
                fund_type="rank_reward_fund",
                amount=Decimal("500.00"),
                transaction_type="inbound",
                reason="Activation: Rank Reward Fund share",
            ),
            FundLog(
                fund_type="tour_fund",
                amount=Decimal("1000.00"),
                transaction_type="inbound",
                reason="Activation: Tour Fund share",
            ),
            FundLog(
                fund_type="leadership_fund",
                amount=Decimal("500.00"),
                transaction_type="inbound",
                reason="Activation: Leadership Fund share",
            ),
            FundLog(
                fund_type="company_fund",
                amount=Decimal("1100.00"),
                transaction_type="inbound",
                reason="Activation: Company Fund share",
            ),
        ]
        FundLog.objects.bulk_create(logs)
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
        star_bonuses = {4: 5000, 5: 10000, 6: 30000, 7: 50000, 8: 100000}

        for level in range(user.star_level + 1, new_star + 1):
            if level in star_bonuses:
                bonus = Decimal(str(star_bonuses[level]))

                if deduct_from_fund("rank_reward_fund", bonus):
                    user.balance += bonus
                    user.rank_reward_bonus += bonus
                    user.star_level = level

                    # --- এই অংশটুকু খেয়াল করুন ---
                    # আপনার মডেলে 'bonus_type' নেই, তাই শুধু 'reason' ব্যবহার করছি
                    BonusLog.objects.create(
                        user=user,
                        amount=bonus,
                        reason=f"Rank Reward: {level} Star - {STAR_TITLES[level]}",
                    )
        user.save()
        STAR_TITLES = {
            0: "Member",
            1: "Member",
            2: "Member",
            3: "Member",
            4: "Leader",
            5: "Sales Officer",
            6: "Sr. Sales Officer",
            7: "Incharge",
            8: "Manager",
        }


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
    ম্যাচিং লজিক (আপডেটেড):
    ১. রেফারার একটিভ না থাকলেও বোনাস পাবে।
    ২. বাইনারি ম্যাচিং লজিক (প্যারেন্ট ইন-একটিভ হলেও বোনাস পাবে)।
    ৩. অটোমেটিক র‍্যাঙ্ক আপডেট।
    """
    with transaction.atomic():
        matching_bonus_amt = Decimal("400.00")

        # ১. রেফারেল বোনাস (Status Check রিমুভ করা হয়েছে)
        referrer = new_active_user.referred_by
        if referrer:  # শুধু ইউজার আছে কি না সেটা চেক করবে, একটিভ কি না দেখবে না
            # চেক: এই নতুন ইউজারের জন্য অলরেডি রেফার বোনাস দেওয়া হয়েছে কি না
            if not BonusLog.objects.filter(
                user=referrer,
                reason__contains=f"Referral Bonus: {new_active_user.username}",
            ).exists():
                ref_bonus = Decimal("500.00")

                if deduct_from_fund("referral_fund", ref_bonus):
                    referrer.balance = (
                        Decimal(str(referrer.balance or "0.00")) + ref_bonus
                    )
                    referrer.referral_bonus = (
                        Decimal(str(referrer.referral_bonus or "0.00")) + ref_bonus
                    )
                    referrer.save()

                    BonusLog.objects.create(
                        user=referrer,
                        amount=ref_bonus,
                        reason=f"Referral Bonus: {new_active_user.username}",
                    )
                    print(
                        f"SUCCESS: Referral bonus added to {referrer.username} (Regardless of status)"
                    )

        # ২. বাইনারি ম্যাচিং লজিক
        child_node = new_active_user
        parent = new_active_user.placement_under

        while parent:
            parent = User.objects.select_for_update().get(pk=parent.pk)

            # পজিশন অনুযায়ী কাউন্ট বাড়ানো (এটি ইন-একটিভ হলেও হবে)
            if child_node.position == "left":
                parent.left_count += 1
                parent.total_left += 1
            else:
                parent.right_count += 1
                parent.total_right += 1

            # ম্যাচিং বোনাস চেক (এখানেও status == "active" চেক রিমুভ করা হয়েছে)
            left_child = User.objects.filter(
                placement_under=parent, position="left"
            ).first()
            right_child = User.objects.filter(
                placement_under=parent, position="right"
            ).first()

            # শর্ত: শুধু দুই পাশে চাইল্ড থাকতে হবে (চাইল্ডরা একটিভ কি না সেটা তোর আগের লজিক অনুযায়ী রাখা হলো)
            if (
                left_child
                and right_child
                and str(left_child.status).lower().strip() == "active"
                and str(right_child.status).lower().strip() == "active"
            ):

                eligible_left = 1 + (left_child.paid_matches or 0)
                eligible_right = 1 + (right_child.paid_matches or 0)
                total_potential_matches = min(eligible_left, eligible_right)

                if total_potential_matches > (parent.paid_matches or 0):
                    new_pairs = total_potential_matches - (parent.paid_matches or 0)
                    total_bonus = new_pairs * matching_bonus_amt

                    if deduct_from_fund("matching_fund", total_bonus):
                        parent.balance = (
                            Decimal(str(parent.balance or "0.00")) + total_bonus
                        )
                        parent.matching_bonus = (
                            Decimal(str(parent.matching_bonus or "0.00")) + total_bonus
                        )
                        parent.paid_matches = total_potential_matches
                        parent.save()

                        BonusLog.objects.create(
                            user=parent,
                            amount=total_bonus,
                            reason=f"Recursive Matching Bonus ({new_pairs} pair)",
                        )

                        # লিডারশিপ বোনাস (এটিও এখন ইন-একটিভ ইউজাররা পাবে)
                        try:
                            distribute_leadership_bonus(parent, total_bonus)
                        except Exception as e:
                            print(f"Leadership Bonus Error: {e}")

            # র‍্যাঙ্ক আপডেট এবং সেভ
            try:
                update_user_rank(parent)
            except Exception as e:
                print(f"Rank Update Error: {e}")

            parent.save()

            child_node = parent
            parent = parent.placement_under

    return True


def calculate_and_apply_order_benefits(order):
    """Order complete hole point, activation ebong MLM bonus trigger korbe (Cashback chara)"""
    user = order.user
    if not user:
        return False

    order_pv_int = int(order.total_pv or 0)

    with transaction.atomic():
        # User-ke lock kora jate race condition na hoy
        user = User.objects.select_for_update().get(pk=user.pk)

        # ১. Point add kora (Inactive theke Active howar jonno)
        current_points = user.points or 0
        user.points = current_points + order_pv_int

        # ২. Status check (Case insensitive)
        current_status = str(user.status).strip().lower()

        if current_status == "active":
            # --- Active User: Shudhu point update hobe, CASHBACK JABENA ---
            user.save()
            print(f"DEBUG: {user.username} (Active) - Points updated, no cashback.")

        else:
            # --- Inactive User: Activation logic ---
            if user.points >= 1000:
                user.status = "active"
                user.save()  # Age status active kore nite hobe
                print(f"DEBUG: {user.username} is now ACTIVE!")

                # ৩. MLM Bonus Trigger (Referral, Matching, Rank, etc.)
                try:
                    from accounts.services import calculate_commission

                    # Ekhon theke Reff, Matching, Rank bonus calculate hobe
                    calculate_commission(user)
                except Exception as e:
                    print(f"MLM/Commission Error: {e}")
            else:
                user.save()  # 1000 point na howa porjonto shudhu point update hobe

    user.refresh_from_db()
    return True


def apply_auto_referral(user_instance):
    """
    যদি ইউজার রেজিস্ট্রেশনের সময় কোনো রেফারার না থাকে,
    তবে তার ডিক্লেয়ার করা division অনুযায়ী অটো রেফারার সেট করবে।
    """
    # ১. যদি অলরেডি রেফারার থাকে, তবে আর কিছু করার দরকার নেই
    if user_instance.referred_by:
        return user_instance

    # ২. যদি রেফারার না থাকে, তবে তার বিভাগ অনুযায়ী ইউজার খুঁজবে
    if user_instance.division:
        # বিভাগের নাম অনুযায়ী ইউজারকে খুঁজবে (যেমন: 'dhaka' ইউজারনেম)
        fallback_referrer = User.objects.filter(
            username=user_instance.division.lower()
        ).first()

        if fallback_referrer:
            user_instance.referred_by = fallback_referrer
        else:
            # যদি বিভাগের নামে ইউজার না থাকে, তবে 'admin' কে চেক করবে
            admin_user = User.objects.filter(username="admin").first()
            if admin_user:
                user_instance.referred_by = admin_user

    return user_instance
