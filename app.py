import streamlit as st
import pandas as pd
import requests
import time
import io
from fpdf import FPDF

# Configuración enfocada en producto clínico
st.set_page_config(page_title="VCI Farmacogenómico", page_icon="💊", layout="wide")

st.title("💊 Plataforma de Farmacogenómica Clínica")
st.write("Analiza variantes genéticas para predecir la respuesta a fármacos y prevenir toxicidad.")

def consultar_ensembl(rs_id):
    """Consulta de patogenicidad general"""
    servidor = "https://rest.ensembl.org"
    endpoint = f"/variation/human/{rs_id}?"
    try:
        respuesta = requests.get(servidor + endpoint, headers={"Content-Type": "application/json"})
        if not respuesta.ok: return "No encontrado"
        datos = respuesta.json()
        significado = datos.get('clinical_significance', [])
        return ", ".join(significado) if significado else "Desconocido"
    except:
        return "Error de conexión"

def consultar_farmacogenomica(rs_id):
    """
    Simulación de API comercial de farmacogenómica.
    (Emojis removidos para compatibilidad estricta con PDF)
    """
    bd_farmacos = {
        "rs6054257": {"farmaco": "Estatinas (Colesterol)", "recomendacion": "[RIESGO] Alta probabilidad de miopatia. Reducir dosis."},
        "rs6040355": {"farmaco": "Antidepresivos (ISRS)", "recomendacion": "[ATENCION] Metabolismo rapido. Posible ineficacia."},
        "rs1801280": {"farmaco": "Warfarina", "recomendacion": "[PELIGRO] Toxicidad severa. Evitar prescripcion."},
    }
    return bd_farmacos.get(rs_id, {"farmaco": "Sin contraindicaciones", "recomendacion": "Dosis estandar segura."})

def generar_pdf_bytes(df_resultados):
    """Genera un informe con un enfoque B2B para médicos"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", style="B", size=14)
    pdf.cell(w=0, h=10, text="Informe Farmacogenomico de Interacciones", align="C")
    pdf.ln(10)
    
    pdf.set_font("helvetica", style="B", size=9)
    pdf.cell(w=25, h=8, text="Variante (ID)", border=1)
    pdf.cell(w=45, h=8, text="Farmaco Afectado", border=1)
    pdf.cell(w=120, h=8, text="Recomendacion Clinica", border=1)
    pdf.ln()
    
    pdf.set_font("helvetica", size=9)
    for index, fila in df_resultados.iterrows():
        pdf.cell(w=25, h=8, text=str(fila['ID']), border=1)
        pdf.cell(w=45, h=8, text=str(fila['Farmaco'])[:30], border=1)
        pdf.cell(w=120, h=8, text=str(fila['Recomendacion_Clinica'])[:75], border=1)
        pdf.ln()
        
    return bytes(pdf.output())

# Interfaz principal
archivo_subido = st.file_uploader("Arrastra aquí el genoma del paciente (.vcf)", type=['vcf'])

if archivo_subido is not None:
    lineas = archivo_subido.getvalue().decode("utf-8").splitlines()
    lineas_saltar = sum(1 for linea in lineas if linea.startswith('##'))
    
    df = pd.read_csv(io.StringIO("\n".join(lineas)), sep='\t', skiprows=lineas_saltar)
    df.rename(columns={'#CHROM': 'CHROM'}, inplace=True)
    
    variantes_conocidas = df[df['ID'].str.startswith('rs', na=False)].copy()
    st.info(f"🧬 Genoma procesado correctamente. {len(variantes_conocidas)} marcadores viables detectados.")
    
    if st.button("Generar Perfil Farmacogenómico"):
        variantes_prueba = variantes_conocidas.head(5).copy()
        
        sig_clinico, farmacos, recomendaciones = [], [], []
        barra_progreso = st.progress(0)
        
        for i, (index, fila) in enumerate(variantes_prueba.iterrows()):
            rsid = fila['ID']
            sig_clinico.append(consultar_ensembl(rsid))
            
            datos_farma = consultar_farmacogenomica(rsid)
            farmacos.append(datos_farma['farmaco'])
            recomendaciones.append(datos_farma['recomendacion'])
            
            barra_progreso.progress((i + 1) / len(variantes_prueba))
            time.sleep(0.5)
            
        variantes_prueba['Significado'] = sig_clinico
        variantes_prueba['Farmaco'] = farmacos
        variantes_prueba['Recomendacion_Clinica'] = recomendaciones
        
        st.success("Análisis de interacciones completado.")
        
        # Corregido el warning de Streamlit: width='stretch'
        st.dataframe(variantes_prueba[['ID', 'Farmaco', 'Recomendacion_Clinica']], width='stretch')
        
        pdf_bytes = generar_pdf_bytes(variantes_prueba)
        st.download_button(
            label="📄 Descargar Informe Médico B2B",
            data=pdf_bytes,
            file_name="perfil_farmacogenomico.pdf",
            mime="application/pdf"
        )