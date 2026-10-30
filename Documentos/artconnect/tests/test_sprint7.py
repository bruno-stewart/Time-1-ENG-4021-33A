"""Testes das funcionalidades da Sprint 7."""
from datetime import date, timedelta

import db
import iniciar_banco
from conftest import buscar, entrar
from politicas import dividir_valor, link_embed, percentual_reembolso


def texto(resposta):
    return resposta.get_data(as_text=True)


def id_de(sql, parametros=()):
    return str(buscar(sql, parametros)["id"])


def contrato(username, nome_artistico):
    return id_de(
        "SELECT c.id FROM contratos c JOIN profiles p ON p.id = c.cliente_id "
        "JOIN artistas a ON a.id = c.artista_id WHERE p.username = %s AND a.nome_artistico = %s",
        (username, nome_artistico),
    )


def proposta(nome_artistico):
    return id_de(
        "SELECT pr.id FROM propostas pr JOIN artistas a ON a.id = pr.artista_id WHERE a.nome_artistico = %s",
        (nome_artistico,),
    )


def artista(nome_artistico):
    return id_de("SELECT id FROM artistas WHERE nome_artistico = %s", (nome_artistico,))


def notificacoes_de(username):
    return db.buscar_todos(
        "SELECT n.* FROM notificacoes n JOIN profiles p ON p.id = n.user_id WHERE p.username = %s "
        "ORDER BY n.criada_em DESC",
        (username,),
    )


def aceitar_selva(cliente):
    """luiz aceita a proposta da Selva Ritmo: cria um contrato futuro aguardando pagamento."""
    entrar(cliente, "luiz")
    cliente.post("/propostas/" + proposta("Selva Ritmo") + "/aceitar")
    return id_de(
        "SELECT c.id FROM contratos c JOIN propostas pr ON pr.id = c.proposta_id "
        "JOIN artistas a ON a.id = pr.artista_id WHERE a.nome_artistico = 'Selva Ritmo'"
    )


# ---------------------------------------------------------------
# Regras de negócio (politicas.py)
# ---------------------------------------------------------------
def test_percentual_de_reembolso_segue_a_politica():
    assert percentual_reembolso("cliente", 45, 100) == 100
    assert percentual_reembolso("cliente", 30, 100) == 100
    assert percentual_reembolso("cliente", 20, 100) == 70
    assert percentual_reembolso("cliente", 10, 100) == 50
    assert percentual_reembolso("cliente", 3, 100) == 0
    # arrependimento em 24h só vale com o evento a mais de 7 dias
    assert percentual_reembolso("cliente", 10, 5) == 100
    assert percentual_reembolso("cliente", 5, 5) == 0
    # cancelamento pelo artista devolve tudo
    assert percentual_reembolso("artista", 1, 500) == 100


def test_divisao_do_valor():
    assert dividir_valor(3080, 70) == (2156.0, 924.0)
    assert dividir_valor(1000, 0) == (0, 1000.0)


def test_link_de_video_vira_embed():
    assert link_embed("https://www.youtube.com/watch?v=abc123XYZ_-") == "https://www.youtube-nocookie.com/embed/abc123XYZ_-"
    assert link_embed("https://youtu.be/abc123") == "https://www.youtube-nocookie.com/embed/abc123"
    assert link_embed("https://vimeo.com/76979871") == "https://player.vimeo.com/video/76979871"
    assert link_embed("https://exemplo.com/video.mp4") == ""
    assert link_embed("https://www.youtube.com/watch?v=<script>") == ""


# ---------------------------------------------------------------
# Pagamento simulado
# ---------------------------------------------------------------
def test_pagamento_retem_o_valor_e_avisa_o_artista(cliente):
    contrato_id = aceitar_selva(cliente)
    assert cliente.get("/contratos/" + contrato_id + "/pagar").status_code == 200

    resposta = cliente.post("/contratos/" + contrato_id + "/pagar", data={"metodo": "pix", "ciente": "on"},
                            follow_redirects=True)
    assert "Pagamento confirmado" in texto(resposta)
    assert buscar("SELECT status FROM contratos WHERE id = %s", (contrato_id,))["status"] == "valor_retido"
    pagamento = buscar("SELECT * FROM pagamentos WHERE contrato_id = %s", (contrato_id,))
    assert pagamento["status"] == "retido"
    assert pagamento["metodo"] == "pix"
    assert pagamento["pago_em"] is not None
    assert "Pagamento de R$ 2.800 confirmado" in notificacoes_de("selvaritmo")[0]["texto"]


