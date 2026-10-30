import hashlib
import os
import secrets
import smtplib
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from psycopg2 import errors
from werkzeug.security import check_password_hash, generate_password_hash

import db
from match import calcular_compatibilidade
from politicas import dividir_valor, link_embed, percentual_reembolso

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")

MINUTOS_VALIDADE_TOKEN = 30

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

STATUS_PROPOSTA = [
    ("enviada", "Aguardando cliente"),
    ("aceita", "Aceita"),
    ("recusada", "Recusada pelo cliente"),
    ("declinada", "Você recusou"),
]

MOTIVOS_DENUNCIA = [
    ("ofensivo", "Conteúdo ofensivo ou discriminatório"),
    ("falso", "Informação falsa ou avaliação de quem não contratou"),
    ("spam", "Propaganda ou spam"),
    ("golpe", "Tentativa de golpe ou pagamento por fora"),
    ("outro", "Outro motivo"),
]

STATUS_CONTRATO = [
    ("aguardando_pagamento", "Aguardando pagamento"),
    ("valor_retido", "Confirmado"),
    ("concluido", "Concluído"),
    ("cancelado", "Cancelado"),
]


def traduzir(lista, codigo):
    for item in lista:
        if item[0] == codigo:
            return item[1]
    return codigo


def id_valido(texto):
    try:
        uuid.UUID(str(texto))
        return True
    except ValueError:
        return False


def numero_ou_none(texto):
    texto = texto.strip().replace(",", ".")
    if texto == "":
        return None
    return float(texto)


# ---------------------------------------------------------------
# Filtros usados nos templates
# ---------------------------------------------------------------
PASTA_FOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img")

# palavra no estilo/categoria do artista -> arquivo em static/img
FOTOS_POR_ESTILO = [
    ("eletr", "eletronico"),
    ("dj", "dj"),
    ("jazz", "jazz"),
    ("acústico", "folk"),
    ("folk", "folk"),
    ("cantor", "jazz"),
    ("mpb", "jazz"),
    ("chef", "chef"),
    ("buffet", "chef"),
    ("cozinha", "chef"),
    ("mágic", "magico"),
    ("foto", "foto"),
    ("stand", "standup"),
    ("teatro", "standup"),
    ("visual", "visual"),
    ("pintura", "visual"),
]


@app.template_filter("foto_artista")
def foto_artista(artista):
    """Devolve a URL da foto do artista, ou "" se não houver foto."""
    if artista.get("foto_url"):
        return artista["foto_url"]
    texto = ""
    for campo in ["estilo", "categoria", "descricao"]:
        if artista.get(campo):
            texto = texto + " " + str(artista[campo]).lower()
    for palavra, arquivo in FOTOS_POR_ESTILO:
        if palavra in texto and os.path.exists(os.path.join(PASTA_FOTOS, arquivo + ".jpg")):
            return url_for("static", filename="img/" + arquivo + ".jpg")
    return ""


@app.template_filter("embed_video")
def filtro_embed_video(url):
    return link_embed(url)


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
    return traduzir(TIPOS_EVENTO, valor)


@app.template_filter("status_pagamento")
def nome_status_pagamento(valor):
    return traduzir(STATUS_PAGAMENTO, valor)


@app.template_filter("status_proposta")
def nome_status_proposta(valor):
    return traduzir(STATUS_PROPOSTA, valor)


@app.template_filter("status_contrato")
def nome_status_contrato(valor):
    return traduzir(STATUS_CONTRATO, valor)


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


def artista_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if session.get("papel") != "artista" or artista_logado() is None:
            flash("Área exclusiva para artistas.", "erro")
            return redirect(url_for("index"))
        return funcao(*args, **kwargs)
    return verificar


def usuario_logado():
    if "usuario_id" not in session:
        return None
    return db.buscar_um("SELECT * FROM profiles WHERE id = %s", (session["usuario_id"],))


def artista_logado():
    if "usuario_id" not in session:
        return None
    return db.buscar_um("SELECT * FROM vw_artistas WHERE user_id = %s", (session["usuario_id"],))


def destino_painel():
    if session.get("papel") == "artista":
        return url_for("artista_painel")
    if session.get("papel") == "admin":
        return url_for("admin_dashboard")
    return url_for("painel")


@app.context_processor
def variaveis_globais():
    notificacoes_novas = 0
    if "usuario_id" in session:
        linha = db.buscar_um(
            "SELECT COUNT(*) AS total FROM notificacoes WHERE user_id = %s AND lida = FALSE",
            (session["usuario_id"],),
        )
        notificacoes_novas = linha["total"]
    return {
        "usuario_nome": session.get("nome"),
        "usuario_papel": session.get("papel"),
        "notificacoes_novas": notificacoes_novas,
    }


def notificar(user_id, tipo, texto, link):
    """Cria um aviso no sino do usuário. Artista sem conta (user_id vazio) é ignorado."""
    if user_id is None:
        return
    db.executar(
        "INSERT INTO notificacoes (user_id, tipo, texto, link) VALUES (%s, %s, %s, %s)",
        (user_id, tipo, texto[:200], link),
    )


def dono_do_artista(artista_id):
    linha = db.buscar_um("SELECT user_id FROM artistas WHERE id = %s", (artista_id,))
    if linha is None:
        return None
    return linha["user_id"]


# ---------------------------------------------------------------
# Página inicial: busca com ordenação por compatibilidade
# ---------------------------------------------------------------
@app.route("/")
def index():
    categoria = request.args.get("categoria", "")
    cidade = request.args.get("cidade", "").strip()
    orcamento_texto = request.args.get("orcamento", "").strip()
    data_texto = request.args.get("data", "").strip()

    orcamento = None
    if orcamento_texto != "":
        try:
            orcamento = numero_ou_none(orcamento_texto)
            if orcamento <= 0:
                orcamento = None
                flash("O orçamento precisa ser maior que zero.", "erro")
        except ValueError:
            flash("Informe o orçamento só com números.", "erro")

    data_evento = None
    if data_texto != "":
        try:
            data_evento = date.fromisoformat(data_texto)
        except ValueError:
            flash("Data inválida.", "erro")

    sql = "SELECT * FROM vw_artistas WHERE ativo = TRUE"
    parametros = []
    if categoria.isdigit():
        sql = sql + " AND categoria_id = %s"
        parametros.append(categoria)
    sql = sql + " ORDER BY nota_media DESC NULLS LAST, total_avaliacoes DESC, nome_artistico"
    artistas = db.buscar_todos(sql, tuple(parametros))

    ocupados = []
    if data_evento is not None:
        linhas = db.buscar_todos(
            "SELECT artista_id FROM disponibilidade WHERE data = %s AND status = 'ocupado' "
            "UNION SELECT artista_id FROM contratos WHERE data_evento = %s AND status <> 'cancelado'",
            (data_evento, data_evento),
        )
        for linha in linhas:
            ocupados.append(str(linha["artista_id"]))

    usar_match = cidade != "" or orcamento is not None or data_evento is not None
    for artista in artistas:
        artista["ocupado"] = str(artista["id"]) in ocupados
        artista["compatibilidade"] = calcular_compatibilidade(
            artista, cidade, orcamento, data_evento is not None, artista["ocupado"]
        )
    if usar_match:
        # ordena pela compatibilidade; em caso de empate, pela nota
        artistas.sort(key=lambda a: (a["compatibilidade"], float(a["nota_media"] or 0)), reverse=True)

    categorias = db.buscar_todos("SELECT * FROM categorias ORDER BY nome")
    depoimentos = db.buscar_todos(
        "SELECT av.nota, av.comentario, p.nome AS cliente, a.nome_artistico, e.tipo "
        "FROM avaliacoes av "
        "JOIN profiles p ON p.id = av.cliente_id "
        "JOIN artistas a ON a.id = av.artista_id "
        "JOIN contratos c ON c.id = av.contrato_id "
        "JOIN eventos e ON e.id = c.evento_id "
        "WHERE av.comentario IS NOT NULL AND av.oculta = FALSE "
        "ORDER BY av.criado_em DESC LIMIT 3"
    )
    totais = db.buscar_um(
        "SELECT COUNT(*) AS artistas, COUNT(DISTINCT cidade) AS cidades FROM artistas WHERE ativo = TRUE"
    )
    foto_hero = ""
    if os.path.exists(os.path.join(PASTA_FOTOS, "hero.jpg")):
        foto_hero = url_for("static", filename="img/hero.jpg")
    return render_template(
        "index.html",
        artistas=artistas,
        categorias=categorias,
        depoimentos=depoimentos,
        categoria_atual=categoria,
        cidade_atual=cidade,
        orcamento_atual=orcamento_texto,
        data_atual=data_texto,
        usar_match=usar_match,
        total_artistas=totais["artistas"],
        total_cidades=totais["cidades"],
        foto_hero=foto_hero,
    )


