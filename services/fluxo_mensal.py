from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from models.leituras import cadastrar_leitura
from models.faturas import cadastrar_fatura


def gerar_fatura_mensal(
    apartamento_id,
    mes,
    ano,
    leitura_agua,
    leitura_gas,
    consumo_agua,
    consumo_gas,
    valor_agua=0,
    valor_gas=0
):
    leitura_id = cadastrar_leitura(
        apartamento_id=apartamento_id,
        mes=mes,
        ano=ano,
        leitura_agua=leitura_agua,
        leitura_gas=leitura_gas
    )

    fatura_id = cadastrar_fatura(
        apartamento_id=apartamento_id,
        leitura_id=leitura_id,
        mes=mes,
        ano=ano,
        consumo_agua=consumo_agua,
        consumo_gas=consumo_gas,
        valor_agua=valor_agua,
        valor_gas=valor_gas
    )

    return fatura_id


if __name__ == "__main__":
    fatura_id = gerar_fatura_mensal(
        apartamento_id=1,
        mes=7,
        ano=2026,
        leitura_agua=145,
        leitura_gas=62,
        consumo_agua=12,
        consumo_gas=6,
        valor_agua=90.00,
        valor_gas=42.00
    )

    print("Fatura mensal gerada com ID:", fatura_id)
