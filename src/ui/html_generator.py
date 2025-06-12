from pathlib import Path
from src.state_manager import finder, individual_selections # Import from state_manager

# No longer need FinderPlaceholder

def create_results_html(results): # individual_selections is no longer a parameter
    if not results:
        return "No hay resultados para mostrar."

    # Access individual_selections from state_manager
    # Note: individual_selections is a defaultdict from state_manager.

    total_groups = len(results)
    total_duplicates = sum(len(group['duplicate_files']) for group in results) # Corrected: access group['duplicate_files']
    total_wasted = sum(group['wasted_space'] for group in results)
    total_wasted_readable = finder.format_size(total_wasted) # finder is from state_manager

    html_parts = []
    # The JavaScript functions (selectAll, deselectAll, etc.) are for direct DOM manipulation if needed,
    # but Gradio's Python callbacks should ideally handle state changes.
    # The onchange event on checkboxes triggers a Python callback via a hidden button.
    html_parts.append(f"""
    <script>
        function handleCheckboxChange(checkboxId, isChecked) {{
            // This function would be responsible for telling Gradio that a checkbox changed.
            // It could update a hidden gr.Textbox or gr.Variable, which then triggers a Python callback.
            // For example:
            // const hiddenInput = document.getElementById('hidden_checkbox_state_input'); // Assuming such an input exists
            // hiddenInput.value = JSON.stringify({{id: checkboxId, checked: isChecked}});
            // hiddenInput.dispatchEvent(new Event('input')); // Trigger change for Gradio
            // console.log("Checkbox " + checkboxId + " changed to " + isChecked);

            // The current setup: clicking a hidden Gradio button.
            // This JS function is not strictly necessary if the onchange directly triggers the Gradio button click.
            // The `gradio_app.querySelector('#checkbox_handler').click()` in the HTML achieves this.
            // However, that doesn't pass the specific checkbox data easily.
        }}

        // Simpler selection functions that could be triggered by buttons if not using Python callbacks for these actions.
        // These are mostly illustrative as Python callbacks handle master selection logic.
        function selectAllCheckboxes(className, checkedState) {{
            const checkboxes = document.querySelectorAll(className ? `input[type="checkbox"].${{className}}` : 'input[type="checkbox"]');
            checkboxes.forEach(cb => {{
                if (cb.checked !== checkedState) {{
                    cb.checked = checkedState;
                    // To inform Gradio, a change event needs to be dispatched *and* a Python callback triggered.
                    // The simplest is to ensure the main hidden button is clicked after a batch change.
                    // cb.dispatchEvent(new Event('change')); // Not enough for Gradio usually
                }}
            }});
            // After batch changing, click the main handler to refresh Python-side status
            const handlerBtn = document.getElementById('checkbox_handler'); // Ensure this ID matches app.py
            if (handlerBtn) {{
                 handlerBtn.click();
            }}
        }}
    </script>
    """)

    html_parts.append(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; text-align: center;">
            <div><strong>Grupos encontrados:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_groups}</span></div>
            <div><strong>Archivos duplicados (copias):</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_duplicates}</span></div>
            <div><strong>Espacio desperdiciado:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{total_wasted_readable}</span></div>
            <div><strong>Aceleración:</strong><br><span style="font-size: 1.5em; color: #ffd700;">{'GPU' if finder.use_gpu else 'CPU'}</span></div>
        </div>
    </div>
    """)

    # Buttons for quick selection - these call JS functions that would then need to trigger Python callback
    # The Python callback `toggle_all_groups` provides some of this functionality already.
    # For more granular JS control, these buttons could call specific JS functions.
    # Example: <button onclick="selectAllCheckboxes('duplicate-checkbox', true)">Select All Duplicates via JS</button>
    # However, it's better to rely on Python callbacks for state consistency.
    # The existing `select_all_btn` in `app.py` calls `toggle_all_groups` in Python.
    # We can remove these JS-only buttons if Python callbacks cover the functionality.
    # For this iteration, let's keep them as they were in the original structure, assuming they might be used
    # or adapted later. The `onchange` on checkboxes is the primary mechanism for updating selection state.
    html_parts.append("""
    <div style="padding: 8px; border-radius: 8px; margin-bottom: 20px; text-align: center;">
        <div style="margin-bottom: 10px;"><strong>Selección rápida (JS based - might be redundant if Python callbacks are preferred):</strong></div>
        <button onclick="selectAllCheckboxes('duplicate-checkbox', true)" style="margin: 5px; padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">📄 Duplicados (JS)</button>
        <button onclick="selectAllCheckboxes('priority-checkbox', true)" style="margin: 5px; padding: 8px 16px; background: #ffc107; color: black; border: none; border-radius: 4px; cursor: pointer;">⭐ Prioritarios (JS)</button>
        <button onclick="selectAllCheckboxes(null, false)" style="margin: 5px; padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer;">❌ Deseleccionar Todo (JS)</button>
    </div>
    """)

    html_parts.append("""
    <div style="border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background-color: #f9f9f9;">
        <div style="background-color: #333; color: white; padding: 12px 15px; font-weight: bold; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px;">
            <div style="text-align: left;">Grupo</div>
            <div style="text-align: center;">Sel.</div>
            <div>Ruta del Archivo (Prioritario es el más reciente)</div>
            <div style="text-align: right;">Modificado</div>
            <div style="text-align: center;">Tamaño</div>
        </div>
    """) # End of header row

    for group_idx, group_data in enumerate(results):
        group_id_display = group_data['group_id']

        # Group Header (Optional - can make UI very busy)
        # html_parts.append(f"""
        # <div style="background-color: #eee; padding: 8px 15px; border-top: 1px solid #ddd; font-weight: bold; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px;">
        #     <div>Grupo {group_id_display}</div>
        #     <div></div> <div>Hash: {group_data['hash'][:12]}...</div> <div></div> <div></div>
        # </div>""")

        # All files in the group, priority file first
        all_files_sorted = sorted(group_data['all_files'], key=lambda x: x['mtime'], reverse=True)

        for file_idx, file_info in enumerate(all_files_sorted):
            is_priority = (file_info['file_id'] == group_data['priority_file']['file_id'])
            file_id = file_info['file_id']

            # Determine selection state from state_manager.individual_selections
            is_checked = individual_selections.get(file_id, False) # Default to False if not in dict

            checkbox_class = "priority-checkbox" if is_priority else "duplicate-checkbox"
            icon = "⭐" if is_priority else "📄"
            row_style = "background-color: #fff;" if group_idx % 2 == 0 else "background-color: #f0f0f0;"
            if is_priority:
                row_style += " font-weight: bold;"


            html_parts.append(f"""
            <div style="{row_style} padding: 8px 15px; border-top: 1px solid #ddd; display: grid; grid-template-columns: 60px 30px 1fr 180px 120px; gap: 10px; align-items: center; font-size: 0.9em;">
                <div style="text-align: left;">{group_id_display if file_idx == 0 else ""}</div>
                <div style="text-align: center;">
                    <input type="checkbox" class="{checkbox_class}" id="{file_id}" name="{file_id}"
                           {'checked' if is_checked else ''}
                           onchange="gradio_app.querySelector('#checkbox_handler').click(); /* handleCheckboxChange('{file_id}', this.checked); */"
                           style="transform: scale(1.1);">
                </div>
                <div style="font-family: monospace; word-break: break-all; font-size: 0.95em;">{icon} {file_info['path']}</div>
                <div style="text-align: right; font-size: 0.85em;">{file_info['mtime_readable']}</div>
                <div style="text-align: center;">{finder.format_size(file_info['size'])}</div>
            </div>
            """)

    html_parts.append("</div>") # End of results table div

    # The hidden button #checkbox_handler is defined in app.py.
    # The onchange event of checkboxes clicks it.
    # That button's .click() event in Python calls `update_selection_status`.
    # For `individual_selections` to be up-to-date when `update_selection_status` runs,
    # client-side JS needs to inform Python about the change before or as part of that click.
    # This is the main challenge with raw HTML checkboxes.
    # A `gr.Variable` or custom JS->Python communication would be more robust here.

    return ''.join(html_parts)
