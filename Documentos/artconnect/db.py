import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/artconnect")


def conectar():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def buscar_todos(sql, parametros=()):
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(sql, parametros)
        linhas = cursor.fetchall()
        return linhas
    finally:
        conexao.close()


def buscar_um(sql, parametros=()):
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(sql, parametros)
        linha = cursor.fetchone()
        return linha
    finally:
        conexao.close()


def executar(sql, parametros=(), retornar=False):
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(sql, parametros)
        resultado = None
        if retornar:
            resultado = cursor.fetchone()
        conexao.commit()
        return resultado
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
