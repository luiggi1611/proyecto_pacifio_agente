import streamlit as st
import openai
from PIL import Image
import json
from datetime import datetime
import tempfile
import os
from gtts import gTTS
import PyPDF2
import docx
import re
import base64
import io
import openai
import json
import base64
import io
import uuid
import hashlib
from PIL import Image
from datetime import datetime
import re

def generate_certificate_id(image_data, ruc=None):
    """
    Genera un ID único para el certificado basado en el contenido de la imagen y RUC
    
    Args:
        image_data: bytes - Datos de la imagen
        ruc: str - RUC del establecimiento (si está disponible)
    
    Returns:
        str: ID único del certificado
    """
    # Crear hash del contenido de la imagen
    image_hash = hashlib.md5(image_data).hexdigest()[:12]
    
    # Si hay RUC, usarlo como parte del ID
    if ruc:
        return f"CERT_{ruc}_{image_hash}"
    else:
        return f"CERT_{image_hash}_{uuid.uuid4().hex[:8]}"

def clean_extracted_data(data):
    """
    Limpia y valida los datos extraídos
    
    Args:
        data: dict - Datos extraídos del certificado
    
    Returns:
        dict: Datos limpios y validados
    """
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
    for field in ['tipo_negocio', 'direccion', 'nombre_cliente', 'nombre_negocio', 'ruc', 'numero_certificado', 'fecha_expedicion', 'zonificacion']:
        value = data.get(field)
        if value and str(value).strip() and str(value).strip().lower() not in ['null', 'none', '', 'n/a']:
            cleaned_data[field] = str(value).strip()
        else:
            cleaned_data[field] = None
    
    return cleaned_data


# Configuración de página
st.set_page_config(
    page_title="🤖 Agente de Seguros IA",
    page_icon="🤖",
    layout="wide"
)

class InsuranceAgent:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def analyze_document_imagev2(self, image: Image.Image) -> dict:
        """Analiza una imagen del certificado usando GPT-4 Vision"""
        try:
            # Convertir imagen a base64
            buffer = io.BytesIO()
            # Redimensionar imagen para reducir tokens
            image_resized = image.copy()
            if image_resized.width > 1024:
                ratio = 1024 / image_resized.width
                new_height = int(image_resized.height * ratio)
                image_resized = image_resized.resize((1024, new_height), Image.Resampling.LANCZOS)
            
            image_resized.save(buffer, format='JPEG', quality=85)
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Más económico que gpt-4-vision-preview
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Analiza esta imagen del certificado de funcionamiento y extrae:
1. Metraje/área del local (en m2)
2. Número máximo de ocupantes/trabajadores
3. Tipo de negocio/actividad comercial
4. Dirección del local
5. Nombre del propietario/empresa

