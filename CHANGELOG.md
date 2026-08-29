# Historial de cambios

Todos los cambios relevantes del proyecto se documentan en este archivo.

## Próxima versión

### Cambiado

- La aplicación y la extensión pasan a llamarse **Photo Swipper Filter**.
- Al conservar o descartar en Google Photos, la extensión avanza a la siguiente
  foto —normalmente más antigua en la biblioteca principal— y reconoce más
  variantes del control de navegación.
- Las pulsaciones cortas de `→` ya no se pierden durante una transición, y
  mantener la tecla activa un avance rápido controlado que conserva cada foto.
- El acceso a Google Photos queda visible en la parte superior de la aplicación.
- La revisión local adopta una interfaz más simple, con exploración de carpetas
  destacada, visor multimedia grande y centrado, y botones con texto claro.
- El visor cambia automáticamente de forma para aprovechar mejor la pantalla
  con fotos y videos verticales, horizontales o cuadrados, sin recortarlos.
- Se pueden crear y guardar carpetas de organización dentro de la biblioteca.
  La flecha `↑` mueve a la carpeta activa y `↓` deshace la decisión anterior.
- Las carpetas de organización se excluyen del escaneo para que los archivos ya
  ordenados no vuelvan a la cola.
- La extensión 0.5.0 usa Papelera como destino predeterminado y agrega `↓` para
  deshacer la última eliminación únicamente mediante el aviso nativo y visible
  de Google Photos. Conservar también puede volver a la foto anterior.
- La extensión 0.6.0 recuerda localmente la última foto que quedó sin decidir y
  la retoma al volver a la biblioteca principal, sin desviar búsquedas, álbumes
  ni la Papelera.
- El registro local de una eliminación ya no bloquea el avance a la foto
  siguiente, manteniendo ágil la revisión.
- La carpeta para nuevos descartes pasa a llamarse
  `_Photo_Swipper_Filter_Para_Eliminar`.
- Se conserva compatibilidad con descartes, sesión y perfil de navegador de la
  versión anterior.

### Seguridad

- Se excluyen explícitamente credenciales, claves de firma, paquetes de
  extensión, bases locales, registros y perfiles del navegador.

### Documentación

- Se agregan guías de arquitectura, seguridad, contribución y evolución futura.
