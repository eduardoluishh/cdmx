# Mapa apocalíptico de la Ciudad de México

*Un día a la vez.* Mapa pixel art del Valle de México con lo que reportan las autoridades: alertas de la SGIRPC, el semáforo del Popocatépetl (Cenapred), sismos (SSN-UNAM), calidad del aire (Sedema) y ciclones (NHC).

Publicado en https://cdmx.eduardoluis.blog

## Cómo se actualiza

- `.github/workflows/datos.yml` corre cada 30 minutos: ejecuta `scripts/actualizar.py`, que arma `data/alertas.json`, y vuelve a publicar el sitio en GitHub Pages.
- Las alertas de la SGIRPC solo se publican en X. Se copian a mano o con una tarea programada de Claude en `data/sgirpc.json` (claves del INEGI para las alcaldías). Al hacer push, el sitio se publica de nuevo.

Por [Eduardo Luis](https://eduardoluis.blog), programado con Claude.
