import streamlit as st
import pandas as pd
import requests
import time
import io
import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import plotly.express as px

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
st.set_page_config(page_title="VCI Farmacogenómica Pro", layout="wide")

def check_password():
    if st.session_state.get("password_correct", False):
        return True
    st.title("🔐 Acceso al Portal Clínico")
    user = st.text_input("ID de Clínica / Usuario", key="login_user")
    password = st.text_input("Contraseña", type="password", key="login_pass")
    if st.button("Entrar"):
        if user in st.secrets["usuarios"] and password == st.secrets["usuarios"][user]:
            st.session_state["password_correct"] = True
            st.session_state["username_logged"] = user
            st.rerun()
        else:
            st.error("❌ Credenciales incorrectas")
    return False

# --- 2. FUNCIONES DE APOYO ---
def cargar_base_datos():
    try: return pd.read_csv('data/bd_farmacos.csv')
    except: return pd.DataFrame(columns=['ID_Variante', 'Farmaco', 'Recomendacion'])

def consultar_farma(rsid, df_bd):
    match = df_bd[df_bd['ID_Variante'] == rsid]
    if not match.empty:
        reco = match.iloc[0]['Recomendacion']
        nivel = 'Peligro' if '[PELIGRO]' in reco else 'Riesgo' if '[RIESGO]' in reco else 'Atención' if '[ATENCION]' in reco else 'Seguro'
        return {'farmaco': match.iloc[0]['Farmaco'], 'reco': reco, 'nivel': nivel}
    return {'farmaco': 'N/A', 'reco': 'Dosis estándar segura', 'nivel': 'Seguro'}

def procesar_vcf_limpio(archivo_subido):
    try:
        contenido = archivo_subido.getvalue().decode("utf-8").splitlines()
        linea_header = next((i for i, l in enumerate(contenido) if l.startswith("#CHROM")), -1)
        if linea_header == -1: return None
        df = pd.read_csv(io.StringIO("\n".join(contenido[linea_header:])), sep=None, engine='python')
        df.columns = df.columns.str.replace('#', '')
        df_rs = df[df['ID'].str.contains('rs', na=False)].copy()
        df_rs['ID'] = df_rs['ID'].str.strip()
        return df_rs
    except: return None

def guardar_analisis_pro(id_paciente, df_resultados, clinica):
    if not os.path.exists("data/analisis"): os.makedirs("data/analisis")
    path_file = f"data/analisis/{time.strftime('%Y%m%d_%H%M')}_{id_paciente}.csv"
    df_resultados.to_csv(path_file, index=False)
    nuevo = pd.DataFrame([{
        "Fecha": time.strftime("%Y-%m-%d %H:%M"),
        "Paciente": id_paciente,
        "Riesgo_Max": df_resultados['Nivel'].iloc[0] if 'Nivel' in df_resultados.columns else "Seguro",
        "Archivo_Full": path_file
    }])
    hist_path = "data/historial_detallado.csv"
    if os.path.exists(hist_path): pd.concat([pd.read_csv(hist_path), nuevo]).to_csv(hist_path, index=False)
    else: nuevo.to_csv(hist_path, index=False)

