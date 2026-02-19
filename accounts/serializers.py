from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import BonusLog, User, WithdrawalRequest
from .services import find_auto_placement_with_division

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

class UserListSerializer(serializers.ModelSerializer):
    reff_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    referred_by_username = serializers.ReadOnlyField(source='referred_by.username')
    placement_under_username = serializers.ReadOnlyField(source='placement_under.username')

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'phone', 'reff_id', 'placement_id', 
            'points', 'balance', 'position', 'left_count', 'right_count',
            'referred_by_username', 'placement_under_username', 
            'reff_id_input', 'placement_id_input',
            'status', 'star_level', 'role', 'createdAt', 'division'
        )

class RegisterSerializer(serializers.ModelSerializer):
    reff_code_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    position_input = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            'username', 'password', 'email', 'phone', 'division', 
            'reff_code_input', 'placement_id_input', 'position_input'
        )
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        reff_code = validated_data.pop('reff_code_input', None)
        placement_code = validated_data.pop('placement_id_input', None)
        pos_input = validated_data.pop('position_input', None)
        user_division = validated_data.get('division')

        user = User.objects.create_user(**validated_data)

        if reff_code:
            referrer = User.objects.filter(reff_id=reff_code).first()
            user.referred_by = referrer

        if placement_code:
            placer = User.objects.filter(placement_id=placement_code).first()
            if placer:
                user.placement_under = placer
                if pos_input in ['left', 'right']:
                    user.position = pos_input
                else:
                    existing_left = User.objects.filter(placement_under=placer, position='left').exists()
                    user.position = 'left' if not existing_left else 'right'
        elif user.referred_by:
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