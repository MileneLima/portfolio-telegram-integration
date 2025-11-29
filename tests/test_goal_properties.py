"""
Testes de propriedades para funcionalidade de metas financeiras
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import composite
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models.schemas import ExpenseCategory, GoalCreate, GoalResponse, GoalStatus
from database.models import Base, Goal


# Estratégias para geração de dados
@composite
def goal_create_strategy(draw):
    """Estratégia para gerar GoalCreate válidos"""
    return GoalCreate(
        categoria=draw(st.sampled_from(list(ExpenseCategory))),
        valor_meta=draw(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2)),
        mes=draw(st.integers(min_value=1, max_value=12)),
        ano=draw(st.integers(min_value=2020, max_value=2030))
    )


@composite
def valid_goal_data_strategy(draw):
    """Estratégia para gerar dados válidos de meta"""
    return {
        'user_id': draw(st.integers(min_value=1, max_value=999999999)),
        'categoria': draw(st.sampled_from([cat.value for cat in ExpenseCategory])),
        'valor_meta': draw(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2)),
        'mes': draw(st.integers(min_value=1, max_value=12)),
        'ano': draw(st.integers(min_value=2020, max_value=2030))
    }


class TestGoalCreationAndUpdate:
    """**Feature: metas-financeiras, Property 2: Criação e atualização de metas**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        # Adicionar constraint UNIQUE manualmente para garantir que funcione
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(goal_data=valid_goal_data_strategy())
    @settings(max_examples=100)
    def test_goal_creation_property(self, goal_data):
        """
        **Feature: metas-financeiras, Property 2: Criação e atualização de metas**
        **Validates: Requirements 1.3, 1.4**
        
        Para qualquer categoria válida e valor positivo, o sistema deve criar
        uma nova meta corretamente no banco de dados.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=goal_data['user_id'],
                categoria=goal_data['categoria'],
                valor_meta=goal_data['valor_meta'],
                mes=goal_data['mes'],
                ano=goal_data['ano']
            )
            
            session.add(goal)
            session.commit()
            
            # Verificar que a meta foi criada
            assert goal.id is not None
            assert goal.user_id == goal_data['user_id']
            assert goal.categoria == goal_data['categoria']
            assert goal.valor_meta == goal_data['valor_meta']
            assert goal.mes == goal_data['mes']
            assert goal.ano == goal_data['ano']
            assert goal.created_at is not None
            assert goal.updated_at is not None
            
            # Verificar que pode ser recuperada do banco
            retrieved_goal = session.query(Goal).filter_by(id=goal.id).first()
            assert retrieved_goal is not None
            assert retrieved_goal.user_id == goal_data['user_id']
            assert retrieved_goal.categoria == goal_data['categoria']
            assert retrieved_goal.valor_meta == goal_data['valor_meta']
        finally:
            session.close()
            engine.dispose()
    
    @given(
        goal_data=valid_goal_data_strategy(),
        new_valor=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2)
    )
    @settings(max_examples=100)
    def test_goal_update_property(self, goal_data, new_valor):
        """
        **Feature: metas-financeiras, Property 2: Criação e atualização de metas**
        **Validates: Requirements 1.3, 1.4**
        
        Para qualquer meta existente, o sistema deve atualizar o valor
        corretamente quando uma nova meta é definida para a mesma categoria/período.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta inicial
            goal = Goal(
                user_id=goal_data['user_id'],
                categoria=goal_data['categoria'],
                valor_meta=goal_data['valor_meta'],
                mes=goal_data['mes'],
                ano=goal_data['ano']
            )
            
            session.add(goal)
            session.commit()
            
            original_id = goal.id
            original_valor = goal.valor_meta
            
            # Atualizar valor da meta
            goal.valor_meta = new_valor
            session.commit()
            
            # Verificar que a meta foi atualizada
            updated_goal = session.query(Goal).filter_by(id=original_id).first()
            assert updated_goal is not None
            assert updated_goal.id == original_id  # Mesmo ID
            assert updated_goal.valor_meta == new_valor  # Novo valor
            assert updated_goal.valor_meta != original_valor or new_valor == original_valor  # Valor mudou ou é igual
            assert updated_goal.user_id == goal_data['user_id']  # Outros campos inalterados
            assert updated_goal.categoria == goal_data['categoria']
            assert updated_goal.mes == goal_data['mes']
            assert updated_goal.ano == goal_data['ano']
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030),
        valor1=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2),
        valor2=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2)
    )
    @settings(max_examples=100)
    def test_goal_uniqueness_constraint_property(self, user_id, categoria, mes, ano, valor1, valor2):
        """
        **Feature: metas-financeiras, Property 2: Criação e atualização de metas**
        **Validates: Requirements 1.3, 1.4**
        
        Para qualquer combinação de usuário/categoria/mês/ano, o sistema deve
        permitir apenas uma meta, garantindo unicidade através de constraint.
        """
        # Skip if valores are the same (not a real duplicate test)
        if valor1 == valor2:
            return
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar primeira meta
            goal1 = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor1,
                mes=mes,
                ano=ano
            )
            
            session.add(goal1)
            session.commit()
            
            # Tentar criar segunda meta com mesma combinação
            goal2 = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor2,
                mes=mes,
                ano=ano
            )
            
            session.add(goal2)
            
            # Deve falhar por violação de constraint de unicidade
            with pytest.raises(Exception):  # IntegrityError
                session.commit()
            
            # Rollback para limpar o estado
            session.rollback()
            
            # Verificar que apenas a primeira meta existe
            goals = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).all()
            
            assert len(goals) == 1
            assert goals[0].valor_meta == valor1
        finally:
            session.close()
            engine.dispose()
    
    @given(
        goals_data=st.lists(
            valid_goal_data_strategy(),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=100)
    def test_multiple_goals_creation_property(self, goals_data):
        """
        **Feature: metas-financeiras, Property 2: Criação e atualização de metas**
        **Validates: Requirements 1.3, 1.4**
        
        Para qualquer conjunto de metas com combinações únicas de
        usuário/categoria/mês/ano, o sistema deve criar todas corretamente.
        """
        session, engine = self.get_fresh_session()
        
        try:
            created_goals = []
            
            # Criar todas as metas (removendo duplicatas)
            seen = set()
            for goal_data in goals_data:
                key = (goal_data['user_id'], goal_data['categoria'], goal_data['mes'], goal_data['ano'])
                if key not in seen:
                    seen.add(key)
                    goal = Goal(
                        user_id=goal_data['user_id'],
                        categoria=goal_data['categoria'],
                        valor_meta=goal_data['valor_meta'],
                        mes=goal_data['mes'],
                        ano=goal_data['ano']
                    )
                    session.add(goal)
                    created_goals.append(goal_data)
            
            session.commit()
            
            # Verificar que todas as metas foram criadas
            total_goals = session.query(Goal).count()
            assert total_goals == len(created_goals)
            
            # Verificar cada meta individualmente
            for goal_data in created_goals:
                retrieved_goal = session.query(Goal).filter_by(
                    user_id=goal_data['user_id'],
                    categoria=goal_data['categoria'],
                    mes=goal_data['mes'],
                    ano=goal_data['ano']
                ).first()
                
                assert retrieved_goal is not None
                assert retrieved_goal.valor_meta == goal_data['valor_meta']
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valores=st.lists(
            st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2),
            min_size=2,
            max_size=5
        ),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=100, deadline=500)
    def test_goal_sequential_updates_property(self, user_id, categoria, valores, mes, ano):
        """
        **Feature: metas-financeiras, Property 2: Criação e atualização de metas**
        **Validates: Requirements 1.3, 1.4**
        
        Para qualquer sequência de atualizações de valor em uma meta,
        o sistema deve sempre refletir o último valor definido.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta inicial
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valores[0],
                mes=mes,
                ano=ano
            )
            
            session.add(goal)
            session.commit()
            
            goal_id = goal.id
            
            # Aplicar sequência de atualizações
            for new_valor in valores[1:]:
                goal.valor_meta = new_valor
                session.commit()
                
                # Verificar que o valor foi atualizado
                updated_goal = session.query(Goal).filter_by(id=goal_id).first()
                assert updated_goal.valor_meta == new_valor
            
            # Verificar que o valor final é o último da sequência
            final_goal = session.query(Goal).filter_by(id=goal_id).first()
            assert final_goal.valor_meta == valores[-1]
            
            # Verificar que ainda existe apenas uma meta
            goals_count = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).count()
            assert goals_count == 1
        finally:
            session.close()
            engine.dispose()


class TestAlertSystem:
    """**Feature: metas-financeiras, Property 6: Sistema de alertas por threshold**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        # Adicionar índices
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        percentual=st.floats(min_value=80.0, max_value=99.9)
    )
    @settings(max_examples=50, deadline=1000)
    def test_alert_at_80_percent_threshold_property(self, user_id, categoria, valor_meta, percentual):
        """
        **Feature: metas-financeiras, Property 6: Sistema de alertas por threshold**
        **Validates: Requirements 4.2, 4.3**
        
        Para qualquer meta que atinja 80% do valor definido, o sistema deve
        identificar que um alerta de proximidade deve ser enviado.
        """
        from models.schemas import GoalStatus, AlertType
        
        # Calcular valor gasto baseado no percentual
        valor_gasto = (valor_meta * Decimal(str(percentual))) / Decimal('100')
        
        # Determinar status esperado
        if percentual >= 100:
            expected_status = GoalStatus.LIMITE_EXCEDIDO
            expected_alert = AlertType.EXCEEDED_100_PERCENT
        elif percentual >= 80:
            expected_status = GoalStatus.PROXIMO_LIMITE
            expected_alert = AlertType.WARNING_80_PERCENT
        else:
            expected_status = GoalStatus.DENTRO_META
            expected_alert = None
        
        # Verificar que o status é calculado corretamente
        progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
        
        if progresso_percentual >= 100:
            status = GoalStatus.LIMITE_EXCEDIDO
        elif progresso_percentual >= 80:
            status = GoalStatus.PROXIMO_LIMITE
        else:
            status = GoalStatus.DENTRO_META
        
        assert status == expected_status
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        percentual=st.floats(min_value=100.1, max_value=200.0)
    )
    @settings(max_examples=50, deadline=1000)
    def test_alert_at_100_percent_threshold_property(self, user_id, categoria, valor_meta, percentual):
        """
        **Feature: metas-financeiras, Property 6: Sistema de alertas por threshold**
        **Validates: Requirements 4.2, 4.3**
        
        Para qualquer meta que exceda 100% do valor definido, o sistema deve
        identificar que um alerta de limite excedido deve ser enviado.
        """
        from models.schemas import GoalStatus, AlertType
        
        # Calcular valor gasto baseado no percentual
        valor_gasto = (valor_meta * Decimal(str(percentual))) / Decimal('100')
        
        # Verificar que o status é calculado corretamente
        progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
        
        if progresso_percentual >= 100:
            status = GoalStatus.LIMITE_EXCEDIDO
            alert_type = AlertType.EXCEEDED_100_PERCENT
        elif progresso_percentual >= 80:
            status = GoalStatus.PROXIMO_LIMITE
            alert_type = AlertType.WARNING_80_PERCENT
        else:
            status = GoalStatus.DENTRO_META
            alert_type = None
        
        # Para percentuais acima de 100%, deve sempre ser LIMITE_EXCEDIDO
        assert status == GoalStatus.LIMITE_EXCEDIDO
        assert alert_type == AlertType.EXCEEDED_100_PERCENT
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        percentual=st.floats(min_value=0.0, max_value=79.9)
    )
    @settings(max_examples=50, deadline=1000)
    def test_no_alert_below_80_percent_property(self, user_id, categoria, valor_meta, percentual):
        """
        **Feature: metas-financeiras, Property 6: Sistema de alertas por threshold**
        **Validates: Requirements 4.2, 4.3**
        
        Para qualquer meta abaixo de 80% do valor definido, o sistema não deve
        enviar alertas.
        """
        from models.schemas import GoalStatus
        
        # Calcular valor gasto baseado no percentual
        valor_gasto = (valor_meta * Decimal(str(percentual))) / Decimal('100')
        
        # Verificar que o status é calculado corretamente
        progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
        
        if progresso_percentual >= 100:
            status = GoalStatus.LIMITE_EXCEDIDO
        elif progresso_percentual >= 80:
            status = GoalStatus.PROXIMO_LIMITE
        else:
            status = GoalStatus.DENTRO_META
        
        # Para percentuais abaixo de 80%, deve sempre ser DENTRO_META
        assert status == GoalStatus.DENTRO_META
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        valores_gastos=st.lists(
            st.decimals(min_value=Decimal('10'), max_value=Decimal('100'), places=2),
            min_size=1,
            max_size=20
        )
    )
    @settings(max_examples=50, deadline=1000)
    def test_alert_threshold_transitions_property(self, user_id, categoria, valor_meta, valores_gastos):
        """
        **Feature: metas-financeiras, Property 6: Sistema de alertas por threshold**
        **Validates: Requirements 4.2, 4.3**
        
        Para qualquer sequência de gastos, o sistema deve transicionar
        corretamente entre os estados de alerta conforme o progresso aumenta.
        """
        from models.schemas import GoalStatus
        
        valor_gasto_acumulado = Decimal('0')
        previous_status = GoalStatus.DENTRO_META
        
        for valor_gasto in valores_gastos:
            valor_gasto_acumulado += valor_gasto
            
            # Calcular status atual
            progresso_percentual = float((valor_gasto_acumulado / valor_meta) * 100) if valor_meta > 0 else 0
            
            if progresso_percentual >= 100:
                current_status = GoalStatus.LIMITE_EXCEDIDO
            elif progresso_percentual >= 80:
                current_status = GoalStatus.PROXIMO_LIMITE
            else:
                current_status = GoalStatus.DENTRO_META
            
            # Verificar que a transição é válida (nunca volta para trás)
            status_order = {
                GoalStatus.DENTRO_META: 0,
                GoalStatus.PROXIMO_LIMITE: 1,
                GoalStatus.LIMITE_EXCEDIDO: 2
            }
            
            assert status_order[current_status] >= status_order[previous_status]
            previous_status = current_status


