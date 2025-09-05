from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import uuid
from datetime import datetime
from PIL import Image

from models import GraphState, ConversationStep, BusinessInfo, SerializableImage
from conversation_nodes import ConversationNodes

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
        """Enrutamiento desde análisis de entrada"""
        next_action = state.get("next_action", "wait")
        
        if next_action == "certificate_analysis":
            return "certificate_analysis"
        elif next_action == "calculate_valuation":
            return "valuation"
        elif next_action == "sales_assistance":
            return "sales_assistance"
        else:
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
        """Enrutamiento desde valuación - CORREGIDO"""
        user_input = state.get("user_input", "").lower()
        
        # Palabras que indican confirmación
        confirmation_words = ["sí", "si", "ok", "correcto", "generar", "acepto", "de acuerdo", "procede"]
        
        # PRIMERO verificar si hay confirmación
        if user_input and any(word in user_input for word in confirmation_words):
            print(f"[DEBUG] Confirmación detectada en: '{user_input}' -> policy_generation")
            return "policy_generation"
        
        # Si necesita confirmación pero no la hay, esperar
        elif state.get("needs_confirmation"):
            print(f"[DEBUG] Esperando confirmación, user_input: '{user_input}' -> wait")
            return "wait"
        
        # En otros casos, ir a asistencia de ventas
        else:
            print(f"[DEBUG] Sin confirmación necesaria -> sales_assistance")
            return "sales_assistance"
    
    def _route_from_policy_generation(self, state: GraphState) -> str:
        """Enrutamiento desde generación de póliza - ARREGLADO"""
        
        # Si ya se generó la póliza, el trabajo está hecho
        if state.get("policy"):
            # Verificar si el usuario pidió audio
            user_input = state.get("user_input", "")
            if isinstance(user_input, dict):
                user_input = str(user_input.get('text', ''))
            user_input = str(user_input).lower()
            
            if any(word in user_input for word in ["audio", "resumen", "sí", "si"]):
                return "audio_generation"
            else:
                # Terminar aquí para evitar bucles
                return "complete"
        else:
            # Si no hay póliza, algo salió mal
            return "complete"
    def _route_from_audio_generation(self, state: GraphState) -> str:
        """Enrutamiento desde generación de audio - ARREGLADO"""
        
        # Si se generó el audio, terminar
        if state.get("audio_file"):
            return "complete"
        else:
            # Si no se pudo generar audio, ir a sales_assistance
            return "sales_assistance"
    
    def _route_from_sales_assistance(self, state: GraphState) -> str:
        """Enrutamiento desde asistencia de ventas - ARREGLADO"""
        
        user_input = state.get("user_input", "")
        if isinstance(user_input, dict):
            user_input = str(user_input.get('text', ''))
        user_input = str(user_input).lower()
        
        # Si solicitan generar póliza Y no tienen póliza
        if any(word in user_input for word in ["poliza", "policy", "generar", "documento"]):
            if not state.get("policy") and state.get("valuation"):
                return "policy_generation"
            else:
                return "complete"  # Ya tienen póliza
        
        # Si solicitan audio Y tienen póliza pero no audio
        elif any(word in user_input for word in ["audio", "resumen", "escuchar"]):
            if state.get("policy") and not state.get("audio_file"):
                return "audio_generation"
            else:
                return "complete"  # Ya tienen audio o no tienen póliza
        
        # Para cualquier otra consulta, mantenerse en sales_assistance
        # pero agregar contador para evitar bucles infinitos
        loop_count = state.get("sales_loop_count", 0)
        if loop_count > 3:
            return "complete"  # Terminar después de 3 iteraciones
        else:
            state["sales_loop_count"] = loop_count + 1
            return "complete"  # Terminar en lugar de hacer bucle
    
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
        Procesa la entrada del usuario y ejecuta el grafo
        """
        # NUEVO: Limpiar y convertir user_input a string
        try:
            if isinstance(user_input, dict):
                # Si es dict del chat input, extraer texto
                clean_input = str(user_input.get('text', '') or user_input.get('message', ''))
            else:
                clean_input = str(user_input)
            clean_input = clean_input.strip()
        except:
            clean_input = ""
        
        # Actualizar estado con la entrada limpia
        state["user_input"] = clean_input
        state["messages"].append({
            "role": "user",
            "content": clean_input
        })
        
        # Ejecutar el grafo
        config = {"configurable": {"thread_id": state["session_id"]}}
        
        try:
            result = self.graph.invoke(state, config)
            return result
        except Exception as e:
            print(f"Error ejecutando grafo: {str(e)}")
            # En caso de error, agregar mensaje de error y devolver estado
            state["messages"].append({
                "role": "assistant",
                "content": "Disculpa, hubo un error procesando tu solicitud. ¿Podrías intentar de nuevo?"
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