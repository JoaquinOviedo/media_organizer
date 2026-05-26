import os
import sys
import gc
from pathlib import Path
from tqdm import tqdm
import concurrent.futures

from src.config_loader import Config
from src.media_io import get_file_type, extract_creation_date, read_image, extract_video_frames_ffmpeg, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from src.quality import analyze_quality
from src.semantic import SemanticAnalyzer
from src.similarity import group_by_time_window, flag_duplicates_in_group
from src.scoring import calculate_score
from src.organizer import Organizer

def calculate_optimal_block_size(total_files: int, config: Config) -> int:
    """
    Calcula el tamaño óptimo del bloque basado en:
    - RAM disponible (max_ram_mb)
    - Cantidad de archivos
    - Estimación de bytes por archivo
    
    Returns: número de archivos por bloque
    """
    mem_config = config.memory_management
    max_ram_mb = mem_config.get("max_ram_mb", 2048)
    bytes_per_file = mem_config.get("estimate_bytes_per_file", 5242880)  # 5MB por defecto
    min_block = mem_config.get("min_block_size", 10)
    max_block = mem_config.get("max_block_size", 500)
    
    # Calcular cuántos archivos caben en la RAM disponible
    estimated_bytes_total = total_files * bytes_per_file
    available_bytes = max_ram_mb * 1024 * 1024
    
    # Si todo cabe en memoria, procesar todo de una vez
    if estimated_bytes_total <= available_bytes:
        block_size = total_files
    else:
        # Calcular bloques proporcionales
        block_size = int((available_bytes / bytes_per_file) * 0.9)  # 90% para estar seguro
    
    # Aplicar límites
    block_size = max(min_block, min(block_size, max_block))
    
    print(f"📊 Configuración de Memoria:")
    print(f"   - RAM disponible: {max_ram_mb}MB")
    print(f"   - Total de archivos: {total_files}")
    print(f"   - Tamaño estimado por archivo: {bytes_per_file / (1024*1024):.1f}MB")
    print(f"   - Tamaño de bloque calculado: {block_size} archivos")
    print(f"   - Cantidad de bloques: {(total_files + block_size - 1) // block_size}")
    
    return block_size

def process_file_io_quality(file_path: str) -> dict:
    """Fase 1: Lectura I/O y calidad (CPU bound). Ideal para multithreading."""
    file_type = get_file_type(file_path)
    creation_date = extract_creation_date(file_path)
    
    item_data = {
        "file_path": file_path,
        "file_type": file_type,
        "creation_date": creation_date,
        "frames": [], # PIL Images
        "quality_data": {},
        "error": None
    }
    
    try:
        if file_type == 'image':
            img = read_image(file_path)
            if img:
                item_data["frames"].append(img)
                item_data["quality_data"] = analyze_quality(img)
        elif file_type == 'video':
            # Leer 3 frames por defecto
            frames = extract_video_frames_ffmpeg(file_path, num_frames=3)
            if frames:
                item_data["frames"] = frames
                # Promediar calidad de los frames
                q_list = [analyze_quality(f) for f in frames]
                item_data["quality_data"] = {
                    "blur_variance": sum(q["blur_variance"] for q in q_list) / len(q_list),
                    "darkness_ratio": sum(q["darkness_ratio"] for q in q_list) / len(q_list),
                    "brightness_ratio": sum(q["brightness_ratio"] for q in q_list) / len(q_list)
                }
    except Exception as e:
        item_data["error"] = str(e)
        
    return item_data

def process_semantic(item_data: dict, semantic_analyzer: SemanticAnalyzer) -> dict:
    """Fase 2: Análisis Semántico con IA (GPU/CPU). Secuencial para evitar OOM/CUDA errors."""
    if item_data.get("error") or not item_data["frames"]:
        item_data["semantic_data"] = {}
        return item_data
        
    frames = item_data["frames"]
    try:
        # Analizar todos los frames y promediar si es video
        sem_list = [semantic_analyzer.analyze(f) for f in frames]
        
        if len(sem_list) == 1:
            item_data["semantic_data"] = sem_list[0]
        else:
            # Promediar scores para video
            avg_scores = {}
            for k in sem_list[0]["clip_scores"].keys():
                avg_scores[k] = sum(s["clip_scores"][k] for s in sem_list) / len(sem_list)
                
            item_data["semantic_data"] = {
                "embedding": sum(s["embedding"] for s in sem_list) / len(sem_list), # Promedio de embeddings
                "clip_scores": avg_scores,
                "num_faces": max(s["num_faces"] for s in sem_list), # Max caras detectadas en cualquier frame
                "is_family_moment": sum(s["is_family_moment"] for s in sem_list) / len(sem_list),
                "is_screenshot": sum(s["is_screenshot"] for s in sem_list) / len(sem_list),
                "is_landscape": sum(s["is_landscape"] for s in sem_list) / len(sem_list),
                "is_pet": sum(s["is_pet"] for s in sem_list) / len(sem_list),
                "is_food": sum(s["is_food"] for s in sem_list) / len(sem_list),
                "is_document": sum(s["is_document"] for s in sem_list) / len(sem_list),
                "is_selfie": sum(s["is_selfie"] for s in sem_list) / len(sem_list)
            }
    except Exception as e:
        item_data["error"] = f"Semantic Error: {e}"
        item_data["semantic_data"] = {}
        
    # Liberar memoria de imágenes, ya no las necesitamos
    item_data["frames"] = [] 
    return item_data

