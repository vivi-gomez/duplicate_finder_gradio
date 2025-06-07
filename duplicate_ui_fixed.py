#!/usr/bin/env python3
"""
Módulo de interfaz de usuario para el detector de duplicados
Contiene funciones para crear la interfaz Gradio y mostrar resultados
"""

import gradio as gr
from pathlib import Path

def create_tree_display(results, group_selections, individual_selections, finder, gpu_available):
    """Crea la visualización en árbol de los resultados"""
    if not results:
        return gr.update(value="No hay resultados para mostrar", visible=True)
    
    html_content = []
    
    # Estadísticas generales
    total_groups = len(results)
    total_duplicates = sum(len(group['duplicate_files']) for group in results)
    total_wasted = sum(group['wasted_space'] for group in results if group_selections.get(group['group_id'], False))
    total_wasted_readable = finder.format_size(total_wasted)
    
    html_content.append(f"""
    <div class="stats-container">
        <div class="stat-item">
            <span class="stat-label">Grupos encontrados:</span>
            <span class="stat-value">{total_groups}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Archivos duplicados:</span>
            <span class="stat-value">{total_duplicates}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Espacio desperdiciado:</span>
            <span class="stat-value">{total_wasted_readable}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Aceleración:</span>
            <span class="stat-value">{'GPU' if gpu_available else 'CPU'}</span>
        </div>
    </div>
    """)
    
    # Tabla de resultados (header is now handled by Gradio components)
    html_content.append("""
    <div class="results-table">
    """) # Removed header HTML
    
    for group in results:
        group_id = group['group_id']
        is_selected = group_selections.get(group_id, False)
        priority_file = group['priority_file']
        duplicate_files = group['duplicate_files']
        
        # Fila del grupo
        selection_class = "selected" if is_selected else ""
        html_content.append(f"""
        <div class="group-row {selection_class}">
            <div class="group-cell group-col">{group_id}</div>
            <div class="group-cell select-col">
                <input type="checkbox" class="group-checkbox" id="group_{group_id}" 
                       {'checked' if is_selected else ''} onchange="toggleGroup({group_id})">
            </div>
            <div class="group-cell filename-col">
                <strong>{Path(priority_file['path']).name}</strong>
            </div>
            <div class="group-cell datetime-col"></div>
            <div class="group-cell size-col"></div>
        </div>
        """)
        
        # Archivo prioritario (guardable)
        priority_selected = individual_selections.get(group_id, {}).get('priority', False)
        html_content.append(f"""
        <div class="file-row priority-file">
            <div class="file-cell group-col"></div>
            <div class="file-cell select-col">
                <input type="checkbox" class="priority-checkbox" id="priority_{group_id}" 
                       {'checked' if priority_selected else ''} onchange="togglePriorityFile({group_id})">
                <span class="priority-icon">⭐</span>
            </div>
            <div class="file-cell filename-col">
                <span class="file-path">{priority_file['path']}</span>
            </div>
            <div class="file-cell datetime-col">{priority_file['mtime_readable']}</div>
            <div class="file-cell size-col">{finder.format_size(priority_file['size'])}</div>
        </div>
        """)
        
        # Archivos duplicados
        duplicate_selections = individual_selections.get(group_id, {}).get('duplicates', [])
        for idx, dup_file in enumerate(duplicate_files):
            is_dup_selected = duplicate_selections[idx] if idx < len(duplicate_selections) else True
            html_content.append(f"""
            <div class="file-row duplicate-file">
                <div class="file-cell group-col"></div>
                <div class="file-cell select-col">
                    <input type="checkbox" class="duplicate-checkbox" id="dup_{group_id}_{idx}" 
                           {'checked' if is_dup_selected else ''} onchange="toggleDuplicateFile({group_id}, {idx})">
                </div>
                <div class="file-cell filename-col">
                    <span class="file-path">{dup_file['path']}</span>
                </div>
                <div class="file-cell datetime-col">{dup_file['mtime_readable']}</div>
                <div class="file-cell size-col">{finder.format_size(dup_file['size'])}</div>
            </div>
            """)
    
    html_content.append("</div>") # Close results-table

    # Removed the entire JavaScript block for event listeners as it's no longer needed.
    # Sorting is now handled by direct Gradio button clicks.
    # Other JS functions for selections (toggleAllGroups, toggleGroup, etc.) might need to be moved
    # to a global JS file if they are still needed and were part of this block.
    # For this refactoring, assuming only sort-related JS is removed.
    # If other JS functions were here and are still needed, this is a bug.
    # Reviewing the removed JS, it seems it also contained selection logic.
    # This means the selection logic (toggleAllGroups, toggleGroup, togglePriorityFile, toggleDuplicateFile,
    # updateSelectAllState, selectAllPriorities, selectAllOthers, updateSelectionCount, DOMContentLoaded setup for these)
    # needs to be preserved. This is a critical oversight in the current diff.
    # The instruction was "Remove the JavaScript <script> block ... that contains event listeners for name_sort_header, size_sort_header, and related logic"
    # This implies only that part of the JS should be removed.

    # Let's assume for now the original JS for selections is still desired and was NOT meant to be fully removed.
    # The following diff will need to be more precise, only removing the sort-related JS.
    # However, the current tool works on a full block replacement basis for the <script> tag.
    # This means I MUST provide the complete new <script> tag content.
    
    # Revised plan:
    # 1. Keep the JavaScript for selections.
    # 2. Remove only the event listeners for 'size_sort_header' and 'name_sort_header' and their related console logs.
    # The `DOMContentLoaded` listener will still run `updateSelectAllState` and `updateSelectionCount`.
    # The `confirmDeleteButtonUI` listener should also be preserved.

    # New Script content (preserving selection and delete confirmation logic)
    html_content.append("""
    <script>
    let allGroupsSelected = true; // Estado global para toggle
    let allPrioritiesSelected = false; // Estado para archivos prioritarios
    let allDuplicatesSelected = true; // Estado para archivos duplicados (por defecto seleccionados)
    
    function toggleAllGroups() {
        const selectAllCheckbox = document.getElementById('select_all');
        const groupCheckboxes = document.querySelectorAll('.group-checkbox');
        allGroupsSelected = !allGroupsSelected;
        selectAllCheckbox.checked = allGroupsSelected;
        groupCheckboxes.forEach(checkbox => {
            checkbox.checked = allGroupsSelected;
            const groupId = checkbox.id.replace('group_', '');
            const groupRow = checkbox.closest('.group-row');
            if (allGroupsSelected) {
                groupRow.classList.add('selected');
            } else {
                groupRow.classList.remove('selected');
            }
        });
        updateSelectionCount();
    }
    
    function toggleGroup(groupId) {
        const checkbox = document.getElementById('group_' + groupId);
        const groupRow = checkbox.closest('.group-row');
        if (checkbox.checked) {
            groupRow.classList.add('selected');
        } else {
            groupRow.classList.remove('selected');
        }
        updateSelectAllState();
        updateSelectionCount();
    }
    
    function togglePriorityFile(groupId) {
        const checkbox = document.getElementById('priority_' + groupId);
        console.log(`Priority file ${groupId}: ${checkbox.checked ? 'selected' : 'deselected'}`);
        // Update hidden fields and trigger Python callback
        document.getElementById('priority_update_group_id_hidden').value = groupId;
        document.getElementById('priority_update_is_checked_hidden').value = checkbox.checked;
        // Forcing change event for Gradio to pick up the new value.
        var iu1 = document.getElementById('priority_update_group_id_hidden'); iu1.dispatchEvent(new Event('input', { bubbles: true }));
        var iu2 = document.getElementById('priority_update_is_checked_hidden'); iu2.dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('trigger_priority_update_btn_hidden').click();
        updateSelectionCount(); // Keep this for immediate UI feedback if any, though Python callback will refresh table
    }
    
    function toggleDuplicateFile(groupId, fileIdx) {
        const checkbox = document.getElementById(`dup_${groupId}_${fileIdx}`);
        console.log(`Duplicate file ${groupId}_${fileIdx}: ${checkbox.checked ? 'selected' : 'deselected'}`);
        // Update hidden fields and trigger Python callback
        document.getElementById('duplicate_update_group_id_hidden').value = groupId;
        document.getElementById('duplicate_update_file_idx_hidden').value = fileIdx;
        document.getElementById('duplicate_update_is_checked_hidden').value = checkbox.checked;
        // Forcing change event
        var iu3 = document.getElementById('duplicate_update_group_id_hidden'); iu3.dispatchEvent(new Event('input', { bubbles: true }));
        var iu4 = document.getElementById('duplicate_update_file_idx_hidden'); iu4.dispatchEvent(new Event('input', { bubbles: true }));
        var iu5 = document.getElementById('duplicate_update_is_checked_hidden'); iu5.dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('trigger_duplicate_update_btn_hidden').click();
        updateSelectionCount(); // Keep this for immediate UI feedback
    }
    
    function updateSelectAllState() {
        const selectAllCheckbox = document.getElementById('select_all');
        const groupCheckboxes = document.querySelectorAll('.group-checkbox');
        const checkedGroups = document.querySelectorAll('.group-checkbox:checked');
        if (checkedGroups.length === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
            allGroupsSelected = false;
        } else if (checkedGroups.length === groupCheckboxes.length) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
            allGroupsSelected = true;
        } else {
            selectAllCheckbox.indeterminate = true;
        }
    }
    
    function selectAllPriorities() {
        allPrioritiesSelected = !allPrioritiesSelected;
        const priorityCheckboxes = document.querySelectorAll('.priority-checkbox');
        priorityCheckboxes.forEach(checkbox => {
            checkbox.checked = allPrioritiesSelected;
        });
        updateSelectionCount();
        return allPrioritiesSelected ? 'seleccionados' : 'deseleccionados';
    }
    
    function selectAllOthers() {
        allDuplicatesSelected = !allDuplicatesSelected;
        const duplicateCheckboxes = document.querySelectorAll('.duplicate-checkbox');
        duplicateCheckboxes.forEach(checkbox => {
            checkbox.checked = allDuplicatesSelected;
        });
        updateSelectionCount();
        return allDuplicatesSelected ? 'seleccionados' : 'deseleccionados';
    }
    
    function updateSelectionCount() {
        const selectedGroups = document.querySelectorAll('.group-checkbox:checked').length;
        const totalGroups = document.querySelectorAll('.group-checkbox').length;
        const selectedPriorities = document.querySelectorAll('.priority-checkbox:checked').length;
        const selectedDuplicates = document.querySelectorAll('.duplicate-checkbox:checked').length;
        console.log(`Grupos: ${selectedGroups}/${totalGroups}, Prioritarios: ${selectedPriorities}, Duplicados: ${selectedDuplicates}`);
    }
    
    document.addEventListener('DOMContentLoaded', function() {
        updateSelectAllState();
        updateSelectionCount();

        // Deletion Confirmation
        const confirmDeleteButtonUI = document.getElementById('confirm_delete_button_ui');
        if (confirmDeleteButtonUI) {
            confirmDeleteButtonUI.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                console.log('Confirm delete button UI clicked.');
                if (window.confirm("Los archivos seleccionados serán borrados PERMANENTEMENTE. Esta acción no se puede deshacer. ¿Está seguro?")) {
                    console.log('User confirmed deletion. Clicking hidden actual delete trigger.');
                    const hiddenActualDeleteButton = document.getElementById('hidden_actual_delete_trigger');
                    if (hiddenActualDeleteButton) {
                        hiddenActualDeleteButton.click();
                    } else {
                        console.error('Hidden actual delete trigger button not found.');
                    }
                } else {
                    console.log('User cancelled deletion.');
                }
            }, true); // Use capture phase
        } else {
            console.warn('Confirm delete button UI element (id: confirm_delete_button_ui) not found at initial script execution.');
        }

        // Deletion Confirmation for Symlinks
        const confirmSymlinkButtonUI = document.getElementById('confirm_symlink_button_ui');
        if (confirmSymlinkButtonUI) {
            confirmSymlinkButtonUI.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                console.log('Confirm symlink button UI clicked.');
                if (window.confirm("Los archivos duplicados seleccionados serán ELIMINADOS y reemplazados por symlinks que apuntan al archivo prioritario. Esta acción para los archivos eliminados no se puede deshacer. ¿Está seguro?")) {
                    console.log('User confirmed symlink creation and deletion. Clicking hidden actual symlink trigger.');
                    const hiddenActualSymlinkButton = document.getElementById('hidden_actual_symlink_trigger');
                    if (hiddenActualSymlinkButton) {
                        hiddenActualSymlinkButton.click();
                    } else {
                        console.error('Hidden actual symlink trigger button (elem_id: hidden_actual_symlink_trigger) not found.');
                    }
                } else {
                    console.log('User cancelled symlink creation.');
                }
            }, true); // Use capture phase
        } else {
            // This console.warn might appear if the results_display HTML is updated and the script re-evaluates before Gradio fully renders.
            // It's generally okay if the button works on subsequent interactions.
            console.warn('Confirm symlink button UI element (elem_id: confirm_symlink_button_ui) not found at initial script (re-)execution.');
        }
    });
    </script>
    """)
    return gr.update(value=''.join(html_content), visible=True)


