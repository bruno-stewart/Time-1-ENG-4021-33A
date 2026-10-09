import os
from datetime import date
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from psycopg2 import errors
from werkzeug.security import check_password_hash, generate_password_hash

import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")

TIPOS_EVENTO = [
    ("casamento", "Casamento"),
    ("corporativo", "Corporativo"),
    ("aniversario", "Aniversário"),
    ("formatura", "Formatura"),
    ("outro", "Outro"),
]

STATUS_PAGAMENTO = [
    ("pendente", "Aguardando pagamento"),
    ("retido", "Valor retido"),
    ("liberado", "Pago ao artista"),
    ("reembolsado", "Reembolsado"),
]


# ---------------------------------------------------------------
# Filtros usados nos templates
# ---------------------------------------------------------------
@app.template_filter("moeda")
def formatar_moeda(valor):
    if valor is None:
        return "R$ 0"
    texto = "{:,.0f}".format(float(valor)).replace(",", ".")
    return "R$ " + texto


@app.template_filter("data_br")
def formatar_data(valor):
    if valor is None:
        return "A definir"
    return valor.strftime("%d/%m/%Y")


@app.template_filter("tipo_evento")
def nome_tipo_evento(valor):
    for codigo, nome in TIPOS_EVENTO:
        if codigo == valor:
            return nome
    return valor


@app.template_filter("status_pagamento")
def nome_status_pagamento(valor):
    for codigo, nome in STATUS_PAGAMENTO:
        if codigo == valor:
            return nome
    return valor


# ---------------------------------------------------------------
# Controle de acesso
# ---------------------------------------------------------------
def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Entre na sua conta para continuar.", "erro")
            return redirect(url_for("login", proximo=request.path))
        return funcao(*args, **kwargs)
    return verificar


def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if session.get("papel") != "admin":
            flash("Acesso restrito ao administrador.", "erro")
            return redirect(url_for("index"))
        return funcao(*args, **kwargs)
    return verificar


def usuario_logado():
    if "usuario_id" not in session:
        return None
    return db.buscar_um("SELECT * FROM profiles WHERE id = %s", (session["usuario_id"],))


@app.context_processor
def variaveis_globais():
    return {"usuario_nome": session.get("nome"), "usuario_papel": session.get("papel")}


# ---------------------------------------------------------------
# Página inicial: busca e listagem de artistas
# ---------------------------------------------------------------
@app.route("/")
def index():
    categoria = request.args.get("categoria", "")
    cidade = request.args.get("cidade", "").strip()

    sql = "SELECT * FROM vw_artistas WHERE ativo = TRUE"
    parametros = []
    if categoria != "":
        sql = sql + " AND categoria_id = %s"
        parametros.append(categoria)
    if cidade != "":
        sql = sql + " AND cidade ILIKE %s"
        parametros.append("%" + cidade + "%")
    sql = sql + " ORDER BY nota_media DESC NULLS LAST, total_avaliacoes DESC, nome_artistico"

    artistas = db.buscar_todos(sql, tuple(parametros))
    categorias = db.buscar_todos("SELECT * FROM categorias ORDER BY nome")
    depoimentos = db.buscar_todos(
        "SELECT av.nota, av.comentario, p.nome AS cliente, a.nome_artistico, e.tipo "
        "FROM avaliacoes av "
        "JOIN profiles p ON p.id = av.cliente_id "
        "JOIN artistas a ON a.id = av.artista_id "
        "JOIN contratos c ON c.id = av.contrato_id "
        "JOIN eventos e ON e.id = c.evento_id "
        "WHERE av.comentario IS NOT NULL "
        "ORDER BY av.criado_em DESC LIMIT 3"
    )
    return render_template(
        "index.html",
        artistas=artistas,
        categorias=categorias,
        depoimentos=depoimentos,
        categoria_atual=categoria,
        cidade_atual=cidade,
    )


