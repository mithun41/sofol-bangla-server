from rest_framework import generics, permissions
from .models import Order
from .serializers import OrderSerializer

# ১. সাধারণ ইউজারদের জন্য অর্ডার তৈরি করা
class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

# ২. এডমিনদের জন্য সব অর্ডারের লিস্ট দেখা (এটিই মিসিং ছিল)
class AdminOrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by("-created_at")
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]

# ৩. এডমিনদের জন্য অর্ডারের স্ট্যাটাস আপডেট করা
class AdminOrderUpdateView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]

# ৪. সাধারণ ইউজারদের জন্য তাদের নিজস্ব অর্ডার লিস্ট দেখা
class UserOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # লগইন করা ইউজারের অর্ডার ফিল্টার করা
        return Order.objects.filter(user=self.request.user).order_by("-created_at")