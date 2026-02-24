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
    """
    ফ্রন্টএন্ড থেকে প্রোডাক্ট আইডি লিস্ট নিয়ে লেটেস্ট ডাটা (প্রাইস, স্টক) ফেরত দেয়।
    """
    permission_classes = [permissions.AllowAny] # ব্র্যাকেট বাদ দেওয়া হয়েছে

    def post(self, request):
        # ডাটা নেওয়া
        product_ids = request.data.get('ids', [])
        
        if not isinstance(product_ids, list):
            return Response({"error": "ids must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        if not product_ids:
            return Response([], status=status.HTTP_200_OK)
        
        # ডাটাবেস থেকে প্রোডাক্ট ফিল্টার
        products = Product.objects.filter(id__in=product_ids)
        
        data = []
        for p in products:
            # ইমেজ ইউআরএল হ্যান্ডেলিং
            image_url = None
            if p.image:
                image_url = request.build_absolute_uri(p.image.url)

            data.append({
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "image": image_url,
                "point_value": p.point_value or 0,
                "stock_status": "in_stock" if (hasattr(p, 'stock') and p.stock > 0) else "available"
            })
            
        return Response(data, status=status.HTTP_200_OK)
    
    





class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # শুধুমাত্র নিজের কার্ট আইটেম দেখবে
        return Cart.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        product = serializer.validated_data.get('product')
        quantity = serializer.validated_data.get('quantity', 1)
        
        # ১. চেক করা যে এই ইউজারের কার্টে এই প্রোডাক্ট অলরেডি আছে কি না
        cart_item = Cart.objects.filter(user=self.request.user, product=product).first()

        if cart_item:
            # ২. যদি থাকে, তবে কোয়ান্টিটি বাড়িয়ে দাও
            cart_item.quantity += quantity
            cart_item.save()
        else:
            # ৩. না থাকলে নতুন করে সেভ করো
            serializer.save(user=self.request.user)

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """পুরো কার্ট খালি করার জন্য: /api/products/cart/clear/"""
        Cart.objects.filter(user=request.user).delete()
        return Response({"message": "Cart cleared successfully"}, status=status.HTTP_204_NO_CONTENT)