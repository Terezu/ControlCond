document.addEventListener("DOMContentLoaded", () => {
    const formulario = document.querySelector("form[data-url-aluguel]");
    if (!formulario) {
        return;
    }

    const leitura = formulario.querySelector("#id_leitura");
    const aluguel = formulario.querySelector("#id_valor_aluguel");
    if (!leitura || !aluguel) {
        return;
    }

    leitura.addEventListener("change", async () => {
        if (!leitura.value) {
            aluguel.value = "";
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
            aluguel.value = dados.valor_aluguel;
        } catch {
            // O servidor ainda aplicará o aluguel padrão se o campo ficar vazio.
        }
    });
});
