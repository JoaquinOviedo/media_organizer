from datetime import datetime

# Año a partir del cual una foto se considera "antigua" (recibe tratamiento especial)
VINTAGE_YEAR_THRESHOLD = 2010

def calculate_score(item: dict, config_thresholds: dict, config_weights: dict) -> tuple:
    """
    Calcula el score total de un item y decide su categoría y motivo.
    
    Lógica especial para fotos antiguas:
      - Las fotos anteriores a VINTAGE_YEAR_THRESHOLD reciben penalizaciones reducidas
        por blur y oscuridad, ya que la calidad técnica de la época era menor.
    
    Lógica especial para duplicados:
      - Solo el(los) marcado(s) como is_duplicate=True reciben penalización.
        El ganador del clúster (is_duplicate=False) NO es penalizado.
    
    Retorna (score, category, reasons)
    """
    score = 0.0
    reasons = []

    # --- ¿Es una foto antigua? ---
    creation_date = item.get("creation_date")
    is_vintage = False
    if isinstance(creation_date, datetime):
        is_vintage = creation_date.year < VINTAGE_YEAR_THRESHOLD

    if is_vintage:
        reasons.append(f"Foto antigua ({creation_date.year})")

    # --- Evaluación de Calidad ---
    quality = item.get("quality_data", {})
    if quality:
        blur = quality.get("blur_variance", 0)
        darkness = quality.get("darkness_ratio", 0)

        blur_threshold = config_thresholds.get("min_blur_variance", 50.0)
        dark_threshold = config_thresholds.get("max_darkness_ratio", 0.85)

        # Para fotos antiguas, reducimos la penalización a la mitad
        blur_penalty = config_weights.get("is_blurry", -3.0)
        dark_penalty = config_weights.get("is_dark", -2.0)
        if is_vintage:
            blur_penalty = blur_penalty * 0.5
            dark_penalty = dark_penalty * 0.5

        if blur < blur_threshold:
            score += blur_penalty
            reasons.append("Imagen borrosa (penalización reducida por antigüedad)" if is_vintage else "Imagen borrosa")

        if darkness > dark_threshold:
            score += dark_penalty
            reasons.append("Imagen oscura (penalización reducida por antigüedad)" if is_vintage else "Imagen demasiado oscura")

    # --- Evaluación Semántica ---
    semantic = item.get("semantic_data", {})
    if semantic:
        # Faces (MediaPipe)
        num_faces = semantic.get("num_faces", 0)
        if num_faces > 0:
            score += config_weights.get("has_faces", 3.0) * num_faces
            reasons.append(f"Personas detectadas ({num_faces})")

        # Persona visible (CLIP) — complementa has_faces para cuerpos sin rostro claro
        if semantic.get("has_a_person", 0) > 0.5:
            score += config_weights.get("has_a_person", 2.0)
            reasons.append("Persona en la imagen (CLIP)")

        # Momento familiar / grupo de personas — mayor prioridad
        if semantic.get("is_family_moment", 0) > 0.5:
            score += config_weights.get("is_family_moment", 5.0)
            reasons.append("Momento familiar/Grupo")

        # Selfie
        if semantic.get("is_selfie", 0) > 0.55:
            score += config_weights.get("is_selfie", 4.0)
            reasons.append("Selfie")

        # Paisaje
        if semantic.get("is_landscape", 0) > 0.6:
            score += config_weights.get("is_landscape", 3.0)
            reasons.append("Paisaje")

        # Mascota
        if semantic.get("is_pet", 0) > 0.6:
            score += config_weights.get("is_pet", 3.0)
            reasons.append("Mascota/Animal")

        # Screenshot (penalización)
        if semantic.get("is_screenshot", 0) > 0.7:
            score += config_weights.get("is_screenshot", -10.0)
            reasons.append("Captura de pantalla")

        # Documento (penalización suave)
        if semantic.get("is_document", 0) > 0.6:
            score += config_weights.get("is_document", -5.0)
            reasons.append("Documento/Texto")

        # Comida (penalización muy leve)
        if semantic.get("is_food", 0) > 0.65:
            score += config_weights.get("is_food", -1.0)
            reasons.append("Foto de comida")

    # --- Evaluación de Similitud / Duplicados ---
    # Solo los archivos marcados como duplicados (los "perdedores" del clúster)
    # reciben penalización. El ganador del clúster tiene is_duplicate=False.
    if item.get("is_duplicate", False):
        score -= 20.0
        reasons.append(item.get("duplicate_reason", "Duplicado/Ráfaga"))

    # --- Decisión Final ---
    min_score = config_thresholds.get("min_score_important", 2.0)

    # Forzar "no_importantes" si es screenshot claro o duplicado descartado
    is_screenshot_clear = semantic and semantic.get("is_screenshot", 0) > 0.80
    if item.get("is_duplicate") or is_screenshot_clear:
        category = "no_importantes"
    elif score >= min_score:
        category = "importantes"
        if not reasons:
            reasons.append("Cumple umbral mínimo (general)")
    else:
        category = "no_importantes"
        if not reasons:
            reasons.append("No alcanza el umbral de importancia")

    motivo_final = " | ".join(reasons)
    return score, category, motivo_final
