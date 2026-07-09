from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from database.database import conectar


def cadastrar_fatura(
    apartamento_id,
    mes,
    ano,
    consumo_agua,
    consumo_gas,
    valor_agua=0,
    valor_gas=0,
    leitura_id=None,
    status="pendente"
):
    valor_total = valor_agua + valor_gas

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO faturas (
            apartamento_id,
            leitura_id,
            mes,
            ano,
            consumo_agua,
            consumo_gas,
            valor_agua,
            valor_gas,
            valor_total,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        apartamento_id,
        leitura_id,
        mes,
        ano,
        consumo_agua,
        consumo_gas,
        valor_agua,
        valor_gas,
        valor_total,
        status
    ))

    conexao.commit()
    fatura_id = cursor.lastrowid
    conexao.close()

    return fatura_id


def listar_faturas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            faturas.id,
            apartamentos.numero,
            apartamentos.bloco,
            faturas.mes,
            faturas.ano,
            faturas.consumo_agua,
            faturas.consumo_gas,
            faturas.valor_agua,
            faturas.valor_gas,
            faturas.valor_total,
            faturas.status
        FROM faturas
        JOIN apartamentos ON faturas.apartamento_id = apartamentos.id
        ORDER BY faturas.ano DESC, faturas.mes DESC
    """)

    faturas = cursor.fetchall()
    conexao.close()

    return faturas


def buscar_fatura_por_id(fatura_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            faturas.id,
            apartamentos.numero,
            apartamentos.bloco,
            faturas.mes,
            faturas.ano,
            faturas.consumo_agua,
            faturas.consumo_gas,
            faturas.valor_agua,
            faturas.valor_gas,
            faturas.valor_total,
            faturas.status
        FROM faturas
        JOIN apartamentos
            ON apartamentos.id = faturas.apartamento_id
        WHERE faturas.id = ?
    """, (fatura_id,))

    fatura = cursor.fetchone()

    conexao.close()

    return fatura


if __name__ == "__main__":
    fatura_id = cadastrar_fatura(
        apartamento_id=1,
        leitura_id=1,
        mes=7,
        ano=2026,
        consumo_agua=10,
        consumo_gas=6,
        valor_agua=85.50,
        valor_gas=42.00
    )

    print("Fatura cadastrada com ID:", fatura_id)

    for fatura in listar_faturas():
        print(fatura)
