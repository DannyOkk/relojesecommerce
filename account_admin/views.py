from .serializer import *
from .models import *
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, logout
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from Velorum.permissions import *
from rest_framework.decorators import api_view, permission_classes

# Create your views here.
class CreateUserView(APIView):

    def post(self, request):
        data = request.data.copy()  # Crear copia mutable para evitar errores
        
        # Si el usuario está autenticado, mantener lógica de roles
        if hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user
            if user.role not in ['admin', 'operator']:
                return Response(
                    {"error": "No tienes permiso para crear usuarios."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Admin puede asignar cualquier rol, operator solo client
            if user.role == 'admin':
                data['role'] = data.get('role', 'client')
            else:
                data['role'] = 'client'
        else:
            # Usuario no autenticado: solo puede crear clientes
            data['role'] = 'client'
        
        serializer = UserSerializer(data=data)
        if serializer.is_valid():
            new_user = serializer.save()
            new_user.set_password(request.data['password'])
            new_user.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangeRoleView(APIView):
    permission_classes = [IsAdmin]  # Solo administradores pueden cambiar roles

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            new_role = request.data.get('role')
            if new_role in dict(User.ROLES):
                user.role = new_role
                user.save()
                return Response({"message": "Rol actualizado correctamente"}, status=status.HTTP_200_OK)
            return Response({"error": "Rol inválido"}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()  # Marca el token como inválido
            return Response({"message": "Sesión cerrada correctamente"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Token inválido o ya expirado"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """Obtener y actualizar perfil del usuario autenticado"""
    try:
        user = request.user
        
        if request.method == 'GET':
            # Código existente para GET
            if user.is_superuser:
                user_role = 'admin'
            else:
                user_role = user.role
            
            profile_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'address': user.address,
                'phone': user.phone,
                'register_date': user.register_date.isoformat(),
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat(),
                'role': user_role,
                'original_role': user.role,
                'permissions': {
                    'can_access_admin': user.role in ['admin', 'operator'] or user.is_superuser,
                    'can_manage_products': user.role == 'admin' or user.is_superuser,
                    'can_view_orders': user.role in ['admin', 'operator'] or user.is_superuser,
                    'can_manage_users': user.role == 'admin' or user.is_superuser
                }
            }
            
            return Response(profile_data, status=status.HTTP_200_OK)
        
        elif request.method == 'PUT':
            # Actualizar perfil del usuario
            data = request.data
            
            # Campos que el usuario puede actualizar
            allowed_fields = ['username', 'email', 'first_name', 'last_name', 'address', 'phone']
            
            # Validar que el username no esté en uso por otro usuario
            if 'username' in data and data['username'] != user.username:
                if User.objects.filter(username=data['username']).exists():
                    return Response(
                        {'error': 'Este nombre de usuario ya está en uso'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validar que el email no esté en uso por otro usuario
            if 'email' in data and data['email'] != user.email:
                if User.objects.filter(email=data['email']).exists():
                    return Response(
                        {'error': 'Este email ya está en uso'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Actualizar solo los campos permitidos
            for field in allowed_fields:
                if field in data:
                    setattr(user, field, data[field])
            
            user.save()
            
            # Devolver los datos actualizados
            if user.is_superuser:
                user_role = 'admin'
            else:
                user_role = user.role
            
            updated_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'address': user.address,
                'phone': user.phone,
                'register_date': user.register_date.isoformat(),
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat(),
                'role': user_role,
                'original_role': user.role,
                'permissions': {
                    'can_access_admin': user.role in ['admin', 'operator'] or user.is_superuser,
                    'can_manage_products': user.role == 'admin' or user.is_superuser,
                    'can_view_orders': user.role in ['admin', 'operator'] or user.is_superuser,
                    'can_manage_users': user.role == 'admin' or user.is_superuser
                }
            }
            
            return Response(updated_data, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response(
            {'error': 'Error al procesar la solicitud', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Cambiar contraseña del usuario autenticado"""
    try:
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not old_password or not new_password:
            return Response(
                {'error': 'Se requiere la contraseña actual y la nueva'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar la contraseña actual
        if not user.check_password(old_password):
            return Response(
                {'error': 'La contraseña actual es incorrecta'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que la nueva contraseña tenga al menos 8 caracteres
        if len(new_password) < 8:
            return Response(
                {'error': 'La nueva contraseña debe tener al menos 8 caracteres'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cambiar la contraseña
        user.set_password(new_password)
        user.save()
        
        return Response(
            {'message': 'Contraseña cambiada correctamente'}, 
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        return Response(
            {'error': 'Error al cambiar la contraseña', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def manage_user(request, user_id):
    """Gestionar usuarios - Solo admins pueden modificar otros usuarios"""
    try:
        # Verificar que el usuario actual es admin
        if not (request.user.role == 'admin' or request.user.is_superuser):
            return Response(
                {'error': 'No tienes permisos para gestionar otros usuarios'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener el usuario a gestionar
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Usuario no encontrado'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method == 'GET':
            # Obtener información del usuario
            user_data = {
                'id': target_user.id,
                'username': target_user.username,
                'email': target_user.email,
                'first_name': target_user.first_name,
                'last_name': target_user.last_name,
                'address': target_user.address,
                'phone': target_user.phone,
                'role': target_user.role,
                'is_staff': target_user.is_staff,
                'is_superuser': target_user.is_superuser,
                'is_active': target_user.is_active,
                'date_joined': target_user.date_joined.isoformat(),
                'register_date': target_user.register_date.isoformat(),
                'last_login': target_user.last_login.isoformat() if target_user.last_login else None
            }
            
            return Response(user_data, status=status.HTTP_200_OK)
        
        elif request.method in ['PUT', 'PATCH']:
            # Actualizar usuario (PUT = completo, PATCH = parcial)
            data = request.data
            
            # Campos que el admin puede actualizar
            allowed_fields = ['username', 'email', 'first_name', 'last_name', 'address', 'phone', 'role', 'is_active']
            
            # Validar que el username no esté en uso por otro usuario
            if 'username' in data and data['username'] != target_user.username:
                if User.objects.filter(username=data['username']).exclude(id=user_id).exists():
                    return Response(
                        {'error': 'Este nombre de usuario ya está en uso'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validar que el email no esté en uso por otro usuario
            if 'email' in data and data['email'] != target_user.email:
                if User.objects.filter(email=data['email']).exclude(id=user_id).exists():
                    return Response(
                        {'error': 'Este email ya está en uso'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validar rol si se está cambiando
            if 'role' in data:
                valid_roles = ['admin', 'operator', 'client']
                if data['role'] not in valid_roles:
                    return Response(
                        {'error': f'Rol inválido. Roles válidos: {valid_roles}'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Prevenir que se quite el último admin
                if target_user.role == 'admin' and data['role'] != 'admin':
                    admin_count = User.objects.filter(role='admin').count()
                    superuser_count = User.objects.filter(is_superuser=True).count()
                    
                    if admin_count == 1 and superuser_count == 0:
                        return Response(
                            {'error': 'No se puede quitar el último administrador del sistema'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
            
            # Prevenir que el admin se desactive a sí mismo
            if 'is_active' in data and not data['is_active'] and target_user.id == request.user.id:
                return Response(
                    {'error': 'No puedes desactivar tu propia cuenta'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Actualizar solo los campos permitidos
            for field in allowed_fields:
                if field in data:
                    setattr(target_user, field, data[field])
            
            target_user.save()
            
            # Devolver los datos actualizados
            updated_data = {
                'id': target_user.id,
                'username': target_user.username,
                'email': target_user.email,
                'first_name': target_user.first_name,
                'last_name': target_user.last_name,
                'address': target_user.address,
                'phone': target_user.phone,
                'role': target_user.role,
                'is_staff': target_user.is_staff,
                'is_superuser': target_user.is_superuser,
                'is_active': target_user.is_active,
                'date_joined': target_user.date_joined.isoformat(),
                'register_date': target_user.register_date.isoformat(),
                'last_login': target_user.last_login.isoformat() if target_user.last_login else None
            }
            
            return Response(updated_data, status=status.HTTP_200_OK)
        
        elif request.method == 'DELETE':
            # Eliminar usuario
            
            # Prevenir que el admin se elimine a sí mismo
            if target_user.id == request.user.id:
                return Response(
                    {'error': 'No puedes eliminar tu propia cuenta'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Prevenir eliminar el último admin
            if target_user.role == 'admin':
                admin_count = User.objects.filter(role='admin').count()
                superuser_count = User.objects.filter(is_superuser=True).count()
                
                if admin_count == 1 and superuser_count == 0:
                    return Response(
                        {'error': 'No se puede eliminar el último administrador del sistema'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Prevenir eliminar superusuarios si no eres superusuario
            if target_user.is_superuser and not request.user.is_superuser:
                return Response(
                    {'error': 'Solo superusuarios pueden eliminar otros superusuarios'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            target_user.delete()
            
            return Response(
                {'message': f'Usuario {target_user.username} eliminado correctamente'}, 
                status=status.HTTP_200_OK
            )
            
    except Exception as e:
        return Response(
            {'error': 'Error al gestionar usuario', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_users(request):
    """Listar todos los usuarios - Solo para admins"""
    try:
        # Verificar que el usuario actual es admin
        if not (request.user.role == 'admin' or request.user.is_superuser):
            return Response(
                {'error': 'No tienes permisos para ver la lista de usuarios'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Parámetros de filtrado opcionales
        role_filter = request.GET.get('role', None)
        active_filter = request.GET.get('active', None)
        search = request.GET.get('search', None)
        
        # Consulta base
        users = User.objects.all()
        
        # Aplicar filtros
        if role_filter:
            users = users.filter(role=role_filter)
        
        if active_filter is not None:
            is_active = active_filter.lower() == 'true'
            users = users.filter(is_active=is_active)
        
        if search:
            users = users.filter(
                models.Q(username__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )
        
        # Ordenar por fecha de registro (más recientes primero)
        users = users.order_by('-register_date')
        
        # Preparar datos de respuesta
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'date_joined': user.date_joined.isoformat(),
                'register_date': user.register_date.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None
            })
        
        return Response({
            'users': users_data,
            'total': len(users_data),
            'filters_applied': {
                'role': role_filter,
                'active': active_filter,
                'search': search
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': 'Error al obtener lista de usuarios', 'detail': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
