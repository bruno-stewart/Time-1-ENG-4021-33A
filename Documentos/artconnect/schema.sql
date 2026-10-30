-- =====================================================
-- ArtConnect - Criação das tabelas (PostgreSQL)
-- Baseado no modelo físico do grupo, adaptado para
-- login próprio da aplicação (username + senha).
-- =====================================================

DROP VIEW  IF EXISTS vw_painel_cliente;
DROP VIEW  IF EXISTS vw_artistas;
DROP TABLE IF EXISTS portfolio, denuncias, cancelamentos, notificacoes, favoritos,
                     tokens_senha, disponibilidade, chamados_suporte,
                     mensagens, avaliacoes, pagamentos, contratos, propostas,
                     pedidos_orcamento, eventos, artistas, categorias,
                     profiles CASCADE;
DROP TYPE  IF EXISTS papel_usuario, tipo_evento, status_orcamento,
                     status_proposta, status_contrato, status_pagamento,
                     status_suporte, status_agenda CASCADE;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- TIPOS (ENUMs) ----------
CREATE TYPE papel_usuario    AS ENUM ('cliente', 'artista', 'admin');
CREATE TYPE tipo_evento      AS ENUM ('casamento', 'corporativo', 'aniversario', 'formatura', 'outro');
CREATE TYPE status_orcamento AS ENUM ('aberto', 'com_propostas', 'fechado', 'cancelado');
-- enviada/aceita/recusada: decisão do cliente; declinada: o artista recusou o pedido
CREATE TYPE status_proposta  AS ENUM ('enviada', 'aceita', 'recusada', 'declinada');
CREATE TYPE status_contrato  AS ENUM ('aguardando_pagamento', 'valor_retido', 'concluido', 'cancelado');
CREATE TYPE status_pagamento AS ENUM ('pendente', 'retido', 'liberado', 'reembolsado');
CREATE TYPE status_suporte   AS ENUM ('aberto', 'em_andamento', 'resolvido');
CREATE TYPE status_agenda    AS ENUM ('disponivel', 'ocupado');

-- ---------- USUÁRIOS ----------
CREATE TABLE profiles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username    TEXT UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    nome        TEXT NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    telefone    TEXT,
    cidade      TEXT,
    papel       papel_usuario NOT NULL DEFAULT 'cliente',
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- CATEGORIAS ----------
CREATE TABLE categorias (
    id          SERIAL PRIMARY KEY,
    nome        TEXT NOT NULL UNIQUE,
    slug        TEXT NOT NULL UNIQUE,
    descricao   TEXT
);

-- ---------- ARTISTAS ----------
CREATE TABLE artistas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID UNIQUE REFERENCES profiles(id) ON DELETE SET NULL,
    nome_artistico  TEXT NOT NULL,
    categoria_id    INT  NOT NULL REFERENCES categorias(id),
    estilo          TEXT,
    cidade          TEXT NOT NULL,
    preco_minimo    NUMERIC(10,2) NOT NULL CHECK (preco_minimo >= 0),
    descricao       TEXT,
    foto_url        TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_artistas_categoria_cidade ON artistas (categoria_id, cidade);

-- ---------- EVENTOS ----------
CREATE TABLE eventos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tipo            tipo_evento NOT NULL,
    categoria_id    INT  NOT NULL REFERENCES categorias(id),
    data_evento     DATE,
    localizacao     TEXT,
    orcamento       NUMERIC(10,2) CHECK (orcamento >= 0),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_eventos_cliente ON eventos (cliente_id);

-- ---------- PEDIDOS DE ORÇAMENTO ----------
CREATE TABLE pedidos_orcamento (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento_id             UUID NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
    categoria_id          INT  NOT NULL REFERENCES categorias(id),
    data_evento           DATE NOT NULL,
    horario_inicio        TIME NOT NULL,
    duracao_horas         NUMERIC(4,1) NOT NULL CHECK (duracao_horas > 0),
    estimativa_convidados INT NOT NULL CHECK (estimativa_convidados > 0),
    local                 TEXT NOT NULL,
    observacoes           TEXT CHECK (char_length(observacoes) <= 600),
    status                status_orcamento NOT NULL DEFAULT 'aberto',
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- PROPOSTAS ----------
CREATE TABLE propostas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id   UUID NOT NULL REFERENCES pedidos_orcamento(id) ON DELETE CASCADE,
    artista_id  UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    valor       NUMERIC(10,2) CHECK (valor >= 0),
    mensagem    TEXT,
    data_sugerida     DATE,          -- preenchida quando é contraproposta de data
    horario_sugerido  TIME,          -- preenchido quando é contraproposta de horário
    status      status_proposta NOT NULL DEFAULT 'enviada',
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pedido_id, artista_id),
    CHECK (status = 'declinada' OR valor IS NOT NULL)
);

