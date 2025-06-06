import gradio as gr
import json
import os
from datetime import datetime

# ================= SESSION LOGIC =================

SESSION_FILE = "last_session.json"

def save_session(groups):
    with open(SESSION_FILE, "w") as f:
        json.dump(groups, f, indent=2, default=str)

def load_last_session():
    try:
        with open(SESSION_FILE, "r") as f:
            groups = json.load(f)
    except FileNotFoundError:
        return []
    # Al cargar, solo selecciona "OTROS"
    for group in groups:
        for file in group["files"]:
            file["seleccionado"] = file.get("categoria", "OTROS") == "OTROS"
        group["seleccionado"] = all(file["seleccionado"] for file in group["files"])
    return groups

# =============== RESULT TREE COMPONENT ===============

def format_file_row(file, is_prioritary):
    checked = "✅" if file.get("seleccionado", False) else "⬜"
    star = "⭐" if is_prioritary else ""
    return [
        checked,
        star,
        file["ruta"],
        file.get("fecha", ""),
        f"{file.get('tamano', 0):.2f} MB"
    ]

def build_results_table(groups):
    rows = []
    for group in groups:
        # Cabecera de grupo: selección, nombre, grupo
        group_checked = "✅" if group.get("seleccionado", False) else "⬜"
        rows.append([
            group_checked,
            "",
            f"{group['prioritario']} (Grupo {group['numero']})",
            "",
            ""
        ])
        for file in group["files"]:
            is_prioritary = (file["ruta"] == group["prioritario"])
            rows.append(format_file_row(file, is_prioritary))
    return rows

# =============== DEMO DATA STRUCTURE ===============

# Esta función simula resultados para mostrar el árbol.
def demo_duplicate_groups():
    return [
        {
            "numero": 0,
            "prioritario": "4x-UltraSharp.pth",
            "seleccionado": False,
            "files": [
                {
                    "id": "f0-0",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/01-ESRGAN/4x-UltraSharp.pth",
                    "fecha": "2021-10-26 04:32:24",
                    "tamano": 63.86,
                    "categoria": "GUARDABLE",
                    "seleccionado": False
                },
                {
                    "id": "f0-1",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/UltraSharp/4x-UltraSharp.pth",
                    "fecha": "2021-10-26 04:32:24",
                    "tamano": 63.86,
                    "categoria": "OTROS",
                    "seleccionado": True
                }
            ]
        },
        {
            "numero": 1,
            "prioritario": "OmniSR_X2_DIV2K.safetensors",
            "seleccionado": True,
            "files": [
                {
                    "id": "f1-0",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/01-ESRGAN/Omni-SR/OmniSR_X2_DIV2K.safetensors",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.58,
                    "categoria": "GUARDABLE",
                    "seleccionado": True
                },
                {
                    "id": "f1-1",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/OmniSR_X2_DIV2K.safetensors",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.58,
                    "categoria": "OTROS",
                    "seleccionado": True
                }
            ]
        },
        {
            "numero": 2,
            "prioritario": "OmniSR_X3_DIV2K.safetensors",
            "seleccionado": True,
            "files": [
                {
                    "id": "f2-0",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/01-ESRGAN/Omni-SR/OmniSR_X3_DIV2K.safetensors",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.60,
                    "categoria": "GUARDABLE",
                    "seleccionado": True
                },
                {
                    "id": "f2-1",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/Omni-SR/.git/lfs/objects/4f/b0/4fb0b68fc314f798d2ddcf",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.60,
                    "categoria": "OTROS",
                    "seleccionado": True
                },
                {
                    "id": "f2-2",
                    "ruta": "/OmniSR_X3_DIV2K.safetensors",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.60,
                    "categoria": "OTROS",
                    "seleccionado": True
                }
            ]
        },
        {
            "numero": 3,
            "prioritario": "OmniSR_X4_DIV2K.safetensors",
            "seleccionado": False,
            "files": [
                {
                    "id": "f3-0",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/01-ESRGAN/Omni-SR/.git/lfs/objects/df/f2/df25e4ed39cb5cbe534d920e292063a0555d932f54c5ec321490a2a59832",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.62,
                    "categoria": "GUARDABLE",
                    "seleccionado": False
                },
                {
                    "id": "f3-1",
                    "ruta": "/mnt/12raid/AI-apps/Stable Diffusion/OmniSR_X4_DIV2K.safetensors",
                    "fecha": "2025-06-06 12:31:12",
                    "tamano": 1.62,
                    "categoria": "OTROS",
                    "seleccionado": True
                }
            ]
        },
    ]

