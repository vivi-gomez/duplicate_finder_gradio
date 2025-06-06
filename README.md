# duplicate_finder_gradio
Aplicación GRADIO para localizar archivos duplicados por hash mediante GPU


# 🔍 Detector de Archivos Duplicados GPU - Setup

## Requisitos del Sistema

- **Python 3.8+**
- **NVIDIA GPU** (RTX 3090 recomendada)
- **CUDA 12.x** instalado
- **Linux/Windows** (probado en Ubuntu 20.04+)

## Instalación

### 1. Crear entorno virtual

```bash
python3 -m venv venv_duplicates
source venv_duplicates/bin/activate  # Linux/Mac
# o
venv_duplicates\Scripts\activate  # Windows
```

### 2. Actualizar pip

```bash
pip install --upgrade pip
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Verificar instalación GPU

```bash
python -c "import cupy as cp; print(f'GPU disponible: {cp.cuda.is_available()}')"
```

## Uso

### Ejecutar la aplicación

```bash
python duplicate_finder_gradio.py
```

La aplicación se abrirá en: `http://localhost:7860`

### Uso básico

1. **Seleccionar directorio**: Introduce la ruta completa del directorio a analizar
2. **Configurar tamaño mínimo**: Archivos menores serán ignorados (default: 1MB)
3. **Iniciar análisis**: Haz clic en "🚀 Iniciar Análisis"
4. **Revisar resultados**: Los archivos duplicados aparecerán en la tabla
5. **Seleccionar archivos**: Usa los botones para seleccionar qué archivos eliminar
6. **Eliminar**: Genera script o elimina directamente

### Características

- **Aceleración GPU**: Usa NVIDIA RTX 3090 para cálculo de hashes
- **Detección inteligente**: Detecta duplicados incluso con nombres diferentes
- **Priorización**: Conserva automáticamente las versiones más recientes
- **Interfaz amigable**: Web interface con Gradio
- **Eliminación segura**: Genera scripts de eliminación o elimina directamente
- **Progreso en tiempo real**: Muestra el progreso del análisis

## Solución de Problemas

### Error: CuPy no encontrado

```bash
# Para CUDA 12.x
pip install cupy-cuda12x

# Para CUDA 11.x
pip install cupy-cuda11x
```

### Error: Sin GPU disponible

La aplicación funcionará en modo CPU si no detecta GPU. Para forzar CPU:

```python
# En duplicate_finder_gradio.py, línea 25
GPU_AVAILABLE = False
```

### Error: Memoria GPU insuficiente

Reduce el número de workers editando la línea 145:

```python
max_workers = min(4, (os.cpu_count() or 1) + 2)  # Reducir de 8 a 4
```

### Error: Permisos de archivo

Ejecuta con permisos de administrador o cambia permisos:

```bash
sudo python duplicate_finder_gradio.py  # Linux
# o
chmod +x delete_duplicates.sh  # Para scripts generados
```

## Configuración Avanzada

### Variables de entorno

```bash
export CUDA_VISIBLE_DEVICES=0  # Usar solo GPU 0
export GRADIO_SERVER_PORT=7860  # Puerto personalizado
```

### Optimización de memoria

Para archivos muy grandes (>1GB), edita los tamaños de chunk:

```python
# Línea 95 - chunk size para GPU
while chunk := f.read(32 * 1024 * 1024):  # 32MB en lugar de 16MB

# Línea 116 - chunk size para CPU  
while chunk := f.read(16 * 1024 * 1024):  # 16MB en lugar de 8MB
```

## Ejemplos de Uso

### Analizar directorio de descargas

```
Directorio: /home/usuario/Descargas
Tamaño mínimo: 10 MB
```

### Analizar biblioteca de medios

```
Directorio: /media/videos
Tamaño mínimo: 100 MB
```

### Analizar backup completo

```
Directorio: /backup
Tamaño mínimo: 1 MB
```

## Métricas de Rendimiento

Con RTX 3090:
- **Archivos pequeños** (1-10MB): ~500 archivos/min
- **Archivos medianos** (10-100MB): ~100 archivos/min  
- **Archivos grandes** (100MB+): ~20 archivos/min

## Seguridad

⚠️ **IMPORTANTE**: 
- Siempre haz backup antes de eliminar archivos
- Revisa cuidadosamente los archivos seleccionados
- Los scripts generados incluyen confirmaciones de seguridad
- La eliminación directa es irreversible
