# Fuentes RSS

Las tres secciones seleccionadas del [directorio oficial RSS de El Tiempo](https://www.eltiempo.com/rss) son:

| Medio | Sección | URL de feed | Idioma |
|---|---|---|---|
| El Tiempo | Política | `https://www.eltiempo.com/rss/politica.xml` | `es` |
| El Tiempo | Economía | `https://www.eltiempo.com/rss/economia.xml` | `es` |
| El Tiempo | Deportes | `https://www.eltiempo.com/rss/deportes.xml` | `es` |

La configuración versionada y consumida por el pipeline es `config/feeds.json`; la página oficial es un directorio y no se debe usar como endpoint de cada sección. Se utilizan únicamente los campos disponibles en RSS y no se descarga el artículo enlazado. Los feeds pueden cambiar y su disponibilidad debe comprobarse durante la ejecución.

## Campos y procedencia

El parser extrae GUID/identificador si está disponible, título, enlace, descripción y fecha de publicación. Para cada extracción se registra fuente, URL, hora UTC, código HTTP, hash de bytes y ubicación Bronze. Una respuesta HTTP exitosa con feed XML válido pero sin items se registra como fuente exitosa con cero noticias; un cuerpo vacío recibe `empty`, y fallas de red, HTTP o XML tienen estados `network_error`, `http_error` o `invalid_xml`. Cada fuente mantiene su estado; el lote completo se marca `complete`, `partial` o `failed` según cuántas fuentes sean válidas. Una falla no se interpreta como éxito vacío.

## Revisión de cambios

Si se actualizan endpoints o secciones, actualice `config/feeds.json` y esta tabla en el mismo cambio. La verificación manual del endpoint puede abrirlo en navegador o usar la ruta de ingesta; no convierta una falla temporal en eliminación silenciosa de la fuente. El directorio oficial sirve para confirmar rutas vigentes.