# =============== FILTRO DE SELECCIÓN ===============

def filter_by_category(groups, guardable, otros, todos):
    # Aplica filtro de selección visual
    filtered = []
    for group in groups:
        group_filtered = {**group}
        group_filtered["files"] = []
        for file in group["files"]:
            if todos:
                group_filtered["files"].append(file)
            elif guardable and file.get("categoria") == "GUARDABLE":
                group_filtered["files"].append(file)
            elif otros and file.get("categoria") == "OTROS":
                group_filtered["files"].append(file)
        filtered.append(group_filtered)
    return filtered

# =============== INTERFAZ GRADIO PRINCIPAL ===============

with gr.Blocks(css="""
#duplicate-results-table { background: #212532; color: #FFF; font-size: 14px;}
#duplicate-results-table .gr-checkbox { margin-right: 6px;}
#duplicate-results-table .gr-highlightedtext { background: #181b25; color: #b6daf7; border-radius: 3px; padding: 2px 5px;}
""") as demo:
    gr.Markdown(
        """
        <div style="display:flex;align-items:center;gap:2em;">
            <button style="background:#6c49f8;color:white;border-radius:7px;padding:7px 14px;border:none;font-weight:bold;font-size:1em;cursor:pointer;">📝 Generar Script</button>
            <button style="background:#222;color:#e64f4f;border-radius:7px;padding:7px 14px;border:none;font-weight:bold;font-size:1em;cursor:pointer;">🗑️ Eliminar Seleccionados</button>
            <button id="load-session-btn" style="background:#191c20;color:#fff;border-radius:7px;padding:7px 14px;border:none;font-weight:bold;font-size:1em;cursor:pointer;">👁️ CARGAR ULTIMA SESSION</button>
        </div>
        """,
        elem_id="main-toolbar"
    )
    with gr.Row():
        chk_guardable = gr.Checkbox(label="⭐ GUARDABLE", value=True, elem_id="chk-guardable")
        chk_otros = gr.Checkbox(label="OTROS", value=True, elem_id="chk-otros")
        chk_todos = gr.Checkbox(label="TODOS", value=True, elem_id="chk-todos")
    with gr.Row():
        table = gr.Dataframe(
            headers=["", "⭐", "Ruta", "Fecha Modificación", "Tamaño"],
            value=[],
            interactive=False,
            elem_id="duplicate-results-table",
            wrap=True
        )
    state_groups = gr.State(demo_duplicate_groups())

    def actualizar_tabla(groups, guardable, otros, todos):
        filtered = filter_by_category(groups, guardable, otros, todos)
        rows = build_results_table(filtered)
        return rows

    def on_cargar_ultima_session():
        groups = load_last_session()
        if not groups:
            groups = demo_duplicate_groups()
        return groups

    # EVENTOS
    chk_guardable.change(
        fn=actualizar_tabla,
        inputs=[state_groups, chk_guardable, chk_otros, chk_todos],
        outputs=table
    )
    chk_otros.change(
        fn=actualizar_tabla,
        inputs=[state_groups, chk_guardable, chk_otros, chk_todos],
        outputs=table
    )
    chk_todos.change(
        fn=actualizar_tabla,
        inputs=[state_groups, chk_guardable, chk_otros, chk_todos],
        outputs=table
    )

    # Botón Cargar Última Sesión
    gr.Button("CARGAR ULTIMA SESSION").click(
        fn=on_cargar_ultima_session,
        inputs=[],
        outputs=state_groups
    ).then(
        actualizar_tabla,
        [state_groups, chk_guardable, chk_otros, chk_todos],
        table
    )

    # Inicializar tabla
    table.value = build_results_table(filter_by_category(demo_duplicate_groups(), True, True, True))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, debug=False)
