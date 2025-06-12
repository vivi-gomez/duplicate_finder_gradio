#!/usr/bin/env python3

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

current_results = []
group_selections = {}
individual_selections = {}
stop_analysis = False

class DuplicateFinder:
    def __init__(self, use_gpu=True):
        self.use_gpu = use_gpu and self._check_gpu()
        self.total_files = 0
        self.processed_files = 0
        self.start_time = None
        
    def _check_gpu(self):
        try:
            import cupy as cp
            cp.cuda.Device(0).compute_capability
            return True
        except:
            return False
    
    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def _calculate_hash(self, file_path, chunk_size=8192):
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                if self.use_gpu:
                    for chunk in iter(lambda: f.read(chunk_size * 4), b""):
                        hash_md5.update(chunk)
                else:
                    for chunk in iter(lambda: f.read(chunk_size), b""):
                        hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (PermissionError, OSError):
            return None
    
    def find_duplicates(self, directory, min_size_mb=1, progress_callback=None):
        global stop_analysis
        
        directory_path = Path(directory)
        if not directory_path.exists():
            raise ValueError(f"Directory does not exist: {directory}")
        
        min_size_bytes = min_size_mb * 1024 * 1024
        file_hashes = defaultdict(list)
        all_files = []
        
        for file_path in directory_path.rglob('*'):
            if stop_analysis:
                return []
            if file_path.is_file():
                try:
                    size = file_path.stat().st_size
                    if size >= min_size_bytes:
                        all_files.append(file_path)
                except OSError:
                    continue
        
        self.total_files = len(all_files)
        self.processed_files = 0
        self.start_time = time.time()
        
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
                        'hash': file_hash
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
        
        duplicate_groups = []
        group_id = 1
        
        for file_hash, files in file_hashes.items():
            if len(files) > 1:
                files.sort(key=lambda x: x['mtime'], reverse=True)
                file_counter = 1
                for file_info in files:
                    file_info['file_id'] = f"g{group_id}f{file_counter}"
                    file_counter += 1
                
                priority_file = files[0]
                duplicate_files = files[1:]
                wasted_space = sum(f['size'] for f in duplicate_files)
                
                group = {
                    'group_id': group_id,
                    'hash': file_hash,
                    'priority_file': priority_file,
                    'duplicate_files': duplicate_files,
                    'all_files': files,
                    'total_files': len(files),
                    'wasted_space': wasted_space
                }
                duplicate_groups.append(group)
                group_id += 1
        
        return duplicate_groups

finder = DuplicateFinder()

def analyze_duplicates(directory, min_size_mb, progress=gr.Progress()):
    global current_results, group_selections, individual_selections, stop_analysis
    
    stop_analysis = False
    
    if not directory or not os.path.exists(directory):
        return (
            "❌ Error: Directorio no válido o no existe",
            gr.update(visible=False),
            gr.update(value=""),
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
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(visible=False))
        
        current_results = results
        group_selections = {}
        individual_selections = {}
        
        for group in results:
            for file_info in group['duplicate_files']:
                individual_selections[file_info['file_id']] = True
            individual_selections[group['priority_file']['file_id']] = False
        
        if not results:
            return (
                "✅ No se encontraron archivos duplicados",
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(visible=False))
        
        total_groups = len(results)
        total_duplicates = sum(len(group['duplicate_files']) for group in results)
        total_wasted = sum(group['wasted_space'] for group in results)
        total_wasted_readable = finder.format_size(total_wasted)
        results_html = create_results_html(results)
        
        status = f"✅ Análisis completado: {total_groups} grupos, {total_duplicates} duplicados, {total_wasted_readable} desperdiciados"
        
        return (
            status,
            gr.update(visible=True),
            results_html,
            gr.update(visible=True))
        
    except Exception as e:
        return (
            f"❌ Error durante el análisis: {str(e)}",
            gr.update(visible=False),
            gr.update(value=""),
            gr.update(visible=False))

def stop_analysis_func():
    global stop_analysis
    stop_analysis = True
    return "⏹️ Deteniendo análisis..."

def handle_checkbox_change(file_id, checked):
    global individual_selections
    individual_selections[file_id] = checked
    return update_selection_status()

def update_selection_status():
    global current_results, individual_selections
    
    if not current_results:
        return "No hay resultados"
    
    total_files = sum(len(group['all_files']) for group in current_results)
    selected_files = sum(1 for selected in individual_selections.values() if selected)
    selected_size = 0
    priority_selected = 0
    duplicate_selected = 0
    
    for group in current_results:
        for file_info in group['all_files']:
            if individual_selections.get(file_info['file_id'], False):
                selected_size += file_info['size']
        if individual_selections.get(group['priority_file']['file_id'], False):
            priority_selected += 1
        for dup_file in group['duplicate_files']:
            if individual_selections.get(dup_file['file_id'], False):
                duplicate_selected += 1
    
    status_parts = [
        f"📊 Seleccionados: {selected_files}/{total_files} archivos",
        f"⭐ Prioritarios: {priority_selected}",
        f"📄 Duplicados: {duplicate_selected}",
        f"💾 Tamaño total: {finder.format_size(selected_size)}"
    ]
    return " | ".join(status_parts)