@app.route("/artistas/<artista_id>")
def artista_detalhe(artista_id):
    artista = db.buscar_um("SELECT * FROM vw_artistas WHERE id = %s", (artista_id,))
    if artista is None:
        flash("Artista não encontrado.", "erro")
        return redirect(url_for("index"))
    avaliacoes = db.buscar_todos(
        "SELECT av.nota, av.comentario, av.criado_em, p.nome AS cliente "
        "FROM avaliacoes av JOIN profiles p ON p.id = av.cliente_id "
        "WHERE av.artista_id = %s ORDER BY av.criado_em DESC",
        (artista_id,),
    )
    return render_template("artista.html", artista=artista, avaliacoes=avaliacoes)


# ---------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        senha = request.form.get("password", "")

        usuario = db.buscar_um("SELECT * FROM profiles WHERE username = %s", (username,))
        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            flash("Usuário ou senha incorretos.", "erro")
            return render_template("login.html", username=username), 401

        session.clear()
        session["usuario_id"] = str(usuario["id"])
        session["nome"] = usuario["nome"]
        session["papel"] = usuario["papel"]
        session.permanent = request.form.get("remember") == "on"

        proximo = request.args.get("proximo", "")
        if proximo.startswith("/") and not proximo.startswith("//"):
            return redirect(proximo)
        return redirect(url_for("painel"))

    return render_template("login.html", username="")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua conta.", "ok")
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# Cadastro de usuário
# ---------------------------------------------------------------
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    categorias = db.buscar_todos("SELECT * FROM categorias ORDER BY nome")

    if request.method == "POST":
        form = request.form
        tipo = form.get("tipo", "contratante")
        username = form.get("username", "").strip().lower()
        nome = form.get("nome", "").strip()
        email = form.get("email", "").strip().lower()
        telefone = form.get("telefone", "").strip()
        cidade = form.get("cidade", "").strip()
        categoria = form.get("categoria", "")
        preco = form.get("preco", "").strip()
        senha = form.get("senha", "")
        confirmar = form.get("confirmar", "")

        erros = []
        if len(username) < 3 or not username.replace("_", "").replace(".", "").isalnum():
            erros.append("O usuário precisa ter ao menos 3 caracteres (letras, números, ponto ou _).")
        if len(nome) < 3:
            erros.append("Informe seu nome completo.")
        if "@" not in email:
            erros.append("Informe um e-mail válido.")
        if cidade == "":
            erros.append("Informe sua cidade.")
        if tipo == "artista" and categoria == "":
            erros.append("Escolha uma categoria.")
        if len(senha) < 8:
            erros.append("A senha precisa ter ao menos 8 caracteres.")
        if senha != confirmar:
            erros.append("As senhas não coincidem.")
        if form.get("termos") != "on":
            erros.append("É necessário aceitar os termos.")

        if len(erros) == 0:
            papel = "cliente"
            if tipo == "artista":
                papel = "artista"
            try:
                novo = db.executar(
                    "INSERT INTO profiles (username, senha_hash, nome, email, telefone, cidade, papel) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (username, generate_password_hash(senha), nome, email, telefone, cidade, papel),
                    retornar=True,
                )
                if papel == "artista":
                    preco_minimo = 0
                    if preco != "":
                        preco_minimo = float(preco.replace(",", "."))
                    db.executar(
                        "INSERT INTO artistas (user_id, nome_artistico, categoria_id, cidade, preco_minimo) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (novo["id"], nome, categoria, cidade, preco_minimo),
                    )
                flash("Conta criada com sucesso! Agora é só entrar.", "ok")
                return redirect(url_for("login"))
            except errors.UniqueViolation:
                erros.append("Esse usuário ou e-mail já está cadastrado.")
            except ValueError:
                erros.append("Informe um preço válido.")

        for erro in erros:
            flash(erro, "erro")
        return render_template("cadastro.html", categorias=categorias, form=form), 400

    return render_template("cadastro.html", categorias=categorias, form={})


