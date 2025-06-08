#!/usr/bin/env python3
"""
Detector de archivos duplicados con interfaz Gradio
Optimizado para GPU NVIDIA
Vista en árbol con selección de archivos duplicados - VERSIÓN 9.6
Con funcionalidad de guardar/cargar sesiones
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

# Importar módulos separados
from duplicate_styles import get_custom_css
from duplicate_ui_fixed import create_tree_display, create_interface_components

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
                
            if file_path.is_file() and not file_path.is_symlink():
                try:
                    # For regular files, stat() follows symlinks by default.
                    # However, we've excluded symlinks above.
                    # So, this will only be called on actual files.
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
                
            # Ordenar por fecha de modificación (más antiguo primero)
            files.sort(key=lambda x: x['mtime'], reverse=False)
            
            size = files[0]['size']
            wasted_space = size * (len(files) - 1)
            total_wasted_space += wasted_space
            
            # Determinar archivo prioritario (más reciente)
            priority_file = files[0]
            
            group_data = {
                'group_id': group_id,
                'hash': file_hash,
                'size': size,
                'size_readable': self.format_size(size),
                'wasted_space': wasted_space,
                'wasted_space_readable': self.format_size(wasted_space),
                'priority_file': priority_file,
                'duplicate_files': files[1:],  # Archivos duplicados (sin el prioritario)
                'group_selected': False  # Por defecto no seleccionado
            }
            
            self.results.append(group_data)
            group_id += 1
        
        elapsed = time.time() - start_time
        
        if self.progress_callback:
            self.progress_callback(100, f"Completado! {len(self.results)} grupos encontrados en {elapsed:.1f}s")
        
        return self.results
    
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
group_selections = {}  # Para rastrear selecciones de grupos
individual_selections = {}  # Para rastrear selecciones individuales
sort_order_descending = True  # Para ordenar por tamaño
sort_name_order_descending = True # Para ordenar por nombre de grupo

def update_progress(progress, message):
    """Actualiza el progreso en la interfaz"""
    return gr.update(value=progress, label=message, visible=True)

def analyze_directory(directory, min_size_mb, progress=gr.Progress()):
    """Analiza directorio y retorna resultados"""
    global current_results, group_selections, individual_selections
    current_results = []
    group_selections = {}
    individual_selections = {}
    
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
        
        # Inicializar selecciones de grupos (todos seleccionados por defecto)
        for group in current_results:
            group_id = group['group_id']
            group_selections[group_id] = True
            individual_selections[group_id] = {
                'priority': False,  # Archivos prioritarios NO seleccionados por defecto
                'duplicates': [True] * len(group['duplicate_files'])  # Duplicados SÍ seleccionados
            }
        
        tree_display = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        
        return "✅ Análisis completado", tree_display, gr.update(visible=True)
        
    except Exception as e:
        logger.error(f"Error en análisis: {e}")
        return f"❌ Error durante el análisis: {str(e)}", gr.update(visible=False), gr.update(visible=False)

def stop_analysis():
    """Detiene el análisis en curso"""
    finder.stop_analysis()
    return "⏹️ Análisis detenido"

def toggle_all_groups():
    """Toggle para seleccionar/deseleccionar todos los grupos"""
    global group_selections
    
    # Determinar si la mayoría están seleccionados
    selected_count = sum(1 for selected in group_selections.values() if selected)
    total_count = len(group_selections)
    
    # Si más del 50% están seleccionados, deseleccionar todos. Si no, seleccionar todos
    new_state = selected_count <= total_count / 2
    
    for group in current_results:
        group_selections[group['group_id']] = new_state
    
    tree_display = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
    selected_files = get_selected_files_count()
    
    action = "seleccionados" if new_state else "deseleccionados"
    return tree_display, f"✅ Todos los grupos {action} ({selected_files} archivos para eliminar)"

def toggle_all_priorities():
    """Toggle para seleccionar/deseleccionar todos los archivos prioritarios"""
    global individual_selections
    
    # Contar cuántos prioritarios están seleccionados
    selected_priorities = sum(1 for group_id in individual_selections 
                            if individual_selections[group_id]['priority'])
    total_priorities = len(individual_selections)
    
    # Toggle basado en el estado actual
    new_state = selected_priorities <= total_priorities / 2
    
    for group_id in individual_selections:
        individual_selections[group_id]['priority'] = new_state
    
    tree_display = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
    action = "seleccionados" if new_state else "deseleccionados"
    return tree_display, f"✅ Archivos guardables {action}"

def toggle_all_others():
    """Toggle para seleccionar/deseleccionar todos los archivos duplicados (otros)"""
    global individual_selections
    
    # Contar cuántos duplicados están seleccionados
    selected_duplicates = 0
    total_duplicates = 0
    
    for group_id in individual_selections:
        duplicates = individual_selections[group_id]['duplicates']
        selected_duplicates += sum(duplicates)
        total_duplicates += len(duplicates)
    
    # Toggle basado en el estado actual
    new_state = selected_duplicates <= total_duplicates / 2
    
    for group_id in individual_selections:
        individual_selections[group_id]['duplicates'] = [new_state] * len(individual_selections[group_id]['duplicates'])
    
    tree_display = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
    action = "seleccionados" if new_state else "deseleccionados"
    return tree_display, f"✅ Archivos duplicados {action}"

def get_selected_files_count():
    """Cuenta archivos seleccionados para eliminación"""
    count = 0
    for group in current_results:
        group_id = group['group_id']
        if group_selections.get(group_id, False):
            # Contar duplicados seleccionados
            if group_id in individual_selections:
                count += sum(individual_selections[group_id]['duplicates'])
            else:
                count += len(group['duplicate_files'])
    return count

def get_selected_files_list():
    """Obtiene lista de archivos seleccionados para eliminación"""
    selected_files = []
    for group in current_results:
        group_id = group['group_id']
        if group_selections.get(group_id, False):
            # Añadir archivos prioritarios si están seleccionados
            if group_id in individual_selections and individual_selections[group_id]['priority']:
                selected_files.append(group['priority_file']['path'])
            
            # Añadir duplicados seleccionados
            if group_id in individual_selections:
                for i, is_selected in enumerate(individual_selections[group_id]['duplicates']):
                    if is_selected and i < len(group['duplicate_files']):
                        selected_files.append(group['duplicate_files'][i]['path'])
            else:
                # Fallback: todos los duplicados
                for dup_file in group['duplicate_files']:
                    selected_files.append(dup_file['path'])
                    
    return selected_files

def create_symlinks():
    """Crea symlinks para archivos que serán eliminados"""
    created_symlinks = []
    errors = []
    
    for group in current_results:
        group_id = group['group_id']
        if not group_selections.get(group_id, False):
            continue
            
        priority_file = group['priority_file']['path']
        
        # Crear symlinks para duplicados que serán eliminados
        if group_id in individual_selections:
            for i, is_selected in enumerate(individual_selections[group_id]['duplicates']):
                if is_selected and i < len(group['duplicate_files']):
                    duplicate_path = group['duplicate_files'][i]['path']
                    symlink_path = str(duplicate_path)  # Use original filename for symlink
                    
                    try:
                        # Eliminar archivo o symlink existente antes de crear el nuevo symlink
                        if os.path.lexists(symlink_path): # Use lexists to also find broken symlinks
                            os.remove(symlink_path)
                        
                        # Crear el symlink
                        os.symlink(priority_file, symlink_path)
                        created_symlinks.append({
                            'symlink': symlink_path,
                            'target': priority_file,
                            'original': duplicate_path
                        })
                    except Exception as e:
                        errors.append(f"{duplicate_path}: {str(e)}")
    
    result = f"✅ Creados {len(created_symlinks)} symlinks"
    
    if errors:
        result += f"\n❌ Errores:\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            result += f"\n... y {len(errors) - 5} errores más"
    
    return result

def generate_symlinks_script():
    """Genera script para crear symlinks"""
    symlinks_data = []
    
    for group in current_results:
        group_id = group['group_id']
        if not group_selections.get(group_id, False):
            continue
            
        priority_file = group['priority_file']['path']
        
        # Generar datos para duplicados que serán eliminados
        if group_id in individual_selections:
            for i, is_selected in enumerate(individual_selections[group_id]['duplicates']):
                if is_selected and i < len(group['duplicate_files']):
                    duplicate_path = group['duplicate_files'][i]['path']
                    symlink_path = str(duplicate_path) + '.symlink'
                    
                    symlinks_data.append({
                        'symlink': symlink_path,
                        'target': priority_file,
                        'original': duplicate_path
                    })
    
    if not symlinks_data:
        return "❌ No hay archivos seleccionados para crear symlinks", None
    
    script_content = f"""#!/bin/bash
