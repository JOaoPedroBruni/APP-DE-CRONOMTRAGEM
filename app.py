import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import io
import os
import re
from io import StringIO
import unicodedata

# ---------------- Configuração da Página ----------------
st.set_page_config(page_title="Plataforma Cronometragem", layout="wide")

# --- FUNÇÃO DE LOGIN ---
def check_password():
    """Retorna `True` se o usuário fez o login, `False` caso contrário."""
    def login_form():
        """Formulário de login centralizado."""
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            with st.form("Credentials"):
                st.image("logo.png", use_container_width=True)
                username = st.text_input("Usuário", key="login_username")
                password = st.text_input("Senha", type="password", key="login_password")
                submitted = st.form_submit_button("Entrar")
                if submitted:
                    correct_username = st.secrets.get("credentials", {}).get("username")
                    correct_password = st.secrets.get("credentials", {}).get("password")
                    if username == correct_username and password == correct_password:
                        st.session_state["password_correct"] = True
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválida")
    if st.session_state.get("password_correct", False):
        return True
    login_form()
    return False

# --- FUNÇÕES AUXILIARES ---
COL_CATEGORIA, COL_EVENTO = "CATEGORIA", "Evento" 
COL_SUBCATEGORIA, COL_PILOTO = "SUBCATEGORIA", "Piloto"
COL_VOLTA, COL_TT = "Volta", "Tempo Total da Volta"
COL_S1, COL_S2, COL_S3 = "Setor 1", "Setor 2", "Setor 3"
COL_VEL = "TOP SPEED"
COLS_TEMPO = [COL_TT, COL_S1, COL_S2, COL_S3]

def parse_tempo(txt):
    if pd.isna(txt): return pd.NaT
    s = str(txt).strip().replace(',', '.')
    if re.fullmatch(r"\d{1,2}:\d{2}\.\d{1,3}", s):
        m, r = s.split(':')
        return pd.to_timedelta(int(m) * 60 + float(r), unit='s')
    if re.fullmatch(r"\d{1,3}\.\d{1,3}", s):
        return pd.to_timedelta(float(s), unit='s')
    if 'days' in s:
        return pd.to_timedelta(s, errors='coerce')
    return pd.to_timedelta(s, errors='coerce')

def fmt_tempo(td):
    if pd.isna(td) or td is None: return "---"
    s = td.total_seconds()
    m = int(round(s * 1000) % 1000)
    n = int(s // 60)
    c = int(s % 60)
    return f"{n:01d}:{c:02d}.{m:03d}"

def formatar_diff_span(td_or_float, unit=""):
    if pd.isna(td_or_float): return ""
    value_num = td_or_float.total_seconds() if isinstance(td_or_float, pd.Timedelta) else td_or_float
    if pd.isna(value_num): return ""
    if value_num == 0: return f"<span class='diff-zero'>0.000 {unit}</span>"
    sinal = "+" if value_num > 0 else ""
    classe = "diff-pos" if value_num > 0 else "diff-neg"
    icone = "▲" if value_num > 0 else "▼"
    return f"<span class='{classe}'>{sinal}{value_num:.3f} {icone} {unit}</span>"

def normalizar_tipos_dados(df):
    for c in COLS_TEMPO:
        if c in df.columns:
            df[c] = df[c].apply(parse_tempo)
    if COL_VEL in df.columns:
        df[COL_VEL] = pd.to_numeric(df[COL_VEL].astype(str).str.replace(',', '.'), errors='coerce')
    return df

def limpar_nome_para_juncao(texto):
    if pd.isna(texto): return ""
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'^\d+\s*-\s*', '', texto)
    return texto.lower().strip()

