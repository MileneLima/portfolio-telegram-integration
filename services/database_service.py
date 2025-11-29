"""
Serviço de consultas ao banco de dados SQLite
Fonte principal para todos os relatórios e análises
"""

from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import select, func, extract, and_
from loguru import logger

from database.sqlite_db import get_db_session
from database.models import Transaction, Goal


class DatabaseService:
    """Serviço para consultas e análises no banco SQLite"""

    async def get_monthly_summary(self, month: int = None, year: int = None, user_id: int = None) -> Dict[str, Any]:
        """Obter resumo mensal do banco SQLite"""
        try:
            if month is None or year is None:
                now = datetime.now()
                month = month or now.month
                year = year or now.year

            async for db in get_db_session():
                # Construir condições da query
                conditions = [
                    extract('month', Transaction.data_transacao) == month,
                    extract('year', Transaction.data_transacao) == year,
                    Transaction.status == 'processed'
                ]
                
                # Adicionar filtro de user_id se fornecido
                if user_id is not None:
                    conditions.append(Transaction.user_id == user_id)
                
                result = await db.execute(
                    select(
                        Transaction.categoria,
                        func.sum(Transaction.valor).label('total'),
                        func.count(Transaction.id).label('count')
                    )
                    .where(and_(*conditions))
                    .group_by(Transaction.categoria)
                )
                
                categorias = {}
                total_geral = 0
                total_transacoes = 0
                
                for row in result:
                    categoria = row.categoria
                    valor = float(row.total)
                    count = row.count
                    
                    categorias[categoria] = valor
                    total_transacoes += count
                    
                    if categoria != "Finanças":
                        total_geral += valor

                # Obter estatísticas por tipo de origem para o período
                source_conditions = [
                    extract('month', Transaction.data_transacao) == month,
                    extract('year', Transaction.data_transacao) == year,
                    Transaction.status == 'processed'
                ]
                
                # Adicionar filtro de user_id se fornecido
                if user_id is not None:
                    source_conditions.append(Transaction.user_id == user_id)
                
                source_result = await db.execute(
                    select(
                        Transaction.source_type,
                        func.count(Transaction.id).label('count')
                    )
                    .where(and_(*source_conditions))
                    .group_by(Transaction.source_type)
                )
                
                source_stats = {}
                for row in source_result:
                    source_type = row.source_type or "text"
                    source_stats[source_type] = row.count

                meses_pt = [
                    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
                ]
                mes_nome = meses_pt[month - 1]

                return {
                    "mes": mes_nome,
                    "total": total_geral,
                    "transacoes": total_transacoes,
                    "categorias": categorias,
                    "source_stats": source_stats
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter resumo mensal: {e}")
            return {"mes": "Erro", "total": 0, "transacoes": 0, "categorias": {}, "source_stats": {}}

    async def get_yearly_summary(self, year: int = None, user_id: int = None) -> Dict[str, Any]:
        """Obter resumo anual do banco SQLite"""
        try:
            if year is None:
                year = datetime.now().year

            async for db in get_db_session():
                # Construir condições da query
                conditions = [
                    extract('year', Transaction.data_transacao) == year,
                    Transaction.status == 'processed'
                ]
                
                # Adicionar filtro de user_id se fornecido
                if user_id is not None:
                    conditions.append(Transaction.user_id == user_id)
                
                result = await db.execute(
                    select(
                        Transaction.categoria,
                        func.sum(Transaction.valor).label('total'),
                        func.count(Transaction.id).label('count')
                    )
                    .where(and_(*conditions))
                    .group_by(Transaction.categoria)
                )
                
                categorias_totais = {}
                total_gastos = 0
                total_financas = 0
                total_transacoes = 0
                
                for row in result:
                    categoria = row.categoria
                    valor = float(row.total)
                    count = row.count
                    
                    total_transacoes += count
                    
                    if categoria == "Finanças":
                        total_financas += valor
                    else:
                        total_gastos += valor
                        categorias_totais[categoria] = valor

                # Obter estatísticas por tipo de origem para o ano
                source_conditions = [
                    extract('year', Transaction.data_transacao) == year,
                    Transaction.status == 'processed'
                ]
                
                # Adicionar filtro de user_id se fornecido
                if user_id is not None:
                    source_conditions.append(Transaction.user_id == user_id)
                
                source_result = await db.execute(
                    select(
                        Transaction.source_type,
                        func.count(Transaction.id).label('count')
                    )
                    .where(and_(*source_conditions))
                    .group_by(Transaction.source_type)
                )
                
                source_stats = {}
                for row in source_result:
                    source_type = row.source_type or "text"
                    source_stats[source_type] = row.count

                dados_mensais = []
                for month in range(1, 13):
                    resumo_mensal = await self.get_monthly_summary(month, year, user_id)
                    if resumo_mensal["transacoes"] > 0:
                        dados_mensais.append(resumo_mensal)

                return {
                    "periodo": "anual",
                    "ano": year,
                    "total_gastos": total_gastos,
                    "total_financas": total_financas,
                    "total_transacoes": total_transacoes,
                    "categorias_totais": categorias_totais,
                    "dados_mensais": dados_mensais,
                    "source_stats": source_stats
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter resumo anual: {e}")
            return {"error": str(e)}

    async def get_transactions_for_period(self, period_type: str, period_value: str = None) -> List[Dict[str, Any]]:
        """Obter transações para um período específico (para insights)"""
        try:
            async for db in get_db_session():
                if period_type == "monthly":
                    if period_value:
                        meses_pt = {
                            "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
                            "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
                            "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
                        }
                        month = meses_pt.get(period_value, datetime.now().month)
                        year = datetime.now().year
                    else:
                        now = datetime.now()
                        month = now.month
                        year = now.year

                    result = await db.execute(
                        select(Transaction)
                        .where(
                            and_(
                                extract('month', Transaction.data_transacao) == month,
                                extract('year', Transaction.data_transacao) == year,
                                Transaction.status == 'processed'
                            )
                        )
                        .order_by(Transaction.data_transacao.desc())
                    )

                elif period_type == "yearly":
                    year = datetime.now().year
                    result = await db.execute(
                        select(Transaction)
                        .where(
                            and_(
                                extract('year', Transaction.data_transacao) == year,
                                Transaction.status == 'processed'
                            )
                        )
                        .order_by(Transaction.data_transacao.desc())
                    )

                else:
                    return []

                transactions = []
                for transaction in result.scalars():
                    # Adicionar informação de origem nas observações
                    observacoes = f"Confiança: {transaction.confianca:.0%}"
                    if transaction.source_type == "audio_transcribed":
                        observacoes += " | Origem: Áudio transcrito"
                    
                    transactions.append({
                        "id": transaction.id,
                        "data": transaction.data_transacao.strftime("%d/%m/%Y"),
                        "descricao": transaction.descricao,
                        "categoria": transaction.categoria,
                        "valor": float(transaction.valor),
                        "observacoes": observacoes,
                        "source_type": transaction.source_type or "text"
                    })

                return transactions

        except Exception as e:
            logger.error(f"❌ Erro ao obter transações para período: {e}")
            return []

    async def get_category_analysis(self, year: int = None) -> Dict[str, Any]:
        """Análise detalhada por categoria"""
        try:
            if year is None:
                year = datetime.now().year

            async for db in get_db_session():
                result = await db.execute(
                    select(
                        Transaction.categoria,
                        func.sum(Transaction.valor).label('total'),
                        func.count(Transaction.id).label('transacoes'),
                        func.avg(Transaction.valor).label('media'),
                        func.max(Transaction.valor).label('maior'),
                        func.min(Transaction.valor).label('menor')
                    )
                    .where(
                        and_(
                            extract('year', Transaction.data_transacao) == year,
                            Transaction.status == 'processed'
                        )
                    )
                    .group_by(Transaction.categoria)
                    .order_by(func.sum(Transaction.valor).desc())
                )

                analise = {}
                for row in result:
                    analise[row.categoria] = {
                        "total": float(row.total),
                        "transacoes": row.transacoes,
                        "media": float(row.media),
                        "maior_gasto": float(row.maior),
                        "menor_gasto": float(row.menor)
                    }

                return analise

        except Exception as e:
            logger.error(f"❌ Erro na análise por categoria: {e}")
            return {}

    async def get_database_stats(self) -> Dict[str, Any]:
        """Estatísticas gerais do banco de dados"""
        try:
            async for db in get_db_session():
                total_result = await db.execute(
                    select(func.count(Transaction.id))
                    .where(Transaction.status == 'processed')
                )
                total_transacoes = total_result.scalar()

                # Estatísticas por tipo de origem
                source_stats_result = await db.execute(
                    select(
                        Transaction.source_type,
                        func.count(Transaction.id).label('count')
                    )
                    .where(Transaction.status == 'processed')
                    .group_by(Transaction.source_type)
                )
                
                source_stats = {}
                for row in source_stats_result:
                    source_type = row.source_type or "text"
                    source_stats[source_type] = row.count

                date_result = await db.execute(
                    select(
                        func.min(Transaction.data_transacao).label('primeira'),
                        func.max(Transaction.data_transacao).label('ultima')
                    )
                    .where(Transaction.status == 'processed')
                )
                dates = date_result.first()

                valor_result = await db.execute(
                    select(func.sum(Transaction.valor))
                    .where(
                        and_(
                            Transaction.status == 'processed',
                            Transaction.categoria != 'Finanças'
                        )
                    )
                )
                total_gasto = valor_result.scalar() or 0

                return {
                    "total_transacoes": total_transacoes,
                    "primeira_transacao": dates.primeira.strftime("%d/%m/%Y") if dates.primeira else "N/A",
                    "ultima_transacao": dates.ultima.strftime("%d/%m/%Y") if dates.ultima else "N/A",
                    "total_gasto": float(total_gasto),
                    "periodo_dias": (dates.ultima - dates.primeira).days if dates.primeira and dates.ultima else 0,
                    "source_stats": source_stats
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {e}")
            return {}

    async def get_monthly_spending_by_category(
        self, 
        user_id: int, 
        categoria: str, 
        mes: int, 
        ano: int
    ) -> float:
        """
        Obter total de gastos de uma categoria específica em um mês
        
        Args:
            user_id: ID do usuário
            categoria: Nome da categoria
            mes: Mês (1-12)
            ano: Ano
            
        Returns:
            Total gasto na categoria no período
        """
        try:
            async for db in get_db_session():
                result = await db.execute(
                    select(func.sum(Transaction.valor))
                    .where(
                        and_(
                            Transaction.user_id == user_id,
                            Transaction.categoria == categoria,
                            extract('month', Transaction.data_transacao) == mes,
                            extract('year', Transaction.data_transacao) == ano,
                            Transaction.status == 'processed'
                        )
                    )
                )
                total = result.scalar()
                return float(total) if total else 0.0

        except Exception as e:
            logger.error(f"❌ Erro ao obter gastos por categoria: {e}")
            return 0.0

    async def get_goal_statistics(
        self, 
        user_id: int, 
        mes: int = None, 
        ano: int = None
    ) -> Dict[str, Any]:
        """
        Obter estatísticas de metas para um usuário em um período
        
        Args:
            user_id: ID do usuário
            mes: Mês (1-12), padrão é mês atual
            ano: Ano, padrão é ano atual
            
        Returns:
            Dicionário com estatísticas de metas incluindo progresso
        """
        try:
            if mes is None or ano is None:
                now = datetime.now()
                mes = mes or now.month
                ano = ano or now.year

            async for db in get_db_session():
                # Buscar todas as metas do usuário para o período
                goals_result = await db.execute(
                    select(Goal)
                    .where(
                        and_(
                            Goal.user_id == user_id,
                            Goal.mes == mes,
                            Goal.ano == ano
                        )
                    )
                )
                goals = goals_result.scalars().all()

                if not goals:
                    return {
                        "mes": mes,
                        "ano": ano,
                        "total_metas": 0,
                        "metas": []
                    }

                metas_info = []
                total_valor_metas = 0.0
                total_valor_gasto = 0.0

                for goal in goals:
                    # Obter gastos da categoria no período
                    gasto_atual = await self.get_monthly_spending_by_category(
                        user_id, goal.categoria, mes, ano
                    )
                    
                    valor_meta = float(goal.valor_meta)
                    progresso_percentual = (gasto_atual / valor_meta * 100) if valor_meta > 0 else 0
                    
                    # Determinar status da meta
                    if progresso_percentual >= 100:
                        status = "LIMITE_EXCEDIDO"
                    elif progresso_percentual >= 80:
                        status = "PROXIMO_LIMITE"
                    else:
                        status = "DENTRO_META"

                    metas_info.append({
                        "id": goal.id,
                        "categoria": goal.categoria,
                        "valor_meta": valor_meta,
                        "valor_gasto": gasto_atual,
                        "progresso_percentual": round(progresso_percentual, 2),
                        "status": status,
                        "created_at": goal.created_at.isoformat() if goal.created_at else None,
                        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None
                    })
                    
                    total_valor_metas += valor_meta
                    total_valor_gasto += gasto_atual

                # Calcular estatísticas gerais
                metas_dentro = sum(1 for m in metas_info if m["status"] == "DENTRO_META")
                metas_proximo = sum(1 for m in metas_info if m["status"] == "PROXIMO_LIMITE")
                metas_excedidas = sum(1 for m in metas_info if m["status"] == "LIMITE_EXCEDIDO")

                return {
                    "mes": mes,
                    "ano": ano,
                    "total_metas": len(goals),
                    "metas_dentro": metas_dentro,
                    "metas_proximo_limite": metas_proximo,
                    "metas_excedidas": metas_excedidas,
                    "total_valor_metas": round(total_valor_metas, 2),
                    "total_valor_gasto": round(total_valor_gasto, 2),
                    "progresso_geral_percentual": round(
                        (total_valor_gasto / total_valor_metas * 100) if total_valor_metas > 0 else 0, 
                        2
                    ),
                    "metas": metas_info
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas de metas: {e}")
            return {
                "mes": mes or datetime.now().month,
                "ano": ano or datetime.now().year,
                "total_metas": 0,
                "metas": [],
                "error": str(e)
            }


database_service = DatabaseService()