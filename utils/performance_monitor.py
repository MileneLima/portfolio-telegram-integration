"""
Utilitário para monitoramento de performance do sistema de metas
"""

import asyncio
from datetime import datetime
from typing import Dict, Any
from loguru import logger
from services.goal_service import goal_service


class PerformanceMonitor:
    """Monitor de performance para o sistema de metas"""
    
    @staticmethod
    def get_metrics_report() -> str:
        """
        Gera relatório formatado das métricas de performance.
        
        Returns:
            String formatada com relatório de métricas
        """
        metrics = goal_service.get_metrics()
        
        report = [
            "=" * 60,
            "📊 RELATÓRIO DE PERFORMANCE - SISTEMA DE METAS",
            "=" * 60,
            "",
            "🎯 Operações de Metas:",
            f"  • Metas criadas: {metrics['goals_created']}",
            f"  • Metas atualizadas: {metrics['goals_updated']}",
            f"  • Metas deletadas: {metrics['goals_deleted']}",
            f"  • Consultas realizadas: {metrics['goals_queried']}",
            "",
            "💾 Performance de Cache:",
            f"  • Cache hits: {metrics['cache_hits']}",
            f"  • Cache misses: {metrics['cache_misses']}",
            f"  • Taxa de acerto: {metrics['cache_hit_rate_percent']:.2f}%",
            f"  • Tamanho do cache: {metrics['cache_size']} período(s)",
            "",
            "🔔 Alertas:",
            f"  • Alertas enviados: {metrics['alerts_sent']}",
            f"  • Cooldowns ativos: {metrics['active_cooldowns']}",
            "",
            "⏱️ Tempo de Execução:",
            f"  • Uptime: {metrics['uptime_seconds']:.2f} segundos",
            f"  • Último reset: {metrics['last_reset'].strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "=" * 60,
        ]
        
        return "\n".join(report)
    
    @staticmethod
    def print_metrics():
        """Imprime relatório de métricas no console"""
        print(PerformanceMonitor.get_metrics_report())
    
    @staticmethod
    def get_cache_efficiency() -> Dict[str, Any]:
        """
        Calcula eficiência do cache.
        
        Returns:
            Dicionário com métricas de eficiência
        """
        metrics = goal_service.get_metrics()
        
        total_queries = metrics['cache_hits'] + metrics['cache_misses']
        hit_rate = (metrics['cache_hits'] / total_queries * 100) if total_queries > 0 else 0
        
        # Classificar eficiência
        if hit_rate >= 80:
            efficiency_level = "Excelente"
        elif hit_rate >= 60:
            efficiency_level = "Boa"
        elif hit_rate >= 40:
            efficiency_level = "Regular"
        else:
            efficiency_level = "Baixa"
        
        return {
            "total_queries": total_queries,
            "hit_rate_percent": round(hit_rate, 2),
            "efficiency_level": efficiency_level,
            "cache_size": metrics['cache_size'],
            "recommendation": PerformanceMonitor._get_cache_recommendation(hit_rate, metrics['cache_size'])
        }
    
    @staticmethod
    def _get_cache_recommendation(hit_rate: float, cache_size: int) -> str:
        """Gera recomendação baseada nas métricas de cache"""
        if hit_rate < 40:
            return "Considere aumentar o TTL do cache para melhorar a taxa de acerto"
        elif cache_size > 100:
            return "Cache muito grande, considere implementar política de eviction"
        elif hit_rate >= 80:
            return "Cache funcionando de forma otimizada"
        else:
            return "Performance de cache adequada"
    
    @staticmethod
    async def cleanup_old_data(months_to_keep: int = 12, dry_run: bool = False) -> Dict[str, Any]:
        """
        Executa limpeza de dados antigos.
        
        Args:
            months_to_keep: Número de meses de histórico a manter
            dry_run: Se True, apenas simula a limpeza sem executar
            
        Returns:
            Dicionário com resultado da operação
        """
        logger.info(f"🧹 Iniciando limpeza de dados antigos (manter {months_to_keep} meses)")
        
        if dry_run:
            logger.info("⚠️ Modo DRY RUN - nenhuma alteração será feita")
            # Em modo dry run, apenas retorna estimativa
            return {
                "dry_run": True,
                "estimated_removals": "Não implementado",
                "message": "Modo dry run - use dry_run=False para executar"
            }
        
        try:
            removed_count = await goal_service.cleanup_old_goals(months_to_keep)
            
            result = {
                "success": True,
                "removed_count": removed_count,
                "months_kept": months_to_keep,
                "timestamp": datetime.now().isoformat(),
                "message": f"Limpeza concluída: {removed_count} meta(s) removida(s)"
            }
            
            logger.info(f"✅ {result['message']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro durante limpeza: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erro durante limpeza de dados"
            }
    
    @staticmethod
    def reset_all_metrics():
        """Reseta todas as métricas do sistema"""
        logger.info("🔄 Resetando métricas do sistema")
        goal_service.reset_metrics()
        logger.info("✅ Métricas resetadas com sucesso")
    
    @staticmethod
    def get_health_status() -> Dict[str, Any]:
        """
        Verifica status de saúde do sistema de metas.
        
        Returns:
            Dicionário com status de saúde
        """
        metrics = goal_service.get_metrics()
        cache_efficiency = PerformanceMonitor.get_cache_efficiency()
        
        # Determinar status geral
        issues = []
        
        if cache_efficiency['hit_rate_percent'] < 40:
            issues.append("Taxa de acerto do cache baixa")
        
        if metrics['cache_size'] > 100:
            issues.append("Cache muito grande")
        
        if metrics['active_cooldowns'] > 50:
            issues.append("Muitos cooldowns ativos")
        
        status = "healthy" if len(issues) == 0 else "warning" if len(issues) <= 2 else "critical"
        
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": metrics['uptime_seconds'],
            "cache_efficiency": cache_efficiency['efficiency_level'],
            "issues": issues,
            "metrics_summary": {
                "total_operations": (
                    metrics['goals_created'] + 
                    metrics['goals_updated'] + 
                    metrics['goals_deleted']
                ),
                "cache_hit_rate": cache_efficiency['hit_rate_percent'],
                "alerts_sent": metrics['alerts_sent']
            }
        }


