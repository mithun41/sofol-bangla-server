from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Banner, Product, Category
from .serializers import BannerSerializer, CartSerializer, ProductSerializer, CategorySerializer
from .models import Product, Category, Cart
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from orders.models import OrderItem

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





# ── Pagination ────────────────────────────────────────────────────────────────
class ProductPagination(PageNumberPagination):
    page_size = 40  # একবারে ৪০টা
    page_size_query_param = "page_size"
    max_page_size = 200


# ── ProductViewSet ─────────────────────────────────────────────────────────────
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = ProductSerializer
    pagination_class = ProductPagination  # ← paginated response

    def get_queryset(self):
        # select_related + only — শুধু দরকারী fields, সব না
        queryset = (
            Product.objects.select_related("category")
            .only(
                "id",
                "name",
                "slug",
                "price",
                "purchase_price",
                "stock",
                "point_value",
                "unit_type",
                "image",
                "barcode_number",
                "barcode_image",
                "is_active",
                "is_featured",
                "created_at",
                "category__id",
                "category__name",
            )
            .filter(is_active=True)
            .order_by("-created_at")
        )

        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(barcode_number__icontains=search_query)
            )

        # category filter
        category_id = self.request.query_params.get("category", None)
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # featured filter
        featured = self.request.query_params.get("featured", None)
        if featured == "true":
            queryset = queryset.filter(is_featured=True)

        return queryset

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    # Admin panel এ সব product লাগে (inactive সহ), pagination ছাড়া
    @action(detail=False, methods=["get"], url_path="all")
    def all_products(self, request):
        """
        GET /api/products/products/all/
        Admin এর ManageProducts page এ ব্যবহার হবে।
        Pagination নেই — সব product একসাথে।
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        queryset = (
            Product.objects.select_related("category")
            .only(
                "id",
                "name",
                "price",
                "purchase_price",
                "stock",
                "point_value",
                "unit_type",
                "image",
                "barcode_number",
                "barcode_image",
                "is_active",
                "is_featured",
                "created_at",
                "category__id",
                "category__name",
            )
            .order_by("-created_at")
        )

        search = request.query_params.get("search", "")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(barcode_number__icontains=search)
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_by_barcode")
    def get_by_barcode(self, request):
        code = request.query_params.get("code")
        if not code:
            return Response({"error": "Barcode not provided"}, status=400)
        product = Product.objects.filter(barcode_number=code, is_active=True).first()
        if not product:
            return Response({"error": "Product not found"}, status=404)
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"], url_path="report")
    def report(self, request):
        """
        GET /api/products/report/
        Returns products added and sold this month, along with their detailed lists.
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        added_qs = Product.objects.filter(created_at__gte=start_of_month).order_by("-created_at")
        added_this_month = added_qs.count()
        added_list = [
            {
                "id": p.id,
                "name": p.name,
                "stock": float(p.stock),
                "barcode": p.barcode_number
            } for p in added_qs
        ]
        
        sold_qs = OrderItem.objects.filter(
            order__status="Completed",
            order__created_at__gte=start_of_month
        )
        
        sold_data = sold_qs.aggregate(total_sold=Sum('quantity'))
        sold_this_month = sold_data.get('total_sold') or 0

        sold_items = sold_qs.values('product_id', 'product_name').annotate(
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')
        
        sold_list = [
            {
                "id": item['product_id'],
                "name": item['product_name'],
                "quantity": float(item['total_quantity'])
            } for item in sold_items
        ]

        return Response({
            "added_this_month": added_this_month,
            "sold_this_month": int(sold_this_month) if sold_this_month else 0,
            "added_products": added_list,
            "sold_products": sold_list
        })


class CartSyncView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        product_ids = request.data.get('ids', [])
        products = Product.objects.filter(id__in=product_ids)
        
        is_active = False
        if request.user.is_authenticated:
            # সরাসরি ইউজার মডেল থেকে স্ট্যাটাস চেক করা ভালো
            u_status = getattr(request.user, 'status', '').lower()
            is_active = (u_status == 'active')

        data = []
        for p in products:
            base_price = float(p.price)
            pv = float(p.point_value or 0)
            
            # --- লজিক আপডেট ---
            if is_active:
                # একটিভ ইউজার হলে: ডিসকাউন্ট পাবে (PV * 2), কিন্তু কোনো PV পাবে না
                offer_discount = pv * 2
                f_price = base_price - offer_discount
                f_pv = 0
                is_offer_applied = True
            else:
                # ইন-একটিভ ইউজার হলে: ফুল প্রাইস দিবে এবং PV পাবে (আইডি একটিভ করার জন্য)
                f_price = base_price
                f_pv = pv
                is_offer_applied = False
                offer_discount = 0

            data.append({
                "id": p.id,
                "name": p.name,
                "product_price": round(f_price, 2),
                "product_pv": f_pv,
                "original_price": base_price,
                "offer_amount": round(offer_discount, 2), # এই টাকাটা সে সেভ করছে/অফার পাচ্ছে
                "is_offer_applied": is_offer_applied,
                "image": request.build_absolute_uri(p.image.url) if p.image else None,
                "stock_status": "in_stock" if p.stock > 0 else "out_of_stock"
            })
            
        return Response(data)


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Only show cart items for the currently logged-in user
        return Cart.objects.filter(user=self.request.user)

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
        return Response(serializer.data)

    # 1. Response for deleting a specific item
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        product_name = instance.product.name
        self.perform_destroy(instance)
        return Response({
            "status": "success",
            "message": f"Item '{product_name}' removed from cart successfully."
        }, status=status.HTTP_200_OK)

    # 2. Response for clearing the whole cart
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """URL: /api/products/cart/clear/"""
        cart_query = Cart.objects.filter(user=request.user)
        count = cart_query.count()
        
        if count > 0:
            cart_query.delete()
            return Response({
                "status": "success",
                "message": "Cart cleared successfully.",
                "deleted_count": count
            }, status=status.HTTP_200_OK)
        
        return Response({
            "message": "Your cart is empty"
        }, status=status.HTTP_200_OK)


class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.all().order_by('-created_at') # অ্যাডমিনে সব দেখাবে
    serializer_class = BannerSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = (MultiPartParser, FormParser)
