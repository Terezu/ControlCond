(() => {
    "use strict";

    const campos = {
        id_cor_primaria: "--controlcond-primary",
        id_cor_secundaria: "--controlcond-secondary",
        id_cor_destaque: "--controlcond-highlight",
    };
    const raiz = document.documentElement;

    const hexParaRgb = (cor) => {
        const valor = cor.replace("#", "");
        return [0, 2, 4]
            .map((indice) => Number.parseInt(valor.slice(indice, indice + 2), 16))
            .join(", ");
    };

    const corContraste = (cor) => {
        const componentes = hexParaRgb(cor)
            .split(", ")
            .map((valor) => Number(valor) / 255);
        const luminancia = (
            (0.2126 * componentes[0])
            + (0.7152 * componentes[1])
            + (0.0722 * componentes[2])
        );
        return luminancia > 0.58 ? "#212529" : "#FFFFFF";
    };

    Object.entries(campos).forEach(([id, variavel]) => {
        const campo = document.getElementById(id);
        if (!campo) {
            return;
        }
        campo.addEventListener("input", () => {
            raiz.style.setProperty(variavel, campo.value);
            raiz.style.setProperty(`${variavel}-rgb`, hexParaRgb(campo.value));
            if (variavel !== "--controlcond-highlight") {
                raiz.style.setProperty(
                    `${variavel}-contrast`,
                    corContraste(campo.value),
                );
            }
        });
    });

    const botaoRestaurar = document.getElementById("restaurar-cores-padrao");
    if (botaoRestaurar) {
        const coresPadrao = {
            id_cor_primaria: botaoRestaurar.dataset.corPrimaria,
            id_cor_secundaria: botaoRestaurar.dataset.corSecundaria,
            id_cor_destaque: botaoRestaurar.dataset.corDestaque,
        };
        botaoRestaurar.addEventListener("click", () => {
            Object.entries(coresPadrao).forEach(([id, cor]) => {
                const campo = document.getElementById(id);
                if (!campo || !cor) {
                    return;
                }
                campo.value = cor;
                campo.dispatchEvent(new Event("input", {bubbles: true}));
            });
        });
    }
})();