# Funções de conveniência para uso em scripts
def print_metrics():
    """Imprime métricas de performance"""
    PerformanceMonitor.print_metrics()


def print_health():
    """Imprime status de saúde do sistema"""
    health = PerformanceMonitor.get_health_status()
    
    print("\n" + "=" * 60)
    print("🏥 STATUS DE SAÚDE DO SISTEMA")
    print("=" * 60)
    print(f"\nStatus: {health['status'].upper()}")
    print(f"Timestamp: {health['timestamp']}")
    print(f"Uptime: {health['uptime_seconds']:.2f} segundos")
    print(f"Eficiência do Cache: {health['cache_efficiency']}")
    
    if health['issues']:
        print("\n⚠️ Problemas Detectados:")
        for issue in health['issues']:
            print(f"  • {issue}")
    else:
        print("\n✅ Nenhum problema detectado")
    
    print("\n📊 Resumo de Métricas:")
    print(f"  • Total de operações: {health['metrics_summary']['total_operations']}")
    print(f"  • Taxa de acerto do cache: {health['metrics_summary']['cache_hit_rate']:.2f}%")
    print(f"  • Alertas enviados: {health['metrics_summary']['alerts_sent']}")
    print("\n" + "=" * 60 + "\n")


async def cleanup_old_goals(months: int = 12, dry_run: bool = False):
    """
    Executa limpeza de metas antigas.
    
    Args:
        months: Número de meses de histórico a manter
        dry_run: Se True, apenas simula sem executar
    """
    result = await PerformanceMonitor.cleanup_old_data(months, dry_run)
    
    print("\n" + "=" * 60)
    print("🧹 LIMPEZA DE DADOS ANTIGOS")
    print("=" * 60)
    
    if result.get('dry_run'):
        print("\n⚠️ MODO DRY RUN - Nenhuma alteração foi feita")
    
    print(f"\n{result['message']}")
    
    if result.get('success'):
        print(f"  • Metas removidas: {result['removed_count']}")
        print(f"  • Meses mantidos: {result['months_kept']}")
    elif result.get('error'):
        print(f"  • Erro: {result['error']}")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "metrics":
            print_metrics()
        elif command == "health":
            print_health()
        elif command == "cleanup":
            months = int(sys.argv[2]) if len(sys.argv) > 2 else 12
            dry_run = "--dry-run" in sys.argv
            asyncio.run(cleanup_old_goals(months, dry_run))
        elif command == "reset":
            PerformanceMonitor.reset_all_metrics()
            print("✅ Métricas resetadas com sucesso")
        else:
            print("Comandos disponíveis:")
            print("  metrics  - Exibir métricas de performance")
            print("  health   - Exibir status de saúde do sistema")
            print("  cleanup [months] [--dry-run] - Limpar metas antigas")
            print("  reset    - Resetar métricas")
    else:
        print("Uso: python -m utils.performance_monitor <comando>")
        print("\nComandos disponíveis:")
        print("  metrics  - Exibir métricas de performance")
        print("  health   - Exibir status de saúde do sistema")
        print("  cleanup [months] [--dry-run] - Limpar metas antigas")
        print("  reset    - Resetar métricas")
