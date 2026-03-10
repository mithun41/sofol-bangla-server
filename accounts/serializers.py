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

        # তোর দেওয়া ফরম্যাট অনুযায়ী ডাটা অ্যাড করা
        data['username'] = user.username
        data['role'] = user.role
        data['name'] = user.name
        # প্রোফাইল পিকচার থাকলে ফুল URL দিবে, না থাকলে None
        data['profile_picture'] = user.profile_picture.url if user.profile_picture else None
        
        # এক্সট্রা ইনফরমেশন যা ড্যাশবোর্ডে লাগবে
        data['email'] = user.email
        data['phone'] = user.phone
        data['balance'] = float(user.balance)
        data['points'] = user.points
        data['left_count'] = user.left_count
        data['right_count'] = user.right_count
        data['total_left'] = user.total_left
        data['total_right'] = user.total_right
        data['reff_id'] = user.reff_id
        data['placement_id'] = user.placement_id
        data['status'] = user.status
        data['star_level'] = user.star_level
        
        return data

# ২. ইউজার প্রোফাইল দেখার বা আপডেট করার সিরিয়ালাইজার
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'name', 'username', 'email', 'phone', 'role', 
            'profile_picture', 'balance', 'points', 'left_count', 
            'right_count', 'total_left', 'total_right', 'reff_id', 
            'placement_id', 'status', 'star_level'
        ]
        read_only_fields = ['username', 'email', 'balance', 'points', 'reff_id', 'placement_id', 'role']

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
            instance.set_password(password) # পাসওয়ার্ড হ্যাশ করে সেভ করবে
        
        # বাকি ফিল্ডগুলো আপডেট করা
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance
    
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
            'status', 'star_level', 'role', 'createdAt', 'division'
        )



class RegisterSerializer(serializers.ModelSerializer):
    # ১. Full Name ফিল্ড যোগ করা হলো
    name = serializers.CharField(
        required=True, 
        max_length=150,
        error_messages={"required": "Please enter your full name."}
    )

    # ২. ইউজারনেম ইউনিক থাকবে (আগের মতোই)
    username = serializers.CharField(
        required=True,
        validators=[UniqueValidator(
            queryset=User.objects.all(), 
            message="This username is already taken."
        )]
    )
    
    # ৩. ফোন ফিল্ড থেকে UniqueValidator সরিয়ে দেওয়া হলো 
    # যাতে এক নাম্বার দিয়ে অনেক আইডি খোলা যায়
    phone = serializers.CharField(
        required=True,
        max_length=15
    )

    reff_code_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    position_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    division = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        # ৪. 'name' ফিল্ডটি fields লিস্টে অন্তর্ভুক্ত করা হলো
        fields = (
            'name', 'username', 'password', 'email', 'phone', 'division', 
            'reff_code_input', 'placement_id_input', 'position_input'
        )
        extra_kwargs = {
            'password': {'write_only': True},
        }

    # Custom field validation for Referral and Placement IDs
    def validate_reff_code_input(self, value):
        if value and not User.objects.filter(reff_id=value).exists():
            raise serializers.ValidationError("Invalid Referral ID. User not found.")
        return value

    def validate_placement_id_input(self, value):
        if value and not User.objects.filter(placement_id=value).exists():
            raise serializers.ValidationError("Placement ID not found in our records.")
        return value

    def create(self, validated_data):
        # ইনপুট থেকে নেটওয়ার্কিং ডাটাগুলো আলাদা করে নেওয়া
        reff_code = validated_data.pop('reff_code_input', None)
        placement_code = validated_data.pop('placement_id_input', None)
        pos_input = validated_data.pop('position_input', None)
        user_division = validated_data.get('division', '')

        # ইউজার তৈরি (এখানে name, phone সব ডাটাবেসে যাবে)
        user = User.objects.create_user(**validated_data)

        # ১. Referrer সেট করা
        if reff_code:
            referrer = User.objects.filter(reff_id=reff_code).first()
            if referrer:
                user.referred_by = referrer

        # ২. Placement সেট করা
        if placement_code:
            placer = User.objects.filter(placement_id=placement_code).first()
            if placer:
                user.placement_under = placer
                if pos_input in ['left', 'right']:
                    user.position = pos_input
                else:
                    existing_left = User.objects.filter(placement_under=placer, position='left').exists()
                    user.position = 'left' if not existing_left else 'right'
        
        # ৩. অটো-প্লেসমেন্ট লজিক
        elif user.referred_by:
            # এখানে আপনার কাস্টম ফাংশনটি কল হবে
            from .utils import find_auto_placement_with_division # আপনার ফাইল অনুযায়ী পাথ ঠিক করে নিন
            parent, pos = find_auto_placement_with_division(user.referred_by, user_division)
            if parent:
                user.placement_under = parent
                user.position = pos

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
        # Checking if a user exists with this specific username AND phone
        if not User.objects.filter(username=data['username'], phone=data['phone']).exists():
            raise serializers.ValidationError("No account found with this username and phone number.")
        return data

    def generate_otp(self):
        username = self.validated_data['username']
        phone = self.validated_data['phone']
        
        # Now we target the specific user uniquely
        user = User.objects.get(username=username, phone=phone)
        
        otp_code = str(random.randint(100000, 999999))
        user.otp = otp_code
        user.otp_expiry = timezone.now() + timedelta(minutes=5)
        user.save()

        self.send_greenweb_sms(phone, otp_code)
        return otp_code

    def send_greenweb_sms(self, phone, otp):
        token = "816302462035b3e9a8b7d749d660d03d3610af4c65"
        to = phone if phone.startswith('88') else f"88{phone}"
        message = f"Your OTP for username {self.validated_data['username']} is {otp}"

        url = "http://api.greenweb.com.bd/api.php"
        payload = {"token": token, "to": to, "message": message}

        try:
            response = requests.post(url, data=payload, timeout=10)
            print(f"GreenWeb Response: {response.text}")
        except Exception as e:
            print(f"GreenWeb Connection Error: {str(e)}")
    
class ResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(required=True) # Identifying the specific account
    phone = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)

    def validate(self, data):
        # Searching for the specific user with username, phone, AND otp
        user = User.objects.filter(
            username=data['username'], 
            phone=data['phone'], 
            otp=data['otp']
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid details. Check your username, phone, or OTP.")
        
        # Checking if OTP is expired
        if user.otp_expiry and user.otp_expiry < timezone.now():
            raise serializers.ValidationError("OTP has expired. Please request a new one.")
            
        return data

    def save(self):
        # Extracting validated data
        username = self.validated_data['username']
        phone = self.validated_data['phone']
        new_password = self.validated_data['new_password']

        # Targeting the exact user to update
        user = User.objects.get(username=username, phone=phone)
        user.set_password(new_password)
        
        # Clearing OTP fields after successful reset
        user.otp = None 
        user.otp_expiry = None
        user.save()
        return user