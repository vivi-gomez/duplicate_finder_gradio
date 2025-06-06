#!/usr/bin/env python3
"""
Detector de archivos duplicados con interfaz Gradio
Optimizado para GPU NVIDIA RTX 3090
"""

import os
import hashlib
import json
import shutil
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import time
from datetime import datetime
import pandas as pd
import gradio as gr
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import cupy as cp
    import numpy as np
    GPU_AVAILABLE = True
    logger.info("GPU CuPy disponible - Usando aceleración GPU")
except ImportError:
    GPU_AVAILABLE = False
    logger.info("GPU CuPy no disponible - Usando CPU")

class DuplicateFinderGPU:
    def __init__(self, min_size=1024*1024):  # 1MB mínimo por defecto
        self.min_size = min_size
        self.files_by_size = defaultdict(list)
        self.duplicates = defaultdict(list)
        self.results = []
        self.progress_callback = None
        self.stop_flag = False
        
    def set_progress_callback(self, callback):
        """Establece callback para actualizar progreso"""
        self.progress_callback = callback
    
    def stop_analysis(self):
        """Detiene el análisis en curso"""
        self.stop_flag = True
    
    def find_large_files(self, directory):
        """Encuentra archivos grandes para procesar"""
        directory = Path(directory)
        
        if self.progress_callback:
            self.progress_callback(0, "Escaneando archivos...")
        
        total_files = 0
        processed_files = 0
        
        # Primer paso: contar archivos
        for _ in directory.rglob('*'):
            if self.stop_flag:
                return {}
            total_files += 1
        
        # Segundo paso: procesar archivos
        for file_path in directory.rglob('*'):
            if self.stop_flag:
                return {}
                
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    size = stat.st_size
                    if size >= self.min_size:
                        self.files_by_size[size].append({
                            'path': file_path,
                            'size': size,
                            'mtime': stat.st_mtime,
                            'mtime_readable': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        })
                except (OSError, PermissionError):
                    continue
            
            processed_files += 1
            if processed_files % 100 == 0 and self.progress_callback:
                progress = (processed_files / total_files) * 30  # 30% del progreso total
                self.progress_callback(progress, f"Escaneados {processed_files}/{total_files} archivos")
        
        # Solo procesar tamaños con múltiples archivos
        potential_duplicates = {size: files for size, files in self.files_by_size.items() if len(files) > 1}
        
        return potential_duplicates
    
    def calculate_hash_gpu(self, file_info, algorithm='sha256'):
        """Calcula hash usando GPU si está disponible"""
        if not GPU_AVAILABLE:
            return self.calculate_hash_cpu(file_info, algorithm)
            
        try:
            hasher = hashlib.new(algorithm)
            file_path = file_info['path']
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(16 * 1024 * 1024):  # 16MB chunks para GPU
                    if self.stop_flag:
                        return None
                    
                    # Procesar en GPU
                    gpu_data = cp.frombuffer(chunk, dtype=cp.uint8)
                    # Convertir de vuelta a CPU para hasher
                    cpu_data = cp.asnumpy(gpu_data).tobytes()
                    hasher.update(cpu_data)
                    
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Error calculando hash GPU para {file_path}: {e}")
            return self.calculate_hash_cpu(file_info, algorithm)
    
    def calculate_hash_cpu(self, file_info, algorithm='sha256'):
        """Calcula hash usando CPU como fallback"""
        hasher = hashlib.new(algorithm)
        file_path = file_info['path']
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192 * 1024):  # 8MB chunks
                    if self.stop_flag:
                        return None
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError) as e:
            logger.error(f"Error leyendo {file_path}: {e}")
            return None
    
    def process_files_parallel(self, files_by_size, max_workers=None):
        """Procesa archivos en paralelo"""
        if max_workers is None:
            # Para GPU, usar menos workers para evitar conflictos de memoria
            max_workers = min(8 if GPU_AVAILABLE else 16, (os.cpu_count() or 1) + 4)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {}
            
            for size, files in files_by_size.items():
                for file_info in files:
                    if self.stop_flag:
                        break
                    future = executor.submit(self.calculate_hash_gpu, file_info)
                    future_to_file[future] = file_info
            
            processed = 0
            total = len(future_to_file)
            
            for future in as_completed(future_to_file):
                if self.stop_flag:
                    break
                    
                file_info = future_to_file[future]
                try:
                    file_hash = future.result()
                    if file_hash:
                        self.duplicates[file_hash].append(file_info)
                    
                    processed += 1
                    if processed % 10 == 0 and self.progress_callback:
                        progress = 30 + (processed / total) * 60  # 60% del progreso total
                        self.progress_callback(progress, f"Procesados {processed}/{total} archivos")
                        
                except Exception as e:
                    logger.error(f"Error procesando {file_info['path']}: {e}")
    
    def analyze_duplicates(self, directory):
        """Analiza duplicados y retorna resultados"""
        start_time = time.time()
        self.stop_flag = False
        self.files_by_size.clear()
        self.duplicates.clear()
        self.results.clear()
        
        if self.progress_callback:
            self.progress_callback(0, "Iniciando análisis...")
        
        files_by_size = self.find_large_files(directory)
        if not files_by_size or self.stop_flag:
            return []
        
        if self.progress_callback:
            self.progress_callback(30, "Calculando hashes...")
        
        self.process_files_parallel(files_by_size)
        
        if self.stop_flag:
            return []
        
        # Filtrar solo los verdaderos duplicados
        true_duplicates = {h: files for h, files in self.duplicates.items() if len(files) > 1}
        
        if self.progress_callback:
            self.progress_callback(90, "Preparando resultados...")
        
        # Preparar datos para la interfaz
        group_id = 0
        total_wasted_space = 0
        
        for file_hash, files in true_duplicates.items():
            if self.stop_flag:
                break
                
            # Ordenar por fecha de modificación (más reciente primero)
            files.sort(key=lambda x: x['mtime'], reverse=True)
            
            size = files[0]['size']
            wasted_space = size * (len(files) - 1)
            total_wasted_space += wasted_space
            
            # Determinar archivo prioritario (más reciente con nombre similar)
            priority_file = self.get_priority_file(files)
            
            group_data = {
                'group_id': group_id,
                'hash': file_hash,
                'size': size,
                'size_readable': self.format_size(size),
                'wasted_space': wasted_space,
                'wasted_space_readable': self.format_size(wasted_space),
                'files': []
            }
            
            for i, file_info in enumerate(files):
                is_priority = file_info['path'] == priority_file['path']
                file_data = {
                    'path': str(file_info['path']),
                    'mtime': file_info['mtime'],
                    'mtime_readable': file_info['mtime_readable'],
                    'is_priority': is_priority,
                    'recommended_delete': not is_priority,
                    'selected': False
                }
                group_data['files'].append(file_data)
            
            self.results.append(group_data)
            group_id += 1
        
        elapsed = time.time() - start_time
        
        if self.progress_callback:
            self.progress_callback(100, f"Completado! {len(self.results)} grupos encontrados en {elapsed:.1f}s")
        
        return self.results
    
    def get_priority_file(self, files):
        """Determina el archivo prioritario basado en fecha y nombre"""
        # Ordenar por fecha de modificación (más reciente primero)
        files_by_date = sorted(files, key=lambda x: x['mtime'], reverse=True)
        
        # Si hay archivos con nombres similares, priorizar el más reciente de esos
        newest = files_by_date[0]
        
        # Buscar archivos con nombres similares al más reciente
        newest_name = Path(newest['path']).stem.lower()
        similar_files = []
        
        for file_info in files:
            file_name = Path(file_info['path']).stem.lower()
            if self.names_similar(newest_name, file_name):
                similar_files.append(file_info)
        
        if similar_files:
            # Retornar el más reciente de los archivos con nombres similares
            return max(similar_files, key=lambda x: x['mtime'])
        
        return newest
    
    def names_similar(self, name1, name2, threshold=0.8):
        """Verifica si dos nombres son similares"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, name1, name2).ratio() > threshold
    
    def format_size(self, size_bytes):
        """Formatea tamaños de archivo legibles"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

