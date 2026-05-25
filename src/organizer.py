import os
import shutil
import pandas as pd
from pathlib import Path

class Organizer:
    def __init__(self, out_importantes: str, out_no_importantes: str):
        self.out_importantes = Path(out_importantes)
        self.out_no_importantes = Path(out_no_importantes)
        
        # Crear directorios si no existen
        self.out_importantes.mkdir(parents=True, exist_ok=True)
        self.out_no_importantes.mkdir(parents=True, exist_ok=True)
        
        self.report_data = []

    def _get_unique_path(self, dest_dir: Path, original_name: str) -> Path:
        """Evita colisiones de nombres añadiendo un sufijo."""
        base_name = Path(original_name).stem
        ext = Path(original_name).suffix
        counter = 1
        
        dest_path = dest_dir / original_name
        while dest_path.exists():
            dest_path = dest_dir / f"{base_name}_{counter}{ext}"
            counter += 1
            
        return dest_path

    def process_and_copy(self, item: dict, base_input_dir: Path = None):
        """
        Copia el archivo a su destino final y registra en el reporte.
        """
        file_path = Path(item["file_path"])
        category = item["category"]
        
        if category == "importantes":
            dest_dir = self.out_importantes
        else:
            dest_dir = self.out_no_importantes
            
        if base_input_dir:
            try:
                # Obtener ruta relativa ignorando el input_dir base
                rel_path = file_path.relative_to(base_input_dir).parent
                dest_dir = dest_dir / rel_path
                dest_dir.mkdir(parents=True, exist_ok=True)
            except ValueError:
                pass
                
        dest_path = self._get_unique_path(dest_dir, file_path.name)
        
        try:
            # copy2 preserva metadatos (fechas, permisos)
            shutil.copy2(file_path, dest_path)
            status = "Copiado"
        except Exception as e:
            status = f"Error: {e}"
            
        self.report_data.append({
            "Archivo Original": str(file_path),
            "Archivo Destino": str(dest_path),
            "Categoria": category,
            "Score": round(item.get("score", 0.0), 2),
            "Motivos": item.get("reasons", ""),
            "Estado": status
        })

    def generate_report(self, output_csv: str = "reporte_clasificacion.csv"):
        """Genera el archivo CSV final."""
        if not self.report_data:
            print("No hay datos para el reporte.")
            return
            
        df = pd.DataFrame(self.report_data)
        df.to_csv(output_csv, index=False, encoding='utf-8-sig')
        print(f"Reporte generado: {output_csv}")
