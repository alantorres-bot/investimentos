# -*- coding: utf-8 -*-
"""Copia os dados do rendimentos.db local para o banco na nuvem (Supabase).

Rode uma única vez, depois de criar o projeto no Supabase:

    set DATABASE_URL=postgresql://...          (ou coloque em .streamlit/secrets.toml)
    .venv\\Scripts\\python.exe migrar_para_postgres.py

O script lê o SQLite local, cria as tabelas no destino e copia tudo,
preservando os ids. Ele recusa rodar se o destino já tiver dados, para não
duplicar nada — use --recriar se quiser apagar e refazer a carga.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

import db

TABELAS = ["investimentos", "rendimentos", "movimentacoes", "faturas_solar"]
SEQUENCIAS = {
    "investimentos": "investimentos_id_seq",
    "rendimentos": "rendimentos_id_seq",
    "movimentacoes": "movimentacoes_id_seq",
    "faturas_solar": "faturas_solar_id_seq",
}


def ler_sqlite(caminho: Path) -> dict[str, list[dict]]:
    if not caminho.exists():
        raise SystemExit(f"Banco local não encontrado: {caminho}")
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    dados = {}
    for tabela in TABELAS:
        try:
            linhas = con.execute(f"SELECT * FROM {tabela}").fetchall()
        except sqlite3.OperationalError:
            linhas = []
        dados[tabela] = [dict(linha) for linha in linhas]
    con.close()
    return dados


def main() -> None:
    recriar = "--recriar" in sys.argv

    url = db.url_banco()
    if url.startswith("sqlite"):
        raise SystemExit(
            "DATABASE_URL não está configurada — sem destino para migrar.\n"
            "Defina a variável de ambiente ou coloque em .streamlit/secrets.toml."
        )
    print(f"Destino: {url.split('@')[-1]}")  # sem mostrar usuário e senha

    dados = ler_sqlite(db.CAMINHO_DB)
    total = sum(len(linhas) for linhas in dados.values())
    print("Origem (SQLite local):")
    for tabela, linhas in dados.items():
        print(f"   {tabela:16} {len(linhas):>5} registro(s)")
    if not total:
        raise SystemExit("Nada a migrar: o banco local está vazio.")

    destino = create_engine(url, pool_pre_ping=True)
    db.criar_schema()  # cria as tabelas no destino

    with destino.begin() as con:
        existentes = {
            tabela: con.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar_one()
            for tabela in TABELAS
        }
    if any(existentes.values()):
        if not recriar:
            print("\nO destino já tem dados:")
            for tabela, quantidade in existentes.items():
                print(f"   {tabela:16} {quantidade:>5}")
            raise SystemExit(
                "Migração cancelada para não duplicar. Rode com --recriar para "
                "apagar o que está lá e carregar de novo."
            )
        with destino.begin() as con:
            for tabela in reversed(TABELAS):
                con.execute(text(f"DELETE FROM {tabela}"))
        print("\nDestino limpo (--recriar).")

    with destino.begin() as con:
        for tabela in TABELAS:
            linhas = dados[tabela]
            if not linhas:
                continue
            colunas = list(linhas[0].keys())
            sql = text(
                f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                f"VALUES ({', '.join(':' + c for c in colunas)})"
            )
            con.execute(sql, linhas)
            print(f"   {tabela:16} {len(linhas):>5} copiado(s)")

        # realinha as sequências para os próximos ids não colidirem
        for tabela, sequencia in SEQUENCIAS.items():
            con.execute(
                text(
                    f"SELECT setval('{sequencia}', "
                    f"COALESCE((SELECT MAX(id) FROM {tabela}), 1))"
                )
            )

    with destino.begin() as con:
        print("\nConferência no destino:")
        for tabela in TABELAS:
            quantidade = con.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar_one()
            marca = "OK " if quantidade == len(dados[tabela]) else "!! "
            print(f"   {marca}{tabela:16} {quantidade:>5} de {len(dados[tabela])}")

    print("\nMigração concluída.")


if __name__ == "__main__":
    main()