def ler_csv_original(src, filename=""):
    categoria_nome, evento_nome = "Desconhecida", "Sessão Desconhecida"
    if filename:
        base = os.path.basename(filename).upper().replace('- LAPTIMES.CSV', '').replace('.CSV', '').strip()
        parts = base.split(' - ')
        if len(parts) > 1:
            categoria_nome, evento_nome = parts[0].strip(), ' - '.join(parts[1:]).strip()
        else:
            evento_nome = parts[0].strip()

    try:
        if hasattr(src, "seek"): src.seek(0)
        content_as_string = src.getvalue().decode("utf-8", "ignore")
        lines = [l.strip() for l in content_as_string.splitlines() if l.strip()]
        
        header_line_index = next((i for i, line in enumerate(lines) if "Lap Tm" in line and "Lap" in line), -1)
        if header_line_index == -1: return pd.DataFrame()

        df_alt = pd.read_csv(StringIO("\n".join(lines[header_line_index:])), sep=',', quotechar='"', engine='python')

        if 'Driver' in df_alt.columns and COL_PILOTO not in df_alt.columns:
            df_alt = df_alt.rename(columns={'Driver': COL_PILOTO})

        hora_pat = re.compile(r"^\d{1,2}:\d{2}:\d{2}\.\d{1,3}$")
        col_hora = next((c for c in df_alt.columns if "Time" in c), None)
        if not col_hora: return pd.DataFrame()

        df_alt["Piloto_tmp"] = df_alt[col_hora].where(~df_alt[col_hora].str.match(hora_pat, na=False)).ffill()
        df_alt = df_alt.dropna(subset=['Lap', 'Lap Tm'])

        df_map = pd.DataFrame({
            COL_CATEGORIA: categoria_nome, COL_EVENTO: evento_nome, COL_SUBCATEGORIA: "N/A",
            COL_PILOTO: df_alt["Piloto_tmp"], "Horário": df_alt[col_hora],
            COL_VOLTA: df_alt["Lap"], COL_TT: df_alt["Lap Tm"],
            COL_S1: df_alt.get("S1 Tm"), COL_S2: df_alt.get("S2 Tm"),
            COL_S3: df_alt.get("S3 Tm"), COL_VEL: df_alt.get("Speed"),
        })
        
        return df_map if COL_PILOTO in df_map.columns and COL_VOLTA in df_map.columns else pd.DataFrame()

    except Exception:
        return pd.DataFrame()

