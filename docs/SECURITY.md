# Seguridad y privacidad

## Datos que nunca deben publicarse

- `.env` y cualquier variante con valores reales.
- ID y secreto OAuth de Google, tokens de acceso o renovación y cookies.
- Claves privadas de firma (`.pem`, `.key`, `.p12`, `.pfx`) y paquetes `.crx`.
- `mvp.sqlite3`, otras bases locales, logs y perfiles del navegador.
- Fotos, videos, audios, rutas personales o exportaciones de decisiones.

`.gitignore` bloquea estas categorías, pero sigue siendo obligatorio revisar el
contenido preparado antes de cada publicación.

## Manejo de credenciales

- `.env.example` solo documenta nombres de variables; no debe contener valores
  reales.
- La sesión OAuth se guarda mediante el Administrador de credenciales de
  Windows, no en Git ni en el navegador de la aplicación.
- `FLASK_SECRET_KEY` puede configurarse localmente. Si está vacía, cada ejecución
  genera una clave temporal.
- La clave privada usada para empaquetar la extensión es local y no forma parte
  del código fuente.

## Lista previa a una publicación

1. Revisar `git status --short`.
2. Revisar `git diff --cached --name-only`.
3. Confirmar que no se prepararon `.env`, bases, logs, claves, `.crx` ni medios.
4. Buscar patrones de secretos en lo preparado sin imprimir valores sensibles.
5. Ejecutar las pruebas y `git diff --check`.

Si una credencial llegó a un commit o a GitHub, eliminar el archivo no alcanza:
hay que revocar y reemplazar la credencial inmediatamente y luego limpiar el
historial correspondiente.
