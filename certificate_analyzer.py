import openai
import json
import base64
import io
import hashlib
import uuid
from PIL import Image
from datetime import datetime
from typing import Dict, Any, Optional
import PyPDF2
import docx
import re

from models import BusinessInfo

class CertificateAnalyzer:
    """Analizador de certificados de funcionamiento"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def analyze_image(self, image: Image.Image) -> BusinessInfo:
        """Analiza una imagen del certificado usando GPT-4 Vision"""
        try:
            # Convertir imagen a base64
            buffer = io.BytesIO()
            
            # Redimensionar imagen para reducir tokens pero mantener calidad de lectura
            image_resized = image.copy()
            if image_resized.width > 1200:
                ratio = 1200 / image_resized.width
                new_height = int(image_resized.height * ratio)
                image_resized = image_resized.resize((1200, new_height), Image.Resampling.LANCZOS)
            
            # Guardar como JPEG con mayor calidad para mejor OCR
            image_resized.save(buffer, format='JPEG', quality=90)
            image_data = buffer.getvalue()
            img_str = base64.b64encode(image_data).decode()
            
            # Prompt mejorado para extraer información
            enhanced_prompt = """
Analiza esta imagen del certificado de funcionamiento peruano y extrae la siguiente información:

CAMPOS REQUERIDOS:
1. **metraje**: El área del local (busca números seguidos de M², m², M^2, m^2). Ejemplo: "80.00 M²" → 80.00
2. **tipo_negocio**: El giro autorizado o actividad comercial (ej: "PANADERÍA - PASTELERÍA")
3. **direccion**: La ubicación completa del establecimiento 
4. **nombre_cliente**: Nombre o razón social del propietario/titular
5. **nombre_negocio**: Nombre comercial del establecimiento (si aparece)
6. **ruc**: Número RUC (generalmente 11 dígitos)
7. **numero_certificado**: Número del certificado (puede estar como "CERTIFICADO N°" o similar)
8. **fecha_expedicion**: Fecha de expedición del certificado
9. **zonificacion**: Tipo de zonificación (ej: "CZ", "RDM", etc.)

INSTRUCCIONES:
- Lee CUIDADOSAMENTE todo el texto visible
- Para el metraje, busca números con decimales seguidos de unidades de área
- Si no encuentras un campo, devuelve null
- Para fechas, mantén el formato original
- Para números, mantén el formato numérico

Responde SOLO en formato JSON válido:
{
    "metraje": numero_o_null,
    "tipo_negocio": "texto_o_null",
    "direccion": "texto_o_null", 
    "nombre_cliente": "texto_o_null",
    "nombre_negocio": "texto_o_null",
    "ruc": "texto_o_null",
    "numero_certificado": "texto_o_null",
    "fecha_expedicion": "texto_o_null",
    "zonificacion": "texto_o_null"
}
            """
            
            # Realizar petición a OpenAI
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": enhanced_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_str}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=800,
                temperature=0
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar respuesta para extraer JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()
            
            # Parsear JSON
            extracted_data = json.loads(result_text)
            
            # Limpiar y validar datos
            cleaned_data = self._clean_extracted_data(extracted_data)
            
            return BusinessInfo.from_dict(cleaned_data)
            
        except json.JSONDecodeError as e:
            print(f"Error parseando JSON: {str(e)}")
            print(f"Respuesta recibida: {result_text}")
            return BusinessInfo()
        except Exception as e:
            print(f"Error analizando imagen del certificado: {str(e)}")
            return BusinessInfo()
    
    def analyze_document(self, document_text: str) -> BusinessInfo:
        """Analiza el texto del documento usando GPT-3.5-turbo"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": """Analiza este certificado de funcionamiento y extrae:
1. Metraje/área del local (en m2) - busca números seguidos de m2, metros cuadrados, etc.
2. Número máximo de ocupantes/trabajadores 
3. Tipo de negocio/actividad comercial
4. Dirección del local
5. Nombre del propietario/empresa
6. RUC
7. Número del certificado
8. Fecha de expedición
9. Zonificación

Responde SOLO en formato JSON válido: 
{
    "metraje": numero_o_null,
    "ocupantes_maximo": numero_o_null,
    "tipo_negocio": "texto_o_null",
    "direccion": "texto_o_null",
    "nombre_cliente": "texto_o_null",
    "ruc": "texto_o_null",
    "numero_certificado": "texto_o_null",
    "fecha_expedicion": "texto_o_null",
    "zonificacion": "texto_o_null"
}"""
                    },
                    {"role": "user", "content": document_text[:3000]}
                ]
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar respuesta para extraer JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()
            
            extracted_data = json.loads(result_text)
            cleaned_data = self._clean_extracted_data(extracted_data)
            
            return BusinessInfo.from_dict(cleaned_data)
            
        except Exception as e:
            print(f"Error analizando documento: {str(e)}")
            return BusinessInfo()
    
    def _clean_extracted_data(self, data: dict) -> dict:
        """Limpia y valida los datos extraídos"""
        cleaned_data = {}
        
        # Limpiar metraje
        if data.get('metraje'):
            metraje_str = str(data['metraje']).replace(',', '.').replace('M²', '').replace('m²', '').replace('M^2', '').replace('m^2', '').strip()
            try:
                cleaned_data['metraje'] = float(metraje_str)
            except:
                cleaned_data['metraje'] = None
        else:
            cleaned_data['metraje'] = None
        
        # Limpiar otros campos
        for field in ['tipo_negocio', 'direccion', 'nombre_cliente', 'nombre_negocio', 'ruc', 'numero_certificado', 'fecha_expedicion', 'zonificacion', 'ocupantes_maximo']:
            value = data.get(field)
            if value and str(value).strip() and str(value).strip().lower() not in ['null', 'none', '', 'n/a']:
                if field == 'ocupantes_maximo':
                    try:
                        cleaned_data[field] = int(value)
                    except:
                        cleaned_data[field] = None
                else:
                    cleaned_data[field] = str(value).strip()
            else:
                cleaned_data[field] = None
        
        return cleaned_data
    
    def generate_certificate_id(self, image_data: bytes, ruc: Optional[str] = None) -> str:
        """Genera un ID único para el certificado"""
        image_hash = hashlib.md5(image_data).hexdigest()[:12]
        
        if ruc:
            return f"CERT_{ruc}_{image_hash}"
        else:
            return f"CERT_{image_hash}_{uuid.uuid4().hex[:8]}"

def extract_text_from_document(uploaded_file) -> str:
    """Extrae texto de documentos PDF/Word"""
    text = ""
    try:
        if uploaded_file.type == "application/pdf":
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = docx.Document(uploaded_file)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        elif uploaded_file.type == "text/plain":
            text = str(uploaded_file.read(), "utf-8")
    except Exception as e:
        print(f"Error extrayendo texto: {str(e)}")
    
    return text