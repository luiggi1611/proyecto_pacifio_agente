from typing import TypedDict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import base64
import io
from PIL import Image

class ConversationStep(Enum):
    WELCOME = "welcome"
    GATHERING_INFO = "gathering_info"
    ANALYZING_CERTIFICATE = "analyzing_certificate"
    ANALYZING_PHOTOS = "analyzing_photos"
    VALUATION_COMPLETE = "valuation_complete"
    POLICY_GENERATED = "policy_generated"
    AUDIO_GENERATED = "audio_generated"
    COMPLETE = "complete"

@dataclass
class SerializableImage:
    """Clase para manejar imágenes de forma serializable en el estado del grafo"""
    data: str  # Base64 string
    filename: str
    format: str = "JPEG"
    
    @classmethod
    def from_pil_image(cls, pil_image: Image.Image, filename: str) -> 'SerializableImage':
        """Crea SerializableImage desde PIL Image"""
        buffer = io.BytesIO()
        # Convertir a RGB si es necesario
        if pil_image.mode in ('RGBA', 'P'):
            pil_image = pil_image.convert('RGB')
        
        pil_image.save(buffer, format='JPEG', quality=90)
        img_data = base64.b64encode(buffer.getvalue()).decode()
        
        return cls(img_data, filename, "JPEG")
    
    def to_pil_image(self) -> Image.Image:
        """Convierte de vuelta a PIL Image"""
        img_data = base64.b64decode(self.data)
        return Image.open(io.BytesIO(img_data))
    
    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización"""
        return {
            "data": self.data,
            "filename": self.filename,
            "format": self.format
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SerializableImage':
        """Crea desde diccionario"""
        return cls(data["data"], data["filename"], data.get("format", "JPEG"))

@dataclass
class BusinessInfo:
    """Información del negocio extraída"""
    metraje: Optional[float] = None
    tipo_negocio: Optional[str] = None
    direccion: Optional[str] = None
    nombre_cliente: Optional[str] = None
    nombre_negocio: Optional[str] = None
    ruc: Optional[str] = None
    numero_certificado: Optional[str] = None
    fecha_expedicion: Optional[str] = None
    zonificacion: Optional[str] = None
    ocupantes_maximo: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BusinessInfo':
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

@dataclass
class Valuation:
    """Valuación del negocio"""
    inventario: float = 0
    mobiliario: float = 0
    infraestructura: float = 0
    total: float = 0
    descripcion: str = ""
    
    def to_dict(self) -> dict:
        return self.__dict__

@dataclass
class InsurancePolicy:
    """Póliza de seguro generada"""
    content: str = ""
    premium_annual: float = 0
    suma_asegurada: float = 0
    fecha_generacion: str = ""
    
    def to_dict(self) -> dict:
        return self.__dict__

class GraphState(TypedDict):
    """Estado del grafo de conversación"""
    # Conversación
    messages: List[dict]
    current_step: ConversationStep
    user_input: str
    
    # Información del negocio
    business_info: BusinessInfo
    valuation: Optional[Valuation]
    
    # Archivos subidos
    certificate_text: Optional[str]
    certificate_images: List[SerializableImage]
    local_photos: List[SerializableImage]
    
    # Productos generados
    policy: Optional[InsurancePolicy]
    audio_file: Optional[str]
    audio_summary: Optional[str]
    
    # Metadatos
    session_id: str
    timestamp: str
    next_action: str
    
    # Flags de control
    needs_certificate: bool
    needs_photos: bool
    needs_confirmation: bool
    ready_for_policy: bool