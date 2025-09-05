"""
llm_controlled_agent.py
Agente de seguros controlado completamente por LLM con memoria de contexto
"""

import openai
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from models import BusinessInfo, Valuation, InsurancePolicy
from certificate_analyzer import CertificateAnalyzer
from valuation_engine import ValuationEngine
from policy_generator import PolicyGenerator

class LLMControlledInsuranceAgent:
    """Agente de seguros controlado completamente por LLM con memoria de contexto"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.certificate_analyzer = CertificateAnalyzer(api_key)
        self.valuation_engine = ValuationEngine()
        self.policy_generator = PolicyGenerator()
        
        # Memoria de contexto para mantener coherencia
        self.context_memory = {
            "user_preferences": {},
            "conversation_style": "formal",
            "mentioned_concerns": [],
            "business_context": {},
            "interaction_history": []
        }
        
        # Herramientas disponibles para el LLM
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "analyze_certificate",
                    "description": "Analiza un certificado de funcionamiento para extraer información del negocio",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trigger_analysis": {
                                "type": "boolean", 
                                "description": "True para activar el análisis del certificado disponible"
                            }
                        },
                        "required": ["trigger_analysis"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_valuation",
                    "description": "Calcula la valuación del negocio basada en la información disponible",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trigger_calculation": {
                                "type": "boolean",
                                "description": "True para activar el cálculo de valuación"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Razón por la cual se está calculando ahora"
                            }
                        },
                        "required": ["trigger_calculation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_policy",
                    "description": "Genera la póliza de seguro oficial",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trigger_generation": {
                                "type": "boolean",
                                "description": "True para generar la póliza"
                            },
                            "user_confirmation_style": {
                                "type": "string",
                                "description": "Cómo el usuario expresó su confirmación"
                            }
                        },
                        "required": ["trigger_generation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_audio_summary",
                    "description": "Genera un resumen en audio de la póliza",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trigger_audio": {
                                "type": "boolean",
                                "description": "True para generar el audio"
                            }
                        },
                        "required": ["trigger_audio"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_context_memory",
                    "description": "Actualiza la memoria de contexto con información importante del usuario",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_preferences": {
                                "type": "object",
                                "description": "Preferencias del usuario detectadas",
                                "additionalProperties": {"type": "string"}
                            },
                            "conversation_style": {
                                "type": "string",
                                "description": "Estilo conversacional preferido: formal, casual, directo"
                            },
                            "business_context": {
                                "type": "object", 
                                "description": "Contexto adicional del negocio mencionado",
                                "additionalProperties": {"type": "string"}
                            },
                            "concerns": {
                                "type": "array",
                                "description": "Preocupaciones o dudas específicas mencionadas",
                                "items": {
                                    "type": "string"
                                }
                            }
                        }
                    }
                }
            }
        ]
    
    def process_conversation(self, state: dict, user_input: str) -> dict:
        """Procesa la conversación usando LLM como controlador principal con memoria"""
        
        # Actualizar historial de interacciones
        self._update_interaction_history(user_input, state)
        
        # Construir contexto actual para el LLM
        context = self._build_enhanced_context(state)
        
        # Agregar mensaje del usuario
        state["messages"].append({
            "role": "user",
            "content": user_input
        })
        
        # Construir mensaje del sistema con contexto completo y memoria
        system_message = self._build_enhanced_system_message(context)
        
        # Preparar mensajes para el LLM con memoria de contexto
        messages = [{"role": "system", "content": system_message}]
        
        # Agregar resumen de interacciones previas importantes
        if self.context_memory["interaction_history"]:
            context_summary = self._build_context_summary()
            messages.append({
                "role": "system", 
                "content": f"MEMORIA DE CONTEXTO: {context_summary}"
            })
        
        # Agregar mensajes recientes de la conversación
        recent_messages = state["messages"][-8:]  # Últimos 8 mensajes para no saturar
        messages.extend(recent_messages)
        
        try:
            # Llamar al LLM con tools
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.2,  # Más determinista para coherencia
                max_tokens=1500
            )
            
            # Procesar respuesta del LLM
            assistant_message = response.choices[0].message
            
            # Si el LLM quiere usar herramientas
            if assistant_message.tool_calls:
                state = self._execute_tool_calls(state, assistant_message.tool_calls)
                
                # Preparar mensajes para segunda llamada
                messages.append({
                    "role": "assistant", 
                    "content": assistant_message.content or "",
                    "tool_calls": assistant_message.tool_calls
                })
                
                # Agregar resultados de las herramientas
                for tool_call in assistant_message.tool_calls:
                    tool_result = self._get_tool_result(state, tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
                
                # Segunda llamada para respuesta final con contexto actualizado
                final_response = self.client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1000
                )
                
                final_content = final_response.choices[0].message.content
            else:
                final_content = assistant_message.content
            
            # Agregar respuesta del asistente
            state["messages"].append({
                "role": "assistant",
                "content": final_content
            })
            
            # Actualizar memoria con esta interacción
            self._update_memory_from_interaction(user_input, final_content, state)
            
        except Exception as e:
            print(f"Error en conversación LLM: {str(e)}")
            state["messages"].append({
                "role": "assistant",
                "content": f"Disculpa, hubo un error procesando tu solicitud. ¿Podrías intentar de nuevo?"
            })
        
        return state
    
    def _update_interaction_history(self, user_input: str, state: dict):
        """Actualiza el historial de interacciones"""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "state_snapshot": {
                "has_certificate": bool(state.get("certificate_images")),
                "has_photos": len(state.get("local_photos", [])),
                "has_valuation": bool(state.get("valuation")),
                "has_policy": bool(state.get("policy"))
            }
        }
        
        self.context_memory["interaction_history"].append(interaction)
        
        # Mantener solo las últimas 20 interacciones para no saturar
        if len(self.context_memory["interaction_history"]) > 20:
            self.context_memory["interaction_history"] = self.context_memory["interaction_history"][-20:]
    
    def _build_enhanced_context(self, state: dict) -> Dict[str, Any]:
        """Construye el contexto mejorado incluyendo memoria"""
        base_context = {
            "business_info": state.get("business_info", BusinessInfo()).to_dict(),
            "has_certificate": bool(state.get("certificate_images") or state.get("certificate_text")),
            "photos_count": len(state.get("local_photos", [])),
            "has_valuation": bool(state.get("valuation")),
            "has_policy": bool(state.get("policy")),
            "has_audio": bool(state.get("audio_file")),
            "session_id": state.get("session_id"),
            "timestamp": datetime.now().isoformat()
        }
        
        # Agregar información de la memoria
        base_context["memory"] = self.context_memory.copy()
        
        return base_context
    
    def _build_enhanced_system_message(self, context: Dict[str, Any]) -> str:
        """Construye mensaje del sistema mejorado - CORREGIDO PARA EVITAR ENLACES FALSOS"""
        
        business_info_str = json.dumps(context['business_info'], indent=2)
        memory_str = json.dumps(context['memory'], indent=2)
        
        return f"""Eres un agente de seguros comerciales experto y conversacional de Seguros Pacífico con memoria de contexto.

