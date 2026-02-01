from rest_framework import serializers
from .models import BonusLog, User, WithdrawalRequest


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

        # ইউজার যদি কোড দেয় তবেই সেট হবে, না দিলে পরে অ্যাডমিন বসাবে
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
    
# serializers.py
# accounts/serializers.py

class UserListSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    # এই ফিল্ডগুলো ঘোষণা করা হয়েছে
    referred_by_username = serializers.ReadOnlyField(source='referred_by.username')
    placement_under_username = serializers.ReadOnlyField(source='placement_under.username')

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'phone', 
            'reff_id', 'placement_id', 'points', 'balance',
            'position', 'left_count', 'right_count', # পজিশন দেখার জন্য এগুলো জরুরি
            'referred_by_username',    # তালিকায় অবশ্যই থাকতে হবে
            'placement_under_username', # তালিকায় অবশ্যই থাকতে হবে
            'status', 'star_level', 'role', 'createdAt'
        )

    def get_role(self, obj):
        if obj.is_superuser:
            return "admin"
        return obj.role
    
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
        
