from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import uuid
from datetime import datetime
from PIL import Image

from models import GraphState, ConversationStep, BusinessInfo, SerializableImage
from conversation_nodes import ConversationNodes
from certificate_analyzer import CertificateAnalyzer
from valuation_engine import ValuationEngine
from policy_generator import PolicyGenerator
class InsuranceAgentGraph:
    """Grafo principal del agente de seguros usando LangGraph"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.nodes = ConversationNodes(api_key)
        self.memory = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Construye el grafo de estados de la conversación"""
        
        # Crear el grafo
        workflow = StateGraph(GraphState)
        
        # Agregar nodos
        workflow.add_node("welcome", self.nodes.welcome_node)
        workflow.add_node("analyze_input", self.nodes.analyze_input_node)
        workflow.add_node("certificate_analysis", self.nodes.certificate_analysis_node)
        workflow.add_node("valuation", self.nodes.valuation_node)
        workflow.add_node("policy_generation", self.nodes.policy_generation_node)
        workflow.add_node("audio_generation", self.nodes.audio_generation_node)
        workflow.add_node("sales_assistance", self.nodes.sales_assistance_node)
        
        # Definir punto de entrada
        workflow.set_entry_point("welcome")
        
        # Definir transiciones condicionales
        workflow.add_conditional_edges(
            "welcome",
            self._route_from_welcome,
            {
                "analyze_input": "analyze_input",
                "wait": END
            }
        )
        
        workflow.add_conditional_edges(
            "analyze_input",
            self._route_from_analyze_input,
            {
                "certificate_analysis": "certificate_analysis",
                "valuation": "valuation",
                "sales_assistance": "sales_assistance",
                "wait": END
            }
        )
        
        workflow.add_conditional_edges(
            "certificate_analysis",
            self._route_from_certificate_analysis,
            {
                "analyze_input": "analyze_input",
                "valuation": "valuation",
                "wait": END
            }
        )
        
        workflow.add_conditional_edges(
            "valuation",
            self._route_from_valuation,
            {
                "policy_generation": "policy_generation",
                "sales_assistance": "sales_assistance",
                "wait": END
            }
        )
        
        workflow.add_conditional_edges(
            "policy_generation",
            self._route_from_policy_generation,
            {
                "audio_generation": "audio_generation",
                "sales_assistance": "sales_assistance",
                "complete": END
            }
        )
        
        workflow.add_conditional_edges(
            "audio_generation",
            self._route_from_audio_generation,
            {
                "sales_assistance": "sales_assistance",
                "complete": END
            }
        )
        
        workflow.add_conditional_edges(
            "sales_assistance",
            self._route_from_sales_assistance,
            {
                "policy_generation": "policy_generation",
                "audio_generation": "audio_generation",
                "valuation": "valuation",
                "analyze_input": "analyze_input",
                "complete": END
            }
        )
        
        return workflow.compile(checkpointer=self.memory)
    
    def _route_from_welcome(self, state: GraphState) -> str:
        """Enrutamiento desde el nodo de bienvenida"""
        if state.get("user_input"):
            return "analyze_input"
        return "wait"
    
    def _route_from_analyze_input(self, state: GraphState) -> str:
        """Enrutamiento desde análisis de entrada - CORREGIDO PARA EVITAR CONFLICTOS"""
        next_action = state.get("next_action", "wait")
        
        print(f"[DEBUG] route_from_analyze_input - next_action: {next_action}")
        print(f"[DEBUG] current_step: {state.get('current_step')}")
        
        # Solo ejecutar si estamos en el paso correcto
        if state.get("current_step") == ConversationStep.GATHERING_INFO:
            
            if next_action == "certificate_analysis":
                return "certificate_analysis"
            elif next_action == "calculate_valuation":
                return "valuation" 
            elif next_action == "ready_for_valuation":
                # Verificar si hay confirmación para proceder
                user_input = str(state.get("user_input", "")).lower()
                confirmation_words = ["sí", "si", "ok", "correcto", "procede", "adelante", "calcular"]
                
                if any(word in user_input for word in confirmation_words):
                    print(f"[DEBUG] Confirmación para valuación -> valuation")
                    return "valuation"
                else:
                    print(f"[DEBUG] Esperando confirmación para valuación -> wait")
                    return "wait"
            elif next_action == "sales_assistance":
                return "sales_assistance"
            else:
                return "wait"
        
        # Si no estamos en GATHERING_INFO, no hacer nada
        else:
            print(f"[DEBUG] No en GATHERING_INFO, manteniendo estado -> wait")
            return "wait"
    def _route_from_certificate_analysis(self, state: GraphState) -> str:
        """Enrutamiento desde análisis de certificado"""
        if state.get("next_action") == "calculate_valuation":
            return "valuation"
        elif state.get("business_info") and state["business_info"].metraje:
            return "analyze_input"  # Para solicitar fotos
        else:
            return "wait"
    
    def _route_from_valuation(self, state: GraphState) -> str:
        """Enrutamiento desde valuación - CORREGIDO PARA EVITAR MÚLTIPLES EJECUCIONES"""
        user_input_raw = state.get("user_input", "")
        
        # Convertir user_input a string de forma segura
        try:
            if isinstance(user_input_raw, dict):
                user_input = str(user_input_raw.get('text', '') or user_input_raw.get('message', ''))
            else:
                user_input = str(user_input_raw)
            user_input = user_input.lower().strip()
        except:
            user_input = ""
        
        print(f"[DEBUG] route_from_valuation - user_input: '{user_input}'")
        print(f"[DEBUG] needs_confirmation: {state.get('needs_confirmation')}")
        print(f"[DEBUG] current_step: {state.get('current_step')}")
        
        # IMPORTANTE: Solo procesar confirmación si estamos específicamente esperando una
        if state.get("needs_confirmation") and state.get("current_step") == ConversationStep.VALUATION_COMPLETE:
            
            # Palabras que indican confirmación para generar póliza
            confirmation_words = ["sí", "si", "ok", "correcto", "generar", "acepto", "de acuerdo", "procede"]
            
            # Palabras que indican consultas/preguntas (NO confirmación)
            question_words = ["cobertura", "cubre", "incluye", "protege", "explica", "precio", "costo", 
                            "prima", "pago", "cuanto", "como", "que", "cuando", "donde", "porque", 
                            "dime", "muestra", "detalle", "información", "info"]
            
            is_question = any(word in user_input for word in question_words)
            is_confirmation = any(word in user_input for word in confirmation_words)
            
            # PRIMERO: Si es una pregunta, ir a sales_assistance
            if is_question and not is_confirmation:
                print(f"[DEBUG] Detectada consulta -> sales_assistance")
                return "sales_assistance"
            
            # SEGUNDO: Si es confirmación clara, ir a policy_generation
            elif is_confirmation and not is_question:
                print(f"[DEBUG] Confirmación detectada -> policy_generation")
                # IMPORTANTE: Limpiar el flag de confirmación para evitar bucles
                state["needs_confirmation"] = False
                return "policy_generation"
            
            # TERCERO: Si es ambiguo o vacío, mantener esperando
            else:
                print(f"[DEBUG] Input ambiguo o vacío -> wait")
                return "wait"
        
        # Si NO necesita confirmación, ir a sales_assistance por defecto
        else:
            print(f"[DEBUG] No necesita confirmación -> sales_assistance")
            return "sales_assistance"
    
    def _route_from_policy_generation(self, state: GraphState) -> str:
        """Enrutamiento desde generación de póliza - SIMPLIFICADO"""
        
        # Si se generó la póliza exitosamente
        if state.get("policy"):
            print(f"[DEBUG] Póliza generada -> sales_assistance")
            return "sales_assistance"
        else:
            # Si no se pudo generar, terminar
            print(f"[DEBUG] Error generando póliza -> complete")
            return "complete"
    def _route_from_audio_generation(self, state: GraphState) -> str:
        """Enrutamiento desde generación de audio - SIMPLIFICADO"""
        
        # Siempre ir a sales_assistance después de generar audio
        print(f"[DEBUG] Audio procesado -> sales_assistance")
        return "sales_assistance"
    
    def _route_from_sales_assistance(self, state: GraphState) -> str:
        """Enrutamiento desde asistencia de ventas - SIMPLIFICADO PARA EVITAR BUCLES"""
        
        user_input = state.get("user_input", "")
        if isinstance(user_input, dict):
            user_input = str(user_input.get('text', ''))
        user_input = str(user_input).lower()
        
        print(f"[DEBUG] route_from_sales_assistance - input: '{user_input}'")
        print(f"[DEBUG] has_policy: {bool(state.get('policy'))}")
        print(f"[DEBUG] has_valuation: {bool(state.get('valuation'))}")
        
        # REGLA SIMPLE: Si ya tienen póliza Y audio, siempre terminar
        if state.get("policy") and state.get("audio_file"):
            print(f"[DEBUG] Tiene póliza y audio -> complete")
            return "complete"
        
        # Si solicitan generar póliza Y no tienen póliza Y tienen valuación
        if any(word in user_input for word in ["poliza", "policy", "generar póliza"]):
            if not state.get("policy") and state.get("valuation"):
                print(f"[DEBUG] Solicitud de póliza -> policy_generation")
                return "policy_generation"
        
        # Si solicitan audio Y tienen póliza Y no tienen audio
        elif any(word in user_input for word in ["audio", "resumen audio", "generar audio"]):
            if state.get("policy") and not state.get("audio_file"):
                print(f"[DEBUG] Solicitud de audio -> audio_generation")
                return "audio_generation"
        
        # Para todo lo demás, terminar para evitar bucles infinitos
        print(f"[DEBUG] Caso general -> complete")
        return "complete"
    
    def create_initial_state(self, session_id: str = None) -> GraphState:
        """Crea el estado inicial del grafo"""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        return GraphState(
            messages=[],
            current_step=ConversationStep.WELCOME,
            user_input="",
            business_info=BusinessInfo(),
            valuation=None,
            certificate_text=None,
            certificate_images=[],
            local_photos=[],
            policy=None,
            audio_file=None,
            audio_summary=None,
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            next_action="welcome",
            needs_certificate=True,
            needs_photos=False,
            needs_confirmation=False,
            ready_for_policy=False
        )
    
    def process_user_input(self, state: GraphState, user_input) -> GraphState:
        """
        Procesa la entrada del usuario y ejecuta el grafo - CORREGIDO
        """
        # CORREGIDO: Limpiar y convertir user_input a string de forma más robusta
        try:
            if isinstance(user_input, dict):
                # Si es dict del chat input, extraer texto
                clean_input = str(user_input.get('text', '') or user_input.get('message', '') or user_input.get('content', ''))
            elif hasattr(user_input, 'text'):
                # Si es objeto con atributo text
                clean_input = str(user_input.text)
            elif hasattr(user_input, 'content'):
                # Si es objeto con atributo content
                clean_input = str(user_input.content)
            else:
                clean_input = str(user_input)
            
            # Limpiar espacios y caracteres especiales
            clean_input = clean_input.strip()
            
        except Exception as e:
            print(f"Error limpiando user_input: {str(e)}")
            clean_input = ""
        
        print(f"[DEBUG] process_user_input - Original: {type(user_input)}, Limpio: '{clean_input[:50]}...'")
        
        # Actualizar estado con la entrada limpia
        state["user_input"] = clean_input
        
        # NO agregar el mensaje aquí - ya se agregó en render_conversation()
        # Solo ejecutar el grafo
        
        # Ejecutar el grafo
        config = {"configurable": {"thread_id": state["session_id"]}}
        
        try:
            print(f"[DEBUG] Ejecutando grafo con input: '{clean_input[:30]}...'")
            result = self.graph.invoke(state, config)
            print(f"[DEBUG] Grafo ejecutado exitosamente")
            return result
        except Exception as e:
            print(f"Error ejecutando grafo: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # En caso de error, agregar mensaje de error y devolver estado
            state["messages"].append({
                "role": "assistant",
                "content": f"Disculpa, hubo un error procesando tu solicitud: {str(e)}. ¿Podrías intentar de nuevo?"
            })
            return state
    
    def process_certificate_document(self, state: GraphState, document_text: str) -> GraphState:
        """
        Procesa un documento de certificado
        
        Args:
            state: Estado actual
            document_text: Texto extraído del documento
        
        Returns:
            GraphState: Estado actualizado
        """
        state["certificate_text"] = document_text
        state["next_action"] = "certificate_analysis"
        
        config = {"configurable": {"thread_id": state["session_id"]}}
        
        try:
            result = self.graph.invoke(state, config)
            return result
        except Exception as e:
            print(f"Error procesando certificado: {str(e)}")
            state["messages"].append({
                "role": "assistant",
                "content": "Hubo un error analizando el certificado. ¿Podrías intentar con otra imagen o proporcionarme la información manualmente?"
            })
            return state
    
    def process_certificate_image(self, state: GraphState, image: Image.Image) -> GraphState:
        """
        Procesa una imagen de certificado (recibe PIL Image directamente)
        
        Args:
            state: Estado actual
            image: PIL Image del certificado
        
        Returns:
            GraphState: Estado actualizado
        """
        try:
            # Crear SerializableImage para guardar en el estado
            serializable_image = SerializableImage.from_pil_image(image, "certificado_funcionamiento.jpg")
            state["certificate_images"] = [serializable_image]
            state["next_action"] = "certificate_analysis"
            
            config = {"configurable": {"thread_id": state["session_id"]}}
            result = self.graph.invoke(state, config)
            return result
            
        except Exception as e:
            print(f"Error procesando imagen de certificado: {str(e)}")
            state["messages"].append({
                "role": "assistant",
                "content": "Hubo un error analizando la imagen del certificado. ¿Podrías intentar con una imagen más clara?"
            })
            return state
    
    def process_local_photos(self, state: GraphState, photos: list) -> GraphState:
        """
        Procesa fotos del local
        
        Args:
            state: Estado actual
            photos: Lista de fotos del local (PIL Images)
        
        Returns:
            GraphState: Estado actualizado
        """
        try:
            # Convertir PIL Images a SerializableImages
            serializable_photos = []
            for i, photo in enumerate(photos):
                serializable_photo = SerializableImage.from_pil_image(photo, f"local_foto_{i+1}.jpg")
                serializable_photos.append(serializable_photo)
            
            state["local_photos"] = serializable_photos
            
            # Si tenemos metraje, calcular valuación
            if state["business_info"].metraje:
                state["next_action"] = "calculate_valuation"
            else:
                state["user_input"] = f"He subido {len(photos)} fotos del local"
            
            config = {"configurable": {"thread_id": state["session_id"]}}
            
            try:
                result = self.graph.invoke(state, config)
                return result
            except Exception as e:
                print(f"Error procesando fotos: {str(e)}")
                state["messages"].append({
                    "role": "assistant",
                    "content": f"He recibido {len(photos)} fotos. Para continuar necesito que me confirmes el metraje de tu local."
                })
                return state
                
        except Exception as e:
            print(f"Error general procesando fotos: {str(e)}")
            state["messages"].append({
                "role": "assistant",
                "content": f"Hubo un error procesando las fotos. He recibido {len(photos)} imágenes pero necesito más información para continuar."
            })
            return state
    
    def get_conversation_summary(self, state: GraphState) -> Dict[str, Any]:
        """
        Obtiene un resumen del estado de la conversación
        
        Args:
            state: Estado actual
        
        Returns:
            Dict: Resumen de la conversación
        """
        return {
            "session_id": state["session_id"],
            "current_step": state["current_step"].value if state["current_step"] else "unknown",
            "business_info": state["business_info"].to_dict() if state["business_info"] else {},
            "valuation": state["valuation"].to_dict() if state.get("valuation") else None,
            "has_policy": bool(state.get("policy")),
            "has_audio": bool(state.get("audio_file")),
            "message_count": len(state["messages"]),
            "needs_certificate": state.get("needs_certificate", False),
            "needs_photos": state.get("needs_photos", False),
            "ready_for_policy": state.get("ready_for_policy", False)
        }
    

import openai
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from models import GraphState, BusinessInfo, Valuation, InsurancePolicy
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
                                "description": "Preferencias del usuario detectadas"
                            },
                            "conversation_style": {
                                "type": "string",
                                "description": "Estilo conversacional preferido: formal, casual, directo"
                            },
                            "business_context": {
                                "type": "object", 
                                "description": "Contexto adicional del negocio mencionado"
                            },
                            "concerns": {
                                "type": "array",
                                "description": "Preocupaciones o dudas específicas mencionadas"
                            }
                        }
                    }
                }
            }
        ]
    
    def process_conversation(self, state: GraphState, user_input: str) -> GraphState:
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
    
    def _update_interaction_history(self, user_input: str, state: GraphState):
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
    
    def _build_enhanced_context(self, state: GraphState) -> Dict[str, Any]:
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
        """Construye mensaje del sistema mejorado con memoria de contexto"""
        
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
    
    def _update_memory_from_interaction(self, user_input: str, assistant_response: str, state: GraphState):
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
    
    def _execute_tool_calls(self, state: GraphState, tool_calls) -> GraphState:
        """Ejecuta las herramientas llamadas por el LLM"""
        
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
                
                elif function_name == "calculate_valuation":
                    if arguments.get("trigger_calculation"):
                        business_info = state["business_info"]
                        photos_count = len(state.get("local_photos", []))
                        
                        if business_info.metraje:
                            valuation = self.valuation_engine.estimate_property_value(
                                business_info, photos_count
                            )
                            state["valuation"] = valuation
                
                elif function_name == "generate_policy":
                    if arguments.get("trigger_generation"):
                        if state.get("valuation") and state["business_info"]:
                            policy = self.policy_generator.generate_policy(
                                state["business_info"],
                                state["valuation"]
                            )
                            state["policy"] = policy
                
                elif function_name == "generate_audio_summary":
                    if arguments.get("trigger_audio"):
                        if state.get("policy"):
                            audio_file, summary_text = self.policy_generator.generate_audio_summary(
                                state["business_info"],
                                state["valuation"],
                                state["policy"]
                            )
                            if audio_file:
                                state["audio_file"] = audio_file
                                state["audio_summary"] = summary_text
                
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
        
        return state
    
    def _get_tool_result(self, state: GraphState, tool_call) -> str:
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
    
    def process_certificate_image(self, state: GraphState, image) -> GraphState:
        """Procesa imagen de certificado"""
        from models import SerializableImage
        
        serializable_image = SerializableImage.from_pil_image(image, "certificado.jpg")
        state["certificate_images"] = [serializable_image]
        
        return state
    
    def process_local_photos(self, state: GraphState, photos: List) -> GraphState:
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