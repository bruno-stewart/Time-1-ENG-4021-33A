# Tabela de favoritos dos clientes

## Para que serve

Quem organiza um evento costuma pesquisar artistas com semanas de antecedência e comparar opções antes de pedir orçamento. Sem favoritos, o cliente precisa refazer a busca toda vez. Esta tabela guarda os artistas que o cliente salvou para contratar depois, e também mostra quais artistas são mais desejados, um dado útil para o dashboard.

## Criação (schema_sprint7.sql)

```sql
CREATE TABLE IF NOT EXISTS favoritos (
    cliente_id  UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    artista_id  UUID NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cliente_id, artista_id)
);
CREATE INDEX IF NOT EXISTS idx_favoritos_artista ON favoritos (artista_id);
```

## Colunas

| Coluna | Tipo | Regra |
|---|---|---|
| cliente_id | UUID | Quem salvou. Se a conta for excluída, os favoritos dela vão junto |
| artista_id | UUID | Artista salvo. Se o artista for apagado, sai dos favoritos de todo mundo |
| criado_em | TIMESTAMPTZ | Quando foi salvo, usado para ordenar a lista do mais recente para o mais antigo |

## Decisões de modelagem

- **Chave primária composta** (`cliente_id`, `artista_id`): o mesmo cliente não salva o mesmo artista duas vezes, então não precisa de uma coluna `id` separada.
- **Tabela de ligação (N para N):** um cliente salva vários artistas, e um artista é salvo por vários clientes.
- **Índice por artista:** a chave primária já deixa rápida a busca "favoritos do cliente X". O índice extra deixa rápida a pergunta contrária, "quantos clientes salvaram o artista Y?".
- **`ON DELETE CASCADE` dos dois lados:** apagar uma conta não deixa linha órfã.
- **Artista suspenso some da lista** sem apagar a linha: a consulta filtra `ativo = TRUE`. Se ele for reativado, volta aos favoritos de quem tinha salvo.

## Dados de exemplo (popular_banco.py)

| Cliente | Artista salvo |
|---|---|
| luiz | Clara Veloso |
| luiz | Chef Raiz |

## Consultas usadas no sistema

```sql
-- lista do painel do cliente
SELECT a.*, f.criado_em AS salvo_em
FROM favoritos f JOIN vw_artistas a ON a.id = f.artista_id
WHERE f.cliente_id = :cliente AND a.ativo = TRUE
ORDER BY f.criado_em DESC;

-- o botão do perfil mostra "Salvo" ou "Salvar"
SELECT 1 FROM favoritos WHERE cliente_id = :cliente AND artista_id = :artista;
```