@app.route("/artistas/<artista_id>")
def artista_detalhe(artista_id):
    artista = None
    if id_valido(artista_id):
        artista = db.buscar_um("SELECT * FROM vw_artistas WHERE id = %s", (artista_id,))
    # perfil suspenso pela moderação só continua visível para o administrador
    if artista is not None and not artista["ativo"] and session.get("papel") != "admin":
        artista = None
    if artista is None:
        flash("Artista não encontrado.", "erro")
        return redirect(url_for("index"))
    avaliacoes = db.buscar_todos(
        "SELECT av.id, av.nota, av.comentario, av.criado_em, p.nome AS cliente "
        "FROM avaliacoes av JOIN profiles p ON p.id = av.cliente_id "
        "WHERE av.artista_id = %s AND av.oculta = FALSE ORDER BY av.criado_em DESC",
        (artista_id,),
    )
    portfolio = db.buscar_todos(
        "SELECT * FROM portfolio WHERE artista_id = %s ORDER BY criado_em", (artista_id,)
    )
    favorito = False
    if session.get("papel") == "cliente":
        favorito = db.buscar_um(
            "SELECT 1 FROM favoritos WHERE cliente_id = %s AND artista_id = %s",
            (session["usuario_id"], artista_id),
        ) is not None
    return render_template(
        "artista.html",
        artista=artista,
        avaliacoes=avaliacoes,
        portfolio=portfolio,
        favorito=favorito,
        motivos=MOTIVOS_DENUNCIA,
    )


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
        return redirect(destino_painel())

    return render_template("login.html", username="")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua conta.", "ok")
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# Recuperação de senha com token
# ---------------------------------------------------------------
def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def enviar_email(destinatario, assunto, corpo):
    """Envia por SMTP se o .env tiver SMTP_HOST; senão, mostra no terminal."""
    servidor = os.environ.get("SMTP_HOST", "")
    if servidor == "":
        print("----- E-MAIL (modo de desenvolvimento) -----")
        print("Para: " + destinatario)
        print("Assunto: " + assunto)
        print(corpo)
        print("--------------------------------------------")
        return

    mensagem = EmailMessage()
    mensagem["From"] = os.environ.get("SMTP_REMETENTE", "nao-responda@artconnect.com.br")
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)
    conexao = smtplib.SMTP(servidor, int(os.environ.get("SMTP_PORTA", 587)))
    try:
        conexao.starttls()
        conexao.login(os.environ.get("SMTP_USUARIO", ""), os.environ.get("SMTP_SENHA", ""))
        conexao.send_message(mensagem)
    finally:
        conexao.quit()


def buscar_token_valido(token):
    return db.buscar_um(
        "SELECT * FROM tokens_senha WHERE token_hash = %s AND usado = FALSE AND expira_em > now()",
        (hash_token(token),),
    )


@app.route("/senha/esqueci", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if "@" not in email:
            flash("Informe um e-mail válido.", "erro")
            return render_template("esqueci_senha.html", email=email), 400

        usuario = db.buscar_um("SELECT id, nome, email FROM profiles WHERE email = %s", (email,))
        if usuario is not None:
            token = secrets.token_urlsafe(32)
            expira = datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_VALIDADE_TOKEN)
            db.transacao([
                # um pedido novo invalida os links anteriores
                ("UPDATE tokens_senha SET usado = TRUE WHERE user_id = %s AND usado = FALSE", (usuario["id"],)),
                ("INSERT INTO tokens_senha (user_id, token_hash, expira_em) VALUES (%s, %s, %s)",
                 (usuario["id"], hash_token(token), expira)),
            ])
            link = url_for("redefinir_senha", token=token, _external=True)
            corpo = (
                "Olá, " + usuario["nome"] + "!\n\n"
                "Recebemos um pedido para redefinir a sua senha do ArtConnect.\n"
                "Use o link abaixo em até " + str(MINUTOS_VALIDADE_TOKEN) + " minutos:\n\n"
                + link + "\n\n"
                "Se não foi você, ignore este e-mail. Sua senha continua a mesma."
            )
            enviar_email(usuario["email"], "Redefinição de senha · ArtConnect", corpo)

        # mesma resposta com ou sem conta, para não revelar quais e-mails estão cadastrados
        flash("Se esse e-mail estiver cadastrado, você vai receber um link para criar uma nova senha.", "ok")
        return redirect(url_for("login"))

    return render_template("esqueci_senha.html", email="")


