#!/usr/bin/env python3
"""
Módulo de estilos CSS para el detector de duplicados
Contiene todos los estilos personalizados para la interfaz Gradio
"""

def get_custom_css():
    """Retorna el CSS personalizado para la interfaz"""
    return """
    /* Estilos generales */
    .gradio-container {
        max-width: 1400px !important;
        margin: 0 auto;
    }
    
    /* Contenedor de estadísticas */
    .stats-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
        margin: 1rem 0;
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .stat-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 0.5rem;
    }
    
    .stat-label {
        font-size: 0.875rem;
        opacity: 0.9;
        margin-bottom: 0.25rem;
    }
    
    .stat-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #ffd700;
    }
    
    /* Tabla de resultados */
    .results-table {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
        margin: 1rem 0;
        background: white;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .table-header {
        display: grid;
        grid-template-columns: 80px 60px 1fr 180px 120px;
        background: linear-gradient(135deg, #6b4b9e 0%, #1e1330 100%);
        color: white;
        font-weight: bold;
        font-size: 0.875rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .header-cell {
        padding: 1rem 0.75rem;
        border-right: 1px solid rgba(255, 255, 255, 0.1);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .header-cell:last-child {
        border-right: none;
    }
    
    .header-cell.select-col input[type="checkbox"] {
        width: 18px;
        height: 18px;
        cursor: pointer;
        accent-color: #667eea;
    }
    
    /* Filas de grupos */
    .group-row {
        display: grid;
        grid-template-columns: 80px 60px 1fr 180px 120px;
        background: #f7fafc;
        border-bottom: 2px solid #e2e8f0;
        transition: all 0.2s ease;
        padding: 0.25rem 0;
    }
    
    .group-row:hover {
        background: #edf2f7;
        transform: translateX(2px);
    }
    
    .group-row.selected {
       /* background: linear-gradient(135deg, #2D3748 0%, #1e1330 100%); */
        color: white;
    }
    
    .group-cell {
        padding: 0.4rem 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-weight: 600;
    }
    
    .group-cell input[type="checkbox"] {
        width: 18px;
        height: 18px;
        cursor: pointer;
        accent-color: #667eea;
    }
    
    .filename-col {
        font-family: 'Monaco', 'Menlo', monospace;
        font-size: 0.875rem;
        background: rgba(0, 0, 0, 0.05);
        border-radius: 4px;
        padding: 0.5rem !important;
    }
    
    /* Filas de archivos */
    .file-row {
        display: grid;
        grid-template-columns: 80px 60px 1fr 180px 120px;
        border-bottom: 1px solid #e2e8f0;
        transition: background 0.2s ease;
    }
    
    .file-row:hover {
        background: #f1f5f9;
    }
    
    /* CAMBIADO: archivo prioritario ahora sin fondo especial */
    .priority-file {
        background: #fef5e7; /* Mismo color que duplicados */
        color: #744210;
        font-weight: 500;
    }
    
    .duplicate-file {
        background: #fef5e7;
        color: #744210;
    }
    
    .file-cell {
        padding: 0.5rem 0.75rem;
        display: flex;
        align-items: center;
        border-right: 1px solid rgba(0, 0, 0, 0.05);
        font-size: 0.875rem;
        gap: 0.5rem;
    }
    
    .file-cell:last-child {
        border-right: none;
    }
    
    .file-cell input[type="checkbox"] {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #667eea;
    }
    
    /* Iconos */
    .priority-icon {
        font-size: 1rem; /* CAMBIADO: 80% del tamaño original (era 1.25rem) */
        color: #d69e2e;
    }
    
    .duplicate-icon {
        font-size: 1rem;
        color: #38a169;
    }
    
    /* Rutas de archivos */
    .file-path {
        font-family: 'Monaco', 'Menlo', monospace;
        font-size: 0.65rem;
        word-break: break-all;
        line-height: 1.3;
    }
    
    /* Columnas específicas */
    .group-col {
        justify-content: center;
        font-weight: bold;
    }
    
    .select-col {
        justify-content: left;
        align-items: center;
    }
    
    .datetime-col {
        font-family: 'Monaco', 'Menlo', monospace;
        font-size: 0.8rem;
        color: #4a5568;
    }
    
    .size-col {
        justify-content: flex-end;
        font-weight: 600;
        /* color: #2d3748; */
    }
    
    /* Botones mejorados */
    .gradio-button {
        transition: all 0.2s ease;
        border-radius: 6px;
        font-weight: 500;
    }
    
    .gradio-button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }
    
    /* Inputs mejorados */
    .gradio-textbox, .gradio-number {
        border-radius: 6px;
        border: 2px solid #e2e8f0;
        transition: border-color 0.2s ease;
    }
    
    .gradio-textbox:focus, .gradio-number:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* Acordeón */
    .gradio-accordion {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        margin-top: 2rem;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .stats-container {
            grid-template-columns: 1fr;
        }
        
        .table-header,
        .group-row,
        .file-row {
            grid-template-columns: 60px 40px 1fr 100px;
        }
        
        .header-cell:nth-child(4),
        .group-cell:nth-child(4),
        .file-cell:nth-child(4) {
            display: none;
        }
        
        .file-path {
            font-size: 0.75rem;
        }
    }
    
    /* Animaciones */
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .results-table {
        animation: slideIn 0.5s ease-out;
    }
    
    /* Scrollbar personalizada */
    .gradio-html::-webkit-scrollbar {
        width: 8px;
    }
    
    .gradio-html::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
    }
    
    .gradio-html::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 4px;
    }
    
    .gradio-html::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    
    /* Estados de carga */
    .loading {
        opacity: 0.7;
        pointer-events: none;
    }
    
    .loading::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 20px;
        height: 20px;
        margin: -10px 0 0 -10px;
        border: 2px solid #f3f3f3;
        border-top: 2px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    /* Tooltips mejorados */
    .gradio-info {
        background: #667eea;
        color: white;
        border-radius: 4px;
        padding: 0.5rem;
        font-size: 0.875rem;
    }
    
    /* Mejoras para el tema oscuro */
    @media (prefers-color-scheme: dark) {
        .results-table {
            background: #1a202c;
            border-color: #2d3748;
        }
        
        .file-row {
            border-color: #2d3748;
        }
        
        .file-row:hover {
            background: #2d3748;
        }
        
        /* CAMBIADO: Color más oscuro para group-row */
        .group-row {
            background: rgb(41, 41, 55);
            border-color: #4a5568;
        }
        
        .group-row:hover {
            background: #4a5568;
        }
        
        /* CAMBIADO: archivo prioritario sin fondo especial en tema oscuro */
        .priority-file {
            background: #2d3748; /* Mismo que duplicados */
            color: #ffd700;
        }
        
        .duplicate-file {
            background: #2d3748;
            color: #a0aec0;
        }
    }
    """