CONTEXTO ACTUAL:
- Información del negocio: {business_info_str}
- ¿Tiene certificado?: {context['has_certificate']}
- Fotos del local: {context['photos_count']}
- ¿Tiene valuación?: {context['has_valuation']}
- ¿Tiene póliza?: {context['has_policy']}
- ¿Tiene audio?: {context['has_audio']}

MEMORIA DE CONTEXTO:
{memory_str}

INSTRUCCIONES CRÍTICAS SOBRE ARCHIVOS:
- NUNCA menciones enlaces de descarga específicos como "Descargar Resumen en Audio"
- NUNCA inventes URLs o enlaces que no existen
- Cuando generes audio, simplemente di: "He generado tu resumen en audio. Estará disponible en el panel de descargas del lado derecho de la pantalla."
- Los archivos se descargan automáticamente desde la interfaz, NO desde enlaces en el chat

PERSONALIDAD Y ESTILO:
- Adapta tu estilo de comunicación basado en la memoria de interacciones previas
- Recuerda las preferencias y preocupaciones del usuario
- Mantén coherencia con el contexto del negocio mencionado anteriormente
- Sé proactivo basándote en patrones de la conversación

OBJETIVO: Ayudar al cliente a obtener un seguro comercial personalizado siguiendo este flujo natural:
1. Recopilar información del negocio (certificado, metraje, tipo, fotos)
2. Calcular valuación cuando tengas suficiente información
3. Generar póliza cuando el cliente esté satisfecho con la cotización
4. Ofrecer resumen en audio si lo desea

