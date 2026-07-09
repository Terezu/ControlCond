from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from database.database import conectar


def cadastrar_apartamento(numero, bloco=None, observacoes=None):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO apartamentos (
            numero,
            bloco,
            observacoes
        )
        VALUES (?, ?, ?)
    """, (
        numero,
        bloco,
        observacoes
    ))

    conexao.commit()
    apartamento_id = cursor.lastrowid
    conexao.close()

    return apartamento_id


def listar_apartamentos():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            numero,
            bloco,
            observacoes
        FROM apartamentos
        ORDER BY bloco, numero
    """)

    apartamentos = cursor.fetchall()
    conexao.close()

    return apartamentos


def buscar_apartamento_por_id(apartamento_id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            numero,
            bloco,
            observacoes
        FROM apartamentos
        WHERE id = ?
    """, (apartamento_id,))

    apartamento = cursor.fetchone()
    conexao.close()

    return apartamento


if __name__ == "__main__":
    apartamento_id = cadastrar_apartamento(
        numero="101",
        bloco="A",
        observacoes="Apartamento de teste"
    )

    print("Apartamento cadastrado com ID:", apartamento_id)

    for apartamento in listar_apartamentos():
        print(apartamento)