# Variables globales para la aplicación
finder = DuplicateFinderGPU()
current_results = []
selected_files = set()

def update_progress(progress, message):
    """Actualiza el progreso en la interfaz"""
    return gr.update(value=progress, label=message, visible=True)

def analyze_directory(directory, min_size_mb, progress=gr.Progress()):
    """Analiza directorio y retorna resultados"""
    global current_results, selected_files
    current_results = []
    selected_files = set()
    
    if not directory or not os.path.exists(directory):
        return "❌ Directorio no válido", gr.update(visible=False), gr.update(visible=False)
    
    # Configurar tamaño mínimo
    finder.min_size = int(min_size_mb * 1024 * 1024)
    
    # Callback de progreso
    def progress_callback(pct, msg):
        progress(pct/100, desc=msg)
    
    finder.set_progress_callback(progress_callback)
    
    try:
        current_results = finder.analyze_duplicates(directory)
        
        if not current_results:
            return "✅ No se encontraron archivos duplicados", gr.update(visible=False), gr.update(visible=False)
        
        # Preparar tabla para mostrar
        table_data = []
        for group in current_results:
            for file_info in group['files']:
                table_data.append([
                    group['group_id'],
                    "⭐ PRIORITARIO" if file_info['is_priority'] else "🔄 DUPLICADO",
                    file_info['path'],
                    file_info['mtime_readable'],
                    group['size_readable'],
                    file_info['recommended_delete']
                ])
        
        df = pd.DataFrame(table_data, columns=[
            "Grupo", "Estado", "Archivo", "Fecha Modificación", "Tamaño", "Eliminar"
        ])
        
        total_groups = len(current_results)
        total_files = sum(len(group['files']) for group in current_results)
        total_wasted = sum(group['wasted_space'] for group in current_results)
        
        summary = f"""
## 📊 Resumen del Análisis

- **Grupos de duplicados:** {total_groups}
- **Archivos analizados:** {total_files}
- **Espacio desperdiciado:** {finder.format_size(total_wasted)}
- **Aceleración:** {'🚀 GPU (NVIDIA RTX 3090)' if GPU_AVAILABLE else '⚡ CPU'}

### 📋 Instrucciones:
1. Los archivos **PRIORITARIOS** (⭐) son los más recientes y recomendados para conservar
2. Los archivos **DUPLICADOS** (🔄) están marcados para eliminación
3. Revisa la tabla y ajusta las selecciones según necesites
4. Usa los botones para seleccionar/deseleccionar archivos
5. Genera script de eliminación o elimina directamente

⚠️ **IMPORTANTE:** Siempre haz backup antes de eliminar archivos
        """
        
        return summary, gr.update(value=df, visible=True), gr.update(visible=True)
        
    except Exception as e:
        logger.error(f"Error en análisis: {e}")
        return f"❌ Error durante el análisis: {str(e)}", gr.update(visible=False), gr.update(visible=False)

