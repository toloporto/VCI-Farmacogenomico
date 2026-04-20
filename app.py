import streamlit as st
import pandas as pd
import requests
import time
import io
from fpdf import FPDF

# 1. Función de comprobación de seguridad (Login)
def check_password():
    """Devuelve True si el usuario introdujo las credenciales correctas."""
    def password_entered():
        """Comprueba si las credenciales coinciden."""
        if st.session_state["username"] == "admin" and st.session_state["password"] == "medico2026":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Seguridad: eliminar contraseña del estado
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # Pantalla inicial de Login
        st.title("🔐 Acceso al Portal Clínico")
        st.text_input("Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Intento fallido
        st.title("🔐 Acceso al Portal Clínico")
        st.text_input("Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        st.error("😕 Usuario o contraseña incorrectos")
        return False
    else:
        # Acceso concedido
        return True

# 2. Aplicación Principal (Solo se ejecuta tras el Login)
if check_password():
    
    # Configuración de página
    st.set_page_config(page_title="VCI Farmacogenómico", page_icon="💊", layout="wide")

    # Barra lateral de usuario
    with st.sidebar:
        st.header("Panel de Control")
        st.write(f"Usuario: **Especialista Clínico**")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()

    st.title("💊 Plataforma de Farmacogenómica Clínica")
    st.write("Analice variantes genéticas para optimizar tratamientos y prevenir toxicidad farmacológica.")

    # --- FUNCIONES DEL MOTOR BIOINFORMÁTICO ---

    def consultar_ensembl(rs_id):
        servidor = "https://rest.ensembl.org"
        endpoint = f"/variation/human/{rs_id}?"
        try:
            respuesta = requests.get(servidor + endpoint, headers={"Content-Type": "application/json"})
            if not respuesta.ok: return "No encontrado"
            datos = respuesta.json()
            significado = datos.get('clinical_significance', [])
            return ", ".join(significado) if significado else "Desconocido"
        except: return "Error de conexión"

    def consultar_farmacogenomica(rs_id):
        # Base de datos simulada para el MVP
        bd_farmacos = {
            "rs6054257": {"farmaco": "Estatinas (Colesterol)", "recomendacion": "[RIESGO] Alta probabilidad de miopatia. Reducir dosis."},
            "rs6040355": {"farmaco": "Antidepresivos (ISRS)", "recomendacion": "[ATENCION] Metabolismo rapido. Posible ineficacia."},
            "rs1801280": {"farmaco": "Warfarina", "recomendacion": "[PELIGRO] Toxicidad severa. Evitar prescripcion."},
        }
        return bd_farmacos.get(rs_id, {"farmaco": "Sin contraindicaciones", "recomendacion": "Dosis estandar segura."})

    def generar_pdf_bytes(df_resultados):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", style="B", size=14)
        pdf.cell(w=0, h=10, text="Informe Farmacogenomico de Interacciones", align="C")
        pdf.ln(10)
        pdf.set_font("helvetica", style="B", size=9)
        pdf.cell(w=25, h=8, text="Variante (ID)", border=1)
        pdf.cell(w=45, h=8, text="Farmaco Afectado", border=1)
        pdf.cell(w=115, h=8, text="Recomendacion Clinica", border=1)
        pdf.ln()
        pdf.set_font("helvetica", size=9)
        for index, fila in df_resultados.iterrows():
            pdf.cell(w=25, h=8, text=str(fila['ID']), border=1)
            pdf.cell(w=45, h=8, text=str(fila['Farmaco'])[:30], border=1)
            pdf.cell(w=115, h=8, text=str(fila['Recomendacion_Clinica'])[:70], border=1)
            pdf.ln()
        return bytes(pdf.output())

    # --- INTERFAZ DE CARGA Y ANÁLISIS ---
    archivo_subido = st.file_uploader("Subir genoma del paciente (.vcf)", type=['vcf'])

    if archivo_subido is not None:
        lineas = archivo_subido.getvalue().decode("utf-8").splitlines()
        lineas_saltar = sum(1 for linea in lineas if linea.startswith('##'))
        df = pd.read_csv(io.StringIO("\n".join(lineas)), sep='\t', skiprows=lineas_saltar)
        df.rename(columns={'#CHROM': 'CHROM'}, inplace=True)
        variantes_conocidas = df[df['ID'].str.startswith('rs', na=False)].copy()
        st.info(f"✅ Archivo VCF procesado. Se han detectado {len(variantes_conocidas)} variantes con ID.")
        
        if st.button("Ejecutar Análisis Clínico"):
            variantes_analisis = variantes_conocidas.head(5).copy()
            resultados_sig, lista_farmacos, lista_recom = [], [], []
            
            barra = st.progress(0)
            status = st.empty()
            
            for i, (index, fila) in enumerate(variantes_analisis.iterrows()):
                rsid = fila['ID']
                status.text(f"Analizando marcador {rsid}...")
                
                resultados_sig.append(consultar_ensembl(rsid))
                farma_info = consultar_farmacogenomica(rsid)
                lista_farmacos.append(farma_info['farmaco'])
                lista_recom.append(farma_info['recomendacion'])
                
                barra.progress((i + 1) / len(variantes_analisis))
                time.sleep(0.4)
            
            variantes_analisis['Significado'] = resultados_sig
            variantes_analisis['Farmaco'] = lista_farmacos
            variantes_analisis['Recomendacion_Clinica'] = lista_recom
            
            status.success("Análisis completado satisfactoriamente.")
            st.dataframe(variantes_analisis[['ID', 'Farmaco', 'Recomendacion_Clinica']], width='stretch')
            
            # Generación de descarga
            pdf_out = generar_pdf_bytes(variantes_analisis)
            st.download_button(
                label="📥 Descargar Informe Clínico (PDF)",
                data=pdf_out,
                file_name="informe_farmacogenomico.pdf",
                mime="application/pdf"
            )
