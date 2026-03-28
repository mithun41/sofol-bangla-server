from rest_framework import serializers
import requests
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import BonusLog, User, WithdrawalRequest
from .services import find_auto_placement_with_division
from decimal import Decimal
from django.db import transaction
from .models import GlobalFund, FundLog
from rest_framework.validators import UniqueValidator

import random
from django.utils import timezone
from datetime import timedelta


# ১. লগইন করার সময় সব ডাটা একসাথে পাঠানোর জন্য কাস্টম সিরিয়ালাইজার
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # ড্যাশবোর্ডের জন্য ইউজার ডাটা আপডেট
        data.update({
            'username': user.username,
            'role': user.role,
            'name': user.name,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'email': user.email,
            'phone': user.phone,
            
            # --- মেইন ব্যালেন্স ও পয়েন্ট ---
            'balance': float(user.balance),
            'points': user.points,
            
            # --- ইউজারের ব্যক্তিগত বোনাস ফান্ড (User Dashboard Funds) ---
            'referral_bonus': float(getattr(user, 'referral_bonus', 0)),
            'matching_bonus': float(getattr(user, 'matching_bonus', 0)),
            'leadership_bonus': float(getattr(user, 'leadership_bonus', 0)),
            'rank_reward_bonus': float(getattr(user, 'rank_reward_bonus', 0)),
            
            # --- নেটওয়ার্ক স্ট্যাটাস ---
            'left_count': user.left_count,
            'right_count': user.right_count,
            'total_left': user.total_left,
            'total_right': user.total_right,
            'reff_id': user.reff_id,
            'placement_id': user.placement_id,
            'status': user.status,
            'star_level': user.star_level,
        })
        return data

# ২. ইউজার প্রোফাইল দেখার বা আপডেট করার সিরিয়ালাইজার
# ১. ইউজার প্রোফাইল দেখার জন্য
class UserProfileSerializer(serializers.ModelSerializer):
    total_offer_earned = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    lifetime_offer_points = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    class Meta:
        model = User
        fields = [
            'name', 'username', 'email', 'phone', 'role', 
            'profile_picture', 'balance', 'points', 'left_count', 
            'right_count', 'total_left', 'total_right', 'reff_id', 
            'placement_id', 'status', 'star_level',
            'referral_bonus', 'matching_bonus', 
            'leadership_bonus', 'rank_reward_bonus', 'total_offer_earned', 'lifetime_offer_points',
        ]
        # এই ফিল্ডগুলো ইউজার নিজে এডিট করতে পারবে না
        read_only_fields = [
            'username', 'email', 'balance', 'points', 'reff_id', 
            'placement_id', 'role', 'status', 'star_level',
            'referral_bonus', 'matching_bonus', 'leadership_bonus', 'rank_reward_bonus'
        ]

# ২. অ্যাডমিন প্যানেলে সব ইউজার লিস্ট দেখার জন্য
class UserListSerializer(serializers.ModelSerializer):
    reff_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    referred_by_username = serializers.ReadOnlyField(source='referred_by.username')
    placement_under_username = serializers.ReadOnlyField(source='placement_under.username')

    class Meta:
        model = User
        fields = (
            'id','name', 'username', 'email', 'phone', 'reff_id', 'placement_id', 
            'points', 'balance', 'position', 'left_count', 'right_count',
            'referred_by_username', 'placement_under_username', 
            'reff_id_input', 'placement_id_input',
            'status', 'star_level', 'role', 'createdAt', 'division',
            # অ্যাডমিন যেন সবার বোনাস দেখতে পারে
            'referral_bonus', 'matching_bonus', 'leadership_bonus', 'rank_reward_bonus'
        )

# ৩. প্রোফাইল আপডেট করার জন্য (আগের মতোই থাকবে)
class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['name', 'email', 'phone', 'profile_picture', 'password']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'email': {'required': False},
            'phone': {'required': False},
        }

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True)
    username = serializers.CharField(validators=[UniqueValidator(queryset=User.objects.all())])
    phone = serializers.CharField(required=True)
    reff_code_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    position_input = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('name', 'username', 'password', 'email', 'phone', 'division', 'reff_code_input', 'placement_id_input', 'position_input')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        reff_code = validated_data.pop('reff_code_input', None)
        placement_code = validated_data.pop('placement_id_input', None)
        pos_input = validated_data.pop('position_input', None)
        
        user = User.objects.create_user(**validated_data)

        if reff_code:
            user.referred_by = User.objects.filter(reff_id=reff_code).first()

        if placement_code:
            placer = User.objects.filter(placement_id=placement_code).first()
            if placer:
                user.placement_under = placer
                user.position = pos_input if pos_input in ['left', 'right'] else ('left' if not User.objects.filter(placement_under=placer, position='left').exists() else 'right')
        elif user.referred_by:
            from .utils import find_auto_placement_with_division
            parent, pos = find_auto_placement_with_division(user.referred_by, validated_data.get('division', ''))
            user.placement_under, user.position = parent, pos

        user.save()
        return user