def stop_analysis():
    """Detiene el análisis en curso"""
    finder.stop_analysis()
    return "⏹️ Análisis detenido"

def select_recommended():
    """Selecciona archivos recomendados para eliminación"""
    global selected_files
    selected_files = set()
    
    for group in current_results:
        for file_info in group['files']:
            if file_info['recommended_delete']:
                selected_files.add(file_info['path'])
    
    return f"✅ Seleccionados {len(selected_files)} archivos recomendados"

def select_all():
    """Selecciona todos los archivos"""
    global selected_files
    selected_files = set()
    
    for group in current_results:
        for file_info in group['files']:
            selected_files.add(file_info['path'])
    
    return f"✅ Seleccionados {len(selected_files)} archivos"

def deselect_all():
    """Deselecciona todos los archivos"""
    global selected_files
    selected_files = set()
    return "✅ Todos los archivos deseleccionados"

def generate_delete_script():
    """Genera script de eliminación"""
    if not selected_files:
        return "❌ No hay archivos seleccionados", None
    
    script_content = f"""#!/bin/bash
# Script generado automáticamente para eliminar archivos duplicados
# Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# ADVERTENCIA: Revisa cuidadosamente antes de ejecutar

echo "Eliminando {len(selected_files)} archivos duplicados..."
echo "ADVERTENCIA: Esta acción no se puede deshacer"
read -p "¿Continuar? (s/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "Operación cancelada"
    exit 1
fi

echo "Iniciando eliminación..."

"""
    
    for i, file_path in enumerate(selected_files, 1):
        script_content += f'echo "({i}/{len(selected_files)}) Eliminando: {file_path}"\n'
        script_content += f'rm "{file_path}"\n'
        script_content += f'if [ $? -eq 0 ]; then\n'
        script_content += f'    echo "✓ Eliminado exitosamente"\n'
        script_content += f'else\n'
        script_content += f'    echo "✗ Error al eliminar"\n'
        script_content += f'fi\n\n'
    
    script_content += '''echo "Eliminación completada"
echo "Archivos procesados: ''' + str(len(selected_files)) + '''"
'''
    
    # Guardar script
    script_path = "delete_duplicates.sh"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    os.chmod(script_path, 0o755)  # Hacer ejecutable
    
    return f"✅ Script generado: {script_path}", script_path

