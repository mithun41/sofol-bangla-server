from rest_framework import generics, permissions
from .models import Order
from .serializers import OrderSerializer

# সাধারণ ইউজারদের জন্য অর্ডার প্লেস করার ভিউ (আগে যেটা ছিল)
class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

# --- এডমিনদের জন্য কাস্টম এপিআই ---

# ১. সব অর্ডারের লিস্ট দেখা
class AdminOrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by("-created_at")
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]

# ২. অর্ডারের স্ট্যাটাস আপডেট করা
class AdminOrderUpdateView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]