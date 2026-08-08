document.addEventListener("DOMContentLoaded", () => {
    const botao = document.getElementById("adicionar-faixa");
    const corpo = document.getElementById("faixas-formset");
    const modelo = document.getElementById("faixa-empty-form");
    const total = document.getElementById("id_faixas-TOTAL_FORMS");

    if (!botao || !corpo || !modelo || !total) {
        return;
    }

    botao.addEventListener("click", () => {
        const indice = Number.parseInt(total.value, 10);
        const fragmento = modelo.content.cloneNode(true);

        fragmento.querySelectorAll("[name], [id], label[for]").forEach((elemento) => {
            if (elemento.name) {
                elemento.name = elemento.name.replaceAll("__prefix__", indice);
            }
            if (elemento.id) {
                elemento.id = elemento.id.replaceAll("__prefix__", indice);
            }
            if (elemento.htmlFor) {
                elemento.htmlFor = elemento.htmlFor.replaceAll("__prefix__", indice);
            }
        });

        corpo.appendChild(fragmento);
        total.value = indice + 1;
    });
});
