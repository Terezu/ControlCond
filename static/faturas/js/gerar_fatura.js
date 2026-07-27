document.addEventListener("DOMContentLoaded", () => {
    const atualizarBonificacao = (escopo) => {
        const modo = escopo.querySelector("#id_modo_bonificacao");
        const tipo = escopo.querySelector("#id_tipo_bonificacao");
        const grupos = escopo.querySelectorAll(
            "[data-bonificacao-especifica]",
        );
        const previa = escopo.querySelector("[data-bonificacao-previa]");
        if (!modo) return;

        const atualizar = () => {
            const especifica = modo.value === "especifica";
            grupos.forEach((grupo) => {
                grupo.hidden = !especifica;
            });
            if (!previa) return;
            if (modo.value === "condominio") {
                const percentual = previa.dataset.percentualPadrao || "0";
                const dias = previa.dataset.diasAntecedencia || "0";
                previa.textContent = (
                    `Prévia: padrão de ${percentual}% até ${dias} dia(s) ` +
                    "antes do vencimento. O valor definitivo será calculado " +
                    "pelo sistema no pagamento."
                );
            } else if (especifica) {
                const rotuloTipo = tipo?.selectedOptions[0]?.text || "";
                previa.textContent = (
                    `Prévia: bonificação específica ${rotuloTipo.toLowerCase()}. ` +
                    "O valor definitivo será calculado pelo sistema no pagamento."
                );
            } else {
                previa.textContent = "Esta fatura não terá bonificação.";
            }
        };
        modo.addEventListener("change", atualizar);
        tipo?.addEventListener("change", atualizar);
        atualizar();
    };
    document.querySelectorAll("[data-bonificacao]").forEach(
        atualizarBonificacao,
    );

    const formulario = document.querySelector("form[data-url-aluguel]");
    if (!formulario) {
        return;
    }

    const leitura = formulario.querySelector("#id_leitura");
    const camposPadrao = [
        "valor_aluguel",
        "valor_condominio",
        "valor_iptu",
    ];
    if (!leitura) {
        return;
    }

    leitura.addEventListener("change", async () => {
        if (!leitura.value) {
            camposPadrao.forEach((nome) => {
                const campo = formulario.querySelector(`#id_${nome}`);
                if (campo) campo.value = "";
            });
            return;
        }

        const url = new URL(
            formulario.dataset.urlAluguel,
            window.location.origin,
        );
        url.searchParams.set("leitura", leitura.value);

        try {
            const resposta = await fetch(url, {
                headers: {"Accept": "application/json"},
                credentials: "same-origin",
            });
            if (!resposta.ok) {
                return;
            }
            const dados = await resposta.json();
            camposPadrao.forEach((nome) => {
                const campo = formulario.querySelector(`#id_${nome}`);
                if (campo) campo.value = dados[nome] ?? "";
            });
        } catch {
            // O servidor ainda aplicará o aluguel padrão se o campo ficar vazio.
        }
    });

    const outros = formulario.querySelector("#id_valor_outros");
    const grupoObservacao = formulario.querySelector(
        "[data-campo-observacao-outros]",
    );
    if (outros && grupoObservacao) {
        const atualizarObservacao = () => {
            const valor = Number(String(outros.value).replace(",", "."));
            grupoObservacao.hidden = !Number.isNaN(valor) && valor === 0;
        };
        outros.addEventListener("input", atualizarObservacao);
        atualizarObservacao();
    }

});