Lee cuidadosamente todo el texto visible en la imagen.
Responde SOLO en formato JSON válido:
{"metraje": numero_o_null, "ocupantes_maximo": numero_o_null, "tipo_negocio": "texto_o_null", "direccion": "texto_o_null", "nombre_cliente": "texto_o_null"}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_str}",
                                    "detail": "low"  # Usar resolución baja para reducir costos
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar respuesta para extraer JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()
            
            return json.loads(result_text)
            
        except Exception as e:
            st.error(f"Error analizando imagen del certificado: {str(e)}")
            return {}
    def analyze_document_image(self, image_path_or_object, api_key):
        """
        Analiza una imagen del certificado usando GPT-4 Vision con identificadores únicos
        
        Args:
            image_path_or_object: str (ruta del archivo) o PIL.Image object
            api_key: str - Tu API key de OpenAI
        
        Returns:
            dict: Datos extraídos del certificado con identificadores
        """
        try:
            # Inicializar cliente OpenAI
            client = openai.OpenAI(api_key=api_key)
            
            # Cargar imagen si es una ruta
            if isinstance(image_path_or_object, str):
                image = Image.open(image_path_or_object)
            else:
                image = image_path_or_object
            
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
            
            # Prompt mejorado para extraer más información
            enhanced_prompt = """
    Analiza esta imagen del certificado de funcionamiento peruano y extrae la siguiente información:

    CAMPOS REQUERIDOS:
    1. **metraje**: El área del local (busca números seguidos de M², m², M^2, m^2). Ejemplo: "80.00 M²" → 80.00
    2. **tipo_negocio**: El giro autorizado o actividad comercial (ej: "PANADERÍA - PASTELERÍA")
    3. **direccion**: La ubicación completa del establecimiento 
    4. **nombre_cliente**: Nombre o razón social del propietario/titular
    5. **nombre_negocio**: Nombre comercial del establecimiento (si aparece)
    6. **ruc**: Número RUC (generalmente 11 dígitos)
    7. **numero_certificado**: Número del certificado (puede estar como "CERTIFICADO Nº" o similar)
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
            response = client.chat.completions.create(
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
                                    "detail": "high"  # Usar alta resolución para mejor OCR
                                }
                            }
                        ]
                    }
                ],
                max_tokens=800,
                temperature=0  # Reducir temperatura para respuestas más consistentes
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
            cleaned_data = clean_extracted_data(extracted_data)
            
            # Generar ID único del certificado
            certificate_id = generate_certificate_id(image_data, cleaned_data.get('ruc'))
            
            # Agregar metadatos
            result = {
                "id_certificado": certificate_id,
                "fecha_procesamiento": datetime.now().isoformat(),
                "version_procesador": "2.0",
                "datos_extraidos": cleaned_data,
                "confiabilidad": "alta" if all([
                    cleaned_data.get('ruc'),
                    cleaned_data.get('numero_certificado'),
                    cleaned_data.get('metraje')
                ]) else "media"
            }
            
            return cleaned_data
            
        except json.JSONDecodeError as e:
            print(f"Error parseando JSON: {str(e)}")
            print(f"Respuesta recibida: {result_text}")
            return {
                "error": "Error parseando respuesta JSON",
                "respuesta_cruda": result_text,
                "fecha_procesamiento": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error analizando imagen del certificado: {str(e)}")
            return {
                "error": str(e),
                "fecha_procesamiento": datetime.now().isoformat()
            }
    def analyze_document(self, document_text: str) -> dict:
        """Analiza el documento cargado usando GPT-3.5-turbo"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": """Analiza este certificado de funcionamiento y extrae:
                    1. Metraje/área del local (en m2) - busca números seguidos de m2, metros cuadrados, etc.
                    2. Número máximo de ocupantes/trabajadores 
                    3. Tipo de negocio/actividad comercial
                    4. Dirección del local
                    5. Nombre del propietario/empresa
                    
                    Responde SOLO en formato JSON válido: 
                    {"metraje": numero_o_null, "ocupantes_maximo": numero_o_null, "tipo_negocio": "texto_o_null", "direccion": "texto_o_null", "nombre_cliente": "texto_o_null"}"""},
                    {"role": "user", "content": document_text[:3000]}
                ]
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar respuesta para extraer JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()
            
            return json.loads(result_text)
            
        except Exception as e:
            st.error(f"Error analizando documento: {str(e)}")
            return {}
    
    def estimate_property_value(self, metraje: float, tipo_negocio: str) -> dict:
        """Estima valores basado en metraje y tipo de negocio"""
        # Factores base por m2 según tipo de negocio (en soles)
        factores = {
            "restaurante": {"inventario": 200, "mobiliario": 350, "infraestructura": 300},
            "tienda": {"inventario": 300, "mobiliario": 150, "infraestructura": 200},
            "oficina": {"inventario": 80, "mobiliario": 250, "infraestructura": 180},
            "farmacia": {"inventario": 500, "mobiliario": 300, "infraestructura": 250},
            "bar": {"inventario": 250, "mobiliario": 400, "infraestructura": 350},
            "panadería": {"inventario": 180, "mobiliario": 280, "infraestructura": 220},
            "default": {"inventario": 200, "mobiliario": 250, "infraestructura": 200}
        }
        
        # Buscar tipo más cercano
        factor_key = "default"
        tipo_lower = tipo_negocio.lower() if tipo_negocio else ""
        for key in factores.keys():
            if key in tipo_lower:
                factor_key = key
                break
        
        factor = factores[factor_key]
        
        # Calcular valores en soles peruanos
        tasa_cambio = 3.8
        
        inventario = metraje * factor["inventario"] * tasa_cambio
        mobiliario = metraje * factor["mobiliario"] * tasa_cambio
        infraestructura = metraje * factor["infraestructura"] * tasa_cambio
        total = inventario + mobiliario + infraestructura
        
        return {
            "inventario": inventario,
            "mobiliario": mobiliario,
            "infraestructura": infraestructura,
            "total": total,
            "descripcion": f"Estimación basada en {metraje}m² para {tipo_negocio or 'negocio comercial'}"
        }
    
    def generate_policy(self, info: dict) -> str:
        """Genera la póliza de seguro"""
        return f"""🏢 **PÓLIZA DE SEGURO COMERCIAL**
Fecha: {datetime.now().strftime('%d/%m/%Y')}

**DATOS DEL ASEGURADO:**
• Nombre: {info.get('nombre_cliente', 'Por definir')}
• Dirección: {info.get('direccion', 'Por definir')}
• Tipo de negocio: {info.get('tipo_negocio', 'Comercio general')}
• Área del local: {info.get('metraje', 'N/A')}m²
• Ocupantes máximo: {info.get('ocupantes_maximo', 'Por definir')}

**COBERTURAS:**
• Inventario/Mercancía: S/ {info.get('valor_inventario', 0):,.2f}
• Mobiliario y Equipos: S/ {info.get('valor_mobiliario', 0):,.2f}
• Mejoras al local: S/ {info.get('valor_infraestructura', 0):,.2f}
• **SUMA ASEGURADA TOTAL: S/ {info.get('valor_total', 0):,.2f}**

**RIESGOS CUBIERTOS:**
✅ Incendio y explosión
✅ Robo y hurto
✅ Daños por agua
✅ Fenómenos naturales
✅ Responsabilidad civil
✅ Gastos de reposición
✅ Lucro cesante (hasta 6 meses)

**TÉRMINOS:**
• Vigencia: 12 meses renovables
• Deducible: 10% del siniestro (mínimo S/ 500)
• Prima anual estimada: S/ {info.get('valor_total', 0) * 0.025:,.2f}
• Modalidad de pago: Mensual, trimestral o anual

**EXCLUSIONES PRINCIPALES:**
❌ Daños por guerra o terrorismo
❌ Desgaste natural
❌ Negligencia comprobada
❌ Eventos nucleares

Esta póliza ha sido diseñada específicamente para tu negocio basada en la información proporcionada.
"""
    
    def generate_audio_summary(self, info: dict) -> tuple:
        """Genera resumen en audio usando gTTS"""
        try:
            summary_text = f"""
Resumen de tu póliza de seguro comercial.

Tu negocio de tipo {info.get('tipo_negocio', 'comercial')} ubicado en {info.get('direccion', 'la dirección proporcionada')}, 
con un área de {info.get('metraje', 0)} metros cuadrados, queda asegurado por un valor total de 
{info.get('valor_total', 0):,.0f} soles.

Las coberturas incluyen inventario por {info.get('valor_inventario', 0):,.0f} soles, 
mobiliario por {info.get('valor_mobiliario', 0):,.0f} soles, 
y mejoras al local por {info.get('valor_infraestructura', 0):,.0f} soles.

La póliza cubre incendio, robo, daños por agua, fenómenos naturales y responsabilidad civil, 
con una prima anual estimada de {info.get('valor_total', 0) * 0.025:,.0f} soles.

Esta póliza ha sido personalizada para proteger tu negocio de manera integral.
            """
            
            # Generar audio con gTTS
            tts = gTTS(text=summary_text, lang='es', slow=False)
            
            # Guardar en archivo temporal
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                return tmp_file.name, summary_text
                
        except Exception as e:
            st.error(f"Error generando audio: {str(e)}")
            return None, None
    
    def chat_response(self, user_message: str, context: str = "") -> str:
        """Genera respuesta conversacional usando GPT-3.5-turbo"""
        try:
            system_msg = f"""Eres un agente de seguros amigable especializado en seguros comerciales en Perú. 
Mantén una conversación natural y útil sobre seguros comerciales.

Contexto actual: {context}

Responde de manera breve y directa."""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_message}
                ]
            )
            return response.choices[0].message.content
        except:
            return "Entiendo. ¿En qué más puedo ayudarte con tu póliza de seguros?"

