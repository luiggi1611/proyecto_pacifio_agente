import openai
import re
from typing import List, Dict, Any
from models import GraphState, ConversationStep, BusinessInfo, Valuation
from certificate_analyzer import CertificateAnalyzer
from valuation_engine import ValuationEngine
from policy_generator import PolicyGenerator

class ConversationNodes:
    """Nodos del grafo de conversación para el agente de seguros"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.certificate_analyzer = CertificateAnalyzer(api_key)
        self.valuation_engine = ValuationEngine()
        self.policy_generator = PolicyGenerator()
    
    def welcome_node(self, state: GraphState) -> GraphState:
        """Nodo de bienvenida inicial"""
        if not state["messages"]:
            welcome_message = {
                "role": "assistant",
                "content": """¡Hola! 👋 Soy tu agente de seguros comerciales de Seguros Pacífico.

Estoy aquí para ayudarte a crear una póliza personalizada para tu negocio. Mi objetivo es proteger tu inversión con la cobertura más adecuada.

Para comenzar, puedo trabajar con:
📄 **Certificados de funcionamiento** (PDF/Word/TXT)
📸 **Fotos del certificado** de funcionamiento  
📷 **Fotos de tu local** comercial
💬 **Información que me proporciones** directamente

¿Podrías empezar compartiéndome el certificado de funcionamiento o contándome sobre tu negocio? 

Por ejemplo: "Tengo una panadería de 50m²" o sube una foto/documento."""
            }
            
            state["messages"].append(welcome_message)
            state["current_step"] = ConversationStep.GATHERING_INFO
            state["needs_certificate"] = True
            state["next_action"] = "wait_for_input"
        
        return state
    
    def analyze_input_node(self, state: GraphState) -> GraphState:
        """Analiza la entrada del usuario y determina la siguiente acción"""
        user_input = state["user_input"].lower()
        
        # Extraer información básica del mensaje
        extracted_info = self._extract_info_from_text(state["user_input"])
        
        # Actualizar business_info con información extraída
        if extracted_info:
            for key, value in extracted_info.items():
                if value and not getattr(state["business_info"], key, None):
                    setattr(state["business_info"], key, value)
        
        # Determinar siguiente acción basada en lo que tenemos
        missing_info = self._identify_missing_info(state["business_info"])
        
        if missing_info:
            state["next_action"] = "gather_info"
            response = self._generate_info_request(missing_info, state["business_info"])
        elif state["business_info"].metraje and state["local_photos"]:
            state["next_action"] = "calculate_valuation"
            response = "Perfecto, tengo toda la información necesaria. Procediendo a calcular la valuación..."
        elif state["business_info"].metraje and not state["local_photos"]:
            state["next_action"] = "request_photos"
            response = f"""Excelente, ya tengo la información básica de tu {state["business_info"].tipo_negocio or 'negocio'} de {state["business_info"].metraje}m².

📸 **Ahora necesito fotos de tu local** para hacer una valuación precisa. Por favor sube fotos que muestren:
• Vista general del interior
• Inventario/mercancía
• Mobiliario y equipos
• Fachada del local

Esto me permitirá calcular el valor exacto para tu seguro."""
        else:
            state["next_action"] = "gather_info"
            response = self._generate_follow_up_question(state["business_info"])
        
        state["messages"].append({
            "role": "assistant",
            "content": response
        })
        
        return state
    
    def certificate_analysis_node(self, state: GraphState) -> GraphState:
        """Analiza certificados de funcionamiento"""
        if state["certificate_text"]:
            # Analizar documento de texto
            business_info = self.certificate_analyzer.analyze_document(state["certificate_text"])
        elif state["certificate_images"]:
            # Analizar imagen del certificado
            # Convertir SerializableImage a PIL Image
            cert_image = state["certificate_images"][0].to_pil_image()
            business_info = self.certificate_analyzer.analyze_image(cert_image)
        else:
            return state
        
        # Actualizar información del negocio
        state["business_info"] = self._merge_business_info(state["business_info"], business_info)
        state["current_step"] = ConversationStep.ANALYZING_CERTIFICATE
        
        # Generar resumen del análisis
        summary = self._generate_certificate_analysis_summary(business_info)
        
        state["messages"].append({
            "role": "assistant",
            "content": summary
        })
        
        # Determinar siguiente paso
        if state["business_info"].metraje:
            state["next_action"] = "request_photos"
        else:
            state["next_action"] = "request_metraje"
        
        return state
    
    def valuation_node(self, state: GraphState) -> GraphState:
        """Calcula la valuación del negocio"""
        if not state["business_info"].metraje:
            state["messages"].append({
                "role": "assistant",
                "content": "No puedo calcular la valuación sin el metraje del local. ¿Podrías proporcionármelo?"
            })
            state["next_action"] = "gather_info"
            return state
        
        # Calcular valuación
        photos_count = len(state["local_photos"]) if state["local_photos"] else 0
        valuation = self.valuation_engine.estimate_property_value(
            state["business_info"], 
            photos_count
        )
        
        state["valuation"] = valuation
        state["current_step"] = ConversationStep.VALUATION_COMPLETE
        
        # Generar cotización
        quote_summary = self.policy_generator.generate_quote_summary(
            state["business_info"], 
            valuation
        )
        
        state["messages"].append({
            "role": "assistant",
            "content": quote_summary
        })
        
        state["next_action"] = "await_confirmation"
        state["needs_confirmation"] = True
        
        return state
    
    def policy_generation_node(self, state: GraphState) -> GraphState:
        """Genera la póliza de seguro"""
        if not state["valuation"]:
            state["next_action"] = "calculate_valuation"
            return state
        
        # Generar póliza
        policy = self.policy_generator.generate_policy(
            state["business_info"],
            state["valuation"]
        )
        
        state["policy"] = policy
        state["current_step"] = ConversationStep.POLICY_GENERATED
        state["ready_for_policy"] = True
        
        response = f"""{policy.content}

