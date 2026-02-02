from rest_framework import serializers
from .models import BonusLog, User, WithdrawalRequest

class UserListSerializer(serializers.ModelSerializer):
    # এই ফিল্ডগুলো ফ্রন্টএন্ড থেকে ইনপুট হিসেবে আসবে
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
            'reff_id_input', 'placement_id_input', # এগুলো যুক্ত করুন
            'status', 'star_level', 'role', 'createdAt'
        )

class RegisterSerializer(serializers.ModelSerializer):
    reff_code_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    placement_id_input = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'phone', 'reff_code_input', 'placement_id_input')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        reff_code = validated_data.pop('reff_code_input', None)
        placement_code = validated_data.pop('placement_id_input', None)
        user = User.objects.create_user(**validated_data)
        if reff_code:
            user.referred_by = User.objects.filter(reff_id=reff_code).first()
        if placement_code:
            placer = User.objects.filter(placement_id=placement_code).first()
            if placer:
                existing_children = User.objects.filter(placement_under=placer).count()
                user.position = 'left' if existing_children == 0 else 'right'
                user.placement_under = placer
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