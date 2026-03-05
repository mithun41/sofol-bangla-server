from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Product, Category
from .serializers import CartSerializer, ProductSerializer, CategorySerializer
from .models import Product, Category, Cart
from django.db.models import Q 

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
    # ১. Router-এর basename এরর ফিক্স করার জন্য ডিফল্ট কুয়েরিসেট
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer

    def get_queryset(self):
        """
        এখানে ডাইনামিক ফিল্টারিং এবং সার্চ হ্যান্ডেল করা হচ্ছে।
        """
        queryset = Product.objects.all().order_by('-created_at')
        
        # ইউআরএল থেকে সার্চ টার্ম নেওয়া হচ্ছে (যেমন: ?search=মধু)
        search_query = self.request.query_params.get('search', None)
        
        if search_query:
            # নাম, ডেসক্রিপশন অথবা বারকোড নম্বর দিয়ে সার্চ করবে
            queryset = queryset.filter(
                Q(name__icontains=search_query) | 
                Q(description__icontains=search_query) |
                Q(barcode_number__icontains=search_query)
            )
            
        return queryset

    def get_permissions(self):
        """
        অ্যাডমিন ছাড়া অন্য কেউ প্রোডাক্ট তৈরি বা এডিট করতে পারবে না।
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        # list, retrieve এবং get_by_barcode সবাই অ্যাক্সেস করতে পারবে
        return [permissions.AllowAny()]

    # ২. বারকোড দিয়ে প্রোডাক্ট খোঁজার কাস্টম এপিআই (যেমন: /api/products/get_by_barcode/?code=123)
    @action(detail=False, methods=['get'])
    def get_by_barcode(self, request):
        barcode = request.query_params.get('code')
        
        if not barcode:
            return Response({"error": "বারকোড পাওয়া যায়নি!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # শুধুমাত্র অ্যাক্টিভ প্রোডাক্ট বারকোড দিয়ে খোঁজা হচ্ছে
            product = Product.objects.get(barcode_number=barcode, is_active=True)
            # সিরিয়ালাইজার কনটেক্সটে রিকোয়েস্ট পাঠানো হচ্ছে যাতে ইমেজ ইউআরএল ঠিক থাকে
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        except Product.DoesNotExist:
            return Response({"error": "এই বারকোডের কোনো প্রোডাক্ট সিস্টেমে নেই!"}, status=status.HTTP_404_NOT_FOUND)

class CartSyncView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        product_ids = request.data.get('ids', [])
        products = Product.objects.filter(id__in=product_ids)
        
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
            
            # ✅ ডিসকাউন্ট লজিক আপডেট: ১ পয়েন্ট = ২ টাকা অফার
            if is_active:
                discount = pv * 2
                final_price = base_price - discount
            else:
                final_price = base_price

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
        # শুধুমাত্র বর্তমান ইউজারের কার্ট আইটেমগুলো দেখাবে
        return Cart.objects.filter(user=self.request.user)

    def get_serializer_context(self):
        # সিরিয়ালাইজারের ভেতর রিকোয়েস্ট অবজেক্ট পাঠানোর জন্য (ইমেজ ইউআরএল এবং ডিসকাউন্ট ক্যালকুলেশনের জন্য জরুরি)
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def perform_create(self, serializer):
        # কার্টে নতুন প্রোডাক্ট অ্যাড করার সময় যদি অলরেডি থাকে তবে কোয়ান্টিটি বাড়িয়ে দেবে
        product = serializer.validated_data.get('product')
        quantity = serializer.validated_data.get('quantity', 1)
        cart_item = Cart.objects.filter(user=self.request.user, product=product).first()

        if cart_item:
            cart_item.quantity += quantity
            cart_item.save()
        else:
            serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        # তোর রিকোয়ারমেন্ট অনুযায়ী সরাসরি Array (লিস্ট) রিটার্ন করবে
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        # কার্ট থেকে আইটেম রিমুভ করার জন্য
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
            
    

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """পুরো কার্ট খালি করার জন্য: /api/products/cart/clear/"""
        Cart.objects.filter(user=request.user).delete()
        return Response({"message": "Cart cleared successfully"}, status=status.HTTP_204_NO_CONTENT)