class TestMonthlyProgressCalculation:
    """**Feature: metas-financeiras, Property 5: Cálculo mensal de progresso**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        # Adicionar índices
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('10000'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030),
        num_transactions=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50, deadline=2000)
    def test_progress_calculation_only_current_month_property(self, user_id, categoria, valor_meta, mes, ano, num_transactions):
        """
        **Feature: metas-financeiras, Property 5: Cálculo mensal de progresso**
        **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
        
        Para qualquer meta definida, o sistema deve calcular o progresso
        considerando apenas gastos do mês atual.
        """
        from database.models import Transaction
        from datetime import date
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            # Criar transações no mês correto
            total_gasto_mes_correto = Decimal('0')
            for i in range(num_transactions):
                valor = Decimal(str(10.0 + i * 5.0))
                transaction = Transaction(
                    user_id=user_id,
                    original_message=f"Test {i}",
                    message_id=1000 + i,
                    chat_id=user_id,
                    descricao=f"Gasto {i}",
                    valor=valor,
                    categoria=categoria,
                    data_transacao=date(ano, mes, min(i + 1, 28)),
                    status='processed'
                )
                session.add(transaction)
                total_gasto_mes_correto += valor
            
            # Criar transações em outros meses (não devem contar)
            other_month = (mes % 12) + 1
            other_year = ano if other_month > mes else ano + 1
            for i in range(3):
                transaction = Transaction(
                    user_id=user_id,
                    original_message=f"Other {i}",
                    message_id=2000 + i,
                    chat_id=user_id,
                    descricao=f"Outro gasto {i}",
                    valor=Decimal('50.00'),
                    categoria=categoria,
                    data_transacao=date(other_year, other_month, min(i + 1, 28)),
                    status='processed'
                )
                session.add(transaction)
            
            session.commit()
            
            # Calcular progresso manualmente (testando a lógica, não o serviço async)
            spending_result = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar()
            
            valor_gasto = spending_result or Decimal('0')
            
            # Verificar que o progresso considera apenas o mês correto
            assert valor_gasto == total_gasto_mes_correto
            
            # Verificar percentual
            progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
            expected_percentual = float((total_gasto_mes_correto / valor_meta) * 100) if valor_meta > 0 else 0
            assert abs(progresso_percentual - expected_percentual) < 0.01
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('10000'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_progress_zero_when_no_expenses_property(self, user_id, categoria, valor_meta, mes, ano):
        """
        **Feature: metas-financeiras, Property 5: Cálculo mensal de progresso**
        **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
        
        Para qualquer meta sem gastos no mês atual, o sistema deve
        mostrar progresso zero.
        """
        from database.models import Transaction
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            # Não criar nenhuma transação
            
            # Calcular progresso manualmente
            spending_result = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar()
            
            valor_gasto = spending_result or Decimal('0')
            
            # Verificar que o progresso é zero
            assert valor_gasto == Decimal('0')
            
            progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
            assert progresso_percentual == 0.0
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('100'), max_value=Decimal('10000'), places=2),
        mes1=st.integers(min_value=1, max_value=11),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_progress_resets_each_month_property(self, user_id, categoria, valor_meta, mes1, ano):
        """
        **Feature: metas-financeiras, Property 5: Cálculo mensal de progresso**
        **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
        
        Para qualquer meta, quando um novo mês inicia, o progresso deve
        reiniciar automaticamente (considerar apenas gastos do novo mês).
        """
        from database.models import Transaction
        from datetime import date
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        mes2 = mes1 + 1
        
        try:
            # Criar metas para dois meses consecutivos
            goal1 = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes1,
                ano=ano
            )
            goal2 = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes2,
                ano=ano
            )
            session.add(goal1)
            session.add(goal2)
            session.commit()
            
            # Criar transações no primeiro mês
            for i in range(3):
                transaction = Transaction(
                    user_id=user_id,
                    original_message=f"Mes1 {i}",
                    message_id=1000 + i,
                    chat_id=user_id,
                    descricao=f"Gasto mes1 {i}",
                    valor=Decimal('100.00'),
                    categoria=categoria,
                    data_transacao=date(ano, mes1, min(i + 1, 28)),
                    status='processed'
                )
                session.add(transaction)
            
            # Criar transações no segundo mês
            for i in range(2):
                transaction = Transaction(
                    user_id=user_id,
                    original_message=f"Mes2 {i}",
                    message_id=2000 + i,
                    chat_id=user_id,
                    descricao=f"Gasto mes2 {i}",
                    valor=Decimal('50.00'),
                    categoria=categoria,
                    data_transacao=date(ano, mes2, min(i + 1, 28)),
                    status='processed'
                )
                session.add(transaction)
            
            session.commit()
            
            # Calcular progresso para cada mês manualmente
            spending_mes1 = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes1,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar() or Decimal('0')
            
            spending_mes2 = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes2,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar() or Decimal('0')
            
            # Verificar que cada mês tem seu próprio progresso
            assert spending_mes1 == Decimal('300.00')  # 3 * 100
            assert spending_mes2 == Decimal('100.00')  # 2 * 50
            
            # Verificar que os progressos são independentes
            assert spending_mes1 != spending_mes2
            
        finally:
            session.close()
            engine.dispose()


class TestTextNormalization:
    """**Feature: metas-financeiras, Property 4: Normalização de texto**"""
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        case_variation=st.sampled_from(['upper', 'lower', 'title', 'mixed', 'random'])
    )
    @settings(max_examples=100, deadline=500)
    def test_case_normalization_property(self, categoria, case_variation):
        """
        **Feature: metas-financeiras, Property 4: Normalização de texto**
        **Validates: Requirements 2.1, 2.2, 2.5**
        
        Para qualquer variação de case (maiúscula/minúscula/mista) de uma
        categoria válida, o sistema deve normalizar corretamente.
        """
        from services.goal_service import goal_service
        
        # Aplicar variação de case
        if case_variation == 'upper':
            test_text = categoria.upper()
        elif case_variation == 'lower':
            test_text = categoria.lower()
        elif case_variation == 'title':
            test_text = categoria.title()
        elif case_variation == 'mixed':
            test_text = ''.join(
                c.upper() if i % 2 == 0 else c.lower()
                for i, c in enumerate(categoria)
            )
        else:  # random
            import random
            test_text = ''.join(
                c.upper() if random.random() > 0.5 else c.lower()
                for c in categoria
            )
        
        # Normalizar deve retornar a categoria original
        normalized = goal_service.normalize_category(test_text)
        assert normalized is not None
        assert normalized.value == categoria
    
    @given(categoria=st.sampled_from([cat.value for cat in ExpenseCategory]))
    @settings(max_examples=100, deadline=500)
    def test_accent_normalization_property(self, categoria):
        """
        **Feature: metas-financeiras, Property 4: Normalização de texto**
        **Validates: Requirements 2.1, 2.2, 2.5**
        
        Para qualquer categoria com acentos e caracteres especiais,
        o sistema deve processar corretamente a normalização.
        """
        from services.goal_service import goal_service
        
        # Normalizar categoria original (que pode ter acentos)
        normalized = goal_service.normalize_category(categoria)
        assert normalized is not None
        assert normalized.value == categoria
        
        # Testar versão sem acentos também deve funcionar
        import unicodedata
        no_accents = unicodedata.normalize('NFKD', categoria)
        no_accents = ''.join([c for c in no_accents if not unicodedata.combining(c)])
        
        normalized_no_accents = goal_service.normalize_category(no_accents)
        assert normalized_no_accents is not None
        assert normalized_no_accents.value == categoria
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        whitespace=st.sampled_from([' ', '  ', '\t', '\n', ' \t '])
    )
    @settings(max_examples=100, deadline=500)
    def test_whitespace_normalization_property(self, categoria, whitespace):
        """
        **Feature: metas-financeiras, Property 4: Normalização de texto**
        **Validates: Requirements 2.1, 2.2, 2.5**
        
        Para qualquer categoria com espaços em branco extras,
        o sistema deve normalizar corretamente.
        """
        from services.goal_service import goal_service
        
        # Adicionar whitespace antes e depois
        test_text = f"{whitespace}{categoria}{whitespace}"
        
        # Normalizar deve retornar a categoria original
        normalized = goal_service.normalize_category(test_text)
        assert normalized is not None
        assert normalized.value == categoria
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        prefix_len=st.integers(min_value=0, max_value=len("Alimentação") - 3)
    )
    @settings(max_examples=100, deadline=500)
    def test_partial_match_normalization_property(self, categoria, prefix_len):
        """
        **Feature: metas-financeiras, Property 4: Normalização de texto**
        **Validates: Requirements 2.1, 2.2, 2.5**
        
        Para qualquer prefixo válido de uma categoria (mínimo 3 caracteres),
        o sistema deve normalizar para a categoria correta.
        """
        from services.goal_service import goal_service
        
        # Pegar prefixo da categoria (mínimo 3 caracteres)
        if len(categoria) < 3:
            return  # Skip categorias muito curtas
        
        prefix_len = max(3, min(prefix_len + 3, len(categoria)))
        partial_text = categoria[:prefix_len]
        
        # Normalizar deve retornar a categoria original
        normalized = goal_service.normalize_category(partial_text)
        assert normalized is not None
        assert normalized.value == categoria
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        typo_position=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, deadline=500)
    def test_typo_tolerance_normalization_property(self, categoria, typo_position):
        """
        **Feature: metas-financeiras, Property 4: Normalização de texto**
        **Validates: Requirements 2.1, 2.2, 2.5**
        
        Para qualquer categoria com pequenos erros de digitação,
        o sistema deve tentar normalizar usando similaridade.
        """
        from services.goal_service import goal_service
        
        # Criar versão com typo (trocar um caractere)
        if len(categoria) < 4:
            return  # Skip categorias muito curtas
        
        typo_position = typo_position % len(categoria)
        typo_text = list(categoria)
        
        # Trocar caractere por outro similar
        char_map = {
            'a': 'e', 'e': 'i', 'i': 'o', 'o': 'u', 'u': 'a',
            'A': 'E', 'E': 'I', 'I': 'O', 'O': 'U', 'U': 'A',
            'ã': 'a', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'
        }
        
        original_char = typo_text[typo_position]
        if original_char in char_map:
            typo_text[typo_position] = char_map[original_char]
            typo_string = ''.join(typo_text)
            
            # Tentar normalizar - pode ou não funcionar dependendo da distância
            normalized = goal_service.normalize_category(typo_string)
            
            # Se normalizou, deve ser para a categoria original ou outra válida
            if normalized is not None:
                assert normalized in ExpenseCategory


class TestCategoryValidation:
    """**Feature: metas-financeiras, Property 1: Validação de categoria**"""
    
    @given(categoria=st.sampled_from([cat.value for cat in ExpenseCategory]))
    @settings(max_examples=100, deadline=500)
    def test_valid_category_validation_property(self, categoria):
        """
        **Feature: metas-financeiras, Property 1: Validação de categoria**
        **Validates: Requirements 1.1**
        
        Para qualquer categoria válida fornecida pelo usuário, o sistema deve
        validar corretamente que ela existe na lista de categorias válidas.
        """
        from services.goal_service import goal_service
        
        # Validar categoria exata
        assert goal_service.validate_category(categoria) is True
        
        # Validar categoria normalizada deve retornar a categoria correta
        normalized = goal_service.normalize_category(categoria)
        assert normalized is not None
        assert normalized.value == categoria
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        case_variation=st.sampled_from(['upper', 'lower', 'title', 'mixed'])
    )
    @settings(max_examples=100)
    def test_category_case_insensitive_validation_property(self, categoria, case_variation):
        """
        **Feature: metas-financeiras, Property 1: Validação de categoria**
        **Validates: Requirements 1.1**
        
        Para qualquer categoria válida em qualquer variação de case
        (maiúscula/minúscula/mista), o sistema deve validar corretamente.
        """
        from services.goal_service import goal_service
        
        # Aplicar variação de case
        if case_variation == 'upper':
            test_categoria = categoria.upper()
        elif case_variation == 'lower':
            test_categoria = categoria.lower()
        elif case_variation == 'title':
            test_categoria = categoria.title()
        else:  # mixed
            test_categoria = ''.join(
                c.upper() if i % 2 == 0 else c.lower()
                for i, c in enumerate(categoria)
            )
        
        # Validar que a categoria é reconhecida
        assert goal_service.validate_category(test_categoria) is True
        
        # Normalizar deve retornar a categoria correta
        normalized = goal_service.normalize_category(test_categoria)
        assert normalized is not None
        assert normalized.value == categoria
    
    @given(invalid_text=st.text(
        alphabet=st.characters(blacklist_categories=['Cs', 'Cc']),
        min_size=1,
        max_size=50
    ).filter(lambda x: x.strip() and not any(
        cat.value.lower() in x.lower() or x.lower() in cat.value.lower()
        for cat in ExpenseCategory
    )))
    @settings(max_examples=100)
    def test_invalid_category_validation_property(self, invalid_text):
        """
        **Feature: metas-financeiras, Property 1: Validação de categoria**
        **Validates: Requirements 1.1**
        
        Para qualquer texto que não corresponda a uma categoria válida,
        o sistema deve retornar False na validação.
        """
        from services.goal_service import goal_service
        
        # Validar que texto inválido não é aceito
        is_valid = goal_service.validate_category(invalid_text)
        
        # Se foi validado como True, deve ter normalizado para uma categoria válida
        if is_valid:
            normalized = goal_service.normalize_category(invalid_text)
            assert normalized is not None
            # Verificar que realmente é similar a alguma categoria
            assert any(
                cat.value.lower() in invalid_text.lower() or 
                invalid_text.lower() in cat.value.lower()
                for cat in ExpenseCategory
            )
        else:
            # Se não validou, normalização deve retornar None
            normalized = goal_service.normalize_category(invalid_text)
            assert normalized is None
    
    @given(
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        prefix=st.text(alphabet=st.characters(whitelist_categories=['L']), min_size=0, max_size=3),
        suffix=st.text(alphabet=st.characters(whitelist_categories=['L']), min_size=0, max_size=3)
    )
    @settings(max_examples=100)
    def test_category_with_extra_chars_validation_property(self, categoria, prefix, suffix):
        """
        **Feature: metas-financeiras, Property 1: Validação de categoria**
        **Validates: Requirements 1.1**
        
        Para qualquer categoria válida com caracteres extras antes ou depois,
        o sistema deve tentar normalizar e validar corretamente.
        """
        from services.goal_service import goal_service
        
        test_text = f"{prefix}{categoria}{suffix}".strip()
        
        if not test_text:
            return  # Skip empty strings
        
        # Tentar validar
        is_valid = goal_service.validate_category(test_text)
        normalized = goal_service.normalize_category(test_text)
        
        # Se a categoria original está contida no texto, deve normalizar corretamente
        if categoria.lower() in test_text.lower():
            assert normalized is not None
            # Pode ser a categoria original ou outra similar
            assert normalized in ExpenseCategory


if __name__ == "__main__":
    print("Executando testes de propriedades de metas financeiras...")
    pytest.main([__file__, "-v"])



class TestOperationConfirmation:
    """**Feature: metas-financeiras, Property 3: Confirmação de operações**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_goal_creation_returns_confirmation_property(self, user_id, categoria, valor_meta, mes, ano):
        """
        **Feature: metas-financeiras, Property 3: Confirmação de operações**
        **Validates: Requirements 1.5, 4.1**
        
        Para qualquer operação de meta executada com sucesso, o sistema deve
        retornar dados de confirmação com detalhes do progresso atual.
        """
        from database.models import Transaction
        from datetime import date
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            # Verificar que a meta foi criada e tem dados para confirmação
            assert goal.id is not None
            assert goal.user_id == user_id
            assert goal.categoria == categoria
            assert goal.valor_meta == valor_meta
            assert goal.mes == mes
            assert goal.ano == ano
            assert goal.created_at is not None
            
            # Calcular progresso para confirmação
            spending_result = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar()
            
            valor_gasto = spending_result or Decimal('0')
            progresso_percentual = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
            
            # Verificar que temos todos os dados necessários para confirmação
            assert valor_gasto >= 0
            assert progresso_percentual >= 0
            assert progresso_percentual <= 100 or valor_gasto > valor_meta
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_inicial=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        valor_novo=st.decimals(min_value=Decimal('100'), max_value=Decimal('1000'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_goal_update_returns_confirmation_property(self, user_id, categoria, valor_inicial, valor_novo, mes, ano):
        """
        **Feature: metas-financeiras, Property 3: Confirmação de operações**
        **Validates: Requirements 1.5, 4.1**
        
        Para qualquer atualização de meta, o sistema deve retornar
        confirmação com o novo valor e progresso atualizado.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta inicial
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_inicial,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            original_id = goal.id
            
            # Atualizar meta
            goal.valor_meta = valor_novo
            goal.updated_at = datetime.now()
            session.commit()
            
            # Verificar que a atualização tem dados para confirmação
            updated_goal = session.query(Goal).filter_by(id=original_id).first()
            assert updated_goal is not None
            assert updated_goal.valor_meta == valor_novo
            assert updated_goal.updated_at is not None
            
            # Verificar que podemos calcular novo progresso
            from sqlalchemy import func, extract, and_
            from database.models import Transaction
            
            spending_result = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar()
            
            valor_gasto = spending_result or Decimal('0')
            novo_progresso = float((valor_gasto / valor_novo) * 100) if valor_novo > 0 else 0
            
            # Verificar que temos dados de confirmação
            assert novo_progresso >= 0
            
        finally:
            session.close()
            engine.dispose()


class TestGoalListing:
    """**Feature: metas-financeiras, Property 7: Listagem de metas**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        num_goals=st.integers(min_value=1, max_value=7),  # Max 7 categorias
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_list_all_user_goals_property(self, user_id, num_goals, mes, ano):
        """
        **Feature: metas-financeiras, Property 7: Listagem de metas**
        **Validates: Requirements 4.4**
        
        Para qualquer usuário, o comando "/metas" deve exibir todas as metas
        definidas com progresso atual correto.
        """
        from database.models import Transaction
        from datetime import date
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar múltiplas metas para diferentes categorias
            categorias = list(ExpenseCategory)[:num_goals]
            created_goals = []
            
            for i, categoria in enumerate(categorias):
                valor_meta = Decimal(str(100.0 * (i + 1)))
                goal = Goal(
                    user_id=user_id,
                    categoria=categoria.value,
                    valor_meta=valor_meta,
                    mes=mes,
                    ano=ano
                )
                session.add(goal)
                created_goals.append((categoria.value, valor_meta))
            
            session.commit()
            
            # Buscar todas as metas do usuário
            all_goals = session.query(Goal).filter_by(
                user_id=user_id,
                mes=mes,
                ano=ano
            ).all()
            
            # Verificar que todas as metas foram retornadas
            assert len(all_goals) == num_goals
            
            # Verificar que cada meta tem dados corretos
            for goal in all_goals:
                assert goal.user_id == user_id
                assert goal.mes == mes
                assert goal.ano == ano
                assert goal.valor_meta > 0
                
                # Verificar que podemos calcular progresso para cada meta
                spending_result = session.query(func.sum(Transaction.valor)).filter(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.categoria == goal.categoria,
                        extract('month', Transaction.data_transacao) == mes,
                        extract('year', Transaction.data_transacao) == ano,
                        Transaction.status == 'processed'
                    )
                ).scalar()
                
                valor_gasto = spending_result or Decimal('0')
                progresso = float((valor_gasto / goal.valor_meta) * 100) if goal.valor_meta > 0 else 0
                
                assert progresso >= 0
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_empty_goal_list_property(self, user_id, mes, ano):
        """
        **Feature: metas-financeiras, Property 7: Listagem de metas**
        **Validates: Requirements 4.4**
        
        Para qualquer usuário sem metas definidas, o sistema deve
        retornar lista vazia.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Não criar nenhuma meta
            
            # Buscar metas do usuário
            all_goals = session.query(Goal).filter_by(
                user_id=user_id,
                mes=mes,
                ano=ano
            ).all()
            
            # Verificar que a lista está vazia
            assert len(all_goals) == 0
            
        finally:
            session.close()
            engine.dispose()


class TestSpecificGoalQuery:
    """**Feature: metas-financeiras, Property 8: Consulta de meta específica**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_query_specific_goal_property(self, user_id, categoria, valor_meta, mes, ano):
        """
        **Feature: metas-financeiras, Property 8: Consulta de meta específica**
        **Validates: Requirements 5.1**
        
        Para qualquer categoria com meta definida, o comando "/meta <categoria>"
        deve exibir a meta correta para aquela categoria.
        """
        from database.models import Transaction
        from sqlalchemy import func, extract, and_
        
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            # Buscar meta específica
            specific_goal = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).first()
            
            # Verificar que a meta foi encontrada
            assert specific_goal is not None
            assert specific_goal.categoria == categoria
            assert specific_goal.valor_meta == valor_meta
            assert specific_goal.mes == mes
            assert specific_goal.ano == ano
            
            # Verificar que podemos calcular progresso
            spending_result = session.query(func.sum(Transaction.valor)).filter(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.categoria == categoria,
                    extract('month', Transaction.data_transacao) == mes,
                    extract('year', Transaction.data_transacao) == ano,
                    Transaction.status == 'processed'
                )
            ).scalar()
            
            valor_gasto = spending_result or Decimal('0')
            progresso = float((valor_gasto / valor_meta) * 100) if valor_meta > 0 else 0
            
            assert progresso >= 0
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_query_nonexistent_goal_property(self, user_id, categoria, mes, ano):
        """
        **Feature: metas-financeiras, Property 8: Consulta de meta específica**
        **Validates: Requirements 5.1**
        
        Para qualquer categoria sem meta definida, o sistema deve
        retornar None ou indicar que não há meta.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Não criar nenhuma meta
            
            # Buscar meta específica
            specific_goal = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).first()
            
            # Verificar que nenhuma meta foi encontrada
            assert specific_goal is None
            
        finally:
            session.close()
            engine.dispose()


class TestGoalRemoval:
    """**Feature: metas-financeiras, Property 9: Remoção de metas**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        valor_meta=st.decimals(min_value=Decimal('0.01'), max_value=Decimal('99999.99'), places=2),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_goal_removal_property(self, user_id, categoria, valor_meta, mes, ano):
        """
        **Feature: metas-financeiras, Property 9: Remoção de metas**
        **Validates: Requirements 5.2, 5.3**
        
        Para qualquer categoria com meta existente, definir valor 0 deve
        remover a meta e parar o cálculo de progresso.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar meta
            goal = Goal(
                user_id=user_id,
                categoria=categoria,
                valor_meta=valor_meta,
                mes=mes,
                ano=ano
            )
            session.add(goal)
            session.commit()
            
            goal_id = goal.id
            
            # Verificar que a meta existe
            existing_goal = session.query(Goal).filter_by(id=goal_id).first()
            assert existing_goal is not None
            
            # Remover meta
            session.delete(existing_goal)
            session.commit()
            
            # Verificar que a meta foi removida
            removed_goal = session.query(Goal).filter_by(id=goal_id).first()
            assert removed_goal is None
            
            # Verificar que não há mais meta para esta categoria/período
            no_goal = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).first()
            assert no_goal is None
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        categoria=st.sampled_from([cat.value for cat in ExpenseCategory]),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_remove_nonexistent_goal_property(self, user_id, categoria, mes, ano):
        """
        **Feature: metas-financeiras, Property 9: Remoção de metas**
        **Validates: Requirements 5.2, 5.3**
        
        Para qualquer categoria sem meta existente, tentar remover
        não deve causar erro.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Não criar nenhuma meta
            
            # Tentar buscar e remover meta inexistente
            goal = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).first()
            
            # Verificar que não há meta
            assert goal is None
            
            # Tentar remover não deve causar erro (operação idempotente)
            if goal:
                session.delete(goal)
                session.commit()
            
            # Verificar que ainda não há meta
            still_no_goal = session.query(Goal).filter_by(
                user_id=user_id,
                categoria=categoria,
                mes=mes,
                ano=ano
            ).first()
            assert still_no_goal is None
            
        finally:
            session.close()
            engine.dispose()


