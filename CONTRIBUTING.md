# Contribuir

## Preparación

1. Creá un entorno virtual de Python.
2. Instalá `requirements-mvp.txt`.
3. Copiá `.env.example` a `.env` únicamente si vas a probar Google Photos.
4. Ejecutá `mvp_app.py` y abrí `http://127.0.0.1:8765`.

## Criterios para un cambio

- Mantener la revisión local como flujo principal.
- No introducir borrado permanente de archivos.
- Agregar o actualizar pruebas cuando cambie el comportamiento.
- Mantener los nombres heredados documentados en `AGENTS.md` mientras no exista
  una migración segura.
- Actualizar `CHANGELOG.md` para cambios visibles.
- No incluir credenciales ni datos personales.

## Antes de crear un commit

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web\app.js
node --check extension\content.js
node --check extension\background.js
git diff --check
git status --short
```

Revisá también `docs/SECURITY.md` y confirmá que el commit no contenga archivos
locales o secretos.
