import bpy
import json
import os
import sys

def format_blender_version(v_tuple):
    """
    Convierte la tupla de versión de Blender en un string amigable.
    Mapea [4, 5, 91] -> 'Blender 4.5.8 LTS'
    Mapea [5, 1, 30] -> 'Blender 5.1.1'
    """
    major, minor, patch = v_tuple
    
    # Lógica específica para tus versiones de trabajo
    if major == 4 and minor == 5:
        return " 4.5.8 LTS"
    
    if major == 5 and minor == 1:
        # En la serie 5.x, el tercer valor suele ser la build interna
        # Lo normalizamos a la versión comercial 5.1.1
        return " 5.1.1"
        
    return f"Blender {major}.{minor}.{patch}"

def get_blend_file_info():
    # Fallback seguro para escena
    scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    
    # OBTENER VERSIÓN FORMATEADA
    # bpy.data.version devuelve algo como (5, 1, 30)
    version_raw = bpy.data.version
    version_string = format_blender_version(version_raw)
    
    # Cámara
    active_camera_name = scene.camera.name if scene.camera else "N/A"
    
    # View Layer
    try:
        view_layer_name = bpy.context.view_layer.name
    except:
        view_layer_name = scene.view_layers[0].name if scene.view_layers else "N/A"

    # Cálculo de resolución real
    ratio = scene.render.resolution_percentage / 100

    return {
        "file_path": bpy.data.filepath if bpy.data.filepath else "Sin Nombre",
        "file_name": os.path.basename(bpy.data.filepath) if bpy.data.filepath else "Sin Nombre",
        "version_blender": version_string, # Ahora es un String, no una tupla
        "active_scene": scene.name,
        "view_layer": view_layer_name,
        "active_camera": active_camera_name,
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "resolution_x": int(scene.render.resolution_x * ratio),
        "resolution_y": int(scene.render.resolution_y * ratio),
        "frame_rate": int(scene.render.fps),
        "engine": scene.render.engine 
    }

def print_json_output(data):
    try:
        # Usamos un prefijo único para que PySide6 lo encuentre sin error
        json_output = json.dumps(data, separators=(',', ':'))
        sys.stdout.write(f"JCRENDER_DATA:{json_output}\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"ERROR_JSON: {str(e)}\n")


if __name__ == "__main__":
    try:
        info_data = get_blend_file_info()
        print_json_output(info_data)
    except Exception as e:
        sys.stderr.write(f"ERROR_EXTRACTOR: {str(e)}\n")
    # Salida limpia para no ensuciar el buffer de PySide6
    sys.exit(0)