# Script generado automáticamente para crear symlinks de archivos duplicados
# Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Este script crea symlinks antes de eliminar los archivos duplicados

echo "Creando {len(symlinks_data)} symlinks..."

"""
    
    for i, link_data in enumerate(symlinks_data, 1):
        script_content += f'echo "({i}/{len(symlinks_data)}) Creando symlink: {link_data["symlink"]}"\n'
        script_content += f'# Original: {link_data["original"]} -> Target: {link_data["target"]}"\n'
        script_content += f'rm -f "{link_data["symlink"]}" 2>/dev/null\n'  # Eliminar symlink existente
        script_content += f'ln -s "{link_data["target"]}" "{link_data["symlink"]}"\n'
        script_content += f'if [ $? -eq 0 ]; then\n'
        script_content += f'    echo "✓ Symlink creado exitosamente"\n'
        script_content += f'else\n'
        script_content += f'    echo "✗ Error al crear symlink"\n'
        script_content += f'fi\n\n'
    
    script_content += f'''echo "Creación de symlinks completada"
echo "Symlinks creados: {len(symlinks_data)}"
echo ""
echo "Los symlinks apuntan a los archivos que se mantendrán."
echo "Después de eliminar los duplicados, los symlinks seguirán funcionando."
'''
    
    # Guardar script
    script_path = f"create_symlinks_{datetime.now().strftime('%Y%m%d')}.sh"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    os.chmod(script_path, 0o755)  # Hacer ejecutable
    
    return f"✅ Script de symlinks generado: {script_path} ({len(symlinks_data)} symlinks)", script_path

def generate_delete_script():
    """Genera script de eliminación"""
    selected_files = get_selected_files_list()
    
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
    script_path = f"deleteduplicates_{datetime.now().strftime('%Y%m%d')}.sh"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    os.chmod(script_path, 0o755)  # Hacer ejecutable
    
    return f"✅ Script generado: {script_path} ({len(selected_files)} archivos)", script_path

def delete_selected_files():
    """Elimina archivos seleccionados directamente"""
    selected_files = get_selected_files_list()
    
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
    
    return result

def save_session():
    """Guarda la sesión actual con resultados y selecciones"""
    if not current_results:
        return "❌ No hay resultados para guardar", None
    
    session_data = {
        'timestamp': datetime.now().isoformat(),
        'results': current_results,
        'group_selections': group_selections,
        'individual_selections': individual_selections,
        'version': '9.6'
    }
    
    # Convertir Path objects a strings para JSON
    for group in session_data['results']:
        group['priority_file']['path'] = str(group['priority_file']['path'])
        for dup_file in group['duplicate_files']:
            dup_file['path'] = str(dup_file['path'])
    
    session_filename = f"duplicate_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(session_filename, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        return f"✅ Sesión guardada: {session_filename}", session_filename
    except Exception as e:
        return f"❌ Error guardando sesión: {str(e)}", None

def load_session(session_file):
    """Carga una sesión previamente guardada"""
    global current_results, group_selections, individual_selections
    
    if not session_file:
        return "❌ No se ha seleccionado archivo", gr.update(visible=False), gr.update(visible=False)
    
    try:
        with open(session_file.name, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Restaurar datos
        current_results = session_data['results']
        group_selections = session_data['group_selections']
        individual_selections = session_data['individual_selections']
        
        # Convertir strings de vuelta a Path objects
        for group in current_results:
            group['priority_file']['path'] = Path(group['priority_file']['path'])
            for dup_file in group['duplicate_files']:
                dup_file['path'] = Path(dup_file['path'])
        
        # Recrear display
        tree_display = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        
        timestamp = session_data.get('timestamp', 'Desconocido')
        return f"✅ Sesión cargada (guardada: {timestamp})", tree_display, gr.update(visible=True)
        
    except Exception as e:
        logger.error(f"Error cargando sesión: {e}")
        return f"❌ Error cargando sesión: {str(e)}", gr.update(visible=False), gr.update(visible=False)

def sort_results_by_size():
    """Ordena los resultados por tamaño y actualiza la vista."""
    global current_results, sort_order_descending, group_selections, individual_selections, finder, GPU_AVAILABLE

    if not current_results:
        return gr.update(value="No hay resultados para ordenar."), "No hay resultados para ordenar."

    current_results.sort(key=lambda x: x['size'], reverse=sort_order_descending)

    # Actualizar los group_id para que coincidan con el nuevo orden
    # Esto es crucial si el group_id se usa como índice directo en algún lado después del sort
    # Sin embargo, group_selections and individual_selections son diccionarios usando group_id como clave,
    # así que el group_id original debe preservarse o las selecciones se desajustarán.
    # Por ahora, asumimos que el group_id es un identificador único y no un índice de lista.
    # Si el group_id fuera un índice, necesitaríamos remapearlos después de ordenar,
    # o asegurar que create_tree_display maneje los group_id originales correctamente.
    # La implementación actual de create_tree_display usa group['group_id'] directamente.

    sort_order_descending = not sort_order_descending  # Invertir para el próximo clic

    new_html_content = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)

    order_message = "descendente" if not sort_order_descending else "ascendente" # Mensaje dice el orden que se aplicó
    status_message = f"Resultados ordenados por tamaño ({order_message})."

    return new_html_content, status_message

def sort_results_by_name():
    """Ordena los resultados por nombre de grupo (nombre del archivo prioritario) y actualiza la vista."""
    global current_results, sort_name_order_descending, group_selections, individual_selections, finder, GPU_AVAILABLE
    if not current_results:
        return gr.update(value="No hay resultados para ordenar."), "No hay resultados para ordenar."

    # Sort by the name of the priority file
    current_results.sort(key=lambda x: Path(x['priority_file']['path']).name.lower(), reverse=sort_name_order_descending)

    # Toggle for next click before generating status message
    order_applied_message = 'descendente' if sort_name_order_descending else 'ascendente'
    sort_name_order_descending = not sort_name_order_descending

    status_message = f"Resultados ordenados por nombre de grupo ({order_applied_message})."

    new_html_content = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
    return new_html_content, status_message

def update_priority_selection_py(group_id_str: str, is_checked_str: str):
    global individual_selections, current_results, group_selections, finder, GPU_AVAILABLE
    try:
        group_id = int(group_id_str)
        is_checked = is_checked_str.lower() == 'true'

        if group_id in individual_selections:
            individual_selections[group_id]['priority'] = is_checked
            logger.info(f"Updated priority selection for group {group_id} to {is_checked}")
        else:
            # This case might happen if individual_selections is not fully populated when results are first loaded.
            # Or if group_id is somehow incorrect.
            # Initialize if missing:
            individual_selections[group_id] = {'priority': is_checked, 'duplicates': []}
            # We might need to know the number of duplicate files to initialize 'duplicates' correctly,
            # but for priority selection, this might be acceptable.
            # A more robust way would be to ensure individual_selections is always complete.
            logger.warning(f"Group ID {group_id} not initially in individual_selections. Initialized for priority update.")

        tree_html = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        selected_files_count = get_selected_files_count()
        selection_summary = f"{selected_files_count} archivos seleccionados para eliminar."

        return tree_html, selection_summary
    except Exception as e:
        logger.error(f"Error in update_priority_selection_py: {e}")
        tree_html = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        return tree_html, str(e)

def update_duplicate_selection_py(group_id_str: str, file_idx_str: str, is_checked_str: str):
    global individual_selections, current_results, group_selections, finder, GPU_AVAILABLE
    try:
        group_id = int(group_id_str)
        file_idx = int(file_idx_str)
        is_checked = is_checked_str.lower() == 'true'

        if group_id in individual_selections:
            if file_idx < len(individual_selections[group_id]['duplicates']):
                individual_selections[group_id]['duplicates'][file_idx] = is_checked
                logger.info(f"Updated duplicate selection for group {group_id}, index {file_idx} to {is_checked}")
            else:
                logger.warning(f"File index {file_idx} out of bounds for group ID {group_id} duplicate update.")
        else:
            # Similar to priority, initialize if group_id is missing.
            # This is less likely for duplicates as it implies a structural issue.
            logger.warning(f"Group ID {group_id} not found in individual_selections for duplicate update.")
            # We cannot safely initialize 'duplicates' here without knowing its correct length.

        tree_html = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        selected_files_count = get_selected_files_count()
        selection_summary = f"{selected_files_count} archivos seleccionados para eliminar."
        return tree_html, selection_summary
    except Exception as e:
        logger.error(f"Error in update_duplicate_selection_py: {e}")
        tree_html = create_tree_display(current_results, group_selections, individual_selections, finder, GPU_AVAILABLE)
        return tree_html, str(e)

def create_interface():
    """Crea la interfaz Gradio"""
    custom_css = get_custom_css()
    
    with gr.Blocks(
        title="🔍 Detector de Archivos Duplicados GPU",
        theme=gr.themes.Base(),
        css=custom_css
    ) as interface:
        
        # Usar los componentes del módulo UI
        components = create_interface_components()
        
        # Desempaquetar componentes - Actualizado para la nueva estructura (31 + 1 new hidden symlink button = 32 componentes)
        (directory_input, min_size_input, analyze_btn, stop_btn, 
         status_output, results_group, select_all_btn,
         select_priorities_btn, select_others_btn,
         generate_script_btn,
         create_symlinks_btn, # This is the new visible button (confirm_symlink_button_ui)
         confirmed_create_symlinks_btn, # This is the new hidden button (hidden_actual_symlink_trigger)
         export_symlinks_btn,
         delete_btn, selection_status, results_display, script_file,
         symlinks_file, save_session_btn, load_session_btn, session_file, load_session_file,
         confirmed_delete_btn,
         name_sort_actual_button, size_sort_actual_button,
         priority_update_group_id, priority_update_is_checked, trigger_priority_update_btn,
         duplicate_update_group_id, duplicate_update_file_idx, duplicate_update_is_checked, trigger_duplicate_update_btn
         ) = components
        
        # Event handlers
        analyze_btn.click(
            fn=analyze_directory,
            inputs=[directory_input, min_size_input],
            outputs=[status_output, results_display, results_group],
            show_progress=True
        )
        
        stop_btn.click(
            fn=stop_analysis,
            outputs=[status_output]
        )
        
        select_all_btn.click(
            fn=toggle_all_groups,
            outputs=[results_display, selection_status]
        )
        
        select_priorities_btn.click(
            fn=toggle_all_priorities,
            outputs=[results_display, selection_status]
        )
        
        select_others_btn.click(
            fn=toggle_all_others,
            outputs=[results_display, selection_status]
        )
        
        generate_script_btn.click(
            fn=generate_delete_script,
            outputs=[selection_status, script_file]
        ).then(
            lambda: gr.update(visible=True),
            outputs=[script_file]
        )
        
        # The visible create_symlinks_btn (confirm_symlink_button_ui) now only triggers JS.
        # The Python click handler is moved to the new hidden button:
        confirmed_create_symlinks_btn.click(
            fn=create_symlinks,
            outputs=[selection_status]
        )
        
        export_symlinks_btn.click(
            fn=generate_symlinks_script,
            outputs=[selection_status, symlinks_file]
        ).then(
            lambda: gr.update(visible=True),
            outputs=[symlinks_file]
        )
        
        # Original delete_btn click handler is removed.
        # The visible delete_btn now triggers JS confirmation first.

        confirmed_delete_btn.click( # This is the new hidden button
            fn=delete_selected_files,
            outputs=[selection_status]
        )
        
        # Nuevos event handlers para sesiones - CORREGIDO
        save_session_btn.click(
            fn=save_session,
            outputs=[selection_status, session_file]
        ).then(
            lambda: gr.update(visible=True),
            outputs=[session_file]
        )
        
        load_session_btn.click(
            fn=lambda: gr.update(visible=True),
            outputs=[load_session_file]
        )
        
        load_session_file.upload(
            fn=load_session,
            inputs=[load_session_file],
            outputs=[status_output, results_display, results_group]
        )

        # Removed click handlers for sort_by_size_btn, size_sort_header_trigger_btn, and name_sort_header_trigger_btn

        # Add new click handlers for the actual header buttons
        name_sort_actual_button.click(
            fn=sort_results_by_name,
            outputs=[results_display, status_output]
        )
        size_sort_actual_button.click(
            fn=sort_results_by_size,
            outputs=[results_display, status_output]
        )

        # Click handlers for individual file selection updates
        trigger_priority_update_btn.click(
            fn=update_priority_selection_py,
            inputs=[priority_update_group_id, priority_update_is_checked],
            outputs=[results_display, selection_status]
        )
        trigger_duplicate_update_btn.click(
            fn=update_duplicate_selection_py,
            inputs=[duplicate_update_group_id, duplicate_update_file_idx, duplicate_update_is_checked],
            outputs=[results_display, selection_status]
        )
    
    return interface

def main():
    """Función principal"""
    print("🔍 Detector de Archivos Duplicados GPU - Versión 9.6")
    print("=" * 60)
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
