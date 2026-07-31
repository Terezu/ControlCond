# Primeira homologação no Render

Este documento prepara a homologação; não executa deploy nem altera DNS.

## Blueprint

O `render.yaml` declara o web service `controlcond-homolog` e o PostgreSQL
exclusivo `controlcond-homolog-db`. O banco começa vazio e recebe somente as
migrations do projeto. Nenhum dado do SQLite local é importado.

O deploy automático começa desabilitado para permitir revisão manual. O build
instala dependências, coleta estáticos e aplica migrations. O start usa:

```bash
gunicorn config.wsgi:application
```

## Variáveis no Render

O Blueprint solicita manualmente a chave secreta, hosts e origens CSRF. Após o
Render informar o subdomínio temporário real, configure:

```text
DJANGO_SECRET_KEY=<chave longa gerada para homologação>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<domínio-temporário-real>.onrender.com,app.controlcond.net.br
DJANGO_CSRF_TRUSTED_ORIGINS=https://<domínio-temporário-real>.onrender.com,https://app.controlcond.net.br
DATABASE_URL=<referenciada automaticamente pelo banco do Blueprint>
DJANGO_DB_CONN_MAX_AGE=60
DJANGO_TRUST_X_FORWARDED_PROTO=True
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False
DJANGO_SECURE_HSTS_PRELOAD=False
DJANGO_LOG_LEVEL=INFO
```

Não substitua o placeholder do domínio antes de o Render fornecer o endereço.
HSTS permanece desabilitado no primeiro deploy.

`SECURE_PROXY_SSL_HEADER` só é definido quando
`DJANGO_TRUST_X_FORWARDED_PROTO=True`. Essa confiança deve permanecer falsa fora
de um proxy que controle e reescreva o cabeçalho `X-Forwarded-Proto`.

## Health check

O Render consulta `GET /healthz/`. A rota executa somente `SELECT 1`, retorna
`{"status":"ok"}` com HTTP 200 ou HTTP 503 quando o banco está indisponível.
Ela não exige autenticação e não expõe configuração, versão ou credenciais.

## Mídia e PDFs

Funciona no primeiro deploy:

- CSS, JavaScript e imagens estáticas coletadas e entregues pelo WhiteNoise;
- PDFs de faturas gerados em memória e enviados diretamente na resposta.

Não é persistente no filesystem efêmero do web service:

- logos enviados por condomínio;
- favicons enviados;
- qualquer arquivo gravado em `media/`.

O PDF ainda acessa a logo personalizada por `configuracao.logo.path`. Antes de
usar um storage remoto, esse trecho deverá ser adaptado e testado para abrir a
imagem pelo Django Storage, por exemplo com `configuracao.logo.open("rb")` e um
stream compatível com o ReportLab. Não há logo padrão estática versionada no
estado atual do projeto.

Para a primeira homologação, escolha conscientemente uma das opções:

1. aceitar uploads apenas como testes descartáveis;
2. desabilitar temporariamente uploads de personalização;
3. configurar posteriormente storage compatível com S3;
4. avaliar disco persistente se o plano permitir e o serviço usar uma única
   instância.

## Superusuário

Depois do primeiro deploy bem-sucedido, abra o Shell do serviço e execute
interativamente:

```bash
python manage.py createsuperuser
```

Não coloque usuário ou senha no Blueprint, em scripts ou arquivos `.env`
versionados.

## Domínio futuro

Somente depois de validar o endereço temporário do Render:

1. adicionar `app.controlcond.net.br` aos domínios do serviço;
2. copiar exatamente o destino DNS informado pelo Render;
3. criar no Registro.br o registro solicitado para o subdomínio `app`;
4. aguardar a propagação;
5. verificar o domínio no painel do Render;
6. confirmar a emissão automática do certificado HTTPS;
7. confirmar `app.controlcond.net.br` em `DJANGO_ALLOWED_HOSTS` e a origem HTTPS
   em `DJANGO_CSRF_TRUSTED_ORIGINS`.

Não é necessário alterar o domínio raiz `controlcond.net.br` nesta etapa.
