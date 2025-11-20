"""
Script de prueba para verificar la sincronización de productos
"""

import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Velorum.settings')
django.setup()

from market.scraper import sync_external_products

if __name__ == '__main__':
    print("🚀 Iniciando prueba de sincronización...")
    print("-" * 60)
    
    resultado = sync_external_products()
    
    print("\n" + "=" * 60)
    print("📊 RESULTADO DE LA SINCRONIZACIÓN")
    print("=" * 60)
    print(f"✅ Éxito: {resultado.get('success', False)}")
    print(f"🆕 Productos nuevos: {resultado.get('nuevos', 0)}")
    print(f"🔄 Productos actualizados: {resultado.get('actualizados', 0)}")
    print(f"📦 Total procesados: {resultado.get('total', 0)}")
    print(f"⚠️ Productos desactivados: {resultado.get('desactivados', 0)}")
    print(f"❌ Errores: {len(resultado.get('errores', []))}")
    
    if resultado.get('errores'):
        print("\n⚠️ ERRORES ENCONTRADOS:")
        for error in resultado.get('errores', []):
            print(f"  - {error}")
    
    print("\n✨ Prueba completada")
