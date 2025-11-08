"""
Serviço de consultas ao banco de dados SQLite
Fonte principal para todos os relatórios e análises
"""

from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import select, func, extract, and_
from loguru import logger

from database.sqlite_db import get_db_session
from database.models import Transaction


class DatabaseService:
    """Serviço para consultas e análises no banco SQLite"""

    async def get_monthly_summary(self, month: int = None, year: int = None) -> Dict[str, Any]:
        """Obter resumo mensal do banco SQLite"""
        try:
            if month is None or year is None:
                now = datetime.now()
                month = month or now.month
                year = year or now.year

            async for db in get_db_session():
                result = await db.execute(
                    select(
                        Transaction.categoria,
                        func.sum(Transaction.valor).label('total'),
                        func.count(Transaction.id).label('count')
                    )
                    .where(
                        and_(
                            extract('month', Transaction.data_transacao) == month,
                            extract('year', Transaction.data_transacao) == year,
                            Transaction.status == 'processed'
                        )
                    )
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

                meses_pt = [
                    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
                ]
                mes_nome = meses_pt[month - 1]

                return {
                    "mes": mes_nome,
                    "total": total_geral,
                    "transacoes": total_transacoes,
                    "categorias": categorias
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter resumo mensal: {e}")
            return {"mes": "Erro", "total": 0, "transacoes": 0, "categorias": {}}

    async def get_yearly_summary(self, year: int = None) -> Dict[str, Any]:
        """Obter resumo anual do banco SQLite"""
        try:
            if year is None:
                year = datetime.now().year

            async for db in get_db_session():
                result = await db.execute(
                    select(
                        Transaction.categoria,
                        func.sum(Transaction.valor).label('total'),
                        func.count(Transaction.id).label('count')
                    )
                    .where(
                        and_(
                            extract('year', Transaction.data_transacao) == year,
                            Transaction.status == 'processed'
                        )
                    )
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

                dados_mensais = []
                for month in range(1, 13):
                    resumo_mensal = await self.get_monthly_summary(month, year)
                    if resumo_mensal["transacoes"] > 0:
                        dados_mensais.append(resumo_mensal)

                return {
                    "periodo": "anual",
                    "ano": year,
                    "total_gastos": total_gastos,
                    "total_financas": total_financas,
                    "total_transacoes": total_transacoes,
                    "categorias_totais": categorias_totais,
                    "dados_mensais": dados_mensais
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
                    transactions.append({
                        "id": transaction.id,
                        "data": transaction.data_transacao.strftime("%d/%m/%Y"),
                        "descricao": transaction.descricao,
                        "categoria": transaction.categoria,
                        "valor": float(transaction.valor),
                        "observacoes": f"Confiança: {transaction.confianca:.0%}"
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
                    "periodo_dias": (dates.ultima - dates.primeira).days if dates.primeira and dates.ultima else 0
                }

        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {e}")
            return {}


database_service = DatabaseService()