def extract_text_from_document(uploaded_file):
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
        st.error(f"Error extrayendo texto: {str(e)}")
    
    return text

def generate_document_analysis_summary(extracted_info: dict, is_image: bool = False) -> str:
    """Genera el resumen del análisis del documento o imagen"""
    doc_type = "imagen del certificado" if is_image else "certificado de funcionamiento"
    summary = f"📄 **He analizado tu {doc_type}:**\n\n"
    
    if extracted_info.get('nombre_cliente'):
        summary += f"• **Cliente:** {extracted_info['nombre_cliente']}\n"
    if extracted_info.get('direccion'):
        summary += f"• **Dirección:** {extracted_info['direccion']}\n"
    if extracted_info.get('tipo_negocio'):
        summary += f"• **Tipo de negocio:** {extracted_info['tipo_negocio']}\n"
    if extracted_info.get('ocupantes_maximo'):
        summary += f"• **Ocupantes máximo:** {extracted_info['ocupantes_maximo']} personas\n"
    if extracted_info.get('metraje'):
        summary += f"• **Área:** {extracted_info['metraje']} m²\n"
    
    if not extracted_info.get('metraje'):
        summary += f"\n❓ No pude encontrar el metraje exacto en la {doc_type}. ¿Podrías decirme cuántos metros cuadrados tiene tu local?"
    else:
        summary += "\n📸 **Siguiente paso:** Necesito fotos del local para hacer la valuación."
    
    if is_image and not any(extracted_info.values()):
        summary += f"\n💡 **Tip:** Si la imagen no se lee bien, puedes intentar con una foto más clara o usar el tab 'Documento' si tienes el archivo digital."
    
    return summary

