from django.shortcuts import render
from .models import Order,Fish,Customer
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.db.models import Sum



# @login_required
# def index(request):
#     order=Order.objects.all().count()
#     total_kg_sum = Fish.objects.aggregate(total_kg_sum=Sum('total_kg'))['total_kg_sum']
#     customers=Customer.objects.all().count()
#     total_sales=Order.objects.filter(status='delivered').aggregate(total_sales=Sum('total_price'))['total_sales']
#     print(total_sales)
#     context={
#         'order':order,
#         'fish':total_kg_sum,
#         'customers':customers,
#         'total_sales':total_sales
#     }
#     return render(request,'index.html',context)

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
@login_required
def index(request):
    # Basic stats
    order_count = Order.objects.all().count()
    total_kg_sum = Fish.objects.aggregate(total_kg_sum=Sum('total_kg'))['total_kg_sum']
    customers_count = Customer.objects.all().count()
    total_sales = Order.objects.filter(status='delivered').aggregate(total_sales=Sum('total_price'))['total_sales'] or 0

    # Latest pending orders
    pending_orders = Order.objects.filter(status='pending').order_by('-created_at')[:5]

    # Orders by status
    status_counts = Order.objects.values('status').annotate(count=Count('id'))

    # Daily sales for last 7 days
    daily_sales = Order.objects.filter(status='delivered').annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        daily_total=Sum('total_price')
    ).order_by('-date')[:7]

    # Top selling fish
    top_selling_fish = Order.objects.filter(status='delivered').values(
        'fish__name'
    ).annotate(
        total_sales=Sum('total_price'),
        total_quantity=Sum('quantity')
    ).order_by('-total_sales')[:5]

    # Low stock alerts
    low_stock_items = Fish.objects.filter(total_kg__lt=10)  # Adjust threshold as needed

    context = {
        'order': order_count,
        'fish': total_kg_sum,
        'customers': customers_count,
        'total_sales': total_sales,
        'pending_orders': pending_orders,
        'status_counts': status_counts,
        'daily_sales': daily_sales,
        'top_selling_fish': top_selling_fish,
        'low_stock_items': low_stock_items,
    }
    return render(request, 'index.html', context)

from django.shortcuts import render, redirect, get_object_or_404
from .forms import FishForm
from django.urls import reverse
from rest_framework import generics
from .serializers import FishSerializer

# List all fishes
@login_required
def fish_list(request):
    fishes = Fish.objects.all()
    return render(request, 'products.html', {'fishes': fishes})


from rest_framework.permissions import AllowAny

class FishListAPIView(generics.ListAPIView):
    queryset = Fish.objects.all()
    serializer_class = FishSerializer
    permission_classes = [AllowAny]

# Add a new fish
@login_required
def fish_create(request):
    if request.method == 'POST':
        form = FishForm(request.POST, request.FILES)
        print(form)
        if form.is_valid():
            form.save()
            return redirect('fish_list')
    return redirect('fish_list')  # Redirect to the list page in case of errors

# Edit an existing fish
@login_required
def fish_edit(request, pk):
    fish = get_object_or_404(Fish, pk=pk)
    if request.method == 'POST':
        form = FishForm(request.POST, request.FILES, instance=fish)
        if form.is_valid():
            form.save()
            return redirect('fish_list')
    return redirect('fish_list')

# Delete a fish
@login_required
def fish_delete(request, pk):
    fish = get_object_or_404(Fish, pk=pk)
    if request.method == 'POST':
        fish.delete()
        return redirect('fish_list')
    return redirect('fish_list')

@login_required
def order_list(request):
    orders = Order.objects.all().order_by('-created_at')
    return render(request, 'order_list.html', {'orders': orders})


from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from .serializers import OrderSerializer
from decimal import Decimal
@api_view(['POST'])
@permission_classes([AllowAny])