@app.route("/senha/redefinir/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    registro = buscar_token_valido(token)
    if registro is None:
        flash("Link inválido ou expirado. Peça um novo.", "erro")
        return redirect(url_for("esqueci_senha"))

    if request.method == "POST":
        senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar", "")
        if len(senha) < 8:
            flash("A senha precisa ter ao menos 8 caracteres.", "erro")
        elif senha != confirmar:
            flash("As senhas não coincidem.", "erro")
        else:
            db.transacao([
                ("UPDATE profiles SET senha_hash = %s WHERE id = %s",
                 (generate_password_hash(senha), registro["user_id"])),
                ("UPDATE tokens_senha SET usado = TRUE WHERE id = %s", (registro["id"],)),
            ])
            flash("Senha alterada! Entre com a nova senha.", "ok")
            return redirect(url_for("login"))
        return render_template("redefinir_senha.html", token=token), 400

    return render_template("redefinir_senha.html", token=token)


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
        if tipo == "artista" and not categoria.isdigit():
            erros.append("Escolha uma categoria.")

        # o preço é validado ANTES de gravar qualquer coisa no banco
        preco_minimo = 0
        if tipo == "artista" and preco != "":
            try:
                preco_minimo = numero_ou_none(preco)
                if preco_minimo < 0:
                    erros.append("O preço não pode ser negativo.")
            except ValueError:
                erros.append("Informe um preço válido.")

        if len(senha) < 8:
            erros.append("A senha precisa ter ao menos 8 caracteres.")
        if senha != confirmar:
            erros.append("As senhas não coincidem.")
        if form.get("termos") != "on":
            erros.append("É necessário aceitar os termos.")

        if len(erros) == 0:
            senha_hash = generate_password_hash(senha)
            try:
                if tipo == "artista":
                    # um único comando: cria o perfil e o artista juntos (ou nenhum dos dois)
                    db.executar(
                        "WITH novo AS ("
                        " INSERT INTO profiles (username, senha_hash, nome, email, telefone, cidade, papel) "
                        " VALUES (%s, %s, %s, %s, %s, %s, 'artista') RETURNING id) "
                        "INSERT INTO artistas (user_id, nome_artistico, categoria_id, cidade, preco_minimo) "
                        "SELECT id, %s, %s, %s, %s FROM novo",
                        (username, senha_hash, nome, email, telefone, cidade,
                         nome, categoria, cidade, preco_minimo),
                    )
                else:
                    db.executar(
                        "INSERT INTO profiles (username, senha_hash, nome, email, telefone, cidade, papel) "
                        "VALUES (%s, %s, %s, %s, %s, %s, 'cliente')",
                        (username, senha_hash, nome, email, telefone, cidade),
                    )
                flash("Conta criada com sucesso! Agora é só entrar.", "ok")
                return redirect(url_for("login"))
            except errors.UniqueViolation:
                erros.append("Esse usuário ou e-mail já está cadastrado.")
            except errors.ForeignKeyViolation:
                erros.append("Escolha uma categoria válida.")

        for erro in erros:
            flash(erro, "erro")
        return render_template("cadastro.html", categorias=categorias, form=form), 400

    return render_template("cadastro.html", categorias=categorias, form=request.args)


# ---------------------------------------------------------------
# Painel do cliente
# ---------------------------------------------------------------
@app.route("/painel")
@login_obrigatorio
def painel():
    if session.get("papel") == "artista":
        return redirect(url_for("artista_painel"))

    usuario_id = session["usuario_id"]
    aba = request.args.get("aba", "visao")

    indicadores = db.buscar_um("SELECT * FROM vw_painel_cliente WHERE cliente_id = %s", (usuario_id,))
    contratos = db.buscar_todos(
        "SELECT c.*, a.nome_artistico, a.estilo, a.foto_url, a.user_id AS artista_user_id, e.tipo, "
        "(SELECT pg.status FROM pagamentos pg WHERE pg.contrato_id = c.id ORDER BY pg.criado_em LIMIT 1) AS status_pagamento, "
        "av.id AS avaliacao_id, av.nota AS minha_nota, "
        "ca.valor_reembolso, ca.percentual_reembolso, ca.cancelado_por, "
        "(SELECT COUNT(*) FROM mensagens m WHERE m.contrato_id = c.id) AS total_mensagens, "
        "(SELECT COUNT(*) FROM mensagens m WHERE m.contrato_id = c.id AND m.destinatario_id = %s AND m.lida = FALSE) AS mensagens_novas, "
        "(c.data_evento <= CURRENT_DATE) AS ja_aconteceu, "
        "(c.data_evento >= CURRENT_DATE) AS no_futuro "
        "FROM contratos c "
        "JOIN artistas a ON a.id = c.artista_id "
        "JOIN eventos e ON e.id = c.evento_id "
        "LEFT JOIN avaliacoes av ON av.contrato_id = c.id "
        "LEFT JOIN cancelamentos ca ON ca.contrato_id = c.id "
        "WHERE c.cliente_id = %s ORDER BY c.data_evento DESC",
        (usuario_id, usuario_id),
    )
    pedidos = db.buscar_todos(
        "SELECT po.*, cat.nome AS categoria, e.tipo FROM pedidos_orcamento po "
        "JOIN eventos e ON e.id = po.evento_id "
        "JOIN categorias cat ON cat.id = po.categoria_id "
        "WHERE e.cliente_id = %s ORDER BY po.criado_em DESC",
        (usuario_id,),
    )
    propostas = db.buscar_todos(
        "SELECT pr.*, a.nome_artistico, a.id AS artista_id FROM propostas pr "
        "JOIN artistas a ON a.id = pr.artista_id "
        "JOIN pedidos_orcamento po ON po.id = pr.pedido_id "
        "JOIN eventos e ON e.id = po.evento_id "
        "WHERE e.cliente_id = %s AND pr.status <> 'declinada' ORDER BY pr.valor",
        (usuario_id,),
    )
    # mensagens antigas que não estão ligadas a nenhum contrato
    mensagens = db.buscar_todos(
        "SELECT m.*, p.nome AS remetente FROM mensagens m "
        "JOIN profiles p ON p.id = m.remetente_id "
        "WHERE m.contrato_id IS NULL AND (m.destinatario_id = %s OR m.remetente_id = %s) ORDER BY m.enviada_em",
        (usuario_id, usuario_id),
    )
    favoritos = db.buscar_todos(
        "SELECT a.*, f.criado_em AS salvo_em FROM favoritos f JOIN vw_artistas a ON a.id = f.artista_id "
        "WHERE f.cliente_id = %s AND a.ativo = TRUE ORDER BY f.criado_em DESC",
        (usuario_id,),
    )
    return render_template(
        "painel.html",
        aba=aba,
        indicadores=indicadores,
        contratos=contratos,
        pedidos=pedidos,
        propostas=propostas,
        mensagens=mensagens,
        favoritos=favoritos,
        usuario_id=usuario_id,
    )


def proposta_do_cliente(proposta_id):
    if not id_valido(proposta_id):
        return None
    return db.buscar_um(
        "SELECT pr.*, po.status AS status_pedido, po.evento_id, po.data_evento AS data_pedido, "
        "po.local, a.nome_artistico, cat.nome AS categoria "
        "FROM propostas pr "
        "JOIN pedidos_orcamento po ON po.id = pr.pedido_id "
        "JOIN eventos e ON e.id = po.evento_id "
        "JOIN artistas a ON a.id = pr.artista_id "
        "JOIN categorias cat ON cat.id = po.categoria_id "
        "WHERE pr.id = %s AND e.cliente_id = %s",
        (proposta_id, session["usuario_id"]),
    )


@app.route("/propostas/<proposta_id>/aceitar", methods=["POST"])
@login_obrigatorio
def aceitar_proposta(proposta_id):
    proposta = proposta_do_cliente(proposta_id)
    if proposta is None:
        flash("Proposta não encontrada.", "erro")
        return redirect(url_for("painel", aba="pedidos"))
    if proposta["status"] != "enviada" or proposta["status_pedido"] not in ("aberto", "com_propostas"):
        flash("Essa proposta não pode mais ser aceita.", "erro")
        return redirect(url_for("painel", aba="pedidos"))

    data_final = proposta["data_sugerida"] or proposta["data_pedido"]
    descricao = proposta["categoria"] + " · proposta aceita pelo painel"
    db.transacao([
        ("UPDATE propostas SET status = 'aceita' WHERE id = %s", (proposta["id"],)),
        ("UPDATE propostas SET status = 'recusada' WHERE pedido_id = %s AND id <> %s AND status = 'enviada'",
         (proposta["pedido_id"], proposta["id"])),
        ("UPDATE pedidos_orcamento SET status = 'fechado' WHERE id = %s", (proposta["pedido_id"],)),
        ("UPDATE eventos SET data_evento = %s WHERE id = %s", (data_final, proposta["evento_id"])),
        ("INSERT INTO contratos (evento_id, proposta_id, cliente_id, artista_id, descricao, data_evento, local, valor_total) "
         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
         (proposta["evento_id"], proposta["id"], session["usuario_id"], proposta["artista_id"],
          descricao, data_final, proposta["local"], proposta["valor"])),
        ("INSERT INTO pagamentos (contrato_id, valor, status) "
         "SELECT id, valor_total, 'pendente' FROM contratos WHERE proposta_id = %s", (proposta["id"],)),
        # a data passa a ficar ocupada na agenda do artista
        ("INSERT INTO disponibilidade (artista_id, data, status, observacao) VALUES (%s, %s, 'ocupado', 'Contrato ArtConnect') "
         "ON CONFLICT (artista_id, data) DO UPDATE SET status = 'ocupado', observacao = 'Contrato ArtConnect'",
         (proposta["artista_id"], data_final)),
    ])
    notificar(dono_do_artista(proposta["artista_id"]), "contrato",
              session["nome"] + " aceitou sua proposta para " + data_final.strftime("%d/%m/%Y") + ".",
              "/artista/painel?aba=agenda")
    flash("Proposta de " + proposta["nome_artistico"] + " aceita! Agora é só fazer o pagamento.", "ok")
    return redirect(url_for("painel", aba="historico"))


@app.route("/propostas/<proposta_id>/recusar", methods=["POST"])
@login_obrigatorio
def recusar_proposta(proposta_id):
    proposta = proposta_do_cliente(proposta_id)
    if proposta is None or proposta["status"] != "enviada":
        flash("Essa proposta não pode ser recusada.", "erro")
        return redirect(url_for("painel", aba="pedidos"))
    db.executar("UPDATE propostas SET status = 'recusada' WHERE id = %s", (proposta["id"],))
    notificar(dono_do_artista(proposta["artista_id"]), "proposta",
              session["nome"] + " recusou sua proposta.", "/artista/painel?aba=propostas")
    flash("Proposta recusada.", "ok")
    return redirect(url_for("painel", aba="pedidos"))


def contrato_do_cliente(contrato_id):
    if not id_valido(contrato_id):
        return None
    return db.buscar_um(
        "SELECT c.*, a.nome_artistico, av.id AS avaliacao_id FROM contratos c "
        "JOIN artistas a ON a.id = c.artista_id "
        "LEFT JOIN avaliacoes av ON av.contrato_id = c.id "
        "WHERE c.id = %s AND c.cliente_id = %s",
        (contrato_id, session["usuario_id"]),
    )


@app.route("/contratos/<contrato_id>/confirmar", methods=["POST"])
@login_obrigatorio
def confirmar_evento(contrato_id):
    contrato = contrato_do_cliente(contrato_id)
    if contrato is None:
        flash("Contrato não encontrado.", "erro")
    elif contrato["status"] != "valor_retido":
        flash("Só dá para confirmar contratos com pagamento retido.", "erro")
    elif contrato["data_evento"] > date.today():
        flash("Você só pode confirmar depois da data do evento.", "erro")
    else:
        db.transacao([
            ("UPDATE contratos SET status = 'concluido' WHERE id = %s", (contrato["id"],)),
            ("UPDATE pagamentos SET status = 'liberado', liberado_em = now() "
             "WHERE contrato_id = %s AND status = 'retido'", (contrato["id"],)),
        ])
        flash("Evento confirmado e pagamento liberado ao artista. Que tal avaliar?", "ok")
        return redirect(url_for("avaliar_contrato", contrato_id=contrato["id"]))
    return redirect(url_for("painel", aba="historico"))


@app.route("/contratos/<contrato_id>/avaliar", methods=["GET", "POST"])
@login_obrigatorio
def avaliar_contrato(contrato_id):
    contrato = contrato_do_cliente(contrato_id)
    if contrato is None:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("painel", aba="historico"))
    if contrato["status"] != "concluido":
        flash("Você só pode avaliar depois que o evento for concluído.", "erro")
        return redirect(url_for("painel", aba="historico"))
    if contrato["avaliacao_id"] is not None:
        flash("Você já avaliou esse serviço.", "erro")
        return redirect(url_for("painel", aba="historico"))

    if request.method == "POST":
        nota = request.form.get("nota", "")
        comentario = request.form.get("comentario", "").strip()
        erros = []
        if nota not in ("1", "2", "3", "4", "5"):
            erros.append("Escolha uma nota de 1 a 5.")
        if len(comentario) > 500:
            erros.append("O comentário pode ter no máximo 500 caracteres.")
        if len(erros) == 0:
            if comentario == "":
                comentario = None
            try:
                db.executar(
                    "INSERT INTO avaliacoes (contrato_id, artista_id, cliente_id, nota, comentario) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (contrato["id"], contrato["artista_id"], session["usuario_id"], int(nota), comentario),
                )
                notificar(dono_do_artista(contrato["artista_id"]), "avaliacao",
                          "Você recebeu uma avaliação nota " + nota + ".", "/artista/painel?aba=avaliacoes")
                flash("Obrigado pela avaliação! Ela já aparece no perfil de " + contrato["nome_artistico"] + ".", "ok")
                return redirect(url_for("artista_detalhe", artista_id=contrato["artista_id"]))
            except errors.UniqueViolation:
                erros.append("Você já avaliou esse serviço.")
        for erro in erros:
            flash(erro, "erro")
        return render_template("avaliar.html", contrato=contrato, form=request.form), 400

    return render_template("avaliar.html", contrato=contrato, form={})


