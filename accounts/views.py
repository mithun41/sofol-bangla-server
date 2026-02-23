from datetime import datetime
from decimal import Decimal
from django.db import transaction
from rest_framework import generics, status, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

# accounts.services থেকে আমাদের লেটেস্ট লজিক
from accounts.services import (
    calculate_commission, 
    update_user_rank, 
    find_auto_placement_with_division
)
from .models import BonusLog, FundLog, GlobalFund, User, WithdrawalRequest
from .serializers import (
    RegisterSerializer, UserListSerializer, WithdrawalSerializer, 
    BonusLogSerializer
)
from django.db.models import Sum
from .models import FundLog # এটা ইম্পোর্ট করা নিশ্চিত কর

# --- USER AUTH & PROFILE ---


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        # ১. সিরিয়ালাইজার দিয়ে ডাটা ভ্যালিডেট করা (Username/Email checks)
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # ডুপ্লিকেট ইউজারনেম বা ইমেইল থাকলে এখান থেকেই এরর যাবে
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        user_division = data.get('division', '') 
        reff_id = data.get('reff_id')
        referrer = None

        # ২. রেফারেল আইডি চেক
        if reff_id:
            try:
                referrer = User.objects.get(reff_id=reff_id)
            except User.DoesNotExist:
                return Response({"reff_id": ["Invalid Referral ID. Please check again."]}, status=status.HTTP_400_BAD_REQUEST)

        # ৩. প্লেসমেন্ট এবং পজিশন লজিক
        placement_id = data.get('placement_id')
        position = data.get('position')
        final_parent = None
        final_pos = None

        if placement_id and position:
            try:
                target_parent = User.objects.get(placement_id=placement_id)
                # পজিশন কি খালি আছে?
                if not User.objects.filter(placement_under=target_parent, position=position).exists():
                    final_parent, final_pos = target_parent, position
                else:
                    # অটো প্লেসমেন্ট লজিক (নিশ্চিত কর এই ফাংশনটি ইম্পোর্ট করা আছে)
                    final_parent, final_pos = find_auto_placement_with_division(target_parent, user_division)
            except User.DoesNotExist:
                return Response({"placement_id": ["Invalid Placement ID."]}, status=status.HTTP_400_BAD_REQUEST)
        
        elif placement_id:
            try:
                target_parent = User.objects.get(placement_id=placement_id)
                final_parent, final_pos = find_auto_placement_with_division(target_parent, user_division)
            except User.DoesNotExist:
                return Response({"placement_id": ["Invalid Placement ID."]}, status=status.HTTP_400_BAD_REQUEST)
        
        elif referrer:
            final_parent, final_pos = find_auto_placement_with_division(referrer, user_division)
        
        else:
            # রুট ইউজার (অ্যাডমিন) চেক
            root_user = User.objects.filter(is_superuser=True).first()
            if root_user:
                final_parent, final_pos = find_auto_placement_with_division(root_user, user_division)

        # ৪. ইউজার তৈরি করা (Atomic Transaction)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data.get('username'),
                    email=data.get('email'),
                    password=data.get('password'),
                    phone=data.get('phone'),
                    name=data.get('name', ''),
                    division=user_division, 
                    referred_by=referrer,
                    placement_under=final_parent,
                    position=final_pos,
                    status='inactive' 
                )
                
                return Response({
                    "message": "User registered successfully!",
                    "user_info": {
                        "username": user.username,
                        "placement_under": final_parent.username if final_parent else "None",
                        "position": final_pos,
                        "division": user.division,
                        "reff_id": user.reff_id
                    }
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # অন্যান্য যেকোনো টেকনিক্যাল এরর
            return Response({"general": [str(e)]}, status=status.HTTP_400_BAD_REQUEST)

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
            "role": user.role,
            "profile_picture": profile_pic,
            "balance": user.balance,
            "points": user.points,
            "left_count": user.left_count,
            "right_count": user.right_count,
            "total_left": user.total_left,
            "total_right": user.total_right,
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

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # ডিফল্ট refresh এবং access টোকেন জেনারেট করা
        data = super().validate(attrs)
        user = self.user
        request = self.context.get('request') # রিকোয়েস্ট অবজেক্টটি নেওয়া

        # প্রোফাইল পিকচারের ফুল লিঙ্ক তৈরি করা
        if user.profile_picture:
            # যদি রিকোয়েস্ট থাকে তবে ফুল ইউআরএল বানাবে, নাহলে রিলেটিভটাই দিবে
            profile_pic_url = request.build_absolute_uri(user.profile_picture.url) if request else user.profile_picture.url
        else:
            profile_pic_url = None

        # userinfo অবজেক্ট এর ভেতরে সব ডাটা ঢুকিয়ে দেওয়া
        data['userinfo'] = {
            "name": user.name if user.name else user.username,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "profile_picture": profile_pic_url,
            "balance": float(user.balance),
            "points": user.points,
            "left_count": user.left_count,
            "right_count": user.right_count,
            "total_left": user.total_left,
            "total_right": user.total_right,
            "reff_id": user.reff_id,
            "placement_id": user.placement_id,
            "status": user.status,
            "star_level": user.star_level
        }

        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

# --- ADMIN USER MANAGEMENT & ACTIVATION ---

class ActivateUserView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request, user_id):
        try:
            with transaction.atomic():
                user = User.objects.get(id=user_id)
                if user.status == 'active':
                    return Response({"message": "User is already active"}, status=400)
                user.status = 'active'
                user.points += 1000
                user.save()
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
        data = request.data
        old_status = user.status

        try:
            with transaction.atomic():
                # ১. আপডেট রেফারার
                reff_id_input = data.get('reff_id_input')
                if reff_id_input:
                    referrer = User.objects.filter(reff_id=reff_id_input).first()
                    if referrer: user.referred_by = referrer

                # ২. প্লেসমেন্ট লজিক
                plc_id_input = data.get('placement_id_input')
                manual_position = data.get('position')

                if plc_id_input:
                    target_parent = User.objects.filter(placement_id=plc_id_input).first()
                    if target_parent:
                        if manual_position in ['left', 'right']:
                            occupied = User.objects.filter(placement_under=target_parent, position=manual_position).exclude(id=user.id).exists()
                            if not occupied:
                                user.placement_under, user.position = target_parent, manual_position
                            else:
                                final_parent, final_pos = find_auto_placement_with_division(target_parent, user.division)
                                user.placement_under, user.position = final_parent, final_pos
                        else:
                            final_parent, final_pos = find_auto_placement_with_division(target_parent, user.division)
                            user.placement_under, user.position = final_parent, final_pos

                # ৩. অন্যান্য তথ্য এবং স্ট্যাটাস
                if 'status' in data: user.status = data['status']
                if 'name' in data: user.name = data['name']
                if 'phone' in data: user.phone = data['phone']
                if 'division' in data: user.division = data['division']

                user.save() 

                # ৪. অ্যাক্টিভেশন চেক
                if old_status == 'inactive' and user.status == 'active':
                    calculate_commission(user)

                self.recalculate_tree_counts()
                user.refresh_from_db()
                return Response(self.get_serializer(user).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def recalculate_tree_counts(self):
        users = User.objects.all()
        users.update(left_count=0, right_count=0, total_left=0, total_right=0)
        active_users_with_parent = User.objects.filter(status='active').exclude(placement_under__isnull=True)
        for u in active_users_with_parent:
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
            return {
                "username": current_user.username,
                "status": current_user.status,
                "position": current_user.position,
                "division": current_user.division,
                "placement_id": current_user.placement_id,
                "left": get_tree(User.objects.filter(placement_under=current_user, position='left').first(), depth + 1),
                "right": get_tree(User.objects.filter(placement_under=current_user, position='right').first(), depth + 1)
            }
        return Response(get_tree(user))

# --- FINANCIALS ---

class BonusLogListView(generics.ListAPIView):
    serializer_class = BonusLogSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        if self.request.user.is_superuser: return BonusLog.objects.all().order_by('-timestamp')
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
    






class AdminDashboardStatsView(APIView):
    """
    অ্যাডমিন ড্যাশবোর্ডের জন্য এক্সেকিউটিভ সামারি এবং গ্লোবাল ফান্ড স্ট্যাটাস প্রদান করে।
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # ১. গ্লোবাল ফান্ডের লেটেস্ট রেকর্ড নেওয়া
        fund = GlobalFund.objects.first()
        
        # ২. বর্তমান মাস ও বছর নির্ধারণ করা
        current_month = datetime.now().month
        current_year = datetime.now().year

        # ৩. মাসিক ইনকাম (Inflow) ক্যালকুলেশন
        # FundLog মডেলে transaction_type 'inbound' হওয়া চাই
        monthly_inflow = FundLog.objects.filter(
            transaction_type='inbound',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # ৪. মাসিক আউটকাম (Outflow) ক্যালকুলেশন
        # FundLog মডেলে transaction_type 'outbound' হওয়া চাই
        monthly_outflow = FundLog.objects.filter(
            transaction_type='outbound',
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # ৫. ফাইনাল রেসপন্স ডাটা স্ট্রাকচার (তোর ফ্রন্টএন্ডের সাথে মিল রেখে)
        data = {
            "summary": {
                "total_users": User.objects.count(),
                "active_users": User.objects.filter(status='active').count(),
                "pending_withdrawals": WithdrawalRequest.objects.filter(status='pending').count(),
                "monthly_revenue": float(monthly_inflow),
                "monthly_payout": float(monthly_outflow),
                "net_profit": float(monthly_inflow - monthly_outflow)
            },
            "funds": {
                "referral": float(fund.referral_fund) if fund else 0.0,
                "matching": float(fund.matching_fund) if fund else 0.0,
                "rank_reward": float(fund.rank_reward_fund) if fund else 0.0,
                "tour": float(fund.tour_fund) if fund else 0.0,
                "leadership": float(fund.leadership_fund) if fund else 0.0,
                "company": float(fund.company_fund) if fund else 0.0,
            }
        }

        return Response(data)