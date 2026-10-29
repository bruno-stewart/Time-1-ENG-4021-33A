"""Prepara o banco na primeira vez que o site sobe em produção.

Se as tabelas ainda não existem, roda o popular_banco.py (cria as tabelas e
insere os dados de exemplo). Se já existem, não faz nada, para não apagar
os dados que os usuários cadastraram.

Uso:  python iniciar_banco.py
"""
from db import conectar
import popular_banco


def tabelas_existem():
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute("SELECT to_regclass('public.profiles') IS NOT NULL AS existe")
        resultado = cursor.fetchone()
        return resultado["existe"]
    finally:
        conexao.close()


if __name__ == "__main__":
    if tabelas_existem():
        print("Banco já configurado, nada a fazer.")
    else:
        print("Banco vazio: criando tabelas e dados de exemplo...")
        popular_banco.popular()