def create_interface_components():
    """Crea todos los componentes de la interfaz Gradio"""
    
    # Título y descripción
    gr.Markdown("""
    # 🔍 Detector de Archivos Duplicados GPU
    
    Encuentra y elimina archivos duplicados usando aceleración GPU (NVIDIA RTX 3090) o CPU como respaldo.
    
    ### Características:
    - ⚡ Aceleración GPU con CuPy
    - 🌳 Vista en árbol organizada
    - 📊 Análisis de espacio desperdiciado
    - 🛡️ Protección de archivos prioritarios (más recientes)
    - 📝 Generación de scripts de eliminación
    - 🔗 Creación de symlinks para preservar referencias
    - 💾 Guardado de sesiones para análisis largos
    """)
    
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
    
    # Archivos de sesión
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
    
    # Grupo de resultados (inicialmente oculto)
    with gr.Group(visible=False) as results_group:
        gr.Markdown("### 📋 Resultados del Análisis")
        
        with gr.Row():
            select_all_btn = gr.Button("☑️ Seleccionar/Deseleccionar Todos", size="sm")
            select_priorities_btn = gr.Button("⭐ Toggle Guardables", size="sm", variant="secondary")
            select_others_btn = gr.Button("📁 Toggle Otros", size="sm", variant="secondary")
            # sort_by_size_btn = gr.Button("Ordenar por Tamaño", size="sm") # Removed old button, replaced by header button
            
        with gr.Row():
            generate_script_btn = gr.Button("📝 Borrar con Script", variant="secondary", size="sm")
            # Visible button for symlink confirmation
            create_symlinks_btn = gr.Button("🔗 Borrar & Crear Symlinks", variant="secondary", size="sm", elem_id="confirm_symlink_button_ui")
            # Hidden button that Python will connect to
            confirmed_create_symlinks_btn = gr.Button("🔗 Borrar & Crear Symlinks (Actual Trigger)", variant="secondary", size="sm", visible=False, elem_id="hidden_actual_symlink_trigger")
            export_symlinks_btn = gr.Button("📤 Exportar Script Symlinks", size="sm")
            delete_btn = gr.Button("🗑️ Eliminar Seleccionados", variant="stop", size="sm", elem_id="confirm_delete_button_ui")

        # New header row using Gradio components
        name_sort_actual_button = gr.Button("Grupo", elem_classes=["header-button"], scale=2) # Matches 80px approx
        size_sort_actual_button = gr.Button("Tamaño", elem_classes=["header-button"], scale=2) # Matches 120px approx

        with gr.Row(elem_classes=["table-header"], equal_height=True):
            # Corresponds to: grid-template-columns: 80px 60px 1fr 180px 120px;
            # Group | Select | File | Date | Size
            # Scale values are approximate to match column widths
            # Total scale is 2+1+7+3+2 = 15.
            # 80px -> scale 2
            # 60px -> scale 1
            # 1fr -> scale 7 (flexible)
            # 180px -> scale 3
            # 120px -> scale 2
            gr.Column(name_sort_actual_button, scale=2, min_width=80)
            gr.HTML("<div class='header-cell select-col'></div>", scale=1, min_width=60) # For the select column (empty header)
            gr.HTML("<div class='header-cell filename-col'>Archivo</div>", scale=7) # File
            gr.HTML("<div class='header-cell datetime-col'>Fecha Modificación</div>", scale=3, min_width=180) # Date
            gr.Column(size_sort_actual_button, scale=2, min_width=120)

        selection_status = gr.Textbox(
            label="📊 Estado de Selección",
            value="Selecciona grupos para eliminar duplicados",
            interactive=False,
            max_lines=3
        )
        
        results_display = gr.HTML(
            label="🌳 Vista de Archivos", # This label might be redundant now
            value="",
            visible=False
        )
        
        script_file = gr.File(
            label="📜 Script de Eliminación",
            visible=False,
            file_count="single"
        )
        
        symlinks_file = gr.File(
            label="🔗 Script de Symlinks",
            visible=False,
            file_count="single"
        )
    
    # Información adicional
    with gr.Accordion("ℹ️ Información y Ayuda", open=False):
        gr.Markdown("""
        ### 🎯 Cómo usar esta herramienta:
        
        1. **Introduce el directorio** donde quieres buscar duplicados
        2. **Configura el tamaño mínimo** para filtrar archivos pequeños
        3. **Ejecuta el análisis** - puede tomar varios minutos según el tamaño
        4. **Revisa los resultados** en la vista de árbol
        5. **Selecciona grupos** para eliminar duplicados (mantiene el archivo más reciente)
        6. **Crea symlinks** para preservar referencias antes de eliminar
        7. **Genera un script** para revisar antes de eliminar, o **elimina directamente**
        8. **Guarda la sesión** para análisis largos y recuperar tu trabajo después
        
        ### 🔍 Explicación de iconos:
        - ⭐ **Archivo prioritario** (más reciente, se conserva)
        - ✓ **Archivo duplicado** (candidato para eliminación)
        - ☑️ **Grupo seleccionado** (duplicados serán eliminados)
        
        ### 💾 Gestión de sesiones:
        - **Guardar Sesión**: Guarda todos los resultados y selecciones actuales
        - **Cargar Sesión**: Restaura una sesión previamente guardada
        - Útil para análisis largos que requieren tiempo para revisar
        - Preserva todas las selecciones manuales realizadas
        
        ### 🔗 Symlinks:
        - Los symlinks preservan las referencias a archivos que serán eliminados
        - Apuntan al archivo prioritario (que se conserva)
        - Útil para mantener la funcionalidad de aplicaciones que referencian archivos específicos
        
        ### ⚠️ Advertencias importantes:
        - Siempre **haz una copia de seguridad** antes de eliminar archivos
        - Los archivos se eliminan **permanentemente** (no van a la papelera)
        - La herramienta prioriza archivos **más recientes** automáticamente
        - Revisa cuidadosamente antes de confirmar eliminaciones masivas
        
        ### 🚀 Rendimiento:
        - Con GPU: Óptimo para archivos grandes (>100MB)
        - Con CPU: Funciona bien para archivos medianos
        - El análisis es más rápido en SSDs que en HDDs
        """)
    
    # size_sort_header_trigger_btn = gr.Button("Size Sort Trigger", visible=False, elem_id="hidden_size_sort_trigger") # Removed
    # name_sort_header_trigger_btn = gr.Button("Name Sort Trigger", visible=False, elem_id="hidden_name_sort_trigger") # Removed
    confirmed_delete_btn = gr.Button("Actual Delete Trigger", visible=False, elem_id="hidden_actual_delete_trigger")

    # Hidden components for JS to Python communication for individual file selections
    priority_update_group_id = gr.Textbox(visible=False, elem_id="priority_update_group_id_hidden", label="p_gid")
    priority_update_is_checked = gr.Textbox(visible=False, elem_id="priority_update_is_checked_hidden", label="p_chk")
    trigger_priority_update_btn = gr.Button("Trigger Priority Update", visible=False, elem_id="trigger_priority_update_btn_hidden")

    duplicate_update_group_id = gr.Textbox(visible=False, elem_id="duplicate_update_group_id_hidden", label="d_gid")
    duplicate_update_file_idx = gr.Textbox(visible=False, elem_id="duplicate_update_file_idx_hidden", label="d_fidx")
    duplicate_update_is_checked = gr.Textbox(visible=False, elem_id="duplicate_update_is_checked_hidden", label="d_chk")
    trigger_duplicate_update_btn = gr.Button("Trigger Duplicate Update", visible=False, elem_id="trigger_duplicate_update_btn_hidden")

    return (directory_input, min_size_input, analyze_btn, stop_btn,
            status_output, results_group, select_all_btn,
            select_priorities_btn, select_others_btn,
            generate_script_btn,
            create_symlinks_btn, # New visible button
            confirmed_create_symlinks_btn, # New hidden button
            export_symlinks_btn,
            delete_btn, selection_status, results_display, script_file,
            symlinks_file, save_session_btn, load_session_btn, session_file, load_session_file,
            confirmed_delete_btn,
            name_sort_actual_button, size_sort_actual_button,
            priority_update_group_id, priority_update_is_checked, trigger_priority_update_btn,
            duplicate_update_group_id, duplicate_update_file_idx, duplicate_update_is_checked, trigger_duplicate_update_btn
            )