# ---------------------------------------------------------------
# Painel do artista
# ---------------------------------------------------------------
@app.route("/artista/painel")
@login_obrigatorio
@artista_obrigatorio
def artista_painel():
    artista = artista_logado()
    aba = request.args.get("aba", "pedidos")

    pedidos = db.buscar_todos(
        "SELECT po.*, e.tipo, p.nome AS cliente, cat.nome AS categoria, "
        "EXISTS (SELECT 1 FROM disponibilidade d WHERE d.artista_id = %s AND d.data = po.data_evento "
        "        AND d.status = 'ocupado') AS conflito "
        "FROM pedidos_orcamento po "
        "JOIN eventos e ON e.id = po.evento_id "
        "JOIN profiles p ON p.id = e.cliente_id "
        "JOIN categorias cat ON cat.id = po.categoria_id "
        "WHERE po.categoria_id = %s AND po.status IN ('aberto', 'com_propostas') "
        "AND po.data_evento >= CURRENT_DATE "
        "AND NOT EXISTS (SELECT 1 FROM propostas pr WHERE pr.pedido_id = po.id AND pr.artista_id = %s) "
        "ORDER BY po.data_evento",
        (artista["id"], artista["categoria_id"], artista["id"]),
    )
    propostas = db.buscar_todos(
        "SELECT pr.*, po.data_evento, po.local, e.tipo, p.nome AS cliente FROM propostas pr "
        "JOIN pedidos_orcamento po ON po.id = pr.pedido_id "
        "JOIN eventos e ON e.id = po.evento_id "
        "JOIN profiles p ON p.id = e.cliente_id "
        "WHERE pr.artista_id = %s ORDER BY pr.criado_em DESC",
        (artista["id"],),
    )
    contratos = db.buscar_todos(
        "SELECT c.*, p.nome AS cliente, e.tipo, "
        "(SELECT COUNT(*) FROM mensagens m WHERE m.contrato_id = c.id AND m.destinatario_id = %s AND m.lida = FALSE) AS mensagens_novas "
        "FROM contratos c "
        "JOIN profiles p ON p.id = c.cliente_id "
        "JOIN eventos e ON e.id = c.evento_id "
        "WHERE c.artista_id = %s AND c.data_evento >= CURRENT_DATE AND c.status <> 'cancelado' "
        "ORDER BY c.data_evento",
        (session["usuario_id"], artista["id"]),
    )
    portfolio = db.buscar_todos(
        "SELECT * FROM portfolio WHERE artista_id = %s ORDER BY criado_em", (artista["id"],)
    )
    agenda = db.buscar_todos(
        "SELECT * FROM disponibilidade WHERE artista_id = %s AND data >= CURRENT_DATE ORDER BY data",
        (artista["id"],),
    )
    avaliacoes = db.buscar_todos(
        "SELECT av.*, p.nome AS cliente FROM avaliacoes av JOIN profiles p ON p.id = av.cliente_id "
        "WHERE av.artista_id = %s AND av.oculta = FALSE ORDER BY av.criado_em DESC",
        (artista["id"],),
    )

    aguardando = 0
    for proposta in propostas:
        if proposta["status"] == "enviada":
            aguardando = aguardando + 1

    return render_template(
        "painel_artista.html",
        artista=artista,
        aba=aba,
        pedidos=pedidos,
        propostas=propostas,
        contratos=contratos,
        agenda=agenda,
        avaliacoes=avaliacoes,
        portfolio=portfolio,
        limite_portfolio=LIMITE_PORTFOLIO,
        aguardando=aguardando,
        hoje=date.today().isoformat(),
    )