HERRAMIENTAS DISPONIBLES:
- analyze_certificate: Para analizar certificados de funcionamiento
- calculate_valuation: Para calcular el valor del negocio
- generate_policy: Para crear la póliza oficial
- generate_audio_summary: Para crear resumen en audio
- update_context_memory: Para actualizar la memoria con información importante

INSTRUCCIONES INTELIGENTES:
1. USA LA MEMORIA: Recuerda preferencias, estilo conversacional y contexto previo
2. SÉ CONVERSACIONAL: No pidas confirmaciones innecesarias, entiende el contexto
3. ADAPTA TU COMUNICACIÓN: Formal/casual según el usuario
4. USA HERRAMIENTAS INTELIGENTEMENTE: Cuando sea lógico, no cuando se lo pidan explícitamente
5. MANTÉN COHERENCIA: Con el contexto del negocio y conversaciones previas
6. SÉ PROACTIVO: Anticipa necesidades basándote en la memoria de contexto
7. NO INVENTES ENLACES: Solo informa que los archivos estarán en el panel de descargas

REGLAS DE DECISIÓN PARA HERRAMIENTAS:
- Analizar certificado: Cuando haya imagen de certificado disponible y no se haya analizado
- Calcular valuación: Cuando tengas tipo de negocio + metraje + (al menos 1 foto OR certificado completo)
- Generar póliza: Cuando el usuario muestre satisfacción/acuerdo con la cotización
- Generar audio: Cuando tengas póliza y el usuario muestre interés en resumen
- Actualizar memoria: Cuando detectes preferencias, estilo, o contexto importante

INFORMACIÓN CRÍTICA NECESARIA:
- Tipo de negocio
- Metraje en m²
- Dirección (del certificado o manual)
- Fotos del local (para valuación precisa)

FRASES CORRECTAS PARA ARCHIVOS:
- "He generado tu resumen en audio. Lo encontrarás en el panel de descargas."
- "Tu póliza está lista. Puedes descargarla desde el panel lateral."
- "El audio estará disponible en unos momentos en la sección de descargas."

FRASES INCORRECTAS (NUNCA USAR):
- "Puedes acceder al resumen en audio a través del siguiente enlace: [cualquier enlace]"
- "Haz clic aquí para descargar"
- "Descargar Resumen en Audio" (como enlace)