-- ---------- CONTRATOS ----------
CREATE TABLE contratos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento_id     UUID NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
    proposta_id   UUID UNIQUE REFERENCES propostas(id),
    cliente_id    UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    artista_id    UUID NOT NULL REFERENCES artistas(id),
    descricao     TEXT,
    data_evento   DATE NOT NULL,
    local         TEXT NOT NULL,
    valor_total   NUMERIC(10,2) NOT NULL CHECK (valor_total >= 0),
    status        status_contrato NOT NULL DEFAULT 'aguardando_pagamento',
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_contratos_cliente ON contratos (cliente_id);
CREATE INDEX idx_contratos_artista ON contratos (artista_id);

-- ---------- PAGAMENTOS ----------
CREATE TABLE pagamentos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id     UUID NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    valor           NUMERIC(10,2) NOT NULL CHECK (valor > 0),
    metodo          TEXT,
    status          status_pagamento NOT NULL DEFAULT 'pendente',
    pago_em         TIMESTAMPTZ,
    liberado_em     TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- AVALIAÇÕES ----------
CREATE TABLE avaliacoes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id   UUID NOT NULL UNIQUE REFERENCES contratos(id) ON DELETE CASCADE,
    artista_id    UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    cliente_id    UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nota          SMALLINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario    TEXT,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- MENSAGENS ----------
CREATE TABLE mensagens (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id      UUID REFERENCES contratos(id) ON DELETE CASCADE,
    remetente_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    destinatario_id  UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    conteudo         TEXT NOT NULL,
    lida             BOOLEAN NOT NULL DEFAULT FALSE,
    enviada_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_mensagens_destinatario ON mensagens (destinatario_id, lida);

-- ---------- SUPORTE ----------
CREATE TABLE chamados_suporte (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    assunto     TEXT NOT NULL,
    descricao   TEXT NOT NULL,
    status      status_suporte NOT NULL DEFAULT 'aberto',
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- AGENDA DO ARTISTA ----------
CREATE TABLE disponibilidade (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artista_id  UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    data        DATE NOT NULL,
    status      status_agenda NOT NULL DEFAULT 'ocupado',
    observacao  TEXT CHECK (char_length(observacao) <= 120),
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (artista_id, data)
);
CREATE INDEX idx_disponibilidade_data ON disponibilidade (data, status);

-- ---------- RECUPERAÇÃO DE SENHA ----------
-- Guarda só o hash do token; o token em si vai apenas no link enviado por e-mail
CREATE TABLE tokens_senha (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    expira_em   TIMESTAMPTZ NOT NULL,
    usado       BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================
-- VIEWS
-- =====================================================
CREATE VIEW vw_artistas AS
SELECT a.*,
       c.nome AS categoria,
       ROUND(AVG(av.nota), 1) AS nota_media,
       COUNT(av.id)           AS total_avaliacoes
FROM artistas a
JOIN categorias c ON c.id = a.categoria_id
LEFT JOIN avaliacoes av ON av.artista_id = a.id
GROUP BY a.id, c.nome;

CREATE VIEW vw_painel_cliente AS
SELECT
    p.id AS cliente_id,
    (SELECT COUNT(*) FROM contratos c
      WHERE c.cliente_id = p.id AND c.data_evento >= CURRENT_DATE
        AND c.status IN ('aguardando_pagamento', 'valor_retido'))   AS proximos_eventos,
    (SELECT COALESCE(SUM(pg.valor), 0) FROM pagamentos pg
      JOIN contratos c ON c.id = pg.contrato_id
      WHERE c.cliente_id = p.id AND pg.status = 'retido')            AS valor_retido,
    (SELECT COALESCE(SUM(c.valor_total), 0) FROM contratos c
      WHERE c.cliente_id = p.id AND c.status <> 'cancelado')         AS total_contratado,
    (SELECT COUNT(*) FROM mensagens m
      WHERE m.destinatario_id = p.id AND m.lida = FALSE)             AS mensagens_novas
FROM profiles p;