def process_block(block_files: list, block_num: int, total_blocks: int, config: Config, semantic_analyzer: SemanticAnalyzer) -> list:
    """
    Procesa un bloque de archivos a través de todas las fases.
    Retorna los items procesados del bloque.
    """
    print(f"\n🔄 Procesando Bloque {block_num}/{total_blocks} ({len(block_files)} archivos)...")
    
    # Fase 1: I/O y Calidad
    print(f"  Fase 1: Extrayendo metadatos...")
    items_phase1 = []
    num_workers = config.processing.get("num_workers", 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_file_io_quality, f): f for f in block_files}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=f"  Calidad Bloque {block_num}", leave=False):
            items_phase1.append(future.result())
    
    # Filtrar errores
    items_valid = [item for item in items_phase1 if not item.get("error") and item.get("frames")]
    print(f"  ✓ {len(items_valid)} archivos válidos en este bloque")
    
    if not items_valid:
        return []
    
    # Fase 2: Semántica
    print(f"  Fase 2: Análisis Semántico...")
    for item in tqdm(items_valid, desc=f"  Semántica Bloque {block_num}", leave=False):
        process_semantic(item, semantic_analyzer)
    
    # Fase 3: Agrupación y Similitud
    print(f"  Fase 3: Agrupando por tiempo...")
    time_window = config.processing.get("time_window_minutes", 60)
    groups = group_by_time_window(items_valid, window_minutes=time_window)
    
    sim_threshold = config.thresholds.get("similarity_threshold", 0.92)
    processed_items = []
    for group in tqdm(groups, desc=f"  Clustering Bloque {block_num}", leave=False):
        processed_group = flag_duplicates_in_group(group, similarity_threshold=sim_threshold)
        processed_items.extend(processed_group)
    
    # Liberar memoria
    del items_phase1
    del items_valid
    del groups
    gc.collect()
    
    print(f"  ✓ Bloque {block_num} procesado: {len(processed_items)} items")
    return processed_items

def main():
    print("🚀 Iniciando Organizador de Medios con Gestión de Memoria...")
    try:
        config = Config()
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
        
    input_dir = Path(config.paths["input_dir"])
    if not input_dir.exists():
        print(f"Error: El directorio de entrada '{input_dir}' no existe.")
        sys.exit(1)
        
    # 1. Escanear archivos
    print("\n📂 Escaneando archivos...")
    all_files = []
    for ext in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS):
        # Escaneo recursivo
        all_files.extend([str(p) for p in input_dir.rglob(f"*{ext}")])
        all_files.extend([str(p) for p in input_dir.rglob(f"*{ext.upper()}")])
        
    all_files = list(set(all_files)) # Eliminar posibles duplicados
    print(f"✓ Encontrados {len(all_files)} archivos multimedia.")
    
    if not all_files:
        print("No hay nada que procesar.")
        sys.exit(0)
    
    # Calcular tamaño óptimo de bloque
    block_size = calculate_optimal_block_size(len(all_files), config)
    total_blocks = (len(all_files) + block_size - 1) // block_size
    
    # Procesar en bloques
    print(f"\n⚙️ Iniciando procesamiento en {total_blocks} bloque(s)...")
    
    semantic_analyzer = SemanticAnalyzer(device=config.processing.get("device", "cpu"))
    all_processed_items = []
    
    for block_num in range(total_blocks):
        start_idx = block_num * block_size
        end_idx = min(start_idx + block_size, len(all_files))
        block_files = all_files[start_idx:end_idx]
        
        block_items = process_block(block_files, block_num + 1, total_blocks, config, semantic_analyzer)
        all_processed_items.extend(block_items)
    
    print(f"\n✓ Procesamiento de bloques completado: {len(all_processed_items)} items procesados")
    
    # Fase 4: Scoring y Organización
    print(f"\n📊 Fase 4: Calculando puntajes y organizando archivos...")
    organizer = Organizer(config.paths["output_importantes"], config.paths["output_no_importantes"])
    
    for item in tqdm(all_processed_items, desc="Scoring"):
        score, category, reasons = calculate_score(item, config.thresholds, config.scoring_weights)
        item["score"] = score
        item["category"] = category
        item["reasons"] = reasons
        organizer.process_and_copy(item, base_input_dir=input_dir)
        
    # Generar reporte
    organizer.generate_report(output_csv="reporte_clasificacion.csv")
    print("\n✅ ¡Proceso Finalizado Exitosamente!")

if __name__ == "__main__":
    main()

