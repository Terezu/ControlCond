# Execução por ambiente

O ControlCond usa SQLite no desenvolvimento local e PostgreSQL quando
`DATABASE_URL` está definida. Segredos pertencem ao ambiente do processo e não
devem ser gravados no repositório.

## Desenvolvimento local

Sem `DATABASE_URL`, a aplicação usa `controlcond.db` na raiz do projeto. O
caminho pode ser substituído apenas para desenvolvimento e testes por
`DJANGO_DATABASE_PATH`.

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

No PowerShell, uma variável temporária pode ser definida com
`$env:DJANGO_DEBUG = "True"`. Não é necessário criar um `.env` para executar o
servidor local.

## Build

```bash
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
```

## Start

O módulo WSGI do projeto é `config.wsgi`:

```bash
gunicorn config.wsgi:application
```

O mesmo comando está declarado no `Procfile` da raiz. Gunicorn é destinado a
Linux/POSIX; no Windows, use o servidor de desenvolvimento apenas localmente.

## Banco PostgreSQL

Em homologação e produção, defina `DATABASE_URL` com uma URL PostgreSQL. Se a
plataforma exigir TLS para o banco, inclua a opção indicada pelo provedor, por
exemplo `sslmode=require`, na própria URL. A URL completa nunca deve ser
registrada em logs ou documentação.

Conexões persistentes usam `DJANGO_DB_CONN_MAX_AGE` e têm health check antes do
reuso. Opções exclusivas do SQLite não são aplicadas ao PostgreSQL.

## Variáveis de ambiente

- `DJANGO_SECRET_KEY`: chave exclusiva e longa; obrigatória com DEBUG falso.
- `DJANGO_DEBUG`: habilita ou desabilita o modo de depuração.
- `DJANGO_ALLOWED_HOSTS`: hosts aceitos, separados por vírgula.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origens HTTPS confiáveis, separadas por vírgula.
- `DATABASE_URL`: conexão PostgreSQL de homologação ou produção.
- `DJANGO_DB_CONN_MAX_AGE`: duração das conexões persistentes, em segundos.
- `DJANGO_DATABASE_PATH`: substituição opcional do SQLite apenas no ambiente local.
- `DJANGO_SQLITE_TIMEOUT`: timeout de escrita do SQLite local.
- `DJANGO_TRUST_X_FORWARDED_PROTO`: confia no protocolo informado pelo proxy.
- `DJANGO_SECURE_SSL_REDIRECT`: redireciona HTTP para HTTPS.
- `DJANGO_SESSION_COOKIE_SECURE`: restringe o cookie de sessão a HTTPS.
- `DJANGO_CSRF_COOKIE_SECURE`: restringe o cookie CSRF a HTTPS.
- `DJANGO_SECURE_HSTS_SECONDS`: duração do HSTS; zero mantém desabilitado.
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`: inclui subdomínios no HSTS.
- `DJANGO_SECURE_HSTS_PRELOAD`: solicita preload de HSTS.
- `DJANGO_EMAIL_BACKEND`: backend de envio de e-mail.
- `DJANGO_DEFAULT_FROM_EMAIL`: remetente padrão.
- `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`: servidor SMTP.
- `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`: autenticação SMTP.
- `DJANGO_EMAIL_USE_TLS`: habilita TLS no SMTP.

Use `.env.example` apenas como referência. O projeto não carrega arquivos `.env`
automaticamente.

## HTTPS e segurança

Em produção, defina explicitamente DEBUG falso, hosts, origens CSRF, cookies
seguros e redirecionamento HTTPS. HSTS, inclusão de subdomínios, preload e
confiança em `X-Forwarded-Proto` permanecem desabilitados até que variáveis
explícitas os habilitem.

Só confie em `X-Forwarded-Proto` quando o proxy remover o cabeçalho recebido do
cliente e recriá-lo com base na conexão externa real.

## Arquivos

WhiteNoise entrega somente os arquivos estáticos coletados em `staticfiles/`.
Com `DEBUG=False`, os arquivos recebem nomes versionados e variantes comprimidas;
no desenvolvimento, o storage simples preserva as URLs usadas pelo `runserver`.
Mídia de usuário, logos personalizados, comprovantes e PDFs permanentes ficam em
`MEDIA_ROOT` e precisarão de armazenamento persistente próprio antes do deploy.
`staticfiles/`, `media/`, bancos e arquivos `.env` permanecem fora do Git.
