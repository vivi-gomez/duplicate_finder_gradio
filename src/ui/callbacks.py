import gradio as gr
import os
import tempfile
import json
from datetime import datetime
from pathlib import Path
# import time # Was potentially for direct time operations, but datetime covers current needs.

# Import actual state variables and finder instance from state_manager
from src.state_manager import finder, current_results, group_selections, individual_selections
import src.state_manager as state_manager # Used to modify state_manager.stop_analysis

# Import HTML generator
from .html_generator import create_results_html # create_results_html now uses state_manager internally

def analyze_duplicates(directory, min_size_mb, progress=gr.Progress(track_tqdm=True)):
    state_manager.stop_analysis = False # Reset stop flag at the beginning of analysis

    if not directory or not os.path.exists(directory):
        return (
            "❌ Error: Directorio no válido o no existe.",
            gr.update(visible=False), # results_group
            gr.update(value=""), # results_display
            gr.update(visible=False) # results_display visibility
        )
    try:
        # Progress callback for find_duplicates
        def ui_progress_callback(status_update_string):
            # find_duplicates provides a string like "Procesando: X/Y (P%) - S archivos/seg - ETA: Es"
            # We can pass this directly to gr.Progress desc.
            # For the progress bar value itself, we'd need to parse X and Y.
            # Example parsing (simplified):
            try:
                parts = status_update_string.split(" ")
                if "/" in parts[1]:
                    processed, total = map(int, parts[1].replace("(", "").replace(")", "").split("/"))
                    progress(processed / total, desc=status_update_string)
                else:
                    progress(None, desc=status_update_string) # Indeterminate progress if parsing fails
            except:
                progress(None, desc=status_update_string) # Fallback for any parsing error

            if state_manager.stop_analysis: # Check stop_analysis flag during progress updates
                raise InterruptedError("Análisis detenido por el usuario desde callback.")


        progress(0, desc="Iniciando análisis...") # Initial progress bar state

        results = finder.find_duplicates(directory, min_size_mb, ui_progress_callback)

        if state_manager.stop_analysis: # Check flag again after find_duplicates completes or is interrupted
            return (
                "⏹️ Análisis detenido por el usuario.",
                gr.update(visible=False), "", gr.update(visible=False)
            )

        current_results.clear()
        current_results.extend(results)

        individual_selections.clear()
        for group in results:
            for file_info in group['duplicate_files']:
                individual_selections[file_info['file_id']] = True # Default select duplicates
            individual_selections[group['priority_file']['file_id']] = False # Default deselect priority

        if not results:
            return (
                "✅ No se encontraron archivos duplicados.",
                gr.update(visible=False), "", gr.update(visible=False)
            )

        total_groups = len(results)
        total_duplicates = sum(len(group['duplicate_files']) for group in results)
        total_wasted = sum(group['wasted_space'] for group in results)
        total_wasted_readable = finder.format_size(total_wasted)

        # create_results_html now gets individual_selections from state_manager
        results_html_content = create_results_html(results)

        analysis_summary = f"✅ Análisis completado: {total_groups} grupos, {total_duplicates} duplicados, {total_wasted_readable} desperdiciados."

        return (
            analysis_summary,
            gr.update(visible=True), # results_group visible
            results_html_content, # results_display content
            gr.update(visible=True) # results_display visible
        )
    except InterruptedError: # Catch custom interrupt
         return ("⏹️ Análisis detenido por el usuario.", gr.update(visible=False), "", gr.update(visible=False))
    except Exception as e:
        current_results.clear()
        individual_selections.clear()
        return (
            f"❌ Error catastrófico durante el análisis: {str(e)}",
            gr.update(visible=False), "", gr.update(visible=False)
        )

def stop_analysis_func():
    state_manager.stop_analysis = True
    return "⏹️ Solicitud de detención enviada. El análisis se detendrá en la próxima actualización de progreso."

def handle_checkbox_change(checkbox_id: str, checkbox_value: bool, request: gr.Request):
    """
    This function is intended to be called if Gradio could directly trigger an event from
    each specific checkbox with its ID and new value.
    With the current raw HTML structure, this function is NOT directly and effectively called by Gradio
    in a way that `checkbox_id` and `checkbox_value` are correctly populated from a specific checkbox.
    The `elem_id` for the Gradio component that would trigger this would need to be set,
    and the component itself would need to be a Gradio input component.
    The current setup uses a hidden button `checkbox_handler_btn` which calls `update_selection_status`.
    If JS were to update a `gr.Variable` with `{'id': file_id, 'checked': new_state}`, then this
    function could be a listener to that `gr.Variable`.
    """
    print(f"DEBUG: handle_checkbox_change called. ID: {checkbox_id}, Value: {checkbox_value}. This callback is likely not correctly wired for specific checkbox updates with the current HTML structure.")
    # If it were correctly wired (e.g. from a gr.Variable updated by JS):
    # if checkbox_id:
    # individual_selections[checkbox_id] = checkbox_value
    # return update_selection_status()
    # For now, it does nothing significant as its trigger is not specific.
    return update_selection_status() # Fallback to global status update


