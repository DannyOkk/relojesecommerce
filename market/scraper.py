"""
Módulo de scraping para sincronizar productos externos
"""

import requests
from bs4 import BeautifulSoup
import re
from django.utils import timezone
from django.utils.text import slugify
from market.models import Product, Category
import logging

logger = logging.getLogger(__name__)

# Headers para evitar bloqueos
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# Configuración del sitio a scrapear
BASE_URL = "https://etomiaccesorios.empretienda.com.ar"
ENDPOINT_AJAX = f"{BASE_URL}/v4/product/category"
CDN_BASE = "https://d22fxaf9t8d39k.cloudfront.net"

# Categorías a sincronizar con sus subcategorías
CATEGORIAS_CONFIG = {
    'relojes': {
        'url': f'{BASE_URL}/relojes',
        'ids': [3930925, 3937579, 3937580, 3991727, 2632928],
        'categoria_nombre': 'Relojes',
        'subcategorias': {
            3930925: 'G-SHOCK',
            3937579: 'TOMI',
            3937580: 'PATEK PHILIPPE',
            3991727: 'CASIO PREMIUM',
            2632928: 'Otros Relojes'
        }
    },
    'premium': {
        'url': f'{BASE_URL}/relojes-gama-premium',
        'ids': [4015782, 4015783, 3937574, 3937575, 3937576, 3937577, 3937578, 3399726],
        'categoria_nombre': 'Premium',
        'subcategorias': {
            4015782: 'BINBOND',
            4015783: 'CHENXI',
            3937574: 'ROLEX',
            3937575: 'PATEK PHILIPPE',
            3937576: 'CASIO',
            3937577: 'RICHARD MILLE',
            3937578: 'HUBLOT',
            3399726: 'Otros Premium'
        }
    },
    'smartwatch': {
        'url': f'{BASE_URL}/smartwatch',
        'ids': [2632977],
        'categoria_nombre': 'Smartwatch',
        'subcategorias': {
            2632977: 'Smartwatch'
        }
    }
}


