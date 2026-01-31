from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from accounts.services import calculate_commission
from .serializers import RegisterSerializer, UserListSerializer
from .models import User

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
        return Response({
            "username": user.username,
            "points": user.points,
            "balance": user.balance,
            "status": user.status,
            "left_count": user.left_count,
            "right_count": user.right_count,
            "reff_id": user.reff_id,
            "placement_id": user.placement_id,
            "position": user.position,
            "referred_by": user.referred_by.username if user.referred_by else None,
            "placement_under": user.placement_under.username if user.placement_under else None,
        })

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
        
        # ১. ম্যানুয়ালি রেফারার সেট করা
        reff_id_input = request.data.get('reff_id_input')
        if reff_id_input:
            referrer = User.objects.filter(reff_id=reff_id_input).first()
            if referrer:
                user.referred_by = referrer
            else:
                return Response({"error": "Invalid Referral ID"}, status=400)

        # ২. ম্যানুয়ালি প্লেসমেন্ট ও পজিশন সেট করা
        plc_id_input = request.data.get('placement_id_input')
        manual_position = request.data.get('position') # 'left' or 'right'

        if plc_id_input:
            placer = User.objects.filter(placement_id=plc_id_input).first()
            if placer:
                user.placement_under = placer
                
                # যদি অ্যাডমিন ম্যানুয়ালি পজিশন দেয়
                if manual_position in ['left', 'right']:
                    # চেক করা ওই পজিশন অলরেডি বুকড কি না
                    is_taken = User.objects.filter(placement_under=placer, position=manual_position).exclude(id=user.id).exists()
                    if is_taken:
                        return Response({"error": f"{manual_position.capitalize()} position is already occupied under this placer."}, status=400)
                    user.position = manual_position
                else:
                    # অটো সেট (Left priority) যদি অ্যাডমিন কিছু না দেয়
                    has_left = User.objects.filter(placement_under=placer, position='left').exclude(id=user.id).exists()
                    user.position = 'right' if has_left else 'left'
            else:
                return Response({"error": "Invalid Placement ID"}, status=400)
        
        user.save()
        
        response = super().update(request, *args, **kwargs)

        # ৩. স্ট্যাটাস একটিভ হলে কমিশন ডিস্ট্রিবিউট হবে
        if old_status == 'inactive' and request.data.get('status') == 'active':
            calculate_commission(user)
            
        return response

class BinaryTreeView(APIView):
    """ইউজারের বাইনারি ট্রি স্ট্রাকচার দেখার API"""
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        user = User.objects.filter(username=username).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        def get_tree(current_user, depth=0):
            if not current_user or depth > 3: # ৩ লেভেল পর্যন্ত ডাটা লোড হবে
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

        data = get_tree(user)
        return Response(data)

class ActivateUserView(APIView):
    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.points += 1000
            calculate_commission(user)
            return Response({"message": "User activated and commission distributed"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)