@app.route("/artista/pedidos/<pedido_id>/responder", methods=["POST"])
@login_obrigatorio
@artista_obrigatorio
def responder_pedido(pedido_id):
    artista = artista_logado()
    pedido = None
    if id_valido(pedido_id):
        pedido = db.buscar_um(
            "SELECT * FROM pedidos_orcamento WHERE id = %s AND categoria_id = %s "
            "AND status IN ('aberto', 'com_propostas')",
            (pedido_id, artista["categoria_id"]),
        )
    if pedido is None:
        flash("Pedido não encontrado ou já encerrado.", "erro")
        return redirect(url_for("artista_painel"))

    acao = request.form.get("acao", "")
    try:
        if acao == "recusar":
            db.executar(
                "INSERT INTO propostas (pedido_id, artista_id, status) VALUES (%s, %s, 'declinada')",
                (pedido["id"], artista["id"]),
            )
            flash("Pedido recusado. Ele não vai mais aparecer na sua lista.", "ok")
            return redirect(url_for("artista_painel"))

        erros = []
        valor = None
        try:
            valor = numero_ou_none(request.form.get("valor", ""))
        except ValueError:
            pass
        if valor is None or valor <= 0:
            erros.append("Informe o valor da proposta.")

        mensagem = request.form.get("mensagem", "").strip()
        if len(mensagem) > 500:
            erros.append("A mensagem pode ter no máximo 500 caracteres.")

        data_sugerida = None
        horario_sugerido = None
        if acao == "contraproposta":
            try:
                data_sugerida = date.fromisoformat(request.form.get("data_sugerida", ""))
                if data_sugerida < date.today():
                    erros.append("A nova data não pode estar no passado.")
            except ValueError:
                erros.append("Informe a nova data da contraproposta.")
            horario = request.form.get("horario_sugerido", "")
            if horario != "":
                horario_sugerido = horario
        else:
            ocupado = db.buscar_um(
                "SELECT 1 FROM disponibilidade WHERE artista_id = %s AND data = %s AND status = 'ocupado'",
                (artista["id"], pedido["data_evento"]),
            )
            if ocupado is not None:
                erros.append("Sua agenda está ocupada nessa data. Envie uma contraproposta com outra data.")

        if len(erros) > 0:
            for erro in erros:
                flash(erro, "erro")
            return redirect(url_for("artista_painel"))

        db.transacao([
            ("INSERT INTO propostas (pedido_id, artista_id, valor, mensagem, data_sugerida, horario_sugerido) "
             "VALUES (%s, %s, %s, %s, %s, %s)",
             (pedido["id"], artista["id"], valor, mensagem or None, data_sugerida, horario_sugerido)),
            ("UPDATE pedidos_orcamento SET status = 'com_propostas' WHERE id = %s AND status = 'aberto'",
             (pedido["id"],)),
        ])
        dono_pedido = db.buscar_um("SELECT cliente_id FROM eventos WHERE id = %s", (pedido["evento_id"],))
        texto_aviso = artista["nome_artistico"] + " enviou uma proposta de " + formatar_moeda(valor) + "."
        if acao == "contraproposta":
            texto_aviso = artista["nome_artistico"] + " sugeriu outra data: " + data_sugerida.strftime("%d/%m/%Y") + "."
        notificar(dono_pedido["cliente_id"], "proposta", texto_aviso, "/painel?aba=pedidos")
        if acao == "contraproposta":
            flash("Contraproposta enviada! O cliente vai ver a nova data no painel dele.", "ok")
        else:
            flash("Proposta enviada! Você será avisado quando o cliente responder.", "ok")
    except errors.UniqueViolation:
        flash("Você já respondeu esse pedido.", "erro")
    return redirect(url_for("artista_painel", aba="propostas"))


@app.route("/artista/agenda", methods=["POST"])
@login_obrigatorio
@artista_obrigatorio
def atualizar_agenda():
    artista = artista_logado()
    acao = request.form.get("acao", "salvar")
    try:
        data_agenda = date.fromisoformat(request.form.get("data", ""))
    except ValueError:
        flash("Informe uma data válida.", "erro")
        return redirect(url_for("artista_painel", aba="agenda"))

    if acao == "remover":
        db.executar("DELETE FROM disponibilidade WHERE artista_id = %s AND data = %s", (artista["id"], data_agenda))
        flash("Data liberada na agenda.", "ok")
        return redirect(url_for("artista_painel", aba="agenda"))

    status = request.form.get("status", "ocupado")
    observacao = request.form.get("observacao", "").strip()
    if data_agenda < date.today():
        flash("Escolha uma data a partir de hoje.", "erro")
    elif status not in ("ocupado", "disponivel"):
        flash("Status inválido.", "erro")
    elif len(observacao) > 120:
        flash("A observação pode ter no máximo 120 caracteres.", "erro")
    else:
        db.executar(
            "INSERT INTO disponibilidade (artista_id, data, status, observacao) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (artista_id, data) DO UPDATE SET status = EXCLUDED.status, observacao = EXCLUDED.observacao",
            (artista["id"], data_agenda, status, observacao or None),
        )
        flash("Agenda atualizada.", "ok")
    return redirect(url_for("artista_painel", aba="agenda"))


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
        if not form.get("categoria", "").isdigit():
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
# Administração
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
    if papel in ("cliente", "artista", "admin"):
        sql = sql + " AND papel = %s"
        parametros.append(papel)
    sql = sql + " ORDER BY criado_em DESC"

    usuarios = db.buscar_todos(sql, tuple(parametros))
    return render_template("usuarios.html", usuarios=usuarios, busca=busca, papel=papel)


@app.route("/admin")
@login_obrigatorio
@admin_obrigatorio
def admin_dashboard():
    totais = db.buscar_um(
        "SELECT "
        "(SELECT COUNT(*) FROM profiles WHERE papel = 'cliente') AS clientes, "
        "(SELECT COUNT(*) FROM profiles WHERE papel = 'artista') AS contas_artista, "
        "(SELECT COUNT(*) FROM artistas WHERE ativo = TRUE) AS artistas_ativos, "
        "(SELECT COUNT(*) FROM profiles WHERE criado_em >= now() - INTERVAL '30 days') AS novos_30_dias, "
        "(SELECT COUNT(*) FROM pedidos_orcamento) AS pedidos, "
        "(SELECT COUNT(*) FROM propostas WHERE status <> 'declinada') AS propostas, "
        "(SELECT COUNT(*) FROM contratos WHERE status <> 'cancelado') AS contratos, "
        "(SELECT COALESCE(SUM(valor_total), 0) FROM contratos WHERE status <> 'cancelado') AS volume, "
        "(SELECT COALESCE(SUM(valor), 0) FROM pagamentos WHERE status = 'retido') AS retido, "
        "(SELECT ROUND(AVG(nota), 1) FROM avaliacoes) AS nota_media, "
        "(SELECT COUNT(*) FROM avaliacoes) AS avaliacoes, "
        "(SELECT COUNT(*) FROM denuncias WHERE status = 'aberta') AS denuncias_abertas"
    )
    pedidos_por_status = db.buscar_todos(
        "SELECT status, COUNT(*) AS total FROM pedidos_orcamento GROUP BY status ORDER BY total DESC"
    )
    contratos_por_status = db.buscar_todos(
        "SELECT status, COUNT(*) AS total FROM contratos GROUP BY status ORDER BY total DESC"
    )
    categorias = db.buscar_todos(
        "SELECT cat.nome, "
        "(SELECT COUNT(*) FROM pedidos_orcamento po WHERE po.categoria_id = cat.id) AS pedidos, "
        "(SELECT COUNT(*) FROM contratos c JOIN artistas a ON a.id = c.artista_id "
        "  WHERE a.categoria_id = cat.id AND c.status <> 'cancelado') AS contratos "
        "FROM categorias cat ORDER BY pedidos DESC, contratos DESC, cat.nome"
    )
    ranking = db.buscar_todos(
        "SELECT nome_artistico, categoria, nota_media, total_avaliacoes FROM vw_artistas "
        "WHERE total_avaliacoes > 0 ORDER BY nota_media DESC, total_avaliacoes DESC LIMIT 5"
    )

    # conversão: quantos pedidos viraram contrato
    fechados = 0
    for linha in pedidos_por_status:
        if linha["status"] == "fechado":
            fechados = linha["total"]
    conversao = 0
    if totais["pedidos"] > 0:
        conversao = round(fechados / totais["pedidos"] * 100)

    maior = 1
    for linha in categorias:
        if linha["pedidos"] + linha["contratos"] > maior:
            maior = linha["pedidos"] + linha["contratos"]

    return render_template(
        "admin.html",
        totais=totais,
        pedidos_por_status=pedidos_por_status,
        contratos_por_status=contratos_por_status,
        categorias=categorias,
        ranking=ranking,
        conversao=conversao,
        maior=maior,
    )


# ---------------------------------------------------------------
# Sprint 7 · Pagamento simulado (o valor fica retido até o evento)
# ---------------------------------------------------------------
METODOS_PAGAMENTO = [
    ("pix", "Pix"),
    ("boleto", "Boleto bancário"),
]


