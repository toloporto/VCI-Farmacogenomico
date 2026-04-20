import streamlit as st
import pandas as pd
import requests
import time
import io
from fpdf import FPDF

# 1. Función de comprobación de seguridad (Login Multi-usuario)
def check_password():
    """Comprueba si el usuario y contraseña existen en los secretos del servidor."""
    def password_entered():
        # Intentamos obtener los usuarios de los secretos
        try:
            usuarios_autorizados = st.secrets["usuarios"]
            user = st.session_state["username"]
            password = st.session_state["password"]

            if user in usuarios_autorizados and str(password) == str(usuarios_autorizados[user]):
                st.session_state["password_correct"] = True
                del st.session_state["password"]
                del st.session_state["username"]
            else:
                st.session_state["password_correct"] = False
        except Exception:
            st.error("Error técnico: No se han configurado los secretos 'usuarios' en el servidor.")
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔐 Acceso al Portal Clínico")
        st.write("Introduzca las credenciales de su centro de salud.")
        st.text_input("ID de Clínica / Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Portal Clínico")
        st.text_input("ID de Clínica / Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        st.error("😕 Credenciales no válidas para este centro.")
        return False
    else:
        return True

# 2. Aplicación Principal
if check_password():
    
    st.set_page_config(page_title="VCI Farmacogenómico", page_icon="💊", layout="wide")

    with st.sidebar:
        st.header("Panel de Control")
        # Mostramos un saludo genérico o podrías personalizarlo
        st.write("✅ Sesión Autorizada")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()

    st.title("💊 Plataforma de Farmacogenómica Clínica")
    st.write("Analice variantes genéticas para optimizar tratamientos y prevenir toxicidad farmacológica.")

    # --- FUNCIONES DEL MOTOR BIOINFORMÁTICO ---

    @st.cache_data
    def cargar_base_datos():
        try:
            return pd.read_csv("data/bd_farmacos.csv", index_col="ID_Variante")
        except Exception:
            st.error("Error: No se encuentra la carpeta 'data' o el archivo 'bd_farmacos.csv'.")
            return pd.DataFrame()

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

    def consultar_farmacogenomica(rs_id, df_bd):
        if not df_bd.empty and rs_id in df_bd.index:
            fila = df_bd.loc[rs_id]
            return {"farmaco": str(fila["Farmaco"]), "recomendacion": str(fila["Recomendacion"])}
        return {"farmaco": "Sin contraindicaciones", "recomendacion": "Dosis estandar segura."}

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
        st.info(f"✅ Archivo VCF procesado. {len(variantes_conocidas)} variantes detectadas.")
        
        if st.button("Ejecutar Análisis Clínico"):
            df_bd = cargar_base_datos()
            if not df_bd.empty:
                variantes_analisis = variantes_conocidas.head(5).copy()
                resultados_sig, lista_farmacos, lista_recom = [], [], []
                barra = st.progress(0)
                
                for i, (index, fila) in enumerate(variantes_analisis.iterrows()):
                    rsid = fila['ID']
                    resultados_sig.append(consultar_ensembl(rsid))
                    farma_info = consultar_farmacogenomica(rsid, df_bd)
                    lista_farmacos.append(farma_info['farmaco'])
                    lista_recom.append(farma_info['recomendacion'])
                    barra.progress((i + 1) / len(variantes_analisis))
                    time.sleep(0.2)
                
                variantes_analisis['Significado'] = resultados_sig
                variantes_analisis['Farmaco'] = lista_farmacos
                variantes_analisis['Recomendacion_Clinica'] = lista_recom
                
                st.success("Análisis completado.")
                st.dataframe(variantes_analisis[['ID', 'Farmaco', 'Recomendacion_Clinica']], width='stretch')
                
                pdf_out = generar_pdf_bytes(variantes_analisis)
                st.download_button(label="📥 Descargar Informe Clínico (PDF)", data=pdf_out, file_name="informe_vci.pdf", mime="application/pdf")