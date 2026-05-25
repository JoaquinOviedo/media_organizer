import cv2
import numpy as np
from PIL import Image

def analyze_quality(image: Image.Image) -> dict:
    """
    Analiza la calidad de una imagen (nitidez, iluminación).
    Devuelve un diccionario con métricas y banderas booleanas.
    """
    # Convertir PIL Image a OpenCV BGR numpy array
    open_cv_image = np.array(image)
    if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 3:
        # Convertir RGB a BGR para OpenCV
        open_cv_image = open_cv_image[:, :, ::-1].copy()
    
    # Convertir a escala de grises
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    
    # Análisis de nitidez (Blur) usando Varianza del Laplaciano
    blur_variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Análisis de iluminación
    # Calculamos qué porcentaje de píxeles son "muy oscuros" (valor < 30 de 255)
    dark_pixels = np.sum(gray < 30)
    total_pixels = gray.shape[0] * gray.shape[1]
    darkness_ratio = dark_pixels / total_pixels
    
    # También podemos detectar si está sobreexpuesta
    bright_pixels = np.sum(gray > 225)
    brightness_ratio = bright_pixels / total_pixels
    
    return {
        "blur_variance": float(blur_variance),
        "darkness_ratio": float(darkness_ratio),
        "brightness_ratio": float(brightness_ratio)
    }
