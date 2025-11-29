"""
Migrações do banco de dados
"""

import sqlite3
from pathlib import Path
from config.settings import get_settings


def get_database_path():
    """Obter caminho do banco de dados"""
    settings = get_settings()
    # Remove sqlite:// prefix to get file path
    db_path = settings.database_url.replace("sqlite:///", "")
    return db_path


def migrate_add_audio_fields():
    """Migração para adicionar campos de áudio à tabela transactions"""
    db_path = get_database_path()
    
    # Verificar se o banco existe
    if not Path(db_path).exists():
        print(f"Banco de dados não encontrado em: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar se as colunas já existem
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        migrations_applied = []
        
        # Adicionar source_type se não existir
        if 'source_type' not in columns:
            cursor.execute("""
                ALTER TABLE transactions 
                ADD COLUMN source_type VARCHAR(20) DEFAULT 'text'
            """)
            migrations_applied.append("source_type")
        
        # Adicionar transcribed_text se não existir
        if 'transcribed_text' not in columns:
            cursor.execute("""
                ALTER TABLE transactions 
                ADD COLUMN transcribed_text TEXT NULL
            """)
            migrations_applied.append("transcribed_text")
        
        # Criar índice para source_type se não existir
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_source_type 
            ON transactions(source_type)
        """)
        
        conn.commit()
        conn.close()
        
        if migrations_applied:
            print(f"Migração concluída. Campos adicionados: {', '.join(migrations_applied)}")
        else:
            print("Nenhuma migração necessária. Campos já existem.")
        
        return True
        
    except Exception as e:
        print(f"Erro durante migração: {e}")
        if 'conn' in locals():
            conn.close()
        return False


def migrate_add_goals_table():
    """Migração para adicionar tabela de metas financeiras"""
    db_path = get_database_path()
    
    # Verificar se o banco existe
    if not Path(db_path).exists():
        print(f"Banco de dados não encontrado em: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar se a tabela goals já existe
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='goals'
        """)
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # Criar tabela goals
            cursor.execute("""
                CREATE TABLE goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    categoria VARCHAR(50) NOT NULL,
                    valor_meta DECIMAL(10,2) NOT NULL,
                    mes INTEGER NOT NULL CHECK (mes >= 1 AND mes <= 12),
                    ano INTEGER NOT NULL CHECK (ano >= 2020),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, categoria, mes, ano)
                )
            """)
            
            # Criar índices otimizados
            cursor.execute("""
                CREATE INDEX idx_goals_user_period 
                ON goals(user_id, mes, ano)
            """)
            
            cursor.execute("""
                CREATE INDEX idx_goals_user_category 
                ON goals(user_id, categoria)
            """)
            
            conn.commit()
            print("Tabela 'goals' criada com sucesso com índices otimizados.")
        else:
            print("Tabela 'goals' já existe.")
        
        # Adicionar índices adicionais para otimização de queries (se não existirem)
        cursor.execute("PRAGMA index_list(goals)")
        existing_indexes = [idx[1] for idx in cursor.fetchall()]
        
        # Índice composto para queries de progresso
        if 'idx_goals_user_cat_period' not in existing_indexes:
            cursor.execute("""
                CREATE INDEX idx_goals_user_cat_period 
                ON goals(user_id, categoria, mes, ano)
            """)
            print("Índice composto idx_goals_user_cat_period criado.")
        
        # Índice para limpeza de metas antigas
        if 'idx_goals_period' not in existing_indexes:
            cursor.execute("""
                CREATE INDEX idx_goals_period 
                ON goals(ano, mes)
            """)
            print("Índice idx_goals_period criado.")
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Erro durante migração de goals: {e}")
        if 'conn' in locals():
            conn.close()
        return False


def migrate_optimize_transactions_indexes():
    """Migração para otimizar índices da tabela transactions para queries de metas"""
    db_path = get_database_path()
    
    if not Path(db_path).exists():
        print(f"Banco de dados não encontrado em: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar índices existentes
        cursor.execute("PRAGMA index_list(transactions)")
        existing_indexes = [idx[1] for idx in cursor.fetchall()]
        
        indexes_created = []
        
        # Índice composto para queries de gastos por categoria e período
        if 'idx_transactions_user_cat_period' not in existing_indexes:
            cursor.execute("""
                CREATE INDEX idx_transactions_user_cat_period 
                ON transactions(user_id, categoria, data_transacao, status)
            """)
            indexes_created.append("idx_transactions_user_cat_period")
        
        # Índice para queries de período
        if 'idx_transactions_period_status' not in existing_indexes:
            cursor.execute("""
                CREATE INDEX idx_transactions_period_status 
                ON transactions(data_transacao, status)
            """)
            indexes_created.append("idx_transactions_period_status")
        
        conn.commit()
        conn.close()
        
        if indexes_created:
            print(f"Índices de otimização criados: {', '.join(indexes_created)}")
        else:
            print("Todos os índices de otimização já existem.")
        
        return True
        
    except Exception as e:
        print(f"Erro durante otimização de índices: {e}")
        if 'conn' in locals():
            conn.close()
        return False


def check_migration_status():
    """Verificar status das migrações"""
    db_path = get_database_path()
    
    if not Path(db_path).exists():
        return {"database_exists": False}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar estrutura da tabela transactions
        cursor.execute("PRAGMA table_info(transactions)")
        columns = {column[1]: column[2] for column in cursor.fetchall()}
        
        # Verificar índices
        cursor.execute("PRAGMA index_list(transactions)")
        indexes = [index[1] for index in cursor.fetchall()]
        
        # Verificar se tabela goals existe
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='goals'
        """)
        goals_table_exists = cursor.fetchone() is not None
        
        conn.close()
        
        return {
            "database_exists": True,
            "has_source_type": "source_type" in columns,
            "has_transcribed_text": "transcribed_text" in columns,
            "has_source_type_index": "idx_transactions_source_type" in indexes,
            "has_goals_table": goals_table_exists,
            "columns": columns
        }
        
    except Exception as e:
        return {"database_exists": True, "error": str(e)}


if __name__ == "__main__":
    print("Verificando status das migrações...")
    status = check_migration_status()
    print(f"Status: {status}")
    
    if status.get("database_exists") and not status.get("error"):
        migrations_needed = False
        
        if not status.get("has_source_type") or not status.get("has_transcribed_text"):
            print("\nExecutando migração de campos de áudio...")
            migrate_add_audio_fields()
            migrations_needed = True
        
        if not status.get("has_goals_table"):
            print("\nExecutando migração de tabela de metas...")
            migrate_add_goals_table()
            migrations_needed = True
        
        # Sempre executar otimização de índices (verifica internamente se já existem)
        print("\nVerificando otimização de índices...")
        migrate_optimize_transactions_indexes()
        
        if not migrations_needed:
            print("\nTodas as migrações já foram aplicadas.")
    else:
        print("\nBanco de dados não encontrado ou erro detectado.")