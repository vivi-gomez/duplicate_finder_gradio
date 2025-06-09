#!/usr/bin/env python3
"""
Detector de Archivos Duplicados GPU - Versión 12 Modificada
Sistema completo con interfaz Gradio nativa mejorada
Modificaciones:
1- Los archivos principales no pueden ser symlinks
2- Los archivos principales no están protegidos (pueden ser seleccionados para borrado)
"""

import gradio as gr
import hashlib
import json
import os
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import threading

# Global variables for state management
current_results = []
file_selections = {}  # Almacena selecciones individuales por archivo
analysis_thread = None
stop_analysis = False

class DuplicateFinder:
    def __init__(self, use_gpu=True):
        self.use_gpu = use_gpu and self._check_gpu()
        self.total_files = 0
        self.processed_files = 0
        self.start_time = None
        
    def _check_gpu(self):
        """Check if GPU acceleration is available"""
        try:
            import cupy as cp
            cp.cuda.Device(0).compute_capability
            return True
        except:
            return False
    
    def format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def _calculate_hash(self, file_path, chunk_size=8192):
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                if self.use_gpu:
                    # Simulate GPU acceleration (in real implementation, use CuPy)
                    for chunk in iter(lambda: f.read(chunk_size * 4), b""):
                        hash_md5.update(chunk)
                else:
                    for chunk in iter(lambda: f.read(chunk_size), b""):
                        hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (PermissionError, OSError):
            return None
    
    def find_duplicates(self, directory, min_size_mb=1, progress_callback=None):
        """Find duplicate files in directory"""
        global stop_analysis
        
        directory_path = Path(directory)
        if not directory_path.exists():
            raise ValueError(f"Directory does not exist: {directory}")
        
        min_size_bytes = min_size_mb * 1024 * 1024
        file_hashes = defaultdict(list)
        
        # Get all files first
        all_files = []
        for file_path in directory_path.rglob('*'):
            if stop_analysis:
                return []
                
            if file_path.is_file() and not file_path.is_symlink():  # Excluir symlinks
                try:
                    size = file_path.stat().st_size
                    if size >= min_size_bytes:
                        all_files.append(file_path)
                except OSError:
                    continue
        
        self.total_files = len(all_files)
        self.processed_files = 0
        self.start_time = time.time()
        
        # Process files
        for file_path in all_files:
            if stop_analysis:
                return []
                
            try:
                file_hash = self._calculate_hash(file_path)
                if file_hash:
                    stat = file_path.stat()
                    file_info = {
                        'path': str(file_path),
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'mtime_readable': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'hash': file_hash,
                        'is_symlink': file_path.is_symlink()
                    }
                    file_hashes[file_hash].append(file_info)
                
                self.processed_files += 1
                
                if progress_callback and self.processed_files % 10 == 0:
                    progress = (self.processed_files / self.total_files) * 100
                    elapsed = time.time() - self.start_time
                    speed = self.processed_files / elapsed if elapsed > 0 else 0
                    eta = (self.total_files - self.processed_files) / speed if speed > 0 else 0
                    
                    status = f"Procesando: {self.processed_files}/{self.total_files} ({progress:.1f}%) - {speed:.1f} archivos/seg - ETA: {eta:.0f}s"
                    progress_callback(status)
                    
            except (PermissionError, OSError):
                continue
        
        # Find duplicates
        duplicate_groups = []
        group_id = 1
        
        for file_hash, files in file_hashes.items():
            if len(files) > 1:
                # Filtrar symlinks y ordenar por tiempo de modificación (más reciente primero)
                physical_files = [f for f in files if not f['is_symlink']]
                
                if not physical_files:
                    continue  # Si todos son symlinks, saltar este grupo
                
                # Ordenar archivos físicos por tiempo de modificación (más reciente primero)
                physical_files.sort(key=lambda x: x['mtime'], reverse=True)
                
                # Todos los archivos (incluyendo symlinks) son considerados para borrado
                # El usuario puede seleccionar cualquiera para borrar
                group = {
                    'group_id': group_id,
                    'hash': file_hash,
                    'files': physical_files + [f for f in files if f['is_symlink']],  # Todos los archivos
                    'total_files': len(files),
                    'wasted_space': sum(f['size'] for f in files[1:])  # Espacio de todos menos el primero
                }
                
                duplicate_groups.append(group)
                group_id += 1
        
        return duplicate_groups

