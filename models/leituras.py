from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from database.database import conectar


def cadastrar_leitura(apartamento_id, mes, ano, leitura_agua=None, leitura_gas=None):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO leituras (
            apartamento_id,
            mes,
            ano,
            leitura_agua,
            leitura_gas
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        apartamento_id,
        mes,
        ano,
        leitura_agua,
        leitura_gas
    ))

    conexao.commit()

    leitura_id = cursor.lastrowid

    conexao.close()

    return leitura_id


def buscar_ultimas_leituras(apartamento_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, leitura_agua, leitura_gas, mes, ano
        FROM leituras
        WHERE apartamento_id = ?
        ORDER BY ano DESC, mes DESC, id DESC
        LIMIT 12
    """, (apartamento_id,))

    leitura = cursor.fetchall()
    conexao.close()

    return leitura


def listar_leituras():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            leituras.id,
            apartamentos.numero,
            apartamentos.bloco,
            leituras.mes,
            leituras.ano,
            leituras.leitura_agua,
            leituras.leitura_gas,
            leituras.data_registro
        FROM leituras
        JOIN apartamentos ON leituras.apartamento_id = apartamentos.id
        ORDER BY leituras.ano DESC, leituras.mes DESC
    """)

    leituras = cursor.fetchall()
    conexao.close()

    return leituras


if __name__ == "__main__":
    leitura_id = cadastrar_leitura(
        apartamento_id=1,
        mes=7,
        ano=2026,
        leitura_agua=135,
        leitura_gas=56
    )

    print("Leitura cadastrada com ID:", leitura_id)

    ultimas = buscar_ultimas_leituras(1)
    print("Últimas leituras:", ultimas)

    todas = listar_leituras()

    for leitura in todas:
        print(leitura)
