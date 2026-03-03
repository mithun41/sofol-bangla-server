from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Product, Category
from .serializers import CartSerializer, ProductSerializer, CategorySerializer
from .models import Product, Category, Cart 

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        queryset = Category.objects.all()
        is_main = self.request.query_params.get('main')
        if is_main == 'true':
            return queryset.filter(parent__isnull=True)
        return queryset
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

# --- নতুন কার্ট সিঙ্ক এপিআই ---


class CartSyncView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        product_ids = request.data.get('ids', [])
        products = Product.objects.filter(id__in=product_ids)
        
        # ইউজার অ্যাক্টিভ কি না তা স্ট্রিং চেক করে নিশ্চিত করা
        is_active = False
        if request.user.is_authenticated:
            u_status = ""
            if hasattr(request.user, 'profile'):
                u_status = getattr(request.user.profile, 'status', '').lower()
            elif hasattr(request.user, 'status'):
                u_status = getattr(request.user, 'status', '').lower()
            
            is_active = (u_status == 'active')

        data = []
        for p in products:
            image_url = request.build_absolute_uri(p.image.url) if p.image else None
            base_price = float(p.price)
            pv = float(p.point_value or 0)
            
            # ডিসকাউন্ট লজিক এপ্লাই
            final_price = (base_price - pv) if is_active else base_price

            data.append({
                "id": p.id,
                "name": p.name,
                "product_price": final_price,
                "image": image_url,
                "product_pv": pv,
                "stock_status": "in_stock" if (hasattr(p, 'stock') and p.stock > 0) else "available"
            })
            
        return Response(data, status=status.HTTP_200_OK)
    
    





class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)

    # এই অংশটুকু মিসিং ছিল - যা ডিসকাউন্ট লজিককে রিকোয়েস্ট পাঠাবে
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def perform_create(self, serializer):
        product = serializer.validated_data.get('product')
        quantity = serializer.validated_data.get('quantity', 1)
        cart_item = Cart.objects.filter(user=self.request.user, product=product).first()

        if cart_item:
            cart_item.quantity += quantity
            cart_item.save()
        else:
            serializer.save(user=self.request.user)
            
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # গ্র্যান্ড সাবটোটাল ক্যালকুলেট করা
        cart_data = serializer.data
        grand_subtotal = sum(item['item_subtotal'] for item in cart_data)
        
        # কাস্টম রেসপন্স ফরম্যাট
        return Response({
            "cart_items": cart_data,
            "grand_subtotal": grand_subtotal,
            "total_items": len(cart_data)
        })

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """পুরো কার্ট খালি করার জন্য: /api/products/cart/clear/"""
        Cart.objects.filter(user=request.user).delete()
        return Response({"message": "Cart cleared successfully"}, status=status.HTTP_204_NO_CONTENT)