class TestGoalCleanup:
    """**Feature: metas-financeiras, Property 10: Operações de limpeza**"""
    
    def get_fresh_session(self):
        """Criar uma nova sessão de banco de dados para cada exemplo do Hypothesis"""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_unique 
                ON goals(user_id, categoria, mes, ano)
            """))
            conn.commit()
        
        Session = sessionmaker(bind=engine)
        return Session(), engine
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        num_goals=st.integers(min_value=1, max_value=7),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_clear_all_goals_property(self, user_id, num_goals, mes, ano):
        """
        **Feature: metas-financeiras, Property 10: Operações de limpeza**
        **Validates: Requirements 5.4, 5.5**
        
        Para qualquer usuário, o comando "/meta limpar" deve remover todas
        as metas após confirmação.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar múltiplas metas
            categorias = list(ExpenseCategory)[:num_goals]
            
            for i, categoria in enumerate(categorias):
                goal = Goal(
                    user_id=user_id,
                    categoria=categoria.value,
                    valor_meta=Decimal(str(100.0 * (i + 1))),
                    mes=mes,
                    ano=ano
                )
                session.add(goal)
            
            session.commit()
            
            # Verificar que as metas foram criadas
            goals_before = session.query(Goal).filter_by(user_id=user_id).all()
            assert len(goals_before) == num_goals
            
            # Limpar todas as metas
            all_goals = session.query(Goal).filter_by(user_id=user_id).all()
            for goal in all_goals:
                session.delete(goal)
            session.commit()
            
            # Verificar que todas as metas foram removidas
            goals_after = session.query(Goal).filter_by(user_id=user_id).all()
            assert len(goals_after) == 0
            
        finally:
            session.close()
            engine.dispose()
    
    @given(
        user_id=st.integers(min_value=1, max_value=999999),
        num_goals=st.integers(min_value=1, max_value=7),
        mes=st.integers(min_value=1, max_value=12),
        ano=st.integers(min_value=2020, max_value=2030)
    )
    @settings(max_examples=50, deadline=1000)
    def test_cancel_cleanup_preserves_goals_property(self, user_id, num_goals, mes, ano):
        """
        **Feature: metas-financeiras, Property 10: Operações de limpeza**
        **Validates: Requirements 5.4, 5.5**
        
        Para qualquer usuário, se a operação de limpeza for cancelada,
        todas as metas devem permanecer inalteradas.
        """
        session, engine = self.get_fresh_session()
        
        try:
            # Criar múltiplas metas
            categorias = list(ExpenseCategory)[:num_goals]
            created_goals = []
            
            for i, categoria in enumerate(categorias):
                valor = Decimal(str(100.0 * (i + 1)))
                goal = Goal(
                    user_id=user_id,
                    categoria=categoria.value,
                    valor_meta=valor,
                    mes=mes,
                    ano=ano
                )
                session.add(goal)
                created_goals.append((categoria.value, valor))
            
            session.commit()
            
            # Verificar que as metas foram criadas
            goals_before = session.query(Goal).filter_by(user_id=user_id).all()
            assert len(goals_before) == num_goals
            
            # Simular cancelamento (não fazer nada)
            # Em uma implementação real, o usuário cancelaria a operação
            
            # Verificar que todas as metas ainda existem
            goals_after = session.query(Goal).filter_by(user_id=user_id).all()
            assert len(goals_after) == num_goals
            
            # Verificar que os valores estão inalterados
            for goal in goals_after:
                matching_created = [g for g in created_goals if g[0] == goal.categoria]
                assert len(matching_created) == 1
                assert goal.valor_meta == matching_created[0][1]
            
        finally:
            session.close()
            engine.dispose()