def test_pagamento_exige_metodo_e_ciencia(cliente):
    contrato_id = aceitar_selva(cliente)
    resposta = cliente.post("/contratos/" + contrato_id + "/pagar", data={"metodo": "cartao", "ciente": "on"})
    assert resposta.status_code == 400
    resposta = cliente.post("/contratos/" + contrato_id + "/pagar", data={"metodo": "pix"})
    assert resposta.status_code == 400
    assert buscar("SELECT status FROM contratos WHERE id = %s", (contrato_id,))["status"] == "aguardando_pagamento"


def test_nao_paga_contrato_ja_pago_nem_de_outro_cliente(cliente):
    entrar(cliente, "helena")
    resposta = cliente.get("/contratos/" + contrato("luiz", "Neon Sombra") + "/pagar", follow_redirects=True)
    assert "Contrato não encontrado" in texto(resposta)
    entrar(cliente, "luiz")
    resposta = cliente.get("/contratos/" + contrato("luiz", "Neon Sombra") + "/pagar", follow_redirects=True)
    assert "não está aguardando pagamento" in texto(resposta)


# ---------------------------------------------------------------
# Cancelamento com reembolso
# ---------------------------------------------------------------
def test_cancelamento_pelo_cliente_com_reembolso_parcial(cliente):
    contrato_id = contrato("luiz", "Neon Sombra")
    # evento daqui a 20 dias, contrato fechado há 10 dias -> faixa de 70%
    db.executar("UPDATE contratos SET data_evento = %s, criado_em = now() - INTERVAL '10 days' WHERE id = %s",
                (date.today() + timedelta(days=20), contrato_id))
    entrar(cliente, "luiz")
    pagina = cliente.get("/contratos/" + contrato_id + "/cancelar")
    assert "70%" in texto(pagina)

    resposta = cliente.post("/contratos/" + contrato_id + "/cancelar",
                            data={"motivo": "Evento adiado pela empresa", "confirmo": "on"}, follow_redirects=True)
    assert "Reembolso de R$ 2.156" in texto(resposta)
    assert buscar("SELECT status FROM contratos WHERE id = %s", (contrato_id,))["status"] == "cancelado"
    registro = buscar("SELECT * FROM cancelamentos WHERE contrato_id = %s", (contrato_id,))
    assert registro["percentual_reembolso"] == 70
    assert float(registro["valor_artista"]) == 924
    linhas = db.buscar_todos("SELECT status, valor FROM pagamentos WHERE contrato_id = %s ORDER BY valor", (contrato_id,))
    assert [(l["status"], float(l["valor"])) for l in linhas] == [("liberado", 924.0), ("reembolsado", 2156.0)]
    assert "cancelou o evento" in notificacoes_de("neonsombra")[0]["texto"]


def test_cancelar_contrato_ainda_nao_pago_nao_cobra_nada(cliente):
    contrato_id = aceitar_selva(cliente)
    cliente.post("/contratos/" + contrato_id + "/cancelar", data={"motivo": "Mudamos de ideia", "confirmo": "on"})
    assert buscar("SELECT COUNT(*) AS n FROM pagamentos WHERE contrato_id = %s", (contrato_id,))["n"] == 0
    assert float(buscar("SELECT valor_reembolso FROM cancelamentos WHERE contrato_id = %s", (contrato_id,))["valor_reembolso"]) == 0
    # a data volta a ficar livre na agenda do artista
    assert buscar("SELECT 1 AS x FROM disponibilidade d JOIN artistas a ON a.id = d.artista_id "
                  "WHERE a.nome_artistico = 'Selva Ritmo' AND d.data = '2026-12-12'") is None


def test_cancelamento_exige_motivo_e_confirmacao(cliente):
    contrato_id = contrato("luiz", "Neon Sombra")
    db.executar("UPDATE contratos SET data_evento = %s WHERE id = %s", (date.today() + timedelta(days=20), contrato_id))
    entrar(cliente, "luiz")
    assert cliente.post("/contratos/" + contrato_id + "/cancelar", data={"motivo": "x", "confirmo": "on"}).status_code == 400
    assert cliente.post("/contratos/" + contrato_id + "/cancelar", data={"motivo": "Motivo válido"}).status_code == 400
    assert buscar("SELECT status FROM contratos WHERE id = %s", (contrato_id,))["status"] == "valor_retido"


