import streamlit as st
import os
import openai
import base64
import io
from PIL import Image
from datetime import datetime
import tempfile
import traceback

# Importar módulos personalizados
from models import GraphState, ConversationStep, BusinessInfo, SerializableImage
from insurance_graph import InsuranceAgentGraph
from certificate_analyzer import extract_text_from_document

# Configuración de página
st.set_page_config(
    page_title="🤖 Agente de Seguros IA - Pacífico",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
.main-header {
    background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
    padding: 1rem;
    border-radius: 10px;
    color: white;
    text-align: center;
    margin-bottom: 2rem;
}

.progress-item {
    padding: 0.5rem;
    margin: 0.2rem 0;
    border-radius: 5px;
    border-left: 4px solid #2a5298;
}

.completed {
    background-color: #d4edda;
    border-left-color: #28a745;
}

.pending {
    background-color: #f8f9fa;
    border-left-color: #6c757d;
}

.chat-container {
    max-height: 600px;
    overflow-y: auto;
    padding: 1rem;
    border: 1px solid #ddd;
    border-radius: 10px;
    background-color: #fafafa;
}
</style>
""", unsafe_allow_html=True)

def debug_log(message, data=None):
    """Función para logging de debug"""
    print(f"[DEBUG] {message}")
    if data:
        print(f"[DEBUG DATA] {data}")
    
    # También mostrar en Streamlit si está en debug mode
    if st.session_state.get("debug_mode", False):
        st.write(f"🔍 DEBUG: {message}")
        if data:
            st.json(data)

def classify_image_type(image: Image.Image, api_key: str) -> str:
    """Clasifica si una imagen es un certificado o foto del local usando GPT-4 Vision"""
    try:
        debug_log("Iniciando clasificación de imagen")
        client = openai.OpenAI(api_key=api_key)
        
        # Convertir imagen a base64
        buffer = io.BytesIO()
        # Redimensionar para reducir tokens
        if image.width > 800:
            ratio = 800 / image.width
            new_height = int(image.height * ratio)
            image = image.resize((800, new_height), Image.Resampling.LANCZOS)
        
        image.save(buffer, format='JPEG', quality=85)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        debug_log(f"Imagen redimensionada a {image.size}, tamaño base64: {len(img_str)} chars")
        
        prompt = """
Analiza esta imagen y determina si es:
1. Un CERTIFICADO DE FUNCIONAMIENTO (documento oficial con texto, sellos, firmas)
2. Una FOTO DEL LOCAL COMERCIAL (interior, exterior, inventario, mobiliario)

Responde SOLO con una palabra:
- "certificate" si es un certificado de funcionamiento
- "local_photo" si es una foto del local/negocio
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=10,
            temperature=0
        )
        
        result = response.choices[0].message.content.strip().lower()
        classification = "certificate" if "certificate" in result else "local_photo"
        debug_log(f"Clasificación de imagen: {classification} (respuesta: {result})")
        return classification
        
    except Exception as e:
        debug_log(f"Error clasificando imagen: {str(e)}")
        traceback.print_exc()
        return "local_photo"