def update_selection_status():
    if not current_results:
        return "No hay resultados para mostrar estado."

    num_total_files_in_view = sum(len(g['all_files']) for g in current_results)
    num_selected_files = sum(1 for fid in individual_selections if individual_selections[fid])

    size_selected_files = 0
    priority_selected_count = 0
    duplicates_selected_count = 0

    for group in current_results:
        pf_id = group['priority_file']['file_id']
        if individual_selections.get(pf_id, False):
            priority_selected_count +=1
            size_selected_files += group['priority_file']['size']
        for df in group['duplicate_files']:
            df_id = df['file_id']
            if individual_selections.get(df_id, False):
                duplicates_selected_count +=1
                size_selected_files += df['size']

    return (f"📊 Seleccionados: {num_selected_files}/{num_total_files_in_view} archivos. "
            f"⭐ Prioritarios: {priority_selected_count}. "
            f"📄 Duplicados: {duplicates_selected_count}. "
            f"💾 Tamaño: {finder.format_size(size_selected_files)}")

def toggle_all_groups(): # "Alternar Selección General"
    if not current_results:
        return "No hay resultados para alternar."

    # Initialize selections if they are empty, based on defaults
    if not individual_selections and current_results:
        for group in current_results:
            individual_selections[group['priority_file']['file_id']] = False
            for f_info in group['duplicate_files']:
                individual_selections[f_info['file_id']] = True

    num_selectable_items = len(individual_selections)
    if num_selectable_items == 0:
        return update_selection_status()

    are_currently_less_than_half_selected = sum(1 for v in individual_selections.values() if v) < (num_selectable_items / 2)
    new_state_for_all = are_currently_less_than_half_selected # If true, select all; else, deselect all

    for file_id in list(individual_selections.keys()):
        individual_selections[file_id] = new_state_for_all

    return update_selection_status()

def generate_deletion_script():
    if not current_results:
        return None, "No hay resultados para generar script."

    files_to_include_in_script = []
    for group in current_results:
        for file_info in group['all_files']:
            if individual_selections.get(file_info['file_id'], False):
                files_to_include_in_script.append(file_info)

    if not files_to_include_in_script:
        return None, "No hay archivos seleccionados para el script."

    script_lines = [
        "#!/bin/bash",
        f"# Script de eliminación generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "set -e",
        "echo 'Iniciando eliminación de archivos...'"
    ]
    total_size = sum(f['size'] for f in files_to_include_in_script)

    for f_info in files_to_include_in_script:
        script_lines.append(f"echo 'Eliminando: \"{f_info['path']}\"'")
        script_lines.append(f"rm -vf \"{f_info['path']}\"") # Added -v for verbose, -f for force

    script_lines.append(f"echo 'Eliminación completada. Total de archivos procesados por el script: {len(files_to_include_in_script)}.'")
    script_lines.append(f"echo 'Espacio total que debería ser liberado: {finder.format_size(total_size)}.'")

    script_content = "\n".join(script_lines)
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(script_content)
            script_path = tmp_file.name
        os.chmod(script_path, 0o755)
        return script_path, f"✅ Script generado: {len(files_to_include_in_script)} archivos. {update_selection_status()}"
    except Exception as e:
        return None, f"❌ Error generando script: {str(e)}"

def delete_selected_files():
    if not current_results:
        return "No hay resultados para eliminar."

    files_to_delete = []
    for group in current_results:
        for file_info in group['all_files']:
            if individual_selections.get(file_info['file_id'], False):
                files_to_delete.append(file_info)

    if not files_to_delete:
        return "No hay archivos seleccionados para eliminar."

    deleted_count = 0
    freed_size = 0
    errors = []

    for file_info in files_to_delete:
        try:
            path = Path(file_info['path'])
            if path.is_file():
                freed_size += file_info['size']
                path.unlink()
                deleted_count += 1
                individual_selections[file_info['file_id']] = False # Mark as unselected
            else:
                errors.append(f"No encontrado o no es archivo: {path}")
                individual_selections[file_info['file_id']] = False # Mark as unselected
        except Exception as e:
            errors.append(f"Error eliminando {path}: {str(e)}")

    # After deletion, the HTML view is stale. A refresh of `results_display` is needed.
    # For now, just update the status message.
    # Re-populating current_results or re-running analysis is a larger operation.

    msg = f"✅ {deleted_count} archivos eliminados, {finder.format_size(freed_size)} liberados."
    if errors:
        msg += f" ⚠️ {len(errors)} errores: {'; '.join(errors[:3])}"
        if len(errors) > 3: msg += "..."

    return f"{msg}\n{update_selection_status()}"


