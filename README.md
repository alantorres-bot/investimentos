# Painel de Investimentos

App local para registrar, mês a mês, quanto cada investimento rendeu — Tesouro Direto,
dinheiro emprestado a juros, crédito de energia solar, aluguel e o que mais você tiver.
Roda no seu computador, sem login, sem servidor e sem serviço externo: os dados ficam
no arquivo `rendimentos.db`, nesta mesma pasta.

## Onde o app roda

Por padrão, no seu computador, com os dados no arquivo `rendimentos.db`. Ele também
roda publicado na internet (celular, de qualquer lugar, com login) usando o Postgres
do Supabase — o passo a passo está em **[PUBLICAR.md](PUBLICAR.md)**.

O que decide isso é o `DATABASE_URL` nos secrets: sem ele, banco local; com ele, banco
na nuvem. A barra lateral sempre mostra qual está em uso.

## Como abrir

Dê **duplo clique em `INICIAR INVESTIMENTOS.bat`**. Ele abre o app no navegador
(http://localhost:8501). Para encerrar, feche a janela preta.

Na primeira vez o próprio `.bat` cria o ambiente e instala as dependências.

### Pelo terminal

```powershell
cd C:\Users\alant\investimentos
python -m venv .venv                       # só na primeira vez
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

## As páginas

| Página | Para quê |
|---|---|
| **Painel** | Total recebido no ano, média mensal, capital investido e retorno médio mensal; gráfico por mês e matriz investimentos × meses |
| **Investimentos** | Cadastrar, editar, encerrar/reativar e excluir investimentos; registrar empréstimos sem juros, aportes, resgates e impostos pagos |
| **Evolução** | Gráfico do patrimônio mês a mês, com projeção de 12 meses (realizado × previsto) |
| **Lançar rendimento** | Informar quanto cada investimento rendeu em um mês |
| **Energia solar** | Calculadora da economia na conta de luz, mês a mês, com payback do sistema |
| **Importar extratos** | Ler os extratos analíticos do Tesouro Direto e lançar os meses automaticamente |
| **Exportar** | Baixar a planilha `.xlsx` do ano e fazer backup do banco |

## Como usar no dia a dia

1. **Cadastre o investimento** (nome, categoria, capital, mês de início). A taxa mensal
   é opcional — se você informar, o app sugere o valor do rendimento nos lançamentos e
   mostra a estimativa na matriz do painel.
2. **Lance o rendimento** de cada mês. Só existe um lançamento por investimento por mês:
   se você lançar o mesmo mês de novo, o valor é atualizado (não duplica).
3. **Confira no painel**, filtrando por ano.
4. **Exporte para Excel** quando quiser levar os números para outro lugar, e faça
   **backup** de vez em quando (o arquivo vai para a pasta `backups`).

### Estimativas

Na matriz do painel, meses sem lançamento de investimentos ativos que tenham taxa
cadastrada aparecem em cinza com `~` (ex.: `~ R$ 1.500,00`). É só projeção:
**estimativas não entram nos totais nem nos indicadores**.

### Empréstimos sem juros

Dinheiro emprestado a alguém sem cobrança de juros entra na aba **Investimentos →
Empréstimo sem juros**. Basta informar para quem, o valor e a data: o app cria o
registro e o aporte do mês, então o valor **passa a compor o patrimônio** como direito
a receber, sem gerar nenhum rendimento.

Quando a pessoa pagar, use *Registrar devolução* — aceita devolução parcial, atualiza o
saldo em aberto e encerra o empréstimo sozinho quando o saldo zera.

Como esse capital não rende, ele reduz a taxa de retorno da carteira: o patrimônio cresce
sem que o rendimento acompanhe. É o comportamento correto, mas vale lembrar ao olhar o
indicador de retorno médio.

### Evolução e projeção

O patrimônio começa em zero e cresce conforme o dinheiro entra e rende:

```
patrimônio(mês) = Σ aportes − Σ resgates − Σ impostos pagos
                + Σ rendimentos, tudo até aquele mês
```

Para a linha refletir a realidade, os aportes e resgates precisam estar registrados na
página **Investimentos → Aportes e resgates**. Sem eles o gráfico não tem como saber
quando cada valor entrou.

A linha cheia verde é o realizado; a tracejada cinza é a projeção de 12 meses, que
repete a taxa do **último mês fechado** — o rendimento daquele mês dividido pelo
patrimônio do início dele —, capitalizando mês a mês. O mês em curso não entra nessa
conta, porque o rendimento dele ainda é parcial e puxaria a projeção para baixo. A taxa vem preenchida nesse valor e pode ser
alterada na tela, e há um campo de **aporte mensal previsto** para simular quanto o
patrimônio cresce se você continuar aplicando.

É projeção de ritmo atual, não promessa: uma taxa de um mês só, mantida por doze.
Lembre que a economia da energia solar reduz despesa (não vira saldo aplicado) e que
juros de empréstimo marcados como “a receber” ainda não entraram no caixa.

### Energia solar

A distribuidora não paga nada em dinheiro: o retorno do sistema é a **economia na conta
de luz**. A página Energia solar calcula essa economia a partir dos dados da fatura
(DANF3E da Energisa):

```
custo sem solar = consumo (kWh) × tarifa cheia com tributos
                + contribuição de iluminação pública + adicional de bandeira
custo com solar = total pago na fatura − multa/juros de atraso
economia do mês = custo sem solar − custo com solar
```

Multa e juros de atraso ficam de fora porque são custo de atraso no pagamento, não do
sistema. Cada campo do formulário traz, no ícone de ajuda, onde encontrá-lo na fatura.

Ao salvar, a fatura fica guardada e a economia é lançada como rendimento daquele mês.
A página ainda mostra economia acumulada, média mensal, retorno sobre o investimento e
**payback estimado**. O saldo de créditos em kWh é registrado à parte: é economia futura
já garantida, que ainda não entrou na conta.

### Importação do Tesouro Direto

O extrato analítico (Tesouro Direto / Nu Investimentos) mostra a posição de cada
aplicação no fim do mês, não o rendimento. O app calcula assim:

```
rendimento do mês = valor bruto do mês
                  - valor bruto do mês anterior
                  - aplicações feitas no mês
                  + resgates do mês
```

Por isso:

- envie **meses seguidos**; o primeiro mês da sequência precisa do extrato do mês
  anterior, senão o valor sai como ganho acumulado (o app avisa quando isso acontece);
- **meses com resgate ficam marcados como estimados** — o extrato não informa o valor
  recebido no resgate, então ele é calculado pelo preço médio do título. Confira o mês
  e ajuste na página "Lançar rendimento" se necessário;
- o valor lançado é o **rendimento bruto** (antes de IR/IOF);
- cada título vira um investimento. Você escolhe se cria um novo ou lança em um já
  cadastrado.

## Backup

O botão de backup copia `rendimentos.db` para `backups\rendimentos_AAAAMMDD_HHMMSS.db`.
Para restaurar, feche o app e substitua o `rendimentos.db` pela cópia desejada.

## Arquivos

```
app.py                    interface (as sete páginas)
db.py                     banco (SQLite ou Postgres), validações e consultas
auth.py                   tela de login e verificação da senha
importador.py             leitura dos extratos analíticos do Tesouro Direto
solar.py                  cálculo da economia e do retorno da energia solar
patrimonio.py             patrimônio realizado e projeção de 12 meses
gerar_senha.py            gera o hash da senha para os secrets
migrar_para_postgres.py   leva os dados locais para o banco na nuvem
PUBLICAR.md               passo a passo para publicar na internet
rendimentos.db            seus dados no modo local (criado automaticamente)
backups/                  cópias do banco local
```

## Login

Sem senha configurada, o app abre direto (uso local). Para exigir login, gere o hash
com `.venv\Scripts\python.exe gerar_senha.py` e coloque `APP_USUARIO` e
`APP_SENHA_HASH` em `.streamlit/secrets.toml`. No app publicado a senha é
obrigatória — ele se recusa a abrir sem ela.
