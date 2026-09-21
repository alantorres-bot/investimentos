"""Identidade visual do app: cores, estilos e blocos de tela reaproveitáveis.

A paleta vem do método de visualização de dados e passou no validador
(separação entre cores boa inclusive para daltonismo). O verde tem contraste
baixo sobre fundo claro, então ele só aparece em **marcas** (barras, linhas,
selos com fundo próprio) — nunca como cor de texto corrido.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------- paleta ---

VERDE = "#1baf7a"        # rendimento, valores realizados
VERDE_ESCURO = "#0f7f58"  # texto sobre fundo claro de selo
AZUL = "#2a78d6"         # patrimônio, capital
CINZA_MARCA = "#9aa0a6"  # previsto, estimativa
VERMELHO = "#e34948"     # queda, alerta

SUPERFICIE = "#fcfcfb"
CARTAO = "#ffffff"
BORDA = "#e6e6e2"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#86857f"


def aplicar_estilo() -> None:
    """CSS global: tipografia, cartões, tabelas e ajustes de celular."""
    st.markdown(
        f"""
        <style>
          .block-container {{ padding-top: 2.2rem; max-width: 1180px; }}

          h1, h2, h3 {{ letter-spacing: -0.02em; color: {TINTA}; }}
          h1 {{ font-size: 1.9rem; font-weight: 700; }}
          h2 {{ font-size: 1.25rem; font-weight: 650; margin-top: 0.4rem; }}

          /* barra lateral mais leve */
          section[data-testid="stSidebar"] {{
              background: {CARTAO};
              border-right: 1px solid {BORDA};
          }}

          /* cartões */
          div[data-testid="stVerticalBlockBorderWrapper"] {{
              background: {CARTAO};
              border-radius: 14px;
              border: 1px solid {BORDA};
              box-shadow: 0 1px 2px rgba(11,11,11,.04);
          }}

          /* indicadores */
          div[data-testid="stMetric"] {{ padding: 0.1rem 0; }}
          div[data-testid="stMetricLabel"] p {{
              font-size: 0.78rem; font-weight: 600; letter-spacing: .04em;
              text-transform: uppercase; color: {TINTA_3};
          }}
          div[data-testid="stMetricValue"] {{
              font-size: 1.55rem; font-weight: 680; color: {TINTA};
              font-variant-numeric: tabular-nums;
          }}

          /* tabelas */
          div[data-testid="stDataFrame"] {{
              border: 1px solid {BORDA}; border-radius: 12px;
          }}

          /* botões */
          div[data-testid="stButton"] button,
          div[data-testid="stFormSubmitButton"] button {{
              border-radius: 10px; font-weight: 600;
          }}

          /* abas */
          button[data-baseweb="tab"] {{ font-weight: 600; }}

          .heroi-rotulo {{
              font-size: .78rem; font-weight: 600; letter-spacing: .08em;
              text-transform: uppercase; color: {TINTA_3}; margin-bottom: .1rem;
          }}
          .heroi-valor {{
              font-size: 2.9rem; font-weight: 700; line-height: 1.05;
              color: {TINTA}; letter-spacing: -0.03em;
              font-variant-numeric: tabular-nums;
          }}
          .heroi-nota {{ font-size: .9rem; color: {TINTA_2}; margin-top: .35rem; }}

          .selo {{
              display: inline-block; padding: .18rem .6rem; border-radius: 999px;
              font-size: .85rem; font-weight: 650; margin-left: .1rem;
          }}
          .selo-alta {{ background: #e6f7f0; color: {VERDE_ESCURO}; }}
          .selo-baixa {{ background: #fdecec; color: #a92b2a; }}
          .selo-neutro {{ background: #f1f1ee; color: {TINTA_2}; }}

          @media (max-width: 640px) {{
              .block-container {{ padding: 1.6rem 1rem 3rem; }}
              h1 {{ font-size: 1.45rem; }}
              .heroi-valor {{ font-size: 2.1rem; }}
              div[data-testid="stMetricValue"] {{ font-size: 1.3rem; }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def cabecalho(titulo: str, subtitulo: str = "") -> None:
    st.markdown(f"# {titulo}")
    if subtitulo:
        st.caption(subtitulo)


def numero_heroi(rotulo: str, valor: str, nota: str = "",
                 variacao: str = "", sentido: str = "neutro") -> None:
    """Número principal da tela, com um selo opcional de variação."""
    selo = ""
    if variacao:
        classe = {"alta": "selo-alta", "baixa": "selo-baixa"}.get(sentido, "selo-neutro")
        seta = {"alta": "▲", "baixa": "▼"}.get(sentido, "")
        selo = f'<span class="selo {classe}">{seta}&nbsp;{variacao}</span>'
    st.markdown(
        f'<div class="heroi-rotulo">{rotulo}</div>'
        f'<div class="heroi-valor">{valor}&nbsp;&nbsp;{selo}</div>'
        + (f'<div class="heroi-nota">{nota}</div>' if nota else ""),
        unsafe_allow_html=True,
    )


def eixo_limpo(grafico):
    """Deixa grade e eixos discretos, como manda o guia de visualização."""
    return (
        grafico
        .configure_view(strokeWidth=0)
        .configure_axis(
            grid=False, domainColor=BORDA, tickColor=BORDA,
            labelColor=TINTA_2, titleColor=TINTA_3, labelFontSize=11,
        )
        .configure_axisY(
            grid=True, gridColor="#f0f0ec", gridDash=[0], domainOpacity=0,
            tickOpacity=0,
        )
        .configure_legend(
            labelColor=TINTA_2, titleColor=TINTA_3, symbolType="stroke",
            symbolStrokeWidth=3, labelFontSize=12,
        )
    )
