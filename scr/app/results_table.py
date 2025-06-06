import gradio as gr

def mostrar_resultados_en_arbol(resultados):
    arbol = []
    for grupo in resultados["grupos"]:
        nodo = {
            "label": f"{grupo['prioritario']} (Grupo #{grupo['numero']})",
            "children": []
        }
        for archivo in grupo["coincidentes"]:
            nodo["children"].append({
                "label": f"{archivo['ruta']} | Fecha: {archivo['fecha']} | Tamaño: {archivo['tamano']}",
                "value": archivo["seleccionado"]
            })
        arbol.append(nodo)
    return arbol

def cargar_sesion_anterior():
    # Aquí va la lógica para cargar la sesión previa desde almacenamiento
    session = obtener_sesion_guardada()
    # Seleccionar automáticamente solo los archivos "otros"
    for grupo in session["grupos"]:
        for archivo in grupo["coincidentes"]:
            archivo["seleccionado"] = archivo["categoria"] == "OTROS"
    return session

with gr.Blocks() as app:
    resultados = gr.State({})
    arbol_resultados = gr.Tree(label="Resultados de Duplicados")
    btn_cargar = gr.Button("Cargar sesión anterior")

    def actualizar_arbol():
        return mostrar_resultados_en_arbol(resultados.value)
    
    btn_cargar.click(
        lambda: cargar_sesion_anterior(),
        None,
        resultados,
    ).then(
        actualizar_arbol,
        None,
        arbol_resultados
    )