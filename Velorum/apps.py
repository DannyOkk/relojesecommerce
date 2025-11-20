"""
Configuración de la aplicación Django Velorum
"""

from django.apps import AppConfig


class VelorumConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Velorum'
    
    def ready(self):
        """
        Hook que se ejecuta cuando Django está listo
        """
        import os
        
        # Solo iniciar scheduler en el proceso principal, no en reloads
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from . import scheduler
                scheduler.start()
            except Exception as e:
                print(f"Error al iniciar scheduler: {e}")
