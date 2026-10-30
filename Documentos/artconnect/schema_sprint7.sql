-- =====================================================
-- ArtConnect - Tabelas da Sprint 7
-- Pode rodar várias vezes: só cria o que ainda não existe.
-- Roda junto com o popular_banco.py e também no iniciar_banco.py,
-- para atualizar o banco que já está no ar sem apagar dados.
-- =====================================================

-- ---------- FAVORITOS ----------
-- Um cliente salva os artistas de que gostou para contratar depois.
CREATE TABLE IF NOT EXISTS favoritos (
    cliente_id  UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    artista_id  UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cliente_id, artista_id)
);
CREATE INDEX IF NOT EXISTS idx_favoritos_artista ON favoritos (artista_id);

-- ---------- NOTIFICAÇÕES ----------
-- Avisos que aparecem no sino do topo da página.
CREATE TABLE IF NOT EXISTS notificacoes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL CHECK (tipo IN ('proposta', 'contrato', 'pagamento', 'cancelamento',
                                              'mensagem', 'avaliacao', 'moderacao')),
    texto       TEXT NOT NULL CHECK (char_length(texto) <= 200),
    link        TEXT,
    lida        BOOLEAN NOT NULL DEFAULT FALSE,
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notificacoes_usuario ON notificacoes (user_id, lida, criada_em DESC);

-- ---------- CANCELAMENTOS ----------
-- Registro de cada cancelamento e do cálculo do reembolso pela política.
CREATE TABLE IF NOT EXISTS cancelamentos (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_id           UUID NOT NULL UNIQUE REFERENCES contratos(id) ON DELETE CASCADE,
    cancelado_por         TEXT NOT NULL CHECK (cancelado_por IN ('cliente', 'artista')),
    motivo                TEXT NOT NULL CHECK (char_length(motivo) BETWEEN 5 AND 300),
    dias_antecedencia     INT  NOT NULL,
    percentual_reembolso  INT  NOT NULL CHECK (percentual_reembolso BETWEEN 0 AND 100),
    valor_reembolso       NUMERIC(10,2) NOT NULL DEFAULT 0,
    valor_artista         NUMERIC(10,2) NOT NULL DEFAULT 0,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- DENÚNCIAS ----------
-- Denúncia de um perfil de artista OU de uma avaliação (nunca os dois).
CREATE TABLE IF NOT EXISTS denuncias (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    denunciante_id  UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    artista_id      UUID REFERENCES artistas(id) ON DELETE CASCADE,
    avaliacao_id    UUID REFERENCES avaliacoes(id) ON DELETE CASCADE,
    motivo          TEXT NOT NULL CHECK (motivo IN ('ofensivo', 'falso', 'spam', 'golpe', 'outro')),
    detalhes        TEXT CHECK (char_length(detalhes) <= 500),
    status          TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'procedente', 'improcedente')),
    decisao         TEXT CHECK (char_length(decisao) <= 300),
    criada_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolvida_em    TIMESTAMPTZ,
    CHECK ((artista_id IS NULL) <> (avaliacao_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_denuncias_status ON denuncias (status, criada_em);
-- a mesma pessoa não denuncia o mesmo conteúdo duas vezes enquanto a denúncia está aberta
CREATE UNIQUE INDEX IF NOT EXISTS idx_denuncias_unica_artista
    ON denuncias (denunciante_id, artista_id) WHERE status = 'aberta' AND artista_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_denuncias_unica_avaliacao
    ON denuncias (denunciante_id, avaliacao_id) WHERE status = 'aberta' AND avaliacao_id IS NOT NULL;

-- avaliação escondida pela moderação deixa de aparecer e de contar na nota
ALTER TABLE avaliacoes ADD COLUMN IF NOT EXISTS oculta BOOLEAN NOT NULL DEFAULT FALSE;

-- ---------- PORTFÓLIO ----------
-- Links de fotos, vídeos e áudios do trabalho do artista.
CREATE TABLE IF NOT EXISTS portfolio (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artista_id  UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL CHECK (tipo IN ('foto', 'video', 'audio')),
    titulo      TEXT NOT NULL CHECK (char_length(titulo) BETWEEN 3 AND 80),
    -- link externo (https) ou imagem da própria plataforma (/static/...)
    url         TEXT NOT NULL CHECK ((url LIKE 'https://%' OR url LIKE '/static/%') AND char_length(url) <= 500),
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_portfolio_artista ON portfolio (artista_id, criado_em);

-- ---------- VIEW DOS ARTISTAS ----------
-- Mesma view de antes, mas sem contar avaliações ocultas pela moderação.
CREATE OR REPLACE VIEW vw_artistas AS
SELECT a.*,
       c.nome AS categoria,
       ROUND(AVG(av.nota), 1) AS nota_media,
       COUNT(av.id)           AS total_avaliacoes
FROM artistas a
JOIN categorias c ON c.id = a.categoria_id
LEFT JOIN avaliacoes av ON av.artista_id = a.id AND av.oculta = FALSE
GROUP BY a.id, c.nome;