def get_session_and_csrf():
    """
    Crea una sesión con cookies y extrae el token CSRF
    
    Returns:
        tuple: (session, csrf_token)
    """
    try:
        session = requests.Session()
        response = session.get(BASE_URL, headers=BROWSER_HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_meta = soup.find('meta', {'name': 'csrf-token'})
        
        if not csrf_meta:
            logger.error("No se encontró el token CSRF en el HTML")
            return None, None
        
        csrf_token = csrf_meta.get('content')
        logger.info(f"Sesión creada exitosamente, CSRF token obtenido")
        
        return session, csrf_token
        
    except Exception as e:
        logger.error(f"Error al crear sesión: {str(e)}")
        return None, None


def scrape_category(session, csrf_token, category_ids, category_name):
    """
    Scrapea todos los productos de una categoría usando paginación
    
    Args:
        session: Sesión de requests con cookies
        csrf_token: Token CSRF para las peticiones AJAX
        category_ids: Lista de IDs de categoría
        category_name: Nombre de la categoría
    
    Returns:
        list: Lista de productos (JSON)
    """
    productos = []
    page = 0
    
    ajax_headers = {
        **BROWSER_HEADERS,
        'X-CSRF-TOKEN': csrf_token,
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    while True:
        try:
            params = {
                'filter_page': page,
                'filter_order': 0,
                'filter_categories[]': category_ids
            }
            
            response = session.get(
                ENDPOINT_AJAX,
                params=params,
                headers=ajax_headers,
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"Error {response.status_code} en página {page} de {category_name}")
                break
            
            data = response.json()
            productos_pagina = data.get('data', [])
            
            if not productos_pagina:
                logger.info(f"Categoría {category_name}: {len(productos)} productos totales")
                break
            
            productos.extend(productos_pagina)
            logger.info(f"Categoría {category_name} - Página {page}: {len(productos_pagina)} productos")
            
            # Si trajo menos de 12, no hay más páginas
            if len(productos_pagina) < 12:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"Error scrapeando página {page} de {category_name}: {str(e)}")
            break
    
    return productos


def process_product_data(producto_json, categoria, subcategorias_map=None):
    """
    Procesa el JSON de un producto y lo crea/actualiza en la BD
    
    Args:
        producto_json: Datos del producto en JSON
        categoria: Instancia de Category
        subcategorias_map: Diccionario {external_id: nombre_subcategoria}
    
    Returns:
        tuple: (producto, created)
    """
    try:
        external_id = str(producto_json['idProductos'])
        nombre = producto_json['p_nombre']
        descripcion = producto_json.get('p_descripcion', '')
        
        # Stock
        stock_info = producto_json['stock'][0] if producto_json.get('stock') else {}
        stock_proveedor = stock_info.get('s_cantidad', 0)
        stock_ilimitado = stock_info.get('s_ilimitado', 0) == 1
        precio_proveedor = stock_info.get('s_precio', producto_json.get('p_precio', 0))
        
        # Ofertas
        en_oferta = producto_json.get('p_oferta', 0) == 1
        precio_oferta_proveedor = producto_json.get('p_precio_oferta', 0) if en_oferta else None
        
        # Imágenes
        imagenes_json = producto_json.get('imagenes', [])
        imagenes_urls = []
        for img in imagenes_json:
            i_link = img.get('i_link', '')
            # Si ya es una URL completa, usarla directamente
            if i_link.startswith('http'):
                imagenes_urls.append(i_link)
            else:
                # Si es solo el path, agregar el CDN base
                imagenes_urls.append(f"{CDN_BASE}/{i_link}")
        
        # URL del producto original
        p_link = producto_json.get('p_link', '')
        external_url = f"{CATEGORIAS_CONFIG[categoria.nombre.lower()]['url']}/{p_link}" if p_link else None
        
        # Calcular precio (markup del 100%)
        precio_calculado = float(precio_proveedor) * 2
        
        # Verificar si el producto ya existe
        try:
            producto_existente = Product.objects.get(external_id=external_id)
            # Si existe y tiene precio manual, mantenerlo
            if producto_existente.precio_manual:
                precio_final = producto_existente.precio
            else:
                precio_final = precio_calculado
        except Product.DoesNotExist:
            # Si no existe, usar el precio calculado
            precio_final = precio_calculado
        
        # Buscar o crear producto
        producto, created = Product.objects.update_or_create(
            external_id=external_id,
            defaults={
                'nombre': nombre,
                'descripcion': descripcion,
                'categoria': categoria,
                'precio': precio_final,
                'precio_proveedor': precio_proveedor,
                'stock_proveedor': stock_proveedor,
                'stock_ilimitado': stock_ilimitado,
                'en_oferta': en_oferta,
                'precio_oferta_proveedor': precio_oferta_proveedor,
                'imagenes': imagenes_urls,
                'external_url': external_url,
                'last_sync': timezone.now(),
            }
        )
        
        return producto, created
        
    except Exception as e:
        logger.error(f"Error procesando producto {producto_json.get('p_nombre', 'unknown')}: {str(e)}")
        return None, False


def sync_external_products():
    """
    Función principal de sincronización
    
    Returns:
        dict: Estadísticas de la sincronización
    """
    logger.info("=" * 60)
    logger.info("INICIANDO SINCRONIZACIÓN DE PRODUCTOS")
    logger.info("=" * 60)
    
    # Obtener sesión y token
    session, csrf_token = get_session_and_csrf()
    if not session or not csrf_token:
        return {
            'success': False,
            'error': 'No se pudo establecer sesión con el proveedor',
            'nuevos': 0,
            'actualizados': 0,
            'total': 0
        }
    
    productos_nuevos = 0
    productos_actualizados = 0
    errores = []
    productos_encontrados = []
    
    # Scrapear cada categoría
    for cat_key, cat_config in CATEGORIAS_CONFIG.items():
        try:
            logger.info(f"\n📦 Procesando categoría: {cat_config['categoria_nombre']}")
            
            # Obtener o crear categoría en BD
            categoria, _ = Category.objects.get_or_create(
                nombre=cat_config['categoria_nombre'],
                defaults={'descripcion': f'Categoría {cat_config["categoria_nombre"]}'}
            )
            
            # Scrapear productos de la categoría
            productos_json = scrape_category(
                session,
                csrf_token,
                cat_config['ids'],
                cat_config['categoria_nombre']
            )
            
            # Obtener mapa de subcategorías para esta categoría
            subcategorias_map = cat_config.get('subcategorias', {})
            
            # Procesar cada producto
            for prod_json in productos_json:
                producto, created = process_product_data(prod_json, categoria, subcategorias_map)
                
                if producto:
                    productos_encontrados.append(producto.external_id)
                    
                    if created:
                        productos_nuevos += 1
                        logger.info(f"✅ Producto NUEVO: {producto.nombre}")
                    else:
                        productos_actualizados += 1
                        logger.debug(f"🔄 Producto actualizado: {producto.nombre}")
                else:
                    errores.append(f"Error procesando producto en {cat_config['categoria_nombre']}")
            
        except Exception as e:
            error_msg = f"Error en categoría {cat_config['categoria_nombre']}: {str(e)}"
            logger.error(error_msg)
            errores.append(error_msg)
    
    # Marcar como no disponibles los productos que ya no existen
    productos_desaparecidos = Product.objects.filter(
        external_id__isnull=False
    ).exclude(
        external_id__in=productos_encontrados
    )
    
    count_desaparecidos = productos_desaparecidos.count()
    if count_desaparecidos > 0:
        productos_desaparecidos.update(desactivado=True)
        logger.info(f"⚠️ {count_desaparecidos} productos marcados como desactivados (ya no existen en proveedor)")
    
    # Estadísticas finales
    total = productos_nuevos + productos_actualizados
    
    logger.info("\n" + "=" * 60)
    logger.info("SINCRONIZACIÓN COMPLETADA")
    logger.info("=" * 60)
    logger.info(f"✅ Productos nuevos: {productos_nuevos}")
    logger.info(f"🔄 Productos actualizados: {productos_actualizados}")
    logger.info(f"📦 Total procesados: {total}")
    logger.info(f"⚠️ Productos desactivados: {count_desaparecidos}")
    logger.info(f"❌ Errores: {len(errores)}")
    
    return {
        'success': True,
        'nuevos': productos_nuevos,
        'actualizados': productos_actualizados,
        'total': total,
        'desactivados': count_desaparecidos,
        'errores': errores
    }
