"""
Utilidades gerais da aplicação
"""

import hashlib
from datetime import datetime, date
from typing import Any, Dict, List
import json
from decimal import Decimal


class CustomJSONEncoder(json.JSONEncoder):
    """Encoder JSON personalizado"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def hash_string(text: str) -> str:
    """Gerar hash SHA256 de uma string"""
    return hashlib.sha256(text.encode()).hexdigest()


def format_currency(value: float, currency: str = "BRL") -> str:
    """Formatar valor como moeda"""
    if currency == "BRL":
        return f"R$ {value:.2f}"
    return f"{value:.2f}"


def parse_date_text(text: str) -> date:
    """Extrair data de texto em português"""
    today = date.today()

    if "hoje" in text.lower():
        return today
    elif "ontem" in text.lower():
        return date(today.year, today.month, today.day - 1)
    elif "anteontem" in text.lower():
        return date(today.year, today.month, today.day - 2)

    return today


def extract_numbers(text: str) -> List[float]:
    """Extrair números de um texto"""
    import re

    pattern = r'\d+(?:[.,]\d{2})?'
    matches = re.findall(pattern, text)

    numbers = []
    for match in matches:
        normalized = match.replace(',', '.')
        numbers.append(float(normalized))

    return numbers


def clean_text(text: str) -> str:
    """Limpar texto removendo caracteres especiais"""
    import re

    cleaned = re.sub(r'[^a-zA-Z0-9\sÃ€-Ã¿,.]', '', text)

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def validate_spreadsheet_id(spreadsheet_id: str) -> bool:
    """Validar ID de planilha Google"""
    import re

    pattern = r'^[a-zA-Z0-9-_]+$'
    return bool(re.match(pattern, spreadsheet_id)) and len(spreadsheet_id) > 20


def get_month_name(month_number: int) -> str:
    """Obter nome do mês em português"""
    months = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    return months.get(month_number, "Janeiro")


def format_transaction_summary(transactions: List[Dict[str, Any]]) -> str:
    """Formatar resumo de transações"""
    if not transactions:
        return "Nenhuma transação encontrada."

    total = sum(float(t.get('valor', 0)) for t in transactions)
    count = len(transactions)

    summary = f"**Resumo:** {count} transações totalizando R$ {total:.2f}\n\n"

    categories = {}
    for t in transactions:
        cat = t.get('categoria', 'Outros')
        categories[cat] = categories.get(cat, 0) + float(t.get('valor', 0))

    for cat, value in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        summary += f"â€¢ {cat}: R$ {value:.2f}\n"

    return summary