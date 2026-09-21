"""Camada de dados do Painel de Investimentos.

Fala com SQLite (arquivo local) ou PostgreSQL (Supabase), conforme a URL de
conexão — o resto do app não precisa saber qual dos dois está em uso:

- sem configuração: usa o arquivo `rendimentos.db` ao lado deste script;
- com `DATABASE_URL` no ambiente ou em `.streamlit/secrets.toml`: usa esse
  banco (é assim que o app roda publicado, com o Postgres do Supabase).

Todas as validações de entrada ficam aqui e levantam ValueError com mensagem
em português, que a interface exibe ao usuário.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PASTA = Path(__file__).resolve().parent
CAMINHO_DB = PASTA / "rendimentos.db"
PASTA_BACKUPS = PASTA / "backups"

CATEGORIAS = [
    "Tesouro Direto",
    "Empréstimo a juros",
    "Empréstimo sem juros",
    "Energia solar",
    "Renda fixa",
    "Fundos/Ações",
    "Imóvel/Aluguel",
    "Outro",
]

MES_INICIAL = "2026-01"
ANO_INICIAL = 2026

MESES = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]

_RE_COMPETENCIA = re.compile(r"^\d{4}-\d{2}$")


# ----------------------------------------------------------------- conexão ---

_engine: Engine | None = None


def url_banco() -> str:
    """URL de conexão: variável de ambiente, secrets do Streamlit ou SQLite local."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        try:  # só existe quando rodando dentro do Streamlit
            import streamlit as st

            url = str(st.secrets.get("DATABASE_URL", "")).strip()
        except Exception:
            url = ""
    if not url:
        return f"sqlite:///{CAMINHO_DB}"
    # o Supabase entrega a URL como postgresql://; fixamos o driver psycopg 3
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = url_banco()
        argumentos = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            argumentos["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **argumentos)
    return _engine


def usando_postgres() -> bool:
    return engine().dialect.name == "postgresql"


def rodando_na_nuvem() -> bool:
    """True quando o app está publicado no Streamlit Community Cloud."""
    return Path("/mount/src").exists() or bool(os.environ.get("STREAMLIT_RUNTIME_ENV"))


def descricao_banco() -> str:
    """Texto curto para mostrar na tela: onde os dados estão."""
    if usando_postgres():
        return "PostgreSQL (nuvem)"
    return CAMINHO_DB.name


def banco_local_indevido() -> bool:
    """App publicado usando arquivo local: os dados reais não estão sendo lidos."""
    return rodando_na_nuvem() and not usando_postgres()


def _consultar(sql: str, **params) -> list[dict]:
    with engine().connect() as con:
        resultado = con.execute(text(sql), params)
        return [dict(linha._mapping) for linha in resultado]


def _um(sql: str, **params) -> dict | None:
    linhas = _consultar(sql, **params)
    return linhas[0] if linhas else None


def _executar(sql: str, **params) -> None:
    with engine().begin() as con:
        con.execute(text(sql), params)


def _inserir(sql: str, **params) -> int:
    """Executa um INSERT ... RETURNING id e devolve o id gerado."""
    with engine().begin() as con:
        return int(con.execute(text(sql), params).scalar_one())


def criar_schema() -> None:
    """Cria as tabelas se ainda não existirem (idempotente, nos dois bancos)."""
    if usando_postgres():
        chave, real = "SERIAL PRIMARY KEY", "DOUBLE PRECISION"
    else:
        chave, real = "INTEGER PRIMARY KEY AUTOINCREMENT", "REAL"

    comandos = [
        f"""
        CREATE TABLE IF NOT EXISTS investimentos (
            id {chave},
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            capital {real} NOT NULL DEFAULT 0,
            taxa_mensal {real},
            mes_inicio TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            observacoes TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS rendimentos (
            id {chave},
            investimento_id INTEGER NOT NULL
                REFERENCES investimentos(id) ON DELETE CASCADE,
            competencia TEXT NOT NULL,
            valor {real} NOT NULL,
            observacao TEXT,
            atualizado_em TEXT NOT NULL,
            UNIQUE (investimento_id, competencia)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_rend_competencia ON rendimentos (competencia)",
        f"""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id {chave},
            investimento_id INTEGER NOT NULL
                REFERENCES investimentos(id) ON DELETE CASCADE,
            competencia TEXT NOT NULL,
            tipo TEXT NOT NULL,
            valor {real} NOT NULL,
            data TEXT,
            observacao TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_mov_competencia ON movimentacoes (competencia)",
        f"""
        CREATE TABLE IF NOT EXISTS faturas_solar (
            id {chave},
            investimento_id INTEGER NOT NULL
                REFERENCES investimentos(id) ON DELETE CASCADE,
            competencia TEXT NOT NULL,
            dias INTEGER,
            consumo_kwh {real} NOT NULL,
            tarifa_cheia {real} NOT NULL,
            tarifa_fio_b {real},
            ilum_publica {real} NOT NULL DEFAULT 0,
            bandeira {real} NOT NULL DEFAULT 0,
            mora {real} NOT NULL DEFAULT 0,
            total_pago {real} NOT NULL,
            saldo_creditos {real},
            atualizado_em TEXT NOT NULL,
            UNIQUE (investimento_id, competencia)
        )
        """,
    ]
    with engine().begin() as con:
        for comando in comandos:
            con.execute(text(comando))


# -------------------------------------------------------------- validações ---

def validar_competencia(competencia: str) -> str:
    """Valida uma competência no formato AAAA-MM, não anterior a 01/2026."""
    competencia = (competencia or "").strip()
    if not _RE_COMPETENCIA.match(competencia):
        raise ValueError(
            "Competência inválida: use o formato AAAA-MM (ex.: 2026-03)."
        )
    ano, mes = int(competencia[:4]), int(competencia[5:])
    if not 1 <= mes <= 12:
        raise ValueError("Competência inválida: o mês deve estar entre 01 e 12.")
    if competencia < MES_INICIAL:
        raise ValueError(
            "Competência inválida: o controle começa em "
            f"{formatar_competencia(MES_INICIAL)}."
        )
    if ano > datetime.now().year + 5:
        raise ValueError("Competência inválida: ano muito distante.")
    return competencia


def _validar_nome(nome: str) -> str:
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do investimento.")
    return nome


def _validar_categoria(categoria: str) -> str:
    categoria = (categoria or "").strip()
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoria inválida: {categoria or '(vazia)'}.")
    return categoria


def _validar_capital(capital) -> float:
    if capital is None or capital == "":
        raise ValueError("Informe o capital investido (use 0 se não houver).")
    try:
        capital = float(capital)
    except (TypeError, ValueError):
        raise ValueError("Capital investido inválido: informe um número.") from None
    if capital < 0:
        raise ValueError("Capital investido não pode ser negativo.")
    return capital


def _validar_taxa(taxa) -> float | None:
    """Taxa mensal em %; vazia significa 'sem estimativa'."""
    if taxa is None or taxa == "":
        return None
    try:
        taxa = float(taxa)
    except (TypeError, ValueError):
        raise ValueError("Taxa mensal inválida: informe um número em %.") from None
    if taxa < 0:
        raise ValueError("Taxa mensal não pode ser negativa.")
    if taxa > 100:
        raise ValueError("Taxa mensal acima de 100% ao mês: confira o valor.")
    return taxa


def _validar_valor(valor) -> float:
    if valor is None or valor == "":
        raise ValueError("Informe o valor recebido.")
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError("Valor recebido inválido: informe um número.") from None
    if valor < 0:
        raise ValueError("Valor recebido não pode ser negativo.")
    return valor


# ------------------------------------------------------------- utilitários ---

def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def formatar_competencia(competencia: str) -> str:
    """'2026-03' -> '03/2026'."""
    if not competencia or len(competencia) < 7:
        return competencia or ""
    return f"{competencia[5:7]}/{competencia[:4]}"


def competencia_de(ano: int, mes: int) -> str:
    return f"{int(ano):04d}-{int(mes):02d}"


# ----------------------------------------------------------- investimentos ---

def listar_investimentos(incluir_inativos: bool = True) -> list[dict]:
    sql = "SELECT * FROM investimentos"
    if not incluir_inativos:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY ativo DESC, LOWER(nome)"
    return _consultar(sql)


def obter_investimento(investimento_id: int) -> dict | None:
    return _um(
        "SELECT * FROM investimentos WHERE id = :id", id=int(investimento_id)
    )


def criar_investimento(
    nome: str,
    categoria: str,
    capital,
    taxa_mensal,
    mes_inicio: str,
    observacoes: str = "",
    ativo: bool = True,
) -> int:
    return _inserir(
        """
        INSERT INTO investimentos
            (nome, categoria, capital, taxa_mensal, mes_inicio,
             ativo, observacoes, criado_em)
        VALUES (:nome, :categoria, :capital, :taxa, :mes_inicio,
                :ativo, :observacoes, :criado_em)
        RETURNING id
        """,
        nome=_validar_nome(nome),
        categoria=_validar_categoria(categoria),
        capital=_validar_capital(capital),
        taxa=_validar_taxa(taxa_mensal),
        mes_inicio=validar_competencia(mes_inicio),
        ativo=1 if ativo else 0,
        observacoes=(observacoes or "").strip(),
        criado_em=agora(),
    )


def atualizar_investimento(
    investimento_id: int,
    nome: str,
    categoria: str,
    capital,
    taxa_mensal,
    mes_inicio: str,
    observacoes: str = "",
    ativo: bool = True,
) -> None:
    _executar(
        """
        UPDATE investimentos
           SET nome = :nome, categoria = :categoria, capital = :capital,
               taxa_mensal = :taxa, mes_inicio = :mes_inicio, ativo = :ativo,
               observacoes = :observacoes
         WHERE id = :id
        """,
        nome=_validar_nome(nome),
        categoria=_validar_categoria(categoria),
        capital=_validar_capital(capital),
        taxa=_validar_taxa(taxa_mensal),
        mes_inicio=validar_competencia(mes_inicio),
        ativo=1 if ativo else 0,
        observacoes=(observacoes or "").strip(),
        id=int(investimento_id),
    )


def definir_situacao(investimento_id: int, ativo: bool) -> None:
    _executar(
        "UPDATE investimentos SET ativo = :ativo WHERE id = :id",
        ativo=1 if ativo else 0,
        id=int(investimento_id),
    )


def encerrar_investimento(investimento_id: int) -> None:
    definir_situacao(investimento_id, False)


def reativar_investimento(investimento_id: int) -> None:
    definir_situacao(investimento_id, True)


def excluir_investimento(investimento_id: int) -> None:
    """Apaga o investimento e, por cascata, todos os seus lançamentos."""
    investimento_id = int(investimento_id)
    with engine().begin() as con:
        # o SQLite só respeita ON DELETE CASCADE com o pragma ligado por conexão
        for tabela in ("rendimentos", "movimentacoes", "faturas_solar"):
            con.execute(
                text(f"DELETE FROM {tabela} WHERE investimento_id = :id"),
                {"id": investimento_id},
            )
        con.execute(
            text("DELETE FROM investimentos WHERE id = :id"), {"id": investimento_id}
        )


# ------------------------------------------------------------- rendimentos ---

def salvar_rendimento(
    investimento_id: int,
    competencia: str,
    valor,
    observacao: str = "",
) -> None:
    """Grava o rendimento do mês; se já existir lançamento, atualiza o valor."""
    if obter_investimento(investimento_id) is None:
        raise ValueError("Investimento não encontrado.")
    _executar(
        """
        INSERT INTO rendimentos
            (investimento_id, competencia, valor, observacao, atualizado_em)
        VALUES (:investimento_id, :competencia, :valor, :observacao, :atualizado_em)
        ON CONFLICT (investimento_id, competencia) DO UPDATE SET
            valor = excluded.valor,
            observacao = excluded.observacao,
            atualizado_em = excluded.atualizado_em
        """,
        investimento_id=int(investimento_id),
        competencia=validar_competencia(competencia),
        valor=_validar_valor(valor),
        observacao=(observacao or "").strip(),
        atualizado_em=agora(),
    )


def obter_rendimento(investimento_id: int, competencia: str) -> dict | None:
    return _um(
        "SELECT * FROM rendimentos "
        "WHERE investimento_id = :id AND competencia = :competencia",
        id=int(investimento_id),
        competencia=competencia,
    )


def excluir_rendimento(rendimento_id: int) -> None:
    _executar("DELETE FROM rendimentos WHERE id = :id", id=int(rendimento_id))


def listar_rendimentos(
    ano: int | None = None, investimento_id: int | None = None
) -> list[dict]:
    sql = """
        SELECT r.id, r.investimento_id, r.competencia, r.valor, r.observacao,
               r.atualizado_em, i.nome, i.categoria
          FROM rendimentos r
          JOIN investimentos i ON i.id = r.investimento_id
    """
    filtros, params = [], {}
    if ano is not None:
        filtros.append("r.competencia LIKE :ano")
        params["ano"] = f"{int(ano)}-%"
    if investimento_id is not None:
        filtros.append("r.investimento_id = :investimento_id")
        params["investimento_id"] = int(investimento_id)
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY r.competencia DESC, LOWER(i.nome)"
    return _consultar(sql, **params)


def anos_disponiveis() -> list[int]:
    """Anos com lançamentos, sempre incluindo 2026 e o ano corrente."""
    linhas = _consultar(
        "SELECT DISTINCT substr(competencia, 1, 4) AS ano FROM rendimentos"
    )
    anos = {int(linha["ano"]) for linha in linhas}
    anos.add(ANO_INICIAL)
    anos.add(max(datetime.now().year, ANO_INICIAL))
    return sorted(anos)


def total_por_competencia(ano: int) -> dict[str, float]:
    linhas = _consultar(
        """
        SELECT competencia, SUM(valor) AS total
          FROM rendimentos
         WHERE competencia LIKE :ano
         GROUP BY competencia
         ORDER BY competencia
        """,
        ano=f"{int(ano)}-%",
    )
    return {linha["competencia"]: float(linha["total"]) for linha in linhas}


def capital_total(somente_ativos: bool = True) -> float:
    sql = "SELECT COALESCE(SUM(capital), 0) AS total FROM investimentos"
    if somente_ativos:
        sql += " WHERE ativo = 1"
    return float(_um(sql)["total"])


# --------------------------------------------- movimentações de capital ---

TIPOS_MOVIMENTACAO = ["aporte", "resgate", "imposto"]
CATEGORIA_SEM_JUROS = "Empréstimo sem juros"


def salvar_movimentacao(
    investimento_id: int,
    competencia: str,
    tipo: str,
    valor,
    data: str = "",
    observacao: str = "",
) -> int:
    """Registra um aporte, um resgate ou um imposto pago no mês."""
    if obter_investimento(investimento_id) is None:
        raise ValueError("Investimento não encontrado.")
    tipo = (tipo or "").strip().lower()
    if tipo not in TIPOS_MOVIMENTACAO:
        raise ValueError(
            "Tipo de movimentação inválido: use aporte, resgate ou imposto."
        )
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError("Valor da movimentação inválido: informe um número.") from None
    if valor <= 0:
        raise ValueError("O valor da movimentação deve ser maior que zero.")

    return _inserir(
        """
        INSERT INTO movimentacoes
            (investimento_id, competencia, tipo, valor, data, observacao, criado_em)
        VALUES (:investimento_id, :competencia, :tipo, :valor, :data, :observacao,
                :criado_em)
        RETURNING id
        """,
        investimento_id=int(investimento_id),
        competencia=validar_competencia(competencia),
        tipo=tipo,
        valor=valor,
        data=(data or "").strip(),
        observacao=(observacao or "").strip(),
        criado_em=agora(),
    )


def listar_movimentacoes(investimento_id: int | None = None) -> list[dict]:
    sql = """
        SELECT m.*, i.nome, i.categoria
          FROM movimentacoes m
          JOIN investimentos i ON i.id = m.investimento_id
    """
    params = {}
    if investimento_id is not None:
        sql += " WHERE m.investimento_id = :investimento_id"
        params["investimento_id"] = int(investimento_id)
    sql += " ORDER BY m.competencia, m.id"
    return _consultar(sql, **params)


def excluir_movimentacao(movimentacao_id: int) -> None:
    _executar("DELETE FROM movimentacoes WHERE id = :id", id=int(movimentacao_id))


def capital_movimentado_por_mes() -> dict[str, float]:
    """Efeito líquido das movimentações em cada mês.

    Aportes entram positivos; resgates e impostos pagos saem negativos.
    """
    linhas = _consultar(
        """
        SELECT competencia,
               SUM(CASE WHEN tipo = 'aporte' THEN valor ELSE -valor END) AS liquido
          FROM movimentacoes
         GROUP BY competencia
         ORDER BY competencia
        """
    )
    return {linha["competencia"]: float(linha["liquido"]) for linha in linhas}


def criar_emprestimo_avulso(
    nome: str,
    valor,
    competencia: str,
    data: str = "",
    observacoes: str = "",
) -> int:
    """Empréstimo sem juros: entra no patrimônio, mas não gera rendimento.

    Cria o investimento e já registra o aporte no mês em que o dinheiro saiu.
    """
    investimento_id = criar_investimento(
        nome=nome,
        categoria=CATEGORIA_SEM_JUROS,
        capital=valor,
        taxa_mensal=None,
        mes_inicio=competencia,
        observacoes=observacoes,
    )
    salvar_movimentacao(
        investimento_id, competencia, "aporte", valor, data,
        "Empréstimo concedido" + (f" em {data}" if data else ""),
    )
    return investimento_id


def saldo_emprestimo(investimento_id: int) -> float:
    """Quanto ainda está emprestado: aportes menos devoluções."""
    linha = _um(
        """
        SELECT COALESCE(SUM(CASE WHEN tipo = 'aporte' THEN valor ELSE -valor END), 0)
               AS saldo
          FROM movimentacoes
         WHERE investimento_id = :id
        """,
        id=int(investimento_id),
    )
    return round(float(linha["saldo"]), 2)


def registrar_devolucao(
    investimento_id: int,
    competencia: str,
    valor,
    data: str = "",
    observacao: str = "",
) -> float:
    """Registra a devolução (total ou parcial) de um empréstimo.

    Baixa o capital pelo valor devolvido e encerra o investimento quando o
    saldo chega a zero. Devolve o saldo que sobrou.
    """
    if obter_investimento(investimento_id) is None:
        raise ValueError("Investimento não encontrado.")
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError("Valor da devolução inválido: informe um número.") from None
    if valor <= 0:
        raise ValueError("O valor da devolução deve ser maior que zero.")

    saldo_atual = saldo_emprestimo(investimento_id)
    if valor > saldo_atual + 0.005:
        raise ValueError(
            f"A devolução ({valor:.2f}) é maior que o saldo em aberto "
            f"({saldo_atual:.2f})."
        )

    salvar_movimentacao(
        investimento_id, competencia, "resgate", valor, data,
        observacao or "Devolução do empréstimo",
    )
    saldo = saldo_emprestimo(investimento_id)
    _executar(
        "UPDATE investimentos SET capital = :capital, ativo = :ativo WHERE id = :id",
        capital=saldo,
        ativo=1 if saldo > 0.005 else 0,
        id=int(investimento_id),
    )
    return saldo


# ----------------------------------------------------------- energia solar ---

def _validar_positivo(valor, rotulo: str, obrigatorio: bool = True) -> float | None:
    if valor is None or valor == "":
        if obrigatorio:
            raise ValueError(f"Informe {rotulo}.")
        return None
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{rotulo.capitalize()} inválido: informe um número.") from None
    if valor < 0:
        raise ValueError(f"{rotulo.capitalize()} não pode ser negativo.")
    return valor


def salvar_fatura_solar(
    investimento_id: int,
    competencia: str,
    consumo_kwh,
    tarifa_cheia,
    total_pago,
    dias=None,
    tarifa_fio_b=None,
    ilum_publica=0,
    bandeira=0,
    mora=0,
    saldo_creditos=None,
) -> None:
    """Grava (ou atualiza) os dados da fatura de energia de um mês."""
    if obter_investimento(investimento_id) is None:
        raise ValueError("Investimento não encontrado.")
    _executar(
        """
        INSERT INTO faturas_solar
            (investimento_id, competencia, dias, consumo_kwh, tarifa_cheia,
             tarifa_fio_b, ilum_publica, bandeira, mora, total_pago,
             saldo_creditos, atualizado_em)
        VALUES (:investimento_id, :competencia, :dias, :consumo, :tarifa,
                :fio_b, :ilum, :bandeira, :mora, :total, :saldo, :atualizado_em)
        ON CONFLICT (investimento_id, competencia) DO UPDATE SET
            dias = excluded.dias,
            consumo_kwh = excluded.consumo_kwh,
            tarifa_cheia = excluded.tarifa_cheia,
            tarifa_fio_b = excluded.tarifa_fio_b,
            ilum_publica = excluded.ilum_publica,
            bandeira = excluded.bandeira,
            mora = excluded.mora,
            total_pago = excluded.total_pago,
            saldo_creditos = excluded.saldo_creditos,
            atualizado_em = excluded.atualizado_em
        """,
        investimento_id=int(investimento_id),
        competencia=validar_competencia(competencia),
        dias=int(dias) if dias not in (None, "") else None,
        consumo=_validar_positivo(consumo_kwh, "o consumo em kWh"),
        tarifa=_validar_positivo(tarifa_cheia, "a tarifa cheia"),
        fio_b=_validar_positivo(tarifa_fio_b, "a tarifa Fio B", obrigatorio=False),
        ilum=_validar_positivo(ilum_publica, "a contribuição de iluminação pública") or 0.0,
        bandeira=_validar_positivo(bandeira, "o adicional de bandeira") or 0.0,
        mora=_validar_positivo(mora, "a multa/juros de atraso") or 0.0,
        total=_validar_positivo(total_pago, "o total pago na fatura"),
        saldo=_validar_positivo(saldo_creditos, "o saldo de créditos", obrigatorio=False),
        atualizado_em=agora(),
    )


def listar_faturas_solar(investimento_id: int) -> list[dict]:
    return _consultar(
        "SELECT * FROM faturas_solar WHERE investimento_id = :id "
        "ORDER BY competencia",
        id=int(investimento_id),
    )


def obter_fatura_solar(investimento_id: int, competencia: str) -> dict | None:
    return _um(
        "SELECT * FROM faturas_solar "
        "WHERE investimento_id = :id AND competencia = :competencia",
        id=int(investimento_id),
        competencia=competencia,
    )


def excluir_fatura_solar(investimento_id: int, competencia: str) -> None:
    """Apaga a fatura e o lançamento de rendimento daquele mês."""
    with engine().begin() as con:
        for tabela in ("faturas_solar", "rendimentos"):
            con.execute(
                text(
                    f"DELETE FROM {tabela} "
                    "WHERE investimento_id = :id AND competencia = :competencia"
                ),
                {"id": int(investimento_id), "competencia": competencia},
            )


# ----------------------------------------------------------------- backup ---

def fazer_backup() -> Path:
    """Copia o banco local para backups/rendimentos_AAAAMMDD_HHMMSS.db.

    Só faz sentido no SQLite: no Postgres o backup é do próprio serviço.
    """
    import shutil

    if usando_postgres():
        raise ValueError(
            "O app está usando o banco na nuvem — o backup fica a cargo do Supabase. "
            "Use “Exportar Excel” para guardar uma cópia dos dados."
        )
    if not CAMINHO_DB.exists():
        raise ValueError("Ainda não há banco de dados para copiar.")
    PASTA_BACKUPS.mkdir(exist_ok=True)
    destino = PASTA_BACKUPS / f"rendimentos_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(CAMINHO_DB, destino)
    return destino


if __name__ == "__main__":
    criar_schema()
    print(f"Banco pronto: {url_banco()}")
