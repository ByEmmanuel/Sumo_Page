# Mini Sumo Lab · Página pública

Sitio: **https://byemmanuel.github.io/Sumo_Page/**

Laboratorio de un robot mini-sumo de 96 × 96 mm y 460 g.
**MS-001 VERDE es mi robot; el ROJO es el rival.**

Esta publicación incluye versiones completas de los algoritmos, comparaciones,
bitácora y resultados de las simulaciones de Webots. El historial se puede
descargar como ZIP. Los registros conservan sus hashes SHA-256 originales.

## Publicación

GitHub Pages publica la raíz de la rama `gh-pages`. Los archivos funcionan en
la subruta `/Sumo_Page/` y no necesitan servidor Python ni dependencias.

La página pública es de consulta. Para editar algoritmos, registrar versiones o
ejecutar combates se utiliza el laboratorio local. No se guardan cambios desde
esta web ni se simula Webots dentro del navegador.

Los datos representan la fecha de la última exportación, visible al pie de cada
vista. Para actualizarlos desde la carpeta del laboratorio:

```sh
python3 tools/export_pages.py publication/Sumo_Page
git -C publication/Sumo_Page add .
git -C publication/Sumo_Page commit -m "Actualizar historial publicado"
git -C publication/Sumo_Page push origin HEAD:main HEAD:gh-pages
```

No se necesita forzar el push. La base SQLite permanece en el laboratorio local.