def test_nao_cancela_evento_que_ja_passou(cliente):
    entrar(cliente, "luiz")
    resposta = cliente.get("/contratos/" + contrato("luiz", "Risada Tardia") + "/cancelar", follow_redirects=True)
    assert "não pode ser cancelado" in texto(resposta)


def test_artista_cancela_reembolsa_tudo_e_reabre_o_pedido(cliente):
    contrato_id = aceitar_selva(cliente)
    cliente.post("/contratos/" + contrato_id + "/pagar", data={"metodo": "pix", "ciente": "on"})
    entrar(cliente, "selvaritmo")
    resposta = cliente.post("/artista/contratos/" + contrato_id + "/cancelar",
                            data={"motivo": "Problema de saúde na equipe"}, follow_redirects=True)
    assert "cliente reembolsado em R$ 2.800" in texto(resposta)
    assert buscar("SELECT status FROM pagamentos WHERE contrato_id = %s", (contrato_id,))["status"] == "reembolsado"
    pedido = buscar("SELECT po.status FROM pedidos_orcamento po JOIN propostas pr ON pr.pedido_id = po.id "
                    "JOIN contratos c ON c.proposta_id = pr.id WHERE c.id = %s", (contrato_id,))
    assert pedido["status"] == "aberto"
    assert "100% de volta" in notificacoes_de("luiz")[0]["texto"]


def test_artista_nao_cancela_contrato_de_outro(cliente):
    entrar(cliente, "selvaritmo")
    cliente.post("/artista/contratos/" + contrato("luiz", "Neon Sombra") + "/cancelar", data={"motivo": "Tentando cancelar"})
    assert buscar("SELECT status FROM contratos WHERE id = %s", (contrato("luiz", "Neon Sombra"),))["status"] == "valor_retido"


# ---------------------------------------------------------------
# Favoritos
# ---------------------------------------------------------------
def test_cliente_salva_e_remove_favorito(cliente):
    entrar(cliente, "luiz")
    cliente.post("/artistas/" + artista("Mestre Ilusão") + "/favorito")
    painel = texto(cliente.get("/painel?aba=favoritos"))
    assert "Mestre Ilusão" in painel and "Clara Veloso" in painel
    assert "Salvo nos favoritos" in texto(cliente.get("/artistas/" + artista("Mestre Ilusão")))

    resposta = cliente.post("/artistas/" + artista("Mestre Ilusão") + "/favorito", follow_redirects=True)
    assert "saiu dos seus favoritos" in texto(resposta)
    assert buscar("SELECT COUNT(*) AS n FROM favoritos")["n"] == 2


def test_artista_nao_tem_favoritos(cliente):
    entrar(cliente, "selvaritmo")
    resposta = cliente.post("/artistas/" + artista("Mestre Ilusão") + "/favorito", follow_redirects=True)
    assert "Só clientes" in texto(resposta)
    assert buscar("SELECT COUNT(*) AS n FROM favoritos")["n"] == 2


# ---------------------------------------------------------------
# Notificações
# ---------------------------------------------------------------
def test_sino_mostra_quantidade_e_abrir_marca_como_lida(cliente):
    entrar(cliente, "luiz")
    assert "Notificações (3 novas)" in texto(cliente.get("/"))
    aviso = notificacoes_de("luiz")[0]
    resposta = cliente.post("/notificacoes/" + str(aviso["id"]) + "/abrir")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith(aviso["link"])
    assert buscar("SELECT lida FROM notificacoes WHERE id = %s", (aviso["id"],))["lida"] is True

    cliente.post("/notificacoes/ler-todas")
    assert buscar("SELECT COUNT(*) AS n FROM notificacoes n JOIN profiles p ON p.id = n.user_id "
                  "WHERE p.username = 'luiz' AND n.lida = FALSE")["n"] == 0


def test_nao_abre_notificacao_de_outra_pessoa(cliente):
    aviso = notificacoes_de("luiz")[0]
    entrar(cliente, "helena")
    resposta = cliente.post("/notificacoes/" + str(aviso["id"]) + "/abrir", follow_redirects=True)
    assert "Notificação não encontrada" in texto(resposta)
    assert buscar("SELECT lida FROM notificacoes WHERE id = %s", (aviso["id"],))["lida"] is False


