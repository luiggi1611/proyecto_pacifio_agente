from typing import Dict, List, Any
from models import BusinessInfo, Valuation

class ValuationEngine:
    """Motor de valuación para seguros comerciales - MEJORADO CON FOTOS OPCIONALES"""
    
    def __init__(self):
        # Factores base por m2 según tipo de negocio (en USD, luego convertidos a soles)
        self.factores = {
            "restaurante": {"inventario": 200, "mobiliario": 350, "infraestructura": 300},
            "tienda": {"inventario": 300, "mobiliario": 150, "infraestructura": 200},
            "oficina": {"inventario": 80, "mobiliario": 250, "infraestructura": 180},
            "farmacia": {"inventario": 500, "mobiliario": 300, "infraestructura": 250},
            "bar": {"inventario": 250, "mobiliario": 400, "infraestructura": 350},
            "panadería": {"inventario": 180, "mobiliario": 280, "infraestructura": 220},
            "taller": {"inventario": 150, "mobiliario": 200, "infraestructura": 250},
            "consultorio": {"inventario": 50, "mobiliario": 300, "infraestructura": 150},
            "salon": {"inventario": 100, "mobiliario": 400, "infraestructura": 200},
            "default": {"inventario": 200, "mobiliario": 250, "infraestructura": 200}
        }
        
        # Tasa de cambio USD a PEN
        self.tasa_cambio = 3.8
        
        # Multiplicadores por ubicación (Lima vs provincias)
        self.multiplicadores_ubicacion = {
            "lima": 1.2,
            "arequipa": 1.0,
            "trujillo": 0.9,
            "cusco": 0.8,
            "default": 0.85
        }
    
    def estimate_property_value(self, business_info: BusinessInfo, photos_count: int = 0) -> Valuation:
        """
        Estima valores basado en información del negocio y fotos (OPCIONALES)
        
        Args:
            business_info: Información del negocio
            photos_count: Número de fotos subidas (OPCIONAL - mejora la precisión)
        
        Returns:
            Valuation: Valuación estimada
        """
        if not business_info.metraje or business_info.metraje <= 0:
            return Valuation(descripcion="No se pudo calcular la valuación sin el metraje")
        
        if not business_info.tipo_negocio:
            return Valuation(descripcion="No se pudo calcular la valuación sin el tipo de negocio")
        
        # Buscar tipo más cercano
        factor_key = self._get_business_type_key(business_info.tipo_negocio)
        factor = self.factores[factor_key]
        
        # Obtener multiplicador por ubicación
        multiplicador_ubicacion = self._get_location_multiplier(business_info.direccion)
        
        # Multiplicador por cantidad de fotos (OPCIONAL - bonificación por precisión)
        # Sin fotos: valuación estándar (factor 1.0)
        # Con fotos: bonificación hasta 15% por mejor información
        if photos_count > 0:
            multiplicador_fotos = 1.0 + (photos_count * 0.03)  # 3% más por cada foto
            multiplicador_fotos = min(multiplicador_fotos, 1.15)  # Máximo 15% adicional
        else:
            multiplicador_fotos = 1.0  # Sin penalización por no tener fotos
        
        # Calcular valores base en soles peruanos
        inventario = (business_info.metraje * factor["inventario"] * 
                     self.tasa_cambio * multiplicador_ubicacion * multiplicador_fotos)
        
        mobiliario = (business_info.metraje * factor["mobiliario"] * 
                     self.tasa_cambio * multiplicador_ubicacion * multiplicador_fotos)
        
        infraestructura = (business_info.metraje * factor["infraestructura"] * 
                          self.tasa_cambio * multiplicador_ubicacion * multiplicador_fotos)
        
        total = inventario + mobiliario + infraestructura
        
        # Generar descripción
        descripcion = self._generate_description(
            business_info, factor_key, photos_count, multiplicador_ubicacion
        )
        
        return Valuation(
            inventario=round(inventario, 2),
            mobiliario=round(mobiliario, 2),
            infraestructura=round(infraestructura, 2),
            total=round(total, 2),
            descripcion=descripcion
        )
    
    def _get_business_type_key(self, tipo_negocio: str) -> str:
        """Encuentra la clave del tipo de negocio más cercana"""
        if not tipo_negocio:
            return "default"
        
        tipo_lower = tipo_negocio.lower()
        
        # Mapeo de palabras clave a tipos de negocio
        keyword_mapping = {
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
        
        for business_type, keywords in keyword_mapping.items():
            if any(keyword in tipo_lower for keyword in keywords):
                return business_type
        
        return "default"
    
    def _get_location_multiplier(self, direccion: str) -> float:
        """Obtiene el multiplicador por ubicación"""
        if not direccion:
            return self.multiplicadores_ubicacion["default"]
        
        direccion_lower = direccion.lower()
        
        if any(zona in direccion_lower for zona in ["lima", "miraflores", "san isidro", "surco", "la molina"]):
            return self.multiplicadores_ubicacion["lima"]
        elif "arequipa" in direccion_lower:
            return self.multiplicadores_ubicacion["arequipa"]
        elif "trujillo" in direccion_lower:
            return self.multiplicadores_ubicacion["trujillo"]
        elif "cusco" in direccion_lower:
            return self.multiplicadores_ubicacion["cusco"]
        else:
            return self.multiplicadores_ubicacion["default"]
    
    def _generate_description(self, business_info: BusinessInfo, factor_key: str, 
                            photos_count: int, multiplicador_ubicacion: float) -> str:
        """Genera descripción de la valuación - MEJORADA PARA FOTOS OPCIONALES"""
        ubicacion_desc = ""
        if multiplicador_ubicacion > 1.0:
            ubicacion_desc = " (zona premium)"
        elif multiplicador_ubicacion < 0.9:
            ubicacion_desc = " (zona económica)"
        
        # Descripción mejorada de fotos
        fotos_desc = ""
        if photos_count > 3:
            fotos_desc = f" Análisis detallado con {photos_count} fotos del local."
        elif photos_count > 0:
            fotos_desc = f" Valuación mejorada con {photos_count} fotos del local."
        else:
            fotos_desc = " Valuación estándar basada en datos del negocio."
        
        return (f"Estimación para {business_info.tipo_negocio or 'negocio comercial'} "
                f"de {business_info.metraje}m²{ubicacion_desc}.{fotos_desc}")
    
    def calculate_premium(self, total_value: float, business_type: str = "") -> float:
        """
        Calcula la prima anual del seguro
        
        Args:
            total_value: Valor total asegurado
            business_type: Tipo de negocio para ajustar la prima
        
        Returns:
            float: Prima anual estimada
        """
        # Tasas base por tipo de negocio (% del valor asegurado)
        tasas_riesgo = {
            "restaurante": 0.0056,  # 0.56% - riesgo alto (fuego, cocina)
            "bar": 0.0056,          # 0.56% - riesgo muy alto (alcohol, peleas)
            "farmacia": 0.0056,     # 0.56% - riesgo bajo (medicinas valiosas pero seguras)
            "oficina": 0.0056,      # 0.56% - riesgo muy bajo
            "consultorio": 0.0056,  # 0.56% - riesgo bajo
            "tienda": 0.0056,       # 0.56% - riesgo medio
            "taller": 0.0056,       # 0.56% - riesgo alto (maquinaria)
            "default": 0.0056       # 0.56% - riesgo medio por defecto
        }
        
        business_key = self._get_business_type_key(business_type)
        tasa = tasas_riesgo.get(business_key, tasas_riesgo["default"])
        
        return round(total_value * tasa, 2)