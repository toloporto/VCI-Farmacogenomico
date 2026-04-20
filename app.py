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

        st.divider()
        st.subheader("📁 Historial Reciente")
        try:
            df_h = pd.read_csv("data/historial_clinico.csv")
            st.dataframe(df_h.tail(5), hide_index=True)
        except:
            st.write("No hay análisis previos.")

    st.title("💊 VCI Farmacogenómica Pro")
    st.write("Panel de análisis genómico y respuesta a fármacos.")

    @st.cache_data
    def cargar_base_datos():
        """Carga la BD de fármacos con soporte para RSIDs duplicados."""
        try:
            # No usamos index_col para manejar RSIDs con múltiples fármacos
            df = pd.read_csv("data/bd_farmacos.csv", encoding="utf-8")
            return df
        except:
            return pd.DataFrame()

    def guardar_en_historial(id_paciente, total_variantes, riesgo_pct):
        """Guarda un resumen del análisis en un archivo local para persistencia."""
        nuevo_registro = pd.DataFrame([{
            "Fecha": time.strftime("%Y-%m-%d %H:%M"),
            "Paciente_ID": id_paciente,
            "Total_Var": total_variantes,
            "Riesgo_%": f"{riesgo_pct:.1f}%"
        }])
        
        try:
            historial = pd.read_csv("data/historial_clinico.csv")
            historial = pd.concat([historial, nuevo_registro], ignore_index=True)
        except FileNotFoundError:
            historial = nuevo_registro
        
        historial.to_csv("data/historial_clinico.csv", index=False)

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
        """Consulta la BD local. Maneja RSIDs que afectan a múltiples fármacos."""
        if df_bd.empty or "ID_Variante" not in df_bd.columns:
            return {"farmaco": "N/A", "reco": "Dosis estándar segura", "nivel": "Seguro"}
        
        # Filtrar todas las filas para este RSID
        coincidencias = df_bd[df_bd["ID_Variante"] == rs_id]
        
        if coincidencias.empty:
            return {"farmaco": "N/A", "reco": "Dosis estándar segura", "nivel": "Seguro"}
        
        # Concatenar todos los fármacos y recomendaciones encontrados
        farmacos = " / ".join(coincidencias["Farmaco"].astype(str).tolist())
        recos = " | ".join(coincidencias["Recomendacion"].astype(str).tolist())
        
        # Determinar el nivel más crítico encontrado
        recos_str = recos.upper()
        if "[PELIGRO]" in recos_str:
            nivel = "Peligro"
        elif "[RIESGO]" in recos_str:
            nivel = "Riesgo"
        elif "[ATENCION]" in recos_str:
            nivel = "Atención"
        else:
            nivel = "Seguro"
        
        return {"farmaco": farmacos, "reco": recos, "nivel": nivel}

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

            # Guardar en historial
            id_paciente = archivo_subido.name.split('.')[0]
            total_vars = len(variantes)
            riesgo_pct = (variantes['Nivel'] != 'Seguro').sum() / total_vars * 100 if total_vars > 0 else 0
            guardar_en_historial(id_paciente, total_vars, riesgo_pct)

            # --- DASHBOARD VISUAL ---
            st.divider()
            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader("📊 Resumen de Riesgos")
                # Gráfico de tarta con los cuatro niveles de alerta
                fig = px.pie(variantes, names='Nivel', color='Nivel',
                             color_discrete_map={
                                 'Peligro':    '#b00020',   # rojo oscuro
                                 'Riesgo':     '#ef553b',   # rojo
                                 'Atención':   '#fecb52',   # amarillo
                                 'Seguro':     '#00cc96'    # verde
                             },
                             hole=0.4)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("📋 Hallazgos Críticos")
                riesgos = variantes[variantes['Nivel'] != 'Seguro']
                if not riesgos.empty:
                    for _, r in riesgos.iterrows():
                        # Mostrar con distintos colores según gravedad
                        if r['Nivel'] == 'Peligro':
                            st.error(f"🚨 **{r['ID']}** → **{r['Farmaco']}**: {r['Recomendacion']}")
                        elif r['Nivel'] == 'Riesgo':
                            st.warning(f"⚠️ **{r['ID']}** → **{r['Farmaco']}**: {r['Recomendacion']}")
                        else:
                            st.info(f"ℹ️ **{r['ID']}** → **{r['Farmaco']}**: {r['Recomendacion']}")
                else:
                    st.success("✅ No se detectaron interacciones de riesgo en los marcadores analizados.")

            st.divider()
            st.subheader("🔍 Detalle Completo")
            st.dataframe(variantes[['ID', 'Farmaco', 'Recomendacion', 'Nivel']], width='stretch')