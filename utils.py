"""
Utilidades para el manejo de imágenes y archivos en el sistema de seguros
"""

import base64
import io
from PIL import Image
from typing import List, Optional
import streamlit as st

from models import SerializableImage

def pil_image_to_base64(pil_image: Image.Image, format: str = "JPEG") -> str:
    """
    Convierte una imagen PIL a string base64
    
    Args:
        pil_image: Imagen PIL
        format: Formato de la imagen (JPEG, PNG, etc.)
    
    Returns:
        str: Imagen codificada en base64
    """
    buffer = io.BytesIO()
    pil_image.save(buffer, format=format)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return img_str

def base64_to_pil_image(base64_str: str) -> Image.Image:
    """
    Convierte string base64 a imagen PIL
    
    Args:
        base64_str: Imagen codificada en base64
    
    Returns:
        Image.Image: Imagen PIL
    """
    img_data = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(img_data))

def resize_image_for_api(image: Image.Image, max_width: int = 1200, quality: int = 90) -> Image.Image:
    """
    Redimensiona imagen para optimizar uso de API manteniendo calidad
    
    Args:
        image: Imagen PIL original
        max_width: Ancho máximo en píxeles
        quality: Calidad de compresión
    
    Returns:
        Image.Image: Imagen redimensionada
    """
    if image.width > max_width:
        ratio = max_width / image.width
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    
    return image

def validate_image_file(uploaded_file) -> bool:
    """
    Valida que el archivo subido sea una imagen válida
    
    Args:
        uploaded_file: Archivo subido por Streamlit
    
    Returns:
        bool: True si es una imagen válida
    """
    try:
        image = Image.open(uploaded_file)
        # Verificar que se puede leer la imagen
        image.verify()
        return True
    except Exception as e:
        st.error(f"Archivo de imagen inválido: {str(e)}")
        return False

def create_image_preview(images: List[SerializableImage], max_cols: int = 4) -> None:
    """
    Crea preview de imágenes en Streamlit
    
    Args:
        images: Lista de imágenes serializables
        max_cols: Número máximo de columnas para mostrar
    """
    if not images:
        return
    
    # Mostrar hasta max_cols imágenes
    display_count = min(len(images), max_cols)
    cols = st.columns(display_count)
    
    for i in range(display_count):
        with cols[i]:
            try:
                pil_image = images[i].to_pil_image()
                st.image(pil_image, caption=f"Imagen {i+1}", use_column_width=True)
            except Exception as e:
                st.error(f"Error mostrando imagen {i+1}: {str(e)}")
    
    # Mostrar contador si hay más imágenes
    if len(images) > max_cols:
        st.info(f"+ {len(images) - max_cols} imagen(es) más")

def get_image_info(serializable_image: SerializableImage) -> dict:
    """
    Obtiene información de una imagen serializable
    
    Args:
        serializable_image: Imagen serializable
    
    Returns:
        dict: Información de la imagen
    """
    try:
        pil_image = serializable_image.to_pil_image()
        return {
            "filename": serializable_image.filename,
            "format": serializable_image.format,
            "size": pil_image.size,
            "mode": pil_image.mode,
            "data_size_kb": len(serializable_image.data) * 3/4 / 1024  # Aproximado para base64
        }
    except Exception as e:
        return {
            "filename": serializable_image.filename,
            "format": serializable_image.format,
            "error": str(e)
        }

def compress_image_if_needed(image: Image.Image, max_size_kb: int = 500) -> Image.Image:
    """
    Comprime imagen si excede el tamaño máximo
    
    Args:
        image: Imagen PIL
        max_size_kb: Tamaño máximo en KB
    
    Returns:
        Image.Image: Imagen comprimida si fue necesario
    """
    # Convertir a bytes para medir tamaño
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=90)
    size_kb = len(buffer.getvalue()) / 1024
    
    if size_kb <= max_size_kb:
        return image
    
    # Reducir calidad gradualmente
    for quality in [80, 70, 60, 50]:
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=quality)
        size_kb = len(buffer.getvalue()) / 1024
        
        if size_kb <= max_size_kb:
            # Cargar imagen comprimida
            buffer.seek(0)
            return Image.open(buffer)
    
    # Si aún es muy grande, redimensionar
    scale_factor = (max_size_kb / size_kb) ** 0.5
    new_width = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)
    
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

def batch_process_uploaded_files(uploaded_files, file_type: str = "image") -> List[SerializableImage]:
    """
    Procesa múltiples archivos subidos
    
    Args:
        uploaded_files: Lista de archivos subidos
        file_type: Tipo de archivo esperado
    
    Returns:
        List[SerializableImage]: Lista de imágenes procesadas
    """
    processed_images = []
    
    for i, uploaded_file in enumerate(uploaded_files):
        try:
            if validate_image_file(uploaded_file):
                # Resetear puntero del archivo
                uploaded_file.seek(0)
                
                # Cargar imagen
                pil_image = Image.open(uploaded_file)
                
                # Optimizar imagen
                pil_image = resize_image_for_api(pil_image)
                pil_image = compress_image_if_needed(pil_image)
                
                # Convertir a SerializableImage
                filename = uploaded_file.name or f"{file_type}_{i+1}.jpg"
                serializable_image = SerializableImage.from_pil_image(pil_image, filename)
                processed_images.append(serializable_image)
                
        except Exception as e:
            st.error(f"Error procesando {uploaded_file.name}: {str(e)}")
    
    return processed_images

def display_image_gallery(images: List[SerializableImage], title: str = "Galería") -> None:
    """
    Muestra galería de imágenes con información detallada
    
    Args:
        images: Lista de imágenes
        title: Título de la galería
    """
    if not images:
        return
    
    st.subheader(title)
    
    for i, img in enumerate(images):
        with st.expander(f"📷 {img.filename}", expanded=(i == 0)):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                try:
                    pil_image = img.to_pil_image()
                    st.image(pil_image, use_column_width=True)
                except Exception as e:
                    st.error(f"Error mostrando imagen: {str(e)}")
            
            with col2:
                info = get_image_info(img)
                st.json(info)