@app.route("/contratos/<contrato_id>/pagar", methods=["GET", "POST"])
@login_obrigatorio
def pagar_contrato(contrato_id):
    contrato = contrato_do_cliente(contrato_id)
    if contrato is None:
        flash("Contrato não encontrado.", "erro")
        return redirect(url_for("painel", aba="historico"))
    if contrato["status"] != "aguardando_pagamento":
        flash("Esse contrato não está aguardando pagamento.", "erro")
        return redirect(url_for("painel", aba="historico"))
    if contrato["data_evento"] < date.today():
        flash("A data desse evento já passou. Cancele o contrato ou fale com o artista.", "erro")
        return redirect(url_for("painel", aba="historico"))

    if request.method == "POST":
        metodo = request.form.get("metodo", "")
        if metodo not in ("pix", "boleto"):
            flash("Escolha a forma de pagamento.", "erro")
            return render_template("pagar.html", contrato=contrato, metodos=METODOS_PAGAMENTO), 400
        if request.form.get("ciente") != "on":
            flash("Confirme que leu como funciona a retenção do valor.", "erro")
            return render_template("pagar.html", contrato=contrato, metodos=METODOS_PAGAMENTO), 400
        db.transacao([
            ("UPDATE pagamentos SET status = 'retido', metodo = %s, pago_em = now() "
             "WHERE contrato_id = %s AND status = 'pendente'", (metodo, contrato["id"])),
            ("UPDATE contratos SET status = 'valor_retido' WHERE id = %s", (contrato["id"],)),
        ])
        notificar(dono_do_artista(contrato["artista_id"]), "pagamento",
                  "Pagamento de " + formatar_moeda(contrato["valor_total"]) + " confirmado para "
                  + contrato["data_evento"].strftime("%d/%m/%Y") + ". O valor fica retido até o evento.",
                  "/artista/painel?aba=agenda")
        flash("Pagamento confirmado! O valor fica retido e só vai para o artista depois do evento.", "ok")
        return redirect(url_for("painel", aba="pagamentos"))

    return render_template("pagar.html", contrato=contrato, metodos=METODOS_PAGAMENTO)


# ---------------------------------------------------------------
# Sprint 7 · Cancelamento com reembolso (política da Sprint 6)
# ---------------------------------------------------------------
def simular_cancelamento(contrato, cancelado_por):
    """Calcula o reembolso de um contrato sem gravar nada."""
    dias = (contrato["data_evento"] - date.today()).days
    horas = (datetime.now(timezone.utc) - contrato["criado_em"]).total_seconds() / 3600
    percentual = percentual_reembolso(cancelado_por, dias, horas)
    pagamento = db.buscar_um(
        "SELECT * FROM pagamentos WHERE contrato_id = %s ORDER BY criado_em LIMIT 1", (contrato["id"],)
    )
    valor_pago = 0
    if pagamento is not None and pagamento["status"] == "retido":
        valor_pago = pagamento["valor"]
    reembolso, parte_artista = dividir_valor(valor_pago, percentual)
    return {
        "dias": dias,
        "percentual": percentual,
        "pagamento": pagamento,
        "valor_pago": valor_pago,
        "reembolso": reembolso,
        "parte_artista": parte_artista,
    }


def cancelar(contrato, cancelado_por, motivo):
    calculo = simular_cancelamento(contrato, cancelado_por)
    comandos = [
        ("UPDATE contratos SET status = 'cancelado' WHERE id = %s", (contrato["id"],)),
        ("INSERT INTO cancelamentos (contrato_id, cancelado_por, motivo, dias_antecedencia, "
         "percentual_reembolso, valor_reembolso, valor_artista) VALUES (%s, %s, %s, %s, %s, %s, %s)",
         (contrato["id"], cancelado_por, motivo, calculo["dias"], calculo["percentual"],
          calculo["reembolso"], calculo["parte_artista"])),
        # a data volta a ficar livre na agenda do artista
        ("DELETE FROM disponibilidade WHERE artista_id = %s AND data = %s AND observacao = 'Contrato ArtConnect'",
         (contrato["artista_id"], contrato["data_evento"])),
    ]
    pagamento = calculo["pagamento"]
    if pagamento is not None and pagamento["status"] == "pendente":
        # nada foi pago: o pagamento pendente deixa de existir
        comandos.append(("DELETE FROM pagamentos WHERE id = %s", (pagamento["id"],)))
    elif pagamento is not None and pagamento["status"] == "retido":
        if calculo["parte_artista"] == 0:
            comandos.append(("UPDATE pagamentos SET status = 'reembolsado' WHERE id = %s", (pagamento["id"],)))
        elif calculo["reembolso"] == 0:
            comandos.append(("UPDATE pagamentos SET status = 'liberado', liberado_em = now() WHERE id = %s",
                             (pagamento["id"],)))
        else:
            # reembolso parcial: o pagamento se divide em duas linhas
            comandos.append(("UPDATE pagamentos SET status = 'reembolsado', valor = %s WHERE id = %s",
                             (calculo["reembolso"], pagamento["id"])))
            comandos.append(("INSERT INTO pagamentos (contrato_id, valor, metodo, status, pago_em, liberado_em) "
                             "VALUES (%s, %s, %s, 'liberado', %s, now())",
                             (contrato["id"], calculo["parte_artista"], pagamento["metodo"], pagamento["pago_em"])))
    if cancelado_por == "artista" and contrato["proposta_id"] is not None:
        # o pedido volta a ficar aberto para outros artistas da categoria
        comandos.append(("UPDATE pedidos_orcamento SET status = 'aberto' WHERE status = 'fechado' AND data_evento >= CURRENT_DATE "
                         "AND id = (SELECT pedido_id FROM propostas WHERE id = %s)", (contrato["proposta_id"],)))
    db.transacao(comandos)
    return calculo


def pode_cancelar(contrato):
    return contrato["status"] in ("aguardando_pagamento", "valor_retido") and contrato["data_evento"] >= date.today()


@app.route("/contratos/<contrato_id>/cancelar", methods=["GET", "POST"])
@login_obrigatorio
def cancelar_contrato(contrato_id):
    contrato = contrato_do_cliente(contrato_id)
    if contrato is None or not pode_cancelar(contrato):
        flash("Esse contrato não pode ser cancelado.", "erro")
        return redirect(url_for("painel", aba="historico"))

    if request.method == "POST":
        motivo = request.form.get("motivo", "").strip()
        if len(motivo) < 5 or len(motivo) > 300:
            flash("Conte o motivo do cancelamento (5 a 300 caracteres).", "erro")
        elif request.form.get("confirmo") != "on":
            flash("Marque a caixa confirmando que leu as regras de reembolso.", "erro")
        else:
            calculo = cancelar(contrato, "cliente", motivo)
            notificar(dono_do_artista(contrato["artista_id"]), "cancelamento",
                      session["nome"] + " cancelou o evento de " + contrato["data_evento"].strftime("%d/%m/%Y")
                      + ". Sua parte: " + formatar_moeda(calculo["parte_artista"]) + ".",
                      "/artista/painel?aba=agenda")
            flash("Contrato cancelado. Reembolso de " + formatar_moeda(calculo["reembolso"]) + " ("
                  + str(calculo["percentual"]) + "% do valor pago).", "ok")
            return redirect(url_for("painel", aba="historico"))
        return render_template("cancelar.html", contrato=contrato,
                               calculo=simular_cancelamento(contrato, "cliente")), 400

    return render_template("cancelar.html", contrato=contrato, calculo=simular_cancelamento(contrato, "cliente"))


