from decimal import Decimal
from django.db import transaction
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.decorators import api_view, permission_classes

from accounts.services import calculate_commission, update_user_rank
from .models import BonusLog, User, WithdrawalRequest
from .serializers import (
    RegisterSerializer, UserListSerializer, WithdrawalSerializer, 
    BonusLogSerializer
)

# --- USER AUTH & PROFILE ---

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny] # নিশ্চিত করুন এটি কাজ করছে
    authentication_classes = []     # এই ভিউয়ের জন্য সব অথেন্টিকেশন বন্ধ করে দিন

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": "User registered successfully!",
            "user": {
                "username": user.username,
                "reff_id": user.reff_id,
                "placement_id": user.placement_id
            }
        }, status=status.HTTP_201_CREATED)

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile_pic = request.build_absolute_uri(user.profile_picture.url) if user.profile_picture else None

        return Response({
            "name": user.name if user.name else user.username,
            "username": user.username,
            "email": user.email,
            "phone": user.phone, 
            "profile_picture": profile_pic,
            "balance": user.balance,
            "points": user.points,
            "left_count": user.left_count,
            "right_count": user.right_count,
            "total_left": user.total_left,   # র‍্যাঙ্ক ট্র্যাকিংয়ের জন্য
            "total_right": user.total_right, # র‍্যাঙ্ক ট্র্যাকিংয়ের জন্য
            "reff_id": user.reff_id,
            "placement_id": user.placement_id,
            "status": user.status,
            "star_level": user.star_level,
        })

    def patch(self, request):
        user = request.user
        if 'name' in request.data: user.name = request.data['name']
        if 'profile_picture' in request.FILES: user.profile_picture = request.FILES['profile_picture']
        user.save()
        return Response({"message": "Profile updated successfully!"})

# --- ADMIN USER MANAGEMENT & ACTIVATION ---

class ActivateUserView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            if user.status == 'active':
                return Response({"message": "User is already active"}, status=400)
            
            user.points += 1000
            user.save() # এটি models.py এর save() কল করবে এবং কমিশন ট্রিগার করবে
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
        data = request.data

        # ১. রেফারেল আপডেট
        reff_id_input = data.get('reff_id_input')
        if reff_id_input:
            referrer = User.objects.filter(reff_id=reff_id_input).first()
            if referrer:
                user.referred_by = referrer
            else:
                return Response({"error": "Invalid Referral ID"}, status=status.HTTP_400_BAD_REQUEST)

        # ২. প্লেসমেন্ট আপডেট
        plc_id_input = data.get('placement_id_input')
        manual_position = data.get('position')

        if plc_id_input:
            placer = User.objects.filter(placement_id=plc_id_input).first()
            if placer:
                user.placement_under = placer
                if manual_position in ['left', 'right']:
                    occupied = User.objects.filter(placement_under=placer, position=manual_position).exclude(id=user.id).exists()
                    if occupied:
                        return Response({"error": f"{manual_position} side is already occupied under this placement ID"}, status=status.HTTP_400_BAD_REQUEST)
                    user.position = manual_position
            else:
                return Response({"error": "Invalid Placement ID"}, status=status.HTTP_400_BAD_REQUEST)
        
        elif manual_position and user.placement_under:
            occupied = User.objects.filter(placement_under=user.placement_under, position=manual_position).exclude(id=user.id).exists()
            if occupied:
                return Response({"error": f"{manual_position} side is already occupied"}, status=status.HTTP_400_BAD_REQUEST)
            user.position = manual_position

        # ৩. স্ট্যাটাস আপডেট লজিক
        old_status = user.status
        new_status = data.get('status')
        if new_status:
            user.status = new_status

        user.save() 

        # কমিশন প্রসেসিং
        if old_status == 'inactive' and user.status == 'active':
            from accounts.services import calculate_commission
            calculate_commission(user)

        # ট্রি রি-ক্যালকুলেশন কল করা
        self.recalculate_tree_counts()

        # ডাটা রিফ্রেশ করে রিটার্ন করা
        user.refresh_from_db()
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    # এই মেথডটি অবশ্যই update মেথডের নিচে এবং একই লেভেলের ইনডেন্টেশনে থাকতে হবে
    def recalculate_tree_counts(self):
        from accounts.services import update_user_rank
        users = User.objects.all()
        
        # সব ইউজারের কাউন্ট রিসেট (নতুন করে গণনার জন্য)
        users.update(left_count=0, right_count=0, total_left=0, total_right=0)
        
        # বটম-আপ অ্যাপ্রোচে ট্রি আপডেট (সিম্পল লজিক)
        for u in User.objects.exclude(placement_under__isnull=True):
            curr = u
            while curr.placement_under:
                parent = curr.placement_under
                if curr.position == 'left':
                    parent.left_count += 1
                    parent.total_left += 1
                elif curr.position == 'right':
                    parent.right_count += 1
                    parent.total_right += 1
                parent.save()
                curr = parent
        
        # সব ইউজারের র‍্যাঙ্ক আপডেট
        for u in User.objects.all():
            update_user_rank(u)
# --- MLM & BINARY TREE ---

class BinaryTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.objects.filter(username=username).first()
        if not user: return Response({"error": "User not found"}, status=404)

        def get_tree(current_user, depth=0):
            if not current_user or depth > 3: return None
            left_child = User.objects.filter(placement_under=current_user, position='left').first()
            right_child = User.objects.filter(placement_under=current_user, position='right').first()

            return {
                "username": current_user.username,
                "status": current_user.status,
                "position": current_user.position,
                "left": get_tree(left_child, depth + 1),
                "right": get_tree(right_child, depth + 1)
            }
        return Response(get_tree(user))

# --- FINANCIALS ---

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