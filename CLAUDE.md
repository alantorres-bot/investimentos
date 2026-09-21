# CLAUDE.md — Painel de Investimentos

App pessoal do Alan para acompanhar, mês a mês, o rendimento de cada investimento
(Tesouro Direto, empréstimos a juros, crédito de energia solar, aluguel etc.).
Uso local, um usuário, sem login e sem serviço externo.

## Stack e execução

- Python 3.13 + Streamlit + SQLAlchemy, pandas/openpyxl para Excel, altair para o gráfico.
- **Dois bancos, um código**: sem `DATABASE_URL` usa SQLite local; com `DATABASE_URL`
  (ambiente ou `st.secrets`) usa o Postgres do Supabase. `db.criar_schema()` ajusta o DDL
  ao dialeto (`SERIAL`/`AUTOINCREMENT`, `DOUBLE PRECISION`/`REAL`). Todo SQL novo precisa
  funcionar nos dois: use parâmetros nomeados (`:nome`), `RETURNING id` em vez de
  `lastrowid` e `LOWER(...)` em vez de `COLLATE NOCASE`.
- As funções de `db.py` devolvem **dicionários**, não `sqlite3.Row`.
- Ambiente virtual próprio em `.venv` — nunca instalar no Python global.
- Rodar: `.venv\Scripts\streamlit run app.py`, ou duplo clique em `INICIAR INVESTIMENTOS.bat`.
- Banco: `rendimentos.db`, criado ao lado do código por `db.criar_schema()` no start do app.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | Toda a interface: sete páginas registradas no dicionário `PAGINAS` no fim do arquivo |
| `db.py` | Acesso ao SQLite, validações de entrada e consultas agregadas |
| `importador.py` | Leitura dos extratos analíticos do Tesouro Direto e cálculo do rendimento por mês |
| `solar.py` | Cálculo da economia mensal e do retorno do sistema de energia solar |
| `patrimonio.py` | Série do patrimônio realizado e projeção para os próximos 12 meses |
| `auth.py` | Login: hash PBKDF2 da senha, tela de entrada e botão de sair |
| `tema.py` | Identidade visual: paleta, CSS global, número-herói e eixo dos gráficos |
| `migrar_para_postgres.py` | Carga única dos dados locais para o Supabase |

## Convenções

- **Tudo em português do Brasil**: nomes de funções, variáveis, docstrings, comentários e
  textos de tela. Valores em reais no formato `R$ 1.234,56` (`formatar_real` em `app.py`).
- **Competência** é sempre a string `AAAA-MM` no banco e nas funções; na tela aparece como
  `MM/AAAA` (`db.formatar_competencia`). O controle começa em `db.MES_INICIAL` = `2026-01`.
- **Validação mora em `db.py`**, não na interface: as funções levantam `ValueError` com
  mensagem pronta em português, e a página exibe com `st.error`.
- **Um lançamento por investimento por mês**: garantido por `UNIQUE (investimento_id,
  competencia)` e por `salvar_rendimento`, que faz upsert (relançar o mês atualiza o valor).
- **Textos com `R$` passam por `md()`** antes de ir para `st.caption`/`st.warning`/`st.metric`:
  sem isso o Streamlit trata dois cifrões na mesma frase como fórmula LaTeX.
- Mensagens após uma ação usam `guardar_flash(...)` + `st.rerun()`; a página seguinte
  chama `mostrar_flash()` logo após o cabeçalho.
- Widgets que dependem de outro widget (valor sugerido do rendimento) ficam **fora** de
  `st.form`, com `key` composta (`f"valor_{inv_id}_{competencia}"`) para recarregarem o
  valor padrão quando a seleção muda.

## Regras de negócio

- **Estimativas** (`capital × taxa_mensal / 100`) só aparecem na matriz do painel, em
  cinza e prefixadas por `~`. Nunca entram em totais, gráfico ou indicadores. São
  calculadas apenas para investimentos ativos, com taxa, a partir do `mes_inicio`.
- **Encerrar** um investimento (`ativo = 0`) preserva o histórico e apenas interrompe as
  estimativas. Excluir é definitivo e apaga os lançamentos em cascata.
- **Indicadores do painel**: total do ano; média mensal = total ÷ meses com lançamento;
  capital investido = soma dos investimentos ativos; retorno médio mensal = média ÷ capital.
