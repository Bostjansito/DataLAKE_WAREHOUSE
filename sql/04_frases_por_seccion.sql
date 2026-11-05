-- Gold mide noticias distintas por frase y sección, no cantidad de menciones.
WITH frecuencias AS (
    SELECT section, phrase, SUM(news_count) AS noticias_distintas
    FROM section_phrases
    WHERE publication_date BETWEEN '2026-10-20' AND '2026-10-22'
    GROUP BY section, phrase
), ranking AS (
    SELECT section, phrase, noticias_distintas,
           ROW_NUMBER() OVER (
               PARTITION BY section ORDER BY noticias_distintas DESC, phrase
           ) AS posicion
    FROM frecuencias
)
SELECT section, posicion, phrase, noticias_distintas
FROM ranking
WHERE posicion <= 10
ORDER BY section, posicion;
