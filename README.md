# Photo Swipper Filter

Organizador multimedia local para revisar fotos, videos y audios con gestos o
flechas, como una aplicación de *swipe*. La prioridad es que la limpieza sea
rápida, privada y reversible.

## Funciones principales

- Selección nativa de una carpeta de Windows y escaneo de todas sus subcarpetas.
- Vista previa de imágenes, videos y audios sin subir los archivos a internet.
- Interfaz de lectura sencilla, con el contenido grande y centrado y acciones
  explicadas en pantalla.
- Visor adaptable a la orientación vertical, horizontal o cuadrada de cada
  foto y video, siempre mostrando el contenido completo.
- Flecha izquierda para eliminar, derecha para conservar, arriba para ordenar
  en la carpeta activa y abajo para deshacer la última decisión.
- Creación de carpetas de organización desde la aplicación, con una carpeta
  activa que queda guardada y puede cambiarse en cualquier momento.
- Movimiento reversible a `_Photo_Swipper_Filter_Para_Eliminar`, conservando la
  estructura original de subcarpetas.
- Historial y progreso guardados localmente en SQLite.
- Precarga de las siguientes imágenes para reducir la espera.
- Extensión opcional para revisar elementos abiertos directamente en Google
  Photos y agregarlos a `Fotos a eliminar` o enviarlos a la Papelera.
- Acceso visible a Google Photos desde la parte superior de la aplicación.
- Inicio oculto en Windows, apertura automática del navegador y actualización
  segura desde GitHub cuando la rama local no tiene cambios.

## Inicio rápido en Windows

1. Ejecutá `iniciar_mvp.bat`.
2. Esperá a que se abra Microsoft Edge en `http://127.0.0.1:8765`.
3. Elegí la carpeta principal que querés ordenar.
4. Creá o seleccioná la carpeta que querés usar para ordenar con `↑`.
5. Revisá los archivos con las flechas:

| Tecla | Acción |
| --- | --- |
| `←` | Mover a la carpeta para eliminar |
| `→` | Conservar en su ubicación |
| `↑` | Mover a la carpeta de organización activa |
| `↓` | Deshacer y volver al archivo anterior |

Nada se elimina definitivamente. Antes del borrado final, revisá la carpeta
`_Photo_Swipper_Filter_Para_Eliminar`.

La carpeta mostrada como **activa para la flecha ↑** continúa seleccionada
hasta que elijas o crees otra. Las carpetas creadas por la aplicación quedan
dentro de la biblioteca principal y no se vuelven a incluir en el escaneo.

Para crear o actualizar el acceso directo del Escritorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

## Instalación manual

Requiere Python 3.10 o posterior.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mvp.txt
.\.venv\Scripts\python.exe mvp_app.py
```

La aplicación queda disponible en `http://127.0.0.1:8765`.

## Google Photos (opcional)

La organización de carpetas locales no necesita una cuenta de Google. Para usar
el Picker oficial:

1. Creá un proyecto en [Google Cloud Console](https://console.cloud.google.com/).
2. Habilitá Google Photos Picker API.
3. Creá un cliente OAuth de tipo **Aplicación web**.
4. Registrá `http://127.0.0.1:8765/auth/google/callback` como URI de redirección.
5. Copiá `.env.example` como `.env` y completá las credenciales solo en ese
   archivo local.

La sesión se guarda en el Administrador de credenciales de Windows. `.env`, los
tokens, las bases locales, los perfiles del navegador y las claves de firma de
la extensión están excluidos de Git.

La API oficial de Google Photos no permite eliminar elementos existentes ni
agregarlos libremente a un álbum. Por eso el Picker es de lectura y la extensión
actúa únicamente sobre la interfaz visible de Google Photos. Las decisiones del
Picker no deben interpretarse como cambios aplicados a un álbum real.

### Extensión de Edge

El iniciador carga automáticamente la carpeta `extension` en un perfil dedicado
de Edge. Si necesitás cargarla manualmente:

1. Abrí `edge://extensions`.
2. Activá **Modo para desarrolladores**.
3. Elegí **Cargar extensión sin empaquetar**.
4. Seleccioná la carpeta `extension` de este repositorio.

La extensión usa las flechas izquierda y derecha dentro de una foto o video
abierto. Después de conservar o descartar, avanza a la siguiente foto; en la
biblioteca principal normalmente será una más antigua. En álbumes y búsquedas
respeta el orden de ese contexto. Google puede cambiar su interfaz; si una
operación no recibe una confirmación visible, se registra como fallida y no como
completada.

Una pulsación corta de `→` conserva y garantiza un avance. Si se mantiene
presionada, se activa el avance rápido y cada foto recorrida se registra como
conservada. La flecha izquierda no se repite automáticamente porque puede
producir cambios reales en un álbum o en la Papelera.

## Estructura del proyecto

```text
extension/                  Extensión local para Google Photos
scripts/                    Inicio automático y acceso directo de Windows
src/local_media.py          Escaneo, movimientos y restauración de archivos
src/mvp_store.py            Persistencia local en SQLite
src/google_photos_picker.py Integración opcional con Google Photos Picker
src/token_vault.py          Sesión OAuth en el almacén seguro de Windows
tests/                      Pruebas automatizadas
web/                        Interfaz local
mvp_app.py                  Servidor y API local
```

El clasificador con IA original continúa en `main.py` y `src/`, pero el flujo
principal del producto es ahora la revisión manual, local y reversible.

## Desarrollo y mantenimiento

- [Guía para contribuir](CONTRIBUTING.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Seguridad y privacidad](docs/SECURITY.md)
- [Hoja de ruta](docs/ROADMAP.md)
- [Historial de cambios](CHANGELOG.md)
- [Instrucciones para asistentes de código](AGENTS.md)

Ejecutar las pruebas:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web\app.js
node --check extension\content.js
node --check extension\background.js
```

## Privacidad

Los archivos seleccionados permanecen en el equipo. No publiques `.env`, bases
SQLite, registros, claves privadas, paquetes firmados de la extensión, perfiles
del navegador ni bibliotecas personales. Consultá `docs/SECURITY.md` antes de
crear un commit.

## Licencia

MIT. Ver [LICENSE](LICENSE).
