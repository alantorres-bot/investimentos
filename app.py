"""Painel de Investimentos — controle mensal de rendimentos.

Execute com:  streamlit run app.py
"""

from __future__ import annotations

import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import auth
import db
import importador
import patrimonio
import solar

st.set_page_config(
    page_title="Painel de Investimentos",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

if db.banco_local_indevido():
    st.error(
        "**Configuração incompleta: o app não está conectado ao banco na nuvem.** "
        "Falta a linha `DATABASE_URL` nos secrets do aplicativo — sem ela o app cria "
        "um banco vazio a cada reinício, e os seus dados (que estão no Supabase, "
        "intactos) não aparecem. Vá em *Manage app → Settings → Secrets*, cole as três "
        "linhas de configuração e reinicie o app."
    )
    st.stop()

# No app publicado (banco na nuvem) a senha é obrigatória; localmente é opcional.
auth.exigir_login(exigir_sempre=db.usando_postgres())

db.criar_schema()

# Deixa números e tabelas legíveis em tela de celular.
st.markdown(
    """
    <style>
      @media (max-width: 640px) {
        [data-testid="stMetricValue"] { font-size: 1.35rem; }
        [data-testid="stMetricLabel"] { font-size: 0.78rem; }
        .block-container { padding-top: 2.5rem; padding-left: 1rem; padding-right: 1rem; }
        h1 { font-size: 1.6rem; }
        h2 { font-size: 1.3rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------- utilitários ---

def formatar_real(valor) -> str:
    """1234.5 -> 'R$ 1.234,50'."""
    if valor is None:
        return ""
    texto = f"{float(valor):,.2f}"
    texto = texto.replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {texto}"


def md(texto: str) -> str:
    """Escapa o cifrão para o Streamlit não tratar 'R$ ... R$' como fórmula."""
    return str(texto).replace("$", r"\$")


def formatar_taxa(taxa) -> str:
    if taxa is None:
        return "—"
    return f"{float(taxa):.2f}".replace(".", ",") + "%"


def mostrar_flash() -> None:
    """Exibe a mensagem guardada antes do último rerun."""
    flash = st.session_state.pop("flash", None)
    if flash:
        tipo, texto = flash
        getattr(st, tipo)(md(texto))


def guardar_flash(tipo: str, texto: str) -> None:
    st.session_state["flash"] = (tipo, texto)


def seletor_competencia(rotulo: str, valor_inicial: str, chave: str) -> str:
    """Dois selects (mês e ano) devolvendo a competência AAAA-MM."""
    anos = list(range(db.ANO_INICIAL, max(db.anos_disponiveis()) + 2))
    ano_ini, mes_ini = int(valor_inicial[:4]), int(valor_inicial[5:])
    if ano_ini not in anos:
        anos.append(ano_ini)
        anos.sort()

    st.caption(rotulo)
    col_mes, col_ano = st.columns(2)
    mes = col_mes.selectbox(
        "Mês",
        options=list(range(1, 13)),
        index=mes_ini - 1,
        format_func=lambda m: db.MESES[m - 1],
        key=f"{chave}_mes",
    )
    ano = col_ano.selectbox(
        "Ano",
        options=anos,
        index=anos.index(ano_ini),
        key=f"{chave}_ano",
    )
    return db.competencia_de(ano, mes)


def rotulo_investimento(inv) -> str:
    marca = "" if inv["ativo"] else "  (encerrado)"
    return f"{inv['nome']} — {inv['categoria']}{marca}"


# --------------------------------------------------- página: investimentos ---

def pagina_investimentos() -> None:
    st.header("Investimentos")
    mostrar_flash()

    investimentos = db.listar_investimentos()

    if investimentos:
        linhas = [
            {
                "Nome": inv["nome"],
                "Categoria": inv["categoria"],
                "Capital": formatar_real(inv["capital"]),
                "Taxa mensal": formatar_taxa(inv["taxa_mensal"]),
                "Início": db.formatar_competencia(inv["mes_inicio"]),
                "Situação": "Ativo" if inv["ativo"] else "Encerrado",
                "Observações": inv["observacoes"] or "",
            }
            for inv in investimentos
        ]
        st.dataframe(linhas, width="stretch", hide_index=True)
        ativos = sum(1 for inv in investimentos if inv["ativo"])
        st.caption(md(
            f"{len(investimentos)} investimento(s) cadastrado(s) · {ativos} ativo(s) · "
            f"capital dos ativos: {formatar_real(db.capital_total())}"
        ))
    else:
        st.info("Nenhum investimento cadastrado ainda. Use o formulário abaixo.")

    aba_novo, aba_avulso, aba_editar, aba_mov = st.tabs(
        ["Novo investimento", "Empréstimo sem juros", "Editar / encerrar",
         "Aportes e resgates"]
    )

    with aba_novo:
        _formulario_investimento()

    with aba_avulso:
        _emprestimos_sem_juros()

    with aba_editar:
        if not investimentos:
            st.info("Cadastre um investimento primeiro.")
        else:
            opcoes = {rotulo_investimento(inv): inv["id"] for inv in investimentos}
            escolhido = st.selectbox(
                "Investimento", list(opcoes.keys()), key="edit_escolha"
            )
            inv = db.obter_investimento(opcoes[escolhido])
            _formulario_investimento(inv)
            _acoes_investimento(inv)

    with aba_mov:
        if not investimentos:
            st.info("Cadastre um investimento primeiro.")
        else:
            _movimentacoes_capital(investimentos)


def _emprestimos_sem_juros() -> None:
    """Empréstimos avulsos: entram no patrimônio, mas não rendem juros."""
    st.caption(
        "Dinheiro emprestado sem cobrança de juros. Entra no patrimônio como valor a "
        "receber e sai quando a pessoa devolver — nenhum rendimento é lançado."
    )

    with st.form("form_avulso", clear_on_submit=True):
        col1, col2 = st.columns([2, 1])
        nome = col1.text_input(
            "Para quem", placeholder="ex.: João da Silva", key="avulso_nome"
        )
        valor = col2.number_input(
            "Valor emprestado (R$)", min_value=0.0, step=100.0, format="%.2f",
            key="avulso_valor",
        )
        col3, col4 = st.columns([1, 2])
        data = col3.date_input(
            "Data do empréstimo",
            value=datetime.now().date(),
            min_value=datetime(db.ANO_INICIAL, 1, 1).date(),
            format="DD/MM/YYYY",
            key="avulso_data",
        )
        observacoes = col4.text_input("Observação", key="avulso_obs")
        enviado = st.form_submit_button("Registrar empréstimo", type="primary")

    if enviado:
        try:
            if valor <= 0:
                raise ValueError("Informe o valor emprestado.")
            db.criar_emprestimo_avulso(
                nome=nome,
                valor=valor,
                competencia=db.competencia_de(data.year, data.month),
                data=data.strftime("%d/%m/%Y"),
                observacoes=observacoes,
            )
            guardar_flash(
                "success",
                f"Empréstimo de {formatar_real(valor)} a {nome.strip()} registrado "
                f"em {data:%d/%m/%Y}.",
            )
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))

    emprestimos = [
        inv for inv in db.listar_investimentos()
        if inv["categoria"] == db.CATEGORIA_SEM_JUROS
    ]
    if not emprestimos:
        st.info("Nenhum empréstimo sem juros registrado.")
        return

    st.divider()
    st.subheader("Empréstimos registrados")
    linhas, em_aberto = [], 0.0
    for inv in emprestimos:
        movs = db.listar_movimentacoes(inv["id"])
        emprestado = sum(float(m["valor"]) for m in movs if m["tipo"] == "aporte")
        devolvido = sum(float(m["valor"]) for m in movs if m["tipo"] == "resgate")
        saldo = db.saldo_emprestimo(inv["id"])
        em_aberto += saldo
        linhas.append({
            "Para quem": inv["nome"],
            "Data": next((m["data"] for m in movs if m["data"]), "—"),
            "Emprestado": formatar_real(emprestado),
            "Devolvido": formatar_real(devolvido),
            "Em aberto": formatar_real(saldo),
            "Situação": "Quitado" if saldo <= 0.005 else "Em aberto",
            "Observação": inv["observacoes"] or "",
        })
    st.dataframe(linhas, width="stretch", hide_index=True)
    st.caption(md(f"Total ainda emprestado: {formatar_real(em_aberto)}"))

    abertos = [inv for inv in emprestimos if db.saldo_emprestimo(inv["id"]) > 0.005]
    if not abertos:
        return

    with st.expander("Registrar devolução"):
        opcoes = {
            f"{inv['nome']} — em aberto {formatar_real(db.saldo_emprestimo(inv['id']))}":
                inv["id"]
            for inv in abertos
        }
        escolhido = st.selectbox("Empréstimo", list(opcoes.keys()), key="dev_inv")
        alvo = opcoes[escolhido]
        saldo = db.saldo_emprestimo(alvo)

        col1, col2 = st.columns(2)
        valor_dev = col1.number_input(
            "Valor devolvido (R$)", min_value=0.0, max_value=float(saldo),
            step=100.0, format="%.2f", value=float(saldo), key="dev_valor",
        )
        data_dev = col2.date_input(
            "Data da devolução", value=datetime.now().date(),
            min_value=datetime(db.ANO_INICIAL, 1, 1).date(),
            format="DD/MM/YYYY", key="dev_data",
        )
        st.caption("Devolução parcial é aceita: o saldo em aberto é atualizado.")
        if st.button("Registrar devolução", key="btn_devolucao"):
            try:
                restante = db.registrar_devolucao(
                    alvo,
                    db.competencia_de(data_dev.year, data_dev.month),
                    valor_dev,
                    data_dev.strftime("%d/%m/%Y"),
                )
                guardar_flash(
                    "success",
                    f"Devolução de {formatar_real(valor_dev)} registrada."
                    + (
                        f" Saldo em aberto: {formatar_real(restante)}."
                        if restante > 0.005
                        else " Empréstimo quitado e encerrado."
                    ),
                )
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))


def _movimentacoes_capital(investimentos) -> None:
    """Registro do dinheiro que entra e sai — base da evolução do patrimônio."""
    st.caption(
        "Registre aqui quando o dinheiro entrou e saiu de cada investimento. "
        "É o que permite ao gráfico de evolução partir do zero e acompanhar os aportes "
        "no tempo, em vez de supor o capital de hoje desde janeiro."
    )

    opcoes = {rotulo_investimento(inv): inv["id"] for inv in investimentos}
    escolhido = st.selectbox("Investimento", list(opcoes.keys()), key="mov_inv")
    inv = db.obter_investimento(opcoes[escolhido])

    with st.form("form_movimentacao", clear_on_submit=True):
        col1, col2 = st.columns(2)
        tipo = col1.selectbox(
            "Tipo",
            db.TIPOS_MOVIMENTACAO,
            format_func=lambda t: {
                "aporte": "Aporte (entrada de dinheiro)",
                "resgate": "Resgate (saída de dinheiro)",
                "imposto": "Imposto pago (IR/IOF retido)",
            }[t],
            key="mov_tipo",
        )
        valor = col2.number_input(
            "Valor (R$)", min_value=0.0, step=100.0, format="%.2f", key="mov_valor"
        )
        competencia = seletor_competencia("Competência", db.MES_INICIAL, "mov_comp")
        col3, col4 = st.columns(2)
        data = col3.text_input(
            "Data (opcional)", placeholder="dd/mm/aaaa", key="mov_data"
        )
        observacao = col4.text_input("Observação", key="mov_obs")
        enviado = st.form_submit_button("Registrar movimentação", type="primary")

    if enviado:
        try:
            db.salvar_movimentacao(inv["id"], competencia, tipo, valor, data, observacao)
            guardar_flash(
                "success",
                f"{tipo.capitalize()} de {formatar_real(valor)} registrado em "
                f"{db.formatar_competencia(competencia)} — {inv['nome']}.",
            )
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))

    movimentacoes = db.listar_movimentacoes(inv["id"])
    if not movimentacoes:
        st.info("Nenhuma movimentação registrada para este investimento.")
        return

    st.dataframe(
        [
            {
                "Competência": db.formatar_competencia(m["competencia"]),
                "Data": m["data"] or "—",
                "Tipo": m["tipo"].capitalize(),
                "Valor": formatar_real(m["valor"]),
                "Observação": m["observacao"] or "",
            }
            for m in movimentacoes
        ],
        width="stretch",
        hide_index=True,
    )
    liquido = sum(
        float(m["valor"]) if m["tipo"] == "aporte" else -float(m["valor"])
        for m in movimentacoes
    )
    st.caption(md(f"Capital líquido aplicado neste investimento: {formatar_real(liquido)}"))

    with st.expander("Excluir uma movimentação"):
        rotulos = {
            f"{db.formatar_competencia(m['competencia'])} · {m['tipo']} · "
            f"{formatar_real(m['valor'])}": m["id"]
            for m in movimentacoes
        }
        alvo = st.selectbox("Movimentação", list(rotulos.keys()), key="mov_excluir")
        if st.button("Excluir movimentação", key="btn_excluir_mov"):
            db.excluir_movimentacao(rotulos[alvo])
            guardar_flash("warning", "Movimentação excluída.")
            st.rerun()


def _formulario_investimento(inv=None) -> None:
    """Formulário de cadastro (inv=None) ou de edição."""
    edicao = inv is not None
    sufixo = f"edit_{inv['id']}" if edicao else "novo"

    with st.form(f"form_inv_{sufixo}", clear_on_submit=not edicao):
        col1, col2 = st.columns(2)
        nome = col1.text_input(
            "Nome", value=inv["nome"] if edicao else "", key=f"nome_{sufixo}"
        )
        categoria = col2.selectbox(
            "Categoria",
            db.CATEGORIAS,
            index=db.CATEGORIAS.index(inv["categoria"]) if edicao else 0,
            key=f"cat_{sufixo}",
        )

        col3, col4 = st.columns(2)
        capital = col3.number_input(
            "Capital investido (R$)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            value=float(inv["capital"]) if edicao else 0.0,
            key=f"cap_{sufixo}",
        )
        taxa_texto = col4.text_input(
            "Taxa de retorno mensal (%) — opcional",
            value=(
                ""
                if not edicao or inv["taxa_mensal"] is None
                else f"{float(inv['taxa_mensal']):g}".replace(".", ",")
            ),
            placeholder="ex.: 0,9",
            key=f"taxa_{sufixo}",
        )

        mes_inicio = seletor_competencia(
            "Mês de início",
            inv["mes_inicio"] if edicao else db.MES_INICIAL,
            f"inicio_{sufixo}",
        )

        ativo = st.checkbox(
            "Investimento ativo",
            value=bool(inv["ativo"]) if edicao else True,
            key=f"ativo_{sufixo}",
        )
        observacoes = st.text_area(
            "Observações",
            value=inv["observacoes"] or "" if edicao else "",
            key=f"obs_{sufixo}",
        )

        enviado = st.form_submit_button(
            "Salvar alterações" if edicao else "Cadastrar investimento",
            type="primary",
        )

    if not enviado:
        return

    try:
        taxa = (taxa_texto or "").strip().replace(",", ".")
        if edicao:
            db.atualizar_investimento(
                inv["id"], nome, categoria, capital, taxa,
                mes_inicio, observacoes, ativo,
            )
            guardar_flash("success", f"Investimento “{nome.strip()}” atualizado.")
        else:
            db.criar_investimento(
                nome, categoria, capital, taxa, mes_inicio, observacoes, ativo
            )
            guardar_flash("success", f"Investimento “{nome.strip()}” cadastrado.")
        st.rerun()
    except ValueError as erro:
        st.error(str(erro))


def _acoes_investimento(inv) -> None:
    st.divider()
    lancamentos = db.listar_rendimentos(investimento_id=inv["id"])
    col1, col2 = st.columns(2)

    with col1:
        if inv["ativo"]:
            if st.button("Encerrar investimento", key=f"enc_{inv['id']}"):
                db.encerrar_investimento(inv["id"])
                guardar_flash("info", f"“{inv['nome']}” encerrado. O histórico foi mantido.")
                st.rerun()
        else:
            if st.button("Reativar investimento", key=f"rea_{inv['id']}"):
                db.reativar_investimento(inv["id"])
                guardar_flash("success", f"“{inv['nome']}” reativado.")
                st.rerun()

    with col2:
        confirmar = st.checkbox(
            f"Confirmo excluir definitivamente e apagar {len(lancamentos)} lançamento(s)",
            key=f"conf_{inv['id']}",
        )
        if st.button("Excluir definitivamente", key=f"del_{inv['id']}", disabled=not confirmar):
            db.excluir_investimento(inv["id"])
            guardar_flash("warning", f"“{inv['nome']}” e seus lançamentos foram excluídos.")
            st.rerun()

    st.caption(
        "Encerrar preserva todo o histórico e apenas para as estimativas futuras. "
        "A exclusão é definitiva e apaga os lançamentos do investimento."
    )


# ------------------------------------------------------------ página: painel ---

def pagina_painel() -> None:
    st.header("Painel")
    mostrar_flash()

    anos = db.anos_disponiveis()
    ano_atual = datetime.now().year
    ano = st.selectbox(
        "Ano",
        anos,
        index=anos.index(ano_atual) if ano_atual in anos else len(anos) - 1,
        key="painel_ano",
    )

    lancamentos = db.listar_rendimentos(ano=ano)
    totais_mes = db.total_por_competencia(ano)
    capital = db.capital_total()

    total_ano = sum(totais_mes.values())
    meses_com_lancamento = len(totais_mes)
    media_mensal = total_ano / meses_com_lancamento if meses_com_lancamento else 0.0
    retorno_medio = (media_mensal / capital * 100) if capital else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Total recebido em {ano}", md(formatar_real(total_ano)))
    col2.metric(
        "Média mensal",
        md(formatar_real(media_mensal)),
        help="Total recebido dividido pelos meses com lançamento no ano.",
    )
    col3.metric("Capital investido", md(formatar_real(capital)))
    col4.metric(
        "Retorno médio mensal",
        formatar_taxa(retorno_medio),
        help="Média mensal recebida sobre o capital dos investimentos ativos.",
    )

    if not lancamentos:
        st.info(
            f"Nenhum rendimento lançado em {ano}. "
            "Use a página “Lançar rendimento” para começar."
        )
        return

    st.subheader("Rendimentos por mês")
    serie = pd.DataFrame(
        {
            "Mês": db.MESES,
            "Rendimento": [
                totais_mes.get(db.competencia_de(ano, m), 0.0) for m in range(1, 13)
            ],
        }
    )
    grafico = (
        alt.Chart(serie)
        .mark_bar(color="#2e7d32", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Mês:N", sort=db.MESES, title=None),
            y=alt.Y("Rendimento:Q", title="R$", axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("Mês:N"),
                alt.Tooltip("Rendimento:Q", format=",.2f", title="R$"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(grafico, width="stretch")

    st.subheader("Rendimento por investimento e mês")
    exibicao, estimado_total = _montar_matriz(ano, lancamentos)
    st.dataframe(
        exibicao.style.map(_estilo_estimativa),
        width="stretch",
        hide_index=True,
    )
    if estimado_total:
        st.caption(md(
            "Valores em cinza com “~” são estimativas (capital × taxa) para meses sem "
            f"lançamento — total estimado no ano: {formatar_real(estimado_total)}. "
            "Estimativas não entram nos totais nem nos indicadores acima."
        ))


def _estilo_estimativa(valor) -> str:
    if isinstance(valor, str) and valor.startswith("~"):
        return "color: #9aa0a6; font-style: italic"
    return ""


def _montar_matriz(ano: int, lancamentos) -> tuple[pd.DataFrame, float]:
    """Monta a matriz investimentos × meses já formatada para exibição."""
    recebidos: dict[int, dict[int, float]] = {}
    for r in lancamentos:
        mes = int(r["competencia"][5:])
        recebidos.setdefault(r["investimento_id"], {})[mes] = float(r["valor"])

    investimentos = [
        inv
        for inv in db.listar_investimentos()
        if inv["id"] in recebidos
        or (inv["ativo"] and inv["mes_inicio"][:4] <= str(ano))
    ]

    linhas, totais_coluna, estimado_total = [], {m: 0.0 for m in range(1, 13)}, 0.0
    for inv in investimentos:
        linha = {"Investimento": inv["nome"]}
        total_linha = 0.0
        for mes in range(1, 13):
            valor = recebidos.get(inv["id"], {}).get(mes)
            if valor is not None:
                linha[db.MESES[mes - 1]] = formatar_real(valor)
                total_linha += valor
                totais_coluna[mes] += valor
                continue
            estimativa = _estimativa_do_mes(inv, ano, mes)
            if estimativa is not None:
                linha[db.MESES[mes - 1]] = "~ " + formatar_real(estimativa)
                estimado_total += estimativa
            else:
                linha[db.MESES[mes - 1]] = "—"
        linha["Total"] = formatar_real(total_linha)
        linhas.append(linha)

    rodape = {"Investimento": "TOTAL"}
    for mes in range(1, 13):
        rodape[db.MESES[mes - 1]] = formatar_real(totais_coluna[mes])
    rodape["Total"] = formatar_real(sum(totais_coluna.values()))
    linhas.append(rodape)

    return pd.DataFrame(linhas), estimado_total


def _estimativa_do_mes(inv, ano: int, mes: int) -> float | None:
    """Estimativa do mês quando não há lançamento (só com taxa e investimento ativo)."""
    if inv["taxa_mensal"] is None or not inv["ativo"]:
        return None
    if db.competencia_de(ano, mes) < inv["mes_inicio"]:
        return None
    return round(float(inv["capital"]) * float(inv["taxa_mensal"]) / 100, 2)


# ----------------------------------------------- página: lançar rendimento ---

def pagina_lancamento() -> None:
    st.header("Lançar rendimento")
    mostrar_flash()

    mostrar_encerrados = st.checkbox(
        "Mostrar também investimentos encerrados", value=False, key="lanc_encerrados"
    )
    investimentos = db.listar_investimentos(incluir_inativos=mostrar_encerrados)
    if not investimentos:
        st.info("Cadastre um investimento antes de lançar rendimentos.")
        return

    opcoes = {rotulo_investimento(inv): inv["id"] for inv in investimentos}
    escolhido = st.selectbox("Investimento", list(opcoes.keys()), key="lanc_inv")
    inv = db.obter_investimento(opcoes[escolhido])

    competencia = seletor_competencia(
        "Competência", _competencia_sugerida(inv), "lanc_comp"
    )

    existente = db.obter_rendimento(inv["id"], competencia)
    estimado = _valor_estimado(inv)

    if existente:
        valor_inicial = float(existente["valor"])
        st.warning(md(
            f"Já existe lançamento para {db.formatar_competencia(competencia)} "
            f"({formatar_real(existente['valor'])}). Salvar substitui o valor."
        ))
    elif estimado is not None:
        valor_inicial = estimado
        st.caption(md(
            f"Valor sugerido pela taxa cadastrada: {formatar_real(inv['capital'])} × "
            f"{formatar_taxa(inv['taxa_mensal'])} = {formatar_real(estimado)}. "
            "Altere se o valor recebido foi outro."
        ))
    else:
        valor_inicial = 0.0
        st.caption("Este investimento não tem taxa cadastrada — informe o valor recebido.")

    col1, col2 = st.columns([1, 2])
    valor = col1.number_input(
        "Valor recebido (R$)",
        min_value=0.0,
        step=50.0,
        format="%.2f",
        value=valor_inicial,
        key=f"valor_{inv['id']}_{competencia}",
    )
    observacao = col2.text_input(
        "Observação",
        value=existente["observacao"] if existente else "",
        key=f"obs_lanc_{inv['id']}_{competencia}",
    )

    if st.button("Salvar lançamento", type="primary", key="salvar_lanc"):
        try:
            db.salvar_rendimento(inv["id"], competencia, valor, observacao)
            acao = "atualizado" if existente else "lançado"
            guardar_flash(
                "success",
                f"Rendimento de {db.formatar_competencia(competencia)} {acao}: "
                f"{formatar_real(valor)} — {inv['nome']}.",
            )
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))

    st.divider()
    st.subheader(f"Lançamentos de {inv['nome']}")
    lancamentos = db.listar_rendimentos(investimento_id=inv["id"])
    if not lancamentos:
        st.caption("Nenhum lançamento para este investimento ainda.")
        return

    total = sum(float(r["valor"]) for r in lancamentos)
    st.caption(md(
        f"{len(lancamentos)} lançamento(s) · total recebido: {formatar_real(total)}"
    ))
    for r in lancamentos:
        col_a, col_b, col_c, col_d = st.columns([1, 1, 3, 1])
        col_a.write(db.formatar_competencia(r["competencia"]))
        col_b.write(md(formatar_real(r["valor"])))
        col_c.write(r["observacao"] or "—")
        if col_d.button("Excluir", key=f"del_rend_{r['id']}"):
            db.excluir_rendimento(r["id"])
            guardar_flash(
                "warning",
                f"Lançamento de {db.formatar_competencia(r['competencia'])} excluído.",
            )
            st.rerun()


def _valor_estimado(inv) -> float | None:
    """Capital × taxa mensal, quando houver taxa cadastrada."""
    if inv["taxa_mensal"] is None:
        return None
    return round(float(inv["capital"]) * float(inv["taxa_mensal"]) / 100, 2)


def _competencia_sugerida(inv) -> str:
    """Primeiro mês sem lançamento, a partir do início do investimento."""
    lancados = {r["competencia"] for r in db.listar_rendimentos(investimento_id=inv["id"])}
    ano, mes = int(inv["mes_inicio"][:4]), int(inv["mes_inicio"][5:])
    hoje = datetime.now()
    for _ in range(120):
        competencia = db.competencia_de(ano, mes)
        if competencia not in lancados:
            return competencia
        if (ano, mes) >= (hoje.year, hoje.month):
            return competencia
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
    return inv["mes_inicio"]


# --------------------------------------------------------- página: exportar ---

def pagina_exportar() -> None:
    st.header("Exportar e backup")
    mostrar_flash()

    anos = db.anos_disponiveis()
    ano_atual = datetime.now().year
    ano = st.selectbox(
        "Ano",
        anos,
        index=anos.index(ano_atual) if ano_atual in anos else len(anos) - 1,
        key="export_ano",
    )

    st.subheader("Planilha do Excel")
    lancamentos = db.listar_rendimentos(ano=ano)
    if not lancamentos:
        st.info(f"Nenhum lançamento em {ano} para exportar.")
    else:
        st.caption(
            f"A planilha traz duas abas: **Matriz** (investimentos × meses, com totais) "
            f"e **Lançamentos** ({len(lancamentos)} registro(s) de {ano})."
        )
        st.download_button(
            "Baixar Excel (.xlsx)",
            data=_planilha_excel(ano),
            file_name=f"investimentos_{ano}_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    st.divider()
    st.subheader("Backup do banco de dados")
    st.caption(md(
        f"Copia o arquivo {db.CAMINHO_DB.name} para a pasta backups, "
        "com data e hora no nome."
    ))
    if st.button("Fazer backup agora"):
        try:
            destino = db.fazer_backup()
            guardar_flash("success", f"Backup salvo em: {destino}")
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))

    backups = sorted(db.PASTA_BACKUPS.glob("rendimentos_*.db"), reverse=True)
    if backups:
        st.caption(f"{len(backups)} backup(s) — mais recente: {backups[0].name}")


def _planilha_excel(ano: int) -> bytes:
    """Gera o .xlsx em memória com as abas Matriz e Lançamentos."""
    matriz = _matriz_numerica(ano)
    lancamentos = pd.DataFrame(
        [
            {
                "Competência": db.formatar_competencia(r["competencia"]),
                "Investimento": r["nome"],
                "Categoria": r["categoria"],
                "Valor recebido": float(r["valor"]),
                "Observação": r["observacao"] or "",
                "Atualizado em": r["atualizado_em"],
            }
            for r in db.listar_rendimentos(ano=ano)
        ]
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        matriz.to_excel(writer, sheet_name="Matriz", index=False)
        lancamentos.to_excel(writer, sheet_name="Lançamentos", index=False)
        for aba, df in (("Matriz", matriz), ("Lançamentos", lancamentos)):
            planilha = writer.sheets[aba]
            for i, coluna in enumerate(df.columns, start=1):
                largura = max(len(str(coluna)) + 2, 14)
                planilha.column_dimensions[
                    planilha.cell(row=1, column=i).column_letter
                ].width = largura
                if coluna not in ("Investimento", "Competência", "Categoria",
                                  "Observação", "Atualizado em"):
                    for linha in range(2, len(df) + 2):
                        planilha.cell(row=linha, column=i).number_format = (
                            '#,##0.00'
                        )
    return buffer.getvalue()


def _matriz_numerica(ano: int) -> pd.DataFrame:
    """Matriz investimentos × meses com valores numéricos (só recebidos)."""
    recebidos: dict[int, dict[int, float]] = {}
    for r in db.listar_rendimentos(ano=ano):
        recebidos.setdefault(r["investimento_id"], {})[int(r["competencia"][5:])] = float(
            r["valor"]
        )

    investimentos = [
        inv
        for inv in db.listar_investimentos()
        if inv["id"] in recebidos or (inv["ativo"] and inv["mes_inicio"][:4] <= str(ano))
    ]

    linhas = []
    for inv in investimentos:
        linha = {"Investimento": inv["nome"], "Categoria": inv["categoria"]}
        for mes in range(1, 13):
            linha[db.MESES[mes - 1]] = recebidos.get(inv["id"], {}).get(mes, 0.0)
        linha["Total"] = sum(recebidos.get(inv["id"], {}).values())
        linhas.append(linha)

    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    total = {"Investimento": "TOTAL", "Categoria": ""}
    for coluna in db.MESES + ["Total"]:
        total[coluna] = float(df[coluna].sum())
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ----------------------------------------------- página: evolução e projeção ---

def pagina_evolucao() -> None:
    st.header("Evolução do patrimônio")
    mostrar_flash()

    rendimentos: dict[str, float] = {}
    for r in db.listar_rendimentos():
        rendimentos[r["competencia"]] = rendimentos.get(r["competencia"], 0.0) + float(
            r["valor"]
        )
    if not rendimentos:
        st.info("Ainda não há rendimentos lançados para montar a evolução.")
        return

    movimentacoes = db.capital_movimentado_por_mes()
    if not movimentacoes:
        st.warning(
            "Nenhum aporte registrado. Cadastre os aportes e resgates na página "
            "Investimentos, aba “Aportes e resgates”, para a evolução partir do zero "
            "e acompanhar o dinheiro que foi entrando."
        )
    realizado = patrimonio.serie_realizada(movimentacoes, rendimentos)
    ultimo = realizado[-1]

    mes_corrente = f"{datetime.now():%Y-%m}"
    taxa_obtida, mes_base = patrimonio.taxa_ultimo_mes_fechado(realizado, mes_corrente)
    mes_em_curso = ultimo.competencia >= mes_corrente

    st.caption(md(
        "Patrimônio = aportes − resgates − impostos pagos + retorno acumulado, mês a "
        "mês. A projeção repete, por 12 meses, a taxa do último mês fechado"
        + (f" ({db.formatar_competencia(mes_base)})" if mes_base else "")
        + " — o mês em curso não entra na conta, porque o rendimento dele ainda é "
        "parcial."
    ))
    if mes_em_curso:
        st.info(
            f"{db.formatar_competencia(ultimo.competencia)} ainda está em curso: o "
            "patrimônio atual já inclui o que foi lançado no mês, mas a taxa da "
            f"projeção vem de {db.formatar_competencia(mes_base)}."
            if mes_base else
            f"{db.formatar_competencia(ultimo.competencia)} ainda está em curso e não "
            "há mês fechado com rendimento para basear a projeção."
        )

    col_taxa, col_aporte = st.columns(2)
    taxa = col_taxa.number_input(
        "Taxa mensal usada na projeção (%)",
        min_value=0.0, max_value=20.0, step=0.05, format="%.3f",
        value=round(taxa_obtida, 3),
        help="Vem preenchida com a taxa do último mês fechado. Altere para simular "
             "outro ritmo.",
        key="evol_taxa",
    )
    aporte_previsto = col_aporte.number_input(
        "Aporte mensal previsto (R$)",
        min_value=0.0, step=500.0, format="%.2f", value=0.0,
        help="Quanto você pretende aplicar por mês daqui para a frente. Deixe 0 para "
             "projetar só o rendimento do que já está aplicado.",
        key="evol_aporte",
    )
    previsto = patrimonio.projetar(ultimo, taxa, aporte_mensal=aporte_previsto)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Patrimônio (capital + retorno)", md(formatar_real(ultimo.valor)),
        help="Tudo o que você tem hoje: o capital que entrou (já descontados resgates "
             "e impostos pagos) somado a tudo o que ele rendeu.",
    )
    col2.metric(
        "Capital investido", md(formatar_real(db.capital_total())),
        help="Só o valor aplicado nos investimentos ativos, sem o retorno — o mesmo "
             "número do Painel. A diferença para o patrimônio é o rendimento que "
             "continua aplicado.",
    )
    col3.metric(
        f"Retorno de {db.formatar_competencia(mes_base)}" if mes_base
        else "Retorno do mês fechado",
        formatar_taxa(taxa_obtida),
        help="Rendimento do último mês fechado sobre o patrimônio do início dele. "
             "É essa taxa que alimenta a projeção.",
    )
    col4.metric(
        f"Previsto em {db.formatar_competencia(previsto[-1].competencia)}",
        md(formatar_real(previsto[-1].valor)),
    )
    col5.metric(
        "Ganho previsto em 12 meses",
        md(formatar_real(
            previsto[-1].valor - ultimo.valor - aporte_previsto * len(previsto)
        )),
        help="Só o rendimento projetado, sem contar os aportes previstos.",
    )

    st.caption(md(
        f"Composição do patrimônio: {formatar_real(ultimo.aportado)} de capital "
        f"líquido aplicado (aportes − resgates − impostos pagos) + "
        f"{formatar_real(ultimo.valor - ultimo.aportado)} de rendimentos acumulados."
    ))

    dados = pd.DataFrame(
        [
            {
                "Competência": p.competencia,
                "Mês": db.formatar_competencia(p.competencia),
                "Patrimônio": p.valor,
                "Série": "Previsto" if p.previsto else "Realizado",
            }
            for p in realizado + previsto
        ]
    )
    # o último ponto realizado também entra na série prevista, para as linhas se unirem
    emenda = dados[dados["Competência"] == ultimo.competencia].copy()
    emenda["Série"] = "Previsto"
    dados = pd.concat([dados, emenda], ignore_index=True).sort_values("Competência")

    ordem_meses = [
        db.formatar_competencia(p.competencia) for p in realizado + previsto
    ]
    base = alt.Chart(dados).encode(
        x=alt.X("Mês:N", sort=ordem_meses, title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(
            "Patrimônio:Q", title="R$",
            scale=alt.Scale(zero=False, nice=True),
            axis=alt.Axis(format=",.0f"),
        ),
        color=alt.Color(
            "Série:N",
            scale=alt.Scale(
                domain=["Realizado", "Previsto"], range=["#2e7d32", "#9aa0a6"]
            ),
            legend=alt.Legend(title=None, orient="top"),
        ),
        strokeDash=alt.StrokeDash(
            "Série:N",
            scale=alt.Scale(domain=["Realizado", "Previsto"], range=[[1, 0], [6, 4]]),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("Mês:N", title="Mês"),
            alt.Tooltip("Patrimônio:Q", format=",.2f", title="R$"),
            alt.Tooltip("Série:N", title="Série"),
        ],
    )
    grafico = (base.mark_line(strokeWidth=2.5) + base.mark_point(size=45, filled=True))
    st.altair_chart(grafico.properties(height=360), width="stretch")

    with st.expander("Ver os números mês a mês"):
        st.dataframe(
            [
                {
                    "Mês": db.formatar_competencia(p.competencia),
                    "Rendimento do mês": formatar_real(p.rendimento),
                    "Patrimônio": formatar_real(p.valor),
                    "Situação": (
                        "Previsto" if p.previsto
                        else "Em curso" if p.competencia >= mes_corrente
                        else "Realizado"
                    ),
                }
                for p in realizado + previsto
            ],
            width="stretch",
            hide_index=True,
        )

    st.caption(
        "A projeção mantém uma única taxa por doze meses, então serve para enxergar o "
        "ritmo atual, não como promessa de resultado. Lembre-se de que a economia da "
        "energia solar reduz despesa (não vira saldo aplicado) e que juros de "
        "empréstimo marcados como “a receber” ainda não entraram no caixa."
    )


# --------------------------------------------------- página: energia solar ---

def pagina_solar() -> None:
    st.header("Energia solar")
    mostrar_flash()
    st.caption(
        "A distribuidora não paga em dinheiro: o retorno é a economia na conta de luz. "
        "Informe os dados da fatura do mês e o app calcula quanto o sistema economizou "
        "e lança esse valor como rendimento do investimento."
    )

    sistemas = [
        inv for inv in db.listar_investimentos() if inv["categoria"] == solar.CATEGORIA
    ]
    if not sistemas:
        st.info(
            "Nenhum sistema de energia solar cadastrado. Cadastre um investimento da "
            "categoria “Energia solar” na página Investimentos, usando o valor pago no "
            "sistema como capital."
        )
        return

    if len(sistemas) == 1:
        inv = sistemas[0]
    else:
        opcoes = {inv["nome"]: inv["id"] for inv in sistemas}
        escolhido = st.selectbox("Sistema", list(opcoes.keys()), key="solar_sistema")
        inv = db.obter_investimento(opcoes[escolhido])

    faturas = db.listar_faturas_solar(inv["id"])
    _formulario_fatura_solar(inv, faturas)

    if faturas:
        st.divider()
        _historico_solar(inv, faturas)


def _formulario_fatura_solar(inv, faturas) -> None:
    ultima = faturas[-1] if faturas else None
    competencia = seletor_competencia(
        "Competência da fatura", _proxima_competencia_solar(inv, faturas), "solar_comp"
    )
    existente = db.obter_fatura_solar(inv["id"], competencia)
    base = existente or ultima

    if existente:
        st.warning(
            f"Já existe fatura registrada para {db.formatar_competencia(competencia)}. "
            "Salvar substitui os dados e recalcula o rendimento do mês."
        )

    st.subheader("Dados da fatura (DANF3E)")
    chave = f"{inv['id']}_{competencia}"

    col1, col2, col3 = st.columns(3)
    consumo = col1.number_input(
        "Consumo (kWh)", min_value=0.0, step=1.0, format="%.2f",
        value=float(existente["consumo_kwh"]) if existente else 0.0,
        help=solar.CAMPOS["consumo_kwh"], key=f"sol_consumo_{chave}",
    )
    tarifa = col2.number_input(
        "Tarifa cheia com tributos (R$/kWh)", min_value=0.0, step=0.01, format="%.6f",
        value=float(base["tarifa_cheia"]) if base else 0.0,
        help=solar.CAMPOS["tarifa_cheia"], key=f"sol_tarifa_{chave}",
    )
    dias = col3.number_input(
        "Nº de dias do ciclo", min_value=0, max_value=45, step=1,
        value=int(existente["dias"]) if existente and existente["dias"] else 30,
        help=solar.CAMPOS["dias"], key=f"sol_dias_{chave}",
    )

    col4, col5, col6 = st.columns(3)
    ilum = col4.number_input(
        "Iluminação pública (R$)", min_value=0.0, step=1.0, format="%.2f",
        value=float(existente["ilum_publica"]) if existente else 0.0,
        help=solar.CAMPOS["ilum_publica"], key=f"sol_ilum_{chave}",
    )
    bandeira = col5.number_input(
        "Adicional de bandeira (R$)", min_value=0.0, step=0.5, format="%.2f",
        value=float(existente["bandeira"]) if existente else 0.0,
        help=solar.CAMPOS["bandeira"], key=f"sol_band_{chave}",
    )
    total = col6.number_input(
        "Total pago na fatura (R$)", min_value=0.0, step=1.0, format="%.2f",
        value=float(existente["total_pago"]) if existente else 0.0,
        help=solar.CAMPOS["total_pago"], key=f"sol_total_{chave}",
    )

    col7, col8, col9 = st.columns(3)
    mora = col7.number_input(
        "Multa/juros de atraso (R$)", min_value=0.0, step=0.5, format="%.2f",
        value=float(existente["mora"]) if existente else 0.0,
        help=solar.CAMPOS["mora"], key=f"sol_mora_{chave}",
    )
    fio_b = col8.number_input(
        "Tarifa Fio B — Ajuste GD II (R$/kWh)", min_value=0.0, step=0.01, format="%.6f",
        value=float(base["tarifa_fio_b"]) if base and base["tarifa_fio_b"] else 0.0,
        help=solar.CAMPOS["tarifa_fio_b"], key=f"sol_fiob_{chave}",
    )
    saldo = col9.number_input(
        "Saldo de créditos (kWh)", min_value=0.0, step=1.0, format="%.0f",
        value=(
            float(existente["saldo_creditos"])
            if existente and existente["saldo_creditos"] else 0.0
        ),
        help=solar.CAMPOS["saldo_creditos"], key=f"sol_saldo_{chave}",
    )

    resultado = solar.calcular_mes(consumo, tarifa, total, ilum, bandeira, mora)

    st.subheader("Cálculo do mês")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Custo sem solar", md(formatar_real(resultado.custo_sem_solar)))
    col_b.metric("Custo com solar", md(formatar_real(resultado.custo_com_solar)))
    col_c.metric("Economia do mês", md(formatar_real(resultado.economia)))
    col_d.metric("Conta eliminada", formatar_taxa(resultado.percentual_economia))
    st.caption(md(
        f"{consumo:,.0f} kWh × {formatar_real(tarifa)} + {formatar_real(ilum)} "
        f"(iluminação pública) + {formatar_real(bandeira)} (bandeira) = "
        f"{formatar_real(resultado.custo_sem_solar)} sem o sistema, contra "
        f"{formatar_real(resultado.custo_com_solar)} efetivamente pagos."
    ))

    if resultado.economia < 0:
        st.error(
            "A economia ficou negativa — confira o total pago e a tarifa: o valor "
            "cobrado está maior do que a conta custaria sem o sistema."
        )

    if st.button("Salvar fatura e lançar o rendimento", type="primary", key="salvar_solar"):
        try:
            if total <= 0 or consumo <= 0 or tarifa <= 0:
                raise ValueError(
                    "Informe pelo menos consumo, tarifa cheia e total pago da fatura."
                )
            db.salvar_fatura_solar(
                investimento_id=inv["id"], competencia=competencia,
                consumo_kwh=consumo, tarifa_cheia=tarifa, total_pago=total,
                dias=dias, tarifa_fio_b=fio_b or None, ilum_publica=ilum,
                bandeira=bandeira, mora=mora, saldo_creditos=saldo or None,
            )
            db.salvar_rendimento(
                inv["id"], competencia, max(resultado.economia, 0),
                f"Economia na conta de luz: {formatar_real(resultado.custo_sem_solar)} "
                f"sem o sistema − {formatar_real(resultado.custo_com_solar)} pagos "
                f"({consumo:,.0f} kWh).",
            )
            guardar_flash(
                "success",
                f"Fatura de {db.formatar_competencia(competencia)} salva. "
                f"Rendimento lançado: {formatar_real(resultado.economia)}.",
            )
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))


def _historico_solar(inv, faturas) -> None:
    resumo = solar.resumo_retorno(faturas, inv["capital"])

    st.subheader("Retorno do investimento")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Economia acumulada", md(formatar_real(resumo.economia_acumulada)))
    col2.metric(
        "Economia média mensal", md(formatar_real(resumo.economia_media)),
        help=f"{resumo.meses} mês(es) registrado(s).",
    )
    col3.metric(
        "Retorno acumulado", formatar_taxa(resumo.retorno_acumulado_pct),
        help=f"Sobre o investimento de {formatar_real(inv['capital'])}.",
    )
    col4.metric(
        "Payback estimado",
        f"{resumo.payback_meses:.1f}".replace(".", ",") + " meses"
        if resumo.payback_meses else "—",
        help="No ritmo atual de economia. Ainda faltam "
             f"{formatar_real(resumo.falta_recuperar)}.",
    )

    linhas = []
    for f in faturas:
        r = solar.calcular_mes(
            f["consumo_kwh"], f["tarifa_cheia"], f["total_pago"],
            f["ilum_publica"], f["bandeira"], f["mora"],
        )
        linhas.append({
            "Competência": db.formatar_competencia(f["competencia"]),
            "Dias": f["dias"] or "—",
            "Consumo (kWh)": f"{float(f['consumo_kwh']):,.0f}".replace(",", "."),
            "Tarifa cheia": f"{float(f['tarifa_cheia']):.6f}".replace(".", ","),
            "Sem solar": formatar_real(r.custo_sem_solar),
            "Pago": formatar_real(r.custo_com_solar),
            "Economia": formatar_real(r.economia),
            "% do investim.": formatar_taxa(
                r.economia / float(inv["capital"]) * 100 if inv["capital"] else 0
            ),
            "Saldo créd. (kWh)": (
                f"{float(f['saldo_creditos']):,.0f}".replace(",", ".")
                if f["saldo_creditos"] is not None else "—"
            ),
        })
    st.dataframe(linhas, width="stretch", hide_index=True)

    if resumo.saldo_creditos:
        st.caption(
            f"Saldo de créditos atual: {resumo.saldo_creditos:,.0f} kWh".replace(",", ".")
            + " — economia futura já garantida, que ainda não entra nos totais acima."
        )

    with st.expander("Excluir uma fatura"):
        opcoes = [db.formatar_competencia(f["competencia"]) for f in faturas]
        escolhida = st.selectbox("Competência", opcoes, key="solar_excluir")
        st.caption("Apaga a fatura e o lançamento de rendimento daquele mês.")
        if st.button("Excluir fatura", key="btn_excluir_solar"):
            competencia = db.competencia_de(int(escolhida[3:]), int(escolhida[:2]))
            db.excluir_fatura_solar(inv["id"], competencia)
            guardar_flash("warning", f"Fatura de {escolhida} excluída.")
            st.rerun()


def _proxima_competencia_solar(inv, faturas) -> str:
    """Primeiro mês sem fatura registrada, a partir do início do investimento."""
    registradas = {f["competencia"] for f in faturas}
    ano, mes = int(inv["mes_inicio"][:4]), int(inv["mes_inicio"][5:])
    hoje = datetime.now()
    for _ in range(120):
        competencia = db.competencia_de(ano, mes)
        if competencia not in registradas or (ano, mes) >= (hoje.year, hoje.month):
            return competencia
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
    return inv["mes_inicio"]


# -------------------------------------------------------- página: importar ---

def pagina_importar() -> None:
    st.header("Importar extratos do Tesouro Direto")
    mostrar_flash()
    st.caption(
        "Envie os extratos analíticos (.xlsx) baixados no Tesouro Direto / Nu "
        "Investimentos. O app calcula o rendimento de cada mês comparando a posição "
        "com a do mês anterior, descontando aplicações e somando resgates. "
        "Envie meses seguidos — o primeiro mês da sequência precisa do extrato do mês "
        "anterior para o cálculo ficar exato."
    )

    arquivos = st.file_uploader(
        "Extratos analíticos (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="upload_extratos",
    )
    if not arquivos:
        return

    extratos = []
    for arquivo in arquivos:
        try:
            extratos.append(importador.ler_extrato(arquivo, arquivo.name))
        except ValueError as erro:
            st.error(str(erro))
    if not extratos:
        return

    for titulo, lista in importador.agrupar_por_titulo(extratos).items():
        _bloco_importacao(titulo, lista)


def _bloco_importacao(titulo: str, lista) -> None:
    st.divider()
    st.subheader(titulo)

    repetidos = importador.competencias_duplicadas(lista)
    if repetidos:
        st.warning(
            "Há mais de um extrato para o(s) mesmo(s) mês(es): "
            + ", ".join(db.formatar_competencia(c) for c in sorted(set(repetidos)))
            + ". Envie apenas um arquivo por mês."
        )
        return

    rendimentos = importador.calcular_rendimentos(lista)
    ultimo = lista[-1]

    st.dataframe(
        [
            {
                "Competência": db.formatar_competencia(r.competencia),
                "Rendimento (bruto)": formatar_real(r.bruto),
                "Aplicações no mês": formatar_real(r.aplicacoes_mes),
                "Resgates no mês": formatar_real(r.resgates) if r.resgates else "—",
                "Cálculo": "estimado" if r.estimado else "exato",
            }
            for r in rendimentos
        ],
        width="stretch",
        hide_index=True,
    )
    for r in rendimentos:
        if r.aviso:
            st.warning(f"{db.formatar_competencia(r.competencia)}: {r.aviso}")

    total = sum(r.bruto for r in rendimentos)
    st.caption(md(
        f"Total de {len(rendimentos)} mês(es): {formatar_real(total)} · "
        f"posição em {db.formatar_competencia(ultimo.competencia)}: "
        f"{formatar_real(ultimo.total_investido)} aplicados, "
        f"{formatar_real(ultimo.total_bruto)} de valor bruto"
    ))

    investimentos = db.listar_investimentos()
    rotulo_novo = f"➕ Criar investimento “{titulo}”"
    opcoes = {rotulo_novo: None}
    opcoes.update({rotulo_investimento(inv): inv["id"] for inv in investimentos})

    padrao = next(
        (
            rotulo
            for rotulo, identificador in opcoes.items()
            if identificador is not None
            and db.obter_investimento(identificador)["nome"].strip().lower()
            == titulo.strip().lower()
        ),
        rotulo_novo,
    )
    destino = st.selectbox(
        "Lançar em",
        list(opcoes.keys()),
        index=list(opcoes.keys()).index(padrao),
        key=f"destino_{titulo}",
    )
    atualizar_capital = st.checkbox(
        "Atualizar o capital do investimento com o valor aplicado do último extrato "
        f"({formatar_real(ultimo.total_investido)})",
        value=True,
        key=f"cap_imp_{titulo}",
    )

    if not st.button(
        f"Importar {len(rendimentos)} lançamento(s)", type="primary", key=f"imp_{titulo}"
    ):
        return

    try:
        investimento_id = opcoes[destino]
        if investimento_id is None:
            investimento_id = db.criar_investimento(
                nome=titulo,
                categoria="Tesouro Direto",
                capital=ultimo.total_investido,
                taxa_mensal=None,
                mes_inicio=min(r.competencia for r in rendimentos),
                observacoes=(
                    f"Vencimento {ultimo.vencimento}. "
                    "Importado dos extratos analíticos do Tesouro Direto."
                ),
            )
        elif atualizar_capital:
            inv = db.obter_investimento(investimento_id)
            db.atualizar_investimento(
                investimento_id, inv["nome"], inv["categoria"],
                ultimo.total_investido, inv["taxa_mensal"], inv["mes_inicio"],
                inv["observacoes"] or "", bool(inv["ativo"]),
            )

        for r in rendimentos:
            observacao = "Importado do extrato analítico"
            if r.estimado:
                observacao += " (mês com resgate/estimativa — confira)"
            db.salvar_rendimento(investimento_id, r.competencia, r.bruto, observacao)

        guardar_flash(
            "success",
            f"{len(rendimentos)} lançamento(s) importado(s) para “{titulo}”: "
            f"{formatar_real(total)}.",
        )
        st.rerun()
    except ValueError as erro:
        st.error(str(erro))


# ---------------------------------------------------------------- navegação ---

PAGINAS = {
    "Painel": pagina_painel,
    "Investimentos": pagina_investimentos,
    "Evolução": pagina_evolucao,
    "Lançar rendimento": pagina_lancamento,
    "Energia solar": pagina_solar,
    "Importar extratos": pagina_importar,
    "Exportar": pagina_exportar,
}

st.sidebar.title("📈 Investimentos")
st.sidebar.caption("Controle mensal de rendimentos")
escolha = st.sidebar.radio("Navegação", list(PAGINAS.keys()), label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption(f"Banco: {db.descricao_banco()}")
auth.botao_sair()

PAGINAS[escolha]()