# --- FUNÇÃO PRINCIPAL DA APLICAÇÃO ---
def main_app():
    st.title("🏎️ Plataforma de Cronometragem Multi-Sessão")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    PASTA_ETAPAS = "etapas_salvas"
    os.makedirs(PASTA_ETAPAS, exist_ok=True)
    
    df_completo = pd.DataFrame()
    
    with st.sidebar.expander("⚙️ Ferramenta de Consolidação"):
        uploaded_files = st.file_uploader("Carregar múltiplos arquivos CSV", type="csv", accept_multiple_files=True)
        if uploaded_files:
            dfs_novos = [ler_csv_original(f, filename=f.name) for f in uploaded_files if not f.name.startswith('.')]
            dfs_novos = [df for df in dfs_novos if not df.empty]
            
            if dfs_novos:
                df_completo = pd.concat(dfs_novos, ignore_index=True)
                st.success(f"{len(dfs_novos)} arquivo(s) carregado(s) com sucesso!")
            else:
                st.error("Nenhum arquivo válido pôde ser processado.")

            if not df_completo.empty:
                nome_consolidado = st.text_input("Nome do arquivo consolidado:", "Etapa_Consolidada.csv")
                if st.button("Salvar Etapa Consolidada"):
                    if nome_consolidado:
                        caminho_salvar = os.path.join(PASTA_ETAPAS, nome_consolidado)
                        df_completo.to_csv(caminho_salvar, sep=';', index=False, encoding='utf-8-sig')
                        st.success(f"Arquivo '{nome_consolidado}' salvo!")
                    else:
                        st.warning("Defina um nome para o arquivo.")

    st.sidebar.header("📁 Selecionar Etapa para Análise")
    arquivos_disponiveis = [filename for filename in os.listdir(PASTA_ETAPAS) if filename.lower().endswith('.csv')]
    opcoes = ["-- Escolha uma etapa --"] + sorted(arquivos_disponiveis)
    arquivo_selecionado = st.sidebar.selectbox("Etapas salvas:", opcoes)

    if not uploaded_files and arquivo_selecionado != "-- Escolha uma etapa --":
        try:
            caminho_completo = os.path.join(PASTA_ETAPAS, arquivo_selecionado)
            df_completo = pd.read_csv(caminho_completo, sep=';', encoding='utf-8-sig', low_memory=False)
        except Exception as e:
            st.error(f"Não foi possível ler a etapa salva: {e}")
    
    if df_completo.empty:
        st.info("⬅️ Selecione uma etapa salva ou carregue novos arquivos para começar a análise.")
        st.stop()
    
    caminho_subcat = "pilotos_subcategoria.csv"
    if os.path.exists(caminho_subcat):
        try:
            try:
                mapa = pd.read_csv(caminho_subcat, sep=';', encoding='utf-8-sig')
            except UnicodeDecodeError:
                mapa = pd.read_csv(caminho_subcat, sep=';', encoding='latin-1')
            
            if len(mapa.columns) >= 2:
                mapa = mapa.rename(columns={mapa.columns[0]: 'Piloto', mapa.columns[1]: 'SUBCATEGORIA_LIDA'})
            else:
                st.error(f"ERRO: Arquivo '{caminho_subcat}' precisa ter pelo menos 2 colunas.")
                st.stop()

            mapa['CHAVE_JUNCAO'] = mapa['Piloto'].apply(limpar_nome_para_juncao)
            df_completo['CHAVE_JUNCAO'] = df_completo[COL_PILOTO].apply(limpar_nome_para_juncao)
            
            if COL_SUBCATEGORIA in df_completo.columns:
                df_completo = df_completo.drop(columns=[COL_SUBCATEGORIA])
            
            df_completo = pd.merge(df_completo, mapa[['CHAVE_JUNCAO', 'SUBCATEGORIA_LIDA']], on='CHAVE_JUNCAO', how='left')
            df_completo = df_completo.rename(columns={'SUBCATEGORIA_LIDA': COL_SUBCATEGORIA})
            df_completo.drop(columns=['CHAVE_JUNCAO'], inplace=True, errors='ignore')

        except Exception as e:
            st.error(f"Ocorreu um erro ao processar o arquivo '{caminho_subcat}': {e}")
    else:
        st.sidebar.warning(f"Arquivo '{caminho_subcat}' não encontrado.")

    if COL_SUBCATEGORIA not in df_completo.columns:
        df_completo[COL_SUBCATEGORIA] = "N/A"
    df_completo[COL_SUBCATEGORIA].fillna("NÃO CADASTRADO", inplace=True)

    df_completo = normalizar_tipos_dados(df_completo)
    
    df_completo[COL_PILOTO] = df_completo[COL_PILOTO].str.replace(r'^\d+\s*-\s*', '', regex=True).str.strip()
    
    st.sidebar.header("🔍 Filtros da Etapa")
    df_final = pd.DataFrame()
    
    categorias_disponiveis = sorted(df_completo[COL_CATEGORIA].dropna().unique())
    if not categorias_disponiveis:
        st.sidebar.error("Nenhuma Categoria encontrada nos dados carregados.")
        st.stop()

    cat_selecionada = st.sidebar.selectbox("CATEGORIA", categorias_disponiveis, index=0)
    
    df_filtrado_cat = df_completo[df_completo[COL_CATEGORIA] == cat_selecionada]
    eventos_disponiveis = sorted(df_filtrado_cat[COL_EVENTO].dropna().unique())
    
    ev_selecionado = None
    if not eventos_disponiveis:
        st.sidebar.warning("Nenhum evento encontrado para a categoria selecionada.")
    else:
        ev_selecionado = st.sidebar.selectbox("Evento / Sessão", eventos_disponiveis, index=0)

    PASTA_MAPAS_IMAGENS = "mapas"
    os.makedirs(PASTA_MAPAS_IMAGENS, exist_ok=True)
    map_select = None

    if arquivo_selecionado and arquivo_selecionado != "-- Escolha uma etapa --":
        MAPEAMENTO_PISTAS = {
            "ET6": "Estoril.png", "25ET6": "Estoril.png",
            "ET7": "Estoril.png", "25ET7": "Estoril.png",
            "ET5": "Algarve.png", "25ET5": "Algarve.png",
            "ET4": "Algarve.png", "25ET4": "Algarve.png",
            "ETX":"Velocitta.png", "25ETX": "Velocitta.png",
            "ET8": "Interlagos.png", "25ET8": "Interlagos.png",
            "ET9": "Interlagos.png", "25ET9": "Interlagos.png",
            "ET3": "Interlagos.png", "25ET3": "Interlagos.png",
            "ET1":"Velocitta.png", "25ET1": "Velocitta.png",
            "ET2":"Velocitta.png", "25ET2": "Velocitta.png",
            
        }
        nome_arquivo_upper = arquivo_selecionado.upper()
        mapa_encontrado = next((v for k, v in MAPEAMENTO_PISTAS.items() if k in nome_arquivo_upper), None)
        
        if mapa_encontrado and os.path.exists(os.path.join(PASTA_MAPAS_IMAGENS, mapa_encontrado)):
            map_select = mapa_encontrado
            st.sidebar.image(os.path.join(PASTA_MAPAS_IMAGENS, map_select), use_container_width=True, caption=f"Pista: {os.path.splitext(map_select)[0].capitalize()}")
    
    if ev_selecionado:
        df_filtrado_ev = df_filtrado_cat[df_filtrado_cat[COL_EVENTO] == ev_selecionado]
        subcategorias_disponiveis = sorted(df_filtrado_ev[COL_SUBCATEGORIA].dropna().unique())
        subcats_selecionadas = st.sidebar.multiselect("SUBCATEGORIA", subcategorias_disponiveis, default=subcategorias_disponiveis)
        df = df_filtrado_ev[df_filtrado_ev[COL_SUBCATEGORIA].isin(subcats_selecionadas)]
        
        pilotos_disponiveis = sorted(df[COL_PILOTO].dropna().unique())
        pilotos_selecionados = st.sidebar.multiselect("Pilotos", pilotos_disponiveis, default=pilotos_disponiveis)
        df_final = df[df[COL_PILOTO].isin(pilotos_selecionados)]
        
        if not df_final.empty:
            voltas = sorted(df_final[COL_VOLTA].dropna().unique())
            voltas_selecionadas = st.sidebar.multiselect("Voltas", voltas, default=voltas)
            df_final = df_final[df_final[COL_VOLTA].isin(voltas_selecionadas)].reset_index(drop=True)

    header_text = f"Análise: {cat_selecionada if cat_selecionada else 'Nenhuma Categoria'}"
    if 'ev_selecionado' in locals() and ev_selecionado:
        header_text += f" - {ev_selecionado}"
    st.header(header_text)
    
    tab_titles = ["Geral", "Volta Rápida", "Velocidade", "Gráficos", "Comparativo Visual", "Piloto x Sessões", "Histórico", "Exportar"]
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        st.subheader("📋 Tabela Completa de Voltas")
        if not df_final.empty:
            df_display = df_final.copy()
            best_lap_geral = df_display[COL_TT].min()
            best_s1_geral = df_display[COL_S1].min() if COL_S1 in df_display.columns and not df_display[COL_S1].dropna().empty else None
            best_s2_geral = df_display[COL_S2].min() if COL_S2 in df_display.columns and not df_display[COL_S2].dropna().empty else None
            best_s3_geral = df_display[COL_S3].min() if COL_S3 in df_display.columns and not df_display[COL_S3].dropna().empty else None
            best_vel_geral = df_display[COL_VEL].max() if COL_VEL in df_display.columns and not df_display[COL_VEL].dropna().empty else None

            def highlight_bests(row):
                styles = pd.Series('', index=row.index)
                if pd.notna(row[COL_TT]) and row[COL_TT] == best_lap_geral: styles[COL_TT] = 'color: #00BFFF; font-weight: bold;'
                if pd.notna(row.get(COL_S1)) and row[COL_S1] == best_s1_geral: styles[COL_S1] = 'background-color: #483D8B; color: white;'
                if pd.notna(row.get(COL_S2)) and row[COL_S2] == best_s2_geral: styles[COL_S2] = 'background-color: #483D8B; color: white;'
                if pd.notna(row.get(COL_S3)) and row[COL_S3] == best_s3_geral: styles[COL_S3] = 'background-color: #483D8B; color: white;'
                if pd.notna(row.get(COL_VEL)) and row[COL_VEL] == best_vel_geral: styles[COL_VEL] = 'background-color: #2E8B57; color: white;'
                return styles

            ordem_colunas = [COL_EVENTO, COL_PILOTO, COL_CATEGORIA, COL_SUBCATEGORIA, "Horário", COL_VOLTA, COL_TT, COL_S1, COL_S2, COL_S3, COL_VEL]
            colunas_existentes = [col for col in ordem_colunas if col in df_display.columns]
            df_display = df_display[colunas_existentes]
            format_dict = {c: fmt_tempo for c in COLS_TEMPO if c in df_display.columns}
            st.dataframe(df_display.style.apply(highlight_bests, axis=1).format(format_dict, na_rep="---"), use_container_width=True, height=600)
        else:
            st.info("Nenhum dado para exibir. Verifique os filtros na barra lateral.")
        
        st.markdown("---")
        st.subheader("🗺️ Mapa da Pista")
        if map_select and os.path.exists(os.path.join(PASTA_MAPAS_IMAGENS, map_select)):
            st.image(os.path.join(PASTA_MAPAS_IMAGENS, map_select), use_container_width=True)
        else:
            st.info("Nenhum mapa selecionado ou encontrado para esta etapa.")
            
    with tabs[1]:
        st.subheader("🏆 Melhor Volta de Cada Piloto")
        if not df_final.empty and COL_TT in df_final and not df_final[COL_TT].dropna().empty:
            df_best_laps = df_final.copy()
            df_best = df_best_laps.loc[df_best_laps.groupby(COL_PILOTO)[COL_TT].idxmin()]
            best_df = df_best.sort_values(by=COL_TT).copy()
            for c in COLS_TEMPO:
                if c in best_df.columns: best_df[c] = best_df[c].apply(fmt_tempo)
            st.dataframe(best_df, hide_index=True, use_container_width=True)
        else: 
            st.info("Não há dados de tempo de volta disponíveis para classificar.")

    with tabs[2]:
        st.subheader("🚀 Maior Top Speed de Cada Piloto")
        if not df_final.empty and COL_VEL in df_final and not df_final[COL_VEL].dropna().empty:
            sp_df = df_final.sort_values(by=COL_VEL, ascending=False).drop_duplicates(subset=[COL_PILOTO], keep='first').copy()
            for c in COLS_TEMPO:
                if c in sp_df.columns: sp_df[c] = sp_df[c].apply(fmt_tempo)
            st.dataframe(sp_df, hide_index=True, use_container_width=True)
        else: 
            st.info("Não há dados de velocidade disponíveis.")
            
    with tabs[3]:
        st.header("📈 Análises Gráficas")
        if df_final.empty:
            st.warning("Selecione os filtros na barra lateral para visualizar os gráficos.")
        else:
            if COL_TT in df_final.columns and not df_final[COL_TT].dropna().empty:
                st.subheader("Comparativo de Tempo por Volta")
                fig, ax = plt.subplots(figsize=(10, 5))
                for p in pilotos_selecionados:
                    g_plot = df_final[(df_final[COL_PILOTO] == p) & (df_final[COL_TT].notna())].sort_values(by=COL_VOLTA)
                    if not g_plot.empty: ax.plot(g_plot[COL_VOLTA], g_plot[COL_TT].dt.total_seconds(), marker='o', linestyle='-', label=p)
                ax.set_xlabel("Volta"); ax.set_ylabel("Tempo (M:SS)")
                ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda s, pos: f'{int(s // 60)}:{int(s % 60):02d}'))
                ax.grid(True, linestyle='--', alpha=0.6); ax.legend()
                st.pyplot(fig, use_container_width=True)

            if COL_VEL in df_final.columns and not df_final[COL_VEL].dropna().empty:
                st.subheader("Comparativo de Top Speed por Volta")
                fig1, ax1 = plt.subplots(figsize=(10, 5))
                for p in pilotos_selecionados:
                    g_plot = df_final[(df_final[COL_PILOTO] == p) & (df_final[COL_VEL].notna())].sort_values(by=COL_VOLTA)
                    if not g_plot.empty: ax1.plot(g_plot[COL_VOLTA], g_plot[COL_VEL], marker='s', linestyle='--', label=p)
                ax1.set_xlabel("Volta"); ax1.set_ylabel("Velocidade (km/h)")
                ax1.grid(True, linestyle='--', alpha=0.6); ax1.legend()
                st.pyplot(fig1, use_container_width=True)
    
    with tabs[4]:
        st.subheader("📊 Comparativo Visual entre Pilotos")
        if df_final.empty:
            st.warning("Nenhum dado disponível para os filtros selecionados.")
        elif 'pilotos_selecionados' in locals() and len(pilotos_selecionados) < 2:
            st.warning("⚠️ Por favor, selecione pelo menos 2 pilotos na barra lateral para fazer a comparação.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                tipo_analise = st.radio("Tipo de Análise:", ("Tempo de Volta", "Velocidade Máxima"), horizontal=True, key="tipo_analise_piloto")
            with col2:
                opcoes_referencia = ["-- Sem Referência --"] + pilotos_selecionados
                modo_comparacao = st.selectbox("Piloto de Referência:", opcoes_referencia, key="modo_comp_piloto")
            with col3:
                filtro_voltas = "Todas as Voltas"
                if tipo_analise == "Tempo de Volta":
                    filtro_voltas = st.radio("Filtrar Voltas:", ("Todas as Voltas", "Apenas Voltas Rápidas"), horizontal=True, key="filtro_voltas_piloto")
            
            st.markdown("---")
            coluna_dado = COL_TT if tipo_analise == "Tempo de Volta" else COL_VEL
            df_analise_piloto = df_final.copy()
            
            if filtro_voltas == "Apenas Voltas Rápidas" and tipo_analise == "Tempo de Volta":
                volta_rapida_geral = df_analise_piloto[coluna_dado].min()
                if pd.notna(volta_rapida_geral):
                    limite_superior = volta_rapida_geral + pd.Timedelta(seconds=15)
                    df_analise_piloto = df_analise_piloto[df_analise_piloto[coluna_dado] <= limite_superior]
            
            if df_analise_piloto.empty:
                st.warning("Nenhuma volta encontrada dentro do critério de 'Voltas Rápidas'.")
            else:
                fig, ax = plt.subplots(figsize=(12, 6))
                piloto_referencia = modo_comparacao if modo_comparacao != "-- Sem Referência --" else None
                for p in pilotos_selecionados:
                    piloto_df_plot = df_analise_piloto[df_analise_piloto[COL_PILOTO] == p].dropna(subset=[coluna_dado])
                    if not piloto_df_plot.empty:
                        dados_y = piloto_df_plot[coluna_dado].dt.total_seconds() if tipo_analise == "Tempo de Volta" else piloto_df_plot[coluna_dado]
                        is_ref = piloto_referencia and p == piloto_referencia
                        ax.plot(piloto_df_plot[COL_VOLTA], dados_y, marker='o', markersize=7 if is_ref else 5, linewidth=3 if is_ref else 1.5, linestyle='-' if is_ref else '--', label=f"{p} (Ref.)" if is_ref else p, zorder=10 if is_ref else 5)
                
                ax.set_xlabel("Volta"); ax.set_title(f"Comparativo de {tipo_analise}"); ax.legend(fontsize='small'); ax.grid(True, which='both', linestyle='--', linewidth=0.5)
                if tipo_analise == "Tempo de Volta":
                    ax.set_ylabel("Tempo de Volta (M:SS)"); ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda s, pos: f'{int(s // 60)}:{int(s % 60):02d}' if s > 0 else ''))
                else:
                    ax.set_ylabel("Velocidade (km/h)")
                st.pyplot(fig, use_container_width=True)
                st.markdown("---")
                
                st.subheader(f"Análise Detalhada: {tipo_analise}")
                df_comp_pivot = df_analise_piloto.pivot_table(index=COL_VOLTA, columns=COL_PILOTO, values=coluna_dado)
                unidade = "" if tipo_analise == "Tempo de Volta" else "km/h"
                
                common_css = """<style> .table-container { overflow-x: auto; } .comp-table { width: 100%; border-collapse: collapse; font-size: 0.9em; } .comp-table th, .comp-table td { padding: 6px 8px; text-align: center; white-space: nowrap; } .comp-table th { font-family: sans-serif; border-bottom: 2px solid #444; } .comp-table td { border-bottom: 1px solid #333; line-height: 1.3; } .comp-table tr:hover td { background-color: #2e2e2e; } .comp-table b { font-size: 1.1em; } .diff-span { font-size: 0.9em; display: block; } .diff-pos { color: #ff4d4d !important; } .diff-neg { color: #4dff4d !important; } .diff-zero { color: #888; } </style>"""
                html = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr><th>Volta</th>"
                for p in pilotos_selecionados: html += f"<th>{p}</th>"
                html += "</tr></thead><tbody>"

                for volta, row in df_comp_pivot.iterrows():
                    html += f"<tr><td><b>{int(volta)}</b></td>"
                    dado_ref = row.get(piloto_referencia)
                    for p in pilotos_selecionados:
                        dado_atual = row.get(p)
                        diff_str = ""
                        if p != piloto_referencia and piloto_referencia and pd.notna(dado_atual) and pd.notna(dado_ref):
                            diff = dado_atual - dado_ref
                            diff_str = f"<span class='diff-span'>{formatar_diff_span(diff, unit=unidade)}</span>"
                        valor_str = fmt_tempo(dado_atual) if tipo_analise == "Tempo de Volta" else (f"{dado_atual:.1f}" if pd.notna(dado_atual) else "---")
                        html += f"<td>{valor_str} {unidade}{diff_str}</td>"
                    html += "</tr>"
                html += "</tbody></table></div>"
                st.markdown(html, unsafe_allow_html=True)
    
    with tabs[5]:
        st.subheader("📊 Comparativo do Piloto entre Sessões")
        if df_final.empty:
            st.warning("Nenhum dado disponível para os filtros selecionados.")
        else:
            pilotos_disponiveis_etapa = sorted(df_filtrado_cat[COL_PILOTO].unique())
            piloto_analise = st.selectbox("Selecione o Piloto para Análise:", pilotos_disponiveis_etapa)
            if piloto_analise:
                df_piloto = df_filtrado_cat[df_filtrado_cat[COL_PILOTO] == piloto_analise]
                sessoes_disponiveis = sorted(df_piloto[COL_EVENTO].unique())
                if len(sessoes_disponiveis) >= 2:
                    sessoes_selecionadas = st.multiselect("Selecione as Sessões para Comparar:", sessoes_disponiveis, default=sessoes_disponiveis)
                    if len(sessoes_selecionadas) >= 2:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                           tipo_analise_sessao = st.radio("Tipo de Análise:", ("Tempo de Volta", "Velocidade Máxima"), horizontal=True, key="tipo_analise_sessao")
                        with col2:
                           sessao_referencia = st.selectbox("Sessão de Referência:", sessoes_selecionadas, key="ref_sessao")
                        with col3:
                            filtro_voltas_sessao = "Todas as Voltas"
                            if tipo_analise_sessao == "Tempo de Volta":
                                filtro_voltas_sessao = st.radio("Filtrar Voltas:", ("Todas as Voltas", "Apenas Voltas Rápidas"), horizontal=True, key="filtro_voltas_sessao")
                        st.markdown("---")
                        coluna_dado = COL_TT if tipo_analise_sessao == "Tempo de Volta" else COL_VEL
                        df_analise_sessao = df_piloto[df_piloto[COL_EVENTO].isin(sessoes_selecionadas)].copy()
                        
                        if filtro_voltas_sessao == "Apenas Voltas Rápidas" and tipo_analise_sessao == "Tempo de Volta":
                            volta_rapida_geral = df_analise_sessao[coluna_dado].min()
                            if pd.notna(volta_rapida_geral):
                                limite_superior = volta_rapida_geral + pd.Timedelta(seconds=15)
                                df_analise_sessao = df_analise_sessao[df_analise_sessao[coluna_dado] <= limite_superior]

                        if df_analise_sessao.empty:
                            st.warning("Nenhuma volta encontrada dentro do critério de 'Voltas Rápidas'.")
                        else:
                            fig_s, ax_s = plt.subplots(figsize=(12, 6))
                            for sessao in sessoes_selecionadas:
                                dados_sessao = df_analise_sessao[df_analise_sessao[COL_EVENTO] == sessao].dropna(subset=[coluna_dado])
                                if not dados_sessao.empty:
                                    dados_y = dados_sessao[coluna_dado].dt.total_seconds() if tipo_analise_sessao == "Tempo de Volta" else dados_sessao[coluna_dado]
                                    is_ref = (sessao == sessao_referencia)
                                    ax_s.plot(dados_sessao[COL_VOLTA], dados_y, marker='o', markersize=7 if is_ref else 5, linewidth=3 if is_ref else 1.5, linestyle='-' if is_ref else '--', label=f"{sessao} (Ref.)" if is_ref else sessao, zorder=10 if is_ref else 5)
                            
                            ax_s.set_xlabel("Volta"); ax_s.set_title(f"Comparativo de {tipo_analise_sessao} para {piloto_analise}"); ax_s.legend(fontsize='small'); ax_s.grid(True, which='both', linestyle='--', linewidth=0.5)
                            if tipo_analise_sessao == "Tempo de Volta":
                               ax_s.set_ylabel("Tempo de Volta (M:SS)"); ax_s.yaxis.set_major_formatter(mticker.FuncFormatter(lambda s, pos: f'{int(s // 60)}:{int(s % 60):02d}' if s > 0 else ''))
                            else:
                               ax_s.set_ylabel("Velocidade (km/h)")
                            st.pyplot(fig_s, use_container_width=True)
                            st.markdown("---")

                            st.subheader(f"Análise Detalhada: {tipo_analise_sessao}")
                            df_comp_pivot_sessao = df_analise_sessao.pivot_table(index=COL_VOLTA, columns=COL_EVENTO, values=coluna_dado)
                            unidade = "" if tipo_analise_sessao == "Tempo de Volta" else "km/h"
                            common_css = """<style> .table-container { overflow-x: auto; } .comp-table { width: 100%; border-collapse: collapse; font-size: 0.9em; } .comp-table th, .comp-table td { padding: 6px 8px; text-align: center; white-space: nowrap; } .comp-table th { font-family: sans-serif; border-bottom: 2px solid #444; } .comp-table td { border-bottom: 1px solid #333; line-height: 1.3; } .comp-table tr:hover td { background-color: #2e2e2e; } .comp-table b { font-size: 1.1em; } .diff-span { font-size: 0.9em; display: block; } .diff-pos { color: #ff4d4d !important; } .diff-neg { color: #4dff4d !important; } .diff-zero { color: #888; } </style>"""
                            html_s = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr><th>Volta</th>"
                            for s in sessoes_selecionadas: html_s += f"<th>{s}</th>"
                            html_s += "</tr></thead><tbody>"

                            for volta, row in df_comp_pivot_sessao.iterrows():
                                html_s += f"<tr><td><b>{int(volta)}</b></td>"
                                dado_ref = row.get(sessao_referencia)
                                for s in sessoes_selecionadas:
                                    dado_atual = row.get(s)
                                    diff_str = ""
                                    if s != sessao_referencia and pd.notna(dado_atual) and pd.notna(dado_ref):
                                        diff = dado_atual - dado_ref
                                        diff_str = f"<span class='diff-span'>{formatar_diff_span(diff, unit=unidade)}</span>"
                                    valor_str = fmt_tempo(dado_atual) if tipo_analise_sessao == "Tempo de Volta" else (f"{dado_atual:.1f}" if pd.notna(dado_atual) else "---")
                                    html_s += f"<td>{valor_str} {unidade}{diff_str}</td>"
                                html_s += "</tr>"
                            html_s += "</tbody></table></div>"
                            st.markdown(html_s, unsafe_allow_html=True)
                else:
                    st.info("Este piloto participou de menos de duas sessões nesta etapa para permitir uma comparação.")

    with tabs[6]:
        st.subheader("🗂️ Histórico de Etapas Salvas")
        files_in_folder = sorted(os.listdir(PASTA_ETAPAS))
        if files_in_folder:
            st.dataframe(pd.DataFrame({"Arquivo": files_in_folder}), hide_index=True)
        else:
            st.info(f"Nenhum arquivo encontrado na pasta '{PASTA_ETAPAS}'.")

    with tabs[7]:
        st.subheader("📤 Exportar dados filtrados")
        if df_final.empty:
            st.info("Não há dados filtrados para exportar.")
        else:
            buf = io.BytesIO()
            out = df_final.copy()
            for c in COLS_TEMPO:
                if c in out.columns: out[c] = out[c].apply(fmt_tempo)
            
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                out.to_excel(writer, index=False, sheet_name='Dados Filtrados')
            
            st.download_button(
                label="⬇️ Baixar como Excel",
                data=buf.getvalue(),
                file_name=f"cronometragem_filtrada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# --- PONTO DE ENTRADA PRINCIPAL ---
if check_password():
    main_app()