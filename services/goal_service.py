"""
Serviço de gerenciamento de metas financeiras
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal
from sqlalchemy import select, and_, extract, func, delete
from loguru import logger
import unicodedata
import re
from collections import defaultdict

from database.sqlite_db import get_db_session
from database.models import Goal, Transaction
from models.schemas import (
    ExpenseCategory, GoalCreate, GoalResponse, GoalStatus,
    GoalAlert, AlertType
)


class GoalService:
    """Serviço para gerenciamento de metas financeiras"""
    
    # Cache de alertas enviados para evitar spam (categoria -> timestamp)
    _alert_cooldown: Dict[str, datetime] = {}
    
    # Cache em memória para metas ativas
    # Estrutura: {(user_id, mes, ano): {categoria: Goal}}
    _goals_cache: Dict[Tuple[int, int, int], Dict[str, Goal]] = {}
    _cache_timestamps: Dict[Tuple[int, int, int], datetime] = {}
    _cache_ttl_seconds: int = 300  # 5 minutos
    
    # Métricas de uso do sistema
    _metrics: Dict[str, Any] = {
        "goals_created": 0,
        "goals_updated": 0,
        "goals_deleted": 0,
        "goals_queried": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "alerts_sent": 0,
        "last_reset": datetime.now()
    }
    
    def normalize_category(self, input_text: str) -> Optional[ExpenseCategory]:
        """
        Normaliza texto de categoria para corresponder às categorias válidas.
        
        Args:
            input_text: Texto fornecido pelo usuário
            
        Returns:
            ExpenseCategory correspondente ou None se não encontrado
        """
        if not input_text:
            return None
        
        # 1. Remover acentos e caracteres especiais
        normalized = unicodedata.normalize('NFKD', input_text)
        normalized = ''.join([c for c in normalized if not unicodedata.combining(c)])
        
        # 2. Converter para lowercase
        normalized = normalized.lower().strip()
        
        # 3. Busca exata primeiro (case-insensitive)
        for category in ExpenseCategory:
            category_normalized = unicodedata.normalize('NFKD', category.value)
            category_normalized = ''.join([c for c in category_normalized if not unicodedata.combining(c)])
            category_normalized = category_normalized.lower()
            
            if normalized == category_normalized:
                return category
        
        # 4. Busca por substring (permite "aliment" para "Alimentação")
        # Apenas se o texto tiver pelo menos 3 caracteres
        if len(normalized) >= 3:
            for category in ExpenseCategory:
                category_normalized = unicodedata.normalize('NFKD', category.value)
                category_normalized = ''.join([c for c in category_normalized if not unicodedata.combining(c)])
                category_normalized = category_normalized.lower()
                
                if normalized in category_normalized or category_normalized in normalized:
                    return category
        
        # 5. Busca por similaridade (Levenshtein distance)
        # Apenas se o texto tiver pelo menos 3 caracteres
        if len(normalized) >= 3:
            best_match = None
            best_distance = float('inf')
            
            for category in ExpenseCategory:
                category_normalized = unicodedata.normalize('NFKD', category.value)
                category_normalized = ''.join([c for c in category_normalized if not unicodedata.combining(c)])
                category_normalized = category_normalized.lower()
                
                distance = self._levenshtein_distance(normalized, category_normalized)
                
                # Aceitar se a distância for menor que 30% do tamanho da string
                threshold = max(len(normalized), len(category_normalized)) * 0.3
                
                if distance < best_distance and distance <= threshold:
                    best_distance = distance
                    best_match = category
            
            return best_match
        
        return None
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calcula a distância de Levenshtein entre duas strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _get_cache_key(self, user_id: int, mes: int, ano: int) -> Tuple[int, int, int]:
        """Gera chave de cache para metas de um período"""
        return (user_id, mes, ano)
    
    def _is_cache_valid(self, cache_key: Tuple[int, int, int]) -> bool:
        """Verifica se o cache ainda é válido"""
        if cache_key not in self._cache_timestamps:
            return False
        
        age = (datetime.now() - self._cache_timestamps[cache_key]).total_seconds()
        return age < self._cache_ttl_seconds
    
    def _invalidate_cache(self, user_id: int, mes: int, ano: int):
        """Invalida cache para um período específico"""
        cache_key = self._get_cache_key(user_id, mes, ano)
        if cache_key in self._goals_cache:
            del self._goals_cache[cache_key]
        if cache_key in self._cache_timestamps:
            del self._cache_timestamps[cache_key]
        logger.debug(f"🗑️ Cache invalidado: user={user_id}, mes={mes}, ano={ano}")
    
    def _update_cache(self, user_id: int, mes: int, ano: int, goals: List[Goal]):
        """Atualiza cache com lista de metas"""
        cache_key = self._get_cache_key(user_id, mes, ano)
        self._goals_cache[cache_key] = {goal.categoria: goal for goal in goals}
        self._cache_timestamps[cache_key] = datetime.now()
        logger.debug(f"💾 Cache atualizado: user={user_id}, mes={mes}, ano={ano}, metas={len(goals)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas de uso do sistema de metas.
        
        Returns:
            Dicionário com métricas de uso
        """
        uptime = (datetime.now() - self._metrics["last_reset"]).total_seconds()
        cache_total = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        cache_hit_rate = (self._metrics["cache_hits"] / cache_total * 100) if cache_total > 0 else 0
        
        return {
            **self._metrics,
            "uptime_seconds": uptime,
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
            "cache_size": len(self._goals_cache),
            "active_cooldowns": len(self._alert_cooldown)
        }
    
    def reset_metrics(self):
        """Reseta as métricas de uso"""
        self._metrics = {
            "goals_created": 0,
            "goals_updated": 0,
            "goals_deleted": 0,
            "goals_queried": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "alerts_sent": 0,
            "last_reset": datetime.now()
        }
        logger.info("📊 Métricas resetadas")
    
    async def cleanup_old_goals(self, months_to_keep: int = 12) -> int:
        """
        Remove metas antigas do banco de dados (opcional).
        
        Args:
            months_to_keep: Número de meses de histórico a manter
            
        Returns:
            Número de metas removidas
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=months_to_keep * 30)
            cutoff_year = cutoff_date.year
            cutoff_month = cutoff_date.month
            
            logger.info(f"🧹 Iniciando limpeza de metas antigas (antes de {cutoff_month}/{cutoff_year})")
            
            async for db in get_db_session():
                # Contar metas que serão removidas
                count_result = await db.execute(
                    select(func.count(Goal.id)).where(
                        and_(
                            Goal.ano < cutoff_year,
                        ) | and_(
                            Goal.ano == cutoff_year,
                            Goal.mes < cutoff_month
                        )
                    )
                )
                count = count_result.scalar() or 0
                
                if count == 0:
                    logger.info("ℹ️ Nenhuma meta antiga para limpar")
                    return 0
                
                # Remover metas antigas
                await db.execute(
                    delete(Goal).where(
                        and_(
                            Goal.ano < cutoff_year,
                        ) | and_(
                            Goal.ano == cutoff_year,
                            Goal.mes < cutoff_month
                        )
                    )
                )
                await db.commit()
                
                logger.info(f"✅ {count} meta(s) antiga(s) removida(s)")
                
                # Limpar cache completo após limpeza
                self._goals_cache.clear()
                self._cache_timestamps.clear()
                
                return count
                
        except Exception as e:
            logger.error(f"❌ Erro ao limpar metas antigas: {e}", exc_info=True)
            return 0
    
    def validate_category(self, categoria: str) -> bool:
        """
        Valida se uma categoria existe na lista de categorias válidas.
        
        Args:
            categoria: Nome da categoria
            
        Returns:
            True se a categoria é válida, False caso contrário
        """
        try:
            # Tentar normalizar a categoria
            normalized = self.normalize_category(categoria)
            return normalized is not None
        except Exception as e:
            logger.error(f"Erro ao validar categoria: {e}")
            return False
    
    async def create_or_update_goal(
        self,
        user_id: int,
        categoria: ExpenseCategory,
        valor_meta: Decimal,
        mes: int,
        ano: int
    ) -> Goal:
        """
        Cria uma nova meta ou atualiza uma existente.
        
        Args:
            user_id: ID do usuário
            categoria: Categoria da meta
            valor_meta: Valor da meta mensal
            mes: Mês da meta (1-12)
            ano: Ano da meta
            
        Returns:
            Goal criada ou atualizada
            
        Raises:
            ValueError: Se os parâmetros forem inválidos
        """
        # Validações de entrada
        if not isinstance(user_id, int) or user_id <= 0:
            logger.error(f"❌ user_id inválido: {user_id}")
            raise ValueError(f"user_id deve ser um inteiro positivo: {user_id}")
        
        if not isinstance(categoria, ExpenseCategory):
            logger.error(f"❌ Categoria inválida: {categoria}")
            raise ValueError(f"categoria deve ser um ExpenseCategory: {categoria}")
        
        if not isinstance(valor_meta, Decimal) or valor_meta <= 0:
            logger.error(f"❌ valor_meta inválido: {valor_meta}")
            raise ValueError(f"valor_meta deve ser um Decimal positivo: {valor_meta}")
        
        if valor_meta.is_infinite() or valor_meta.is_nan():
            logger.error(f"❌ valor_meta especial inválido: {valor_meta}")
            raise ValueError(f"valor_meta não pode ser infinito ou NaN: {valor_meta}")
        
        if not (1 <= mes <= 12):
            logger.error(f"❌ Mês inválido: {mes}")
            raise ValueError(f"mes deve estar entre 1 e 12: {mes}")
        
        if not (2020 <= ano <= 2030):
            logger.error(f"❌ Ano inválido: {ano}")
            raise ValueError(f"ano deve estar entre 2020 e 2030: {ano}")
        
        try:
            async for db in get_db_session():
                # Verificar se já existe uma meta para esta combinação
                result = await db.execute(
                    select(Goal).where(
                        and_(
                            Goal.user_id == user_id,
                            Goal.categoria == categoria.value,
                            Goal.mes == mes,
                            Goal.ano == ano
                        )
                    )
                )
                existing_goal = result.scalar_one_or_none()
                
                if existing_goal:
                    # Atualizar meta existente
                    old_value = existing_goal.valor_meta
                    existing_goal.valor_meta = valor_meta
                    existing_goal.updated_at = datetime.now()
                    await db.commit()
                    await db.refresh(existing_goal)
                    
                    # Atualizar métricas e invalidar cache
                    self._metrics["goals_updated"] += 1
                    self._invalidate_cache(user_id, mes, ano)
                    
                    logger.info(
                        f"✅ Meta atualizada: user={user_id}, categoria={categoria.value}, "
                        f"valor_antigo=R$ {old_value}, valor_novo=R$ {valor_meta}, mes={mes}, ano={ano}"
                    )
                    return existing_goal
                else:
                    # Criar nova meta
                    new_goal = Goal(
                        user_id=user_id,
                        categoria=categoria.value,
                        valor_meta=valor_meta,
                        mes=mes,
                        ano=ano
                    )
                    db.add(new_goal)
                    await db.commit()
                    await db.refresh(new_goal)
                    
                    # Atualizar métricas e invalidar cache
                    self._metrics["goals_created"] += 1
                    self._invalidate_cache(user_id, mes, ano)
                    
                    logger.info(
                        f"✅ Meta criada: user={user_id}, categoria={categoria.value}, "
                        f"valor=R$ {valor_meta}, mes={mes}, ano={ano}"
                    )
                    return new_goal
                    
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(
                f"❌ Erro ao criar/atualizar meta: user={user_id}, categoria={categoria.value}, "
                f"valor={valor_meta}, mes={mes}, ano={ano} - {e}",
                exc_info=True
            )
            raise
    
    async def get_user_goals(
        self,
        user_id: int,
        mes: Optional[int] = None,
        ano: Optional[int] = None
    ) -> List[GoalResponse]:
        """
        Obtém todas as metas de um usuário para um período.
        
        Args:
            user_id: ID do usuário
            mes: Mês (opcional, usa mês atual se não fornecido)
            ano: Ano (opcional, usa ano atual se não fornecido)
            
        Returns:
            Lista de GoalResponse com progresso calculado
        """
        try:
            if mes is None or ano is None:
                now = datetime.now()
                mes = mes or now.month
                ano = ano or now.year
            
            # Atualizar métrica
            self._metrics["goals_queried"] += 1
            
            # Verificar cache
            cache_key = self._get_cache_key(user_id, mes, ano)
            if self._is_cache_valid(cache_key):
                self._metrics["cache_hits"] += 1
                goals = list(self._goals_cache[cache_key].values())
                logger.debug(f"💾 Cache hit: user={user_id}, mes={mes}, ano={ano}, metas={len(goals)}")
            else:
                self._metrics["cache_misses"] += 1
                
                async for db in get_db_session():
                    # Buscar todas as metas do usuário para o período
                    result = await db.execute(
                        select(Goal).where(
                            and_(
                                Goal.user_id == user_id,
                                Goal.mes == mes,
                                Goal.ano == ano
                            )
                        )
                    )
                    goals = result.scalars().all()
                    
                    # Atualizar cache
                    self._update_cache(user_id, mes, ano, goals)
            
            # Calcular progresso para cada meta
            goal_responses = []
            for goal in goals:
                progress = await self.get_goal_progress(
                    user_id, ExpenseCategory(goal.categoria), mes, ano
                )
                if progress:
                    goal_responses.append(progress)
            
            return goal_responses
                
        except Exception as e:
            logger.error(f"❌ Erro ao obter metas do usuário: {e}")
            return []
    
    async def get_goal_progress(
        self,
        user_id: int,
        categoria: ExpenseCategory,
        mes: int,
        ano: int
    ) -> Optional[GoalResponse]:
        """
        Calcula o progresso de uma meta específica.
        
        Args:
            user_id: ID do usuário
            categoria: Categoria da meta
            mes: Mês
            ano: Ano
            
        Returns:
            GoalResponse com progresso calculado ou None se não existir
        """
        try:
            # Verificar cache primeiro
            cache_key = self._get_cache_key(user_id, mes, ano)
            goal = None
            
            if self._is_cache_valid(cache_key):
                cached_goals = self._goals_cache.get(cache_key, {})
                goal = cached_goals.get(categoria.value)
                if goal:
                    self._metrics["cache_hits"] += 1
                    logger.debug(f"💾 Cache hit para meta: user={user_id}, categoria={categoria.value}")
            
            if not goal:
                self._metrics["cache_misses"] += 1
                
                async for db in get_db_session():
                    # Buscar a meta
                    goal_result = await db.execute(
                        select(Goal).where(
                            and_(
                                Goal.user_id == user_id,
                                Goal.categoria == categoria.value,
                                Goal.mes == mes,
                                Goal.ano == ano
                            )
                        )
                    )
                    goal = goal_result.scalar_one_or_none()
                    
                    if not goal:
                        return None
            
            # Calcular gastos do mês para a categoria (sempre busca do banco para dados atualizados)
            # NOTA: Não filtra por user_id pois o sistema é compartilhado entre usuários
            async for db in get_db_session():
                spending_result = await db.execute(
                    select(func.sum(Transaction.valor)).where(
                        and_(
                            Transaction.categoria == categoria.value,
                            extract('month', Transaction.data_transacao) == mes,
                            extract('year', Transaction.data_transacao) == ano,
                            Transaction.status == 'processed'
                        )
                    )
                )
                valor_gasto = spending_result.scalar() or Decimal('0')
                
                # Calcular percentual e status
                progresso_percentual = float((valor_gasto / goal.valor_meta) * 100) if goal.valor_meta > 0 else 0
                
                if progresso_percentual >= 100:
                    status = GoalStatus.LIMITE_EXCEDIDO
                elif progresso_percentual >= 80:
                    status = GoalStatus.PROXIMO_LIMITE
                else:
                    status = GoalStatus.DENTRO_META
                
                return GoalResponse(
                    id=goal.id,
                    categoria=categoria,
                    valor_meta=goal.valor_meta,
                    valor_gasto=valor_gasto,
                    progresso_percentual=progresso_percentual,
                    status=status,
                    mes=mes,
                    ano=ano
                )
                
        except Exception as e:
            logger.error(f"❌ Erro ao calcular progresso da meta: {e}")
            return None
    
    async def delete_goal(
        self,
        user_id: int,
        categoria: ExpenseCategory,
        mes: int,
        ano: int
    ) -> bool:
        """
        Remove uma meta específica.
        
        Args:
            user_id: ID do usuário
            categoria: Categoria da meta
            mes: Mês
            ano: Ano
            
        Returns:
            True se removida com sucesso, False caso contrário
        """
        try:
            logger.info(
                f"🗑️ Tentativa de remoção de meta: user={user_id}, categoria={categoria.value}, "
                f"mes={mes}, ano={ano}"
            )
            
            async for db in get_db_session():
                result = await db.execute(
                    select(Goal).where(
                        and_(
                            Goal.user_id == user_id,
                            Goal.categoria == categoria.value,
                            Goal.mes == mes,
                            Goal.ano == ano
                        )
                    )
                )
                goal = result.scalar_one_or_none()
                
                if goal:
                    valor_removido = goal.valor_meta
                    await db.delete(goal)
                    await db.commit()
                    
                    # Atualizar métricas e invalidar cache
                    self._metrics["goals_deleted"] += 1
                    self._invalidate_cache(user_id, mes, ano)
                    
                    logger.info(
                        f"✅ Meta removida com sucesso: user={user_id}, categoria={categoria.value}, "
                        f"valor=R$ {valor_removido}, mes={mes}, ano={ano}"
                    )
                    return True
                else:
                    logger.warning(
                        f"⚠️ Meta não encontrada para remoção: user={user_id}, categoria={categoria.value}, "
                        f"mes={mes}, ano={ano}"
                    )
                    return False
                    
        except Exception as e:
            logger.error(
                f"❌ Erro ao remover meta: user={user_id}, categoria={categoria.value}, "
                f"mes={mes}, ano={ano} - {e}",
                exc_info=True
            )
            return False
    
    async def clear_all_goals(self, user_id: int) -> int:
        """
        Remove todas as metas de um usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Número de metas removidas
        """
        try:
            logger.info(f"🧹 Tentativa de limpeza de todas as metas: user={user_id}")
            
            async for db in get_db_session():
                result = await db.execute(
                    select(Goal).where(Goal.user_id == user_id)
                )
                goals = result.scalars().all()
                
                count = len(goals)
                
                if count == 0:
                    logger.info(f"ℹ️ Nenhuma meta para limpar: user={user_id}")
                    return 0
                
                # Log das metas que serão removidas
                categorias_removidas = [goal.categoria for goal in goals]
                logger.info(f"🗑️ Removendo {count} meta(s): user={user_id}, categorias={categorias_removidas}")
                
                for goal in goals:
                    await db.delete(goal)
                
                await db.commit()
                
                # Atualizar métricas e limpar cache do usuário
                self._metrics["goals_deleted"] += count
                
                # Invalidar cache para todos os períodos do usuário
                keys_to_remove = [key for key in self._goals_cache.keys() if key[0] == user_id]
                for key in keys_to_remove:
                    del self._goals_cache[key]
                    if key in self._cache_timestamps:
                        del self._cache_timestamps[key]
                
                logger.info(f"✅ {count} meta(s) removida(s) com sucesso para usuário {user_id}")
                return count
                
        except Exception as e:
            logger.error(f"❌ Erro ao limpar todas as metas: user={user_id} - {e}", exc_info=True)
            return 0
    
    async def check_goal_alerts(
        self,
        user_id: int,
        categoria: ExpenseCategory,
        current_spending: Decimal
    ) -> Optional[GoalAlert]:
        """
        Verifica se deve enviar alertas para uma meta.
        
        Args:
            user_id: ID do usuário
            categoria: Categoria da meta
            current_spending: Valor atual gasto
            
        Returns:
            GoalAlert se deve enviar alerta, None caso contrário
        """
        try:
            now = datetime.now()
            mes = now.month
            ano = now.year
            
            # Buscar progresso da meta
            progress = await self.get_goal_progress(user_id, categoria, mes, ano)
            
            if not progress:
                return None
            
            # Verificar cooldown de alertas (máximo 1 por categoria por dia)
            cooldown_key = f"{user_id}_{categoria.value}_{mes}_{ano}"
            last_alert = self._alert_cooldown.get(cooldown_key)
            
            if last_alert:
                hours_since_last = (now - last_alert).total_seconds() / 3600
                if hours_since_last < 24:
                    return None  # Ainda em cooldown
            
            # Determinar tipo de alerta
            percentual = progress.progresso_percentual
            
            if percentual >= 100:
                alert_type = AlertType.EXCEEDED_100_PERCENT
            elif percentual >= 80:
                alert_type = AlertType.WARNING_80_PERCENT
            else:
                return None  # Não precisa de alerta
            
            # Registrar alerta enviado e atualizar métrica
            self._alert_cooldown[cooldown_key] = now
            self._metrics["alerts_sent"] += 1
            
            return GoalAlert(
                tipo=alert_type,
                categoria=categoria,
                valor_meta=progress.valor_meta,
                valor_atual=progress.valor_gasto,
                percentual=percentual
            )
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar alertas de meta: {e}")
            return None


# Instância global do serviço
goal_service = GoalService()