✅ **¡Tu póliza ha sido generada exitosamente!**

¿Te gustaría que también genere un resumen en audio de tu póliza para que puedas escuchar los puntos más importantes?"""
        
        state["messages"].append({
            "role": "assistant",
            "content": response
        })
        
        state["next_action"] = "offer_audio"
        
        return state
    
    def audio_generation_node(self, state: GraphState) -> GraphState:
        """Genera el resumen en audio"""
        if not state["policy"]:
            state["next_action"] = "generate_policy"
            return state
        
        # Generar audio
        audio_file, summary_text = self.policy_generator.generate_audio_summary(
            state["business_info"],
            state["valuation"],
            state["policy"]
        )
        
        if audio_file:
            state["audio_file"] = audio_file
            state["audio_summary"] = summary_text
            state["current_step"] = ConversationStep.AUDIO_GENERATED
            
            response = """🔊 **¡Perfecto! He generado tu resumen en audio.**

Tu póliza está completamente lista. Tienes disponible:
📄 **Póliza completa** en formato texto
🔊 **Resumen en audio** con los puntos principales

¿Hay algo más en lo que pueda ayudarte? Por ejemplo:
• Explicar alguna cobertura específica
• Ajustar algún valor de la póliza
• Información sobre el proceso de pago
• Dudas sobre el procedimiento en caso de siniestro"""
        else:
            response = """✅ **Tu póliza está lista para descargar.**

Hubo un problema generando el audio, pero tienes disponible la póliza completa en formato texto.