def toggle_all_groups():
    global individual_selections, current_results
    
    if not current_results:
        return "No hay grupos para seleccionar"
    
    total_selections = len(individual_selections)
    selected_count = sum(1 for selected in individual_selections.values() if selected)
    new_state = selected_count < (total_selections / 2)
    
    for group in current_results:
        for file_info in group['all_files']:
            individual_selections[file_info['file_id']] = new_state
    
    return update_selection_status()

def generate_deletion_script():
    global current_results, individual_selections
    
    if not current_results:
        return None, "No hay resultados para generar script"
    
    selected_files = []
    for group in current_results:
        for file_info in group['all_files']:
            if individual_selections.get(file_info['file_id'], False):
                selected_files.append(file_info)
    
    if not selected_files:
        return None, "No hay archivos seleccionados para generar script"
    
    script_lines = [
        "#!/bin/bash",
        f"# Script de eliminación de archivos duplicados",
        f"# Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "set -e",
        "echo 'Iniciando eliminación de archivos seleccionados...'",
        ""
    ]
    
    total_size = sum(file_info['size'] for file_info in selected_files)
    
    for file_info in selected_files:
        file_path = file_info['path']
        script_lines.append(f"echo 'Eliminando: {file_path}'")
        script_lines.append(f"rm -f '{file_path}'")
    
    script_lines.extend([
        "",
        f"echo 'Completado: {len(selected_files)} archivos eliminados'",
        f"echo 'Espacio liberado: {finder.format_size(total_size)}'",
        ""
    ])
    
    script_content = '\n'.join(script_lines)
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
    temp_file.write(script_content)
    temp_file.close()
    os.chmod(temp_file.name, 0o755)
    
    status = f"✅ Script generado: {len(selected_files)} archivos, {finder.format_size(total_size)} a liberar"
    return temp_file.name, f"{status}\n{update_selection_status()}"

def delete_selected_files():
    global current_results, individual_selections
    
    if not current_results:
        return "No hay resultados para eliminar"
    
    selected_files = []
    for group in current_results:
        for file_info in group['all_files']:
            if individual_selections.get(file_info['file_id'], False):
                selected_files.append(file_info)
    
    if not selected_files:
        return "No hay archivos seleccionados para eliminar"
    
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
                individual_selections[file_info['file_id']] = False
        except Exception as e:
            errors.append(f"Error eliminando {file_info['path']}: {str(e)}")
    
    result = f"✅ {deleted_files} archivos eliminados, {finder.format_size(deleted_size)} liberados"
    
    if errors:
        result += f"\n⚠️ {len(errors)} errores:"
        for error in errors[:5]:
            result += f"\n  {error}"
        if len(errors) > 5:
            result += f"\n  ... y {len(errors) - 5} errores más"
    
    return f"{result}\n{update_selection_status()}"

def save_session():
    global current_results, group_selections, individual_selections
    
    if not current_results:
        return None, "No hay resultados para guardar"
    
    session_data = {
        'timestamp': datetime.now().isoformat(),
        'results': current_results,
        'group_selections': group_selections,
        'individual_selections': individual_selections,
        'gpu_available': finder.use_gpu
    }
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(session_data, temp_file, indent=2, ensure_ascii=False)
    temp_file.close()
    
    return temp_file.name, f"✅ Sesión guardada con {len(current_results)} grupos"

def load_session(file_path):
    global current_results, group_selections, individual_selections
    
    if not file_path:
        return "No se seleccionó archivo", gr.update(visible=False), gr.update(value=""), gr.update(visible=False)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        current_results = session_data.get('results', [])
        group_selections = session_data.get('group_selections', {})
        individual_selections = session_data.get('individual_selections', {})
        
        if current_results:
            results_html = create_results_html(current_results)
            status = f"✅ Sesión cargada: {len(current_results)} grupos"
            return status, gr.update(visible=True), results_html, gr.update(visible=True)
        else:
            return "⚠️ Sesión cargada pero sin resultados", gr.update(visible=False), gr.update(value=""), gr.update(visible=False)
            
    except Exception as e:
        return f"❌ Error cargando sesión: {str(e)}", gr.update(visible=False), gr.update(value=""), gr.update(visible=False)