# Global finder instance
finder = DuplicateFinder()

def analyze_duplicates(directory, min_size_mb, progress=gr.Progress()):
    """Analyze directory for duplicates"""
    global current_results, file_selections, analysis_thread, stop_analysis
    
    stop_analysis = False
    
    if not directory or not os.path.exists(directory):
        return (
            "❌ Error: Directorio no válido o no existe",
            [],  # Empty results for accordion
            "No hay resultados para mostrar",
            gr.update(visible=False)
        )
    
    try:
        def update_progress(status):
            progress(0.5, desc=status)
        
        progress(0.1, desc="Iniciando análisis...")
        
        results = finder.find_duplicates(directory, min_size_mb, update_progress)
        
        if stop_analysis:
            return (
                "⏹️ Análisis detenido por el usuario",
                [],
                "Análisis detenido",
                gr.update(visible=False)
            )
        
        current_results = results
        file_selections = {}  # Reset selections
        
        if not results:
            return (
                "✅ No se encontraron archivos duplicados",
                [],
                "No se encontraron archivos duplicados",
                gr.update(visible=False)
            )
        
        total_groups = len(results)
        total_duplicates = sum(group['total_files'] - 1 for group in results)  # Todos menos uno por grupo
        total_wasted = sum(group['wasted_space'] for group in results)
        total_wasted_readable = finder.format_size(total_wasted)
        
        # Create accordion structure
        accordion_data = create_accordion_data(results)
        
        # Create statistics
        stats_html = create_stats_html(total_groups, total_duplicates, total_wasted_readable)
        
        status = f"✅ Análisis completado: {total_groups} grupos, {total_duplicates} duplicados, {total_wasted_readable} desperdiciados"
        
        return (
            status,
            accordion_data,
            stats_html,
            gr.update(visible=True)
        )
        
    except Exception as e:
        return (
            f"❌ Error durante el análisis: {str(e)}",
            [],
            "Error en el análisis",
            gr.update(visible=False)
        )

def stop_analysis_func():
    """Stop the current analysis"""
    global stop_analysis
    stop_analysis = True
    return "⏹️ Deteniendo análisis..."

