"""Tela de login do app.

A senha nunca é guardada em texto: o que fica em `.streamlit/secrets.toml` (ou
nos secrets do Streamlit Cloud) é um hash PBKDF2-SHA256 com sal, gerado pelo
script `gerar_senha.py`. O login compara o hash da senha digitada com esse
valor, em tempo constante.

Secrets esperados:

    APP_USUARIO = "alan"
    APP_SENHA_HASH = "pbkdf2_sha256$240000$<sal>$<hash>"
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
from pathlib import Path

import streamlit as st

ALGORITMO = "pbkdf2_sha256"
ITERACOES = 240_000
MAX_TENTATIVAS = 5


def gerar_hash(senha: str, iteracoes: int = ITERACOES) -> str:
    """Devolve 'pbkdf2_sha256$iterações$sal$hash' para guardar nos secrets."""
    if not senha or len(senha) < 8:
        raise ValueError("Use uma senha com pelo menos 8 caracteres.")
    sal = _secrets.token_hex(16)
    resumo = _calcular(senha, sal, iteracoes)
    return f"{ALGORITMO}${iteracoes}${sal}${resumo}"


def _calcular(senha: str, sal: str, iteracoes: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(sal), iteracoes
    ).hex()


def verificar(senha: str, armazenado: str) -> bool:
    """Confere a senha digitada contra o hash guardado."""
    try:
        algoritmo, iteracoes, sal, resumo = armazenado.split("$")
        if algoritmo != ALGORITMO:
            return False
        calculado = _calcular(senha, sal, int(iteracoes))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calculado, resumo)


def _config() -> tuple[str, str]:
    try:
        usuario = str(st.secrets.get("APP_USUARIO", "")).strip()
        senha_hash = str(st.secrets.get("APP_SENHA_HASH", "")).strip()
    except Exception:  # nenhum secrets.toml presente
        usuario, senha_hash = "", ""
    return usuario, senha_hash


CAMINHO_SECRETS = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


def _gravar_secrets(usuario: str, senha_hash: str) -> bool:
    """Guarda usuário e hash no secrets.toml local. False se não der para gravar."""
    try:
        CAMINHO_SECRETS.parent.mkdir(exist_ok=True)
        linhas = []
        if CAMINHO_SECRETS.exists():
            for linha in CAMINHO_SECRETS.read_text(encoding="utf-8").splitlines():
                if linha.strip().startswith(("APP_USUARIO", "APP_SENHA_HASH")):
                    continue
                linhas.append(linha)
        linhas = [
            f'APP_USUARIO = "{usuario}"',
            f'APP_SENHA_HASH = "{senha_hash}"',
            *linhas,
        ]
        CAMINHO_SECRETS.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _definir_senha() -> None:
    """Primeiro acesso: a própria tela cria a senha, sem precisar de terminal."""
    st.markdown("### 📈 Painel de Investimentos")
    st.info(
        "Primeiro acesso: escolha o usuário e a senha que você vai usar para entrar. "
        "A senha é guardada apenas como código embaralhado (hash) — nem eu nem o "
        "arquivo de configuração guardam a senha em si."
    )

    with st.form("definir_senha"):
        usuario = st.text_input("Usuário", value="alan")
        senha = st.text_input("Senha (mínimo 8 caracteres)", type="password")
        confirmacao = st.text_input("Repita a senha", type="password")
        salvar = st.form_submit_button("Salvar senha e entrar", type="primary")

    if salvar:
        if not usuario.strip():
            st.error("Informe o usuário.")
        elif senha != confirmacao:
            st.error("As duas senhas não são iguais.")
        else:
            try:
                senha_hash = gerar_hash(senha)
            except ValueError as erro:
                st.error(str(erro))
            else:
                if _gravar_secrets(usuario.strip(), senha_hash):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = usuario.strip()
                    st.rerun()
                else:
                    st.error(
                        "Não consegui gravar o arquivo de configuração. Copie as duas "
                        "linhas abaixo para os secrets do app:"
                    )
                    st.code(
                        f'APP_USUARIO = "{usuario.strip()}"\n'
                        f'APP_SENHA_HASH = "{senha_hash}"',
                        language="toml",
                    )
    st.stop()


def exigir_login(exigir_sempre: bool = False) -> None:
    """Bloqueia o app até o login ser feito.

    Sem senha configurada, o app roda livremente (uso local). Se
    `exigir_sempre` for True — caso do app publicado —, pede a criação da senha
    na hora, para nunca ficar exposto sem proteção.
    """
    if st.session_state.get("autenticado"):
        return

    usuario_certo, senha_hash = _config()
    if not senha_hash:
        if exigir_sempre:
            _definir_senha()
        return

    st.markdown("### 📈 Painel de Investimentos")
    st.caption("Informe seu usuário e senha para continuar.")

    with st.form("login"):
        usuario = st.text_input("Usuário", key="login_usuario")
        senha = st.text_input("Senha", type="password", key="login_senha")
        entrar = st.form_submit_button("Entrar", type="primary")

    tentativas = st.session_state.get("tentativas_login", 0)
    if tentativas >= MAX_TENTATIVAS:
        st.error(
            "Muitas tentativas sem sucesso. Feche e abra o aplicativo para "
            "tentar de novo."
        )
        st.stop()

    if entrar:
        usuario_ok = hmac.compare_digest(
            usuario.strip().lower(), usuario_certo.lower()
        )
        if usuario_ok and verificar(senha, senha_hash):
            st.session_state["autenticado"] = True
            st.session_state["usuario"] = usuario_certo
            st.session_state.pop("tentativas_login", None)
            st.rerun()
        st.session_state["tentativas_login"] = tentativas + 1
        st.error("Usuário ou senha incorretos.")

    st.stop()


def botao_sair() -> None:
    """Botão de sair na barra lateral, quando há login configurado."""
    if not st.session_state.get("autenticado"):
        return
    st.sidebar.caption(f"Conectado como {st.session_state.get('usuario', '')}")
    if st.sidebar.button("Sair", width="stretch"):
        for chave in ("autenticado", "usuario"):
            st.session_state.pop(chave, None)
        st.rerun()
