"""Prepara o banco toda vez que o site sobe em produção.

Se as tabelas ainda não existem, roda o popular_banco.py (cria as tabelas e
insere os dados de exemplo). Se já existem, só aplica o schema_sprint7.sql,
que cria as tabelas novas sem apagar os dados que os usuários cadastraram.

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


def aplicar_atualizacoes():
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        arquivo = open("schema_sprint7.sql", encoding="utf-8")
        cursor.execute(arquivo.read())
        arquivo.close()
        conexao.commit()
    finally:
        conexao.close()


if __name__ == "__main__":
    if tabelas_existem():
        print("Banco já configurado: aplicando as tabelas novas, se faltar alguma...")
        aplicar_atualizacoes()
    else:
        print("Banco vazio: criando tabelas e dados de exemplo...")
        popular_banco.popular()