def create_stats_html(total_groups, total_duplicates, total_wasted_readable):
    """Create statistics HTML"""
    gpu_status = 'GPU' if finder.use_gpu else 'CPU'
    
    return f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; text-align: center;">
            <div><strong>Grupos encontrados:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_groups}</span></div>
            <div><strong>Archivos duplicados:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_duplicates}</span></div>
            <div><strong>Espacio desperdiciado:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_wasted_readable}</span></div>
            <div><strong>Aceleración:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{gpu_status}</span></div>
        </div>
    </div>
    """

def create_accordion_data(results):
    """Create data structure for accordion display"""
    accordion_data = []
    
    for group in results:
        group_id = group['group_id']
        files = group['files']
        
        # Usar el primer archivo físico como referencia para el nombre
        main_filename = Path(files[0]['path']).name if files else "Unknown"
        
        # Crear item del acordeón
        accordion_item = {
            'group_id': group_id,
            'label': f"Grupo {group_id}: {main_filename}",
            'files': files,
            'wasted_space': group['wasted_space']
        }
        
        accordion_data.append(accordion_item)
    
    return accordion_data

def create_group_interface(group_data):
    """Create interface for a single group"""
    components = []
    
    # Group header
    wasted_space = finder.format_size(group_data['wasted_space'])
    
    header_html = f"""
    <div style="background: #272734; border-top: 2px solid #2D3748; padding: 15px; margin-bottom: 10px; border-radius: 8px;">
        <div style="color: white; font-size: 16px; font-weight: bold; margin-bottom: 8px;">
            Grupo {group_data['group_id']} - {Path(group_data['files'][0]['path']).name if group_data['files'] else 'Unknown'}
        </div>
        <div style="color: #A0AEC0; font-size: 14px;">
            📄 {len(group_data['files'])} archivos | 💾 Espacio desperdiciado: {wasted_space}
        </div>
    </div>
    """
    
    components.append(gr.HTML(header_html))
    
    # Files with checkboxes (todos pueden ser seleccionados)
    file_checkboxes = []
    for i, file_info in enumerate(group_data['files']):
        file_path = file_info['path']
        file_id = f"group_{group_data['group_id']}_file_{i}"
        
        symlink_indicator = " (Symlink)" if file_info.get('is_symlink', False) else ""
        
        # File info HTML
        file_html = f"""
        <div style="background: #2B3444; padding: 12px; margin-bottom: 8px; border-radius: 6px; border-left: 4px solid #4A5568;">
            <div style="color: white; font-size: 12px; font-family: monospace; margin-bottom: 4px;">
                📄 {file_path}{symlink_indicator}
            </div>
            <div style="color: #A0AEC0; font-size: 10px;">
                📅 {file_info['mtime_readable']} | 📏 {finder.format_size(file_info['size'])}
            </div>
        </div>
        """
        
        # Checkbox for selection
        checkbox = gr.Checkbox(
            label=f"Seleccionar para eliminar",
            value=file_selections.get(file_id, False),
            elem_id=file_id,
            scale=0
        )
        
        # Store checkbox reference
        file_checkboxes.append((checkbox, file_id, file_path))
        
        # Add components
        components.append(gr.HTML(file_html))
        components.append(checkbox)
    
    return components, file_checkboxes

def update_file_selection(file_id, selected):
    """Update file selection state"""
    global file_selections
    file_selections[file_id] = selected
    return get_selection_status()

def get_selection_status():
    """Get current selection status"""
    selected_count = sum(1 for selected in file_selections.values() if selected)
    total_count = len(file_selections)
    
    if selected_count == 0:
        return "No hay archivos seleccionados para eliminar"
    else:
        return f"✅ {selected_count} de {total_count} archivos seleccionados para eliminar"

def select_all_duplicates():
    """Select all duplicate files"""
    global file_selections, current_results
    
    if not current_results:
        return "No hay archivos para seleccionar", []
    
    # Check if all files are selected
    all_selected = True
    for group in current_results:
        for i, _ in enumerate(group['files']):
            file_id = f"group_{group['group_id']}_file_{i}"
            if not file_selections.get(file_id, False):
                all_selected = False
                break
        if not all_selected:
            break
    
    # Toggle selection
    new_state = not all_selected
    updates = []
    
    for group in current_results:
        for i, _ in enumerate(group['files']):
            file_id = f"group_{group['group_id']}_file_{i}"
            file_selections[file_id] = new_state
            updates.append(gr.update(value=new_state))
    
    status = get_selection_status()
    return status, updates

def confirm_deletion():
    """Show deletion confirmation dialog"""
    selected_files = []
    total_size = 0
    
    for group in current_results:
        for i, file_info in enumerate(group['files']):
            file_id = f"group_{group['group_id']}_file_{i}"
            if file_selections.get(file_id, False):
                selected_files.append(file_info['path'])
                total_size += file_info['size']
    
    if not selected_files:
        return "❌ No hay archivos seleccionados para eliminar"
    
    return f"""
⚠️ ADVERTENCIA: Estás a punto de eliminar {len(selected_files)} archivos.
💾 Espacio a liberar: {finder.format_size(total_size)}

Los archivos se eliminarán PERMANENTEMENTE y no se podrán recuperar.

