import streamlit as st
import os
import openai
import base64
import io
from PIL import Image
from datetime import datetime
import tempfile
import traceback
import uuid

# Importar módulos personalizados
from models import GraphState, ConversationStep, BusinessInfo, SerializableImage
from insurance_graph import InsuranceAgentGraph,LLMControlledInsuranceAgent
from certificate_analyzer import extract_text_from_document

# NUEVO: Import del agente LLM modificado
from llm_controlled_agent import LLMControlledInsuranceAgent

def setup_insurance_agent(api_key: str):
    """Configura el agente de seguros controlado por LLM - CORREGIDO"""
    try:
        if not st.session_state.get("insurance_agent"):
            st.session_state.insurance_agent = LLMControlledInsuranceAgent(api_key)
            st.session_state.graph_state = create_initial_state()
            
            # Mensaje de bienvenida inicial
            welcome_message = {
                "role": "assistant",
                "content": """¡Hola! Soy tu agente de seguros comerciales de Seguros Pacífico.

🚀 **Proceso súper simple:**
1. Sube tu certificado de funcionamiento
2. Recibe tu cotización automáticamente
3. ¡Genera tu póliza en 1 click!

Solo necesitas subir la foto de tu certificado y yo me encargo del resto. ¿Comenzamos?"""
            }
            
            st.session_state.graph_state["messages"] = [welcome_message]
            
        return True
    except Exception as e:
        st.error(f"Error configurando el agente: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def create_initial_state() -> dict:
    """Crea el estado inicial simplificado"""
    return {
        "messages": [],
        "business_info": BusinessInfo(),
        "valuation": None,
        "certificate_text": None,
        "certificate_images": [],
        "local_photos": [],
        "policy": None,
        "audio_file": None,
        "audio_summary": None,
        "session_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "show_policy_buttons": False,
        "policy_generated": False,
        "show_download_buttons": False
    }

def debug_log(message, data=None):
    """Función para logging de debug"""
    print(f"[DEBUG] {message}")
    if data:
        print(f"[DEBUG DATA] {data}")

def classify_image_type(image: Image.Image, api_key: str) -> str:
    """Clasifica si una imagen es un certificado o foto del local usando GPT-4 Vision"""
    try:
        debug_log("Iniciando clasificación de imagen")
        client = openai.OpenAI(api_key=api_key)
        
        # Convertir imagen a base64
        buffer = io.BytesIO()
        if image.width > 800:
            ratio = 800 / image.width
            new_height = int(image.height * ratio)
            image = image.resize((800, new_height), Image.Resampling.LANCZOS)
        
        image.save(buffer, format='JPEG', quality=85)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
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
        debug_log(f"Clasificación de imagen: {classification}")
        return classification
        
    except Exception as e:
        debug_log(f"Error clasificando imagen: {str(e)}")
        return "local_photo"

def process_uploaded_image_llm(uploaded_file, graph_state, insurance_agent, api_key):
    """Procesa imagen subida para el agente LLM - AUTOMATIZADO"""
    try:
        debug_log(f"Procesando imagen: {uploaded_file.name}")
        
        # Convertir a PIL Image
        pil_image = Image.open(uploaded_file)
        
        # Clasificar tipo de imagen
        image_type = classify_image_type(pil_image, api_key)
        debug_log(f"Tipo de imagen detectado: {image_type}")
        
        if image_type == "certificate":
            # Procesar certificado automáticamente
            debug_log("Procesando certificado automáticamente...")
            graph_state = insurance_agent.process_certificate_image(graph_state, pil_image)
            
            # AUTOMÁTICO: Hacer que el LLM procese y cotice inmediatamente
            graph_state = insurance_agent.process_conversation(
                graph_state, 
                f"He subido mi certificado de funcionamiento ({uploaded_file.name}). Por favor analízalo y genera mi cotización automáticamente."
            )
            
        else:  # local_photo
            # Procesar foto del local
            debug_log("Procesando foto del local...")
            graph_state = insurance_agent.process_local_photos(graph_state, [pil_image])
            
            graph_state = insurance_agent.process_conversation(
                graph_state, 
                f"He subido una foto de mi local comercial ({uploaded_file.name})."
            )
        
        return graph_state, "Procesando imagen..."
        
    except Exception as e:
        error_msg = f"Error procesando imagen: {str(e)}"
        debug_log(error_msg)
        return graph_state, error_msg

def initialize_session_state():
    """Inicializa el estado de la sesión"""
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    
    if "insurance_agent" not in st.session_state:
        st.session_state.insurance_agent = None
    
    if "graph_state" not in st.session_state:
        st.session_state.graph_state = None

def render_progress_panel():
    """Renderiza el panel de progreso"""
    st.subheader("📊 Progreso del Seguro")
    
    if not st.session_state.graph_state:
        return
    
    state = st.session_state.graph_state
    business_info = state.get("business_info", BusinessInfo())
    
    progress_items = [
        ("📄 Certificado", bool(business_info.direccion or business_info.tipo_negocio)),
        ("💰 Cotización", bool(state.get("valuation"))),
        ("📋 Póliza", bool(state.get("policy"))),
        ("📊 Audio", bool(state.get("audio_file")))
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
            st.success("✅ Póliza lista para descargar")
        
        # Descargar audio
        if state.get("audio_file"):
            audio_file_path = state["audio_file"]
            
            try:
                if os.path.exists(audio_file_path):
                    with open(audio_file_path, 'rb') as audio_file:
                        audio_data = audio_file.read()
                    
                    st.download_button(
                        "🔊 Descargar Audio",
                        data=audio_data,
                        file_name=f"resumen_poliza_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3",
                        mime="audio/mp3",
                        use_container_width=True
                    )
                    
                    # Reproductor de audio
                    st.audio(audio_data, format='audio/mp3')
                    st.success("✅ Audio listo para descargar")
                    
                else:
                    st.error("❌ Archivo de audio no encontrado")
                    
            except Exception as e:
                st.error(f"❌ Error cargando audio: {str(e)}")

def render_download_buttons_in_chat():
    """Renderiza botón de descarga de póliza y reproductor de audio en el chat"""
    state = st.session_state.graph_state
    
    if state.get("policy") and state.get("audio_file"):
        st.markdown("---")
        st.markdown("### 📥 Tus documentos están listos:")
        
        # Botón de descarga de póliza (mantener como estaba)
        policy_content = state["policy"].content
        st.download_button(
            "📄 Descargar Póliza",
            data=policy_content,
            file_name=f"poliza_seguro_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            type="primary"
        )
        
        st.markdown("---")
        
        # Reproductor de audio integrado
        audio_file_path = state["audio_file"]
        try:
            if os.path.exists(audio_file_path):
                with open(audio_file_path, 'rb') as audio_file:
                    audio_data = audio_file.read()
                
                st.markdown("### 🔊 Resumen en audio de tu póliza:")
                st.audio(audio_data, format='audio/mp3')
                
                # Opcional: Botón pequeño de descarga del audio también
                st.download_button(
                    "💾 Descargar Audio",
                    data=audio_data,
                    file_name=f"resumen_poliza_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3",
                    mime="audio/mp3",
                    help="Descarga el archivo de audio para guardarlo"
                )
                
            else:
                st.error("Audio no disponible")
        except Exception as e:
            st.error(f"Error cargando el audio: {str(e)}")

def render_enhanced_conversation_llm():
    """Renderiza la conversación con botones de confirmación corregidos"""
    st.subheader("💬 Conversación con tu Agente de Seguros IA")
    
    if not st.session_state.graph_state:
        st.warning("Configura tu API Key para comenzar")
        return
    
    # Mostrar mensajes de la conversación
    messages = st.session_state.graph_state.get("messages", [])
    
    for i, message in enumerate(messages):
        if message["role"] == "user":
            st.chat_message("user", avatar="👤").write(message["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.write(message["content"])
                
                # CONDICIONES PARA MOSTRAR BOTONES DE CONFIRMACIÓN
                is_last_message = (i == len(messages) - 1)
                is_assistant = (message["role"] == "assistant")
                has_valuation = bool(st.session_state.graph_state.get("valuation"))
                no_policy = not bool(st.session_state.graph_state.get("policy"))
                mentions_policy = ("póliza" in message["content"].lower() or "poliza" in message["content"].lower())
                
                should_show_confirmation = (is_last_message and is_assistant and has_valuation and no_policy and mentions_policy)
                

                
                # MOSTRAR BOTONES DE CONFIRMACIÓN SI CUMPLE CONDICIONES
                if should_show_confirmation:
                    st.markdown("---")
                    st.markdown("### 🎯 CONFIRMACIÓN REQUERIDA")
                    st.write("**¿Deseas generar tu póliza oficial ahora?**")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("✅ SÍ, GENERAR PÓLIZA", key=f"confirm_yes_{i}", type="primary", use_container_width=True):
                            with st.spinner("Generando póliza y audio..."):
                                st.session_state.graph_state = st.session_state.insurance_agent.process_conversation(
                                    st.session_state.graph_state, 
                                    "sí, confirmo generar póliza"
                                )
                            st.rerun()
                    
                    with col2:
                        if st.button("❌ NO, DESPUÉS", key=f"confirm_no_{i}", type="secondary", use_container_width=True):
                            st.session_state.graph_state = st.session_state.insurance_agent.process_conversation(
                                st.session_state.graph_state, 
                                "no, generar después"
                            )
                            st.rerun()
                
                # MOSTRAR BOTONES DE DESCARGA SI LA PÓLIZA ESTÁ LISTA
                elif (is_last_message and 
                      st.session_state.graph_state.get("policy") and 
                      st.session_state.graph_state.get("audio_file")):
                    render_download_buttons_in_chat()
    
    # Input para nuevos mensajes
    try:
        prompt = st.chat_input(
            "Sube tu certificado o escribe tu mensaje...",
            accept_file=True,
            file_type=["jpg", "jpeg", "png"]
        )
    except:
        # Fallback para versiones de Streamlit sin soporte de archivos
        col1, col2 = st.columns([4, 1])
        with col1:
            text_input = st.text_input("Escribe tu mensaje:", key="text_input")
        with col2:
            uploaded_files = st.file_uploader("Subir imagen", type=["jpg", "jpeg", "png"], 
                                            accept_multiple_files=True, key="file_upload")
        
        prompt = None
        if text_input or uploaded_files:
            prompt = {
                'text': text_input if text_input else "",
                'files': uploaded_files if uploaded_files else []
            }
    
    if prompt:
        # Manejar diferentes tipos de input
        if isinstance(prompt, str):
            user_message = prompt
            uploaded_files = []
        elif hasattr(prompt, 'text') and hasattr(prompt, 'files'):
            user_message = prompt.text if prompt.text else ""
            uploaded_files = prompt.files if prompt.files else []
        elif isinstance(prompt, dict):
            user_message = prompt.get('text', '')
            uploaded_files = prompt.get('files', [])
        else:
            user_message = str(prompt)
            uploaded_files = []
        
        # Procesar imágenes primero (si las hay)
        if uploaded_files:
            if not isinstance(uploaded_files, list):
                uploaded_files = [uploaded_files]
                
            for uploaded_file in uploaded_files:
                debug_log(f"Procesando imagen: {uploaded_file.name}")
                
                with st.spinner(f"Analizando {uploaded_file.name}..."):
                    try:
                        # Procesar la imagen con el agente LLM modificado
                        new_state, response_msg = process_uploaded_image_llm(
                            uploaded_file, 
                            st.session_state.graph_state,
                            st.session_state.insurance_agent,
                            st.session_state.api_key
                        )
                        
                        # Actualizar el estado
                        st.session_state.graph_state = new_state
                        debug_log(f"Imagen {uploaded_file.name} procesada exitosamente")
                        
                    except Exception as e:
                        debug_log(f"Error procesando imagen: {str(e)}")
                        st.error(f"Error procesando imagen: {str(e)}")
        
        # Procesar mensaje de texto (si lo hay)
        if user_message and user_message.strip():
            with st.spinner("Procesando mensaje..."):
                try:
                    # Usar el agente LLM para procesar la conversación
                    st.session_state.graph_state = st.session_state.insurance_agent.process_conversation(
                        st.session_state.graph_state, 
                        user_message
                    )
                    debug_log("Mensaje de texto procesado exitosamente")
                except Exception as e:
                    debug_log(f"Error en la conversación: {str(e)}")
                    st.error(f"Error en la conversación: {str(e)}")
        
        # Si se procesó algo, recargar la página
        if (uploaded_files and len(uploaded_files) > 0) or (user_message and user_message.strip()):
            st.rerun()
    
    # Información adicional
    st.info("🚀 **Proceso automatizado** - Solo sube tu certificado y recibe tu cotización al instante")


# Configuración de página
st.set_page_config(
    page_title="🤖 Agente de Seguros IA - Pacífico",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)




import streamlit as st
import streamlit.components.v1 as components

def load_pacifico_styles():
    """Carga los estilos de PacÃ­fico Seguros con carrusel"""
    
    st.html("""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
    :root{
        --p-navy:#003B73;
        --p-blue:#005CB9;
        --p-cyan:#00AEEF;
        --p-bg:#F4F9FF;
        --p-text:#0B2239;
        --p-success:#2BB673;
    }
    
    /* Force font loading */
    html, body, [class*="css"], .stApp, div[data-testid="stAppViewContainer"] { 
        font-family:'Inter', sans-serif !important; 
    }
    
    /* Background fix */
    .stApp, div[data-testid="stAppViewContainer"] > div:first-child {
        background-color: var(--p-bg) !important;
    }
    
    /* ========== CARRUSEL STYLES ========== */
    .carousel-container {
        position: relative;
        width: 100%;
        height: 300px;
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 14px 34px rgba(0,92,185,.25);
        margin: 20px 0;
    }
    
    .carousel-slide {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        transition: opacity 0.8s ease-in-out;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 40px;
        box-sizing: border-box;
    }
    
    .carousel-slide.active {
        opacity: 1;
    }
    
    /* Slide 1: Gradiente principal con IA */
    .slide-1 {
        background: linear-gradient(135deg, var(--p-navy) 0%, var(--p-blue) 55%, var(--p-cyan) 100%);
        color: white;
    }
    
    /* Slide 2: Seguros de auto */
    .slide-2 {
        background: linear-gradient(135deg, #1a472a 0%, #2d5a3d 50%, #48a867 100%);
        color: white;
    }
    
    /* Slide 3: Seguros de hogar */
    .slide-3 {
        background: linear-gradient(135deg, #8b3a3a 0%, #a04747 50%, #d4776b 100%);
        color: white;
    }
    
    /* Contenido del slide */
    .slide-content {
        flex: 1;
        max-width: 60%;
        z-index: 2;
        position: relative;
    }
    
    .slide-content h1 {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 0 0 15px;
        line-height: 1.2;
    }
    
    .slide-content p {
        font-size: 1.1rem;
        margin: 0 0 20px;
        opacity: 0.95;
        line-height: 1.5;
    }
    
    .slide-content .features {
        font-size: 0.95rem;
        opacity: 0.9;
        margin-bottom: 25px;
    }
    
    /* Imagen del slide */
    .slide-image {
        flex: 0 0 35%;
        max-width: 250px;
        height: 200px;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
    }
    
    .slide-image img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        filter: drop-shadow(0 10px 20px rgba(0,0,0,0.3));
        transition: transform 0.3s ease;
    }
    
    .slide-image:hover img {
        transform: scale(1.05);
    }
    
    /* Emoji como imagen alternativa */
    .slide-emoji {
        font-size: 8rem;
        opacity: 0.9;
        text-shadow: 0 10px 20px rgba(0,0,0,0.3);
        transition: transform 0.3s ease;
    }
    
    .slide-image:hover .slide-emoji {
        transform: scale(1.1) rotate(5deg);
    }
    
    /* Botones del carrusel */
    .cta-row { 
        margin-top: 20px; 
        display: flex; 
        gap: 12px; 
        flex-wrap: wrap; 
    }
    
    .btn-primary, .btn-ghost{ 
        text-decoration: none; 
        font-weight: 700; 
        border-radius: 12px; 
        padding: 12px 18px;
        display: inline-block;
        transition: all 0.3s ease;
        font-size: 0.95rem;
    }
    
    .btn-primary{ 
        background: rgba(255,255,255,0.95); 
        color: var(--p-navy); 
        box-shadow: 0 8px 18px rgba(0,0,0,.15); 
    }
    
    .btn-primary:hover {
        background: white;
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(0,0,0,.2);
    }
    
    .btn-ghost{ 
        background: rgba(255,255,255,0.15); 
        color: #fff; 
        border: 1.5px solid rgba(255,255,255,.7);
        backdrop-filter: blur(10px);
    }
    
    .btn-ghost:hover {
        background: rgba(255,255,255,.25);
        border-color: rgba(255,255,255,.9);
        transform: translateY(-1px);
    }
    
    /* NavegaciÃ³n del carrusel */
    .carousel-nav {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        gap: 8px;
        z-index: 10;
    }
    
    .carousel-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: rgba(255,255,255,0.4);
        cursor: pointer;
        transition: all 0.3s ease;
        border: 2px solid transparent;
    }
    
    .carousel-dot.active {
        background: white;
        box-shadow: 0 0 0 2px rgba(255,255,255,0.3);
    }
    
    .carousel-dot:hover {
        background: rgba(255,255,255,0.7);
        transform: scale(1.2);
    }
    
    /* Flechas de navegaciÃ³n */
    .carousel-arrow {
        position: absolute;
        top: 50%;
        transform: translateY(-50%);
        background: rgba(255,255,255,0.2);
        border: none;
        color: white;
        font-size: 1.5rem;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        cursor: pointer;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .carousel-arrow:hover {
        background: rgba(255,255,255,0.3);
        transform: translateY(-50%) scale(1.1);
    }
    
    .carousel-arrow.prev {
        left: 15px;
    }
    
    .carousel-arrow.next {
        right: 15px;
    }
    
    /* Brand chip */
    .brand-chip{
        position: absolute; 
        top: 20px; 
        right: 20px; 
        background: rgba(255,255,255,0.95); 
        color: var(--p-navy);
        border-radius: 999px; 
        padding: 8px 16px; 
        font-weight: 700;
        box-shadow: 0 10px 22px rgba(0,60,115,.18);
        font-size: 0.85rem;
        z-index: 10;
        backdrop-filter: blur(10px);
    }
    
    /* Streamlit button overrides */
    .stButton > button{
        background: var(--p-blue) !important; 
        color: #fff !important; 
        border: 0 !important;
        border-radius: 12px !important; 
        padding: 10px 16px !important;
        box-shadow: 0 8px 18px rgba(0,92,185,.20) !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover{ 
        filter: brightness(1.05);
        transform: translateY(-1px);
    }
    
    /* Mobile responsiveness */
    @media (max-width: 768px) {
        .carousel-container {
            height: 400px;
        }
        
        .carousel-slide {
            flex-direction: column;
            text-align: center;
            padding: 30px 20px;
            gap: 20px;
        }
        
        .slide-content {
            max-width: 100%;
            order: 2;
        }
        
        .slide-content h1 {
            font-size: 1.6rem;
        }
        
        .slide-image {
            order: 1;
            flex: 0 0 auto;
            max-width: 150px;
            height: 120px;
        }
        
        .slide-emoji {
            font-size: 4rem;
        }
        
        .brand-chip {
            position: relative;
            top: auto;
            right: auto;
            margin-bottom: 10px;
            display: inline-block;
        }
        
        .cta-row {
            flex-direction: column;
            gap: 8px;
        }
        
        .btn-primary, .btn-ghost {
            text-align: center;
            width: 100%;
        }
        
        .carousel-arrow {
            display: none; /* Ocultar flechas en mÃ³vil */
        }
    }
    </style>
    """)
import streamlit as st, base64, pathlib

def img_tag_local(path: str, alt=""):
    b64 = base64.b64encode(pathlib.Path(path).read_bytes()).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="max-width:100%;height:auto;border-radius:12px">'
b64 = base64.b64encode(pathlib.Path("file.png").read_bytes()).decode("utf-8")


def render_carousel():
    """Renderiza el carrusel principal de Pacífico"""
    st.html(f"""
    <div class="carousel-container">
        <span class="brand-chip">Pacífico Seguros · IA</span>
        
        <!-- Slide 1: IA Agent -->
        <div class="carousel-slide slide-1 active">
            <div class="slide-content">
                <h1>🛡️ Agente de Seguros IA</h1>
                <p>Tu asistente conversacional inteligente que cotiza lo mejor para tu negocio</p>
                <div class="features">✓ Cotizaciones instantáneas 24/7 </div>
                <div class="cta-row">
                    <a class="btn-primary" href="https://www.pacifico.com.pe" target="_blank">Pacifico Seguros</a>
                </div>
            </div>
            <div class="slide-image">
                <!-- Puedes reemplazar el emoji con una imagen real 
                <div class="slide-emoji">🤖</div>-->
               <img  src="data:image/png;base64,{b64}alt="IA Assistant">
            </div>
        </div>
        
    
    </div>
    
    
    """)

def main():
    """Función principal simplificada"""
    
    # Header
    load_pacifico_styles()
    
    # Renderizar header
    render_carousel()
    # Inicializar estado
    initialize_session_state()
    
    # Sidebar para configuración
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        # API Key
        api_key = st.secrets["api_key"]
        
        if api_key != st.session_state.api_key:
            st.session_state.api_key = api_key
            st.session_state.insurance_agent = None
            st.session_state.graph_state = None
        
        if not api_key:
            st.warning("⚠️ Ingresa tu API Key para comenzar")
            return
        
        # Configurar agente
        if setup_insurance_agent(api_key):
            st.success("✅ Agente IA configurado")
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
        
        # Botón para reiniciar
        if st.button("🔄 Nueva Consulta", use_container_width=True):
            api_key_backup = st.session_state.api_key
            st.session_state.clear()
            st.session_state.api_key = api_key_backup
            st.rerun()
    
    # Conversación principal con botones interactivos
    render_enhanced_conversation_llm()

if __name__ == "__main__":
    main()