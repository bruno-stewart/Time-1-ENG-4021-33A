"""Cria as tabelas (schema.sql) e popula o banco com dados de exemplo.

Uso:  python popular_banco.py
"""
from werkzeug.security import generate_password_hash

from db import conectar

SENHA_PADRAO = "artconnect123"

CATEGORIAS = [
    ("Chefs & Buffet", "chefs-buffet", "Menus autorais, buffet e equipe de salão"),
    ("Mágicos", "magicos", "Mágica de perto, mentalismo e shows de palco"),
    ("DJs", "djs", "Sets sob medida com som e iluminação"),
    ("Cantores", "cantores", "Voz e violão, trio ou banda completa"),
    ("Foto & Vídeo", "foto-video", "Cobertura documental e filmes de evento"),
    ("Stand-up & Teatro", "standup-teatro", "Comédia, esquetes e performances ao vivo"),
    ("Arte Visual", "arte-visual", "Pintura ao vivo, murais e caricaturas"),
]

# (username, nome, email, telefone, cidade, papel)
USUARIOS = [
    ("admin", "Administrador ArtConnect", "admin@artconnect.com.br", "(21) 90000-0000", "Rio de Janeiro", "admin"),
    ("luiz", "Luiz Gullo", "luiz@exemplo.com", "(21) 98888-1111", "Rio de Janeiro", "cliente"),
    ("helena", "Helena Prado", "helena@exemplo.com", "(11) 97777-2222", "São Paulo", "cliente"),
    ("rafael", "Rafael Torres", "rafael@exemplo.com", "(21) 96666-3333", "Rio de Janeiro", "cliente"),
    ("selvaritmo", "Selva Ritmo", "contato@selvaritmo.com", "(11) 95555-4444", "São Paulo", "artista"),
    ("coletivomare", "Coletivo Maré", "contato@coletivomare.com", "(21) 94444-5555", "Rio de Janeiro", "artista"),
    ("neonsombra", "Neon Sombra", "contato@neonsombra.com", "(11) 93333-6666", "São Paulo", "artista"),
]

# (username ou None, nome_artistico, slug_categoria, estilo, cidade, preco, descricao)
ARTISTAS = [
    ("selvaritmo", "Selva Ritmo", "djs", "DJ Set", "São Paulo", 2400, "Sets de house e brasilidades para casamentos e festas."),
    (None, "Pulso Tropical", "djs", "Eletrônico", "Brasília", 2600, "Eletrônico tropical com iluminação própria."),
    (None, "Chef Raiz", "chefs-buffet", "Cozinha brasileira", "São Paulo", 3200, "Menu degustação com ingredientes locais."),
    (None, "Clara Veloso", "cantores", "MPB e Pop", "Salvador", 2100, "Voz e violão ou banda completa."),
    ("coletivomare", "Coletivo Maré", "cantores", "Jazz & MPB", "Rio de Janeiro", 1800, "Quinteto de jazz e MPB para eventos corporativos."),
    (None, "Ateliê Aurora", "arte-visual", "Pintura ao vivo", "Recife", 900, "Painéis pintados ao vivo durante o evento."),
    (None, "Mestre Ilusão", "magicos", "Mágica de perto", "Belo Horizonte", 1200, "Close-up e mentalismo para todas as idades."),
    (None, "Risada Tardia", "standup-teatro", "Stand-up", "São Paulo", 2860, "Stand-up de 45 minutos para eventos corporativos."),
    ("neonsombra", "Neon Sombra", "djs", "Eletrônico", "São Paulo", 3080, "Techno e eletrônico para aniversários e festas."),
    (None, "Vento Sul Trio", "cantores", "Acústico", "Sorocaba", 2530, "Set acústico de trio para festivais."),
    (None, "Estúdio Lume", "foto-video", "Eventos", "Rio de Janeiro", 2200, "Cobertura documental de foto e vídeo."),
]