@app.route("/artista/contratos/<contrato_id>/cancelar", methods=["POST"])
@login_obrigatorio
@artista_obrigatorio
def artista_cancelar_contrato(contrato_id):
    artista = artista_logado()
    contrato = None
    if id_valido(contrato_id):
        contrato = db.buscar_um("SELECT * FROM contratos WHERE id = %s AND artista_id = %s",
                                (contrato_id, artista["id"]))
    motivo = request.form.get("motivo", "").strip()
    if contrato is None or not pode_cancelar(contrato):
        flash("Esse contrato não pode ser cancelado.", "erro")
    elif len(motivo) < 5 or len(motivo) > 300:
        flash("Conte ao cliente o motivo do cancelamento (5 a 300 caracteres).", "erro")
    else:
        calculo = cancelar(contrato, "artista", motivo)
        notificar(contrato["cliente_id"], "cancelamento",
                  artista["nome_artistico"] + " cancelou o evento de " + contrato["data_evento"].strftime("%d/%m/%Y")
                  + ". Você recebe 100% de volta.", "/painel?aba=historico")
        anteriores = db.buscar_um(
            "SELECT COUNT(*) AS total FROM cancelamentos ca JOIN contratos c ON c.id = ca.contrato_id "
            "WHERE c.artista_id = %s AND ca.cancelado_por = 'artista' AND ca.criado_em >= now() - INTERVAL '12 months'",
            (artista["id"],),
        )
        flash("Contrato cancelado e cliente reembolsado em " + formatar_moeda(calculo["reembolso"]) + ".", "ok")
        if anteriores["total"] >= 2:
            flash("Atenção: este é o seu cancelamento nº " + str(anteriores["total"])
                  + " em 12 meses. Pela política, o perfil pode ser suspenso por 30 dias.", "erro")
        else:
            flash("Advertência: cancelamentos pelo artista contam para a política de suspensão.", "erro")
    return redirect(url_for("artista_painel", aba="agenda"))


