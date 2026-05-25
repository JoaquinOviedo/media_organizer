import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def flag_duplicates_in_group(items: list, similarity_threshold: float = 0.92) -> list:
    """
    Recibe una lista de diccionarios que representan imágenes/videos dentro 
    de una misma ventana temporal.
    Identifica elementos muy similares (ráfagas) y marca a los redundantes.
    Devuelve la misma lista modificada con un flag 'is_duplicate' y un motivo.
    """
    if not items or len(items) == 1:
        for item in items:
            item["is_duplicate"] = False
        return items

    # Extraer los embeddings
    embeddings = [item["semantic_data"]["embedding"] for item in items]
    matrix = np.vstack(embeddings)
    
    # Calcular matriz de similitud del coseno
    sim_matrix = cosine_similarity(matrix)
    
    n = len(items)
    # Lista para mantener registro de qué items ya hemos marcado como redundantes
    is_redundant = [False] * n
    
    # Evaluar pares para encontrar similitudes
    # Recorremos para formar "clústeres" simples
    for i in range(n):
        if is_redundant[i]:
            continue
            
        cluster_indices = [i]
        for j in range(i + 1, n):
            if not is_redundant[j] and sim_matrix[i, j] >= similarity_threshold:
                cluster_indices.append(j)
                
        if len(cluster_indices) > 1:
            # Hay elementos similares. Elegir el "mejor" del clúster.
            # Prioridad: 1) Personas/Familia, 2) Paisaje, 3) Nitidez, 4) Iluminación
            # Para fotos antiguas (pre-2010), la nitidez tiene menos peso en la decisión.

            from datetime import datetime
            VINTAGE_YEAR = 2010

            def get_quality_score(idx):
                item = items[idx]
                q = item.get("quality_data", {})
                s = item.get("semantic_data", {})

                creation_date = item.get("creation_date")
                is_vintage = isinstance(creation_date, datetime) and creation_date.year < VINTAGE_YEAR

                blur = q.get("blur_variance", 0)
                dark = q.get("darkness_ratio", 1.0)

                # Para fotos antiguas reducimos el impacto del blur en la comparación
                blur_weight = 30.0 if is_vintage else 80.0

                # Prioridades semánticas (pesos altos para que dominen sobre calidad técnica)
                faces   = s.get("num_faces", 0) * 300        # Mayor prioridad: personas
                family  = s.get("is_family_moment", 0) * 250  # Segunda: familia/grupo
                selfie  = s.get("is_selfie", 0) * 180         # Tercera: selfie
                landscape = s.get("is_landscape", 0) * 150    # Cuarta: paisaje

                return faces + family + selfie + landscape + (blur * blur_weight) - (dark * 100)

            best_idx = max(cluster_indices, key=get_quality_score)
            
            for idx in cluster_indices:
                if idx != best_idx:
                    is_redundant[idx] = True
                    items[idx]["is_duplicate"] = True
                    items[idx]["duplicate_reason"] = "Ráfaga/Duplicado detectado"

    # Asegurarnos de que todos tengan la key 'is_duplicate'
    for i, item in enumerate(items):
        if not item.get("is_duplicate"):
            item["is_duplicate"] = False
            
    return items

def group_by_time_window(items: list, window_minutes: int = 60) -> list:
    """
    Agrupa los items en sublistas si su fecha de creación está dentro 
    de una misma ventana de tiempo (window_minutes).
    items: lista de diccionarios, deben tener la key 'creation_date'.
    """
    if not items:
        return []
        
    # Ordenar por fecha
    sorted_items = sorted(items, key=lambda x: x["creation_date"])
    
    groups = []
    current_group = [sorted_items[0]]
    
    for item in sorted_items[1:]:
        delta = item["creation_date"] - current_group[-1]["creation_date"]
        if delta.total_seconds() <= window_minutes * 60:
            current_group.append(item)
        else:
            groups.append(current_group)
            current_group = [item]
            
    if current_group:
        groups.append(current_group)
        
    return groups
