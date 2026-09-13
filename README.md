# Mini Sumo Lab · Gelatina Nuclear

**[Abrir la web](https://byemmanuel.github.io/Sumo_Page/#simulation)** · [Informe completo](INFORME_WEBOTS_REAL.md) · [Descargar proyecto y evidencias](https://byemmanuel.github.io/Sumo_Page/laboratorio-completo.zip)

Estado al 13 de septiembre de 2026: **22 revisiones, física v0022,3600 asaltos**. El robot es un diseño nominal de495g, ruedas42mm y batería2S; todavía no hay medidas físicas. La ficha de460g corresponde al modelo inicial y está identificada aparte.

## Qué puedes revisar desde otra PC

- Web de consulta con historial, archivos C/HAL, diferencias, resultados y curvas.
- [Informe](INFORME_WEBOTS_REAL.md), [resumen del avance](REVISION_DEL_AVANCE.md) y [protocolo de medidas físicas](PROTOCOLO_MEDIDAS_REALES.md).
- [Calibración cada8ms](https://byemmanuel.github.io/Sumo_Page/calibracion_webots.json), con condiciones, muestras válidas y pruebas fallidas.
- [Proyecto Webots](Mini-Sumo-real/), [evaluación final](Mini-Sumo-real/runs/evaluacion_final.json) y [registros](Mini-Sumo-real/runs/).
- [Historial original sin SQLite](mini-sumo-historial.zip), que conserva los hashes de todas las revisiones.
- [ZIP completo del laboratorio](https://byemmanuel.github.io/Sumo_Page/laboratorio-completo.zip): fuentes del servidor, web, herramientas, proyecto, instantáneas y evidencias de pruebas. Para consultar basta la web; ejecutar simulaciones requiere WebotsR2025a y un entorno local.

No hay que ejecutar entrenamientos ni simulaciones para revisar estos resultados. Las estrategias históricas no se ajustaron para ganar en el modelo. La equivalencia neuronal con realimentación independiente sigue abierta y algunas calibraciones aleatorias quedaron censuradas por caída; el informe lo distingue de las comprobaciones aprobadas.

## Contenido de esta publicación

Se excluyen SQLite, credenciales, cachés, objetos y ejecutables compilados. Las rutas del equipo se retiran de las copias de registros. [MANIFIESTO_PUBLICACION.json](MANIFIESTO_PUBLICACION.json) conserva hashes originales y públicos e identifica cada archivo saneado. Los hashes de algoritmos registrados no cambian al publicar.

GitHub Pages sirve la raíz de `gh-pages`, bajo `/Sumo_Page/`. La web pública es de consulta. El mismo commit se publica en `main` y `gh-pages`; no se simula persistencia de edición en el navegador.