# ---------------------------------------------------------------
# Sprint 7 · Artistas favoritos
# ---------------------------------------------------------------
@app.route("/artistas/<artista_id>/favorito", methods=["POST"])
@login_obrigatorio
def alternar_favorito(artista_id):
    if session.get("papel") != "cliente":
        flash("Só clientes podem salvar artistas favoritos.", "erro")
        return redirect(url_for("index"))
    artista = None
    if id_valido(artista_id):
        artista = db.buscar_um("SELECT id, nome_artistico FROM artistas WHERE id = %s AND ativo = TRUE", (artista_id,))
    if artista is None:
        flash("Artista não encontrado.", "erro")
        return redirect(url_for("index"))

    existe = db.buscar_um("SELECT 1 FROM favoritos WHERE cliente_id = %s AND artista_id = %s",
                          (session["usuario_id"], artista["id"]))
    if existe is None:
        db.executar("INSERT INTO favoritos (cliente_id, artista_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (session["usuario_id"], artista["id"]))
        flash(artista["nome_artistico"] + " foi salvo nos seus favoritos.", "ok")
    else:
        db.executar("DELETE FROM favoritos WHERE cliente_id = %s AND artista_id = %s",
                    (session["usuario_id"], artista["id"]))
        flash(artista["nome_artistico"] + " saiu dos seus favoritos.", "ok")

    voltar = request.form.get("voltar", "")
    if voltar.startswith("/") and not voltar.startswith("//"):
        return redirect(voltar)
    return redirect(url_for("artista_detalhe", artista_id=artista["id"]))


# ---------------------------------------------------------------
# Sprint 7 · Central de notificações
# ---------------------------------------------------------------
@app.route("/notificacoes")
@login_obrigatorio
def notificacoes():
    lista = db.buscar_todos(
        "SELECT * FROM notificacoes WHERE user_id = %s ORDER BY criada_em DESC LIMIT 50",
        (session["usuario_id"],),
    )
    return render_template("notificacoes.html", notificacoes=lista)


@app.route("/notificacoes/<notificacao_id>/abrir", methods=["POST"])
@login_obrigatorio
def abrir_notificacao(notificacao_id):
    aviso = None
    if id_valido(notificacao_id):
        aviso = db.buscar_um("SELECT * FROM notificacoes WHERE id = %s AND user_id = %s",
                             (notificacao_id, session["usuario_id"]))
    if aviso is None:
        flash("Notificação não encontrada.", "erro")
        return redirect(url_for("notificacoes"))
    db.executar("UPDATE notificacoes SET lida = TRUE WHERE id = %s", (aviso["id"],))
    link = aviso["link"] or ""
    if link.startswith("/") and not link.startswith("//"):
        return redirect(link)
    return redirect(url_for("notificacoes"))


@app.route("/notificacoes/ler-todas", methods=["POST"])
@login_obrigatorio
def ler_todas_notificacoes():
    db.executar("UPDATE notificacoes SET lida = TRUE WHERE user_id = %s AND lida = FALSE", (session["usuario_id"],))
    flash("Todas as notificações foram marcadas como lidas.", "ok")
    return redirect(url_for("notificacoes"))


# ---------------------------------------------------------------
# Sprint 7 · Conversa entre cliente e artista dentro do contrato
# ---------------------------------------------------------------
def contrato_da_conversa(contrato_id):
    """Contrato que o usuário logado pode ver: ele é o cliente ou o artista."""
    if not id_valido(contrato_id):
        return None
    return db.buscar_um(
        "SELECT c.*, a.nome_artistico, a.user_id AS artista_user_id, a.estilo, a.categoria_id, a.foto_url, "
        "p.nome AS cliente FROM contratos c "
        "JOIN artistas a ON a.id = c.artista_id JOIN profiles p ON p.id = c.cliente_id "
        "WHERE c.id = %s AND (c.cliente_id = %s OR a.user_id = %s)",
        (contrato_id, session["usuario_id"], session["usuario_id"]),
    )


@app.route("/contratos/<contrato_id>/conversa", methods=["GET", "POST"])
@login_obrigatorio
def conversa(contrato_id):
    contrato = contrato_da_conversa(contrato_id)
    if contrato is None:
        flash("Conversa não encontrada.", "erro")
        return redirect(destino_painel())

    sou_cliente = str(contrato["cliente_id"]) == session["usuario_id"]
    outro_id = contrato["artista_user_id"] if sou_cliente else contrato["cliente_id"]

    if request.method == "POST":
        conteudo = request.form.get("conteudo", "").strip()
        if outro_id is None:
            flash("Esse artista ainda não tem conta na plataforma para responder mensagens.", "erro")
        elif contrato["status"] == "cancelado":
            flash("Não dá para enviar mensagens em um contrato cancelado.", "erro")
        elif conteudo == "" or len(conteudo) > 1000:
            flash("Escreva uma mensagem de até 1000 caracteres.", "erro")
        else:
            db.executar(
                "INSERT INTO mensagens (contrato_id, remetente_id, destinatario_id, conteudo) VALUES (%s, %s, %s, %s)",
                (contrato["id"], session["usuario_id"], outro_id, conteudo),
            )
            notificar(outro_id, "mensagem", session["nome"] + ": " + conteudo[:120],
                      url_for("conversa", contrato_id=contrato["id"]))
        return redirect(url_for("conversa", contrato_id=contrato["id"]) + "#fim")

    # abrir a conversa marca como lidas as mensagens recebidas
    db.executar("UPDATE mensagens SET lida = TRUE WHERE contrato_id = %s AND destinatario_id = %s AND lida = FALSE",
                (contrato["id"], session["usuario_id"]))
    mensagens = db.buscar_todos(
        "SELECT m.*, p.nome AS remetente FROM mensagens m JOIN profiles p ON p.id = m.remetente_id "
        "WHERE m.contrato_id = %s ORDER BY m.enviada_em",
        (contrato["id"],),
    )
    return render_template("conversa.html", contrato=contrato, mensagens=mensagens,
                           sou_cliente=sou_cliente, pode_responder=outro_id is not None and contrato["status"] != "cancelado",
                           usuario_id=session["usuario_id"])


# ---------------------------------------------------------------
# Sprint 7 · Denúncias e moderação
# ---------------------------------------------------------------
@app.route("/denunciar", methods=["POST"])
@login_obrigatorio
def denunciar():
    alvo = request.form.get("alvo", "")
    alvo_id = request.form.get("alvo_id", "")
    motivo = request.form.get("motivo", "")
    detalhes = request.form.get("detalhes", "").strip()

    artista_id = None
    avaliacao_id = None
    if id_valido(alvo_id) and alvo == "artista":
        linha = db.buscar_um("SELECT id FROM artistas WHERE id = %s", (alvo_id,))
        if linha is not None:
            artista_id = linha["id"]
            voltar = linha["id"]
    elif id_valido(alvo_id) and alvo == "avaliacao":
        linha = db.buscar_um("SELECT id, artista_id FROM avaliacoes WHERE id = %s", (alvo_id,))
        if linha is not None:
            avaliacao_id = linha["id"]
            voltar = linha["artista_id"]
    if artista_id is None and avaliacao_id is None:
        flash("Conteúdo não encontrado.", "erro")
        return redirect(url_for("index"))

    codigos = []
    for item in MOTIVOS_DENUNCIA:
        codigos.append(item[0])
    if motivo not in codigos:
        flash("Escolha o motivo da denúncia.", "erro")
    elif len(detalhes) > 500:
        flash("Os detalhes podem ter no máximo 500 caracteres.", "erro")
    else:
        try:
            db.executar(
                "INSERT INTO denuncias (denunciante_id, artista_id, avaliacao_id, motivo, detalhes) "
                "VALUES (%s, %s, %s, %s, %s)",
                (session["usuario_id"], artista_id, avaliacao_id, motivo, detalhes or None),
            )
            flash("Denúncia enviada. A equipe analisa em até 48 horas e você recebe a resposta nas notificações.", "ok")
        except errors.UniqueViolation:
            flash("Você já denunciou esse conteúdo e a análise ainda está aberta.", "erro")
    return redirect(url_for("artista_detalhe", artista_id=voltar))


@app.route("/admin/denuncias")
@login_obrigatorio
@admin_obrigatorio
def admin_denuncias():
    filtro = request.args.get("status", "aberta")
    if filtro not in ("aberta", "procedente", "improcedente"):
        filtro = "aberta"
    denuncias = db.buscar_todos(
        "SELECT d.*, p.nome AS denunciante, "
        "COALESCE(a.nome_artistico, a2.nome_artistico) AS artista, COALESCE(a.id, a2.id) AS artista_ref, "
        "a.ativo AS artista_ativo, av.comentario, av.nota, av.oculta, pc.nome AS autor_avaliacao "
        "FROM denuncias d "
        "JOIN profiles p ON p.id = d.denunciante_id "
        "LEFT JOIN artistas a ON a.id = d.artista_id "
        "LEFT JOIN avaliacoes av ON av.id = d.avaliacao_id "
        "LEFT JOIN artistas a2 ON a2.id = av.artista_id "
        "LEFT JOIN profiles pc ON pc.id = av.cliente_id "
        "WHERE d.status = %s ORDER BY d.criada_em",
        (filtro,),
    )
    contagem = db.buscar_todos("SELECT status, COUNT(*) AS total FROM denuncias GROUP BY status")
    totais = {"aberta": 0, "procedente": 0, "improcedente": 0}
    for linha in contagem:
        totais[linha["status"]] = linha["total"]
    return render_template("denuncias.html", denuncias=denuncias, filtro=filtro, totais=totais,
                           motivos=dict(MOTIVOS_DENUNCIA))


@app.route("/admin/denuncias/<denuncia_id>/decidir", methods=["POST"])
@login_obrigatorio
@admin_obrigatorio
def decidir_denuncia(denuncia_id):
    denuncia = None
    if id_valido(denuncia_id):
        denuncia = db.buscar_um("SELECT * FROM denuncias WHERE id = %s AND status = 'aberta'", (denuncia_id,))
    if denuncia is None:
        flash("Denúncia não encontrada ou já decidida.", "erro")
        return redirect(url_for("admin_denuncias"))

    decisao = request.form.get("decisao", "")
    justificativa = request.form.get("justificativa", "").strip()
    if decisao not in ("procedente", "improcedente"):
        flash("Escolha uma decisão.", "erro")
        return redirect(url_for("admin_denuncias"))
    if len(justificativa) < 5 or len(justificativa) > 300:
        flash("Escreva a justificativa da decisão (5 a 300 caracteres).", "erro")
        return redirect(url_for("admin_denuncias"))

    comandos = [
        ("UPDATE denuncias SET status = %s, decisao = %s, resolvida_em = now() WHERE id = %s",
         (decisao, justificativa, denuncia["id"])),
    ]
    if decisao == "procedente":
        if denuncia["avaliacao_id"] is not None:
            comandos.append(("UPDATE avaliacoes SET oculta = TRUE WHERE id = %s", (denuncia["avaliacao_id"],)))
            # outras denúncias abertas sobre a mesma avaliação são resolvidas junto
            comandos.append(("UPDATE denuncias SET status = 'procedente', decisao = %s, resolvida_em = now() "
                             "WHERE avaliacao_id = %s AND status = 'aberta'", (justificativa, denuncia["avaliacao_id"])))
        else:
            comandos.append(("UPDATE artistas SET ativo = FALSE WHERE id = %s", (denuncia["artista_id"],)))
            comandos.append(("UPDATE denuncias SET status = 'procedente', decisao = %s, resolvida_em = now() "
                             "WHERE artista_id = %s AND status = 'aberta'", (justificativa, denuncia["artista_id"])))
    db.transacao(comandos)

    texto = "Sua denúncia foi analisada: "
    if decisao == "procedente":
        texto = texto + "o conteúdo foi removido. Obrigado por ajudar!"
    else:
        texto = texto + "não encontramos violação das regras."
    notificar(denuncia["denunciante_id"], "moderacao", texto, "/notificacoes")
    if decisao == "procedente" and denuncia["artista_id"] is not None:
        notificar(dono_do_artista(denuncia["artista_id"]), "moderacao",
                  "Seu perfil foi suspenso pela moderação: " + justificativa, "/artista/painel")
    flash("Decisão registrada.", "ok")
    return redirect(url_for("admin_denuncias"))


@app.route("/admin/artistas/<artista_id>/reativar", methods=["POST"])
@login_obrigatorio
@admin_obrigatorio
def reativar_artista(artista_id):
    if id_valido(artista_id):
        db.executar("UPDATE artistas SET ativo = TRUE WHERE id = %s", (artista_id,))
        notificar(dono_do_artista(artista_id), "moderacao", "Seu perfil foi reativado e voltou para a busca.",
                  "/artista/painel")
        flash("Perfil reativado.", "ok")
    return redirect(url_for("admin_denuncias", status="procedente"))


# ---------------------------------------------------------------
# Sprint 7 · Portfólio do artista
# ---------------------------------------------------------------
LIMITE_PORTFOLIO = 12


@app.route("/artista/portfolio", methods=["POST"])
@login_obrigatorio
@artista_obrigatorio
def adicionar_portfolio():
    artista = artista_logado()
    tipo = request.form.get("tipo", "")
    titulo = request.form.get("titulo", "").strip()
    url = request.form.get("url", "").strip()

    total = db.buscar_um("SELECT COUNT(*) AS total FROM portfolio WHERE artista_id = %s", (artista["id"],))
    erros = []
    if tipo not in ("foto", "video", "audio"):
        erros.append("Escolha o tipo do item.")
    if len(titulo) < 3 or len(titulo) > 80:
        erros.append("O título precisa ter de 3 a 80 caracteres.")
    if not url.startswith("https://") or len(url) > 500 or " " in url:
        erros.append("Cole um link completo começando com https://")
    elif tipo == "video" and link_embed(url) == "":
        erros.append("Para vídeo, use um link do YouTube ou do Vimeo.")
    if total["total"] >= LIMITE_PORTFOLIO:
        erros.append("O portfólio aceita até " + str(LIMITE_PORTFOLIO) + " itens. Remova um para adicionar outro.")

    if len(erros) == 0:
        db.executar("INSERT INTO portfolio (artista_id, tipo, titulo, url) VALUES (%s, %s, %s, %s)",
                    (artista["id"], tipo, titulo, url))
        flash("Item adicionado ao portfólio. Ele já aparece no seu perfil.", "ok")
    for erro in erros:
        flash(erro, "erro")
    return redirect(url_for("artista_painel", aba="portfolio"))


@app.route("/artista/portfolio/<item_id>/remover", methods=["POST"])
@login_obrigatorio
@artista_obrigatorio
def remover_portfolio(item_id):
    artista = artista_logado()
    if id_valido(item_id):
        db.executar("DELETE FROM portfolio WHERE id = %s AND artista_id = %s", (item_id, artista["id"]))
        flash("Item removido do portfólio.", "ok")
    return redirect(url_for("artista_painel", aba="portfolio"))


@app.errorhandler(404)
def nao_encontrado(erro):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