def popular():
    conexao = conectar()
    cursor = conexao.cursor()

    print("Criando tabelas...")
    for nome_arquivo in ["schema.sql", "schema_sprint7.sql"]:
        arquivo = open(nome_arquivo, encoding="utf-8")
        cursor.execute(arquivo.read())
        arquivo.close()

    print("Inserindo categorias...")
    for categoria in CATEGORIAS:
        cursor.execute(
            "INSERT INTO categorias (nome, slug, descricao) VALUES (%s, %s, %s)",
            categoria,
        )

    print("Inserindo usuários...")
    senha_hash = generate_password_hash(SENHA_PADRAO)
    for usuario in USUARIOS:
        cursor.execute(
            "INSERT INTO profiles (username, senha_hash, nome, email, telefone, cidade, papel) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (usuario[0], senha_hash, usuario[1], usuario[2], usuario[3], usuario[4], usuario[5]),
        )

    print("Inserindo artistas...")
    for artista in ARTISTAS:
        cursor.execute(
            "INSERT INTO artistas (user_id, nome_artistico, categoria_id, estilo, cidade, preco_minimo, descricao) "
            "VALUES ((SELECT id FROM profiles WHERE username = %s), %s, "
            "(SELECT id FROM categorias WHERE slug = %s), %s, %s, %s, %s)",
            artista,
        )

    print("Inserindo eventos, contratos, pagamentos, avaliações e mensagens de exemplo...")
    # (cliente, artista, tipo, descricao, data, local, valor, status_contrato, status_pagamento, nota, comentario)
    contratos = [
        ("luiz", "Selva Ritmo", "casamento", "Set de 3 horas", "2026-10-03", "Espaço Jardim Ipê, São Paulo", 4620, "valor_retido", "retido", None, None),
        ("luiz", "Coletivo Maré", "corporativo", "Banda completa", "2026-10-24", "Hotel Vila Nova, Rio de Janeiro", 7150, "aguardando_pagamento", "pendente", None, None),
        ("luiz", "Neon Sombra", "aniversario", "Set eletrônico", "2026-11-15", "Casa Amarela, São Paulo", 3080, "valor_retido", "retido", None, None),
        ("luiz", "Risada Tardia", "corporativo", "Stand-up de 45 min", "2026-07-19", "Auditório Central, São Paulo", 2860, "concluido", "liberado", 5, "Plateia não parou de rir. Recomendo!"),
        ("luiz", "Ateliê Aurora", "outro", "Painel ao vivo", "2026-05-30", "Praça das Artes, São Paulo", 1980, "concluido", "liberado", 5, "Painel lindo, todo mundo parou para ver."),
        ("helena", "Selva Ritmo", "casamento", "Set de 4 horas", "2026-09-20", "Espaço Jardim Ipê, São Paulo", 4800, "concluido", "liberado", 5, "Chegaram uma hora antes para passagem de som. A pista não esvaziou."),
        ("rafael", "Coletivo Maré", "corporativo", "Quinteto", "2026-09-10", "Hotel Vila Nova, Rio de Janeiro", 6500, "concluido", "liberado", 4, "Banda muito bem ensaiada, atrasou alguns minutos na montagem."),
        ("luiz", "Estúdio Lume", "formatura", "Cobertura de foto e vídeo", "2026-08-15", "Clube Monte Líbano, Rio de Janeiro", 2200, "concluido", "liberado", None, None),
    ]
    for item in contratos:
        cursor.execute(
            "INSERT INTO eventos (cliente_id, tipo, categoria_id, data_evento, localizacao, orcamento) "
            "VALUES ((SELECT id FROM profiles WHERE username = %s), %s, "
            "(SELECT categoria_id FROM artistas WHERE nome_artistico = %s), %s, %s, %s) RETURNING id",
            (item[0], item[2], item[1], item[4], item[5], item[6]),
        )
        evento_id = cursor.fetchone()["id"]

        cursor.execute(
            "INSERT INTO contratos (evento_id, cliente_id, artista_id, descricao, data_evento, local, valor_total, status) "
            "VALUES (%s, (SELECT id FROM profiles WHERE username = %s), "
            "(SELECT id FROM artistas WHERE nome_artistico = %s), %s, %s, %s, %s, %s) RETURNING id, cliente_id, artista_id",
            (evento_id, item[0], item[1], item[3], item[4], item[5], item[6], item[7]),
        )
        contrato = cursor.fetchone()

        cursor.execute(
            "INSERT INTO pagamentos (contrato_id, valor, metodo, status) VALUES (%s, %s, 'pix', %s)",
            (contrato["id"], item[6], item[8]),
        )

        if item[9] is not None:
            cursor.execute(
                "INSERT INTO avaliacoes (contrato_id, artista_id, cliente_id, nota, comentario) "
                "VALUES (%s, %s, %s, %s, %s)",
                (contrato["id"], contrato["artista_id"], contrato["cliente_id"], item[9], item[10]),
            )

    # Mensagens do artista Selva Ritmo para o cliente luiz, dentro do contrato de 03/10
    mensagens = [
        "Oi! Confirmo a data de 3 de outubro. Consigo chegar às 18h.",
        "Vocês têm som no local ou levo minha estrutura?",
        "Mando o roteiro das músicas até amanhã.",
    ]
    for posicao in range(len(mensagens)):
        texto = mensagens[posicao]
        # horários diferentes para a conversa aparecer na ordem certa
        horas_atras = len(mensagens) - posicao
        cursor.execute(
            "INSERT INTO mensagens (contrato_id, remetente_id, destinatario_id, conteudo, enviada_em) VALUES "
            "((SELECT c.id FROM contratos c JOIN artistas a ON a.id = c.artista_id "
            "  JOIN profiles p ON p.id = c.cliente_id "
            "  WHERE a.nome_artistico = 'Selva Ritmo' AND p.username = 'luiz'), "
            "(SELECT id FROM profiles WHERE username = 'selvaritmo'), "
            "(SELECT id FROM profiles WHERE username = 'luiz'), %s, now() - %s * INTERVAL '1 hour')",
            (texto, horas_atras),
        )

    print("Inserindo pedidos de orçamento, propostas e agenda dos artistas...")
    # (cliente, slug_categoria, tipo, data, horario, duracao, convidados, local, observacoes)
    pedidos = [
        ("luiz", "djs", "casamento", "2026-12-12", "20:00", 4, 150, "Casa de Festas Lagoa, Rio de Janeiro", "Pista com house e MPB remix."),
        ("helena", "cantores", "aniversario", "2026-11-28", "19:00", 3, 60, "Salão Vila Madalena, São Paulo", "Voz e violão no jantar."),
        ("rafael", "djs", "corporativo", "2026-12-05", "21:00", 5, 200, "Rooftop Centro, Rio de Janeiro", None),
    ]
    for item in pedidos:
        cursor.execute(
            "INSERT INTO eventos (cliente_id, tipo, categoria_id, data_evento, localizacao) "
            "VALUES ((SELECT id FROM profiles WHERE username = %s), %s, "
            "(SELECT id FROM categorias WHERE slug = %s), %s, %s) RETURNING id",
            (item[0], item[2], item[1], item[3], item[7]),
        )
        evento_id = cursor.fetchone()["id"]
        cursor.execute(
            "INSERT INTO pedidos_orcamento (evento_id, categoria_id, data_evento, horario_inicio, "
            "duracao_horas, estimativa_convidados, local, observacoes) "
            "VALUES (%s, (SELECT id FROM categorias WHERE slug = %s), %s, %s, %s, %s, %s, %s)",
            (evento_id, item[1], item[3], item[4], item[5], item[6], item[7], item[8]),
        )

    # Duas respostas ao pedido do luiz: uma proposta normal e uma contraproposta de data
    cursor.execute(
        "INSERT INTO propostas (pedido_id, artista_id, valor, mensagem) VALUES ("
        "(SELECT po.id FROM pedidos_orcamento po JOIN eventos e ON e.id = po.evento_id "
        " JOIN profiles p ON p.id = e.cliente_id WHERE p.username = 'luiz' AND po.status = 'aberto'), "
        "(SELECT id FROM artistas WHERE nome_artistico = 'Selva Ritmo'), 2800, "
        "'Levo som e iluminação. Set de 4 horas com house e brasilidades.')"
    )
    cursor.execute(
        "INSERT INTO propostas (pedido_id, artista_id, valor, mensagem, data_sugerida) VALUES ("
        "(SELECT po.id FROM pedidos_orcamento po JOIN eventos e ON e.id = po.evento_id "
        " JOIN profiles p ON p.id = e.cliente_id WHERE p.username = 'luiz' AND po.status = 'aberto'), "
        "(SELECT id FROM artistas WHERE nome_artistico = 'Neon Sombra'), 3100, "
        "'No dia 12 já tenho show. Consigo no dia seguinte, mesmo horário.', '2026-12-13')"
    )
    cursor.execute(
        "UPDATE pedidos_orcamento SET status = 'com_propostas' WHERE id = "
        "(SELECT po.id FROM pedidos_orcamento po JOIN eventos e ON e.id = po.evento_id "
        " JOIN profiles p ON p.id = e.cliente_id WHERE p.username = 'luiz' AND po.status = 'aberto')"
    )

    # (artista, data, status, observacao)
    agenda = [
        ("Selva Ritmo", "2026-11-21", "ocupado", "Show particular"),
        ("Selva Ritmo", "2026-12-05", "ocupado", "Festival em Campinas"),
        ("Neon Sombra", "2026-12-12", "ocupado", "Show já fechado"),
        ("Coletivo Maré", "2026-11-29", "ocupado", "Viagem"),
        ("Coletivo Maré", "2026-12-20", "disponivel", "Aceita evento de fim de ano"),
    ]
    for item in agenda:
        cursor.execute(
            "INSERT INTO disponibilidade (artista_id, data, status, observacao) VALUES "
            "((SELECT id FROM artistas WHERE nome_artistico = %s), %s, %s, %s)",
            item,
        )

    print("Inserindo favoritos, notificações e portfólio (Sprint 7)...")
    for artista in ["Clara Veloso", "Chef Raiz"]:
        cursor.execute(
            "INSERT INTO favoritos (cliente_id, artista_id) VALUES "
            "((SELECT id FROM profiles WHERE username = 'luiz'), "
            "(SELECT id FROM artistas WHERE nome_artistico = %s))",
            (artista,),
        )

    # (username, tipo, texto, link)
    notificacoes = [
        ("luiz", "proposta", "Selva Ritmo enviou uma proposta de R$ 2.800 para o seu pedido de DJs.", "/painel?aba=pedidos"),
        ("luiz", "proposta", "Neon Sombra enviou uma contraproposta para 13/12/2026.", "/painel?aba=pedidos"),
        ("luiz", "pagamento", "O pagamento do contrato com Coletivo Maré está pendente.", "/painel?aba=historico"),
        ("selvaritmo", "mensagem", "Você tem uma conversa ativa com Luiz Gullo.", "/artista/painel?aba=propostas"),
    ]
    for item in notificacoes:
        cursor.execute(
            "INSERT INTO notificacoes (user_id, tipo, texto, link) VALUES "
            "((SELECT id FROM profiles WHERE username = %s), %s, %s, %s)",
            item,
        )

    # (artista, tipo, titulo, url)
    portfolio = [
        ("Selva Ritmo", "foto", "Set no casamento do Jardim Ipê", "/static/img/dj.jpg"),
        ("Coletivo Maré", "foto", "Quinteto no Hotel Vila Nova", "/static/img/jazz.jpg"),
        ("Neon Sombra", "foto", "Techno na Casa Amarela", "/static/img/eletronico.jpg"),
    ]
    for item in portfolio:
        cursor.execute(
            "INSERT INTO portfolio (artista_id, tipo, titulo, url) VALUES "
            "((SELECT id FROM artistas WHERE nome_artistico = %s), %s, %s, %s)",
            item,
        )

    conexao.commit()
    cursor.close()
    conexao.close()
    print("Banco populado! Usuário de teste: luiz / senha: " + SENHA_PADRAO)


if __name__ == "__main__":
    popular()
