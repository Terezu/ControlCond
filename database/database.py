import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "controlcond.db"


def conectar():
    conexao = sqlite3.connect(DB_PATH)
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def _colunas(cursor, tabela):
    return [coluna[1] for coluna in cursor.execute(f"PRAGMA table_info({tabela})")]


def _migrar_tabelas_antigas(cursor):
    colunas_leituras = _colunas(cursor, "leituras")
    if "morador_id" in colunas_leituras and "apartamento_id" not in colunas_leituras:
        cursor.execute("ALTER TABLE leituras RENAME TO leituras_antiga")
        cursor.execute("""
            CREATE TABLE leituras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento_id INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                ano INTEGER NOT NULL,

                leitura_agua REAL,
                leitura_gas REAL,

                data_registro TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (apartamento_id) REFERENCES apartamentos(id)
            )
        """)
        cursor.execute("""
            INSERT INTO leituras (
                id,
                apartamento_id,
                mes,
                ano,
                leitura_agua,
                leitura_gas,
                data_registro
            )
            SELECT
                id,
                morador_id,
                mes,
                ano,
                leitura_agua,
                leitura_gas,
                data_registro
            FROM leituras_antiga
        """)
        cursor.execute("DROP TABLE leituras_antiga")

    colunas_faturas = _colunas(cursor, "faturas")
    if "morador_id" in colunas_faturas and "apartamento_id" not in colunas_faturas:
        cursor.execute("ALTER TABLE faturas RENAME TO faturas_antiga")
        cursor.execute("""
            CREATE TABLE faturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento_id INTEGER NOT NULL,
                leitura_id INTEGER,

                mes INTEGER NOT NULL,
                ano INTEGER NOT NULL,

                consumo_agua REAL NOT NULL,
                consumo_gas REAL NOT NULL,

                valor_agua REAL DEFAULT 0,
                valor_gas REAL DEFAULT 0,
                valor_total REAL DEFAULT 0,

                status TEXT DEFAULT 'pendente',
                data_geracao TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (apartamento_id) REFERENCES apartamentos(id),
                FOREIGN KEY (leitura_id) REFERENCES leituras(id)
            )
        """)
        cursor.execute("""
            INSERT INTO faturas (
                id,
                apartamento_id,
                leitura_id,
                mes,
                ano,
                consumo_agua,
                consumo_gas,
                valor_agua,
                valor_gas,
                valor_total,
                status,
                data_geracao
            )
            SELECT
                id,
                morador_id,
                leitura_id,
                mes,
                ano,
                consumo_agua,
                consumo_gas,
                valor_agua,
                valor_gas,
                valor_total,
                status,
                data_geracao
            FROM faturas_antiga
        """)
        cursor.execute("DROP TABLE faturas_antiga")


def criar_tabelas():
    conexao = conectar()
    conexao.execute("PRAGMA foreign_keys = OFF")
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS apartamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            bloco TEXT,
            observacoes TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leituras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartamento_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,

            leitura_agua REAL,
            leitura_gas REAL,

            data_registro TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (apartamento_id) REFERENCES apartamentos(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartamento_id INTEGER NOT NULL,
            leitura_id INTEGER,

            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,

            consumo_agua REAL NOT NULL,
            consumo_gas REAL NOT NULL,

            valor_agua REAL DEFAULT 0,
            valor_gas REAL DEFAULT 0,
            valor_total REAL DEFAULT 0,

            status TEXT DEFAULT 'pendente',
            data_geracao TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (apartamento_id) REFERENCES apartamentos(id),
            FOREIGN KEY (leitura_id) REFERENCES leituras(id)
        )
    """)

    _migrar_tabelas_antigas(cursor)

    conexao.commit()
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.close()


if __name__ == "__main__":
    criar_tabelas()
    print("Banco de dados criado com sucesso.")
