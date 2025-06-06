import gradio as gr
from src.components.result_tree import build_results_table
from src.app.session_logic import load_last_session, save_session

def cargar_ultima_sesion():
    return load_last_session()

def actualizar_tabla(groups):
    return build_results_table(groups)

with gr.Blocks(css="src/app/styles.css") as demo:
    gr.Markdown("<h3>🔄 <b>Generar Script</b>  🗑️ Eliminar Seleccionados  👁 CARGAR ULTIMA SESSION</h3>")
    with gr.Row():
        chk_guardable = gr.Checkbox(label="⭐ GUARDABLE", value=True)
        chk_otros = gr.Checkbox(label="OTROS", value=True)
        chk_todos = gr.Checkbox(label="TODOS", value=True)
        btn_cargar = gr.Button("CARGAR ULTIMA SESSION")
    tabla = gr.Dataframe(headers=["", "⭐", "Ruta", "Fecha Modificación", "Tamaño"], interactive=True)
    state_groups = gr.State([])

    def on_cargar(_):
        groups = cargar_ultima_sesion()
        state_groups.value = groups
        return actualizar_tabla(groups)

    btn_cargar.click(on_cargar, None, tabla)