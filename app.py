import streamlit as st
import pandas as pd
import requests
import time
import io
from fpdf import FPDF
import plotly.express as px  # Nueva librería para gráficos

# 1. Función de comprobación de seguridad (Login Multi-usuario)
def check_password():
    def password_entered():
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
            st.error("Error técnico: Configure los secretos en el servidor.")
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔐 Acceso al Portal Clínico")
        st.text_input("ID de Clínica / Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Portal Clínico")
        st.text_input("ID de Clínica / Usuario", on_change=password_entered, key="username")
        st.text_input("Contraseña", type="password", on_change=password_entered, key="password")
        st.error("😕 Credenciales no válidas.")
        return False
    return True

if check_password():
    st.set_page_config(page_title="VCI Pro Dashboard", page_icon="📊", layout="wide")

    with st.sidebar:
        st.header("⚙️ Panel")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()

    st.title("💊 VCI Farmacogenómica Pro")
    st.write("Panel de análisis genómico y respuesta a fármacos.")

    @st.cache_data
    def cargar_base_datos():
        try:
            return pd.read_csv("data/bd_farmacos.csv", index_col="ID_Variante")
        except:
            return pd.DataFrame()

    def consultar_ensembl(rs_id):
        servidor = "https://rest.ensembl.org"
        endpoint = f"/variation/human/{rs_id}?"
        try:
            r = requests.get(servidor + endpoint, headers={"Content-Type": "application/json"})
            if not r.ok: return "No encontrado"
            sig = r.json().get('clinical_significance', [])
            return ", ".join(sig) if sig else "Benigno/Frecuente"
        except: return "Error API"

    def consultar_farma(rs_id, df_bd):
        if not df_bd.empty and rs_id in df_bd.index:
            fila = df_bd.loc[rs_id]
            # Determinar nivel de alerta para el gráfico
            nivel = "Riesgo/Peligro" if "[RIESGO]" in str(fila["Recomendacion"]) or "[PELIGRO]" in str(fila["Recomendacion"]) else "Atención"
            return {"farmaco": str(fila["Farmaco"]), "reco": str(fila["Recomendacion"]), "nivel": nivel}
        return {"farmaco": "N/A", "reco": "Dosis estándar segura", "nivel": "Seguro"}

    archivo_subido = st.file_uploader("Cargar archivo VCF", type=['vcf'])

    if archivo_subido:
        df_bd = cargar_base_datos()
        lineas = archivo_subido.getvalue().decode("utf-8").splitlines()
        lineas_vcf = [l for l in lineas if not l.startswith('##')]
        df = pd.read_csv(io.StringIO("\n".join(lineas_vcf)), sep='\t')
        df.rename(columns={'#CHROM': 'CHROM'}, inplace=True)
        variantes = df[df['ID'].str.startswith('rs', na=False)].head(10).copy()

        if st.button("🚀 Iniciar Análisis Visual"):
            res_sig, res_far, res_rec, res_niv = [], [], [], []
            barra = st.progress(0)
            
            for i, (idx, fila) in enumerate(variantes.iterrows()):
                rsid = fila['ID']
                res_sig.append(consultar_ensembl(rsid))
                f = consultar_farma(rsid, df_bd)
                res_far.append(f['farmaco'])
                res_rec.append(f['reco'])
                res_niv.append(f['nivel'])
                barra.progress((i + 1) / len(variantes))
                time.sleep(0.1)

            variantes['Farmaco'] = res_far
            variantes['Recomendacion'] = res_rec
            variantes['Nivel'] = res_niv

            # --- DASHBOARD VISUAL ---
            st.divider()
            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader("📊 Resumen de Riesgos")
                # Crear gráfico de tarta
                fig = px.pie(variantes, names='Nivel', color='Nivel',
                             color_discrete_map={'Riesgo/Peligro':'#ef553b', 'Atención':'#fecb52', 'Seguro':'#636efa'},
                             hole=0.4)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("📋 Hallazgos Críticos")
                riesgos = variantes[variantes['Nivel'] != 'Seguro']
                if not riesgos.empty:
                    for _, r in riesgos.iterrows():
                        st.warning(f"**{r['ID']}** afecta a **{r['Farmaco']}**: {r['Recomendacion']}")
                else:
                    st.success("No se detectaron interacciones de riesgo en los marcadores analizados.")

            st.divider()
            st.subheader("🔍 Detalle Completo")
            st.dataframe(variantes[['ID', 'Farmaco', 'Recomendacion', 'Nivel']], width='stretch')