def process_uploaded_image(uploaded_file, graph_state, insurance_graph, api_key):
    """Procesa una imagen subida, la clasifica y actualiza el estado con debug detallado"""
    try:
        debug_log(f"Procesando imagen: {uploaded_file.name}")
        
        # Convertir a PIL Image
        pil_image = Image.open(uploaded_file)
        debug_log(f"PIL Image cargada: {pil_image.size}, modo: {pil_image.mode}")
        
        # Clasificar tipo de imagen
        image_type = classify_image_type(pil_image, api_key)
        debug_log(f"Tipo de imagen detectado: {image_type}")
        
        if image_type == "certificate":
            debug_log("Procesando como certificado...")
            
            # NUEVO: Debug del estado ANTES del procesamiento
            debug_log("Estado ANTES del procesamiento:", {
                "business_info_before": graph_state["business_info"].to_dict(),
                "messages_count_before": len(graph_state["messages"])
            })
            
            try:
                # Procesar certificado directamente con el analizador
                business_info_extracted = insurance_graph.nodes.certificate_analyzer.analyze_image(pil_image)
                debug_log("Datos extraídos del certificado:", business_info_extracted.to_dict())
                
                # Crear SerializableImage para el estado
                serializable_image = SerializableImage.from_pil_image(pil_image, "certificado_funcionamiento.jpg")
                graph_state["certificate_images"] = [serializable_image]
                
                # Combinar información manualmente
                existing_info = graph_state["business_info"]
                debug_log("Información existente:", existing_info.to_dict())
                
                # Actualizar campos uno por uno
                for field, value in business_info_extracted.to_dict().items():
                    if value and not getattr(existing_info, field, None):
                        setattr(existing_info, field, value)
                        debug_log(f"Campo actualizado: {field} = {value}")
                
                # Generar mensaje de respuesta
                summary_parts = []
                if existing_info.nombre_cliente:
                    summary_parts.append(f"Cliente: {existing_info.nombre_cliente}")
                if existing_info.direccion:
                    summary_parts.append(f"Dirección: {existing_info.direccion}")
                if existing_info.tipo_negocio:
                    summary_parts.append(f"Tipo: {existing_info.tipo_negocio}")
                if existing_info.metraje:
                    summary_parts.append(f"Área: {existing_info.metraje}m²")
                if existing_info.ruc:
                    summary_parts.append(f"RUC: {existing_info.ruc}")
                
                if summary_parts:
                    response_msg = f"📄 He analizado tu certificado de funcionamiento:\n\n" + "\n".join([f"• {part}" for part in summary_parts])
                    
                    if not existing_info.metraje:
                        response_msg += "\n\n❓ No encontré el metraje en el certificado. ¿Podrías decirme cuántos metros cuadrados tiene tu local?"
                    else:
                        response_msg += "\n\n📸 Siguiente paso: Necesito fotos del local para hacer la valuación precisa."
                else:
                    response_msg = "📄 He procesado el certificado pero no pude extraer información clara. ¿Podrías proporcionarme los datos manualmente?"
                
                # NUEVO: Debug del estado DESPUÉS del procesamiento
                debug_log("Estado DESPUÉS del procesamiento:", {
                    "business_info_after": graph_state["business_info"].to_dict(),
                    "certificate_images_count": len(graph_state.get("certificate_images", [])),
                    "response_message": response_msg[:100] + "..."
                })
                
                new_state = graph_state
                debug_log("Certificado procesado exitosamente")
                
            except Exception as e:
                debug_log(f"Error procesando certificado: {str(e)}")
                traceback.print_exc()
                new_state = graph_state
                response_msg = f"Error procesando certificado: {str(e)}"
            
        else:  # local_photo
            debug_log("Procesando como foto del local...")
            try:
                # Crear SerializableImage
                filename = uploaded_file.name or f"local_foto.jpg"
                serializable_image = SerializableImage.from_pil_image(pil_image, filename)
                
                # Agregar a fotos del local
                current_photos = graph_state.get("local_photos", [])
                current_photos.append(serializable_image)
                graph_state["local_photos"] = current_photos
                debug_log(f"Foto agregada. Total fotos: {len(current_photos)}")
                
                # Si tenemos metraje, calcular valuación
                if graph_state["business_info"].metraje:
                    graph_state["next_action"] = "calculate_valuation"
                    graph_state["user_input"] = f"He subido una foto del local (total: {len(current_photos)} fotos)"
                    debug_log("Iniciando cálculo de valuación")
                else:
                    graph_state["user_input"] = f"He subido una foto del local (total: {len(current_photos)} fotos)"
                    graph_state["next_action"] = "analyze_input"
                    debug_log("Solicitando más información")
                
                # Ejecutar el grafo
                config = {"configurable": {"thread_id": graph_state["session_id"]}}
                new_state = insurance_graph.graph.invoke(graph_state, config)
                
                response_msg = f"📷 Perfecto, he recibido una foto de tu local comercial. Ahora tengo {len(current_photos)} imagen(es) del negocio."
                debug_log("Foto del local procesada exitosamente")
                
            except Exception as e:
                debug_log(f"Error procesando foto del local: {str(e)}")
                traceback.print_exc()
                new_state = graph_state
                response_msg = f"Error procesando foto: {str(e)}"
        
        return new_state, response_msg
        
    except Exception as e:
        error_msg = f"Error general procesando imagen: {str(e)}"
        debug_log(error_msg)
        traceback.print_exc()
        return graph_state, error_msg
def initialize_session_state():
    """Inicializa el estado de la sesión"""
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    
    if "insurance_graph" not in st.session_state:
        st.session_state.insurance_graph = None
    
    if "graph_state" not in st.session_state:
        st.session_state.graph_state = None
    
    if "conversation_initialized" not in st.session_state:
        st.session_state.conversation_initialized = False

def setup_insurance_graph(api_key: str):
    """Configura el grafo de seguros"""
    try:
        if not st.session_state.insurance_graph:
            st.session_state.insurance_graph = InsuranceAgentGraph(api_key)
            st.session_state.graph_state = st.session_state.insurance_graph.create_initial_state()
            
            # Ejecutar nodo de bienvenida
            config = {"configurable": {"thread_id": st.session_state.graph_state["session_id"]}}
            st.session_state.graph_state = st.session_state.insurance_graph.graph.invoke(
                st.session_state.graph_state, config
            )
            st.session_state.conversation_initialized = True
            
        return True
    except Exception as e:
        st.error(f"Error configurando el agente: {str(e)}")
        return False

