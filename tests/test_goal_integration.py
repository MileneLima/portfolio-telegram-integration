"""
Integration tests for goal system with expense flow
"""

import pytest
from datetime import datetime
from decimal import Decimal

from models.schemas import ExpenseCategory
from services.goal_service import goal_service


@pytest.mark.asyncio
class TestGoalExpenseIntegration:
    """Test integration between goal system and expense flow"""
    
    async def test_expense_with_goal_shows_progress(self):
        """
        Test that when an expense is registered and a goal exists,
        the confirmation message includes goal progress information.
        
        **Feature: metas-financeiras, Integration Test**
        **Validates: Requirements 4.1**
        """
        user_id = 12345
        categoria = ExpenseCategory.ALIMENTACAO
        valor_meta = Decimal('500.00')
        
        now = datetime.now()
        
        # Create a goal
        goal = await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=categoria,
            valor_meta=valor_meta,
            mes=now.month,
            ano=now.year
        )
        
        assert goal is not None
        
        # Get progress (simulating what happens in _send_confirmation)
        progress = await goal_service.get_goal_progress(
            user_id=user_id,
            categoria=categoria,
            mes=now.month,
            ano=now.year
        )
        
        # Verify progress is returned
        assert progress is not None
        assert progress.categoria == categoria
        assert progress.valor_meta == valor_meta
        
        # Clean up
        await goal_service.delete_goal(user_id, categoria, now.month, now.year)
    
    async def test_expense_without_goal_no_alert(self):
        """
        Test that expenses for categories without goals
        don't trigger any alerts.
        
        **Feature: metas-financeiras, Integration Test**
        **Validates: Requirements 4.1**
        """
        user_id = 12349
        categoria = ExpenseCategory.OUTROS
        
        # Don't create a goal
        
        # Try to check for alert (no transactions exist, so progress will be 0)
        alert = await goal_service.check_goal_alerts(
            user_id=user_id,
            categoria=categoria,
            current_spending=Decimal('100.00')
        )
        
        # No alert should be triggered (no goal exists)
        assert alert is None
    
    async def test_expense_below_80_percent_no_alert(self):
        """
        Test that expenses below 80% of goal don't trigger alerts.
        
        **Feature: metas-financeiras, Integration Test**
        **Validates: Requirements 4.2**
        """
        user_id = 12350
        categoria = ExpenseCategory.CASA
        valor_meta = Decimal('1000.00')
        
        now = datetime.now()
        
        # Create a goal
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=categoria,
            valor_meta=valor_meta,
            mes=now.month,
            ano=now.year
        )
        
        # Check for alert (no transactions exist, so progress will be 0%)
        alert = await goal_service.check_goal_alerts(
            user_id=user_id,
            categoria=categoria,
            current_spending=Decimal('500.00')
        )
        
        # No alert should be triggered (0% < 80%)
        assert alert is None
        
        # Clean up
        await goal_service.delete_goal(user_id, categoria, now.month, now.year)
    
    async def test_goal_info_structure(self):
        """
        Test that goal progress structure is correct for display
        in confirmation messages.
        
        **Feature: metas-financeiras, Integration Test**
        **Validates: Requirements 4.1**
        """
        user_id = 12351
        categoria = ExpenseCategory.FINANCAS
        valor_meta = Decimal('2000.00')
        
        now = datetime.now()
        
        # Create a goal
        await goal_service.create_or_update_goal(
            user_id=user_id,
            categoria=categoria,
            valor_meta=valor_meta,
            mes=now.month,
            ano=now.year
        )
        
        # Get progress
        progress = await goal_service.get_goal_progress(
            user_id=user_id,
            categoria=categoria,
            mes=now.month,
            ano=now.year
        )
        
        # Verify structure
        assert progress is not None
        assert hasattr(progress, 'valor_meta')
        assert hasattr(progress, 'valor_gasto')
        assert hasattr(progress, 'progresso_percentual')
        assert hasattr(progress, 'status')
        assert progress.valor_meta == valor_meta
        assert progress.valor_gasto >= 0
        assert progress.progresso_percentual >= 0
        
        # Clean up
        await goal_service.delete_goal(user_id, categoria, now.month, now.year)