def test_proposta_nova_gera_notificacao_para_o_cliente(cliente):
    entrar(cliente, "selvaritmo")
    pedido = id_de("SELECT po.id FROM pedidos_orcamento po JOIN eventos e ON e.id = po.evento_id "
                   "JOIN profiles p ON p.id = e.cliente_id WHERE p.username = 'rafael'")
    db.executar("DELETE FROM disponibilidade WHERE data = '2026-12-05'")
    cliente.post("/artista/pedidos/" + pedido + "/responder", data={"acao": "proposta", "valor": "3000"})
    assert notificacoes_de("rafael")[0]["texto"] == "Selva Ritmo enviou uma proposta de R$ 3.000."


# ---------------------------------------------------------------
# Conversa no contrato
# ---------------------------------------------------------------
def test_conversa_marca_lidas_e_envia_mensagem(cliente):
    contrato_id = contrato("luiz", "Selva Ritmo")
    entrar(cliente, "luiz")
    pagina = texto(cliente.get("/contratos/" + contrato_id + "/conversa"))
    assert "Vocês têm som no local" in pagina
    assert buscar("SELECT COUNT(*) AS n FROM mensagens WHERE contrato_id = %s AND lida = FALSE", (contrato_id,))["n"] == 0

    cliente.post("/contratos/" + contrato_id + "/conversa", data={"conteudo": "Temos som, pode vir só com o controlador."})
    entrar(cliente, "selvaritmo")
    assert "pode vir só com o controlador" in texto(cliente.get("/contratos/" + contrato_id + "/conversa"))
    assert notificacoes_de("selvaritmo")[0]["tipo"] == "mensagem"


def test_conversa_e_privada(cliente):
    entrar(cliente, "helena")
    resposta = cliente.get("/contratos/" + contrato("luiz", "Selva Ritmo") + "/conversa", follow_redirects=True)
    assert "Conversa não encontrada" in texto(resposta)


def test_nao_envia_mensagem_para_artista_sem_conta(cliente):
    contrato_id = contrato("luiz", "Estúdio Lume")
    entrar(cliente, "luiz")
    cliente.post("/contratos/" + contrato_id + "/conversa", data={"conteudo": "Oi!"})
    assert buscar("SELECT COUNT(*) AS n FROM mensagens WHERE contrato_id = %s", (contrato_id,))["n"] == 0


# ---------------------------------------------------------------
# Denúncias e moderação
# ---------------------------------------------------------------
def avaliacao_do_rafael():
    return id_de("SELECT av.id FROM avaliacoes av JOIN profiles p ON p.id = av.cliente_id WHERE p.username = 'rafael'")


def test_denuncia_de_avaliacao_procedente_esconde_e_recalcula_nota(cliente):
    entrar(cliente, "helena")
    cliente.post("/denunciar", data={"alvo": "avaliacao", "alvo_id": avaliacao_do_rafael(), "motivo": "falso"})
    resposta = cliente.post("/denunciar", data={"alvo": "avaliacao", "alvo_id": avaliacao_do_rafael(), "motivo": "falso"},
                            follow_redirects=True)
    assert "já denunciou" in texto(resposta)

    entrar(cliente, "admin")
    assert "Banda muito bem ensaiada" in texto(cliente.get("/admin/denuncias"))
    denuncia = id_de("SELECT id FROM denuncias")
    cliente.post("/admin/denuncias/" + denuncia + "/decidir",
                 data={"decisao": "procedente", "justificativa": "Cliente não reconheceu o evento"})

    assert buscar("SELECT oculta FROM avaliacoes WHERE id = %s", (avaliacao_do_rafael(),))["oculta"] is True
    perfil = texto(cliente.get("/artistas/" + artista("Coletivo Maré")))
    assert "Banda muito bem ensaiada" not in perfil
    assert buscar("SELECT total_avaliacoes FROM vw_artistas WHERE nome_artistico = 'Coletivo Maré'")["total_avaliacoes"] == 0
    assert "conteúdo foi removido" in notificacoes_de("helena")[0]["texto"]


