document.addEventListener("DOMContentLoaded", () => {
    const formulario = document.querySelector("form[data-url-aluguel]");
    if (!formulario) {
        return;
    }

    const leitura = formulario.querySelector("#id_leitura");
    const camposPadrao = [
        "valor_aluguel",
        "valor_condominio",
        "valor_iptu",
        "valor_bonificacao",
        "dia_limite_bonificacao",
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