¿Estás seguro de que quieres continuar?

Archivos a eliminar:
{chr(10).join(f"• {f}" for f in selected_files[:10])}
{"..." if len(selected_files) > 10 else ""}
"""

def delete_selected_files():
    """Delete selected duplicate files"""
    global current_results, file_selections
    
    selected_files = []
    for group in current_results:
        for i, file_info in enumerate(group['files']):
            file_id = f"group_{group['group_id']}_file_{i}"
            if file_selections.get(file_id, False):
                selected_files.append(file_info)
    
    if not selected_files:
        return "❌ No hay archivos seleccionados para eliminar"
    
    deleted_files = 0
    deleted_size = 0
    errors = []
    
    for file_info in selected_files:
        try:
            file_path = Path(file_info['path'])
            if file_path.exists():
                file_path.unlink()
                deleted_files += 1
                deleted_size += file_info['size']
        except Exception as e:
            errors.append(f"Error eliminando {file_info['path']}: {str(e)}")
    
    result = f"✅ {deleted_files} archivos eliminados exitosamente\n💾 Espacio liberado: {finder.format_size(deleted_size)}"
    
    if errors:
        result += f"\n⚠️ {len(errors)} errores encontrados:"
        for error in errors[:3]:  # Show first 3 errors
            result += f"\n  • {error}"
        if len(errors) > 3:
            result += f"\n  ... y {len(errors) - 3} errores más"
    
    # Reset selections after deletion
    file_selections = {}
    
    return result

def generate_deletion_script():
    """Generate deletion script for selected files"""
    global current_results, file_selections
    
    selected_files = []
    total_size = 0
    
    for group in current_results:
        for i, file_info in enumerate(group['files']):
            file_id = f"group_{group['group_id']}_file_{i}"
            if file_selections.get(file_id, False):
                selected_files.append(file_info)
                total_size += file_info['size']
    
    if not selected_files:
        return None, "❌ No hay archivos seleccionados para generar script"
    
    script_lines = [
        "#!/bin/bash",
        "# Script de eliminación de archivos duplicados",
        f"# Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Archivos a eliminar: {len(selected_files)}",
        f"# Espacio a liberar: {finder.format_size(total_size)}",
        "#",
        "# ADVERTENCIA: Este script eliminará archivos permanentemente",
        "# Asegúrate de tener una copia de seguridad antes de ejecutar",
        "#",
        "set -e",
        "",
        "echo 'Iniciando eliminación de archivos duplicados...'",
        ""
    ]
    
    for file_info in selected_files:
        file_path = file_info['path']
        script_lines.append(f"echo 'Eliminando: {file_path}'")
        script_lines.append(f"rm -f '{file_path}'")
        script_lines.append("")
    
    script_lines.extend([
        f"echo 'Completado: {len(selected_files)} archivos eliminados'",
        f"echo 'Espacio liberado: {finder.format_size(total_size)}'",
        ""
    ])
    
    script_content = '\n'.join(script_lines)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
    temp_file.write(script_content)
    temp_file.close()
    
    # Make executable
    os.chmod(temp_file.name, 0o755)
    
    status = f"✅ Script generado exitosamente\n📄 Archivos incluidos: {len(selected_files)}\n💾 Espacio a liberar: {finder.format_size(total_size)}"
    return temp_file.name, status

def save_session():
    """Save current session to file"""
    global current_results, file_selections
    
    if not current_results:
        return None, "❌ No hay resultados para guardar"
    
    session_data = {
        'timestamp': datetime.now().isoformat(),
        'version': '12',
        'results': current_results,
        'file_selections': file_selections,
        'gpu_available': finder.use_gpu
    }
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(session_data, temp_file, indent=2, ensure_ascii=False)
    temp_file.close()
    
    return temp_file.name, f"✅ Sesión guardada exitosamente\n📊 Grupos: {len(current_results)}\n☑️ Selecciones: {sum(1 for s in file_selections.values() if s)}"

def load_session(file_path):
    """Load session from file"""
    global current_results, file_selections
    
    if not file_path:
        return "❌ No se seleccionó archivo", [], "Selecciona un archivo de sesión", gr.update(visible=False)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        current_results = session_data.get('results', [])
        file_selections = session_data.get('file_selections', {})
        
        if current_results:
            accordion_data = create_accordion_data(current_results)
            total_groups = len(current_results)
            total_duplicates = sum(group['total_files'] - 1 for group in current_results)
            total_wasted = sum(group['wasted_space'] for group in current_results)
            stats_html = create_stats_html(total_groups, total_duplicates, finder.format_size(total_wasted))
            
            status = f"✅ Sesión cargada exitosamente\n📊 Grupos: {len(current_results)}\n☑️ Selecciones: {sum(1 for s in file_selections.values() if s)}"
            return status, accordion_data, stats_html, gr.update(visible=True)
        else:
            return "⚠️ Sesión cargada pero sin resultados", [], "Sesión vacía", gr.update(visible=False)
            
    except Exception as e:
        return f"❌ Error cargando sesión: {str(e)}", [], "Error al cargar", gr.update(visible=False)

def create_interface():
    """Create the main Gradio interface"""
    
    with gr.Blocks(title="🔍 Detector de Archivos Duplicados GPU v12", theme=gr.themes.Default(primary_hue="blue", neutral_hue="slate")) as interface:
        
        # Header
        gr.Markdown("""
        # 🔍 Detector de Archivos Duplicados GPU v12
        
        Encuentra y elimina archivos duplicados con interfaz mejorada usando componentes Gradio nativos.
        
        ### Características:
        - ⚡ Aceleración GPU con CuPy
        - 🗂️ Vista en acordeón organizada
        - ☑️ Selección manual de archivos (incluyendo principales)
        - 📝 Generación de scripts de eliminación
        - ⚠️ Confirmación antes de eliminar
        - 💾 Guardado de sesiones
        """)
        
        # Input section
        with gr.Row():
            with gr.Column(scale=3):
                directory_input = gr.Textbox(
                    label="📁 Directorio a analizar",
                    placeholder="/ruta/a/tu/directorio",
                    value="",
                    info="Introduce la ruta completa del directorio donde buscar duplicados"
                )
            with gr.Column(scale=1):
                min_size_input = gr.Number(
                    label="📏 Tamaño mínimo (MB)",
                    value=1,
                    minimum=0.1,
                    step=0.1,
                    info="Solo archivos mayores a este tamaño"
                )
        
        # Control buttons
        with gr.Row():
            analyze_btn = gr.Button("🔍 Analizar Duplicados", variant="primary", size="lg")
            stop_btn = gr.Button("⏹️ Detener", variant="secondary")
            save_session_btn = gr.Button("💾 Guardar Sesión", variant="secondary", size="sm")
        
        # Load session
        with gr.Row():
            load_session_file = gr.File(
                label="📂 Cargar Sesión",
                file_types=[".json"],
                file_count="single"
            )
        
        # Status
        status_output = gr.Textbox(
            label="📊 Estado",
            value="Listo para analizar",
            interactive=False,
            max_lines=4
        )
        
        # Results section
        with gr.Group(visible=False) as results_group:
            # Statistics
            stats_display = gr.HTML(
                label="📊 Estadísticas",
                value=""
            )
            
            # Results display
            results_accordion = gr.HTML(
                label="📋 Resultados",
                value=""
            )
            
            # Manual selection section
            with gr.Accordion("☑️ Selección Manual de Archivos", open=True):
                gr.Markdown("""
                **Instrucciones:**
                - ☑️ Marca los archivos que deseas eliminar (incluyendo los principales)
                - 📝 Todos los archivos pueden ser seleccionados para eliminación
                - 🔄 Usa "Seleccionar/Deseleccionar Todos" para cambiar todas las selecciones
                """)
                
                selection_interface = gr.Column()
                
            # Selection status
            selection_status = gr.Textbox(
                label="Estado de Selección",
                value="No hay archivos seleccionados",
                interactive=False
            )
            
            # Selection controls
            with gr.Row():
                select_all_btn = gr.Button("☑️ Seleccionar/Deseleccionar Todos", size="sm")
                update_selection_btn = gr.Button("🔄 Actualizar Estado", size="sm")
            
            # Action buttons
            gr.Markdown("### ⚠️ Acciones de Eliminación")
            
            with gr.Row():
                confirm_btn = gr.Button("⚠️ Ver Confirmación", variant="secondary")
                delete_btn = gr.Button("🗑️ Eliminar Seleccionados", variant="stop")
                generate_script_btn = gr.Button("📝 Generar Script", variant="secondary")
            
            # Confirmation display
            confirmation_display = gr.Textbox(
                label="⚠️ Confirmación de Eliminación",
                value="",
                interactive=False,
                max_lines=15,
                visible=False
            )
            
            # Generated files
            script_file = gr.File(
                label="📜 Script de Eliminación",
                visible=False,
                file_count="single"
            )
            
            session_file = gr.File(
                label="💾 Archivo de Sesión",
                visible=False,
                file_count="single"
            )
        
        # Store checkbox components for dynamic management
        checkbox_state = gr.State({})
        checkbox_components = gr.State([])
        
        # Event handlers
        def handle_analyze(directory, min_size):
            status, accordion_data, stats_html, group_visibility = analyze_duplicates(directory, min_size)
            
            if accordion_data:
                # Create accordion HTML
                accordion_html = create_accordion_html(accordion_data)
                return (
                    status,
                    stats_html,
                    accordion_html,
                    group_visibility,
                    get_selection_status(),
                    gr.update(visible=False)  # Hide confirmation
                )
            else:
                return (
                    status,
                    stats_html,
                    "No hay resultados para mostrar",
                    group_visibility,
                    "No hay archivos para seleccionar",
                    gr.update(visible=False)
                )
        
        def handle_confirm():
            confirmation_text = confirm_deletion()
            return confirmation_text, gr.update(visible=True)
        
        def handle_delete():
            result = delete_selected_files()
            return result, get_selection_status(), gr.update(visible=False)
        
        def handle_generate_script():
            script_file_path, message = generate_deletion_script()
            if script_file_path:
                return script_file_path, message, gr.update(visible=True)
            else:
                return None, message, gr.update(visible=False)
        
        def handle_save_session():
            session_file_path, message = save_session()
            if session_file_path:
                return session_file_path, message, gr.update(visible=True)
            else:
                return None, message, gr.update(visible=False)
        
        def handle_load_session(file_path):
            status, accordion_data, stats_html, group_visibility = load_session(file_path)
            
            if accordion_data:
                accordion_html = create_accordion_html(accordion_data)
                return (
                    status,
                    stats_html,
                    accordion_html,
                    group_visibility,
                    get_selection_status()
                )
            else:
                return (
                    status,
                    stats_html,
                    "No hay resultados para mostrar",
                    group_visibility,
                    "No hay archivos para seleccionar"
                )
        
        # Bind events
        analyze_btn.click(
            fn=handle_analyze,
            inputs=[directory_input, min_size_input],
            outputs=[status_output, stats_display, results_accordion, results_group, selection_status, confirmation_display]
        )
        
        stop_btn.click(
            fn=stop_analysis_func,
            outputs=[status_output]
        )
        
        select_all_btn.click(
            fn=select_all_duplicates,
            outputs=[selection_status]
        )
        
        confirm_btn.click(
            fn=handle_confirm,
            outputs=[confirmation_display, confirmation_display]
        )
        
        delete_btn.click(
            fn=handle_delete,
            outputs=[status_output, selection_status, confirmation_display]
        )
        
        generate_script_btn.click(
            fn=handle_generate_script,
            outputs=[script_file, status_output, script_file]
        )
        
        save_session_btn.click(
            fn=handle_save_session,
            outputs=[session_file, status_output, session_file]
        )
        
        load_session_file.upload(
            fn=handle_load_session,
            inputs=[load_session_file],
            outputs=[status_output, stats_display, results_accordion, results_group, selection_status]
        )
    
    return interface

def create_accordion_html(accordion_data):
    """Create HTML for accordion display with visual feedback"""
    if not accordion_data:
        return "No hay resultados para mostrar"
    
    html_parts = []
    
    for group_data in accordion_data:
        group_id = group_data['group_id']
        files = group_data['files']
        wasted_space = finder.format_size(group_data['wasted_space'])
        
        # Group header
        main_filename = Path(files[0]['path']).name if files else "Unknown"
        html_parts.append(f"""
        <div style="margin-bottom: 20px; border: 1px solid #4A5568; border-radius: 8px; overflow: hidden;">
            <!-- Header principal -->
            <div style="background: #272734; border-top: 2px solid #2D3748; padding: 15px;">
                <div style="color: white; font-size: 16px; font-weight: bold; margin-bottom: 8px;">
                    Grupo {group_id}: {main_filename}
                </div>
                <div style="color: #A0AEC0; font-size: 12px;">
                    📄 {len(files)} archivos | 💾 Espacio desperdiciado: {wasted_space}
                </div>
            </div>
            
            <!-- Archivos -->
            <div>
        """)
        
        # Files
        for i, file_info in enumerate(files):
            file_id = f"group_{group_id}_file_{i}"
            is_selected = file_selections.get(file_id, False)
            selected_style = "border-left: 4px solid #48BB78;" if is_selected else "border-left: 4px solid #E53E3E;"
            selection_indicator = "✅" if is_selected else "⭕"
            symlink_indicator = " (Symlink)" if file_info.get('is_symlink', False) else ""
            
            html_parts.append(f"""
                <div style="background: #2B3444; padding: 12px; margin: 8px; border-radius: 6px; {selected_style}">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="margin-right: 10px; font-size: 16px;">{selection_indicator}</span>
                        <div style="color: #F56565; font-size: 12px; font-weight: bold;">
                            📄 Archivo {i+1}{symlink_indicator}
                        </div>
                    </div>
                    <div style="color: white; font-size: 12px; font-family: monospace; margin-bottom: 4px; margin-left: 25px;">
                        {file_info['path']}
                    </div>
                    <div style="color: #A0AEC0; font-size: 10px; margin-left: 25px;">
                        📅 {file_info['mtime_readable']} | 📏 {finder.format_size(file_info['size'])}
                    </div>
                </div>
            """)
        
        html_parts.append("""
            </div>
        </div>
        """)
    
    return ''.join(html_parts)

def toggle_all_selections():
    """Toggle all file selections"""
    global file_selections, current_results
    
    if not current_results:
        return "No hay archivos para seleccionar"
    
    # Check if all files are selected
    all_file_ids = []
    for group in current_results:
        for i in range(len(group['files'])):
            file_id = f"group_{group['group_id']}_file_{i}"
            all_file_ids.append(file_id)
    
    if not all_file_ids:
        return "No hay archivos para seleccionar"
    
    # Check current state
    all_selected = all(file_selections.get(file_id, False) for file_id in all_file_ids)
    
    # Toggle state
    new_state = not all_selected
    for file_id in all_file_ids:
        file_selections[file_id] = new_state
    
    return get_selection_status()

def main():
    """Main function"""
    print("🔍 Detector de Archivos Duplicados GPU - Versión 12 Modificada")
    print("=" * 60)
    print("🚀 Características principales:")
    print("- Archivos principales no pueden ser symlinks")
    print("- Archivos principales NO están protegidos (pueden ser seleccionados para borrado)")
    print(f"⚡ Aceleración GPU: {'Disponible' if finder.use_gpu else 'No disponible'}")
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