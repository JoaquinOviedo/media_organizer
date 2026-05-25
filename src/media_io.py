import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from PIL import Image, ExifTags
import pillow_heif

# Registrar HEIF opener
pillow_heif.register_heif_opener()

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}

def get_file_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'

def extract_creation_date(file_path: str) -> datetime:
    """Extrae la fecha de creación del archivo (EXIF para imágenes, stat para videos)."""
    try:
        file_type = get_file_type(file_path)
        if file_type == 'image':
            with Image.open(file_path) as img:
                exif = img.getexif()
                if exif is not None:
                    # 36867 es DateTimeOriginal
                    for tag_id in exif:
                        tag = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag == 'DateTimeOriginal':
                            date_str = exif.get(tag_id)
                            # Formato típico EXIF: "2023:05:25 15:30:00"
                            return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    
    # Fallback: fecha de modificación o creación del archivo
    stat = os.stat(file_path)
    try:
        # En Windows st_ctime es creación
        return datetime.fromtimestamp(stat.st_ctime)
    except AttributeError:
        return datetime.fromtimestamp(stat.st_mtime)

def read_image(file_path: str) -> Image.Image:
    """Lee una imagen (soportando HEIC) y la convierte a RGB."""
    try:
        img = Image.open(file_path)
        img = img.convert("RGB")
        return img
    except Exception as e:
        print(f"Error leyendo imagen {file_path}: {e}")
        return None

def extract_video_frames_ffmpeg(video_path: str, num_frames: int = 3) -> list:
    """Extrae N frames de un video usando FFmpeg (vía subprocess) equiespaciados."""
    frames = []
    temp_dir = tempfile.mkdtemp(prefix="video_frames_")
    try:
        # Primero, obtener la duración del video
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration_str = result.stdout.strip()
        try:
            duration = float(duration_str) if duration_str else 0.0
        except ValueError:
            duration = 0.0
        
        # Calcular los timestamps equiespaciados
        if duration > 0:
            intervals = [duration * i / (num_frames + 1) for i in range(1, num_frames + 1)]
        else:
            intervals = [0.0] * num_frames
            
        for i, timestamp in enumerate(intervals):
            output_frame = os.path.join(temp_dir, f"frame_{i}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
                "-frames:v", "1", "-q:v", "2", output_frame
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(output_frame):
                img = Image.open(output_frame).copy() # Cargar y desconectar del archivo
                frames.append(img)
                
    except Exception as e:
        print(f"Error extrayendo frames de {video_path}: {e}")
    finally:
        # Limpiar el directorio temporal
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    return frames