# ---------------------------------------------------------------
# Painel do cliente
# ---------------------------------------------------------------
@app.route("/painel")
@login_obrigatorio
def painel():
    usuario_id = session["usuario_id"]
    aba = request.args.get("aba", "historico")

    indicadores = db.buscar_um("SELECT * FROM vw_painel_cliente WHERE cliente_id = %s", (usuario_id,))
    contratos = db.buscar_todos(
        "SELECT c.*, a.nome_artistico, a.estilo, e.tipo, pg.status AS status_pagamento "
        "FROM contratos c "
        "JOIN artistas a ON a.id = c.artista_id "
        "JOIN eventos e ON e.id = c.evento_id "
        "LEFT JOIN pagamentos pg ON pg.contrato_id = c.id "
        "WHERE c.cliente_id = %s ORDER BY c.data_evento DESC",
        (usuario_id,),
    )
    pedidos = db.buscar_todos(
        "SELECT po.*, cat.nome AS categoria, e.tipo FROM pedidos_orcamento po "
        "JOIN eventos e ON e.id = po.evento_id "
        "JOIN categorias cat ON cat.id = po.categoria_id "
        "WHERE e.cliente_id = %s ORDER BY po.criado_em DESC",
        (usuario_id,),
    )
    mensagens = db.buscar_todos(
        "SELECT m.*, p.nome AS remetente FROM mensagens m "
        "JOIN profiles p ON p.id = m.remetente_id "
        "WHERE m.destinatario_id = %s OR m.remetente_id = %s ORDER BY m.enviada_em",
        (usuario_id, usuario_id),
    )
    return render_template(
        "painel.html",
        aba=aba,
        indicadores=indicadores,
        contratos=contratos,
        pedidos=pedidos,
        mensagens=mensagens,
        usuario_id=usuario_id,
    )


# ---------------------------------------------------------------
# Pedido de orçamento
# ---------------------------------------------------------------
@app.route("/orcamento", methods=["GET", "POST"])
@login_obrigatorio
def orcamento():
    categorias = db.buscar_todos("SELECT * FROM categorias ORDER BY nome")

    if request.method == "POST":
        form = request.form
        erros = []
        try:
            data_evento = date.fromisoformat(form.get("data", ""))
            if data_evento < date.today():
                erros.append("A data não pode estar no passado.")
        except ValueError:
            erros.append("Informe a data do evento.")
        if form.get("categoria", "") == "":
            erros.append("Escolha o tipo de serviço.")
        if form.get("horario", "") == "":
            erros.append("Informe o horário de início.")
        if not form.get("duracao", "").isdigit() or int(form.get("duracao")) < 1:
            erros.append("Informe a duração em horas.")
        if not form.get("convidados", "").isdigit() or int(form.get("convidados")) < 1:
            erros.append("Informe a estimativa de convidados.")
        if len(form.get("local", "").strip()) < 5:
            erros.append("Informe o local com pelo menos 5 caracteres.")
        if len(form.get("observacoes", "")) > 600:
            erros.append("As observações podem ter no máximo 600 caracteres.")

        if len(erros) == 0:
            evento = db.executar(
                "INSERT INTO eventos (cliente_id, tipo, categoria_id, data_evento, localizacao) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (session["usuario_id"], form.get("tipo_evento", "outro"), form["categoria"],
                 form["data"], form["local"].strip()),
                retornar=True,
            )
            db.executar(
                "INSERT INTO pedidos_orcamento (evento_id, categoria_id, data_evento, horario_inicio, "
                "duracao_horas, estimativa_convidados, local, observacoes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (evento["id"], form["categoria"], form["data"], form["horario"], form["duracao"],
                 form["convidados"], form["local"].strip(), form.get("observacoes", "").strip()),
            )
            flash("Pedido enviado! Você vai receber as propostas no seu painel.", "ok")
            return redirect(url_for("painel", aba="pedidos"))

        for erro in erros:
            flash(erro, "erro")
        return render_template("orcamento.html", categorias=categorias, tipos=TIPOS_EVENTO,
                               form=form, hoje=date.today().isoformat()), 400

    return render_template("orcamento.html", categorias=categorias, tipos=TIPOS_EVENTO,
                           form=request.args, hoje=date.today().isoformat())