class BonusLogSerializer(serializers.ModelSerializer):
    user_username = serializers.ReadOnlyField(source='user.username')
    class Meta:
        model = BonusLog
        fields = ['id', 'user_username', 'amount', 'reason', 'timestamp']

class WithdrawalSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    class Meta:
        model = WithdrawalRequest
        fields = ['id', 'amount','username', 'method', 'account_number', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']
        

# ১. ফান্ডে টাকা জমানোর লজিক (১০০০ পয়েন্ট = ৪০০০ টাকা হিসেবে)
def distribute_money_to_funds(points):
    total_money = Decimal(points) * 4
    fund, created = GlobalFund.objects.get_or_create(id=1)
    
    # তোর দেওয়া ক্যালকুলেশন অনুযায়ী পারসেন্টেজ
    distributions = {
        'referral_fund': total_money * Decimal('0.125'),  # ১২.৫%
        'matching_fund': total_money * Decimal('0.10'),   # ১০%
        'rank_reward_fund': total_money * Decimal('0.125'),# ১২.৫%
        'tour_fund': total_money * Decimal('0.25'),       # ২৫%
        'leadership_fund': total_money * Decimal('0.125'), # ১২.৫%
        'company_fund': total_money * Decimal('0.275'),    # ২৭.৫%
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

# ২. ফান্ড থেকে টাকা কাটানোর লজিক (ব্যাকআপ হিসেবে কোম্পানি ফান্ডসহ)
def deduct_from_fund(primary_fund_name, amount):
    fund, created = GlobalFund.objects.get_or_create(id=1)
    primary_balance = getattr(fund, primary_fund_name)
    company_balance = fund.company_fund
    
    amount = Decimal(amount)

    with transaction.atomic():
        if primary_balance >= amount:
            # যদি মেইন ফান্ডে টাকা থাকে
            setattr(fund, primary_fund_name, primary_balance - amount)
            FundLog.objects.create(fund_type=primary_fund_name, amount=amount, transaction_type='outbound', reason="Bonus distribution")
        elif (primary_balance + company_balance) >= amount:
            # যদি মেইন ফান্ড + কোম্পানি ফান্ড মিলায়া হয়
            remaining = amount - primary_balance
            setattr(fund, primary_fund_name, 0)
            fund.company_fund -= remaining
            FundLog.objects.create(fund_type=primary_fund_name, amount=primary_balance, transaction_type='outbound', reason="Partial bonus")
            FundLog.objects.create(fund_type='company_fund', amount=remaining, transaction_type='outbound', reason="Bonus backup support")
        else:
            # টাকা নাই!
            return False 
        
        fund.save()
        return True
    





class ForgotPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)

    def validate(self, data):
        # Specific user check
        if not User.objects.filter(username=data['username'], phone=data['phone']).exists():
            raise serializers.ValidationError("Account not found with provided username and phone.")
        return data

    def generate_otp(self):
        username = self.validated_data['username']
        phone = self.validated_data['phone']
        
        # Using .filter().first() to avoid MultipleObjectsReturned crash
        user = User.objects.filter(username=username, phone=phone).first()
        
        if user:
            otp_code = str(random.randint(100000, 999999))
            user.otp = otp_code
            user.otp_expiry = timezone.now() + timedelta(minutes=5)
            user.save()
            
            # Real SMS Sending
            self.send_greenweb_sms(phone, otp_code, username)
            return otp_code
        return None

    def send_greenweb_sms(self, phone, otp, username):
        token = "816302462035b3e9a8b7d749d660d03d3610af4c65"
        to = phone if phone.startswith('88') else f"88{phone}"
        message = f"OTP for user {username} is {otp}. Valid for 5 mins."

        url = "http://api.greenweb.com.bd/api.php"
        payload = {"token": token, "to": to, "message": message}

        try:
            # Using 10s timeout to prevent server hanging
            response = requests.post(url, data=payload, timeout=10)
            print(f"SMS Response: {response.text}")
        except Exception as e:
            print(f"SMS Delivery Failed: {str(e)}")

# 3. Reset Password Logic
class ResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)

    def validate(self, data):
        user = User.objects.filter(
            username=data['username'], 
            phone=data['phone'], 
            otp=data['otp']
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid credentials or OTP.")
        
        if user.otp_expiry and user.otp_expiry < timezone.now():
            raise serializers.ValidationError("OTP has expired. Please try again.")
            
        return data

    def save(self):
        username = self.validated_data['username']
        phone = self.validated_data['phone']
        user = User.objects.get(username=username, phone=phone)
        
        user.set_password(self.validated_data['new_password'])
        user.otp = None 
        user.otp_expiry = None
        user.save()
        return user
    
class VerifyOTPSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)

    def validate(self, data):
        user = User.objects.filter(
            username=data['username'], 
            phone=data['phone'], 
            otp=data['otp']
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid credentials or OTP.")
        
        if user.otp_expiry and user.otp_expiry < timezone.now():
            raise serializers.ValidationError("OTP has expired.")
            
        return data

class ResetPasswordFinalSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)

    def save(self):
        user = User.objects.get(username=self.validated_data['username'])
        user.set_password(self.validated_data['new_password'])
        user.otp = None 
        user.otp_expiry = None
        user.save()
        return user