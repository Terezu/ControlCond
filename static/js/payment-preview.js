(() => {
    "use strict";

    const resumo = document.getElementById("resumo-pagamento");
    const dataPagamento = document.getElementById("id_data_pagamento");
    if (!resumo || !dataPagamento) {
        return;
    }

    const moeda = new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    });
    const campos = {
        valor_original: "pagamento-valor-original",
        desconto: "pagamento-desconto",
        bonificacao: "pagamento-bonificacao",
        multa: "pagamento-multa",
        juros: "pagamento-juros",
        valor_final: "pagamento-valor-final",
    };
    const negativos = new Set(["desconto", "bonificacao"]);
    const erro = document.getElementById("erro-previsao-pagamento");
    let requisicaoAtual = null;

    const atualizar = async () => {
        if (!dataPagamento.value) {
            return;
        }
        requisicaoAtual?.abort();
        requisicaoAtual = new AbortController();
        const url = new URL(resumo.dataset.previewUrl, window.location.origin);
        url.searchParams.set("data_pagamento", dataPagamento.value);
        try {
            const resposta = await fetch(url, {
                headers: {"X-Requested-With": "XMLHttpRequest"},
                signal: requisicaoAtual.signal,
            });
            const dados = await resposta.json();
            if (!resposta.ok) {
                throw new Error(dados.erro || "Não foi possível calcular.");
            }
            Object.entries(campos).forEach(([campo, id]) => {
                const prefixo = negativos.has(campo) ? "- " : "";
                document.getElementById(id).textContent = (
                    `${prefixo}${moeda.format(Number(dados[campo]))}`
                );
            });
            document.getElementById("pagamento-periodo").textContent = (
                `${dados.dias_em_atraso} dias em atraso · `
                + `${dados.dias_antecipados} dias antecipados`
            );
            erro.classList.add("d-none");
            erro.textContent = "";
        } catch (falha) {
            if (falha.name === "AbortError") {
                return;
            }
            erro.textContent = falha.message;
            erro.classList.remove("d-none");
        }
    };

    dataPagamento.addEventListener("change", atualizar);
})();
