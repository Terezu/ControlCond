# Configuração segura de produção

O ControlCond usa as variáveis do ambiente do processo. Antes de iniciar o
servidor de produção, configure pelo menos:

```powershell
$env:DJANGO_DEBUG = "False"
$env:DJANGO_SECRET_KEY = "gere-uma-chave-longa-aleatoria-e-exclusiva"
$env:DJANGO_ALLOWED_HOSTS = "condominio.exemplo.com"
$env:DJANGO_CSRF_TRUSTED_ORIGINS = "https://condominio.exemplo.com"
$env:DJANGO_DATABASE_PATH = "C:\\dados\\ControlCond\\controlcond.db"
```

Com `DJANGO_DEBUG=False`, HTTPS, cookies seguros e HSTS são habilitados por
padrão. O proxy ou servidor web deve encaminhar somente tráfego HTTPS à
aplicação. Não armazene a chave secreta em arquivos versionados. Mantenha o
banco fora da pasta do repositório e inclua esse caminho na rotina de backup.
As transações de escrita usam o modo `IMMEDIATE` do SQLite e aguardam até 20
segundos por padrão; ajuste `DJANGO_SQLITE_TIMEOUT` somente com um inteiro
positivo caso a carga do ambiente exija outro tempo.

Se o proxy encerrar o TLS e conversar com o Django por HTTP, configure-o para
remover qualquer `X-Forwarded-Proto` enviado pelo cliente e definir o cabeçalho
com o protocolo externo. Somente depois habilite:

```powershell
$env:DJANGO_TRUST_X_FORWARDED_PROTO = "True"
```

Sem essa garantia no proxy, não habilite a opção: confiar em um cabeçalho
forjado permitiria que o cliente enganasse as verificações de conexão segura.

Use sempre uma versão de manutenção suportada do Python e atualize as
dependências dentro dos intervalos de `requirements.txt`. Após a atualização,
execute `python -m pip check` e a suíte de testes.

Valide a configuração antes de publicar:

```powershell
python manage.py check --deploy
```

As telas de apartamentos, leituras, faturas e PDFs só podem ser acessadas por
usuários ativos com perfil de equipe (`is_staff`). O cadastro e a manutenção
desses usuários são feitos pelo painel `/admin/`.

## Banco de dados e Git

Arquivos `*.db` estão ignorados para evitar o versionamento de dados do
condomínio. Se um banco já tiver sido adicionado ao Git antes dessa regra,
retire-o somente do índice, preservando o arquivo local:

```powershell
git rm --cached -- controlcond.db
```

Se o repositório já tiver sido compartilhado, considere os dados históricos
como expostos e avalie a limpeza do histórico e a troca de credenciais que
possam estar armazenadas no banco.

Se alguma instalação utilizou uma `SECRET_KEY` que já esteve versionada, gere
uma nova chave; essa troca invalida sessões antigas. Também redefina as senhas
dos operadores caso um banco com hashes de autenticação tenha sido publicado.

Antes de cada publicação, aplique as migrações. Elas também corrigem registros
legados cujo total da fatura não corresponda à soma de água e gás:

```powershell
python manage.py migrate
```

## Tarifas de consumo

O cálculo de água usa a categoria **Residencial Normal — Água e Esgoto de
Curitiba**, vigente desde 17/05/2026, conforme a
[tabela oficial da SANEPAR](https://www.sanepar.com.br/tarifas). As faixas ficam
registradas em `calculos/services.py`, e cada fatura preserva os valores usados
na emissão.

Antes de faturar após um novo reajuste, atualize as faixas e os testes. Se o
condomínio usar outra localidade, categoria ou percentual de esgoto, adapte a
configuração antes de emitir cobranças. O valor do gás também é uma constante
do projeto e deve ser conferido com o fornecedor sempre que houver reajuste.