# --- 3. EXPORTACIÓN PDF (Sintaxis 2026) ---
def generar_reporte_pdf(id_paciente, df, clinica):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(31, 119, 180)
    pdf.cell(0, 10, "VCI FARMACOGENÓMICA PRO", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(100)
    pdf.cell(0, 5, f"Clínica: {clinica} | Fecha: {time.strftime('%d/%m/%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)
    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(0)
    pdf.cell(0, 10, f" PACIENTE: {id_paciente}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.ln(5)
    for _, r in df.iterrows():
        if r['Nivel'] == 'Peligro': pdf.set_fill_color(255, 200, 200)
        elif r['Nivel'] == 'Riesgo': pdf.set_fill_color(255, 230, 180)
        else: pdf.set_fill_color(255, 255, 255)
        top = pdf.get_y()
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(40, 10, f" {r['ID']}", 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=True)
        pdf.cell(50, 10, f" {r['Farmaco']}", 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=True)
        pdf.set_font("helvetica", "", 9)
        pdf.multi_cell(100, 5, f" {r['Recomendacion']}", 1, 'L', True)
        pdf.set_y(max(pdf.get_y(), top + 10))
    return bytes(pdf.output())

# --- 4. INTERFAZ Y ESTADOS ---
if check_password():
    # Inicialización de estados
    if 'df_activo' not in st.session_state: st.session_state.df_activo = None
    if 'id_activo' not in st.session_state: st.session_state.id_activo = None
    if 'source' not in st.session_state: st.session_state.source = None

    with st.sidebar:
        st.header("📂 Gestión de Pacientes")
        if os.path.exists("data/historial_detallado.csv"):
            h = pd.read_csv("data/historial_detallado.csv")
            busqueda = st.text_input("🔍 Buscar Paciente")
            if busqueda: h = h[h['Paciente'].str.contains(busqueda, case=False, na=False)]
            
            st.write("---")
            lista_opciones = ["-- Seleccionar --"] + [f"{r['Paciente']} ({r['Fecha']})" for _, r in h.iterrows()]
            seleccion = st.selectbox("Recuperar registro:", lista_opciones)
            
            if seleccion != "-- Seleccionar --":
                idx = lista_opciones.index(seleccion) - 1
                row = h.iloc[idx]
                st.session_state.df_activo = pd.read_csv(row['Archivo_Full'])
                st.session_state.id_activo = row['Paciente']
                st.session_state.source = 'historial'
            
            st.write("---")
            if st.button("✨ Limpiar Pantalla"):
                st.session_state.df_activo = None
                st.session_state.id_activo = None
                st.session_state.source = None
                if "uploader" in st.session_state:
                    del st.session_state["uploader"]
                st.rerun()
            if st.button("🗑️ Borrar Historial"):
                if os.path.exists("data/historial_detallado.csv"): os.remove("data/historial_detallado.csv")
                st.rerun()
        else:
            st.info("Historial vacío.")

    st.title("🧬 VCI Farmacogenómica Pro")
    
    # MOSTRAR CARGADOR SOLO SI NO HAY DATOS
    if st.session_state.df_activo is None:
        archivo = st.file_uploader("Cargar genoma (.vcf)", type=['vcf', 'txt'], key="uploader")
        if archivo:
            v_raw = procesar_vcf_limpio(archivo)
            if v_raw is not None:
                st.session_state.df_activo = v_raw.head(20)
                st.session_state.id_activo = archivo.name.split('.')[0]
                st.session_state.source = 'upload'
                st.rerun()

    # BOTÓN DE ANÁLISIS (Sección informativa mejorada)
    if st.session_state.df_activo is not None and 'Nivel' not in st.session_state.df_activo.columns:
        st.success(f"✅ Archivo validado con éxito: **{st.session_state.id_activo}**")
        num_v = len(st.session_state.df_activo)
        st.info(f"📊 Se han detectado **{num_v}** variantes listas para análisis.")
        
        if st.button("🚀 Iniciar Análisis Visual"):
            df = st.session_state.df_activo.copy()
            db = cargar_base_datos()
            fars, recs, nivs = [], [], []
            barra = st.progress(0.0)
            for i, (idx, r) in enumerate(df.iterrows()):
                res = consultar_farma(r['ID'], db)
                fars.append(res['farmaco']); recs.append(res['reco']); nivs.append(res['nivel'])
                barra.progress(float((i + 1) / len(df)))
                time.sleep(0.04)
            df['Farmaco'], df['Recomendacion'], df['Nivel'] = fars, recs, nivs
            st.session_state.df_activo = df
            clinica_n = st.session_state.get("username_logged", "Clínica VCI")
            guardar_analisis_pro(st.session_state.id_activo, df, clinica_n)
            st.rerun()

    # DASHBOARD
    if st.session_state.df_activo is not None and 'Nivel' in st.session_state.df_activo.columns:
        df = st.session_state.df_activo
        c1, c2 = st.columns([1, 2])
        with c1:
            fig = px.pie(df, names='Nivel', title="Distribución de Riesgo", hole=0.4,
                         color='Nivel', color_discrete_map={'Peligro':'#b00020','Riesgo':'#ef553b','Atención':'#fecb52','Seguro':'#00cc96'})
            st.plotly_chart(fig, width='stretch')
            pdf = generar_reporte_pdf(st.session_state.id_activo, df, "Clínica VCI")
            st.download_button("📩 Descargar PDF", pdf, f"Informe_{st.session_state.id_activo}.pdf", "application/pdf")

        with c2:
            st.subheader("📋 Hallazgos Críticos")
            riesgos = df[df['Nivel'] != 'Seguro']
            if not riesgos.empty:
                for _, r in riesgos.iterrows():
                    if r['Nivel'] == 'Peligro': st.error(f"🚨 **{r['Farmaco']}**: {r['Recomendacion']}")
                    elif r['Nivel'] == 'Riesgo': st.warning(f"⚠️ **{r['Farmaco']}**: {r['Recomendacion']}")
            else: st.success("No se detectaron riesgos genómicos.")
            st.dataframe(df[['ID', 'Farmaco', 'Nivel']], width='stretch')