# ---------------------------------------------------------------
# Edição de usuário
# ---------------------------------------------------------------
@app.route("/perfil/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_perfil():
    usuario = usuario_logado()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        cidade = request.form.get("cidade", "").strip()
        nova_senha = request.form.get("nova_senha", "")

        erros = []
        if len(nome) < 3:
            erros.append("Informe seu nome completo.")
        if "@" not in email:
            erros.append("Informe um e-mail válido.")
        if nova_senha != "" and len(nova_senha) < 8:
            erros.append("A nova senha precisa ter ao menos 8 caracteres.")

        if len(erros) == 0:
            try:
                db.executar(
                    "UPDATE profiles SET nome = %s, email = %s, telefone = %s, cidade = %s WHERE id = %s",
                    (nome, email, telefone, cidade, usuario["id"]),
                )
                if nova_senha != "":
                    db.executar(
                        "UPDATE profiles SET senha_hash = %s WHERE id = %s",
                        (generate_password_hash(nova_senha), usuario["id"]),
                    )
                session["nome"] = nome
                flash("Dados salvos!", "ok")
                return redirect(url_for("editar_perfil"))
            except errors.UniqueViolation:
                erros.append("Esse e-mail já está em uso por outra conta.")

        for erro in erros:
            flash(erro, "erro")

    return render_template("perfil_editar.html", usuario=usuario)


# ---------------------------------------------------------------
# Remoção de usuário
# ---------------------------------------------------------------
@app.route("/conta/excluir", methods=["GET", "POST"])
@login_obrigatorio
def excluir_conta():
    usuario = usuario_logado()

    if request.method == "POST":
        senha = request.form.get("password", "")
        confirmacao = request.form.get("confirm_text", "").strip().upper()

        retidos = db.buscar_um(
            "SELECT COUNT(*) AS total FROM pagamentos pg JOIN contratos c ON c.id = pg.contrato_id "
            "WHERE c.cliente_id = %s AND pg.status = 'retido'",
            (usuario["id"],),
        )

        if not check_password_hash(usuario["senha_hash"], senha):
            flash("Senha incorreta.", "erro")
        elif confirmacao != "EXCLUIR" or request.form.get("confirm_check") != "on":
            flash("Confirme a exclusão digitando EXCLUIR e marcando a caixa.", "erro")
        elif retidos["total"] > 0:
            flash("Você tem contratações com pagamento retido. Finalize-as antes de excluir a conta.", "erro")
        else:
            db.executar("UPDATE artistas SET ativo = FALSE WHERE user_id = %s", (usuario["id"],))
            db.executar("DELETE FROM profiles WHERE id = %s", (usuario["id"],))
            session.clear()
            flash("Sua conta foi excluída.", "ok")
            return redirect(url_for("index"))

    return render_template("excluir.html")


# ---------------------------------------------------------------
# Listagem de usuários (administrador)
# ---------------------------------------------------------------
@app.route("/usuarios")
@login_obrigatorio
@admin_obrigatorio
def listar_usuarios():
    busca = request.args.get("busca", "").strip()
    papel = request.args.get("papel", "")

    sql = "SELECT id, username, nome, email, telefone, cidade, papel, criado_em FROM profiles WHERE TRUE"
    parametros = []
    if busca != "":
        sql = sql + " AND (nome ILIKE %s OR username ILIKE %s OR email ILIKE %s)"
        parametros.append("%" + busca + "%")
        parametros.append("%" + busca + "%")
        parametros.append("%" + busca + "%")
    if papel != "":
        sql = sql + " AND papel = %s"
        parametros.append(papel)
    sql = sql + " ORDER BY criado_em DESC"

    usuarios = db.buscar_todos(sql, tuple(parametros))
    return render_template("usuarios.html", usuarios=usuarios, busca=busca, papel=papel)


@app.errorhandler(404)
def nao_encontrado(erro):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