def extract_numbers_from_text(text: str) -> list:
    """Extrae números de un texto"""
    return re.findall(r'\d+\.?\d*', text)

def main():
    st.title("🤖 Agente de Seguros IA")
    st.markdown("**Conversación natural para crear tu póliza personalizada**")
    
    # Configurar API Key
    if "openai_api_key" not in st.session_state:
        st.session_state.openai_api_key = ""
    
    api_key = st.sidebar.text_input(
        "🔑 API Key de OpenAI:",
        type="password",
        value=st.session_state.openai_api_key,
        help="Usa GPT-3.5-turbo para costos mínimos"
    )
    
    if not api_key:
        st.warning("⚠️ Ingresa tu API Key de OpenAI para comenzar")
        st.info("💡 **Tip:** Este agente usa GPT-3.5-turbo y GPT-4o-mini (las APIs más económicas) para minimizar costos")
        return
    
    st.session_state.openai_api_key = api_key
    
    # Inicializar agente
    if "agent" not in st.session_state:
        st.session_state.agent = InsuranceAgent(api_key)
    
    # Inicializar estado del agente
    if "conversation" not in st.session_state:
        st.session_state.conversation = []
        st.session_state.business_info = {}
        st.session_state.step = "welcome"
        
        # Mensaje inicial
        welcome_msg = """¡Hola! 👋 Soy tu agente de seguros comerciales.

Estoy aquí para ayudarte a crear una póliza personalizada para tu negocio. Puedo trabajar con:
📄 Certificados de funcionamiento (PDF/Word/TXT)
📸 Fotos del certificado de funcionamiento  
📷 Fotos del local comercial

¿Podrías empezar compartiéndome el certificado de funcionamiento (documento o foto) o contándome sobre tu negocio?"""
        
        st.session_state.conversation.append({"role": "assistant", "content": welcome_msg})
    
    # Interfaz principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💬 Conversación")
        
        # Mostrar conversación
        for message in st.session_state.conversation:
            if message["role"] == "user":
                st.chat_message("user").write(message["content"])
            else:
                st.chat_message("assistant").write(message["content"])
        
        # Input del usuario
        user_input = st.chat_input("Escribe tu mensaje aquí...")
        
        if user_input:
            # Agregar mensaje del usuario
            st.session_state.conversation.append({"role": "user", "content": user_input})
            
            # Procesar mensaje
            with st.spinner("Pensando..."):
                response = process_user_message(user_input)
                st.session_state.conversation.append({"role": "assistant", "content": response})
            
            st.rerun()
    
    with col2:
        st.subheader("📁 Cargar Archivos")
        
        # Cargar certificado (documento o imagen)
        st.markdown("**📄 Certificado de Funcionamiento:**")
        
        # Tabs para diferentes tipos de certificado
        tab1, tab2 = st.tabs(["📄 Documento", "📸 Foto"])
        
        with tab1:
            uploaded_doc = st.file_uploader(
                "Sube tu certificado (PDF, Word, TXT):",
                type=['pdf', 'docx', 'txt'],
                help="Archivo de documento",
                key="cert_doc"
            )
            
            if uploaded_doc and f"doc_{uploaded_doc.name}" not in st.session_state.business_info:
                with st.spinner("Analizando documento..."):
                    document_text = extract_text_from_document(uploaded_doc)
                    
                    if document_text:
                        # Analizar documento
                        extracted_info = st.session_state.agent.analyze_document(document_text)
                        print(extracted_info)
                        # Actualizar información del negocio
                        st.session_state.business_info.update(extracted_info)
                        st.session_state.business_info[f"doc_{uploaded_doc.name}"] = True
                        
                        # Generar respuesta sobre el análisis
                        summary = generate_document_analysis_summary(extracted_info)
                        st.session_state.conversation.append({"role": "assistant", "content": summary})
                        st.session_state.step = "document_analyzed"
                    
                st.success(f"✅ Documento analizado: {uploaded_doc.name}")
                st.rerun()
        
        with tab2:
            uploaded_cert_image = st.file_uploader(
                "Sube una foto del certificado:",
                type=['jpg', 'jpeg', 'png'],
                help="Foto clara del certificado de funcionamiento",
                key="cert_image"
            )
            
            if uploaded_cert_image and f"cert_img_{uploaded_cert_image.name}" not in st.session_state.business_info:
                # Mostrar preview de la imagen
                cert_image = Image.open(uploaded_cert_image)
                st.image(cert_image, caption="Certificado cargado", use_column_width=True)
                
                with st.spinner("Leyendo certificado con IA..."):
                    # Analizar imagen del certificado
                    extracted_info = st.session_state.agent.analyze_document_image(cert_image,api_key)
                    print(extracted_info)
                    # Actualizar información del negocio
                    st.session_state.business_info.update(extracted_info)
                    st.session_state.business_info[f"cert_img_{uploaded_cert_image.name}"] = True
                    
                    # Generar respuesta sobre el análisis
                    summary = generate_document_analysis_summary(extracted_info, is_image=True)
                    st.session_state.conversation.append({"role": "assistant", "content": summary})
                    st.session_state.step = "document_analyzed"
                
                st.success(f"✅ Certificado (imagen) analizado: {uploaded_cert_image.name}")
                st.rerun()
        
        # Cargar fotos del local
        st.markdown("**📸 Fotos del Local:**")
        uploaded_images = st.file_uploader(
            "Fotos del interior y exterior:",
            type=['jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            help="Fotos que muestren inventario, mobiliario y espacio",
            key="local_images"
        )
        
        if uploaded_images and len(uploaded_images) != st.session_state.business_info.get('num_images', 0):
            st.session_state.business_info['num_images'] = len(uploaded_images)
            
            # Mostrar preview
            cols = st.columns(2)
            for i, img in enumerate(uploaded_images[:4]):
                with cols[i % 2]:
                    st.image(Image.open(img), caption=f"Foto {i+1}", use_column_width=True)
            
            if len(uploaded_images) > 4:
                st.info(f"+ {len(uploaded_images) - 4} fotos más")
            
            # Procesar fotos si tenemos metraje
            if st.session_state.business_info.get('metraje'):
                with st.spinner("Analizando fotos y calculando valuación..."):
                    valuation = st.session_state.agent.estimate_property_value(
                        st.session_state.business_info['metraje'],
                        st.session_state.business_info.get('tipo_negocio', '')
                    )
                    
                    # Actualizar información con valuación
                    st.session_state.business_info.update(valuation)
                    
                    response = f"""📸 ¡Excelente! He analizado las {len(uploaded_images)} fotos de tu local.

**💰 Valuación estimada:**
• Inventario/Mercancía: S/ {valuation['inventario']:,.2f}
• Mobiliario y Equipos: S/ {valuation['mobiliario']:,.2f}  
• Infraestructura: S/ {valuation['infraestructura']:,.2f}
• **Total estimado: S/ {valuation['total']:,.2f}**

{valuation['descripcion']}

¿Te parece correcta esta valuación? Si estás de acuerdo, procederé a generar tu póliza."""
                    
                    st.session_state.conversation.append({"role": "assistant", "content": response})
                    st.session_state.step = "photos_analyzed"
            else:
                response = f"He recibido {len(uploaded_images)} fotos del local. Ahora necesito que me confirmes el metraje para poder hacer la valuación correcta."
                st.session_state.conversation.append({"role": "assistant", "content": response})
            
            st.rerun()
        
        # Estado del proceso
        st.subheader("📊 Progreso")
        
        progress_items = [
            ("📄 Certificado", bool(st.session_state.business_info.get('direccion') or st.session_state.business_info.get('tipo_negocio'))),
            ("📏 Metraje", bool(st.session_state.business_info.get('metraje'))),
            ("📸 Fotos Local", st.session_state.business_info.get('num_images', 0) > 0),
            ("💰 Valuación", bool(st.session_state.business_info.get('total'))),
            ("📋 Póliza", 'poliza_content' in st.session_state),
            ("🔊 Audio", 'audio_file' in st.session_state)
        ]
        
        for item, completed in progress_items:
            if completed:
                st.success(f"✅ {item}")
            else:
                st.info(f"⏳ {item}")
        
        # Resumen de información actual
        if st.session_state.business_info:
            st.subheader("📋 Información Actual")
            info = st.session_state.business_info
            
            if info.get('tipo_negocio'):
                st.write(f"**Tipo:** {info['tipo_negocio']}")
            if info.get('metraje'):
                st.write(f"**Área:** {info['metraje']} m²")
            if info.get('direccion'):
                st.write(f"**Dirección:** {info['direccion']}")
            if info.get('total'):
                st.write(f"**Valor estimado:** S/ {info['total']:,.2f}")
        
        # Descargas
        if 'poliza_content' in st.session_state:
            st.subheader("📥 Descargar")
            
            st.download_button(
                "📄 Descargar Póliza",
                data=st.session_state.poliza_content,
                file_name=f"poliza_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain"
            )
            
            if 'audio_file' in st.session_state and os.path.exists(st.session_state.audio_file):
                with open(st.session_state.audio_file, 'rb') as audio_file:
                    st.download_button(
                        "🔊 Descargar Audio",
                        data=audio_file.read(),
                        file_name=f"resumen_poliza_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3",
                        mime="audio/mp3"
                    )
                
                # Reproducir audio
                st.audio(st.session_state.audio_file)
    
    # Botón para reiniciar
    if st.sidebar.button("🔄 Nueva Consulta"):
        # Limpiar session state excepto API key
        keys_to_keep = ['openai_api_key']
        keys_to_delete = [key for key in st.session_state.keys() if key not in keys_to_keep]
        for key in keys_to_delete:
            del st.session_state[key]
        # Reinicializar agente
        st.session_state.agent = InsuranceAgent(api_key)
        st.rerun()

def process_user_message(user_message: str) -> str:
    """Procesa el mensaje del usuario y genera una respuesta contextual"""
    
    user_input = user_message.lower()
    
    # Extraer números del mensaje (para metraje)
    numbers = extract_numbers_from_text(user_input)
    
    # Si mencionan metraje y no lo tenemos
    if not st.session_state.business_info.get('metraje') and numbers:
        metraje = float(numbers[0])
        st.session_state.business_info['metraje'] = metraje
        
        # Si también tenemos fotos, hacer valuación
        if st.session_state.business_info.get('num_images', 0) > 0:
            valuation = st.session_state.agent.estimate_property_value(
                metraje,
                st.session_state.business_info.get('tipo_negocio', '')
            )
            st.session_state.business_info.update(valuation)
            
            return f"""¡Perfecto! He registrado {metraje} m² como el área de tu local.

**💰 Valuación estimada:**
• Inventario/Mercancía: S/ {valuation['inventario']:,.2f}
• Mobiliario y Equipos: S/ {valuation['mobiliario']:,.2f}  
• Infraestructura: S/ {valuation['infraestructura']:,.2f}
• **Total estimado: S/ {valuation['total']:,.2f}**

¿Te parece correcta esta valuación? Si estás de acuerdo, procederé a generar tu póliza."""
        else:
            return f"¡Perfecto! He registrado {metraje} m² como el área de tu local. Ahora necesito fotos del interior para hacer la valuación correcta."
    
    # Detectar confirmaciones para generar póliza
    confirmations = ["sí", "si", "ok", "correcto", "bien", "de acuerdo", "generar", "poliza"]
    if any(word in user_input for word in confirmations):
        
        # Si tenemos valuación pero no póliza
        if st.session_state.business_info.get('total') and 'poliza_content' not in st.session_state:
            # Copiar información de business_info incluyendo campos con nombres diferentes
            policy_info = st.session_state.business_info.copy()
            policy_info['valor_inventario'] = policy_info.get('inventario', 0)
            policy_info['valor_mobiliario'] = policy_info.get('mobiliario', 0)
            policy_info['valor_infraestructura'] = policy_info.get('infraestructura', 0)
            policy_info['valor_total'] = policy_info.get('total', 0)
            
            # Generar póliza
            policy_content = st.session_state.agent.generate_policy(policy_info)
            st.session_state.poliza_content = policy_content
            
            return f"{policy_content}\n\n¿Te gustaría que genere también un resumen en audio de tu póliza?"
        
        # Si tenemos póliza pero no audio
        elif 'poliza_content' in st.session_state and 'audio_file' not in st.session_state:
            # Generar audio
            audio_file, summary = st.session_state.agent.generate_audio_summary(st.session_state.business_info)
            
            if audio_file:
                st.session_state.audio_file = audio_file
                st.session_state.audio_summary = summary
                return """🔊 **¡Perfecto! He generado tu póliza completa y un resumen en audio.**

Puedes descargar ambos archivos usando los botones del panel lateral. El resumen en audio incluye los puntos más importantes de tu cobertura.

¿Hay algo más en lo que pueda ayudarte con tu póliza?"""
            else:
                return "✅ **Tu póliza está lista para descargar.**\n\nHubo un problema generando el audio, pero puedes descargar el documento de póliza."
    
    # Detectar información básica del negocio si no tenemos documento
    business_types = {
        "restaurante": ["restaurante", "restaurant", "comida", "cocina"],
        "tienda": ["tienda", "store", "comercio", "venta"],
        "oficina": ["oficina", "office", "consultorio"],
        "farmacia": ["farmacia", "botica", "medicinas"],
        "bar": ["bar", "cantina", "licores"],
        "panadería": ["panadería", "bakery", "pan"]
    }
    
    for business, keywords in business_types.items():
        if any(keyword in user_input for keyword in keywords):
            if not st.session_state.business_info.get('tipo_negocio'):
                st.session_state.business_info['tipo_negocio'] = business
                
                missing_info = []
                if not st.session_state.business_info.get('metraje'):
                    missing_info.append("📏 metros cuadrados del local")
                if not st.session_state.business_info.get('direccion'):
                    missing_info.append("📍 dirección")
                
                if missing_info:
                    return f"¡Perfecto! He registrado que tienes un {business}. Ahora necesito: {', '.join(missing_info)}"
                else:
                    return f"¡Excelente! Ya tengo la información básica de tu {business}. 📸 **Ahora necesito fotos del local** para hacer la valuación."
            break
    
    # Respuesta general usando IA
    context = f"Información actual: {st.session_state.business_info}"
    return st.session_state.agent.chat_response(user_message, context)

if __name__ == "__main__":
    main()