# info_archivo_blend.py (VERSIÓN CORREGIDA)

import bpy
import json
import os
import sys

def get_blend_file_info():
    """
    Recopila la información clave del archivo .blend y la retorna
    en un diccionario.
    """
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    blend_data = bpy.context.blend_data

    # Datos bpy.app
    version = bpy.app.version_string
    
    # Intenta obtener el nombre de la cámara activa de forma segura
    active_camera_name = "N/A"
    if scene.camera and scene.camera.name:
        active_camera_name = scene.camera.name

    
    
    # Intenta obtener el nombre de la View Layer activa de forma segura
    view_layer_name = "N/A"
    # El acceso correcto a la View Layer de contexto es scene.view_layer (singular)
    #if scene.view_layers and scene.view_layers.name:
        #view_layers_name = scene.view_layers.name
        
    # Recopilación de metadatos
    info = {
        "file_path": bpy.data.filepath if bpy.data.filepath else "Sin Nombre",
        "file_name": os.path.basename(bpy.data.filepath) if bpy.data.filepath else "Sin Nombre",
        "version_blender": version,
        "active_scene": scene.name,
        # CORRECCIÓN: Usar scene.view_layer (singular) en lugar de scene.view_layers.active
        "view_layer": view_layer.name,
        "active_camera": active_camera_name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "frame_rate": scene.render.fps,
    }
    
    return info

def print_json_output(data):
    """
    Serializa el diccionario a una cadena JSON e imprime al stdout.
    """
    try:
        json_output = json.dumps(data, indent=None)
        # 1. Imprimir solo el JSON
        print(json_output)
        
    except Exception as e:
        # Enviar error de JSON al stderr
        print(f"ERROR_JSON: Fallo al crear JSON: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        info_data = get_blend_file_info()
        print_json_output(info_data)
    except Exception as e:
        # Capturar cualquier otro error inesperado y enviarlo a stderr
        print(f"ERROR_BLENDER_SCRIPT: Fallo en el script: {e}", file=sys.stderr)
        
    # Forzar salida limpia para evitar más "basura" en stdout/stderr
    sys.stdout.flush()
    sys.exit(0)