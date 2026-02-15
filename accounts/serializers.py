from rest_framework import serializers
from .models import BonusLog, User, WithdrawalRequest
from .services import find_auto_placement_with_division # services থেকে ফাংশনটি ইমপোর্ট করবি

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
            'status', 'star_level', 'role', 'createdAt', 'division' # division যোগ করলাম
        )

class RegisterSerializer(serializers.ModelSerializer):
    # ফ্রন্টএন্ড থেকে আসা ইনপুট ফিল্ড
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

        # ১. ইউজার ক্রিয়েট করা
        user = User.objects.create_user(**validated_data)

        # ২. রেফারার সেট করা
        referrer = None
        if reff_code:
            referrer = User.objects.filter(reff_id=reff_code).first()
            user.referred_by = referrer

        # ৩. প্লেসমেন্ট লজিক
        if placement_code:
            # ক) ম্যানুয়াল প্লেসমেন্ট (যদি ইউজার নিজে আইডি দেয়)
            placer = User.objects.filter(placement_id=placement_code).first()
            if placer:
                user.placement_under = placer
                # যদি পজিশন দেওয়া থাকে তবে সেটা নিবে, নাহলে অটোমেটিক খালি জায়গা নিবে
                if pos_input in ['left', 'right']:
                    user.position = pos_input
                else:
                    existing_left = User.objects.filter(placement_under=placer, position='left').exists()
                    user.position = 'left' if not existing_left else 'right'
        
        elif referrer:
            # খ) অটো প্লেসমেন্ট (ডিভিশন অনুযায়ী)
            # এই ফাংশনটা তোর services.py এ থাকবে যা আমরা আগে আলোচনা করেছি
            parent, pos = find_auto_placement_with_division(referrer, user_division)
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
    class Meta:
        model = WithdrawalRequest
        fields = ['id', 'amount', 'method', 'account_number', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']