def create_results_html(results):
    if not results:
        return "No hay resultados para mostrar"
    
    total_groups = len(results)
    total_duplicates = sum(len(group['duplicate_files']) for group in results)
    total_wasted = sum(group['wasted_space'] for group in results)
    total_wasted_readable = finder.format_size(total_wasted)
    
    html_parts = []
    html_parts.append(f"""
    <script>
        function selectAll() {{
            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {{
                cb.checked = true;
                cb.dispatchEvent(new Event('change'));
            }});
        }}
        function deselectAll() {{
            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {{
                cb.checked = false;
                cb.dispatchEvent(new Event('change'));
            }});
        }}
        function selectAllDuplicates() {{
            const duplicates = document.querySelectorAll('.duplicate-checkbox');
            duplicates.forEach(cb => {{
                cb.checked = true;
                cb.dispatchEvent(new Event('change'));
            }});
        }}
        function selectAllPriority() {{
            const priorities = document.querySelectorAll('.priority-checkbox');
            priorities.forEach(cb => {{
                cb.checked = true;
                cb.dispatchEvent(new Event('change'));
            }});
        }}
    </script>
    """)
    
    html_parts.append(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; text-align: center;">
            <div><strong>Grupos encontrados:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_groups}</span></div>
            <div><strong>Archivos duplicados:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_duplicates}</span></div>
            <div><strong>Espacio desperdiciado:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_wasted_readable}</span></div>
            <div><strong>Aceleración:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{'GPU' if finder.use_gpu else 'CPU'}</span></div>
        </div>
    </div>
    """)
    
    html_parts.append("""
    <div style="padding: 8px; border-radius: 8px; margin-bottom: 20px; text-align: center;">
        <div style="margin-bottom: 10px;"><strong>Selección rápida:</strong></div>
        <button onclick="selectAllDuplicates()" style="margin: 5px; padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">📄 Todos los Duplicados</button>
        <button onclick="selectAllPriority()" style="margin: 5px; padding: 8px 16px; background: #ffc107; color: black; border: none; border-radius: 4px; cursor: pointer;">⭐ Todos los Prioritarios</button>
        <button onclick="deselectAll()" style="margin: 5px; padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer;">❌ Deseleccionar Todo</button>
    </div>
    """)
    
    html_parts.append("""
    <div style="border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: ;">
        <div style="background: #4a5568; color: white; padding: 15px; font-weight: bold; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px;">
            <div style="text-align: left;">Grupo</div>
            <div style="text-align: center;"></div>
            <div>Archivo</div>
            <div style="text-align: right;">Fecha</div>
            <div style="text-align: center;">Tamaño</div>
        </div>
    """)
    
    for group in results:
        group_id = group['group_id']
        priority_file = group['priority_file']
        duplicate_files = group['duplicate_files']
        
        html_parts.append(f"""
        <div style="background: #272734; padding: 10px; border-top: 0.5px solid #4A5568; font-weight: bold; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px;">
            <div style="text-align: center;">{group_id}</div>
            <div></div>
            <div><strong>{Path(priority_file['path']).name}</strong></div>
            <div></div>
            <div></div>
        </div>
        """)
        
        is_selected = individual_selections.get(priority_file['file_id'], False)
        checkbox_style = "accent-color: #ffc107;" if not is_selected else "accent-color: #28a745;"
        
        html_parts.append(f"""
        <div style="background: #; padding: 8px; border-top: 0.5px solid #4a5568; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px; font-size: 0.9em;">
            <div style="text-align: center;">⭐</div>
            <div style="text-align: center;">
                <input type="checkbox" id="{priority_file['file_id']}" {'checked' if is_selected else ''} 
                       style="{checkbox_style} transform: scale(1.2);"
                       onchange="gradio_app.querySelector('#checkbox_handler').click()">
            </div>
            <div style="font-family: monospace; word-break: break-all; font-size: 0.9em;">{priority_file['path']}</div>
            <div style="text-align: right;">{priority_file['mtime_readable']}</div>
            <div style="text-align: center;">{finder.format_size(priority_file['size'])}</div>
        </div>
        """)
        
        for dup_file in duplicate_files:
            is_selected = individual_selections.get(dup_file['file_id'], True)
            checkbox_style = "accent-color: #28a745;" if is_selected else "accent-color: #dc3545;"
            
            html_parts.append(f"""
            <div style="background: #; padding: 8px; border-top: 0.5px solid #4a5568; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px; font-size: 0.9em;">
                <div style="text-align: center;">📄</div>
                <div style="text-align: center;">
                    <input type="checkbox" id="{dup_file['file_id']}" {'checked' if is_selected else ''} 
                           style="{checkbox_style} transform: scale(1.2);"
                           onchange="gradio_app.querySelector('#checkbox_handler').click()">
                </div>
                <div style="font-family: monospace; word-break: break-all; font-size: 0.9em;">{dup_file['path']}</div>
                <div style="text-align: right;">{dup_file['mtime_readable']}</div>
                <div style="text-align: center;">{finder.format_size(dup_file['size'])}</div>
            </div>
            """)
    
    html_parts.append("</div>")
    html_parts.append("""
    <button id="checkbox_handler" style="display: none;" onclick="updateSelections()"></button>
    <script>
    function updateSelections() {
    }
    </script>
    """)
    
    return ''.join(html_parts)

def create_interface():
    with gr.Blocks(title="🔍 Detector de Archivos Duplicados GPU v11", theme=gr.themes.Default(primary_hue="blue", neutral_hue="slate")) as interface:
        
        gr.Markdown("""
        # 🔍 Detector de Archivos Duplicados GPU v11 - Con Checkboxes
        """)
        
        with gr.Row():
            with gr.Column(scale=3):
                directory_input = gr.Textbox(
                    label="📁 Directorio a analizar",
                    placeholder="/media/ewz/KVM2/onetrainer_linux/Find-Duplicate-MIO/test",
                    value="/media/ewz/KVM2/onetrainer_linux/Find-Duplicate-MIO/test",
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
        
        with gr.Row():
            analyze_btn = gr.Button("🔍 Analizar Duplicados", variant="primary", size="lg")
            stop_btn = gr.Button("⏹️ Detener", variant="secondary")
            save_session_btn = gr.Button("💾 Guardar Sesión", variant="secondary", size="sm")
            load_session_btn = gr.Button("📂 Cargar Sesión", variant="secondary", size="sm")
        
        status_output = gr.Textbox(
            label="📊 Estado",
            value="Listo para analizar",
            interactive=False,
            max_lines=2
        )
        
        session_file = gr.File(
            label="💾 Archivo de Sesión",
            visible=False,
            file_count="single"
        )
        
        load_session_file = gr.File(
            label="📂 Cargar Sesión",
            file_types=[".json"],
            visible=False,
            file_count="single"
        )
        
        with gr.Group(visible=False) as results_group:
            gr.Markdown("### 📋 Resultados del Análisis")
            
            with gr.Row():
                select_all_btn = gr.Button("☑️ Alternar Selección General", size="sm")
                refresh_btn = gr.Button("🔄 Actualizar Estado", size="sm", variant="secondary")
                generate_script_btn = gr.Button("📝 Generar Script", variant="secondary", size="sm")
                delete_btn = gr.Button("🗑️ Eliminar Seleccionados", variant="stop", size="sm")
            
            gr.Markdown("""
            <div style="text-align: center; padding: 10px; background: ; border-radius: 5px; margin: 10px 0;">
                <span style="margin: 0 15px;">⭐ **Archivo prioritario** (más reciente)</span>  | 
                <span style="margin: 0 15px;">📄 **Archivo duplicado** (más antiguo)</span> |
                <span style="margin: 0 15px;">☑️ **Checkbox** = será eliminado</span>
            </div>
            """)
            
            selection_status = gr.Textbox(
                label="📊 Estado de Selección",
                value="Usa los checkboxes para seleccionar archivos específicos",
                interactive=False,
                max_lines=3
            )
            
            results_display = gr.HTML(
                label="🌳 Vista de Archivos",
                value="",
                visible=False
            )
            
            script_file = gr.File(
                label="📜 Script de Eliminación",
                visible=False,
                file_count="single"
            )
        
        analyze_btn.click(
            fn=analyze_duplicates,
            inputs=[directory_input, min_size_input],
            outputs=[status_output, results_group, results_display, results_display]
        )
        
        stop_btn.click(
            fn=stop_analysis_func,
            outputs=[status_output]
        )
        
        select_all_btn.click(
            fn=toggle_all_groups,
            outputs=[selection_status]
        )
        
        refresh_btn.click(
            fn=update_selection_status,
            outputs=[selection_status]
        )
        
        generate_script_btn.click(
            fn=generate_deletion_script,
            outputs=[script_file, selection_status]
        )
        
        delete_btn.click(
            fn=delete_selected_files,
            outputs=[selection_status]
        )
        
        save_session_btn.click(
            fn=save_session,
            outputs=[session_file, selection_status]
        )
        
        load_session_file.upload(
            fn=load_session,
            inputs=[load_session_file],
            outputs=[status_output, results_group, results_display, results_display]
        )
    
    return interface

def main():
    print("🔍 Detector de Archivos Duplicados GPU - Versión 11 con Checkboxes")
    print("=" * 70)
    print(f"🚀 Aceleración GPU: {'Disponible' if finder.use_gpu else 'No disponible'}")

    interface = create_interface() 

    from fastapi.staticfiles import StaticFiles
    interface.app.mount("/static", StaticFiles(directory="."), name="static")

    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True,
        show_error=True
    )

if __name__ == "__main__":
    main()
