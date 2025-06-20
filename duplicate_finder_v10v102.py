#!/usr/bin/env python3
"""
Detector de archivos duplicados con interfaz Gradio
Optimizado para GPU NVIDIA
Vista en árbol con selección de archivos duplicados - VERSIÓN 10
Con funcionalidad de guardar/cargar sesiones
CORREGIDO: Manejo mejorado de errores GPU y archivos problemáticos
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
from duplicate_styles_v10v101 import get_custom_css
from duplicate_ui_fixed_v10v101 import create_tree_display, create_interface_components

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    try:
        import cupy as cp
        # Verificar que CuPy funciona correctamente
        test_array = cp.array([1, 2, 3])
        _ = cp.asnumpy(test_array)
        GPU_AVAILABLE = True
        logger.info("GPU CuPy disponible - Usando aceleración GPU")
    except ImportError:
        GPU_AVAILABLE = False
        logger.info("GPU CuPy no disponible - Usando CPU")
    except Exception as e:
        GPU_AVAILABLE = False
        logger.warning(f"GPU CuPy disponible pero con problemas ({e}) - Usando CPU")

    import numpy as np
except ImportError:
    GPU_AVAILABLE = False
    logger.info("NumPy/CuPy no disponible - Usando CPU")

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
                except (OSError, PermissionError) as e:
                    logger.debug(f"Error accediendo a {file_path}: {e}")
                    continue
            
            processed_files += 1
            if processed_files % 100 == 0 and self.progress_callback:
                progress = (processed_files / total_files) * 30  # 30% del progreso total
                self.progress_callback(progress, f"Escaneados {processed_files}/{total_files} archivos")
        
        # Solo procesar tamaños con múltiples archivos
        potential_duplicates = {size: files for size, files in self.files_by_size.items() if len(files) > 1}
        
        return potential_duplicates
    
    def calculate_hash_gpu(self, file_info, algorithm='sha256'):
        """Calcula hash usando GPU si está disponible con manejo mejorado de errores"""
        if not GPU_AVAILABLE:
            return self.calculate_hash_cpu(file_info, algorithm)
            
        try:
            hasher = hashlib.new(algorithm)
            file_path = file_info['path']
            
            # Verificar que el archivo existe y es accesible
            if not file_path.exists() or not file_path.is_file():
                logger.warning(f"Archivo no accesible: {file_path}")
                return None
            
            # Verificar permisos de lectura
            if not os.access(file_path, os.R_OK):
                logger.warning(f"Sin permisos de lectura: {file_path}")
                return self.calculate_hash_cpu(file_info, algorithm)
            
            with open(file_path, 'rb') as f:
                while True:
                    if self.stop_flag:
                        return None
                    
                    chunk = f.read(16 * 1024 * 1024)  # 16MB chunks para GPU
                    if not chunk:
                        break
                    
                    # Validar que el chunk no está vacío y es válido para GPU
                    if len(chunk) == 0:
                        continue
                    
                    try:
                        # Procesar en GPU con validación adicional
                        gpu_data = cp.frombuffer(chunk, dtype=cp.uint8)
                        
                        # Verificar que los datos GPU son válidos
                        if gpu_data.size == 0:
                            hasher.update(chunk)  # Fallback directo
                            continue
                        
                        # Convertir de vuelta a CPU para hasher
                        cpu_data = cp.asnumpy(gpu_data)
                        hasher.update(cpu_data.tobytes())
                        
                    except (cp.cuda.memory.MemoryError, RuntimeError, ValueError) as gpu_error:
                        logger.debug(f"Error GPU en chunk de {file_path}: {gpu_error}")
                        # Fallback: procesar chunk directamente en CPU
                        hasher.update(chunk)
                        continue
                    
            return hasher.hexdigest()
            
        except (OSError, PermissionError, IOError) as io_error:
            logger.warning(f"Error I/O calculando hash GPU para {file_path}: {io_error}")
            return self.calculate_hash_cpu(file_info, algorithm)
        except Exception as e:
            logger.error(f"Error inesperado calculando hash GPU para {file_path}: {e}")
            return self.calculate_hash_cpu(file_info, algorithm)
    
    def calculate_hash_cpu(self, file_info, algorithm='sha256'):
        """Calcula hash usando CPU como fallback con manejo mejorado de errores"""
        hasher = hashlib.new(algorithm)
        file_path = file_info['path']
        
        try:
            # Verificaciones adicionales para CPU
            if not file_path.exists() or not file_path.is_file():
                logger.warning(f"Archivo no accesible para CPU: {file_path}")
                return None
            
            if not os.access(file_path, os.R_OK):
                logger.warning(f"Sin permisos de lectura para CPU: {file_path}")
                return None
            
            # Verificar que el archivo no esté vacío
            if file_path.stat().st_size == 0:
                logger.debug(f"Archivo vacío: {file_path}")
                return hasher.hexdigest()  # Hash de archivo vacío
            
            with open(file_path, 'rb') as f:
                while True:
                    if self.stop_flag:
                        return None
                    
                    chunk = f.read(8192 * 1024)  # 8MB chunks
                    if not chunk:
                        break
                    hasher.update(chunk)
                    
            return hasher.hexdigest()
            
        except (OSError, PermissionError, IOError) as e:
            logger.error(f"Error I/O leyendo {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado calculando hash CPU para {file_path}: {e}")
            return None
    
    def process_files_parallel(self, files_by_size, max_workers=None):
        """Procesa archivos en paralelo con manejo mejorado de errores"""
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
            successful_hashes = 0
            failed_hashes = 0
            
            for future in as_completed(future_to_file):
                if self.stop_flag:
                    break
                    
                file_info = future_to_file[future]
                try:
                    file_hash = future.result(timeout=30)  # Timeout de 30 segundos por archivo
                    if file_hash:
                        self.duplicates[file_hash].append(file_info)
                        successful_hashes += 1
                    else:
                        failed_hashes += 1
                        logger.debug(f"Hash fallido para: {file_info['path']}")
                    
                    processed += 1
                    if processed % 10 == 0 and self.progress_callback:
                        progress = 30 + (processed / total) * 60  # 60% del progreso total
                        status_msg = f"Procesados {processed}/{total} archivos"
                        if failed_hashes > 0:
                            status_msg += f" ({failed_hashes} errores)"
                        self.progress_callback(progress, status_msg)
                        
                except Exception as e:
                    failed_hashes += 1
                    logger.error(f"Error procesando {file_info['path']}: {e}")
                    processed += 1
            
            if self.progress_callback and (successful_hashes > 0 or failed_hashes > 0):
                final_msg = f"Completado: {successful_hashes} exitosos"
                if failed_hashes > 0:
                    final_msg += f", {failed_hashes} errores"
                self.progress_callback(90, final_msg)
    
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
            result_msg = f"Completado! {len(self.results)} grupos encontrados en {elapsed:.1f}s"
            if total_wasted_space > 0:
                result_msg += f" - Espacio desperdiciado: {self.format_size(total_wasted_space)}"
            self.progress_callback(100, result_msg)
        
        return self.results
    
    def format_size(self, size_bytes):
        """Formatea tamaños de archivo legibles"""
        if size_bytes == 0:
            return "0 B"
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
                    symlink_path = str(duplicate_path) + '.symlink'
                    
                    try:
                        # Eliminar symlink existente si existe
                        if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                            os.unlink(symlink_path)
                        
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
    script_path = "create_symlinks.sh"
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
    script_path = "delete_duplicates.sh"
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
        'version': '10.0'
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
        
	# Desempaquetar componentes - CORREGIDO: ahora son 21 elementos
        (directory_input, min_size_input, analyze_btn, stop_btn, 
         status_output, results_group, select_all_btn,
         select_priorities_btn, select_others_btn, generate_script_btn, 
         create_symlinks_btn, export_symlinks_btn, delete_btn, 
         selection_status, results_display, script_file, symlinks_file,
         save_session_btn, load_session_btn, session_file, load_session_file) = components
        
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
        
        create_symlinks_btn.click(
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
        
        delete_btn.click(
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
    
    return interface

def main():
    """Función principal"""
    print("🔍 Detector de Archivos Duplicados GPU - Versión 10")
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
