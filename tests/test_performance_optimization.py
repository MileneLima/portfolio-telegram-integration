"""
Testes para otimizações de performance do sistema de metas
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from services.goal_service import goal_service
from models.schemas import ExpenseCategory
from database.models import Goal, Transaction
from database.sqlite_db import get_db_session


@pytest.mark.asyncio
class TestPerformanceOptimization:
    """Testes de otimização de performance"""
    
    async def test_cache_functionality(self):
        """Testa se o cache está funcionando corretamente"""
        user_id = 999001
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Limpar métricas antes do teste
        goal_service.reset_metrics()
        
        # Criar uma meta
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.ALIMENTACAO,
            valor_meta=Decimal("1000.00"),
            mes=mes,
            ano=ano
        )
        
        # Primeira consulta - deve ser cache miss
        initial_metrics = goal_service.get_metrics()
        initial_misses = initial_metrics["cache_misses"]
        
        goals1 = await goal_service.get_user_goals(user_id, mes, ano)
        
        metrics_after_first = goal_service.get_metrics()
        assert metrics_after_first["cache_misses"] > initial_misses, "Primeira consulta deve ser cache miss"
        
        # Segunda consulta - deve ser cache hit
        initial_hits = metrics_after_first["cache_hits"]
        goals2 = await goal_service.get_user_goals(user_id, mes, ano)
        
        metrics_after_second = goal_service.get_metrics()
        assert metrics_after_second["cache_hits"] > initial_hits, "Segunda consulta deve ser cache hit"
        
        # Verificar que os dados são os mesmos
        assert len(goals1) == len(goals2)
        assert goals1[0].valor_meta == goals2[0].valor_meta
        
        # Limpar
        await goal_service.clear_all_goals(user_id)
    
    async def test_cache_invalidation_on_update(self):
        """Testa se o cache é invalidado ao atualizar uma meta"""
        user_id = 999002
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Criar meta inicial
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.TRANSPORTE,
            valor_meta=Decimal("500.00"),
            mes=mes,
            ano=ano
        )
        
        # Consultar para popular cache
        goals1 = await goal_service.get_user_goals(user_id, mes, ano)
        assert goals1[0].valor_meta == Decimal("500.00")
        
        # Atualizar meta (deve invalidar cache)
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.TRANSPORTE,
            valor_meta=Decimal("800.00"),
            mes=mes,
            ano=ano
        )
        
        # Consultar novamente - deve buscar do banco com novo valor
        goals2 = await goal_service.get_user_goals(user_id, mes, ano)
        assert goals2[0].valor_meta == Decimal("800.00"), "Cache deve ter sido invalidado"
        
        # Limpar
        await goal_service.clear_all_goals(user_id)
    
    async def test_cache_invalidation_on_delete(self):
        """Testa se o cache é invalidado ao deletar uma meta"""
        user_id = 999003
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Criar meta
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.SAUDE,
            valor_meta=Decimal("300.00"),
            mes=mes,
            ano=ano
        )
        
        # Consultar para popular cache
        goals1 = await goal_service.get_user_goals(user_id, mes, ano)
        assert len(goals1) == 1
        
        # Deletar meta (deve invalidar cache)
        deleted = await goal_service.delete_goal(
            user_id=user_id,
            categoria=ExpenseCategory.SAUDE,
            mes=mes,
            ano=ano
        )
        assert deleted is True
        
        # Consultar novamente - deve retornar lista vazia
        goals2 = await goal_service.get_user_goals(user_id, mes, ano)
        assert len(goals2) == 0, "Cache deve ter sido invalidado após delete"
    
    async def test_metrics_tracking(self):
        """Testa se as métricas estão sendo rastreadas corretamente"""
        user_id = 999004
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Resetar métricas
        goal_service.reset_metrics()
        initial_metrics = goal_service.get_metrics()
        
        assert initial_metrics["goals_created"] == 0
        assert initial_metrics["goals_updated"] == 0
        assert initial_metrics["goals_deleted"] == 0
        assert initial_metrics["goals_queried"] == 0
        
        # Criar meta
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.LAZER,
            valor_meta=Decimal("400.00"),
            mes=mes,
            ano=ano
        )
        
        metrics_after_create = goal_service.get_metrics()
        assert metrics_after_create["goals_created"] == 1
        
        # Atualizar meta
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.LAZER,
            valor_meta=Decimal("600.00"),
            mes=mes,
            ano=ano
        )
        
        metrics_after_update = goal_service.get_metrics()
        assert metrics_after_update["goals_updated"] == 1
        
        # Consultar metas
        await goal_service.get_user_goals(user_id, mes, ano)
        
        metrics_after_query = goal_service.get_metrics()
        assert metrics_after_query["goals_queried"] == 1
        
        # Deletar meta
        await goal_service.delete_goal(
            user_id=user_id,
            categoria=ExpenseCategory.LAZER,
            mes=mes,
            ano=ano
        )
        
        metrics_after_delete = goal_service.get_metrics()
        assert metrics_after_delete["goals_deleted"] == 1
        
        # Verificar métricas de cache
        assert "cache_hit_rate_percent" in metrics_after_delete
        assert "cache_size" in metrics_after_delete
        assert "uptime_seconds" in metrics_after_delete
    
    async def test_cleanup_old_goals(self):
        """Testa a limpeza de metas antigas"""
        user_id = 999005
        
        # Criar meta antiga (2 anos atrás)
        old_date = datetime.now() - timedelta(days=730)
        old_mes = old_date.month
        old_ano = old_date.year
        
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.CASA,
            valor_meta=Decimal("1500.00"),
            mes=old_mes,
            ano=old_ano
        )
        
        # Criar meta recente
        current_mes = datetime.now().month
        current_ano = datetime.now().year
        
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.CASA,
            valor_meta=Decimal("2000.00"),
            mes=current_mes,
            ano=current_ano
        )
        
        # Verificar que ambas existem
        async for db in get_db_session():
            from sqlalchemy import select
            result = await db.execute(
                select(Goal).where(Goal.user_id == user_id)
            )
            goals_before = result.scalars().all()
            assert len(goals_before) == 2
        
        # Executar limpeza (manter apenas 12 meses)
        removed_count = await goal_service.cleanup_old_goals(months_to_keep=12)
        
        # Verificar que a meta antiga foi removida
        async for db in get_db_session():
            result = await db.execute(
                select(Goal).where(Goal.user_id == user_id)
            )
            goals_after = result.scalars().all()
            assert len(goals_after) == 1
            assert goals_after[0].mes == current_mes
            assert goals_after[0].ano == current_ano
        
        assert removed_count >= 1, "Pelo menos uma meta antiga deve ter sido removida"
        
        # Limpar
        await goal_service.clear_all_goals(user_id)
    
    async def test_cache_ttl_expiration(self):
        """Testa se o cache expira após o TTL"""
        user_id = 999006
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Criar meta
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.FINANCAS,
            valor_meta=Decimal("700.00"),
            mes=mes,
            ano=ano
        )
        
        # Consultar para popular cache
        await goal_service.get_user_goals(user_id, mes, ano)
        
        # Verificar que o cache está válido
        cache_key = goal_service._get_cache_key(user_id, mes, ano)
        assert goal_service._is_cache_valid(cache_key)
        
        # Simular expiração do cache (modificar timestamp)
        old_timestamp = datetime.now() - timedelta(seconds=goal_service._cache_ttl_seconds + 10)
        goal_service._cache_timestamps[cache_key] = old_timestamp
        
        # Verificar que o cache não é mais válido
        assert not goal_service._is_cache_valid(cache_key)
        
        # Limpar
        await goal_service.clear_all_goals(user_id)
    
    async def test_multiple_users_cache_isolation(self):
        """Testa se o cache isola corretamente dados de diferentes usuários"""
        user1_id = 999007
        user2_id = 999008
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Criar metas para usuário 1
        await goal_service.create_or_update_goal(
            user_id=user1_id,
            categoria=ExpenseCategory.ALIMENTACAO,
            valor_meta=Decimal("1000.00"),
            mes=mes,
            ano=ano
        )
        
        # Criar metas para usuário 2
        await goal_service.create_or_update_goal(
            user_id=user2_id,
            categoria=ExpenseCategory.ALIMENTACAO,
            valor_meta=Decimal("2000.00"),
            mes=mes,
            ano=ano
        )
        
        # Consultar metas de cada usuário
        goals_user1 = await goal_service.get_user_goals(user1_id, mes, ano)
        goals_user2 = await goal_service.get_user_goals(user2_id, mes, ano)
        
        # Verificar isolamento
        assert len(goals_user1) == 1
        assert len(goals_user2) == 1
        assert goals_user1[0].valor_meta == Decimal("1000.00")
        assert goals_user2[0].valor_meta == Decimal("2000.00")
        
        # Limpar
        await goal_service.clear_all_goals(user1_id)
        await goal_service.clear_all_goals(user2_id)
    
    async def test_metrics_reset(self):
        """Testa se o reset de métricas funciona corretamente"""
        user_id = 999009
        mes = datetime.now().month
        ano = datetime.now().year
        
        # Criar algumas operações
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=ExpenseCategory.OUTROS,
            valor_meta=Decimal("500.00"),
            mes=mes,
            ano=ano
        )
        
        await goal_service.get_user_goals(user_id, mes, ano)
        
        # Verificar que há métricas
        metrics_before = goal_service.get_metrics()
        assert metrics_before["goals_created"] > 0 or metrics_before["goals_queried"] > 0
        
        # Resetar métricas
        goal_service.reset_metrics()
        
        # Verificar que as métricas foram zeradas
        metrics_after = goal_service.get_metrics()
        assert metrics_after["goals_created"] == 0
        assert metrics_after["goals_updated"] == 0
        assert metrics_after["goals_deleted"] == 0
        assert metrics_after["goals_queried"] == 0
        assert metrics_after["cache_hits"] == 0
        assert metrics_after["cache_misses"] == 0
        assert metrics_after["alerts_sent"] == 0
        
        # Limpar
        await goal_service.clear_all_goals(user_id)
