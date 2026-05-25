# 📷 Filtrador de Fotos

Un organizador inteligente de fotos y videos que usa **IA (CLIP + MediaPipe)** para clasificar automáticamente tu biblioteca multimedia en "importantes" y "no importantes", sin necesidad de revisión manual.

---

## ¿Qué hace?

Analiza una carpeta con fotos y videos (incluyendo subcarpetas) y los copia organizados a dos destinos:

- **`importantes/`** → fotos con personas, momentos familiares, selfies, paisajes y mascotas.
- **`no_importantes/`** → capturas de pantalla, documentos, imágenes borrosas/oscuras y duplicados/ráfagas.

Genera además un reporte CSV (`reporte_clasificacion.csv`) con el score, categoría y motivo de clasificación de cada archivo.

---

## ¿Cómo funciona?

El proceso corre en **4 fases secuenciales**:

```
Fase 1 → I/O + Calidad (paralelo, CPU)
Fase 2 → Análisis Semántico con IA (secuencial, GPU/CPU)
Fase 3 → Agrupación temporal + Detección de duplicados
Fase 4 → Scoring + Copia de archivos + Reporte CSV
```

### Fase 1 — I/O y Calidad
Lee cada archivo, extrae su fecha de creación (EXIF o metadatos del sistema), y analiza métricas de calidad técnica:
- **Blur** → varianza del Laplaciano sobre la imagen en escala de grises.
- **Oscuridad** → proporción de píxeles con valor < 30 (sobre 255).
- **Sobreexposición** → proporción de píxeles con valor > 225.

Esta fase corre en paralelo con `ThreadPoolExecutor`.

### Fase 2 — Análisis Semántico (IA)
Usa el modelo **CLIP (`openai/clip-vit-base-patch32`)** para clasificar el contenido de la imagen mediante *zero-shot classification* contra un conjunto de etiquetas predefinidas:

| Etiqueta CLIP | Clave interna |
|---|---|
| family gathering or celebration | `is_family_moment` |
| group of people together smiling | `is_family_moment` (sumada) |
| beautiful landscape or nature | `is_landscape` |
| screenshot of a phone or computer screen | `is_screenshot` |
| pet or animal | `is_pet` |
| food or meal | `is_food` |
| document, text, or paper | `is_document` |
| selfie or close-up portrait | `is_selfie` |
| **a photo with a person in it** | `has_a_person` |

Adicionalmente, usa **MediaPipe Face Detection** para contar rostros humanos con precisión (`num_faces`).

Para videos, se extraen N frames equiespaciados (configurables) y se promedian los scores semánticos.

### Fase 3 — Similitud y Duplicados
Agrupa los archivos en ventanas temporales (configurable, en minutos). Dentro de cada grupo, compara los embeddings CLIP con **similitud del coseno**. Si dos imágenes superan el umbral de similitud, se forma un clúster y se elige el "ganador" por:
1. Mayor cantidad de rostros detectados
2. Mayor probabilidad de momento familiar
3. Mayor probabilidad de selfie
4. Mayor probabilidad de paisaje
5. Mayor nitidez y menor oscuridad

Los "perdedores" del clúster son marcados como duplicados y reciben una penalización de -20 en el score.

### Fase 4 — Scoring y Organización
Cada archivo recibe un **score numérico** basado en los pesos configurados en `config.json`. Si el score supera `min_score_important`, va a `importantes/`. Caso contrario, a `no_importantes/`.

**Tratamiento especial para fotos antiguas (pre-2010):** las penalizaciones por blur y oscuridad se reducen a la mitad, ya que la calidad técnica de las cámaras de esa época era menor.

---

## Instalación