def test_denuncia_improcedente_mantem_conteudo(cliente):
    entrar(cliente, "helena")
    cliente.post("/denunciar", data={"alvo": "avaliacao", "alvo_id": avaliacao_do_rafael(), "motivo": "ofensivo"})
    entrar(cliente, "admin")
    cliente.post("/admin/denuncias/" + id_de("SELECT id FROM denuncias") + "/decidir",
                 data={"decisao": "improcedente", "justificativa": "Crítica educada"})
    assert buscar("SELECT oculta FROM avaliacoes WHERE id = %s", (avaliacao_do_rafael(),))["oculta"] is False
    assert buscar("SELECT status FROM denuncias")["status"] == "improcedente"


def test_perfil_suspenso_some_da_busca_e_pode_voltar(cliente):
    entrar(cliente, "luiz")
    cliente.post("/denunciar", data={"alvo": "artista", "alvo_id": artista("Mestre Ilusão"), "motivo": "golpe",
                                     "detalhes": "Pediu pagamento por fora"})
    entrar(cliente, "admin")
    cliente.post("/admin/denuncias/" + id_de("SELECT id FROM denuncias") + "/decidir",
                 data={"decisao": "procedente", "justificativa": "Pedido de pagamento por fora confirmado"})
    cliente.get("/logout")
    assert "Mestre Ilusão" not in texto(cliente.get("/"))
    assert "Artista não encontrado" in texto(cliente.get("/artistas/" + artista("Mestre Ilusão"), follow_redirects=True))

    entrar(cliente, "admin")
    cliente.post("/admin/artistas/" + artista("Mestre Ilusão") + "/reativar")
    cliente.get("/logout")
    assert "Mestre Ilusão" in texto(cliente.get("/"))


def test_so_admin_decide_denuncia(cliente):
    entrar(cliente, "helena")
    cliente.post("/denunciar", data={"alvo": "avaliacao", "alvo_id": avaliacao_do_rafael(), "motivo": "spam"})
    cliente.post("/admin/denuncias/" + id_de("SELECT id FROM denuncias") + "/decidir",
                 data={"decisao": "procedente", "justificativa": "Tentando sozinha"})
    assert buscar("SELECT status FROM denuncias")["status"] == "aberta"


# ---------------------------------------------------------------
# Portfólio
# ---------------------------------------------------------------
def test_artista_adiciona_video_que_aparece_no_perfil(cliente):
    entrar(cliente, "selvaritmo")
    cliente.post("/artista/portfolio", data={"tipo": "video", "titulo": "Set completo",
                                             "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    perfil = texto(cliente.get("/artistas/" + artista("Selva Ritmo")))
    assert "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" in perfil
    assert "Set no casamento do Jardim Ipê" in perfil


def test_portfolio_valida_links(cliente):
    entrar(cliente, "selvaritmo")
    resposta = cliente.post("/artista/portfolio", data={"tipo": "foto", "titulo": "Foto",
                                                        "url": "http://inseguro.com/a.jpg"}, follow_redirects=True)
    assert "https://" in texto(resposta)
    resposta = cliente.post("/artista/portfolio", data={"tipo": "video", "titulo": "Vídeo",
                                                        "url": "https://exemplo.com/video.mp4"}, follow_redirects=True)
    assert "YouTube ou do Vimeo" in texto(resposta)
    assert buscar("SELECT COUNT(*) AS n FROM portfolio p JOIN artistas a ON a.id = p.artista_id "
                  "WHERE a.nome_artistico = 'Selva Ritmo'")["n"] == 1


def test_artista_so_remove_o_proprio_item(cliente):
    item = id_de("SELECT p.id FROM portfolio p JOIN artistas a ON a.id = p.artista_id WHERE a.nome_artistico = 'Neon Sombra'")
    entrar(cliente, "selvaritmo")
    cliente.post("/artista/portfolio/" + item + "/remover")
    assert buscar("SELECT 1 AS x FROM portfolio WHERE id = %s", (item,)) is not None
    entrar(cliente, "neonsombra")
    cliente.post("/artista/portfolio/" + item + "/remover")
    assert buscar("SELECT 1 AS x FROM portfolio WHERE id = %s", (item,)) is None


# ---------------------------------------------------------------
# Atualização do banco que já está no ar
# ---------------------------------------------------------------
def test_atualizacao_do_banco_pode_rodar_varias_vezes_sem_apagar_dados(cliente):
    iniciar_banco.aplicar_atualizacoes()
    iniciar_banco.aplicar_atualizacoes()
    assert buscar("SELECT COUNT(*) AS n FROM favoritos")["n"] == 2
    assert buscar("SELECT COUNT(*) AS n FROM profiles")["n"] == 7