¿Hay algo más en lo que pueda ayudarte con tu seguro?"""
        
        state["messages"].append({
            "role": "assistant",
            "content": response
        })
        
        state["next_action"] = "complete"
        state["current_step"] = ConversationStep.COMPLETE
        
        return state
    
    def sales_assistance_node(self, state: GraphState) -> GraphState:
        """Nodo para asistencia adicional - CORREGIDO"""
        user_input = state["user_input"].lower()
        
        # NUEVO: Verificar el estado actual para dar respuestas apropiadas
        has_policy = bool(state.get("policy"))
        has_valuation = bool(state.get("valuation"))
        has_audio = bool(state.get("audio_file"))
        
        # Detectar tipos de consultas
        if any(word in user_input for word in ["cobertura", "cubre", "incluye", "protege", "explica"]):
            response = self._handle_coverage_questions(state, has_policy)
        elif any(word in user_input for word in ["precio", "costo", "prima", "pago", "cuanto"]):
            response = self._handle_pricing_questions(state, has_policy)
        elif any(word in user_input for word in ["contratar", "comprar", "adquirir", "firmar"]):
            response = self._handle_purchase_intent(state, has_policy)
        elif any(word in user_input for word in ["siniestro", "dano", "daño", "accidente", "reclamo"]):
            response = self._handle_claims_questions(state)
        elif any(word in user_input for word in ["documentos", "papeles", "requisitos", "necesito"]):
            response = self._handle_documents_questions(state, has_policy)
        else:
            response = self._generate_sales_response(user_input, state)
        
        state["messages"].append({
            "role": "assistant",
            "content": response
        })
        
        # NO cambiar current_step ni next_action - mantener estado actual
        return state

    
    def _extract_info_from_text(self, text: str) -> Dict[str, Any]:
        """Extrae información del negocio del texto del usuario"""
        extracted = {}
        text_lower = text.lower()
        
        # Extraer metraje
        metraje_patterns = [
            r'(\d+\.?\d*)\s*m[²2]',
            r'(\d+\.?\d*)\s*metros?\s*cuadrados?',
            r'(\d+\.?\d*)\s*m\s*cuadrados?'
        ]
        
        for pattern in metraje_patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    extracted['metraje'] = float(match.group(1))
                    break
                except:
                    continue
        
        # Extraer tipo de negocio
        business_types = {
            "restaurante": ["restaurante", "restaurant", "comida", "cocina", "cevichería"],
            "tienda": ["tienda", "store", "comercio", "venta", "bodega", "minimarket"],
            "oficina": ["oficina", "office", "administrativa", "servicios"],
            "farmacia": ["farmacia", "botica", "medicinas", "droguería"],
            "bar": ["bar", "cantina", "licores", "discoteca", "pub"],
            "panadería": ["panadería", "bakery", "pan", "pastelería", "repostería"],
            "taller": ["taller", "mecánica", "reparación", "automotriz"],
            "consultorio": ["consultorio", "clínica", "médico", "dental", "veterinaria"],
            "salon": ["salón", "peluquería", "spa", "belleza", "estética"]
        }
        
        for business_type, keywords in business_types.items():
            if any(keyword in text_lower for keyword in keywords):
                extracted['tipo_negocio'] = business_type
                break
        
        return extracted
    
    def _identify_missing_info(self, business_info: BusinessInfo) -> List[str]:
        """Identifica qué información falta"""
        missing = []
        
        if not business_info.metraje:
            missing.append("metraje")
        if not business_info.tipo_negocio:
            missing.append("tipo_negocio")
        if not business_info.direccion:
            missing.append("direccion")
        
        return missing
    
    def _generate_info_request(self, missing_info: List[str], business_info: BusinessInfo) -> str:
        """Genera solicitud de información faltante"""
        responses = {
            "metraje": "¿Cuántos metros cuadrados tiene tu local?",
            "tipo_negocio": "¿Qué tipo de negocio tienes? (ej: restaurante, tienda, oficina)",
            "direccion": "¿Cuál es la dirección de tu negocio?"
        }
        
        if len(missing_info) == 1:
            return responses[missing_info[0]]
        else:
            requests = [responses[info] for info in missing_info[:2]]
            return f"Para cotizar tu seguro necesito: {' y '.join(requests)}"
    
    def _generate_follow_up_question(self, business_info: BusinessInfo) -> str:
        """Genera pregunta de seguimiento basada en la información actual"""
        if business_info.tipo_negocio and not business_info.metraje:
            return f"Perfecto, tienes un {business_info.tipo_negocio}. ¿Cuántos metros cuadrados tiene?"
        elif business_info.metraje and not business_info.tipo_negocio:
            return f"Entiendo que tu local tiene {business_info.metraje}m². ¿Qué tipo de negocio es?"
        else:
            return "¿Podrías contarme más detalles sobre tu negocio para poder cotizar tu seguro?"
    
    def _merge_business_info(self, existing: BusinessInfo, new: BusinessInfo) -> BusinessInfo:
        """Combina información de negocio existente con nueva"""
        merged_dict = existing.to_dict()
        
        for key, value in new.to_dict().items():
            if value and not merged_dict.get(key):
                merged_dict[key] = value
        
        return BusinessInfo.from_dict(merged_dict)
    
    def _generate_certificate_analysis_summary(self, business_info: BusinessInfo) -> str:
        """Genera resumen del análisis del certificado"""
        summary = "📄 **He analizado tu certificado de funcionamiento:**\n\n"
        
        if business_info.nombre_cliente:
            summary += f"• **Cliente:** {business_info.nombre_cliente}\n"
        if business_info.direccion:
            summary += f"• **Dirección:** {business_info.direccion}\n"
        if business_info.tipo_negocio:
            summary += f"• **Tipo de negocio:** {business_info.tipo_negocio}\n"
        if business_info.metraje:
            summary += f"• **Área:** {business_info.metraje} m²\n"
        if business_info.ruc:
            summary += f"• **RUC:** {business_info.ruc}\n"
        
        if not business_info.metraje:
            summary += "\n❓ No pude encontrar el metraje exacto en el certificado. ¿Podrías decirme cuántos metros cuadrados tiene tu local?"
        else:
            summary += "\n📸 **Siguiente paso:** Necesito fotos del local para hacer la valuación precisa."
        
        return summary
    
    def _handle_pricing_questions(self, state: GraphState, has_policy: bool = False) -> str:
        """Maneja preguntas sobre precios - CORREGIDO"""
        if state["valuation"]:
            premium_annual = state["valuation"].total * 0.025
            premium_monthly = premium_annual / 12
            
            if has_policy:
                # Si ya tiene póliza, dar información más específica
                return f"""💰 **Información detallada de costos de tu póliza activa:**

    **💳 Prima de tu seguro:**
    • **Prima anual:** S/ {premium_annual:,.2f}
    • **Prima mensual:** S/ {premium_monthly:,.2f}
    • **Prima diaria:** Solo S/ {premium_monthly/30:,.0f} soles

    **📋 Opciones de pago:**
    • **Anual:** S/ {premium_annual:,.2f} (sin recargo)
    • **Semestral:** S/ {premium_annual/2*1.02:,.2f} (2% recargo)
    • **Trimestral:** S/ {premium_annual/4*1.03:,.2f} por cuota (3% recargo)
    • **Mensual:** S/ {premium_monthly*1.05:,.2f} por cuota (5% recargo)

    **💡 Recomendación:** El pago anual te ahorra hasta S/ {premium_annual*0.05:,.0f} en recargos.

    **🎯 Valor asegurado:** S/ {state["valuation"].total:,.2f}
    Esto significa que pagas solo el {(premium_annual/state["valuation"].total)*100:.2f}% del valor de tu negocio por protección completa.

    ¿Te gustaría información sobre formas de pago o descuentos disponibles?"""
            else:
                # Si no tiene póliza, usar respuesta original
                return f"""💰 **Información de costos de tu seguro:**

    • **Prima anual:** S/ {premium_annual:,.2f}
    • **Prima mensual:** S/ {premium_monthly:,.2f}
    • **Por día:** Solo S/ {premium_monthly/30:,.0f} soles

    **¿Sabías que?** Por menos de lo que gastas en un café al día, proteges completamente tu negocio.

    La prima se calcula sobre el valor total asegurado de S/ {state["valuation"].total:,.2f}, lo que representa una excelente protección para tu inversión."""
        else:
            return "Para darte el precio exacto necesito calcular la valuación de tu negocio. ¿Podrías proporcionarme el metraje y tipo de negocio?"

    def _handle_coverage_questions(self, state: GraphState, has_policy: bool = False) -> str:
        """Maneja preguntas sobre coberturas - CORREGIDO"""
        if has_policy:
            # Si ya tiene póliza, dar información más detallada y específica
            return """🛡️ **Coberturas ACTIVAS en tu póliza:**

    **🔥 INCENDIO Y EXPLOSIÓN**
    • Daños por fuego, rayo, explosión
    • Gastos de extinción y salvamento
    • Daños por humo y calor
    • **Cobertura:** 100% suma asegurada

    **🚨 ROBO Y HURTO**
    • Sustracción violenta o clandestina
    • Daños por intento de robo
    • Robo de dinero en efectivo (hasta S/ 2,000)
    • **Cobertura:** 100% suma asegurada

    **💧 DAÑOS POR AGUA**
    • Filtración, desborde, rotura de tuberías
    • Daños por lluvia e inundación
    • Rotura de tanques y cisternas
    • **Cobertura:** 100% suma asegurada

    **🌪️ FENÓMENOS NATURALES**
    • Terremoto, maremoto, huayco
    • Vientos huracanados
    • Granizo y avalanchas
    • **Deducible:** 5% del siniestro (mín. S/ 1,000)

    **👥 RESPONSABILIDAD CIVIL**
    • Daños a terceros hasta S/ 100,000
    • Gastos de defensa legal
    • Daños por productos defectuosos
    • **Sin deducible**

    **💼 LUCRO CESANTE**
    • Pérdida de ingresos hasta 6 meses
    • 60% de tus ingresos promedio
    • Gastos adicionales de funcionamiento
    • **Período de espera:** 72 horas

    **🆘 SERVICIOS DE EMERGENCIA 24/7**
    • Cerrajería de emergencia
    • Plomería básica
    • Limpieza post-siniestro
    • **Sin costo adicional**

    ¿Quieres que te explique alguna cobertura en detalle?"""
        else:
            # Respuesta original si no tiene póliza
            return """🛡️ **Tu seguro incluye cobertura completa:**

    **🔥 Incendio y Explosión**
    • Daños por fuego, rayo, explosión
    • Gastos de extinción y salvamento

    **🚨 Robo y Hurto**
    • Sustracción violenta o clandestina
    • Daños por intento de robo

    **💧 Daños por Agua**
    • Filtración, desborde, rotura de tuberías
    • Daños por lluvia e inundación

    **🌍 Fenómenos Naturales**
    • Terremoto, maremoto, huayco
    • Vientos huracanados

    **👥 Responsabilidad Civil**
    • Daños a terceros hasta S/ 100,000
    • Gastos de defensa legal

    **💼 Lucro Cesante**
    • Pérdida de ingresos hasta 6 meses
    • 60% de tus ingresos promedio

    ¿Te interesa alguna cobertura en particular?"""

    def _handle_purchase_intent(self, state: GraphState, has_policy: bool = False) -> str:
        """Maneja intención de compra - CORREGIDO"""
        if has_policy:
            return """🎉 **¡Tu póliza ya está lista y activa!**

    **📋 Pasos para activar tu seguro:**

    **✅ COMPLETADO:**
    • Análisis de riesgo ✓
    • Valuación personalizada ✓
    • Generación de póliza ✓

    **📝 PENDIENTE - Solo necesitas:**

    **1. 📄 DOCUMENTACIÓN**
    • Copia simple de RUC
    • Certificado de funcionamiento
    • Copia de DNI del representante legal

    **2. 💳 ACTIVACIÓN DEL SEGURO**
    • Primera cuota: S/ {(state['valuation'].total * 0.025 / 12 * 1.05):,.2f} (pago mensual)
    • O prima anual: S/ {(state['valuation'].total * 0.025):,.2f} (ahorro en recargos)

    **3. 🏢 CONTACTO PARA FINALIZAR:**
    • **WhatsApp:** +51 999-123-456 (envía "QUIERO CONTRATAR PÓLIZA")
    • **Email:** ventas@segurospacifico.com.pe
    • **Oficina:** Av. Larco 345, Miraflores
    • **Código de póliza:** POL-{datetime.now().strftime('%Y%m%d')}-{state['business_info'].ruc or '000000'}

    **⚡ ACTIVACIÓN INMEDIATA:** Tu negocio estará protegido desde el momento del primer pago.

    **🎁 BONUS:** Si contratas hoy, recibes 1 mes adicional de cobertura SIN COSTO.

    ¿Listo para activar tu protección?"""
        else:
            return "Perfecto, primero necesito generar tu póliza personalizada. ¿Tienes toda la información de tu negocio lista?"

    def _handle_documents_questions(self, state: GraphState, has_policy: bool = False) -> str:
        """NUEVO: Maneja preguntas sobre documentos"""
        if has_policy:
            return """📄 **Documentos necesarios para activar tu póliza:**

    **📋 DOCUMENTOS OBLIGATORIOS:**
    • ✅ **RUC:** Copia simple vigente
    • ✅ **Certificado de funcionamiento:** El que ya analizaste
    • ✅ **DNI:** Del representante legal

    **📋 DOCUMENTOS ADICIONALES (recomendados):**
    • 📄 **Licencia municipal:** Si tienes
    • 📸 **Fotos actuales:** Las que ya subiste están bien
    • 🏢 **Contrato de alquiler:** Si el local es alquilado
    • 💼 **Estados financieros:** Para mejor evaluación

    **📤 FORMAS DE ENVÍO:**
    • **Email:** documentos@segurospacifico.com.pe
    • **WhatsApp:** +51 999-123-456
    • **Presencial:** Av. Larco 345, Miraflores

    **⏱️ TIEMPO DE PROCESAMIENTO:**
    • Documentos completos: 24 horas
    • Activación inmediata con pago

    ¿Tienes todos los documentos listos?"""
        else:
            return "Una vez que tengas tu póliza generada, te indicaré exactamente qué documentos necesitas."
    def _generate_sales_response(self, user_input: str, state: GraphState) -> str:
        """Genera respuesta de ventas usando IA"""
        try:
            context = f"""
Estado actual: {state['current_step']}
Información del negocio: {state['business_info'].to_dict() if state['business_info'] else 'Ninguna'}
Valuación: {state['valuation'].to_dict() if state.get('valuation') else 'No calculada'}
Póliza generada: {'Sí' if state.get('policy') else 'No'}
"""
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": f"""Eres un agente de seguros comerciales amigable y persuasivo de Seguros Pacífico. 
Tu objetivo es vender el seguro y resolver dudas. Mantén un tono conversacional y enfócate en los beneficios.
Contexto actual: {context}
Responde de manera breve y directa, siempre orientado a cerrar la venta."""
                    },
                    {"role": "user", "content": user_input}
                ]
            )
            return response.choices[0].message.content
        except:
            return "Entiendo tu consulta. ¿En qué más puedo ayudarte con tu seguro comercial?"