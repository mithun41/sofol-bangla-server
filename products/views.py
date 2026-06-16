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
                "expiry_date",
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

        # stock status filter
        stock_status = self.request.query_params.get("stock_status", None)
        if stock_status == "out":
            queryset = queryset.filter(stock__lte=0)
        elif stock_status == "low":
            queryset = queryset.filter(stock__gt=0, stock__lt=5)

        # expiry status filter
        expiry_status = self.request.query_params.get("expiry_status", None)
        if expiry_status:
            today = timezone.now().date()
            if expiry_status == "expired":
                queryset = queryset.filter(expiry_date__lt=today)
            elif expiry_status == "expiring_soon":
                soon_date = today + timezone.timedelta(days=5)
                queryset = queryset.filter(expiry_date__gte=today, expiry_date__lte=soon_date)

        # date range filter (for added products)
        start_date_str = self.request.query_params.get("start_date")
        end_date_str = self.request.query_params.get("end_date")

        if start_date_str or end_date_str:
            from django.utils.dateparse import parse_date
            from datetime import datetime, time
            
            start_dt = None
            end_dt = None

            if start_date_str:
                parsed_start = parse_date(start_date_str)
                if parsed_start:
                    start_dt = timezone.make_aware(datetime.combine(parsed_start, time.min))
            
            if end_date_str:
                parsed_end = parse_date(end_date_str)
                if parsed_end:
                    end_dt = timezone.make_aware(datetime.combine(parsed_end, time.max))

            if start_dt and end_dt:
                queryset = queryset.filter(created_at__range=(start_dt, end_dt))
            elif start_dt:
                queryset = queryset.filter(created_at__gte=start_dt)
            elif end_dt:
                queryset = queryset.filter(created_at__lte=end_dt)

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
                "expiry_date",
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
        GET /api/products/report/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        Returns products added within the date range. Defaults to today.
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=403)

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        added_qs = Product.objects.all()

        if start_date_str and end_date_str:
            from django.utils.dateparse import parse_date
            from datetime import datetime, time
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)
            if start_date and end_date:
                start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
                end_dt = timezone.make_aware(datetime.combine(end_date, time.max))
                added_qs = added_qs.filter(created_at__range=(start_dt, end_dt))
        else:
            # Default to today
            now = timezone.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            added_qs = added_qs.filter(created_at__gte=start_of_day)

        added_qs = added_qs.order_by("-created_at")
        added_count = added_qs.count()
        added_list = [
            {
                "id": p.id,
                "name": p.name,
                "stock": float(p.stock),
                "barcode": p.barcode_number
            } for p in added_qs
        ]

        return Response({
            "added_count": added_count,
            "added_products": added_list,
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
