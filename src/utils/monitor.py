"""
System monitoring and health checks
"""
import asyncio
import psutil
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from ..config import settings
from ..database import db_manager

logger = logging.getLogger(__name__)

class SystemMonitor:
    """System monitoring and health checks"""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.health_checks = []
        self.metrics_history = []
        self.max_history_size = 1000
    
    async def check_system_health(self) -> Dict[str, Any]:
        """Perform comprehensive system health check"""
        health_status = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'healthy',
            'checks': {},
            'metrics': {},
            'alerts': []
        }
        
        try:
            # Check system resources
            health_status['checks']['system_resources'] = await self._check_system_resources()
            
            # Check database connectivity
            health_status['checks']['database'] = await self._check_database()
            
            # Check Ollama service
            health_status['checks']['ollama'] = await self._check_ollama()
            
            # Check Redis connectivity
            health_status['checks']['redis'] = await self._check_redis()
            
            # Check external APIs
            health_status['checks']['external_apis'] = await self._check_external_apis()
            
            # Get system metrics
            health_status['metrics'] = await self._get_system_metrics()
            
            # Determine overall status
            failed_checks = [check for check in health_status['checks'].values() if not check['status']]
            if failed_checks:
                health_status['overall_status'] = 'degraded' if len(failed_checks) < 3 else 'unhealthy'
                health_status['alerts'] = [check['message'] for check in failed_checks]
            
            # Store in history
            self.metrics_history.append(health_status)
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history.pop(0)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error in system health check: {e}")
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'overall_status': 'error',
                'error': str(e),
                'checks': {},
                'metrics': {},
                'alerts': [f"Health check failed: {e}"]
            }
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Check thresholds
            cpu_ok = cpu_percent < 80
            memory_ok = memory.percent < 85
            disk_ok = disk.percent < 90
            
            status = cpu_ok and memory_ok and disk_ok
            
            return {
                'status': status,
                'message': 'System resources OK' if status else 'High resource usage detected',
                'details': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'disk_percent': disk.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_free_gb': disk.free / (1024**3)
                }
            }
            
        except Exception as e:
            return {
                'status': False,
                'message': f'System resource check failed: {e}',
                'details': {}
            }
    
    async def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        try:
            # Try to get a simple query
            stats = await db_manager.get_stats()
            
            return {
                'status': True,
                'message': 'Database connection OK',
                'details': {
                    'total_news': stats.total_news_collected,
                    'processed_news': stats.total_news_processed,
                    'published_news': stats.total_news_published
                }
            }
            
        except Exception as e:
            return {
                'status': False,
                'message': f'Database connection failed: {e}',
                'details': {}
            }
    
    async def _check_ollama(self) -> Dict[str, Any]:
        """Check Ollama service"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{settings.ollama_base_url}/api/tags"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [model['name'] for model in data.get('models', [])]
                        
                        return {
                            'status': True,
                            'message': 'Ollama service OK',
                            'details': {
                                'available_models': models,
                                'current_model': settings.ollama_model
                            }
                        }
                    else:
                        return {
                            'status': False,
                            'message': f'Ollama returned status {response.status}',
                            'details': {}
                        }
                        
        except Exception as e:
            return {
                'status': False,
                'message': f'Ollama service unavailable: {e}',
                'details': {}
            }
    
    async def _check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity"""
        try:
            # Simple ping test
            await db_manager.redis.ping()
            
            return {
                'status': True,
                'message': 'Redis connection OK',
                'details': {}
            }
            
        except Exception as e:
            return {
                'status': False,
                'message': f'Redis connection failed: {e}',
                'details': {}
            }
    
    async def _check_external_apis(self) -> Dict[str, Any]:
        """Check external API availability"""
        apis_status = {}
        
        # Check RSS feeds
        try:
            async with aiohttp.ClientSession() as session:
                for feed_url in settings.rss_feeds[:2]:  # Check first 2 feeds
                    try:
                        async with session.get(feed_url, timeout=10) as response:
                            apis_status[feed_url] = response.status == 200
                    except:
                        apis_status[feed_url] = False
        except Exception as e:
            apis_status['error'] = str(e)
        
        working_apis = sum(1 for status in apis_status.values() if status)
        total_apis = len(apis_status)
        
        return {
            'status': working_apis > 0,
            'message': f'{working_apis}/{total_apis} external APIs working',
            'details': apis_status
        }
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system metrics"""
        try:
            uptime = datetime.utcnow() - self.start_time
            
            return {
                'uptime_seconds': uptime.total_seconds(),
                'uptime_hours': uptime.total_seconds() / 3600,
                'process_count': len(psutil.pids()),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def get_metrics_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get metrics history for the last N hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        return [
            metrics for metrics in self.metrics_history
            if datetime.fromisoformat(metrics['timestamp']) > cutoff_time
        ]
    
    def get_uptime_stats(self) -> Dict[str, Any]:
        """Get uptime statistics"""
        uptime = datetime.utcnow() - self.start_time
        
        return {
            'start_time': self.start_time.isoformat(),
            'uptime_seconds': uptime.total_seconds(),
            'uptime_hours': uptime.total_seconds() / 3600,
            'uptime_days': uptime.days
        }
    
    async def send_alert(self, message: str, severity: str = 'warning'):
        """Send alert notification"""
        alert = {
            'timestamp': datetime.utcnow().isoformat(),
            'message': message,
            'severity': severity
        }
        
        logger.warning(f"ALERT [{severity.upper()}]: {message}")
        
        # Here you could integrate with notification services
        # like email, Slack, Discord, etc.
        
        return alert
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for dashboard"""
        if not self.metrics_history:
            return {'status': 'no_data', 'message': 'No health data available'}
        
        latest = self.metrics_history[-1]
        
        return {
            'status': latest['overall_status'],
            'timestamp': latest['timestamp'],
            'alerts_count': len(latest.get('alerts', [])),
            'checks_passed': sum(1 for check in latest['checks'].values() if check['status']),
            'total_checks': len(latest['checks']),
            'uptime_hours': latest['metrics'].get('uptime_hours', 0)
        }

# Global monitor instance
system_monitor = SystemMonitor()
