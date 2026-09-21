# -*- coding: utf-8 -*-
"""Gera o hash da sua senha para colocar nos secrets.

Rode com:  .venv\\Scripts\\python.exe gerar_senha.py

A senha digitada não é gravada em lugar nenhum nem aparece na tela — só o hash
é impresso, e é ele que vai para o secrets.toml.
"""

from getpass import getpass

import auth


def main() -> None:
    print("Gerador de senha do Painel de Investimentos\n")
    usuario = input("Usuário (ex.: alan): ").strip() or "alan"

    while True:
        senha = getpass("Senha (mínimo 8 caracteres, não aparece na tela): ")
        confirmacao = getpass("Repita a senha: ")
        if senha != confirmacao:
            print("As senhas não conferem. Tente de novo.\n")
            continue
        try:
            resumo = auth.gerar_hash(senha)
            break
        except ValueError as erro:
            print(f"{erro}\n")

    print("\nCopie as duas linhas abaixo para o seu secrets:\n")
    print(f'APP_USUARIO = "{usuario}"')
    print(f'APP_SENHA_HASH = "{resumo}"')
    print(
        "\nLocalmente: cole em .streamlit/secrets.toml (já está no .gitignore).\n"
        "No Streamlit Cloud: Settings > Secrets, no app publicado."
    )


if __name__ == "__main__":
    main()
