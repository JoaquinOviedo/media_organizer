# Arquitectura

## Vista general

Photo Swipper Filter es una aplicación local con cuatro partes:

1. `mvp_app.py` expone la página y una API HTTP limitada a `127.0.0.1`.
2. `web/` presenta la tarjeta actual, reproduce medios y envía decisiones.
3. `src/` valida rutas, mueve archivos y persiste el progreso.
4. `extension/` asiste sobre una pestaña visible de Google Photos.

## Flujo local

```text
Selector nativo de Windows
          |
          v
Escaneo recursivo y validación de rutas
          |
          v
SQLite local <-> API local <-> Interfaz web
          |
          v
Mover/restaurar dentro de la biblioteca elegida
```

La interfaz nunca recibe permiso general sobre el sistema de archivos. El
servidor selecciona y valida la carpeta, y cada operación comprueba que origen y
destino sigan dentro de ella.

## Decisiones

- `pending`: todavía no revisado.
- `keep`: permanece en su ubicación.
- `delete`: se mueve a la carpeta para eliminar, sin borrado definitivo.
- `organize`: se mueve a la carpeta de organización activa.
- `print`: crea una copia en `A imprimir` y se persiste como `keep`, porque el
  original se conserva en su ubicación.

Las carpetas de organización son subcarpetas directas de la biblioteca. La
selección activa se persiste por biblioteca y esos destinos se excluyen del
escaneo recursivo para evitar reimportar archivos ya ordenados. Tanto `delete`
como `organize` conservan la ruta relativa original para que la siguiente
operación de deshacer pueda restaurar el archivo.

`A imprimir` es una carpeta administrada y excluida del escaneo. La base guarda
solo la ruta relativa exacta de la copia creada, de modo que deshacer pueda
quitar esa copia sin tocar el original ni otros archivos de la carpeta.

SQLite almacena rutas, metadatos y decisiones. Los archivos multimedia no se
copian a la base ni se envían a un servidor remoto.

## Google Photos

El Picker oficial autentica y permite leer elementos elegidos por el usuario.
La extensión es un componente separado que opera sobre controles visibles de
Google Photos y reporta el resultado al servidor local. No existe una
sincronización automática y segura entre una decisión del Picker y un elemento
abierto después en Google Photos.

La posición de revisión se conserva únicamente en el almacenamiento local de
la extensión como identificador y URL de la foto abierta. Una operación
confirmada elimina ese punto; al mostrarse la foto siguiente se crea el nuevo.
La reanudación automática solo se aplica al entrar a la biblioteca principal y
valida que la URL guardada pertenezca a `photos.google.com`.

## Compatibilidad histórica

Los identificadores internos `swipeclean:*`, el servicio seguro
`SwipeClean.GooglePhotos`, el perfil dedicado de Edge y la exclusión de
`_SwipeClean_Para_Eliminar` se mantienen para no romper instalaciones previas.
No son la marca visible del producto.
