from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from account_admin.models import User

# Create your models here.
class Category(models.Model):
    nombre = models.CharField(max_length=110, unique=True)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Category"  
        verbose_name_plural = "Categories"  

class Product(models.Model):
    # Información básica
    nombre = models.CharField(max_length=250)
    descripcion = models.TextField()
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    
    # Precios
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    precio_proveedor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_manual = models.BooleanField(default=False)  # Si el admin modificó el precio manualmente
    
    # Ofertas
    en_oferta = models.BooleanField(default=False)
    precio_oferta_proveedor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Stock (sistema dual)
    stock = models.PositiveIntegerField(default=0)  # Deprecated - usar stock_proveedor
    stock_proveedor = models.PositiveIntegerField(default=0)  # Stock del proveedor
    stock_vendido = models.PositiveIntegerField(default=0)  # Stock que ya vendiste
    stock_ilimitado = models.BooleanField(default=False)  # Si el proveedor tiene stock infinito
    
    # Categoría e imágenes
    categoria = models.ForeignKey(Category, on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='products/', blank=True, null=True)  # Deprecated
    imagenes = models.JSONField(default=list, blank=True)  # Array de URLs de imágenes
    
    # Dropshipping
    external_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    external_url = models.URLField(max_length=500, null=True, blank=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    
    # Control
    desactivado = models.BooleanField(default=False)

    @property
    def stock_disponible(self):
        """Stock disponible para vender (stock_proveedor - stock_vendido)"""
        if self.stock_ilimitado:
            return 999999
        return max(0, self.stock_proveedor - self.stock_vendido)
    
    @property
    def disponible(self):
        """Producto disponible si tiene stock y no está desactivado"""
        return self.stock_disponible > 0 and not self.desactivado
    
    @property
    def imagen_principal(self):
        """Retorna la primera imagen del array de imágenes"""
        if self.imagenes and len(self.imagenes) > 0:
            return self.imagenes[0]
        return None
    
    @property
    def precio_final(self):
        """Precio que ve el cliente (considera ofertas)"""
        if self.en_oferta and self.precio_oferta_proveedor:
            return self.precio_oferta_proveedor * 2  # Markup del 100%
        return self.precio

    def save(self, *args, **kwargs):
        # Auto-generar slug si no existe
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.nombre)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Product"  
        verbose_name_plural = "Products"
        indexes = [
            models.Index(fields=['external_id']),
            models.Index(fields=['slug']),
        ]  

class Order(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),      # Pedido creado, esperando pago
    ('en_revision', 'En revisión'),  # Pago enviado, esperando revisión
        ('pagado', 'Pagado'),            # Pago confirmado
        ('preparando', 'Preparando'),    # Preparando el pedido para envío
        ('enviado', 'Enviado'),          # Pedido en camino
        ('entregado', 'Entregado'),      # Pedido completado
        ('cancelado', 'Cancelado'),      # Pedido cancelado
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)  # Relación con Client
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    direccion_envio = models.TextField(blank=True, default='')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def total_update(self):
        self.total = sum(detalle.subtotal for detalle in self.detalles.all())
        self.save()

    def save(self, *args, **kwargs):
        if self.pk:  # Solo si el pedido ya existe
            pedido_anterior = Order.objects.get(pk=self.pk)
            if pedido_anterior.estado != 'cancelado' and self.estado == 'cancelado':
                # Si el pedido se cancela, devolver stock vendido
                for detalle in self.detalles.all():
                    detalle.producto.stock_vendido -= detalle.cantidad
                    # Asegurar que no sea negativo
                    if detalle.producto.stock_vendido < 0:
                        detalle.producto.stock_vendido = 0
                    detalle.producto.save()

        super().save(*args, **kwargs)

    def __str__(self):
        username = self.usuario.username if self.usuario else "None"
        return f"Pedido {self.id} - {username}"
    
    class Meta:
        verbose_name = "Order"  
        verbose_name_plural = "Orders"  

class OrderDetail(models.Model):
    pedido = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Product, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.producto.precio * self.cantidad
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} (Pedido {self.pedido.id})"
    
    class Meta:
        verbose_name = "Order Detail"  
        verbose_name_plural = "Order Details"

