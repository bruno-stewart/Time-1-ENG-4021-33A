# Tabela de notificações

## Para que serve

Antes, o cliente só descobria que tinha recebido uma proposta se abrisse o painel e procurasse. O artista também não sabia quando um pagamento era confirmado ou um evento era cancelado. Esta tabela guarda os avisos de cada usuário, que aparecem no sino do topo da página com a quantidade de não lidos.

## Criação (schema_sprint7.sql)

```sql
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
```

## Colunas

| Coluna | Tipo | Regra |
|---|---|---|
| id | UUID | Chave primária gerada automaticamente |
| user_id | UUID | Quem recebe o aviso. Excluir a conta apaga os avisos |
| tipo | TEXT | Um dos 7 tipos da tabela abaixo. Define o ícone na tela |
| texto | TEXT | Frase curta, até 200 caracteres |
| link | TEXT | Página que abre ao clicar (sempre um caminho interno, começando com `/`) |
| lida | BOOLEAN | Começa `FALSE`; vira `TRUE` quando o usuário clica ou usa "marcar todas" |
| criada_em | TIMESTAMPTZ | Ordena do mais novo para o mais antigo |

## Quando cada tipo é criado

| Tipo | Quem recebe | Quando |
|---|---|---|
| proposta | Cliente | Um artista envia proposta ou contraproposta |
| proposta | Artista | O cliente recusa a proposta |
| contrato | Artista | O cliente aceita a proposta |
| pagamento | Artista | O cliente paga e o valor fica retido |
| cancelamento | A outra parte | Cliente ou artista cancela o contrato |
| mensagem | A outra parte | Chega mensagem nova na conversa do contrato |
| avaliacao | Artista | O cliente avalia o serviço |
| moderacao | Denunciante / artista | A denúncia é decidida, o perfil é suspenso ou reativado |

## Decisões de modelagem

- **Texto pronto em vez de montar na hora:** a frase é gravada como o usuário vai ler. Se o artista mudar de nome depois, o aviso antigo continua contando o que aconteceu naquele momento.
- **`CHECK` no tipo** em vez de `ENUM`: dá para criar um tipo novo no futuro com `ALTER TABLE`, sem recriar o tipo no banco que já está no ar.
- **Índice (`user_id`, `lida`, `criada_em`):** a consulta mais frequente roda em toda página ("quantos avisos não lidos o usuário tem?"), então precisa ser rápida.
- **Artista sem conta não recebe aviso:** artistas cadastrados só pela equipe (sem `user_id`) são ignorados pela função `notificar()`.
- **Link só interno:** a rota que abre o aviso só redireciona para caminhos que começam com `/`, para ninguém usar um aviso para mandar o usuário a outro site.

## Consultas usadas no sistema

```sql
-- número do sino (todas as páginas)
SELECT COUNT(*) FROM notificacoes WHERE user_id = :usuario AND lida = FALSE;

-- tela de notificações
SELECT * FROM notificacoes WHERE user_id = :usuario ORDER BY criada_em DESC LIMIT 50;
```