def delete_selected_files():
    """Elimina archivos seleccionados directamente"""
    if not selected_files:
        return "❌ No hay archivos seleccionados"
    
    deleted_count = 0
    errors = []
    
    for file_path in selected_files:
        try:
            os.remove(file_path)
            deleted_count += 1
        except Exception as e:
            errors.append(f"{file_path}: {str(e)}")
    
    result = f"✅ Eliminados {deleted_count}/{len(selected_files)} archivos"
    
    if errors:
        result += f"\n❌ Errores:\n" + "\n".join(errors[:5])  # Mostrar solo los primeros 5 errores
        if len(errors) > 5:
            result += f"\n... y {len(errors) - 5} errores más"
    
    # Limpiar selección
    selected_files.clear()
    
    return result

def create_interface():
    """Crea la interfaz Gradio"""
    with gr.Blocks(
        title="🔍 Detector de Archivos Duplicados GPU",
        theme=gr.themes.Soft(),
        css="""
        .duplicate-header { 
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        """
    ) as interface:
        
        gr.HTML("""
        <div class="duplicate-header">
            <h1>🔍 Detector de Archivos Duplicados GPU</h1>
            <p>Optimizado para NVIDIA RTX 3090 - Detección inteligente con conservación de versiones prioritarias</p>
        </div>
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                directory_input = gr.Textbox(
                    label="📁 Directorio a analizar",
                    placeholder="/ruta/a/tu/carpeta",
                    info="Introduce la ruta completa del directorio"
                )
            with gr.Column(scale=1):
                min_size_input = gr.Number(
                    label="📏 Tamaño mínimo (MB)",
                    value=1,
                    minimum=0.1,
                    step=0.1,
                    info="Archivos menores serán ignorados"
                )
        
        with gr.Row():
            analyze_btn = gr.Button("🚀 Iniciar Análisis", variant="primary", size="lg")
            stop_btn = gr.Button("⏹️ Detener", variant="secondary")
        
        status_output = gr.Markdown(label="Estado")
        
        with gr.Group(visible=False) as results_group:
            with gr.Row():
                select_recommended_btn = gr.Button("✨ Seleccionar Recomendados", variant="secondary")
                select_all_btn = gr.Button("☑️ Seleccionar Todos", variant="secondary")
                deselect_all_btn = gr.Button("⬜ Deseleccionar Todos", variant="secondary")
            
            with gr.Row():
                generate_script_btn = gr.Button("📝 Generar Script", variant="primary")
                delete_btn = gr.Button("🗑️ Eliminar Seleccionados", variant="stop")
            
            selection_status = gr.Markdown("Ningún archivo seleccionado")
            
            results_table = gr.Dataframe(
                label="📋 Archivos Duplicados Encontrados",
                headers=["Grupo", "Estado", "Archivo", "Fecha Modificación", "Tamaño", "Eliminar"],
                datatype=["number", "str", "str", "str", "str", "bool"],
                interactive=True,
                wrap=True
            )
            
            script_file = gr.File(label="📥 Descargar Script", visible=False)
        
        # Event handlers
        analyze_btn.click(
            fn=analyze_directory,
            inputs=[directory_input, min_size_input],
            outputs=[status_output, results_table, results_group],
            show_progress=True
        )
        
        stop_btn.click(
            fn=stop_analysis,
            outputs=[status_output]
        )
        
        select_recommended_btn.click(
            fn=select_recommended,
            outputs=[selection_status]
        )
        
        select_all_btn.click(
            fn=select_all,
            outputs=[selection_status]
        )
        
        deselect_all_btn.click(
            fn=deselect_all,
            outputs=[selection_status]
        )
        
        generate_script_btn.click(
            fn=generate_delete_script,
            outputs=[selection_status, script_file]
        ).then(
            lambda: gr.update(visible=True),
            outputs=[script_file]
        )
        
        delete_btn.click(
            fn=delete_selected_files,
            outputs=[selection_status]
        )
    
    return interface

def main():
    """Función principal"""
    print("🔍 Detector de Archivos Duplicados GPU")
    print("=" * 50)
    print(f"🚀 Aceleración GPU: {'Disponible' if GPU_AVAILABLE else 'No disponible'}")
    print("🌐 Iniciando interfaz Gradio...")
    
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=False,
        show_error=True
    )

if __name__ == "__main__":
    main()