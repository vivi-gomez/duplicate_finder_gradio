import gradio as gr
from .callbacks import setup_callbacks
# from ..core.finder import DuplicateFinder # This was a placeholder, finder is not used directly in app.py

# Placeholder for finder instance, will be managed by state_manager later
# finder = DuplicateFinder() # This was commented out, DuplicateFinder class is not instantiated here.

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
            load_session_btn = gr.Button("📂 Cargar Sesión", variant="secondary", size="sm") # In original, this was load_session_file but it's a button

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
            label="📂 Cargar Sesión", # This is the actual file input
            file_types=[".json"],
            visible=False, # Should be visible, or triggered by load_session_btn
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
                visible=False # Should be visible if results_group is visible
            )

            script_file = gr.File(
                label="📜 Script de Eliminación",
                visible=False, # Output for generated script
                file_count="single"
            )

            # Hidden button for checkbox onchange event, as per original HTML structure
            # The JS on each checkbox input calls: `gradio_app.querySelector('#checkbox_handler').click()`
            checkbox_handler_btn = gr.Button(elem_id="checkbox_handler", visible=False)

        # Setup callbacks
        setup_callbacks(
            interface=interface,
            analyze_btn=analyze_btn,
            stop_btn=stop_btn,
            select_all_btn=select_all_btn, # This is the "Alternar Selección General" button
            refresh_btn=refresh_btn,
            generate_script_btn=generate_script_btn,
            delete_btn=delete_btn,
            save_session_btn=save_session_btn,
            load_session_file=load_session_file, # This is the gr.File component for uploads
            directory_input=directory_input,
            min_size_input=min_size_input,
            status_output=status_output,
            results_group=results_group,
            results_display=results_display,
            selection_status=selection_status,
            script_file_output=script_file, # Output gr.File for the script
            session_file_output=session_file, # Output gr.File for the session
            checkbox_dummy_btn_for_event=checkbox_handler_btn # Pass the hidden button
        )

    return interface
