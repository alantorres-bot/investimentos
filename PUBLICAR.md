# Publicar o app na internet (celular, com login)

Passo a passo para deixar o Painel de Investimentos acessível de qualquer lugar,
com usuário e senha, usando **Streamlit Community Cloud** (app) + **Supabase**
(banco de dados). Os dois são gratuitos nos planos que você vai usar.

O código já está pronto para isso: ele usa o `rendimentos.db` local quando não há
`DATABASE_URL` configurada, e o Postgres do Supabase quando há.

Tempo estimado: 40 minutos. Me chame em qualquer etapa que eu executo a parte
técnica.

---

## 1. Criar o banco no Supabase

1. Entre em https://supabase.com e crie a conta (pode usar a conta Google).
2. **New project**:
   - *Name*: `investimentos`
   - *Database Password*: gere uma senha forte e **guarde no seu gerenciador de
     senhas** — ela faz parte da string de conexão.
   - *Region*: `South America (São Paulo)`.
3. Aguarde o projeto subir (± 2 minutos).
4. Vá em **Project Settings → Database → Connection string → URI** e copie o
   endereço. Ele se parece com:

   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
   ```

   Troque `[YOUR-PASSWORD]` pela senha do passo 2.

> Use a string do **Connection pooling** (porta 6543). É a recomendada para apps
> que abrem e fecham conexões, como este.

## 2. Definir a senha do app

No terminal, dentro da pasta do projeto:

```powershell
.venv\Scripts\python.exe gerar_senha.py
```

Ele pede usuário e senha (a senha não aparece na tela nem é gravada) e imprime
duas linhas prontas para colar nos secrets. **A senha digitada nunca é guardada
em lugar nenhum — só o hash.**

## 3. Configurar o acesso local

Copie `.streamlit/secrets.toml.exemplo` para `.streamlit/secrets.toml` e preencha:

```toml
APP_USUARIO = "alan"
APP_SENHA_HASH = "pbkdf2_sha256$240000$...$..."
DATABASE_URL = "postgresql://postgres.xxxx:SENHA@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
```

Esse arquivo está no `.gitignore` e **não vai para o GitHub**.

## 4. Levar seus dados para a nuvem

```powershell
.venv\Scripts\python.exe migrar_para_postgres.py
```

O script cria as tabelas no Supabase, copia investimentos, rendimentos,
movimentações e faturas de energia, e confere os totais no fim. Ele se recusa a
rodar se o destino já tiver dados (evita duplicar) — use `--recriar` se precisar
refazer a carga do zero.

Depois disso, rode o app local (`INICIAR INVESTIMENTOS.bat`). A barra lateral deve
mostrar **Banco: PostgreSQL (nuvem)** e pedir login.

## 5. Publicar o código no GitHub

```powershell
cd C:\Users\alant\investimentos
git init
git add .
git commit -m "Painel de Investimentos"
```

Crie um repositório **privado** em https://github.com/new (ex.: `investimentos`)
e siga as instruções de "push an existing repository":

```powershell
git remote add origin https://github.com/SEU-USUARIO/investimentos.git
git branch -M main
git push -u origin main
```

Confira antes do push: `git status` não pode listar `secrets.toml` nem
`rendimentos.db`.

## 6. Publicar o app

1. Entre em https://share.streamlit.io com a conta do GitHub.
2. **Create app → Deploy a public app from a repo**, e aponte para o repositório:
   - *Repository*: `SEU-USUARIO/investimentos`
   - *Branch*: `main`
   - *Main file path*: `app.py`
3. Em **Advanced settings → Secrets**, cole as três linhas do seu
   `secrets.toml` (usuário, hash e `DATABASE_URL`).
4. **Deploy**. Em 2–3 minutos o app estará no ar em
   `https://SEU-APP.streamlit.app`.

Como o `DATABASE_URL` está presente, o app **exige login** — sem senha
configurada ele se recusa a abrir, para nunca ficar exposto.

## 7. Usar no celular

Abra o endereço no Chrome (Android) ou Safari (iPhone) e use **Adicionar à tela
de início**. Ele passa a abrir como um aplicativo, em tela cheia, sem a barra do
navegador.

A interface já se adapta à tela pequena: os indicadores empilham, as tabelas
rolam na horizontal e a barra lateral vira um menu no canto.

---

## Depois de publicado

- **Alterar o app**: edite os arquivos, `git commit` e `git push`. O Streamlit
  Cloud republica sozinho em cerca de um minuto.
- **Backup**: o botão de backup do app só funciona no modo local (SQLite). Na
  nuvem, use *Exportar Excel* para guardar uma cópia, e o próprio Supabase mantém
  backups diários do banco.
- **Trocar a senha**: rode `gerar_senha.py` de novo e atualize o valor em
  *Settings → Secrets* no Streamlit Cloud.
- **Voltar ao modo local**: comente a linha `DATABASE_URL` no `secrets.toml`. O
  app volta a usar o `rendimentos.db` do seu computador.

## Segurança

- A senha do banco e o hash do login ficam apenas nos secrets — nunca no
  repositório.
- Mantenha o repositório **privado**: mesmo sem segredos, o código descreve seus
  investimentos.
- O login protege a tela, mas quem tiver o endereço vai ver a página de login.
  Se quiser um nível a mais, dá para restringir o app por e-mail nas
  configurações do Streamlit Cloud.
