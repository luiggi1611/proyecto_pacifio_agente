import tempfile
from gtts import gTTS
from datetime import datetime
from typing import Optional, Tuple
from models import BusinessInfo, Valuation, InsurancePolicy
import os 
class PolicyGenerator:
    """Generador de pólizas de seguro y contenido de audio"""
    
    def __init__(self):
        self.company_name = "Seguros Pacífico"
        self.policy_version = "2024.1"
        import tempfile
        import os
        self.temp_dir = tempfile.mkdtemp(prefix="seguros_audio_")
    def generate_policy(self, business_info: BusinessInfo, valuation: Valuation) -> InsurancePolicy:
        """
        Genera la póliza de seguro completa
        
        Args:
            business_info: Información del negocio
            valuation: Valuación del negocio
        
        Returns:
            InsurancePolicy: Póliza generada
        """
        premium_annual = valuation.total * 5.6/1000  # 0.56% del valor asegurado
        
        # Generar contenido de la póliza
        policy_content = self._generate_policy_content(business_info, valuation, premium_annual)
        
        return InsurancePolicy(
            content=policy_content,
            premium_annual=premium_annual,
            suma_asegurada=valuation.total,
            fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M')
        )
    
    def _generate_policy_content(self, business_info: BusinessInfo, valuation: Valuation, premium_annual: float) -> str:
        """Genera el contenido detallado de la póliza"""
        
        policy_number = f"POL-{datetime.now().strftime('%Y%m%d')}-{business_info.ruc or '000000'}"
        
        return f"""
🏢 **PÓLIZA DE SEGURO COMERCIAL - {self.company_name}**
═══════════════════════════════════════════════════════════════

**INFORMACIÓN DE LA PÓLIZA**
• Número de Póliza: {policy_number}
• Fecha de Emisión: {datetime.now().strftime('%d/%m/%Y')}
• Vigencia: {datetime.now().strftime('%d/%m/%Y')} al {datetime.now().replace(year=datetime.now().year + 1).strftime('%d/%m/%Y')}
• Versión: {self.policy_version}

**DATOS DEL ASEGURADO**
• Razón Social/Nombre: {business_info.nombre_cliente or 'Por definir'}
• RUC: {business_info.ruc or 'Por definir'}
• Dirección del Riesgo: {business_info.direccion or 'Por definir'}
• Actividad Comercial: {business_info.tipo_negocio or 'Comercio general'}
• Área del Local: {business_info.metraje or 'N/A'} m²
• Zonificación: {business_info.zonificacion or 'Comercial'}

**RESUMEN DE COBERTURAS Y SUMAS ASEGURADAS**
┌─────────────────────────────────────────────────────────────┐
│ CONCEPTO                    │ SUMA ASEGURADA (S/)           │
├─────────────────────────────────────────────────────────────┤
│ Inventario/Mercancía        │ S/ {valuation.inventario:>15,.2f} │
│ Mobiliario y Equipos        │ S/ {valuation.mobiliario:>15,.2f} │
│ Mejoras e Instalaciones     │ S/ {valuation.infraestructura:>15,.2f} │
├─────────────────────────────────────────────────────────────┤
│ **SUMA ASEGURADA TOTAL**    │ **S/ {valuation.total:>13,.2f}** │
└─────────────────────────────────────────────────────────────┘

**RIESGOS CUBIERTOS**
✅ **Incendio y Explosión**
   • Daños causados por fuego, rayo, explosión
   • Gastos de extinción y salvamento

✅ **Robo y Hurto**
   • Sustracción violenta o clandestina
   • Daños por intento de robo

✅ **Daños por Agua**
   • Filtración, desborde, rotura de tuberías
   • Daños por lluvia e inundación

✅ **Fenómenos Naturales**
   • Terremoto, maremoto, huayco
   • Vientos huracanados

✅ **Responsabilidad Civil**
   • Daños a terceros hasta S/ 100,000
   • Gastos de defensa legal

✅ **Gastos Adicionales**
   • Gastos de reposición de documentos
   • Alquiler temporal de local alternativo

✅ **Lucro Cesante**
   • Pérdida de ingresos hasta 6 meses
   • Cobertura del 60% de ingresos promedio

**CONDICIONES ECONÓMICAS**
• Prima Anual: S/ {premium_annual:,.2f}
• Forma de Pago: Mensual (S/ {premium_annual/12:,.2f}) / Trimestral / Anual
• Deducible General: 10% del siniestro (mínimo S/ 500)
• Deducible Terremoto: 5% del siniestro (mínimo S/ 1,000)

**PRINCIPALES EXCLUSIONES**
❌ Daños por guerra, huelgas, conmoción civil
❌ Daños nucleares y contaminación
❌ Desgaste natural y deterioro gradual
❌ Negligencia grave del asegurado
❌ Actos dolosos del asegurado o empleados

**PROCEDIMIENTO EN CASO DE SINIESTRO**
1. 📞 **Aviso inmediato**: Llamar al 0-800-1-2345 (24/7)
2. 📧 **Email**: siniestros@segurospacifico.com.pe
3. 📄 **Documentos**: Denuncia policial (si aplica), fotos del daño
4. ⏰ **Plazo**: Máximo 3 días calendario desde ocurrido el siniestro

**BENEFICIOS ADICIONALES**
🔧 **Asesoría en Prevención**: Consultoría gratuita en seguridad
🚨 **Sistema de Alertas**: Notificaciones de riesgos meteorológicos
📱 **App Móvil**: Gestión digital de póliza y reportes
🎯 **Descuentos**: 5% por no siniestralidad anual

**CLÁUSULAS ESPECIALES**
• **Actualización Automática**: Suma asegurada se ajusta según inflación
• **Cobertura 24/7**: Válida todos los días del año
• **Extensión Territorial**: Cobertura en todo el territorio nacional
• **Gastos de Emergencia**: Hasta S/ 5,000 sin autorización previa

**DATOS DEL AGENTE**
• Agente: IA Seguros Pacífico
• Código: AGT-IA-001
• Email: agente.ia@segurospacifico.com.pe
• Teléfono: 01-234-5678

**INFORMACIÓN IMPORTANTE**
Esta póliza ha sido diseñada específicamente para su negocio basada en:
{valuation.descripcion}

La presente póliza está sujeta a las Condiciones Generales del Seguro 
Multiriesgo Comercial de {self.company_name}, las cuales forman parte 
integral de este contrato.

═══════════════════════════════════════════════════════════════
**{self.company_name}** - Tu tranquilidad, nuestro compromiso
www.segurospacifico.com.pe | Lima, Perú
═══════════════════════════════════════════════════════════════

*Documento generado automáticamente por el Agente IA*
*Fecha y hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}*
"""
    
    def generate_audio_summary(self, business_info: BusinessInfo, valuation: Valuation, policy: InsurancePolicy) -> Tuple[Optional[str], Optional[str]]:
        """
        Genera resumen en audio usando gTTS - CORREGIDO PARA PERSISTENCIA
        
        Args:
            business_info: Información del negocio
            valuation: Valuación del negocio
            policy: Póliza generada
        
        Returns:
            Tuple[str, str]: (ruta_archivo_audio, texto_resumen)
        """
        try:
            print("[DEBUG] Iniciando generación de audio...")
            
            # Generar texto del resumen
            summary_text = self._generate_audio_script(business_info, valuation, policy)
            print(f"[DEBUG] Script generado: {len(summary_text)} caracteres")
            
            # Crear archivo temporal persistente en nuestro directorio
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            audio_filename = f"resumen_poliza_{timestamp}.mp3"
            audio_path = os.path.join(self.temp_dir, audio_filename)
            
            print(f"[DEBUG] Generando archivo de audio en: {audio_path}")
            
            # Generar audio con gTTS
            tts = gTTS(text=summary_text, lang='es', slow=False)
            tts.save(audio_path)
            
            # Verificar que el archivo se creó correctamente
            if os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                print(f"[DEBUG] Audio generado exitosamente: {audio_path} ({file_size} bytes)")
                return audio_path, summary_text
            else:
                print("[DEBUG] ERROR: Archivo de audio no se creó")
                return None, None
                
        except Exception as e:
            print(f"[DEBUG] Error generando audio: {str(e)}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def _generate_audio_script(self, business_info: BusinessInfo, valuation: Valuation, policy: InsurancePolicy) -> str:
        """Genera el script para el audio - MEJORADO"""
        
        # Obtener información con valores por defecto seguros
        tipo_negocio = business_info.tipo_negocio or 'negocio comercial'
        direccion = business_info.direccion or 'la dirección registrada'
        metraje = business_info.metraje or 0
        
        # Formatear números de forma segura
        try:
            total_formatted = f"{valuation.total:,.0f}".replace(",", " ")
            inventario_formatted = f"{valuation.inventario:,.0f}".replace(",", " ")
            mobiliario_formatted = f"{valuation.mobiliario:,.0f}".replace(",", " ")
            infraestructura_formatted = f"{valuation.infraestructura:,.0f}".replace(",", " ")
            prima_formatted = f"{policy.premium_annual:,.0f}".replace(",", " ")
        except:
            # Fallback si hay error en formateo
            total_formatted = str(int(valuation.total))
            inventario_formatted = str(int(valuation.inventario))
            mobiliario_formatted = str(int(valuation.mobiliario))
            infraestructura_formatted = str(int(valuation.infraestructura))
            prima_formatted = str(int(policy.premium_annual))
        
        return f"""
¡Felicitaciones! Tu póliza de seguro comercial ha sido generada exitosamente.

Tu {tipo_negocio}, ubicado en {direccion}, con un área de {metraje} metros cuadrados, ahora está completamente protegido.

Hemos asegurado tu negocio por un valor total de {total_formatted} soles, distribuidos de la siguiente manera:

Inventario y mercancía por {inventario_formatted} soles.
Mobiliario y equipos por {mobiliario_formatted} soles.
Mejoras e instalaciones por {infraestructura_formatted} soles.

Tu póliza incluye cobertura completa contra incendio, robo, daños por agua, fenómenos naturales, y responsabilidad civil. También tienes protección por lucro cesante hasta por seis meses.

La prima anual de tu seguro es de {prima_formatted} soles, que puedes pagar de forma mensual, trimestral o anual, según tu conveniencia.

En caso de cualquier siniestro, puedes comunicarte las veinticuatro horas del día al cero ocho cero cero uno dos tres cuatro cinco, o enviar un correo a siniestros arroba seguros pacífico punto com punto pe.

Tu póliza está vigente desde hoy y por los próximos doce meses. 

¡Gracias por confiar en Seguros Pacífico para proteger tu negocio!
        """.strip()
    
    def cleanup_audio_files(self):
        """Limpia archivos de audio temporales antiguos"""
        try:
            import shutil
            import os
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                files = os.listdir(self.temp_dir)
                print(f"[DEBUG] Limpiando {len(files)} archivos de audio temporales")
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"[DEBUG] Error limpiando archivos temporales: {str(e)}")
    def generate_quote_summary(self, business_info: BusinessInfo, valuation: Valuation) -> str:
        """
        Genera un resumen de cotización antes de la póliza final
        
        Args:
            business_info: Información del negocio
            valuation: Valuación del negocio
        
        Returns:
            str: Resumen de cotización
        """
        premium_annual = valuation.total * 5.6/1000
        premium_monthly = premium_annual / 12
        
        return f"""
💰 **COTIZACIÓN DE SEGURO COMERCIAL**

**Tu Negocio:**
• {business_info.tipo_negocio or 'Negocio comercial'}
• {business_info.metraje or 0} m² 
• {business_info.direccion or 'Dirección por confirmar'}

**Valuación Estimada:**
• Inventario: S/ {valuation.inventario:,.2f}
• Mobiliario: S/ {valuation.mobiliario:,.2f}
• Infraestructura: S/ {valuation.infraestructura:,.2f}
• **Total: S/ {valuation.total:,.2f}**

**Costo del Seguro:**
• Prima Anual: S/ {premium_annual:,.2f}
• Prima Mensual: S/ {premium_monthly:,.2f}
• **Solo S/ {premium_monthly/30:,.0f} soles por día**

**Coberturas Principales:**
✅ Incendio y explosión
✅ Robo y hurto  
✅ Daños por agua
✅ Fenómenos naturales
✅ Responsabilidad civil
✅ Lucro cesante (6 meses)

¿Te parece correcta esta cotización? Si estás de acuerdo, procedo a generar tu póliza oficial.
"""