def render_progress_panel():
    """Renderiza el panel de progreso"""
    st.subheader("📊 Progreso del Seguro")
    
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    business_info = state.get("business_info", BusinessInfo())
    
    progress_items = [
        ("📄 Certificado", bool(business_info.direccion or business_info.tipo_negocio)),
        ("📏 Metraje", bool(business_info.metraje)),
        ("📸 Fotos Local", len(state.get("local_photos", [])) > 0),
        ("💰 Valuación", bool(state.get("valuation"))),
        ("📋 Póliza", bool(state.get("policy"))),
        ("🔊 Audio", bool(state.get("audio_file")))
    ]
    
    for item, completed in progress_items:
        if completed:
            st.markdown(f"""
            <div class="progress-item completed">
                ✅ {item}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="progress-item pending">
                ⏳ {item}
            </div>
            """, unsafe_allow_html=True)

def render_business_info_panel():
    """Renderiza el panel de información del negocio"""
    if not st.session_state.graph_state:
        return
    
    business_info = st.session_state.graph_state.get("business_info", BusinessInfo())
    valuation = st.session_state.graph_state.get("valuation")
    
    if any([business_info.tipo_negocio, business_info.metraje, business_info.direccion]):
        st.subheader("🏢 Información del Negocio")
        
        if business_info.nombre_cliente:
            st.write(f"**Cliente:** {business_info.nombre_cliente}")
        if business_info.tipo_negocio:
            st.write(f"**Tipo:** {business_info.tipo_negocio}")
        if business_info.metraje:
            st.write(f"**Área:** {business_info.metraje} m²")
        if business_info.direccion:
            st.write(f"**Dirección:** {business_info.direccion}")
        if business_info.ruc:
            st.write(f"**RUC:** {business_info.ruc}")
        
        if valuation:
            st.write(f"**Valor estimado:** S/ {valuation.total:,.2f}")

