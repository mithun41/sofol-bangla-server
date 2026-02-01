from decimal import Decimal
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, permission_classes

from accounts.services import calculate_commission
from .models import BonusLog, User, WithdrawalRequest
from .serializers import (
    RegisterSerializer, UserListSerializer, WithdrawalSerializer, 
    BonusLogSerializer
)

# --- USER AUTH & PROFILE ---

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User registered successfully!",
                "user": {
                    "username": user.username,
                    "reff_id": user.reff_id,
                    "placement_id": user.placement_id
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # প্রোফাইল পিকচারের URL সেফলি হ্যান্ডেল করা
        profile_pic = None
        if user.profile_picture:
            try:
                profile_pic = request.build_absolute_uri(user.profile_picture.url)
            except:
                profile_pic = None

        return Response({
            "name": user.name if hasattr(user, 'name') else user.get_full_name(),
            "username": user.username,
            "email": user.email,
            "phone": getattr(user, 'phone', ""), # যদি ফোন ফিল্ড থাকে
            "profile_picture": profile_pic,
            "balance": user.balance,
            "reff_id": user.reff_id,
            "placement_id": user.placement_id,
            "status": user.status,
        })

    def patch(self, request):
        user = request.user
        data = request.data

        # ১. নাম আপডেট
        if 'name' in data:
            user.name = data['name']
        
        # ২. প্রোফাইল পিকচার আপডেট (যদি ফাইল পাঠানো হয়)
        if 'profile_picture' in request.FILES:
            # পুরানো ছবি থাকলে ডিলিট করার লজিক এখানে যোগ করা যায়
            user.profile_picture = request.FILES['profile_picture']

        user.save()
        return Response({"message": "Profile updated successfully!"})

# --- ADMIN USER MANAGEMENT & ACTIVATION ---

class ActivateUserView(APIView):
    """ইউজার এক্টিভেশন এবং কমিশন ডিস্ট্রিবিউশন করার API"""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.points += 1000
            calculate_commission(user)
            return Response({"message": "User activated and commission distributed"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

class UserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('-createdAt')
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]

class UserUpdateView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        old_status = user.status
        
        # ১. রেফারার ও প্লেসমেন্ট আপডেট লজিক
        reff_id_input = request.data.get('reff_id_input')
        if reff_id_input:
            referrer = User.objects.filter(reff_id=reff_id_input).first()
            if referrer:
                user.referred_by = referrer
        
        plc_id_input = request.data.get('placement_id_input')
        if plc_id_input:
            placer = User.objects.filter(placement_id=plc_id_input).first()
            if placer:
                user.placement_under = placer

        user.save()
        response = super().update(request, *args, **kwargs)

        # ২. স্ট্যাটাস পরিবর্তন হলে কমিশন ট্রিগার করা
        if old_status == 'inactive' and request.data.get('status') == 'active':
            calculate_commission(user)
            
        return response

# --- MLM & BINARY TREE ---

class BinaryTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.objects.filter(username=username).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        def get_tree(current_user, depth=0):
            if not current_user or depth > 3:
                return None
            
            left_child = User.objects.filter(placement_under=current_user, position='left').first()
            right_child = User.objects.filter(placement_under=current_user, position='right').first()

            return {
                "username": current_user.username,
                "placement_id": current_user.placement_id,
                "status": current_user.status,
                "position": current_user.position,
                "left": get_tree(left_child, depth + 1),
                "right": get_tree(right_child, depth + 1)
            }

        return Response(get_tree(user))

# --- FINANCIALS (WITHDRAW & LOGS) ---

class BonusLogListView(generics.ListAPIView):
    serializer_class = BonusLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return BonusLog.objects.all().order_by('-timestamp')
        return BonusLog.objects.filter(user=self.request.user).order_by('-timestamp')

class WithdrawalListCreateView(generics.ListCreateAPIView):
    serializer_class = WithdrawalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        amount = Decimal(self.request.data.get('amount', 0))

        if user.balance >= amount:
            user.balance -= amount
            user.save()
            serializer.save(user=user)
        else:
            raise serializers.ValidationError("Insufficient balance.")

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_withdrawal_list(request):
    withdrawals = WithdrawalRequest.objects.all().order_by('-created_at')
    serializer = WithdrawalSerializer(withdrawals, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_approve_withdraw(request, pk):
    try:
        withdraw_req = WithdrawalRequest.objects.get(pk=pk)
        action = request.data.get('action')

        if action == 'approve':
            withdraw_req.status = 'approved'
        elif action == 'reject':
            withdraw_req.status = 'rejected'
            user = withdraw_req.user
            user.balance += withdraw_req.amount
            user.save()

        withdraw_req.save()
        return Response({"message": f"Successfully {action}ed"})
    except WithdrawalRequest.DoesNotExist:
        return Response({"error": "Not found"}, status=404)