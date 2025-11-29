"""
Testes para os métodos de suporte a metas no DatabaseService
"""

import pytest
from datetime import datetime
from decimal import Decimal

from services.database_service import database_service
from database.sqlite_db import get_db_session
from database.models import Goal, Transaction


@pytest.mark.asyncio
class TestDatabaseServiceGoalSupport:
    """Testes para métodos de suporte a metas no DatabaseService"""

    async def test_get_monthly_spending_by_category(self):
        """Testar consulta de gastos por categoria e mês"""
        user_id = 999999
        categoria = "Alimentação"
        mes = 11
        ano = 2025
        
        # Criar transações de teste
        async for db in get_db_session():
            # Transação no mês correto
            t1 = Transaction(
                user_id=user_id,
                message_id=1,
                chat_id=1,
                original_message="test",
                descricao="Almoço",
                valor=Decimal("50.00"),
                categoria=categoria,
                data_transacao=datetime(ano, mes, 15).date(),
                status="processed"
            )
            
            # Outra transação no mês correto
            t2 = Transaction(
                user_id=user_id,
                message_id=2,
                chat_id=1,
                original_message="test",
                descricao="Jantar",
                valor=Decimal("30.00"),
                categoria=categoria,
                data_transacao=datetime(ano, mes, 20).date(),
                status="processed"
            )
            
            # Transação em outro mês (não deve contar)
            t3 = Transaction(
                user_id=user_id,
                message_id=3,
                chat_id=1,
                original_message="test",
                descricao="Café",
                valor=Decimal("20.00"),
                categoria=categoria,
                data_transacao=datetime(ano, mes + 1 if mes < 12 else 1, 5).date(),
                status="processed"
            )
            
            # Transação de outra categoria (não deve contar)
            t4 = Transaction(
                user_id=user_id,
                message_id=4,
                chat_id=1,
                original_message="test",
                descricao="Uber",
                valor=Decimal("25.00"),
                categoria="Transporte",
                data_transacao=datetime(ano, mes, 18).date(),
                status="processed"
            )
            
            db.add_all([t1, t2, t3, t4])
            await db.commit()
            
            try:
                # Testar o método
                total = await database_service.get_monthly_spending_by_category(
                    user_id, categoria, mes, ano
                )
                
                # Deve somar apenas t1 e t2
                assert total == 80.00, f"Esperado 80.00, obtido {total}"
                
            finally:
                # Limpar dados de teste
                await db.execute(
                    Transaction.__table__.delete().where(Transaction.user_id == user_id)
                )
                await db.commit()

    async def test_get_goal_statistics(self):
        """Testar estatísticas de metas"""
        user_id = 999998
        mes = 11
        ano = 2025
        
        async for db in get_db_session():
            # Criar metas de teste
            goal1 = Goal(
                user_id=user_id,
                categoria="Alimentação",
                valor_meta=Decimal("500.00"),
                mes=mes,
                ano=ano
            )
            
            goal2 = Goal(
                user_id=user_id,
                categoria="Transporte",
                valor_meta=Decimal("200.00"),
                mes=mes,
                ano=ano
            )
            
            db.add_all([goal1, goal2])
            await db.commit()
            
            # Criar transações para testar progresso
            t1 = Transaction(
                user_id=user_id,
                message_id=1,
                chat_id=1,
                original_message="test",
                descricao="Almoço",
                valor=Decimal("450.00"),  # 90% da meta
                categoria="Alimentação",
                data_transacao=datetime(ano, mes, 15).date(),
                status="processed"
            )
            
            t2 = Transaction(
                user_id=user_id,
                message_id=2,
                chat_id=1,
                original_message="test",
                descricao="Uber",
                valor=Decimal("250.00"),  # 125% da meta
                categoria="Transporte",
                data_transacao=datetime(ano, mes, 20).date(),
                status="processed"
            )
            
            db.add_all([t1, t2])
            await db.commit()
            
            try:
                # Testar o método
                stats = await database_service.get_goal_statistics(user_id, mes, ano)
                
                # Verificar estrutura básica
                assert stats["mes"] == mes
                assert stats["ano"] == ano
                assert stats["total_metas"] == 2
                
                # Verificar contadores de status
                assert stats["metas_proximo_limite"] == 1  # Alimentação (90%)
                assert stats["metas_excedidas"] == 1  # Transporte (125%)
                assert stats["metas_dentro"] == 0
                
                # Verificar totais
                assert stats["total_valor_metas"] == 700.00
                assert stats["total_valor_gasto"] == 700.00
                
                # Verificar metas individuais
                assert len(stats["metas"]) == 2
                
                # Encontrar meta de Alimentação
                meta_alimentacao = next(m for m in stats["metas"] if m["categoria"] == "Alimentação")
                assert meta_alimentacao["valor_meta"] == 500.00
                assert meta_alimentacao["valor_gasto"] == 450.00
                assert meta_alimentacao["progresso_percentual"] == 90.00
                assert meta_alimentacao["status"] == "PROXIMO_LIMITE"
                
                # Encontrar meta de Transporte
                meta_transporte = next(m for m in stats["metas"] if m["categoria"] == "Transporte")
                assert meta_transporte["valor_meta"] == 200.00
                assert meta_transporte["valor_gasto"] == 250.00
                assert meta_transporte["progresso_percentual"] == 125.00
                assert meta_transporte["status"] == "LIMITE_EXCEDIDO"
                
            finally:
                # Limpar dados de teste
                await db.execute(
                    Goal.__table__.delete().where(Goal.user_id == user_id)
                )
                await db.execute(
                    Transaction.__table__.delete().where(Transaction.user_id == user_id)
                )
                await db.commit()

    async def test_get_goal_statistics_no_goals(self):
        """Testar estatísticas quando não há metas"""
        user_id = 999997
        mes = 11
        ano = 2025
        
        stats = await database_service.get_goal_statistics(user_id, mes, ano)
        
        assert stats["mes"] == mes
        assert stats["ano"] == ano
        assert stats["total_metas"] == 0
        assert stats["metas"] == []

    async def test_get_monthly_spending_by_category_no_transactions(self):
        """Testar consulta quando não há transações"""
        user_id = 999996
        categoria = "Alimentação"
        mes = 11
        ano = 2025
        
        total = await database_service.get_monthly_spending_by_category(
            user_id, categoria, mes, ano
        )
        
        assert total == 0.0
