import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import io
import os
import re
from io import StringIO

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

# --- FUNÇÕES AUXILIARES (SEU CÓDIGO ORIGINAL) ---
COL_LOCAL, COL_EVENTO = "Local", "Evento"
COL_CAT, COL_PILOTO = "CATEGORIA", "Piloto"
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
    return pd.to_timedelta(s, errors='coerce')

def fmt_tempo(td):
    if pd.isna(td) or td is None: return "---"
    s = td.total_seconds()
    m = int((s % 1) * 1000)
    n = int(s // 60)
    c = int(s % 60)
    return f"{n:01d}:{c:02d}.{m:03d}"
    
def formatar_diferenca_html(td_or_float, unit=""):
    if pd.isna(td_or_float): return "<td></td>"
    value = td_or_float.total_seconds() if isinstance(td_or_float, pd.Timedelta) else td_or_float
    if pd.isna(value): return "<td></td>"
    sinal = "+" if value > 0 else ""
    classe = "diff-pos" if value > 0 else "diff-neg"
    icone = "▲" if value > 0 else "▼"
    if value == 0: return f"<td>0.000 {unit}</td>"
    return f"<td class='{classe}'>{sinal}{value:.3f} {icone} {unit}</td>"

def formatar_diff_span(td_or_float, unit=""):
    if pd.isna(td_or_float): return ""
    value = td_or_float.total_seconds() if isinstance(td_or_float, pd.Timedelta) else td_or_float
    if pd.isna(value): return ""
    if value == 0: return f"<span class='diff-zero'>0.000 {unit}</span>"
    sinal = "+" if value > 0 else ""
    classe = "diff-pos" if value > 0 else "diff-neg"
    icone = "▲" if value > 0 else "▼"
    return f"<span class='{classe}'>{sinal}{value:.3f} {icone} {unit}</span>"

def normalizar(df):
    for c in COLS_TEMPO:
        if c in df.columns: df[c] = df[c].apply(parse_tempo)
    if COL_VEL in df.columns:
        df[COL_VEL] = pd.to_numeric(df[COL_VEL].astype(str).str.replace(',', '.'), errors='coerce')
    return df

def ler_csv_auto(src, filename=""):
    local_nome, evento_nome = "Desconhecido", "Sessão Desconhecida"
    if filename:
        base = os.path.basename(filename).upper().replace('- LAPTIMES.CSV', '').replace('.CSV', '').strip()
        parts = base.split(' - ')
        if len(parts) > 1:
            local_nome, evento_nome = parts[0].strip(), ' - '.join(parts[1:]).strip()
        else:
            evento_nome = parts[0].strip()
    try:
        df = pd.read_csv(src, sep=';', encoding='windows-1252', low_memory=False)
        if COL_PILOTO in df.columns and COL_VOLTA in df.columns:
            df[COL_LOCAL], df[COL_EVENTO] = local_nome, evento_nome
            return normalizar(df)
    except Exception: pass
    raw = src.getvalue().decode("utf-8", "ignore") if hasattr(src, "getvalue") else open(src, "r", encoding="utf-8", errors="ignore").read()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    try:
        hdr_index = next(i for i, l in enumerate(lines) if "Lap Tm" in l and "Lap" in l)
        df_alt = pd.read_csv(StringIO("\n".join(lines[hdr_index:])), sep=',', quotechar='"', engine='python')
        hora_pat = re.compile(r"^\d{1,2}:\d{2}:\d{2}\.\d{1,3}$")
        col_hora = next(c for c in df_alt.columns if df_alt[c].astype(str).str.match(hora_pat).sum() > 0)
        df_alt["Piloto_tmp"] = df_alt[col_hora].where(~df_alt[col_hora].str.match(hora_pat, na=False)).ffill()
        df_alt = df_alt.dropna(subset=['Lap', 'Lap Tm'])
        df_map = pd.DataFrame({
            COL_LOCAL: local_nome, COL_EVENTO: evento_nome, COL_CAT: "N/A", COL_PILOTO: df_alt["Piloto_tmp"],
            "Horário": df_alt[col_hora], COL_VOLTA: df_alt["Lap"], COL_TT: df_alt["Lap Tm"], COL_S1: df_alt.get("S1 Tm"),
            COL_S2: df_alt.get("S2 Tm"), COL_S3: df_alt.get("S3 Tm"), COL_VEL: df_alt.get("Speed"),
        })
        return normalizar(df_map)
    except (StopIteration, ValueError, KeyError): return pd.DataFrame()

# --- FUNÇÃO PRINCIPAL DA APLICAÇÃO (MODIFICADA) ---
def main_app():
    st.title("🏎️ Plataforma de Cronometragem Multi-Sessão")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    PASTA_ETAPAS = "etapas_salvas"
    PASTA_MAPAS = "mapas"
    os.makedirs(PASTA_ETAPAS, exist_ok=True)
    os.makedirs(PASTA_MAPAS, exist_ok=True)
    
    df_completo = pd.DataFrame()
    
    # ===== FERRAMENTA DE CONSOLIDAÇÃO (PARA USO LOCAL COM PRÉ-VISUALIZAÇÃO) =====
    with st.sidebar.expander("⚙️ Ferramenta de Consolidação (Uso Local)"):
        st.info("Carregue múltiplos arquivos para pré-visualizar e depois salvar como uma etapa única.")
        uploaded_files = st.file_uploader("Carregar múltiplos arquivos CSV", type="csv", accept_multiple_files=True)
        
        # Se houver arquivos carregados, eles têm prioridade para visualização
        if uploaded_files:
            st.info("Modo de Pré-visualização: Analisando arquivos recém-carregados.")
            dfs_novos = [ler_csv_auto(f, filename=f.name) for f in uploaded_files]
            df_completo = pd.concat(dfs_novos, ignore_index=True)

            nome_consolidado = st.text_input("Nome do arquivo consolidado final:", "Etapa_Consolidada.csv")
            if st.button("Salvar Etapa Consolidada"):
                if nome_consolidado:
                    caminho_salvar = os.path.join(PASTA_ETAPAS, nome_consolidado)
                    # Salva o mesmo dataframe que está sendo pré-visualizado
                    df_completo.to_csv(caminho_salvar, sep=';', index=False, encoding='utf-8-sig')
                    st.success(f"Arquivo '{nome_consolidado}' salvo na pasta '{PASTA_ETAPAS}'!")
                else:
                    st.warning("Por favor, defina um nome para o arquivo consolidado.")

    # ===== LÓGICA PRINCIPAL PARA ANÁLISE (LÊ DA PASTA SE NÃO HOUVER PRÉ-VISUALIZAÇÃO) =====
    st.sidebar.header("📁 Selecionar Etapa para Análise")

    @st.cache_data
    def carregar_dados_da_pasta(caminho_do_arquivo):
        return ler_csv_auto(caminho_do_arquivo, filename=os.path.basename(caminho_do_arquivo))

    try:
        arquivos_disponiveis = [f for f in os.listdir(PASTA_ETAPAS) if f.lower().endswith('.csv')]
        if not arquivos_disponiveis:
            st.sidebar.warning(f"Nenhum arquivo .csv encontrado na pasta '{PASTA_ETAPAS}'.")
        
        opcoes = ["-- Escolha uma etapa --"] + sorted(arquivos_disponiveis)
        arquivo_selecionado = st.sidebar.selectbox("Etapas salvas disponíveis:", opcoes)

        # Só carrega do arquivo salvo se NENHUM arquivo estiver sendo pré-visualizado
        if not uploaded_files and arquivo_selecionado != "-- Escolha uma etapa --":
            caminho_completo = os.path.join(PASTA_ETAPAS, arquivo_selecionado)
            with st.spinner(f"Carregando dados de '{arquivo_selecionado}'..."):
                df_completo = carregar_dados_da_pasta(caminho_completo)
            st.sidebar.success(f"Analisando: {arquivo_selecionado}")

    except FileNotFoundError:
        st.error(f"ERRO: A pasta '{PASTA_ETAPAS}' não foi encontrada. Crie-a no seu projeto.")
        st.stop()

    # Se, após tudo, o dataframe estiver vazio, mostra a mensagem inicial
    if df_completo.empty:
        st.info("⬅️ Selecione uma etapa salva ou carregue novos arquivos para começar a análise.")
        st.stop()
        
    # ===== SEU CÓDIGO DE FILTROS E ANÁLISE (ORIGINAL E SEM ALTERAÇÕES) =====
    # A partir daqui, seu código original continua igual, pois ele só depende do `df_completo`
    MAPA_PILOTO = None
    # ... (O restante do seu código, desde MAPA_PILOTO até o final das abas, continua exatamente igual)
    # ... cole seu código de análise aqui ...
    for ext in (".csv", ".xlsx"):
        f = f"pilotos_categoria{ext}"
        if os.path.exists(f): MAPA_PILOTO = f; break
    if MAPA_PILOTO:
        try:
            mapa = pd.read_excel(MAPA_PILOTO) if MAPA_PILOTO.endswith(".xlsx") else pd.read_csv(MAPA_PILOTO, sep=';', encoding='windows-1252')
            mapa[COL_PILOTO] = mapa[COL_PILOTO].str.strip()
            mapa[COL_CAT] = mapa[COL_CAT].str.strip()
            df_completo = df_completo.drop(columns=[COL_CAT], errors="ignore").merge(mapa[[COL_PILOTO, COL_CAT]], on=COL_PILOTO, how='left')
            df_completo[COL_CAT].fillna("NÃO CADASTRADO", inplace=True)
        except Exception as e: st.error(f"Erro ao ler ou mesclar o arquivo de categorias '{MAPA_PILOTO}': {e}")
    else: df_completo[COL_CAT] = "NÃO CADASTRADO"

    st.sidebar.header("🔍 Filtros da Etapa")
    df_final, pilotos_selecionados = pd.DataFrame(), []
    locais_disponiveis = sorted(df_completo[COL_LOCAL].dropna().unique())
    loc_selecionado = st.sidebar.selectbox("Local", locais_disponiveis, index=0 if locais_disponiveis else None)
    if loc_selecionado:
        df_filtrado_loc = df_completo[df_completo[COL_LOCAL] == loc_selecionado]
        eventos_disponiveis = sorted(df_filtrado_loc[COL_EVENTO].dropna().unique())
        ev_selecionado = st.sidebar.selectbox("Evento / Sessão", eventos_disponiveis, index=0 if eventos_disponiveis else None)
        if ev_selecionado:
            df_filtrado_ev = df_filtrado_loc[df_filtrado_loc[COL_EVENTO] == ev_selecionado]
            categorias_disponiveis = sorted(df_filtrado_ev[COL_CAT].dropna().unique())
            if not categorias_disponiveis: st.sidebar.warning(f"Nenhuma categoria encontrada para o evento '{ev_selecionado}'.")
            cats_selecionadas = st.sidebar.multiselect("Categorias", categorias_disponiveis, default=categorias_disponiveis)
            df = df_filtrado_ev[df_filtrado_ev[COL_CAT].isin(cats_selecionadas)]
            
            EXTS_MAPA = (".png", ".jpg", ".jpeg", ".svg", ".gif")
            mapas_disp = [f for f in os.listdir(PASTA_MAPAS) if f.lower().endswith(EXTS_MAPA)]
            default_map = "— nenhum —"
            mapa_encontrado = next((f for f in mapas_disp if os.path.splitext(f)[0].lower() == loc_selecionado.lower()), None)
            if mapa_encontrado: default_map = mapa_encontrado
            opcoes_mapa = ["— nenhum —"] + mapas_disp
            map_select = st.sidebar.selectbox("🗺️ Escolher mapa", opcoes_mapa, index=opcoes_mapa.index(default_map))
            if map_select != "— nenhum —": st.sidebar.image(os.path.join(PASTA_MAPAS, map_select), use_container_width=True)
            
            pilotos_disponiveis = sorted(df[COL_PILOTO].dropna().unique())
            pilotos_selecionados = st.sidebar.multiselect("Pilotos", pilotos_disponiveis, default=pilotos_disponiveis[:5])
            df_final = df[df[COL_PILOTO].isin(pilotos_selecionados)]
            
            if not df_final.empty:
                voltas = sorted(df_final[COL_VOLTA].dropna().unique())
                voltas_selecionadas = st.sidebar.multiselect("Voltas", voltas, default=voltas)
                df_final = df_final[df_final[COL_VOLTA].isin(voltas_selecionadas)].reset_index(drop=True)

    best_lap = df_final[COL_TT].min() if not df_final.empty and COL_TT in df_final else None
    best_spd = df_final[COL_VEL].max() if not df_final.empty and COL_VEL in df_final else None
    best_sec = {}
    if not df_final.empty:
        for sec in [COL_S1, COL_S2, COL_S3]:
            if sec in df_final.columns and not df_final[sec].dropna().empty: best_sec[sec] = df_final[sec].min()

    st.header(f"Análise: {loc_selecionado} - {ev_selecionado if 'ev_selecionado' in locals() and ev_selecionado else ''}")
    tab_titles = ["Geral", "Volta Rápida", "Velocidade", "Gráficos", "Comparativo Visual", "Histórico", "Exportar"]
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        st.subheader("📋 Tabela Completa de Voltas")
        if not df_final.empty:
            cols_to_show = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
            cols_existentes = [col for col in cols_to_show if col in df_final.columns]
            show_df = df_final[cols_existentes].copy()
            for c in COLS_TEMPO:
                if c in show_df.columns: show_df[c] = show_df[c].apply(fmt_tempo)
            def sty_all(row):
                original_row = df_final.loc[row.name]
                styles = pd.Series('', index=row.index)
                if best_lap and COL_TT in original_row and pd.notna(original_row[COL_TT]) and original_row[COL_TT] == best_lap: styles[COL_TT] = 'color: #00BFFF; font-weight: bold;'
                for sec_col in [COL_S1, COL_S2, COL_S3]:
                    if sec_col in original_row and sec_col in best_sec and pd.notna(original_row[sec_col]) and original_row[sec_col] == best_sec[sec_col]: styles[sec_col] = 'background-color: #483D8B; color: white;'
                if best_spd and COL_VEL in original_row and pd.notna(original_row[COL_VEL]) and original_row[COL_VEL] == best_spd: styles[COL_VEL] = 'background-color: #2E8B57; color: white;'
                return styles
            st.dataframe(show_df.style.apply(sty_all, axis=1), hide_index=True, use_container_width=True)
        else: st.info("Nenhum dado para exibir. Verifique os filtros selecionados.")
        st.markdown("---")
        st.subheader("🗺️ Mapa da Pista")
        if 'map_select' in locals() and map_select != "— nenhum —":
            map_path = os.path.join(PASTA_MAPAS, map_select)
            if os.path.exists(map_path): st.image(map_path, use_container_width=True)
            else: st.warning(f"Arquivo do mapa '{map_select}' não encontrado na pasta '{PASTA_MAPAS}'.")
        else: st.info("Selecione um mapa na barra lateral para exibi-lo aqui.")

    with tabs[1]:
        st.subheader("🏆 Melhor Volta de Cada Piloto")
        if not df_final.empty and COL_TT in df_final and not df_final[COL_TT].dropna().empty:
            df_best = df_final.loc[df_final.groupby(COL_PILOTO)[COL_TT].idxmin()]
            cols_to_show_best = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
            best_df = df_best[[col for col in cols_to_show_best if col in df_best.columns]].copy().sort_values(by=COL_TT)
            for c in COLS_TEMPO:
                if c in best_df.columns: best_df[c] = best_df[c].apply(fmt_tempo)
            st.dataframe(best_df, hide_index=True, use_container_width=True)
        else: st.info("Não há dados de tempo de volta disponíveis para os pilotos selecionados.")

    with tabs[2]:
        st.subheader("🚀 Maior Top Speed de Cada Piloto")
        if not df_final.empty and COL_VEL in df_final and not df_final[COL_VEL].dropna().empty:
            df_sorted = df_final.sort_values(by=COL_VEL, ascending=False).dropna(subset=[COL_VEL])
            sp_df = df_sorted.drop_duplicates(subset=[COL_PILOTO], keep='first')
            cols_to_show_sp = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA, COL_VEL] + COLS_TEMPO
            sp_df = sp_df[[col for col in cols_to_show_sp if col in sp_df.columns]]
            for c in COLS_TEMPO:
                if c in sp_df.columns: sp_df[c] = sp_df[c].apply(fmt_tempo)
            st.dataframe(sp_df, hide_index=True, use_container_width=True)
        else: st.info("Não há dados de velocidade disponíveis para os pilotos e voltas selecionados.")

    with tabs[3]:
        st.header("📈 Análises Gráficas")
        if df_final.empty or len(pilotos_selecionados) == 0: st.warning("Selecione pilotos para visualizar os gráficos.")
        else:
            if COL_TT in df_final.columns and not df_final[COL_TT].dropna().empty:
                st.subheader("Comparativo de Tempo por Volta")
                fig, ax = plt.subplots(figsize=(10, 5))
                for p in pilotos_selecionados:
                    g = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
                    g_plot = g.dropna(subset=[COL_TT])
                    if not g_plot.empty: ax.plot(g_plot[COL_VOLTA], g_plot[COL_TT].dt.total_seconds(), marker='o', markersize=4, linestyle='-', label=p.split(' - ')[0])
                ax.set_xlabel("Volta"); ax.set_ylabel("Tempo de Volta (M:SS)"); ax.set_title("Desempenho de Tempo de Volta")
                ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda s, pos: f'{int(s // 60)}:{int(s % 60):02d}'))
                ax.grid(True, linestyle='--', alpha=0.6); ax.legend()
                st.pyplot(fig, use_container_width=True)
                st.markdown("---")
            if COL_VEL in df_final.columns and not df_final[COL_VEL].dropna().empty:
                st.subheader("Comparativo de Top Speed por Volta")
                fig1, ax1 = plt.subplots(figsize=(10, 5))
                for p in pilotos_selecionados:
                    g = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
                    g_plot = g.dropna(subset=[COL_VEL])
                    if not g_plot.empty: ax1.plot(g_plot[COL_VOLTA], g_plot[COL_VEL], marker='s', markersize=4, linestyle='--', label=p.split(' - ')[0])
                ax1.set_xlabel("Volta"); ax1.set_ylabel("Velocidade (km/h)"); ax1.set_title("Desempenho de Top Speed por Volta")
                ax1.grid(True, linestyle='--', alpha=0.6); ax1.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=10)); ax1.legend()
                st.pyplot(fig1, use_container_width=True)

    with tabs[4]:
        st.subheader("📊 Comparativo Visual")
        # ... (seu código original de comparativo visual) ...
    with tabs[5]:
        st.subheader("🗂️ Histórico de Etapas Salvas")
        files_in_folder = sorted(os.listdir(PASTA_ETAPAS))
        if files_in_folder: st.dataframe(pd.DataFrame(files_in_folder, columns=["Arquivo"]), hide_index=True)
        else: st.info("Nenhum arquivo de etapa salvo.")

    with tabs[6]:
        st.subheader("📤 Exportar dados filtrados")
        # ... (seu código original de exportação) ...


# --- PONTO DE ENTRADA PRINCIPAL ---
if check_password():
    main_app()