Responde de manera natural, inteligente y contextual, usando la memoria para personalizar la experiencia."""
    def _build_context_summary(self) -> str:
        """Construye un resumen del contexto para la memoria"""
        recent_interactions = self.context_memory["interaction_history"][-5:]  # Últimas 5
        
        summary_parts = []
        
        if self.context_memory["user_preferences"]:
            summary_parts.append(f"Preferencias del usuario: {self.context_memory['user_preferences']}")
        
        if self.context_memory["conversation_style"]:
            summary_parts.append(f"Estilo conversacional: {self.context_memory['conversation_style']}")
        
        if self.context_memory["mentioned_concerns"]:
            summary_parts.append(f"Preocupaciones mencionadas: {self.context_memory['mentioned_concerns']}")
        
        if self.context_memory["business_context"]:
            summary_parts.append(f"Contexto del negocio: {self.context_memory['business_context']}")
        
        if recent_interactions:
            summary_parts.append(f"Últimas {len(recent_interactions)} interacciones registradas")
        
        return " | ".join(summary_parts) if summary_parts else "Sin contexto previo"
    
    def _update_memory_from_interaction(self, user_input: str, assistant_response: str, state: dict):
        """Actualiza la memoria basándose en la interacción"""
        
        # Detectar estilo conversacional
        if any(word in user_input.lower() for word in ["por favor", "gracias", "disculpe"]):
            self.context_memory["conversation_style"] = "formal"
        elif any(word in user_input.lower() for word in ["hey", "hola", "qué tal"]):
            self.context_memory["conversation_style"] = "casual"
        
        # Detectar preocupaciones específicas
        concern_indicators = ["preocupa", "duda", "no estoy seguro", "problema", "riesgo"]
        for indicator in concern_indicators:
            if indicator in user_input.lower():
                self.context_memory["mentioned_concerns"].append({
                    "concern": user_input,
                    "timestamp": datetime.now().isoformat()
                })
        
        # Mantener solo las últimas 10 preocupaciones
        if len(self.context_memory["mentioned_concerns"]) > 10:
            self.context_memory["mentioned_concerns"] = self.context_memory["mentioned_concerns"][-10:]
    
    def _execute_tool_calls(self, state: dict, tool_calls) -> dict:
        """Ejecuta las herramientas llamadas por el LLM - CORREGIDO PARA AUDIO"""
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            try:
                if function_name == "analyze_certificate":
                    if arguments.get("trigger_analysis") and state.get("certificate_images"):
                        cert_image = state["certificate_images"][0].to_pil_image()
                        business_info = self.certificate_analyzer.analyze_image(cert_image)
                        # Combinar con información existente
                        existing_info = state["business_info"]
                        for field, value in business_info.to_dict().items():
                            if value and not getattr(existing_info, field, None):
                                setattr(existing_info, field, value)
                        print(f"[DEBUG] Certificado analizado: {business_info.to_dict()}")
                
                elif function_name == "calculate_valuation":
                    if arguments.get("trigger_calculation"):
                        business_info = state["business_info"]
                        photos_count = len(state.get("local_photos", []))
                        
                        if business_info.metraje:
                            valuation = self.valuation_engine.estimate_property_value(
                                business_info, photos_count
                            )
                            state["valuation"] = valuation
                            print(f"[DEBUG] Valuación calculada: S/ {valuation.total:,.2f}")
                
                elif function_name == "generate_policy":
                    if arguments.get("trigger_generation"):
                        if state.get("valuation") and state["business_info"]:
                            policy = self.policy_generator.generate_policy(
                                state["business_info"],
                                state["valuation"]
                            )
                            state["policy"] = policy
                            print(f"[DEBUG] Póliza generada: Prima S/ {policy.premium_annual:,.2f}")
                
                elif function_name == "generate_audio_summary":
                    if arguments.get("trigger_audio"):
                        if state.get("policy"):
                            print("[DEBUG] Iniciando generación de audio...")
                            try:
                                audio_file, summary_text = self.policy_generator.generate_audio_summary(
                                    state["business_info"],
                                    state["valuation"],
                                    state["policy"]
                                )
                                
                                if audio_file:
                                    state["audio_file"] = audio_file
                                    state["audio_summary"] = summary_text
                                    print(f"[DEBUG] Audio generado exitosamente: {audio_file}")
                                    
                                    # NUEVO: Verificar que el archivo existe
                                    import os
                                    if os.path.exists(audio_file):
                                        print(f"[DEBUG] Archivo de audio confirmado en: {audio_file}")
                                    else:
                                        print(f"[DEBUG] WARNING: Archivo de audio no encontrado: {audio_file}")
                                        state["audio_file"] = None
                                else:
                                    print("[DEBUG] Error: No se pudo generar archivo de audio")
                                    state["audio_file"] = None
                                    state["audio_summary"] = "Error generando audio"
                                    
                            except Exception as audio_error:
                                print(f"[DEBUG] Error en generación de audio: {str(audio_error)}")
                                state["audio_file"] = None
                                state["audio_summary"] = f"Error: {str(audio_error)}"
                
                elif function_name == "update_context_memory":
                    # Actualizar memoria de contexto
                    if arguments.get("user_preferences"):
                        self.context_memory["user_preferences"].update(arguments["user_preferences"])
                    
                    if arguments.get("conversation_style"):
                        self.context_memory["conversation_style"] = arguments["conversation_style"]
                    
                    if arguments.get("business_context"):
                        self.context_memory["business_context"].update(arguments["business_context"])
                    
                    if arguments.get("concerns"):
                        self.context_memory["mentioned_concerns"].extend(arguments["concerns"])
                            
            except Exception as e:
                print(f"Error ejecutando herramienta {function_name}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        return state

    
    def _get_tool_result(self, state: dict, tool_call) -> str:
        """Obtiene el resultado de una herramienta ejecutada"""
        function_name = tool_call.function.name
        
        if function_name == "analyze_certificate":
            business_info = state.get("business_info", BusinessInfo())
            return f"Certificado analizado. Información extraída: {business_info.to_dict()}"
        
        elif function_name == "calculate_valuation":
            valuation = state.get("valuation")
            if valuation:
                return f"Valuación calculada exitosamente. Total: S/ {valuation.total:,.2f} (Inventario: S/ {valuation.inventario:,.2f}, Mobiliario: S/ {valuation.mobiliario:,.2f}, Infraestructura: S/ {valuation.infraestructura:,.2f}). Prima estimada: S/ {valuation.total * 0.025:,.2f} anual."
            else:
                return "No se pudo calcular la valuación. Verificar información del negocio."
        
        elif function_name == "generate_policy":
            policy = state.get("policy")
            if policy:
                return f"Póliza generada exitosamente. Prima anual: S/ {policy.premium_annual:,.2f}, Suma asegurada: S/ {policy.suma_asegurada:,.2f}"
            else:
                return "No se pudo generar la póliza."
        
        elif function_name == "generate_audio_summary":
            if state.get("audio_file"):
                return "Resumen en audio generado exitosamente y disponible para descarga."
            else:
                return "No se pudo generar el audio."
        
        elif function_name == "update_context_memory":
            return "Memoria de contexto actualizada con nueva información del usuario."
        
        return "Herramienta ejecutada."
    
    def process_certificate_image(self, state: dict, image) -> dict:
        """Procesa imagen de certificado"""
        from models import SerializableImage
        
        serializable_image = SerializableImage.from_pil_image(image, "certificado.jpg")
        state["certificate_images"] = [serializable_image]
        
        return state
    
    def process_local_photos(self, state: dict, photos: List) -> dict:
        """Procesa fotos del local"""
        from models import SerializableImage
        
        serializable_photos = []
        for i, photo in enumerate(photos):
            serializable_photo = SerializableImage.from_pil_image(photo, f"local_foto_{i+1}.jpg")
            serializable_photos.append(serializable_photo)
        
        current_photos = state.get("local_photos", [])
        current_photos.extend(serializable_photos)
        state["local_photos"] = current_photos
        
        return state
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen de la memoria de contexto para debugging"""
        return {
            "user_preferences": self.context_memory["user_preferences"],
            "conversation_style": self.context_memory["conversation_style"],
            "mentioned_concerns_count": len(self.context_memory["mentioned_concerns"]),
            "business_context": self.context_memory["business_context"],
            "interaction_history_count": len(self.context_memory["interaction_history"])
        }