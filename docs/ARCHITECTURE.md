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
- `later`: se oculta temporalmente de la ronda principal.
- `delete`: se mueve a la carpeta para eliminar, sin borrado definitivo.

SQLite almacena rutas, metadatos y decisiones. Los archivos multimedia no se
copian a la base ni se envían a un servidor remoto.

## Google Photos

El Picker oficial autentica y permite leer elementos elegidos por el usuario.
La extensión es un componente separado que opera sobre controles visibles de
Google Photos y reporta el resultado al servidor local. No existe una
sincronización automática y segura entre una decisión del Picker y un elemento
abierto después en Google Photos.

## Compatibilidad histórica

Los identificadores internos `swipeclean:*`, el servicio seguro
`SwipeClean.GooglePhotos`, el perfil dedicado de Edge y la exclusión de
`_SwipeClean_Para_Eliminar` se mantienen para no romper instalaciones previas.
No son la marca visible del producto.