def render_downloads_panel():
    """Renderiza el panel de descargas"""
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    
    if state.get("policy") or state.get("audio_file"):
        st.subheader("📥 Descargar Documentos")
        
        # Descargar póliza
        if state.get("policy"):
            policy_content = state["policy"].content
            st.download_button(
                "📄 Descargar Póliza",
                data=policy_content,
                file_name=f"poliza_seguro_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # Descargar audio
        if state.get("audio_file") and os.path.exists(state["audio_file"]):
            try:
                with open(state["audio_file"], 'rb') as audio_file:
                    st.download_button(
                        "🔊 Descargar Audio",
                        data=audio_file.read(),
                        file_name=f"resumen_poliza_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3",
                        mime="audio/mp3",
                        use_container_width=True
                    )
                
                # Reproducir audio
                st.audio(state["audio_file"])
            except Exception as e:
                st.error(f"Error cargando audio: {str(e)}")

def render_image_gallery():
    """Renderiza galería de imágenes subidas"""
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    local_photos = state.get("local_photos", [])
    
    if local_photos:
        st.subheader("🖼️ Fotos del Local")
        
        # Mostrar fotos en filas de 3
        cols_per_row = 3
        for i in range(0, len(local_photos), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(local_photos):
                    with col:
                        try:
                            photo = local_photos[i + j]
                            pil_image = photo.to_pil_image()
                            st.image(pil_image, caption=f"Foto {i+j+1}", use_column_width=True)
                        except Exception as e:
                            st.error(f"Error mostrando imagen {i+j+1}: {str(e)}")
    
    # También mostrar certificados si los hay
    certificate_images = state.get("certificate_images", [])
    if certificate_images:
        st.subheader("📄 Certificado de Funcionamiento")
        
        for i, cert_image in enumerate(certificate_images):
            try:
                pil_image = cert_image.to_pil_image()
                st.image(pil_image, caption=f"Certificado {i+1}", use_column_width=True)
            except Exception as e:
                st.error(f"Error mostrando certificado {i+1}: {str(e)}")
    
    # Verificar si st.chat_input está disponible con file_uploader
    try:
        # Input del usuario con soporte para archivos
        user_input = st.chat_input(
            "Escribe tu mensaje o sube una imagen (certificado o foto del local)...",
            accept_file=True,
            file_type=["jpg", "jpeg", "png"]
        )
        debug_log("st.chat_input con file_uploader disponible")
    except Exception as e:
        debug_log(f"Error con st.chat_input file_uploader: {str(e)}")
        st.error("Tu versión de Streamlit no soporta file_uploader en chat_input. Actualiza a la versión más reciente.")
        
        # Fallback: usar input normal y file_uploader separado
        col1, col2 = st.columns([3, 1])
        with col1:
            user_text = st.chat_input("Escribe tu mensaje...")
        with col2:
            uploaded_file = st.file_uploader("Subir imagen", type=["jpg", "jpeg", "png"], key="fallback_upload")
        
        # Simular estructura de user_input
        user_input = {}
        if user_text:
            user_input["message"] = user_text
        if uploaded_file:
            user_input["file"] = uploaded_file
        
        if not user_text and not uploaded_file:
            user_input = None
    
    if user_input:
        debug_log("Input del usuario recibido", user_input.keys() if isinstance(user_input, dict) else type(user_input))
        
        message = user_input.get("message") if isinstance(user_input, dict) else None
        uploaded_files = user_input.get("file") if isinstance(user_input, dict) else None
        
        # Si user_input es string (texto simple)
        if isinstance(user_input, str):
            message = user_input
            uploaded_file = None
        
        # Procesar mensaje de texto
        if message:
            debug_log(f"Procesando mensaje de texto: {message[:50]}...")
            with st.spinner("Procesando mensaje..."):
                try:
                    st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                        st.session_state.graph_state, message
                    )
                    debug_log("Mensaje procesado exitosamente")
                except Exception as e:
                    debug_log(f"Error procesando mensaje: {str(e)}")
                    traceback.print_exc()
                    st.error(f"Error procesando mensaje: {str(e)}")
            st.rerun()  
        
        # Procesar imagen subida
        if uploaded_files:
            for i, uploaded_file in enumerate(uploaded_files):
                debug_log(f"Procesando imagen {i+1}: {uploaded_file.name}")
                
                # NUEVO: Debug del estado ANTES de procesar
                debug_log("Estado del grafo ANTES de procesar imagen:", {
                    "business_info": st.session_state.graph_state["business_info"].to_dict(),
                    "messages_count": len(st.session_state.graph_state["messages"]),
                    "current_step": str(st.session_state.graph_state["current_step"])
                })
                
                # IMPORTANTE: Agregar imagen del usuario al historial ANTES de procesar
                st.session_state.graph_state["messages"].append({
                    "role": "user",
                    "content": f"📎 Imagen subida: {uploaded_file.name}"
                })
                
                with st.spinner(f"Analizando imagen {i+1} automáticamente..."):
                    try:
                        # Procesar la imagen automáticamente
                        new_state, response_msg = process_uploaded_image(
                            uploaded_file, 
                            st.session_state.graph_state,
                            st.session_state.insurance_graph,
                            st.session_state.api_key
                        )
                        
                        # NUEVO: Debug del estado DESPUÉS de procesar
                        debug_log("Estado del grafo DESPUÉS de procesar imagen:", {
                            "business_info": new_state["business_info"].to_dict(),
                            "messages_count": len(new_state["messages"]),
                            "current_step": str(new_state["current_step"]),
                            "certificate_images": len(new_state.get("certificate_images", [])),
                            "local_photos": len(new_state.get("local_photos", []))
                        })
                        
                        # Actualizar estado
                        st.session_state.graph_state = new_state
                        
                        # IMPORTANTE: Agregar respuesta del asistente al historial
                        st.session_state.graph_state["messages"].append({
                            "role": "assistant",
                            "content": response_msg
                        })
                        
                        # NUEVO: Debug final del estado
                        debug_log("Estado FINAL después de agregar mensajes:", {
                            "business_info_final": st.session_state.graph_state["business_info"].to_dict(),
                            "messages_count_final": len(st.session_state.graph_state["messages"])
                        })
                            
                        debug_log(f"Imagen {i+1} procesada exitosamente")
                        
                    except Exception as e:
                        debug_log(f"Error procesando imagen {i+1}: {str(e)}")
                        traceback.print_exc()
                        # Agregar mensaje de error al historial
                        st.session_state.graph_state["messages"].append({
                            "role": "assistant",
                            "content": f"Error procesando imagen {uploaded_file.name}: {str(e)}"
                        })
            
            st.rerun()

def test_openai_connection(api_key):
    """Prueba la conexión con OpenAI"""
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=5
        )
        return True, "Conexión exitosa"
    except Exception as e:
        return False, str(e)