class Pay(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
    ('en_revision', 'En revisión'),
        ('completado', 'Completado'),
        ('fallido', 'Fallido'),
    ]
    pedido = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="pagos")  # 1:N
    metodo = models.CharField(max_length=20, choices=[
        ('tarjeta', 'Tarjeta de Crédito/Débito'),
        ('paypal', 'PayPal'),
        ('transferencia', 'Transferencia Bancaria'),
    ])
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    creado = models.DateTimeField(default=timezone.now, editable=False)
    actualizado = models.DateTimeField(auto_now=True)
    # Datos adicionales por método (no guardar datos sensibles de tarjeta)
    metadata = models.JSONField(default=dict, blank=True)
    # Referencias externas (p. ej. id de PayPal, referencia de transferencia)
    external_id = models.CharField(max_length=120, blank=True, default='')
    # URL de redirección (PayPal) y comprobante para transferencia
    external_redirect_url = models.URLField(blank=True, default='')
    comprobante_url = models.URLField(blank=True, default='')
    # Comprobante subido (imagen o PDF)
    comprobante_archivo = models.FileField(upload_to='comprobantes/', blank=True, null=True)

    def save(self, *args, **kwargs):
        # En MySQL no tenemos constraint parcial, validamos en aplicación.
        if self.pedido_id and self.estado in ('pendiente', 'en_revision'):
            # Evitar múltiples pagos "abiertos" (pendiente o en revisión) para el mismo pedido
            qs = Pay.objects.filter(pedido_id=self.pedido_id, estado__in=['pendiente', 'en_revision'])
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('Ya existe un pago abierto (pendiente o en revisión) para este pedido.')
        if not self.monto_pagado and self.pedido_id:
            self.monto_pagado = self.pedido.total
        super().save(*args, **kwargs)

    def complete(self):
        if self.estado not in ['pendiente', 'en_revision']:
            return
        self.estado = 'completado'
        self.save()
        # Actualizar estado del pedido si aún estaba pendiente
        if self.pedido.estado in ['pendiente', 'en_revision']:
            self.pedido.estado = 'pagado'
            self.pedido.save()

    def fail(self):
        if self.estado not in ['pendiente', 'en_revision']:
            return
        self.estado = 'fallido'
        self.save()

    def __str__(self):
        return f"Pago de {self.monto_pagado} - {self.metodo} ({self.estado})"

    class Meta:
        verbose_name = "Pay"  
        verbose_name_plural = "Pays"
        # Nota: constraint parcial removido por incompatibilidad MySQL (W036). Validación en save() / serializer.

class Shipment(models.Model):
    pedido = models.OneToOneField(Order, on_delete=models.CASCADE)
    direccion_envio = models.TextField()
    empresa_envio = models.CharField(max_length=100)
    numero_guia = models.CharField(max_length=50, unique=True, null=True, blank=True)
    fecha_envio = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    fecha_entrega_estimada = models.CharField(max_length=100, null=True, blank=True)
    estado = models.CharField(max_length=50, choices=[
        ('pendiente', 'Pendiente'),
        ('preparando', 'Preparando'),
        ('en camino', 'En camino'),
        ('entregado', 'Entregado'),
    ], default='pendiente')

    def __str__(self):
        return f"Envío de Pedido {self.pedido.id} - {self.empresa_envio} (Guía: {self.numero_guia if self.numero_guia else 'N/A'})"

    class Meta:
        verbose_name = "Shipment"  
        verbose_name_plural = "Shipments"
    
class Cart(models.Model):
    """Modelo para representar el carrito de compras de un usuario"""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carrito de {self.usuario.username}"
    
    def total(self):
        """Calcula el total del carrito"""
        return sum(item.subtotal() for item in self.items.all())
    
    def cantidad_items(self):
        """Obtiene la cantidad total de items en el carrito"""
        return sum(item.cantidad for item in self.items.all())
    
    def limpiar(self):
        """Elimina todos los items del carrito"""
        self.items.all().delete()
    
    class Meta:
        verbose_name = "Carrito"
        verbose_name_plural = "Carritos"

class CartItem(models.Model):
    """Modelo para representar un item en el carrito"""
    carrito = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Product, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"
    
    def subtotal(self):
        """Calcula el subtotal del item"""
        return self.producto.precio * self.cantidad
    
    class Meta:
        verbose_name = "Item de Carrito"
        verbose_name_plural = "Items de Carrito"
        unique_together = ('carrito', 'producto')  # Un producto solo puede estar una vez en el carrito

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey('market.Product', on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='uniq_favorite_user_product')
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} ♥ {self.product_id}'
