import gradio as gr
from typing import List, Dict, Any

def format_file_row(file: Dict[str, Any], is_prioritary: bool) -> List[Any]:
    # Checkbox, estrella para prioritatario, ruta, fecha, tamaño
    return [
        gr.Checkbox(value=file["seleccionado"], label="", elem_id=f"file-check-{file['id']}"),
        "⭐" if is_prioritary else "",
        gr.HighlightedText(value=file["ruta"], elem_id=f"file-path-{file['id']}"),
        file["fecha"],
        f"{file['tamano']:.2f} MB"
    ]

def build_results_table(groups: List[Dict[str, Any]]) -> gr.Dataframe:
    rows = []
    for group in groups:
        # Cabecera de grupo: checkbox, nombre, grupo, (columnas vacías para fecha y tamaño)
        rows.append([
            gr.Checkbox(value=group["seleccionado"], label="", elem_id=f"group-check-{group['numero']}"),
            "",
            f"{group['prioritario']} (Grupo {group['numero']})",
            "",
            ""
        ])
        # Archivos del grupo
        for file in group["files"]:
            is_prioritary = (file["ruta"] == group["prioritario"])
            rows.append(format_file_row(file, is_prioritary))
    headers = ["", "⭐", "Ruta", "Fecha Modificación", "Tamaño"]
    return gr.Dataframe(
        value=rows,
        headers=headers,
        interactive=True,
        elem_id="duplicate-results-table"
    )