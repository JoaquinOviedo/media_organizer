# Guía de trabajo para Photo Swipper Filter

Estas reglas ayudan a mantener las decisiones importantes del producto en
futuras modificaciones, tanto manuales como asistidas por IA.

## Invariantes del producto

- El flujo principal es local: elegir una carpeta, escanear recursivamente y
  revisar imágenes, videos y audios.
- La flecha izquierda mueve de forma reversible; nunca debe borrar
  definitivamente un archivo.
- Hay que preservar la estructura relativa de subcarpetas al mover y restaurar.
- La interfaz y la API deben validar que toda ruta permanezca dentro de la
  biblioteca elegida.
- Google Photos es opcional y secundario. No afirmar que una decisión del Picker
  modificó un álbum o la Papelera.
- Una operación de la extensión solo cuenta como correcta cuando Google Photos
  muestra una confirmación verificable.

## Compatibilidad

- `_SwipeClean_Para_Eliminar` es el nombre heredado de la carpeta de descartes:
  debe seguir excluido del escaneo para no reimportar archivos antiguos.
- `SwipeClean.GooglePhotos` es el identificador heredado del Administrador de
  credenciales de Windows. No cambiarlo sin implementar una migración.
- Los mensajes internos `swipeclean:*`, los identificadores CSS de la extensión
  y los nombres de los lanzadores pueden mantenerse como protocolo interno.
- El perfil histórico de Edge debe conservarse para no cerrar la sesión del
  usuario después de una actualización de marca.

## Seguridad

- No leer, imprimir, versionar ni copiar el contenido de `.env` o de una clave
  privada.
- No agregar tokens OAuth, secretos de cliente, cookies, bases SQLite, logs,
  perfiles del navegador, paquetes `.crx`, archivos `.pem` ni medios personales.
- Usar `.env.example` únicamente con valores vacíos o ficticios.
- Antes de publicar, revisar los archivos preparados para commit y ejecutar una
  búsqueda de patrones de secretos sin mostrar los valores encontrados.

## Validación mínima

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web\app.js
node --check extension\content.js
node --check extension\background.js
```

Si se cambia el iniciador, comprobar tanto `/` como `/api/status`. Un puerto
abierto por sí solo no demuestra que la aplicación esté lista.
