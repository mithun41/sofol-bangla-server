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
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

# গুরুত্বপূর্ণ ইম্পোর্ট যা আপনার মিস ছিল (NameError ফিক্স করার জন্য)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

# আপনার মডেল ও সার্ভিস ইম্পোর্ট
from accounts.services import (
    calculate_commission,
    update_user_rank,
    find_auto_placement_with_division,
)
from orders.models import Order, OrderItem
from .models import BonusLog, FundLog, GlobalFund, User, WithdrawalRequest
from .serializers import (
    ForgotPasswordSerializer,
    RegisterSerializer,
    ResetPasswordFinalSerializer,
    ResetPasswordSerializer,
    UserListSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
    VerifyOTPSerializer,
    WithdrawalSerializer,
    BonusLogSerializer,
)
from django.db.models import Sum

# --- USER AUTH & PROFILE ---


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        user_division = data.get("division", "").strip()  # বিভাগটা নিলাম
        reff_id = data.get("reff_id")
        placement_id = data.get("placement_id")
        position = data.get("position")

        referrer = None
        final_parent = None
        final_pos = None

        # ১. রেফারেল লজিক (ম্যানুয়াল অথবা অটো বিভাগ ভিত্তিক)
        if reff_id:
            referrer = User.objects.filter(reff_id=reff_id).first()
            if not referrer:
                return Response(
                    {"reff_id": ["Invalid Referral ID. User not found."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # --- অটো রেফারেল লজিক শুরু ---
            if user_division:
                # বিভাগের নামে ইউজার খুঁজছি (যেমন: 'dhaka', 'rajshahi')
                referrer = User.objects.filter(username__iexact=user_division).first()

            # যদি বিভাগের নামে ইউজার না পায়, তবে সুপারইউজার/এডমিনকে ধরবে
            if not referrer:
                referrer = User.objects.filter(is_superuser=True).first()
            # --- অটো রেফারেল লজিক শেষ ---

        # ২. প্লেসমেন্ট আইডি ভ্যালিডেশন
        if placement_id:
            target_parent = User.objects.filter(placement_id=placement_id).first()
            if not target_parent:
                return Response(
                    {"placement_id": ["Placement ID not found in our records."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if position:
                if position not in ["left", "right"]:
                    return Response(
                        {"position": ["Position must be 'left' or 'right'."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                is_occupied = User.objects.filter(
                    placement_under=target_parent, position=position
                ).exists()
                if is_occupied:
                    return Response(
                        {
                            "position": [
                                f"The {position} side under this ID is already occupied."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                final_parent, final_pos = target_parent, position
            else:
                final_parent, final_pos = find_auto_placement_with_division(
                    target_parent, user_division
                )

        # ৩. যদি প্লেসমেন্ট আইডি না থাকে, তবে রেফারারের আন্ডারে অটো প্লেসমেন্ট
        elif referrer:
            final_parent, final_pos = find_auto_placement_with_division(
                referrer, user_division
            )

        # ৪. ইউজার তৈরি করা (Atomic Transaction)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data.get("username"),
                    email=data.get("email"),
                    password=data.get("password"),
                    phone=data.get("phone"),
                    name=data.get("name", ""),
                    division=user_division,
                    referred_by=referrer,  # এখানে আমাদের অটো বা ম্যানুয়াল রেফারার বসে যাবে
                    placement_under=final_parent,
                    position=final_pos,
                    status="inactive",
                )

                return Response(
                    {
                        "status": "success",
                        "message": "Registration successful!",
                        "user_info": {
                            "username": user.username,
                            "reff_id": user.reff_id,
                            "referred_by": (
                                user.referred_by.username if user.referred_by else None
                            ),
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )

        except Exception as e:
            return Response(
                {"non_field_errors": [str(e)]}, status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # এখানে context={'request': request} যোগ করা হয়েছে
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        # আপডেটের সময়ও কনটেক্সট দেওয়া ভালো, যাতে রিটার্ন করা ডেটাতে ফুল ইমেজ লিঙ্ক থাকে
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Profile updated successfully!", "data": serializer.data}
            )
        return Response(serializer.errors, status=400)


class ProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    # এই নিচের লাইনটা খুব গুরুত্বপূর্ণ, এটা ছাড়া 415 এরর দিবেই
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def patch(self, request):
        user = request.user
        # partial=True দেওয়া হয়েছে যাতে শুধু পাঠানো ডাটাগুলো আপডেট হয়
        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": "success",
                    "message": "Profile updated successfully",
                    "data": serializer.data,
                }
            )
        return Response(serializer.errors, status=400)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # ডিফল্ট refresh এবং access টোকেন জেনারেট করা
        data = super().validate(attrs)
        user = self.user
        request = self.context.get("request")  # রিকোয়েস্ট অবজেক্টটি নেওয়া

        # প্রোফাইল পিকচারের ফুল লিঙ্ক তৈরি করা
        if user.profile_picture:
            # যদি রিকোয়েস্ট থাকে তবে ফুল ইউআরএল বানাবে, নাহলে রিলেটিভটাই দিবে
            profile_pic_url = (
                request.build_absolute_uri(user.profile_picture.url)
                if request
                else user.profile_picture.url
            )
        else:
            profile_pic_url = None

        # userinfo অবজেক্ট এর ভেতরে সব ডাটা ঢুকিয়ে দেওয়া
        data["userinfo"] = {
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
            "star_level": user.star_level,
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
                # ইউজারকে লক করে আনা
                user = User.objects.select_for_update().get(id=user_id)

                if user.status == "active":
                    return Response({"message": "User is already active"}, status=400)

                # স্ট্যাটাস পরিবর্তন করুন
                user.status = "active"
                # চাইলে এখান থেকেই পয়েন্ট সেট করে দিতে পারেন
                if user.points < 1000:
                    user.points = 1000

                # save() কল করলেই মডেলের লজিক অনুযায়ী ফান্ডে ৪০০০ টাকা চলে যাবে
                user.points = 1000
                user.save() # এটি মডেলের save() কল করবে এবং সব লজিক রান করবে
                user.refresh_from_db()

                return Response(
                    {
                        "status": "success",
                        "message": "User activated and 4000 TK distributed to funds!",
                    }
                )

        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class UserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by("-createdAt")
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
                reff_id_input = data.get("reff_id_input")
                if reff_id_input:
                    referrer = User.objects.filter(reff_id=reff_id_input).first()
                    if referrer:
                        user.referred_by = referrer
                    else:
                        return Response({"error": "Invalid Referral ID!"}, status=400)

                # ২. প্লেসমেন্ট লজিক
                plc_id_input = data.get("placement_id_input")
                manual_position = data.get("position")

                if plc_id_input:
                    target_parent = User.objects.filter(
                        placement_id=plc_id_input
                    ).first()
                    if not target_parent:
                        return Response(
                            {"error": f"Placement ID {plc_id_input} not found!"},
                            status=400,
                        )

                    if manual_position in ["left", "right"]:
                        # পজিশন চেক (নিজের আইডি বাদে অন্য কেউ আছে কি না)
                        occupied = (
                            User.objects.filter(
                                placement_under=target_parent, position=manual_position
                            )
                            .exclude(id=user.id)
                            .exists()
                        )

                        if not occupied:
                            user.placement_under = target_parent
                            user.position = manual_position
                        else:
                            return Response(
                                {
                                    "error": f"{manual_position.capitalize()} side is already occupied!"
                                },
                                status=400,
                            )
                    else:
                        # অটো প্লেসমেন্ট
                        final_parent, final_pos = find_auto_placement_with_division(
                            target_parent, user.division
                        )
                        user.placement_under, user.position = final_parent, final_pos

                # ৩. অন্যান্য তথ্য আপডেট
                if "status" in data:
                    user.status = data["status"]
                if "name" in data:
                    user.name = data["name"]
                if "phone" in data:
                    user.phone = data["phone"]

                user.save()

                # ৪. এক্টিভেশন হলে কমিশন ক্যালকুলেশন
                if old_status == "inactive" and user.status == "active":
                    # এখানে চাইলে তুই distribute_money_to_funds(4000) কল করতে পারিস যদি ম্যানুয়ালি এক্টিভ করিস
                    calculate_commission(user)

                # ৫. পুরো ট্রি আপডেট করা
                self.recalculate_tree_counts()

                user.refresh_from_db()
                return Response(self.get_serializer(user).data)

        except Exception as e:
            return Response(
                {"error": f"Server Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST
            )

    def recalculate_tree_counts(self):
        """
        পুরো নেটওয়ার্কের কাউন্ট এবং র‍্যাঙ্ক নতুন করে হিসেব করার ফাংশন
        """
        from accounts.models import User
        from accounts.services import update_user_rank

        # ১. সবার ডাটা মেমোরিতে লোড করা (মাইগ্রেশনের এরর এড়াতে এটা ফাংশনের ভেতরে)
        all_users = list(User.objects.all())
        user_map = {u.id: u for u in all_users}

        # ২. সবার কাউন্ট রিসেট করা
        for u in all_users:
            u.left_count = 0
            u.right_count = 0
            u.total_left = 0
            u.total_right = 0

        # ৩. Bottom-up calculation
        for u in all_users:
            is_active = u.status == "active"
            curr = u

            while curr.placement_under_id:
                parent = user_map.get(curr.placement_under_id)
                if not parent:
                    break

                if curr.position == "left":
                    parent.total_left += 1
                    if is_active:
                        parent.left_count += 1
                elif curr.position == "right":
                    parent.total_right += 1
                    if is_active:
                        parent.right_count += 1

                curr = parent

        # ৪. বাল্ক আপডেট এবং র‍্যাঙ্ক চেক
        with transaction.atomic():
            for u in all_users:
                update_user_rank(u)
                u.save()

        print("Tree counts and Ranks recalculated successfully!")


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

            # ইমেজ ইউআরএল হ্যান্ডেল করা
            if current_user.profile_picture:
                profile_pic_url = request.build_absolute_uri(
                    current_user.profile_picture.url
                )
            else:
                profile_pic_url = f"https://ui-avatars.com/api/?name={current_user.username}&background=random&color=fff"

            return {
                "username": current_user.username,
                "status": current_user.status,
                "position": current_user.position,
                "division": current_user.division,
                "placement_id": current_user.placement_id,
                "profile_picture": profile_pic_url,
                "left": get_tree(
                    User.objects.filter(
                        placement_under=current_user, position="left"
                    ).first(),
                    depth + 1,
                ),
                "right": get_tree(
                    User.objects.filter(
                        placement_under=current_user, position="right"
                    ).first(),
                    depth + 1,
                ),
            }

        return Response(get_tree(user))


# --- FINANCIALS ---


class BonusLogListView(generics.ListAPIView):
    serializer_class = BonusLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return BonusLog.objects.all().order_by("-timestamp")
        return BonusLog.objects.filter(user=self.request.user).order_by("-timestamp")


from decimal import Decimal
from django.db import transaction
from rest_framework import serializers, generics
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser


class WithdrawalListCreateView(generics.ListCreateAPIView):
    serializer_class = WithdrawalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
     return WithdrawalRequest.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        # ডাটা থেকে অ্যামাউন্ট নেওয়া
        raw_amount = self.request.data.get("amount", 0)

        try:
            amount = Decimal(str(raw_amount))
        except:
            raise serializers.ValidationError("Invalid amount format.")

        if amount <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")

        # এটমিক ট্রানজেকশন যাতে টাকা কাটা এবং রিকোয়েস্ট সেভ একসাথে হয়
        with transaction.atomic():
            # ইউজারকে লেটেস্ট ডাটা দিয়ে রিফ্রেশ করা (টাকা ডাবল কাটা রোধ করতে)
            user.refresh_from_db()
            if user.balance >= amount:
                user.balance -= amount
                user.save()
                serializer.save(user=user, amount=amount)
            else:
                raise serializers.ValidationError("Insufficient balance.")


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_withdrawal_list(request):  # এই নাম আর urls.py এর নাম এক হতে হবে
    withdrawals = WithdrawalRequest.objects.all().order_by("-created_at")
    serializer = WithdrawalSerializer(withdrawals, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_approve_withdraw(request, pk):
    try:
        # ট্রানজেকশন শুরু যাতে টাকা ব্যাক হওয়া এবং রিকোয়েস্ট সেভ হওয়া নিরাপদ থাকে
        with transaction.atomic():
            # select_for_update ব্যবহার করা হয়েছে যাতে একই সময়ে অন্য কেউ রিকোয়েস্টটি এডিট না করতে পারে
            withdraw_req = WithdrawalRequest.objects.select_for_update().get(pk=pk)

            if withdraw_req.status != "pending":
                return Response(
                    {"error": "এই রিকোয়েস্টটি অলরেডি প্রসেস করা হয়ে গেছে।"}, status=400
                )

            action = request.data.get("action")  # 'approve' অথবা 'reject'

            if action == "approve":
                withdraw_req.status = "approved"
                withdraw_req.save()
                return Response(
                    {"message": "Withdrawal request approved successfully."}
                )

            elif action == "reject":
                withdraw_req.status = "rejected"

                # --- টাকা ব্যাক করার লজিক ---
                user = withdraw_req.user
                user.balance += withdraw_req.amount  # টাকা মেইন ব্যালেন্সে ফেরত পাঠানো
                user.save()

                withdraw_req.save()
                return Response(
                    {"message": "Request rejected and amount refunded to user balance."}
                )

            else:
                return Response(
                    {"error": "Invalid action. Use 'approve' or 'reject'"}, status=400
                )

    except WithdrawalRequest.DoesNotExist:
        return Response({"error": "Withdrawal request খুঁজে পাওয়া যায়নি।"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=400)


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        fund = GlobalFund.objects.first()
        current_month = datetime.now().month
        current_year = datetime.now().year

        # --- নতুন প্রফিট ক্যালকুলেশন লজিক শুরু ---

        # ১. সর্বমোট লাভ (শুধু Completed অর্ডারের আইটেম থেকে)
        total_profit = OrderItem.objects.filter(order__status="Completed").aggregate(
            total=Sum("profit")
        )["total"] or Decimal("0.00")

        # ২. চলতি মাসের লাভ (শুধু Completed অর্ডার থেকে)
        monthly_profit = OrderItem.objects.filter(
            order__status="Completed",
            order__created_at__month=current_month,
            order__created_at__year=current_year,
        ).aggregate(total=Sum("profit"))["total"] or Decimal("0.00")

        # --- নতুন প্রফিট ক্যালকুলেশন লজিক শেষ ---

        monthly_inflow = FundLog.objects.filter(
            transaction_type="inbound",
            created_at__month=current_month,
            created_at__year=current_year,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        monthly_outflow = FundLog.objects.filter(
            transaction_type="outbound",
            created_at__month=current_month,
            created_at__year=current_year,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        data = {
            "summary": {
                "total_users": User.objects.count(),
                "active_users": User.objects.filter(status="active").count(),
                "pending_withdrawals": WithdrawalRequest.objects.filter(
                    status="pending"
                ).count(),
                "completed_orders": Order.objects.filter(
                    status="Completed"
                ).count(),  # কমপ্লিটেড অর্ডার সংখ্যা
                "monthly_revenue": float(monthly_inflow),
                "monthly_payout": float(monthly_outflow),
                "monthly_profit": float(monthly_profit),  # চলতি মাসের প্রফিট
                "net_profit": float(total_profit),  # লাইফটাইম প্রফিট
                "net_fund_balance": float(monthly_inflow - monthly_outflow),
            },
            "funds": {
                "referral": float(fund.referral_fund) if fund else 0.0,
                "matching": float(fund.matching_fund) if fund else 0.0,
                "rank_reward": float(fund.rank_reward_fund) if fund else 0.0,
                "tour": float(fund.tour_fund) if fund else 0.0,
                "leadership": float(fund.leadership_fund) if fund else 0.0,
                "company": float(fund.company_fund) if fund else 0.0,
            },
        }

        return Response(data)


# --- ১. LOGOUT API (মোবাইল অ্যাপের জন্য মাস্ট) ---
class LogoutView(APIView):
    """
    অ্যাপ থেকে লগআউট করার সময় Refresh Token ব্ল্যাকলিস্ট করবে।
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"success": True, "message": "Successfully logged out!"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": "Invalid token or already logged out"},
                status=status.HTTP_400_BAD_REQUEST,
            )


# --- ২. PASSWORD CHANGE API (সিকিউরিটির জন্য) ---
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not user.check_password(old_password):
            return Response(
                {"error": "Old password is correct"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password changed successfully!"})


class ForgotPasswordView(APIView):
    """ধাপ ১: ওটিপি জেনারেট এবং সেন্ড করা"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.generate_otp()
            return Response(
                {
                    "status": "success",
                    "message": "OTP has been sent to your phone number.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "message": list(serializer.errors.values())[0][0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


class VerifyOTPView(APIView):
    """ধাপ ২: ওটিপি চেক করা"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {
                    "status": "success",
                    "message": "OTP verified successfully. Now you can set a new password.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "message": list(serializer.errors.values())[0][0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


def find_first_empty_slot(parent_user):
    """
    একটি নির্দিষ্ট প্যারেন্টের নিচে যেখানে প্রথম ফাঁকা জায়গা (Left or Right) আছে তা খুঁজে বের করে।
    Breadth-First Search (BFS) অ্যালগরিদম ব্যবহার করা হয়েছে।
    """
    queue = [parent_user]

    while queue:
        current = queue.pop(0)

        # বাম পাশে খালি আছে কি না চেক
        left_child = User.objects.filter(
            placement_under=current, position="left"
        ).first()
        if not left_child:
            return current, "left"

        # ডান পাশে খালি আছে কি না চেক
        right_child = User.objects.filter(
            placement_under=current, position="right"
        ).first()
        if not right_child:
            return current, "right"

        # যদি দুই পাশেই ইউজার থাকে, তবে তাদের কিউতে যোগ করো নিচের লেভেলে চেক করার জন্য
        queue.append(left_child)
        queue.append(right_child)


class ResetPasswordView(APIView):
    """ধাপ ৩: নতুন পাসওয়ার্ড সেভ করা"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordFinalSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": "success",
                    "message": "Password has been reset successfully. Please login.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "message": list(serializer.errors.values())[0][0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
                # ১. রেফারার আপডেট
                reff_id_input = data.get("reff_id_input")
                if reff_id_input:
                    referrer = User.objects.filter(reff_id=reff_id_input).first()
                    if referrer:
                        user.referred_by = referrer
                    else:
                        return Response(
                            {"error": "Invalid Referral ID!"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # ২. অটো-প্লেসমেন্ট এবং পজিশন আপডেট
                placement_id_input = data.get("placement_id_input")
                position_input = data.get("position")  # 'left' অথবা 'right'

                if placement_id_input:
                    target_placement_user = User.objects.filter(
                        reff_id=placement_id_input
                    ).first()

                    if target_placement_user:
                        # যদি অ্যাডমিন নির্দিষ্ট পজিশনে বসাতে চায় এবং সেটা ফাঁকা থাকে
                        if position_input:
                            exists = (
                                User.objects.filter(
                                    placement_under=target_placement_user,
                                    position=position_input,
                                )
                                .exclude(id=user.id)
                                .exists()
                            )

                            if not exists:
                                user.placement_under = target_placement_user
                                user.position = position_input
                            else:
                                # যদি ওই পজিশন বুকড থাকে, তবে অটোমেটিক নিচে ফাঁকা জায়গা খুঁজবে
                                final_parent, final_pos = find_first_empty_slot(
                                    target_placement_user
                                )
                                user.placement_under = final_parent
                                user.position = final_pos
                        else:
                            # যদি অ্যাডমিন পজিশন না দেয়, সরাসরি নিচে ফাঁকা জায়গা খুঁজবে
                            final_parent, final_pos = find_first_empty_slot(
                                target_placement_user
                            )
                            user.placement_under = final_parent
                            user.position = final_pos
                    else:
                        return Response(
                            {"error": "Invalid Placement ID!"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # যদি শুধু পজিশন আপডেট করতে চায় প্লেসমেন্ট আইডি ছাড়া
                elif position_input:
                    user.position = position_input

                # ৩. সাধারণ তথ্য আপডেট
                if "status" in data:
                    user.status = data["status"]
                if "name" in data:
                    user.name = data["name"]
                if "phone" in data:
                    user.phone = data["phone"]

                user.save()

                # ৪. ইনএক্টিভ থেকে এক্টিভ হলে কমিশন ক্যালকুলেশন
                if old_status == "inactive" and user.status == "active":
                    # নিশ্চিত করো তোমার calculate_commission ফাংশনটি ইম্পোর্ট করা আছে
                    try:
                        calculate_commission(user)
                    except NameError:
                        pass  # ফাংশন না থাকলে এরর ইগনোর করবে

                # ৫. পুরো ট্রির কাউন্ট এবং র‍্যাঙ্ক রি-ক্যালকুলেশন
                self.recalculate_tree_counts()

                user.refresh_from_db()
                return Response(self.get_serializer(user).data)

        except Exception as e:
            return Response({"error": str(e)}, status=400)

    def recalculate_tree_counts(self):
        """
        পুরো সিস্টেমের কাউন্ট এবং র‍্যাঙ্ক রি-ক্যালকুলেট করার পাওয়ারফুল মেথড।
        """
        all_users = list(User.objects.all())
        user_map = {u.id: u for u in all_users}

        for u in all_users:
            u.left_count = 0
            u.right_count = 0
            u.total_left = 0
            u.total_right = 0

        for u in all_users:
            is_active = u.status == "active"
            curr = u
            while curr.placement_under_id:
                parent = user_map.get(curr.placement_under_id)
                if not parent:
                    break

                if curr.position == "left":
                    parent.total_left += 1
                    if is_active:
                        parent.left_count += 1
                elif curr.position == "right":
                    parent.total_right += 1
                    if is_active:
                        parent.right_count += 1
                curr = parent

        with transaction.atomic():
            for u in all_users:
                update_user_rank(u)
                u.save()


class MyNetworkView(APIView):
    """
    ইউজারের ডিরেক্ট রেফারেল এবং ডাউনলাইন টিমের একটিভ/ইনএকটিভ মেম্বার আলাদাভাবে কাউন্ট করা।
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # ১. সরাসরি রেফারেল (Direct Referrals)
        referrals = User.objects.filter(referred_by=user).order_by("-createdAt")

        # ২. রিকার্সিভ ফাংশন: একটিভ এবং টোটাল মেম্বার কাউন্ট করার জন্য
        def count_team_stats(node):
            stats = {"total": 0, "active": 0, "members": []}

            children = User.objects.filter(placement_under=node)
            for child in children:
                stats["total"] += 1
                if str(child.status).lower().strip() == "active":
                    stats["active"] += 1

                stats["members"].append(child)

                # নিচের লেভেলের ডাটা নিয়ে আসা
                child_stats = count_team_stats(child)
                stats["total"] += child_stats["total"]
                stats["active"] += child_stats["active"]
                stats["members"].extend(child_stats["members"])

            return stats

        # ৩. বাম এবং ডান সাইড আলাদা করা
        left_child = User.objects.filter(placement_under=user, position="left").first()
        right_child = User.objects.filter(
            placement_under=user, position="right"
        ).first()

        # ডিফল্ট ভ্যালু
        left_stats = {"total": 0, "active": 0, "members": []}
        right_stats = {"total": 0, "active": 0, "members": []}

        # বাম পাশের হিসাব
        if left_child:
            left_stats["total"] = 1
            if str(left_child.status).lower().strip() == "active":
                left_stats["active"] = 1
            left_stats["members"].append(left_child)

            res = count_team_stats(left_child)
            left_stats["total"] += res["total"]
            left_stats["active"] += res["active"]
            left_stats["members"].extend(res["members"])

        # ডান পাশের হিসাব
        if right_child:
            right_stats["total"] = 1
            if str(right_child.status).lower().strip() == "active":
                right_stats["active"] = 1
            right_stats["members"].append(right_child)

            res = count_team_stats(right_child)
            right_stats["total"] += res["total"]
            right_stats["active"] += res["active"]
            right_stats["members"].extend(res["members"])

        # ৪. রেসপন্স পাঠানো
        return Response(
            {
                "status": "success",
                "referrals": UserListSerializer(referrals, many=True).data,
                "all_team": UserListSerializer(
                    left_stats["members"] + right_stats["members"], many=True
                ).data,
                "left_team": UserListSerializer(
                    left_stats["members"], many=True
                ).data,
                "right_team": UserListSerializer(
                    right_stats["members"], many=True
                ).data,
                "summary": {
                    "username": user.username,
                    "total_referrals": referrals.count(),
                    # এটি এখন রিয়েল-টাইম একটিভ মেম্বার গুনবে
                    "active_left": left_stats["active"],
                    "active_right": right_stats["active"],
                    # এটি ইন-একটিভ + একটিভ সব গুনবে
                    "total_left": left_stats["total"],
                    "total_right": right_stats["total"],
                },
            }
        )
