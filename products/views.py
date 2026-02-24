from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer

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