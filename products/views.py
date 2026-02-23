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
    ফ্রন্টএন্ড থেকে প্রোডাক্ট আইডি লিস্ট নিয়ে লেটেস্ট ডাটা (প্রাইস, স্টক) ফেরত দেয়।
    """
    permission_classes = [permissions.AllowAny()] # যে কেউ কার্ট চেক করতে পারবে

    def post(self, request):
        product_ids = request.data.get('ids', [])
        if not product_ids:
            return Response([], status=status.HTTP_200_OK)
        
        # ডাটাবেস থেকে শুধু কার্টে থাকা প্রোডাক্টগুলো ফিল্টার করা
        products = Product.objects.filter(id__in=product_ids)
        
        # ডাটা রেডি করা (সিরিয়ালাইজার ব্যবহার করলে আরও ভালো হয়)
        data = []
        for p in products:
            data.append({
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "image": request.build_absolute_uri(p.image.url) if p.image else None,
                "point_value": p.point_value or 0,
                "stock_status": "in_stock" if (hasattr(p, 'stock') and p.stock > 0) else "available"
            })
            
        return Response(data, status=status.HTTP_200_OK)