- **Importação do Tesouro Direto** (`importador.py`): o extrato analítico traz posição, não
  rendimento. `rendimento = bruto do mês − bruto do mês anterior − aplicações do mês +
  resgates`. Resgates não vêm em valor no extrato; são deduzidos da queda na quantidade de
  títulos e valorados pelo preço médio — esses meses voltam com `estimado=True` e aviso.
  O primeiro mês de uma sequência que já tenha aplicações anteriores também é sinalizado,
  porque o número seria o ganho acumulado. O valor gravado é o **bruto** (antes de IR/IOF).

- **Energia solar** (`solar.py` + tabela `faturas_solar`): o retorno é a economia na
  conta de luz, não dinheiro recebido. `economia = (consumo × tarifa cheia + iluminação
  pública + bandeira) − (total pago − mora)`. Multa/juros de atraso saem do cálculo por
  serem custo de atraso, não do sistema. Salvar a fatura grava também o rendimento do mês
  (`db.salvar_rendimento`), e excluir a fatura apaga os dois. O saldo de créditos em kWh
  é só acompanhamento: nunca entra em totais.

- **Evolução do patrimônio** (`patrimonio.py` + tabela `movimentacoes`): o patrimônio
  parte de zero e é `Σ aportes − Σ resgates − Σ impostos + Σ rendimentos` até o mês.
  Nunca use `capital_total()` como base da série: o capital de hoje não valia em janeiro.
  A projeção usa a taxa do **último mês fechado** (`taxa_ultimo_mes_fechado`) — rendimento
  daquele mês sobre o patrimônio do início dele, sem contar aportes — capitalizada por
  12 meses, com aporte mensal previsto opcional. O mês corrente nunca serve de base: seu
  rendimento é parcial. Meses fechados sem rendimento lançado também são pulados. O último ponto realizado
  é duplicado na série prevista para as duas linhas se encontrarem no gráfico, e o eixo Y
  usa `zero=False` para a curva não achatar.

- **Empréstimos sem juros** (categoria `Empréstimo sem juros`): criados por
  `db.criar_emprestimo_avulso`, que cria o investimento **e** o aporte na mesma chamada —
  sem aporte o valor não apareceria no patrimônio. Nunca recebem lançamento de rendimento.
  `db.registrar_devolucao` grava o resgate, baixa o capital e encerra o investimento
  quando `saldo_emprestimo` chega a zero; devolução maior que o saldo é recusada.

## Identidade visual

- Paleta validada pelo método de data-viz: **verde `#1baf7a`** (realizado, rendimento),
  **azul `#2a78d6`** (patrimônio/capital), **cinza `#9aa0a6`** (previsto e estimativa).
  Passa nos testes de daltonismo; o verde tem contraste 2,74 sobre o fundo claro, então
  só aparece em marcas (barras, linhas, selos com fundo) — **nunca como cor de texto**.
- Tema claro definido em `.streamlit/config.toml`; o CSS global vive em
  `tema.aplicar_estilo()`, chamado uma vez no topo de `app.py`.
- Cada página começa com `tema.cabecalho(titulo, subtitulo)`; a tela principal usa
  `tema.numero_heroi(...)` para o patrimônio. O herói recebe HTML puro — **não** passe o
  texto por `md()` ali, senão a barra invertida do escape aparece na tela; use `&nbsp;`
  para os espaços do selo, que o Streamlit remove ao sanitizar o HTML.
- Gráficos Altair passam por `tema.eixo_limpo(...)`: sem grade vertical, grade
  horizontal discreta, eixos recessivos. Barras com canto arredondado de 4px no topo.
- Navegação: `st.navigation` com três grupos (Acompanhar, Registrar, Ferramentas). Ela
  é sempre renderizada no topo da barra lateral — o que for escrito antes aparece
  **abaixo** dela, por isso a marca fica no rodapé.

## Ao alterar

- Nova página: escreva `pagina_xxx()` e registre em `PAGINAS`.
- Nova coluna no banco: `criar_schema()` precisa continuar idempotente e não pode quebrar
  bancos existentes (use `ALTER TABLE ... ADD COLUMN` protegido por checagem).
- Teste com `.venv\Scripts\python.exe app.py` (bare mode) para pegar erro de sintaxe/import,
  e depois no navegador com `streamlit run`.
- Ao mudar `db.py`, `solar.py`, `importador.py` ou `patrimonio.py`, **reinicie o servidor**:
  o Streamlit recarrega `app.py` a cada save, mas mantém os módulos importados em memória,
  e a tela quebra com `AttributeError` em nomes recém-criados.
