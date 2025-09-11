"""
llm_controlled_agent.py - MODIFICADO PARA COTIZACIÓN AUTOMÁTICA
Agente de seguros que cotiza automáticamente con el certificado
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
    """Agente de seguros que cotiza automáticamente al subir certificado"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.certificate_analyzer = CertificateAnalyzer(api_key)
        self.valuation_engine = ValuationEngine()
        self.policy_generator = PolicyGenerator()
        
        # Estado interno para controlar el flujo
        self.awaiting_policy_confirmation = False
        
        # Memoria de contexto simplificada
        self.context_memory = {
            "user_preferences": {},
            "conversation_style": "formal",
            "mentioned_concerns": [],
            "business_context": {},
            "interaction_history": []
        }
        
        # Herramientas actualizadas
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "process_certificate_and_quote",
                    "description": "Procesa automáticamente el certificado y genera cotización completa",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trigger_processing": {
                                "type": "boolean",
                                "description": "True para procesar certificado y generar cotización automáticamente"
                            }
                        },
                        "required": ["trigger_processing"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_business_info",
                    "description": "Actualiza información del negocio cuando el usuario proporciona datos adicionales",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metraje": {"type": "number", "description": "Área del local en metros cuadrados"},
                            "tipo_negocio": {"type": "string", "description": "Tipo o giro del negocio"},
                            "direccion": {"type": "string", "description": "Dirección del local comercial"},
                            "nombre_cliente": {"type": "string", "description": "Nombre del propietario/cliente"},
                            "nombre_negocio": {"type": "string", "description": "Nombre comercial del negocio"},
                            "ruc": {"type": "string", "description": "RUC del negocio"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "show_policy_confirmation",
                    "description": "Muestra botones de confirmación para generar la póliza",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "show_buttons": {
                                "type": "boolean",
                                "description": "True para mostrar botones Sí/No"
                            }
                        },
                        "required": ["show_buttons"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_policy_and_audio",
                    "description": "Genera la póliza oficial y el audio",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "generate_policy": {"type": "boolean", "description": "True para generar póliza"},
                            "generate_audio": {"type": "boolean", "description": "True para generar audio"}
                        },
                        "required": ["generate_policy"]
                    }
                }
            }
        ]
    
    def process_conversation(self, state: dict, user_input: str) -> dict:
        """Procesa la conversación con flujo automático mejorado"""
        
        # Verificar si el usuario confirmó generar póliza
        if self.awaiting_policy_confirmation:
            if user_input.lower().strip() in ['sí', 'si', 'yes', 'y', 'confirmo', 'ok', 'generar']:
                # Usuario confirmó - generar póliza y audio automáticamente
                state = self._generate_policy_and_audio_directly(state)
                self.awaiting_policy_confirmation = False
                return state
            elif user_input.lower().strip() in ['no', 'n', 'cancelar', 'después']:
                state["messages"].append({
                    "role": "assistant",
                    "content": "Entendido. Tu cotización queda guardada. Puedes pedirme generar la póliza cuando estés listo."
                })
                self.awaiting_policy_confirmation = False
                return state
        
        # Agregar mensaje del usuario
        state["messages"].append({
            "role": "user",
            "content": user_input
        })
        
        # Construir contexto para LLM
        context = self._build_context(state)
        system_message = self._build_system_message(context)
        
        # Preparar mensajes
        messages = [{"role": "system", "content": system_message}]
        messages.extend(state["messages"][-6:])  # Últimos 6 mensajes
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1200
            )
            
            assistant_message = response.choices[0].message
            
            # Ejecutar herramientas si es necesario
            if assistant_message.tool_calls:
                state = self._execute_tool_calls(state, assistant_message.tool_calls)
                
                # Segunda llamada para respuesta final
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": assistant_message.tool_calls
                })
                
                for tool_call in assistant_message.tool_calls:
                    tool_result = self._get_tool_result(state, tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
                
                final_response = self.client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=messages,
                    temperature=0.1,
                    max_tokens=800
                )
                
                final_content = final_response.choices[0].message.content
            else:
                final_content = assistant_message.content
            
            # Agregar respuesta del asistente
            state["messages"].append({
                "role": "assistant", 
                "content": final_content
            })
            
        except Exception as e:
            print(f"Error en conversación LLM: {str(e)}")
            state["messages"].append({
                "role": "assistant",
                "content": "Disculpa, hubo un error procesando tu solicitud. ¿Podrías intentar de nuevo?"
            })
        
        return state
    
    def _execute_tool_calls(self, state: dict, tool_calls) -> dict:
        """Ejecuta las herramientas llamadas por el LLM"""
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            try:
                if function_name == "process_certificate_and_quote":
                    if arguments.get("trigger_processing") and state.get("certificate_images"):
                        # Analizar certificado
                        cert_image = state["certificate_images"][0].to_pil_image()
                        business_info = self.certificate_analyzer.analyze_image(cert_image)
                        
                        # Actualizar información existente
                        existing_info = state["business_info"]
                        for field, value in business_info.to_dict().items():
                            if value and not getattr(existing_info, field, None):
                                setattr(existing_info, field, value)
                        
                        # Calcular cotización automáticamente si tenemos datos mínimos
                        if existing_info.tipo_negocio and existing_info.metraje:
                            valuation = self.valuation_engine.estimate_property_value(
                                existing_info, 0  # Sin fotos del local por ahora
                            )
                            state["valuation"] = valuation
                            state["ready_for_policy"] = True
                            print(f"[DEBUG] Cotización automática generada: S/ {valuation.total:,.2f}")
                
                elif function_name == "update_business_info":
                    existing_info = state["business_info"]
                    for field, value in arguments.items():
                        if value is not None and value != "":
                            if field == "metraje":
                                existing_info.metraje = float(value)
                            else:
                                setattr(existing_info, field, str(value))
                
                elif function_name == "show_policy_confirmation":
                    if arguments.get("show_buttons"):
                        self.awaiting_policy_confirmation = True
                        state["show_policy_buttons"] = True
                
                elif function_name == "generate_policy_and_audio":
                    if arguments.get("generate_policy"):
                        state = self._generate_policy_and_audio_directly(state)
                        
            except Exception as e:
                print(f"Error ejecutando herramienta {function_name}: {str(e)}")
        
        return state
    
    def _generate_policy_and_audio_directly(self, state: dict) -> dict:
        """Genera póliza y audio directamente"""
        try:
            if state.get("valuation") and state["business_info"]:
                # Generar póliza
                policy = self.policy_generator.generate_policy(
                    state["business_info"],
                    state["valuation"]
                )
                state["policy"] = policy
                
                # Generar audio
                audio_file, summary_text = self.policy_generator.generate_audio_summary(
                    state["business_info"],
                    state["valuation"],
                    policy
                )
                
                if audio_file:
                    state["audio_file"] = audio_file
                    state["audio_summary"] = summary_text
                
                # Marcar como completado
                state["policy_generated"] = True
                state["show_download_buttons"] = True
                
                print(f"[DEBUG] Póliza y audio generados exitosamente")
                
        except Exception as e:
            print(f"[DEBUG] Error generando póliza y audio: {str(e)}")
        
        return state
    
    def _get_tool_result(self, state: dict, tool_call) -> str:
        """Obtiene el resultado de una herramienta ejecutada"""
        function_name = tool_call.function.name
        
        if function_name == "process_certificate_and_quote":
            business_info = state.get("business_info", BusinessInfo())
            valuation = state.get("valuation")
            
            if valuation:
                return f"""Certificado procesado y cotización generada exitosamente.
                
Información extraída:
- Negocio: {business_info.tipo_negocio}
- Área: {business_info.metraje} m²
- Dirección: {business_info.direccion}

Cotización:
- Valor total asegurado: S/ {valuation.total:,.2f}
- Prima anual: S/ {valuation.total * 5.6/1000:,.2f}
- Prima mensual: S/ {(valuation.total * 5.6/1000)/12:,.2f}

Lista para generar póliza oficial."""
            else:
                return "Certificado procesado pero falta información para cotizar."
        
        elif function_name == "update_business_info":
            return "Información del negocio actualizada."
        
        elif function_name == "show_policy_confirmation":
            return "Mostrando botones de confirmación para generar póliza."
        
        elif function_name == "generate_policy_and_audio":
            if state.get("policy_generated"):
                return "Póliza y audio generados exitosamente. Disponibles para descarga."
            else:
                return "Error generando póliza y audio."
        
        return "Herramienta ejecutada."
    
    def _build_system_message(self, context: Dict[str, Any]) -> str:
        """Construye mensaje del sistema actualizado"""
        
        business_info_str = json.dumps(context['business_info'], indent=2)
        
        return f"""Eres un agente de seguros comerciales de Seguros Pacífico con flujo automatizado.

CONTEXTO ACTUAL:
- Información del negocio: {business_info_str}
- ¿Tiene certificado?: {context['has_certificate']}
- ¿Tiene cotización?: {context['has_valuation']}
- ¿Tiene póliza?: {context['has_policy']}
- ¿Esperando confirmación?: {self.awaiting_policy_confirmation}

FLUJO AUTOMATIZADO:
1. **Cuando se suba CERTIFICADO** → Usar process_certificate_and_quote INMEDIATAMENTE
2. **Cuando tengas COTIZACIÓN completa** → Preguntar "¿Te gustaría que genere tu póliza oficial?" + usar show_policy_confirmation
3. **Cuando usuario confirme "Sí"** → Usar generate_policy_and_audio para crear documentos

REGLAS CRÍTICAS:
- Al detectar certificado subido → llamar process_certificate_and_quote automáticamente
- NO pedir información adicional si ya tienes tipo_negocio + metraje del certificado  
- Después de generar cotización → SIEMPRE preguntar sobre póliza Y usar show_policy_confirmation
- SIEMPRE usar show_policy_confirmation cuando preguntes sobre generar póliza
- SÉ PROACTIVO: procesa y cotiza automáticamente

MENSAJES REQUERIDOS:
- Tras analizar certificado: "He analizado tu certificado y generado tu cotización personalizada..."
- Tras cotizar: "¿Te gustaría que genere tu póliza oficial?" + USAR show_policy_confirmation
- Tras generar póliza: "¡Perfecto! Tu póliza y resumen en audio están listos para descargar."

IMPORTANTE: Cuando preguntes sobre generar la póliza, SIEMPRE usar la herramienta show_policy_confirmation para activar los botones en la interfaz."""
    
    def _build_context(self, state: dict) -> Dict[str, Any]:
        """Construye el contexto actual del estado"""
        return {
            "business_info": state.get("business_info", BusinessInfo()).to_dict(),
            "has_certificate": bool(state.get("certificate_images")),
            "has_valuation": bool(state.get("valuation")),
            "has_policy": bool(state.get("policy")),
            "ready_for_policy": state.get("ready_for_policy", False)
        }
    
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
        """Obtiene un resumen de la memoria de contexto"""
        return {
            "user_preferences": self.context_memory["user_preferences"],
            "conversation_style": self.context_memory["conversation_style"],
            "mentioned_concerns_count": len(self.context_memory["mentioned_concerns"]),
            "business_context": self.context_memory["business_context"],
            "interaction_history_count": len(self.context_memory["interaction_history"])
        }   