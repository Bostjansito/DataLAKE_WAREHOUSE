-- Ejecutar cada sentencia por separado en Athena. Todos los resultados deben
-- estar vacíos. Un COUNT DISTINCT de una concatenación no es seguro: usar tuplas
-- reales en GROUP BY para no colisionar claves que contienen separadores.
SELECT news_id, COUNT(*) AS filas
FROM news
GROUP BY news_id
HAVING COUNT(*) <> 1;

SELECT news_id, entity, entity_type, COUNT(*) AS filas
FROM news_entities
GROUP BY news_id, entity, entity_type
HAVING COUNT(*) <> 1;

SELECT news_id, phrase, COUNT(*) AS filas
FROM news_key_phrases
GROUP BY news_id, phrase
HAVING COUNT(*) <> 1;

SELECT 'news_entities' AS tabla, e.news_id
FROM news_entities e
LEFT JOIN news n ON n.news_id = e.news_id
WHERE n.news_id IS NULL
UNION ALL
SELECT 'news_key_phrases', p.news_id
FROM news_key_phrases p
LEFT JOIN news n ON n.news_id = p.news_id
WHERE n.news_id IS NULL;

-- La fecha de la fila hija debe coincidir con la noticia vigente.
SELECT 'news_entities' AS tabla, e.news_id, e.publication_date
FROM news_entities e
JOIN news n ON n.news_id = e.news_id
WHERE e.publication_date IS DISTINCT FROM n.publication_date
UNION ALL
SELECT 'news_key_phrases', p.news_id, p.publication_date
FROM news_key_phrases p
JOIN news n ON n.news_id = p.news_id
WHERE p.publication_date IS DISTINCT FROM n.publication_date;
