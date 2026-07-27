# ControlCond — teste externo local

## Objetivo desta versão

Esta branch prepara o ControlCond para validação funcional em um computador
local. O banco é criado no equipamento do tester e nenhum dado, credencial ou
arquivo gerado de outro ambiente é necessário.

> Use somente dados fictícios. Esta versão não deve receber dados pessoais,
> financeiros ou documentos reais.

## Requisitos

- Git;
- Python 3.14.3;
- navegador atualizado (Chrome, Edge ou Firefox);
- Windows 10/11, Linux ou macOS com suporte ao Python indicado;
- acesso autorizado ao repositório privado.

## 1. Clonar a branch correta

Substitua `<URL_DO_REPOSITORIO_PRIVADO>` pela URL fornecida pelo responsável:

```console
git clone --branch release/teste-externo --single-branch <URL_DO_REPOSITORIO_PRIVADO> ControlCond
cd ControlCond
```

Confirme:

```console
git branch --show-current
```

O resultado deve ser `release/teste-externo`.

## 2. Criar e ativar o ambiente virtual

Crie o ambiente:

```console
python -m venv .venv
```

No Windows CMD:

```bat
.venv\Scripts\activate.bat
```

No PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

No Linux/macOS:

```bash
source .venv/bin/activate
```

Quando estiver ativo, o terminal normalmente exibirá `(.venv)`.

## 3. Instalar dependências

```console
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 4. Criar a configuração local

No Windows CMD:

```bat
copy .env.example .env
```

No PowerShell:

```powershell
Copy-Item .env.example .env
```

No Linux/macOS:

```bash
cp .env.example .env
```

Abra `.env` e substitua `DJANGO_SECRET_KEY` por uma chave longa e exclusiva
para este teste local. Mantenha:

- `DJANGO_DEBUG=True`;
- `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`;
- `DJANGO_DATABASE_PATH=controlcond.db`;
- as opções HTTPS como `False`, pois o servidor local usa HTTP.

O arquivo `.env` é carregado somente quando existe e não substitui variáveis
definidas diretamente pelo sistema operacional.

## 5. Preparar o banco vazio

```console
python manage.py migrate
python manage.py check
python manage.py createsuperuser
```

Escolha usuário, e-mail fictício e senha exclusivos para o teste. O arquivo
`controlcond.db` será criado localmente e não deve ser compartilhado.

## 6. Iniciar e acessar

```console
python manage.py runserver
```

Acesse:

- aplicação: <http://127.0.0.1:8000/>
- administração: <http://127.0.0.1:8000/admin/>

Para encerrar, retorne ao terminal e pressione `Ctrl+C`.

## 7. Executar testes automatizados

```console
python manage.py test
```

Para verificar migrações ainda não geradas:

```console
python manage.py makemigrations --check --dry-run
```

## Problemas comuns

### PowerShell bloqueia a ativação

Use o CMD com `.venv\Scripts\activate.bat` ou libere scripts apenas no processo
atual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Python não foi encontrado

Confirme `python --version`. No Windows, tente `py -3.14 --version` e substitua
`python` por `py -3.14` nos comandos. Se a versão não existir, instale Python
3.14.3 e marque a opção para adicioná-lo ao `PATH`.

### Porta 8000 ocupada

Use outra porta:

```console
python manage.py runserver 8001
```

Depois acesse <http://127.0.0.1:8001/>.

### Dependência não instalada

Com o ambiente virtual ativo:

```console
python -m pip install -r requirements.txt
python -m pip check
```

### Migrações pendentes ou coluna inexistente

```console
python manage.py showmigrations
python manage.py migrate
```

Não copie um banco de outro ambiente para contornar esse erro.

## Segurança durante o teste

- não compartilhar ou versionar `.env`;
- não compartilhar `controlcond.db` nem seus backups;
- não usar nomes, documentos, endereços ou informações bancárias reais;
- não enviar PDFs ou ZIPs com dados reais;
- não publicar capturas, logs ou gravações sem revisar seu conteúdo;
- apagar os dados locais ao final conforme orientação do responsável pelo teste.

## Estado inicial esperado

Não há fixture ou seed de demonstração nesta versão. Após criar o
superusuário, cadastre pela interface somente condomínios e dados fictícios.
O roteiro completo está em `ROTEIRO_TESTES.md`.