def save_session():
    if not current_results:
        return None, "No hay resultados para guardar."

    session_state = {
        'timestamp': datetime.now().isoformat(),
        'current_results': current_results,
        'group_selections': dict(group_selections), # Convert defaultdict to dict for JSON
        'individual_selections': dict(individual_selections), # Convert defaultdict to dict
        'finder_config': {'use_gpu': finder.use_gpu} # Example of saving finder config
    }
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp_file:
            json.dump(session_state, tmp_file, indent=2, ensure_ascii=False)
            file_path = tmp_file.name
        return file_path, f"✅ Sesión guardada. {update_selection_status()}"
    except Exception as e:
        return None, f"❌ Error guardando sesión: {str(e)}"

def load_session(uploaded_file_obj):
    if not uploaded_file_obj:
        return ("⚠️ No se seleccionó archivo.", gr.update(visible=False), "", gr.update(visible=False))

    try:
        with open(uploaded_file_obj.name, 'r', encoding='utf-8') as f:
            session_state = json.load(f)

        current_results.clear()
        current_results.extend(session_state.get('current_results', []))

        group_selections.clear()
        group_selections.update(session_state.get('group_selections', {}))

        individual_selections.clear()
        individual_selections.update(session_state.get('individual_selections', {}))

        # Example: Restore finder config if needed, be cautious with global objects
        # if 'finder_config' in session_state:
        #     finder.use_gpu = session_state['finder_config'].get('use_gpu', finder.use_gpu)

        if current_results:
            # create_results_html gets individual_selections from state_manager
            html_output = create_results_html(current_results)
            return (f"✅ Sesión cargada ({len(current_results)} grupos). {update_selection_status()}",
                    gr.update(visible=True), html_output, gr.update(visible=True))
        else:
            return ("⚠️ Sesión cargada pero sin resultados.", gr.update(visible=False), "", gr.update(visible=False))

    except Exception as e:
        current_results.clear()
        individual_selections.clear()
        return (f"❌ Error cargando sesión: {str(e)}", gr.update(visible=False), "", gr.update(visible=False))

def setup_callbacks(interface, analyze_btn, stop_btn, select_all_btn, refresh_btn,
                    generate_script_btn, delete_btn, save_session_btn, load_session_file,
                    directory_input, min_size_input, status_output, results_group,
                    results_display, selection_status, script_file_output, session_file_output,
                    checkbox_dummy_btn_for_event):

    analyze_btn.click(
        fn=analyze_duplicates,
        inputs=[directory_input, min_size_input, gr.Progress(track_tqdm=True)],
        outputs=[status_output, results_group, results_display, results_display]
    )

    stop_btn.click(fn=stop_analysis_func, outputs=[status_output])
    select_all_btn.click(fn=toggle_all_groups, outputs=[selection_status])
    refresh_btn.click(fn=update_selection_status, outputs=[selection_status])
    generate_script_btn.click(fn=generate_deletion_script, outputs=[script_file_output, selection_status])
    delete_btn.click(fn=delete_selected_files, outputs=[selection_status]) # Consider also updating results_display
    save_session_btn.click(fn=save_session, outputs=[session_file_output, selection_status])

    load_session_file.upload(
        fn=load_session,
        inputs=[load_session_file],
        outputs=[status_output, results_group, results_display, results_display]
    )

    # The checkbox_dummy_btn_for_event is clicked by JS from raw HTML checkboxes.
    # This click ideally should inform Python which checkbox changed and its new state.
    # However, without JS sending that specific data, this Python function can only react generally.
    # `update_selection_status` re-reads the `individual_selections` dict (which JS should have updated).
    # The `handle_checkbox_change` function is a more targeted callback but isn't directly usable here
    # without a mechanism (like JS updating a gr.Variable) to feed it the specific checkbox data.
    if checkbox_dummy_btn_for_event:
        checkbox_dummy_btn_for_event.click(
            fn=update_selection_status, # Primary function to call, as it reads the current state of individual_selections
            inputs=None,
            outputs=[selection_status],
            # _js can be used to get data, but requires careful implementation.
            # For example, JS could collect all checkbox states and pass them as a JSON string.
            # js_get_checkbox_states = """
            # () => {
            #   const cbs = document.querySelectorAll('input[type="checkbox"][id^="g"]'); // Selects file checkboxes
            #   const states = {};
            #   cbs.forEach(cb => { states[cb.id] = cb.checked; });
            #   return [JSON.stringify(states)]; // Return as a list of arguments for Python function
            # }
            # """
            # If using such JS, `update_selection_status_from_js(json_states_str)` could be the Python target.
            # And `individual_selections` would be updated from `json_states_str`.
        )
    # Note: The `handle_checkbox_change(file_id, checked_state)` is still the "ideal" callback for a single checkbox
    # if Gradio were managing those checkboxes as individual components or if JS could call a Python endpoint with that data.
    # The current setup means client-side JS *must* correctly update server-side `individual_selections` for `update_selection_status` to be accurate.
    # This is a known limitation of mixing raw HTML inputs with Python-centric Gradio state.
    pass
