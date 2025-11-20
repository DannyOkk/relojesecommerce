"""
Configuración del scheduler para tareas automáticas
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler_started = False


def start():
    """
    Inicia el scheduler cuando Django arranca
    """
    global scheduler_started
    
    if scheduler_started:
        logger.info("Scheduler ya está en ejecución")
        return
    
    try:
        from market.scraper import sync_external_products
        
        # Configurar job de sincronización cada 1 hora
        scheduler.add_job(
            func=sync_external_products,
            trigger=IntervalTrigger(hours=1),
            id='sync_external_products',
            name='Sincronizar productos externos',
            replace_existing=True,
            max_instances=1  # Solo una instancia a la vez
        )
        
        scheduler.start()
        scheduler_started = True
        
        logger.info("✅ Scheduler iniciado - Sincronización automática cada 1 hora")
        
    except Exception as e:
        logger.error(f"Error al iniciar scheduler: {str(e)}")


def stop():
    """
    Detiene el scheduler
    """
    global scheduler_started
    
    if scheduler_started:
        scheduler.shutdown()
        scheduler_started = False
        logger.info("Scheduler detenido")