def debug_setup():
    """Setup inicial de debugging"""
    st.sidebar.subheader("🔧 Debug Info")
    
    # Test de API Key
    if st.session_state.get("api_key"):
        if st.sidebar.button("Test API Key"):
            success, message = test_openai_connection(st.session_state.api_key)
            if success:
                st.sidebar.success("✅ API Key funciona")
            else:
                st.sidebar.error(f"❌ Error API Key: {message}")
    
    # Información de Streamlit
    st.sidebar.text(f"Streamlit: {st.__version__}")
    
    # Estado del grafo
    if st.session_state.get("graph_state"):
        st.sidebar.text(f"Session ID: {st.session_state.graph_state.get('session_id', 'N/A')[:8]}...")
        st.sidebar.text(f"Messages: {len(st.session_state.graph_state.get('messages', []))}")
    
    # Reiniciar estado completo
    if st.sidebar.button("🗑️ Reset Completo"):
        st.session_state.clear()
        st.rerun()
def render_conversation():
    """Renderiza la conversación con soporte automático para imágenes usando st.chat_input"""
    st.subheader("💬 Conversación con tu Agente de Seguros")
    
    # Toggle para modo debug
    st.session_state.debug_mode = st.checkbox("🔍 Modo Debug", value=st.session_state.get("debug_mode", False))
    
    if not st.session_state.graph_state:
        st.warning("Configura tu API Key para comenzar")
        return
    
    # Mostrar estado actual en debug mode
    if st.session_state.debug_mode:
        with st.expander("Estado Actual del Grafo", expanded=False):
            st.json({
                "current_step": str(st.session_state.graph_state.get("current_step", "Unknown")),
                "message_count": len(st.session_state.graph_state.get("messages", [])),
                "business_info": st.session_state.graph_state.get("business_info", {}).to_dict() if st.session_state.graph_state.get("business_info") else {},
                "local_photos_count": len(st.session_state.graph_state.get("local_photos", [])),
                "next_action": st.session_state.graph_state.get("next_action", "Unknown")
            })
    
    # Contenedor de chat
    chat_container = st.container()
    
    with chat_container:
        # Mostrar mensajes de la conversación
        messages = st.session_state.graph_state.get("messages", [])
        debug_log(f"Mostrando {len(messages)} mensajes")
        
        for i, message in enumerate(messages):
            if message["role"] == "user":
                st.chat_message("user").write(message["content"])
            else:
                st.chat_message("assistant").write(message["content"])
    
    # Chat input con soporte para archivos
    prompt = st.chat_input(
        "Escribe tu mensaje o sube una imagen (certificado o foto del local)...",
        accept_file=True,
        file_type=["jpg", "jpeg", "png"]
    )
    
    if prompt:
        debug_log("Input del usuario recibido", type(prompt))
        
        # Si es solo texto (string)
        if isinstance(prompt, str):
            user_message = prompt
            uploaded_files = []
            debug_log(f"Mensaje de texto: {user_message[:50]}...")
            
        # Si es dict-like con texto y/o archivos
        else:
            user_message = prompt.text if hasattr(prompt, 'text') else prompt.get('text', '')
            uploaded_files = prompt.files if hasattr(prompt, 'files') else prompt.get('files', [])
            debug_log(f"Mensaje: '{user_message}', Archivos: {len(uploaded_files)}")
        
        # Procesar mensaje de texto si existe
        if user_message:
            debug_log(f"Procesando mensaje de texto: {user_message[:50]}...")
            
            # IMPORTANTE: Agregar mensaje del usuario al historial ANTES de procesar
            st.session_state.graph_state["messages"].append({
                "role": "user",
                "content": message
            })
            
            with st.spinner("Procesando mensaje..."):
                try:
                    # NUEVO: Debug antes de process_user_input
                    debug_log("ANTES de process_user_input:", {
                        "user_input_to_process": message,
                        "current_step": str(st.session_state.graph_state.get("current_step")),
                        "needs_confirmation": st.session_state.graph_state.get("needs_confirmation"),
                        "has_valuation": bool(st.session_state.graph_state.get("valuation")),
                        "has_policy": bool(st.session_state.graph_state.get("policy"))
                    })
                    
                    # Ejecutar process_user_input
                    st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                        st.session_state.graph_state, message
                    )
                    
                    # NUEVO: Debug después de process_user_input
                    debug_log("DESPUÉS de process_user_input:", {
                        "current_step": str(st.session_state.graph_state.get("current_step")),
                        "needs_confirmation": st.session_state.graph_state.get("needs_confirmation"),
                        "has_policy": bool(st.session_state.graph_state.get("policy")),
                        "next_action": st.session_state.graph_state.get("next_action")
                    })
                    
                    debug_log("Mensaje procesado exitosamente")
                    
                except Exception as e:
                    debug_log(f"ERROR en process_user_input: {str(e)}")
                    traceback.print_exc()
        
        # Procesar archivos subidos si existen
        if uploaded_files:
            for i, uploaded_file in enumerate(uploaded_files):
                debug_log(f"Procesando imagen {i+1}: {uploaded_file.name}")
                
                # IMPORTANTE: Agregar imagen del usuario al historial ANTES de procesar
                st.session_state.graph_state["messages"].append({
                    "role": "user",
                    "content": f"📎 Imagen subida: {uploaded_file.name}"
                })
                
                with st.spinner(f"Analizando imagen {i+1} automáticamente..."):
                    try:
                        # Procesar la imagen automáticamente
                        new_state, response_msg = process_uploaded_image(
                            uploaded_file, 
                            st.session_state.graph_state,
                            st.session_state.insurance_graph,
                            st.session_state.api_key
                        )
                        
                        # Actualizar estado
                        st.session_state.graph_state = new_state
                        
                        # IMPORTANTE: Agregar respuesta del asistente al historial
                        st.session_state.graph_state["messages"].append({
                            "role": "assistant",
                            "content": response_msg
                        })
                            
                        debug_log(f"Imagen {i+1} procesada exitosamente")
                        
                    except Exception as e:
                        debug_log(f"Error procesando imagen {i+1}: {str(e)}")
                        traceback.print_exc()
                        # Agregar mensaje de error al historial
                        st.session_state.graph_state["messages"].append({
                            "role": "assistant",
                            "content": f"Error procesando imagen {uploaded_file.name}: {str(e)}"
                        })
        
        # Recargar la página para mostrar las respuestas
        st.rerun()
    
    # Información adicional sobre el uso
    st.info("💡 **Tip:** Puedes escribir mensajes, subir imágenes, o ambos a la vez en el chat de abajo. Las imágenes se analizan automáticamente.")
    
    # Botones de acción rápida basados en el contexto
    if st.session_state.graph_state:
        state = st.session_state.graph_state
        
        # Mostrar botón para generar póliza si tenemos valuación pero no póliza
        if state.get("valuation") and not state.get("policy"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 Generar Póliza", type="primary", use_container_width=True):
                    with st.spinner("Generando póliza completa..."):
                        try:
                            # Agregar mensaje del usuario al historial
                            st.session_state.graph_state["messages"].append({
                                "role": "user",
                                "content": "Generar póliza"
                            })
                            
                            st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                                st.session_state.graph_state, "sí, generar póliza"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error generando póliza: {str(e)}")
            
            with col2:
                if st.button("💰 Ver Cotización", use_container_width=True):
                    with st.spinner("Actualizando cotización..."):
                        try:
                            # Agregar mensaje del usuario al historial
                            st.session_state.graph_state["messages"].append({
                                "role": "user",
                                "content": "Ver cotización"
                            })
                            
                            st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                                st.session_state.graph_state, "muéstrame el resumen de la cotización"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error mostrando cotización: {str(e)}")
        
        # Mostrar botón para generar audio si tenemos póliza pero no audio
        elif state.get("policy") and not state.get("audio_file"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔊 Generar Resumen en Audio", use_container_width=True):
                    with st.spinner("Generando resumen en audio..."):
                        try:
                            # Agregar mensaje del usuario al historial
                            st.session_state.graph_state["messages"].append({
                                "role": "user",
                                "content": "Generar resumen en audio"
                            })
                            
                            st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                                st.session_state.graph_state, "sí, generar audio"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error generando audio: {str(e)}")
            
            with col2:
                if st.button("📞 Información de Contacto", use_container_width=True):
                    with st.spinner("Obteniendo información de contacto..."):
                        try:
                            # Agregar mensaje del usuario al historial
                            st.session_state.graph_state["messages"].append({
                                "role": "user",
                                "content": "Información de contacto"
                            })
                            
                            st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                                st.session_state.graph_state, "dame información de contacto para contratar"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error obteniendo contacto: {str(e)}")
        
        # Si ya tenemos todo, mostrar opciones de finalización
        # Si ya tenemos todo, mostrar opciones de finalización
        elif state.get("policy") and state.get("audio_file"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("Ver Coberturas", use_container_width=True):
                    # Usar el grafo - enviar mensaje a través del sistema
                    try:
                        st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                            st.session_state.graph_state, "explícame las coberturas incluidas"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
            
            with col2:
                if st.button("Información de Costos", use_container_width=True):
                    # Usar el grafo - enviar mensaje a través del sistema
                    try:
                        st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                            st.session_state.graph_state, "dame más detalles sobre los costos"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
            
            with col3:
                if st.button("Cómo Contratar", use_container_width=True):
                    # Usar el grafo - enviar mensaje a través del sistema
                    try:
                        st.session_state.graph_state = st.session_state.insurance_graph.process_user_input(
                            st.session_state.graph_state, "quiero contratar el seguro"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")


def debug_conversation_flow():
    """Debugging detallado para entender por qué falla el flujo - CORREGIDO"""
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    
    st.subheader("🔍 Análisis del Flujo de Conversación")
    
    # 1. Estado actual
    st.write("**1. Estado Actual del Sistema:**")
    st.code(f"""
Current Step: {state.get('current_step', 'Unknown')}
Next Action: {state.get('next_action', 'Unknown')}
Needs Confirmation: {state.get('needs_confirmation', False)}
Ready for Policy: {state.get('ready_for_policy', False)}
    """)
    
    # 2. Datos disponibles
    st.write("**2. Datos Disponibles:**")
    business_info = state.get("business_info", BusinessInfo())
    valuation = state.get("valuation")
    policy = state.get("policy")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("**Business Info:**")
        data = business_info.to_dict()
        for key, value in data.items():
            status = "✅" if value else "❌"
            st.write(f"{status} {key}")
    
    with col2:
        st.write("**Valuación:**")
        if valuation:
            st.write("✅ Existe")
            st.write(f"Total: S/ {valuation.total:,.2f}")
        else:
            st.write("❌ No existe")
    
    with col3:
        st.write("**Póliza:**")
        if policy:
            st.write("✅ Existe")
        else:
            st.write("❌ No existe")
    
    # 3. Análisis del problema
    st.write("**3. Análisis del Problema:**")
    
    # Verificar si debe generar póliza
    should_generate_policy = valuation and not policy
    st.write(f"¿Debería generar póliza? {should_generate_policy}")
    
    if should_generate_policy:
        # Verificar qué está bloqueando la generación
        st.write("**¿Qué está bloqueando la generación?**")
        
        if state.get('needs_confirmation'):
            st.warning("🟡 Sistema esperando confirmación del usuario")
            st.write("El sistema generó la cotización y está esperando que el usuario confirme con 'sí', 'ok', 'generar', etc.")
        
        if state.get('current_step') == ConversationStep.VALUATION_COMPLETE:
            st.info("🔵 Sistema en paso de valuación completa")
            st.write("Debería estar en modo de espera para confirmación")
        
        # Verificar el enrutamiento - CORREGIDO
        st.write("**4. Verificación de Enrutamiento:**")
        
        # Manejar user_input de forma segura
        user_input_raw = state.get('user_input', '')
        try:
            if isinstance(user_input_raw, dict):
                # Si es un dict, extraer el texto
                user_input = str(user_input_raw.get('text', '') or user_input_raw.get('message', ''))
            else:
                user_input = str(user_input_raw)
            user_input = user_input.lower()
        except:
            user_input = ''
        
        st.write(f"Último user_input: '{user_input}'")
        st.write(f"Tipo de user_input: {type(state.get('user_input'))}")
        
        confirmation_words = ["sí", "si", "ok", "correcto", "generar"]
        has_confirmation = any(word in user_input for word in confirmation_words)
        st.write(f"¿Contiene palabras de confirmación? {has_confirmation}")
        
        # Mostrar qué ruta tomaría
        if state.get("needs_confirmation") and not has_confirmation:
            st.write("→ Ruta: wait (esperando confirmación)")
        elif has_confirmation:
            st.write("→ Ruta: policy_generation")
        else:
            st.write("→ Ruta: sales_assistance")
    
    # 4. Último mensaje del usuario - CORREGIDO
    st.write("**5. Historial de Mensajes Recientes:**")
    messages = state.get("messages", [])
    if messages:
        # Mostrar últimos 3 mensajes
        for msg in messages[-3:]:
            try:
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                content = str(msg.get("content", "")).strip()
                # Truncar contenido de forma segura
                if len(content) > 100:
                    content = content[:100] + "..."
                st.write(f"{role_icon} **{msg['role']}:** {content}")
            except Exception as e:
                st.write(f"Error mostrando mensaje: {str(e)}")
    
    return state
# Función para testear el enrutamiento manualmente
def test_routing_logic():
    """Testea la lógica de enrutamiento con diferentes inputs"""
    st.subheader("🧪 Test de Lógica de Enrutamiento")
    
    if not st.session_state.graph_state:
        st.write("No hay estado del grafo")
        return
    
    state = st.session_state.graph_state
    
    # Input de prueba
    test_input = st.text_input("Probar con este input:", placeholder="sí, generar póliza")
    
    if test_input and st.button("Probar Enrutamiento"):
        # Simular el enrutamiento
        st.write("**Resultado del enrutamiento:**")
        
        # Copiar la lógica de _route_from_valuation
        if state.get("needs_confirmation"):
            st.write("1. Sistema necesita confirmación: ✅")
            
            confirmation_words = ["sí", "si", "ok", "correcto", "generar"]
            has_confirmation = any(word in test_input.lower() for word in confirmation_words)
            
            if has_confirmation:
                st.success("2. Input contiene confirmación: ✅")
                st.success("→ Debería ir a: policy_generation")
                
                # Probar generar póliza manualmente
                if st.button("Ejecutar Generación de Póliza"):
                    try:
                        # Actualizar estado
                        state["user_input"] = test_input
                        
                        # Llamar al nodo directamente
                        new_state = st.session_state.insurance_graph.nodes.policy_generation_node(state)
                        
                        if new_state.get("policy"):
                            st.success("Póliza generada exitosamente!")
                            st.session_state.graph_state = new_state
                            st.rerun()
                        else:
                            st.error("No se pudo generar la póliza")
                            
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        traceback.print_exc()
            else:
                st.warning("2. Input NO contiene confirmación: ❌")
                st.warning("→ Permanecería en: wait")
        else:
            st.write("1. Sistema NO necesita confirmación: ❌")
            st.write("→ Iría a: sales_assistance")

# Función para forzar el paso correcto
def force_correct_step():
    """Fuerza el sistema al paso correcto basado en los datos disponibles"""
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    
    st.subheader("🔧 Corregir Estado del Sistema")
    
    if st.button("Forzar Estado Correcto"):
        try:
            # Determinar el estado correcto basado en los datos
            if state.get("policy"):
                state["current_step"] = ConversationStep.POLICY_GENERATED
                state["next_action"] = "offer_audio"
                state["needs_confirmation"] = False
                st.success("Estado corregido a: POLICY_GENERATED")
                
            elif state.get("valuation"):
                state["current_step"] = ConversationStep.VALUATION_COMPLETE
                state["next_action"] = "await_confirmation"
                state["needs_confirmation"] = True
                st.success("Estado corregido a: VALUATION_COMPLETE")
                
            else:
                state["current_step"] = ConversationStep.GATHERING_INFO
                state["next_action"] = "gather_info"
                state["needs_confirmation"] = False
                st.success("Estado corregido a: GATHERING_INFO")
            
            st.rerun()
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            traceback.print_exc()
def main():
    """Función principal de la aplicación"""
    
    # Header principal
    st.markdown("""
    <div class="main-header">
        <h1>🤖 Agente de Seguros IA - Pacífico</h1>
        <p>Tu asistente inteligente para seguros comerciales personalizados</p>
        <small>💡 Ahora puedes subir imágenes directamente en el chat - detecta automáticamente certificados y fotos del local</small>
    </div>
    """, unsafe_allow_html=True)
    
    # Inicializar estado
    initialize_session_state()
    
    # Sidebar para configuración
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        # API Key
        api_key = st.text_input(
            "🔑 API Key de OpenAI:",
            type="password",
            value=st.session_state.get("api_key", ""),
            help="Ingresa tu API Key de OpenAI"
        )
        
        if api_key != st.session_state.api_key:
            st.session_state.api_key = api_key
            # Resetear el grafo si cambia la API key
            st.session_state.insurance_graph = None
            st.session_state.graph_state = None
            st.session_state.conversation_initialized = False
        
        if not api_key:
            st.warning("⚠️ Ingresa tu API Key para comenzar")
            st.info("💡 Este agente usa GPT-3.5-turbo y GPT-4o-mini (APIs económicas)")
            return
        
        # Configurar grafo
        if setup_insurance_graph(api_key):
            st.success("✅ Agente configurado")
        else:
            return
        
        st.divider()
        
        # Panel de progreso
        render_progress_panel()
        
        st.divider()
        
        # Panel de información del negocio
        render_business_info_panel()
        
        st.divider()
        
        # Panel de descargas
        render_downloads_panel()
        
        st.divider()
        
        # Galería de imágenes
        render_image_gallery()
        
        st.divider()
        
        # Debug setup
        debug_setup()
        
        st.divider()
        if st.session_state.get("debug_mode"):
            st.divider()
            debug_conversation_flow()
            st.divider()
            test_routing_logic()
            st.divider()
            force_correct_step()
        # Botón para reiniciar
        if st.button("🔄 Nueva Consulta", use_container_width=True):
            # Limpiar estado pero mantener API key
            api_key_backup = st.session_state.api_key
            st.session_state.clear()
            st.session_state.api_key = api_key_backup
            st.rerun()
    
    # Layout principal - solo conversación ahora
    # Conversación principal (ocupa todo el ancho)
    render_conversation()
    
    # Información del estado actual (colapsado por defecto)
    if st.session_state.graph_state:
        with st.expander("🔍 Estado del Sistema", expanded=False):
            summary = st.session_state.insurance_graph.get_conversation_summary(
                st.session_state.graph_state
            )
            st.json(summary)

if __name__ == "__main__":
    main() 