def create_order(request):
    serializer = OrderSerializer(data=request.data)

    if serializer.is_valid():
        fish_id = serializer.validated_data['fish'].id
        quantity = serializer.validated_data['quantity']
        
        try:
            fish = Fish.objects.get(id=fish_id)

            # Validate requested quantity
            if quantity <= 0:
                return Response({"error": "Quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            
            if float(fish.total_kg) < float(quantity):
                return Response({"error": "Not enough stock available."}, status=status.HTTP_400_BAD_REQUEST)

            # Calculate total price
            total_price = float(fish.price_per_kg) * float(quantity)

            with transaction.atomic():
                # Deduct quantity from stock
                fish.total_kg = float(fish.total_kg) - float(quantity)
                fish.save()

                # Create order
                order = serializer.save(total_price=total_price)
            
            # Return response
            return Response({
                "id": order.id,
                "fish": order.fish.name,
                "quantity": order.quantity,
                "total_price": order.total_price,
                "status": order.status,
            }, status=status.HTTP_201_CREATED)

        except Fish.DoesNotExist:
            return Response({"error": "Fish not found."}, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from rest_framework.views import APIView


class OrderActionView(APIView):
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            action = request.data.get('action')
            
            if action == 'cancel':
                if order.status == 'pending':
                    order.status = 'cancelled'
                    order.save()
                    return Response({"message": "Order cancelled successfully"})
                return Response(
                    {"error": "Can only cancel pending orders"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            return Response(
                {"error": "Invalid action"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
            

class AdminOrderView(APIView):
    def get(self, request):
        orders = Order.objects.all()
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    def patch(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            new_status = request.data.get('status')
            
            if new_status in ['processing', 'delivered']:
                order.status = new_status
                order.save()
                return Response({"message": f"Order marked as {new_status}"})
                
            return Response(
                {"error": "Invalid status"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )           
            

from .serializers import CustomerRegistrationSerializer, CustomerLoginSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Customer
@api_view(['POST'])
def register_customer(request):
    serializer = CustomerRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        customer = serializer.save()
        
        # Generate tokens
        refresh = RefreshToken.for_user(customer)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

        return Response({
            'message': 'Registration successful',
            'customer': {
                'id': customer.id,
                'full_name': customer.full_name,
                'phone': customer.phone,
            },
            'tokens': tokens
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def login_customer(request):
    serializer = CustomerLoginSerializer(data=request.data)
    if serializer.is_valid():
        customer = Customer.objects.get(phone=serializer.validated_data['phone'])
        
        # Generate tokens
        refresh = RefreshToken.for_user(customer)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

        return Response({
            'message': 'Login successful',
            'customer': {
                'id': customer.id,
                'full_name': customer.full_name,
                'phone': customer.phone,
            },
            'tokens': tokens
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# Add an endpoint to get orders for a specific customer
@api_view(['GET'])
@permission_classes([AllowAny])
def get_customer_orders(request, customer_id):
    try:
        orders = Order.objects.filter(id=customer_id)
        
        order_data = []
        for order in orders:
            order_data.append({
                'id': order.id,
                'fish_name': order.fish.name,
                'quantity': order.quantity,
                'total_price': order.total_price,
                'status': order.status,
                'created_at': order.created_at
            })
            
        return Response(order_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

def customersList(request):
    customers=Customer.objects.all()
    return render(request,'customers_list.html',{'customers':customers})




from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from .forms import CustomUserCreationForm, LoginForm


def register_view(request):
    if request.method == "POST":
        print(request.POST)
        form = CustomUserCreationForm(request.POST)
        print(form)
        if form.is_valid():
            user = form.save(commit=False)
            print('user:',user)
            user.is_business = True
            user.save()
            login(request, user)
            messages.success(request, f"{user} Registration successful!")
            return redirect("index")
        else:
            messages.error(request, form.errors)
    else:
        form = CustomUserCreationForm()
    return render(request, "register.html", {"form": form})



from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.http import HttpResponseRedirect
from django.conf import settings
from django.utils import timezone

@csrf_protect
@never_cache
def login_view(request):
    # Redirect if user is already authenticated
    if request.user.is_authenticated:
        if request.user.is_business:
            return redirect("index")
        

    form = LoginForm(request.POST or None)
    print("Form errors:", form.errors) 
    print(form)
    
    if request.method == "POST":
        print("POST data:", request.POST)
        
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            
            user = authenticate(username=username, password=password)
            print(user)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Configure session settings
                    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                    request.session['last_activity'] = str(timezone.now())
                    
                    messages.success(request, "Logged in Successfully")
                    
                    # Redirect based on user type
                    if user.is_business:
                        return redirect("index")
                    
                else:
                    messages.error(request, "Account is disabled")
            else:
                messages.error(request, "Invalid username or password")
    
    return render(request, "login.html", {"form": form})

@never_cache
def logout_view(request):
    if request.user.is_authenticated:
        # Store the logout message before clearing the session
        messages.success(request, "Logged out successfully")
        
        # Logout the user
        logout(request)
        
        # Clear all session data
        request.session.flush()
        
        # Clear any potential session cookies
        response = HttpResponseRedirect('/accounts/login/')
        response.delete_cookie(settings.SESSION_COOKIE_NAME)
        
        # Set strict no-cache headers
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
    
    return redirect('login')

from rest_framework.views import APIView
from .models import Address
from .serializers import AddressSerializer

class AddressAPI(APIView):
    # Get all addresses for a customer
    def get(self, request, user_id):
        try:
            addresses = Address.objects.filter(customer_id=user_id)
            serializer = AddressSerializer(addresses, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    # Create new address
    def post(self, request, user_id):
        try:
            customer = Customer.objects.get(id=user_id)
            serializer = AddressSerializer(data=request.data)
            
            if serializer.is_valid():
                serializer.save(customer=customer)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Customer.DoesNotExist:
            return Response(
                {"error": "Customer not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

class AddressDetailAPI(APIView):
    # Get single address
    def get(self, request, user_id, address_id):
        try:
            address = Address.objects.get(customer_id=user_id, id=address_id)
            serializer = AddressSerializer(address)
            return Response(serializer.data)
        except Address.DoesNotExist:
            return Response(
                {"error": "Address not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

    # Update address
    def put(self, request, user_id, address_id):
        try:
            address = Address.objects.get(customer_id=user_id, id=address_id)
            serializer = AddressSerializer(address, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Address.DoesNotExist:
            return Response(
                {"error": "Address not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

    # Delete address
    def delete(self, request, user_id, address_id):
        try:
            address = Address.objects.get(customer_id=user_id, id=address_id)
            address.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Address.DoesNotExist:
            return Response(
                {"error": "Address not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

class SetDefaultAddressAPI(APIView):
    def post(self, request, user_id, address_id):
        try:
            address = Address.objects.get(customer_id=user_id, id=address_id)
            address.is_default = True
            address.save()
            serializer = AddressSerializer(address)
            return Response(serializer.data)
        except Address.DoesNotExist:
            return Response(
                {"error": "Address not found"}, 
                status=status.HTTP_404_NOT_FOUND)
            
            
            
class OrderDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            # Get the order by ID
            order = Order.objects.get(id=pk)
         
            serializer = OrderSerializer(order)
            return Response(serializer.data)

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
            
# views.py
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password
from .models import Customer

class ChangePhoneNumberView(APIView):
    def post(self, request, user_id):
        try:
            current_phone = request.data.get('current_phone')
            new_phone = request.data.get('new_phone')
            password = request.data.get('password')

            if not all([current_phone, new_phone, password]):
                return Response({
                    'error': 'Please provide current phone, new phone and password'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if new phone already exists
            if Customer.objects.filter(phone=new_phone).exists():
                return Response({
                    'error': 'Phone number already registered'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get customer by ID and verify current phone
            customer = Customer.objects.get(id=user_id)
            
            if customer.phone != current_phone:
                return Response({
                    'error': 'Current phone number does not match'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify password
            if not check_password(password, customer.password):
                return Response({
                    'error': 'Invalid password'
                }, status=status.HTTP_400_BAD_REQUEST)

            customer.phone = new_phone
            customer.save()

            return Response({
                'message': 'Phone number updated successfully',
                'new_phone': new_phone
            })

        except Customer.DoesNotExist:
            return Response({
                'error': 'Customer not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
            
            
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.mail import send_mail
import random

class RequestPasswordResetView(APIView):
    def post(self, request):
        email = request.data.get('email')
        
        # Check if user exists
        try:
            user = Customer.objects.get(email=email)
            
            # Create a simple 6-digit code
            reset_code = str(random.randint(100000, 999999))
            
            # Save this code in user's record
            user.reset_code = reset_code
            user.save()
            
            # Send email
            send_mail(
                'Password Reset',
                f'Your reset code is: {reset_code}',
                settings.EMAIL_HOST_USER,
                [email],
            )
            
            return Response({"message": "Reset code sent to your email"})
            
        except Customer.DoesNotExist:
            return Response({"error": "Email not found"})

class ResetPasswordView(APIView):
    def post(self, request):
        code = request.data.get('code')
        new_password = request.data.get('password')
        
        if not code or not new_password:
            return Response({
                "error": "Both code and password are required"
            }, status=400)

        try:
            # Find user with this code
            user = Customer.objects.get(reset_code=code)
            
            # Set new password
            user.password = new_password  # Note: This should be hashed
            # Clear reset code
            user.reset_code = None
            user.save()
            
            return Response({
                "message": "Password updated successfully"
            })
            
        except Customer.DoesNotExist:
            return Response({
                "error": "Invalid or expired reset code"
            }, status=400)