### Requisitos
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) — los binarios `ffmpeg.exe` y `ffprobe.exe` deben estar en la raíz del proyecto o en el PATH del sistema.
- GPU NVIDIA con CUDA (recomendado para acelerar CLIP, aunque funciona en CPU).

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/filtrador-de-fotos.git
cd filtrador-de-fotos

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/macOS

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. (Opcional, para GPU con CUDA) Instalar PyTorch con soporte CUDA
# Ver https://pytorch.org/get-started/locally/ para el comando exacto según tu versión de CUDA
```

---

## Configuración (`config.json`)

```json
{
    "paths": {
        "input_dir": "E:/FotosFiltrar",
        "output_importantes": "E:/FotosProcesadas/importantes",
        "output_no_importantes": "E:/FotosProcesadas/no_importantes"
    },
    "processing": {
        "num_workers": 4,
        "batch_size_clip": 32,
        "device": "cuda",
        "video_sample_frames": 10,
        "time_window_minutes": 0
    },
    "thresholds": {
        "min_blur_variance": 15.0,
        "max_darkness_ratio": 0.90,
        "similarity_threshold": 0.92,
        "min_score_important": 2.0
    },
    "scoring_weights": {
        "has_faces": 5.0,
        "has_a_person": 2.0,
        "is_blurry": -3.0,
        "is_dark": -2.0,
        "is_screenshot": -10.0,
        "is_document": -5.0,
        "is_family_moment": 10.0,
        "is_landscape": 5.0,
        "is_pet": 5.0,
        "is_selfie": 5.0,
        "is_food": -1.0
    }
}
```

### Descripción de cada campo

#### `paths`
| Campo | Descripción |
|---|---|
| `input_dir` | Carpeta raíz con tus fotos y videos (se escanea recursivamente) |
| `output_importantes` | Destino de los archivos clasificados como importantes |
| `output_no_importantes` | Destino de los archivos clasificados como no importantes |

#### `processing`
| Campo | Descripción |
|---|---|
| `num_workers` | Hilos para la Fase 1 (I/O paralelo). Valor recomendado: número de núcleos de CPU |
| `batch_size_clip` | Reservado para uso futuro (batch processing de CLIP) |
| `device` | `"cuda"` para GPU, `"cpu"` para procesador. CUDA es ~10x más rápido |
| `video_sample_frames` | Cantidad de frames a extraer por video para el análisis |
| `time_window_minutes` | Ventana temporal (minutos) para agrupar fotos y detectar ráfagas. `0` = sin agrupación |

#### `thresholds`
| Campo | Descripción |
|---|---|
| `min_blur_variance` | Score de nitidez mínimo (varianza del Laplaciano). Menor = más borrosa |
| `max_darkness_ratio` | Proporción máxima de píxeles oscuros permitida (0.0–1.0) |
| `similarity_threshold` | Umbral de similitud coseno para detectar duplicados (0.0–1.0). Valores altos = más estricto |
| `min_score_important` | Score mínimo para clasificar una foto como "importante" |

#### `scoring_weights`
Pesos para el cálculo del score final. Positivo = suma, negativo = penaliza.

| Campo | Descripción |
|---|---|
| `has_faces` | **Bonus por cada rostro** detectado por MediaPipe (se multiplica por la cantidad) |
| `has_a_person` | Bonus si CLIP detecta al menos una persona en la imagen (cuerpo, espalda, etc.) |
| `is_family_moment` | Bonus por momentos familiares o grupos de personas |
| `is_selfie` | Bonus por selfies o retratos cercanos |
| `is_landscape` | Bonus por paisajes naturales |
| `is_pet` | Bonus por fotos de mascotas o animales |
| `is_food` | Penalización leve por fotos de comida |
| `is_screenshot` | Penalización por capturas de pantalla |
| `is_document` | Penalización por fotos de documentos o texto |
| `is_blurry` | Penalización por imágenes borrosas |
| `is_dark` | Penalización por imágenes demasiado oscuras |

---

## Uso

```bash
# Asegurarte de estar en la raíz del proyecto con el entorno activado
python main.py
```

El script mostrará el progreso por fase y generará `reporte_clasificacion.csv` al finalizar.

---

## Estructura del proyecto

```
filtrador-de-fotos/
│
├── main.py                  # Punto de entrada principal, orquesta las 4 fases
├── config.json              # Configuración de rutas, umbrales y pesos
├── requirements.txt         # Dependencias de Python
├── ffmpeg.exe               # Binario FFmpeg (Windows)
├── ffprobe.exe              # Binario FFprobe (Windows)
│
└── src/
    ├── __init__.py
    ├── config_loader.py     # Carga y valida config.json
    ├── media_io.py          # Lectura de imágenes/videos, extracción de fechas y frames
    ├── quality.py           # Análisis de nitidez e iluminación (OpenCV)
    ├── semantic.py          # Análisis semántico con CLIP y detección de rostros (MediaPipe)
    ├── similarity.py        # Agrupación temporal y detección de duplicados/ráfagas
    ├── scoring.py           # Cálculo del score final y decisión de categoría
    └── organizer.py         # Copia de archivos al destino y generación del reporte CSV
```

### Descripción de cada archivo

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Orquesta todo el pipeline: escaneo → calidad → semántica → similitud → scoring → copia |
| `config.json` | Configuración completa del sistema (rutas, pesos, umbrales, hardware) |
| `requirements.txt` | Lista de dependencias pip |
| `src/config_loader.py` | Clase `Config` que carga `config.json` y expone sus secciones como propiedades |
| `src/media_io.py` | Lee imágenes (incluyendo `.heic`) y videos, extrae fecha EXIF, y usa FFmpeg para frames |
| `src/quality.py` | Calcula `blur_variance`, `darkness_ratio` y `brightness_ratio` usando OpenCV |
| `src/semantic.py` | Clasifica imágenes con CLIP zero-shot y cuenta rostros con MediaPipe |
| `src/similarity.py` | Agrupa por ventana temporal y detecta duplicados/ráfagas por similitud coseno |
| `src/scoring.py` | Suma pesos según los atributos detectados y decide la categoría final |
| `src/organizer.py` | Copia archivos a `importantes/` o `no_importantes/` y genera el CSV de reporte |

---

## Formatos soportados

| Tipo | Extensiones |
|---|---|
| Imágenes | `.jpg`, `.jpeg`, `.png`, `.heic`, `.webp` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv` |

---

## Licencia

MIT
