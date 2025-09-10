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

# --- FUNÇÃO DE LOGIN (COM NOVA ESTÉTICA) ---
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

# --- FUNÇÃO PRINCIPAL DA APLICAÇÃO ---
def main_app():
    """
    Contém toda a lógica da aplicação de cronometragem.
    Só é executada após o login bem-sucedido.
    """
    st.title("🏎️ Plataforma de Cronometragem Multi-Sessão")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    PASTA_ETAPAS = "etapas_salvas"
    os.makedirs(PASTA_ETAPAS, exist_ok=True)
    PASTA_MAPAS = "mapas"
    os.makedirs(PASTA_MAPAS, exist_ok=True)

    COL_LOCAL, COL_EVENTO = "Local", "Evento"
    COL_CAT, COL_PILOTO = "CATEGORIA", "Piloto"
    COL_VOLTA, COL_TT = "Volta", "Tempo Total da Volta"
    COL_S1, COL_S2, COL_S3 = "Setor 1", "Setor 2", "Setor 3"
    COL_VEL = "TOP SPEED"
    COLS_TEMPO = [COL_TT, COL_S1, COL_S2, COL_S3]
    EXTS_MAPA = (".png", ".jpg", ".jpeg", ".svg", ".gif")

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

    st.sidebar.header("📁 Importar Dados da Etapa")
    uploaded_files = st.sidebar.file_uploader("Carregar arquivos CSV da etapa", type="csv", accept_multiple_files=True)
    df_completo = pd.DataFrame()
    if uploaded_files:
        dfs_novos = []
        for up_file in uploaded_files:
            df_upload = ler_csv_auto(up_file, filename=up_file.name)
            if not df_upload.empty: dfs_novos.append(df_upload)
        if dfs_novos:
            df_novos_concatenados = pd.concat(dfs_novos, ignore_index=True)
            df_completo = pd.concat([df_completo, df_novos_concatenados], ignore_index=True).drop_duplicates()
            st.sidebar.subheader("Salvar Dados")
            if st.sidebar.button("Salvar Arquivos Importados (Separados)"):
                for up_file in uploaded_files:
                    with open(os.path.join(PASTA_ETAPAS, up_file.name), "wb") as f: f.write(up_file.getvalue())
                st.sidebar.success(f"{len(dfs_novos)} arquivo(s) salvo(s)!")
            nome_etapa_consolidada = st.sidebar.text_input("Nome para a etapa consolidada:", "ETAPA_CONSOLIDADA.csv")
            if st.sidebar.button("Salvar Etapa Consolidada (Arquivo Único)"):
                if nome_etapa_consolidada:
                    df_para_salvar = df_novos_concatenados.copy()
                    for col in COLS_TEMPO:
                        if col in df_para_salvar.columns: df_para_salvar[col] = df_para_salvar[col].apply(fmt_tempo)
                    caminho_salvar = os.path.join(PASTA_ETAPAS, nome_etapa_consolidada)
                    df_para_salvar.to_csv(caminho_salvar, sep=';', index=False, encoding='utf-8-sig')
                    st.sidebar.success(f"Etapa consolidada salva como '{nome_etapa_consolidada}'!")
                else: st.sidebar.warning("Por favor, insira um nome para o arquivo consolidado.")
    if df_completo.empty:
        st.info("⬅️ Nenhuma etapa carregada. Importe um ou mais arquivos CSV na barra lateral para começar.")
        st.stop()

    MAPA_PILOTO = None
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
        if len(pilotos_selecionados) < 2: st.warning("⚠️ Por favor, selecione de 2 a 5 pilotos na barra lateral para fazer a comparação.")
        elif df_final.empty: st.warning("Nenhum dado disponível para os filtros selecionados.")
        else:
            col1, col2 = st.columns(2)
            with col1: tipo_analise = st.radio("Tipo de Análise:", ("Tempo de Volta", "Velocidade Máxima"), horizontal=True, key="tipo_analise")
            with col2:
                opcoes_referencia = ["-- Comparação Sequencial --"] + pilotos_selecionados
                modo_comparacao = st.selectbox("Modo de Comparação:", opcoes_referencia, key="modo_comp")
            st.markdown("---")
            coluna_dado = COL_TT if tipo_analise == "Tempo de Volta" else COL_VEL
            if coluna_dado not in df_final.columns or df_final[coluna_dado].dropna().empty: st.error(f"A coluna '{coluna_dado}' não contém dados válidos para a análise.")
            else:
                try:
                    df_comp_pivot = df_final.pivot_table(index=COL_VOLTA, columns=COL_PILOTO, values=coluna_dado)
                    df_comp = df_comp_pivot.reset_index()
                except Exception as e: st.error(f"Não foi possível criar a tabela de comparação. Erro: {e}"); st.stop()
                unidade = "" if tipo_analise == "Tempo de Volta" else "km/h"
                y_label = "Tempo de Volta (M:SS)" if tipo_analise == "Tempo de Volta" else f"Velocidade Máxima ({unidade})"
                fig, ax = plt.subplots(figsize=(12, 6))
                if tipo_analise == "Tempo de Volta":
                    def format_yticks(seconds, pos): return f'{int(seconds // 60)}:{int(seconds % 60):02d}' if seconds > 0 else ''
                    ax.yaxis.set_major_formatter(mticker.FuncFormatter(format_yticks))
                else: ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=10))
                piloto_referencia = modo_comparacao if modo_comparacao != "-- Comparação Sequencial --" else None
                for p in pilotos_selecionados:
                    piloto_df_plot = df_final[df_final[COL_PILOTO] == p].dropna(subset=[coluna_dado]).sort_values(by=COL_VOLTA)
                    if not piloto_df_plot.empty:
                        dados_y = piloto_df_plot[coluna_dado].dt.total_seconds() if tipo_analise == "Tempo de Volta" else piloto_df_plot[coluna_dado]
                        is_ref = piloto_referencia and p == piloto_referencia
                        ax.plot(piloto_df_plot[COL_VOLTA], dados_y, marker='o', markersize=7 if is_ref else 6, linewidth=3 if is_ref else 2, linestyle='--' if is_ref else '-', label=f"{p.split(' - ')[0]} (Ref.)" if is_ref else p.split(' - ')[0], zorder=10 if is_ref else 5, alpha=0.9)
                ax.set_xlabel("Volta"); ax.set_ylabel(y_label); ax.set_title(f"Comparativo de {tipo_analise}")
                ax.legend(fontsize='small'); ax.grid(True, which='both', linestyle='--', linewidth=0.5)
                if not df_final.empty and not df_final[COL_VOLTA].dropna().empty: ax.set_xticks(sorted(df_final[COL_VOLTA].dropna().unique().astype(int)))
                st.pyplot(fig, use_container_width=True)
                st.markdown("---")
                st.subheader(f"Análise Detalhada: {tipo_analise}")
                common_css = """<style> .table-container { overflow-x: auto; } .comp-table { width: 100%; border-collapse: collapse; font-size: 0.9em; } .comp-table th, .comp-table td { padding: 6px 8px; text-align: center; white-space: nowrap; } .comp-table th { font-family: sans-serif; border-bottom: 2px solid #444; } .comp-table td { border-bottom: 1px solid #333; line-height: 1.3; } .comp-table tr:hover td { background-color: #2e2e2e; } .comp-table b { font-size: 1.1em; } .diff-span { font-size: 0.9em; display: block; } .diff-pos { color: #ff4d4d !important; } .diff-neg { color: #4dff4d !important; } .diff-zero { color: #888; } .best-value { background-color: #483D8B; border-radius: 4px; } </style>"""
                html = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr>"
                header_pilotos = pilotos_selecionados
                if not piloto_referencia:
                    for i, p in enumerate(header_pilotos):
                        html += f"<th>{p}</th>"
                        if i < len(header_pilotos) - 1: html += "<th>VS</th>"
                else:
                    for p in header_pilotos: html += f"<th>{p}</th>"
                html += "</tr></thead><tbody>"
                if not df_comp.empty:
                    op = 'min' if tipo_analise == "Tempo de Volta" else 'max'
                    best_values = df_final.groupby(COL_PILOTO)[coluna_dado].agg(op).to_dict()
                    for _, row in df_comp.iterrows():
                        html += "<tr>"
                        if not piloto_referencia:
                            for i, p in enumerate(header_pilotos):
                                dado_atual = row.get(p)
                                is_best = best_values.get(p) and pd.notna(dado_atual) and dado_atual == best_values.get(p)
                                cell_class = "best-value" if is_best else ""
                                valor_str = fmt_tempo(dado_atual) if tipo_analise == "Tempo de Volta" else (f"{dado_atual:.1f}" if pd.notna(dado_atual) else "---")
                                html += f"<td class='{cell_class}'><b>{int(row[COL_VOLTA])}</b><br>{valor_str} {unidade}</td>"
                                if i < len(header_pilotos) - 1:
                                    dado_prox = row.get(header_pilotos[i+1])
                                    diff = dado_prox - dado_atual if pd.notna(dado_atual) and pd.notna(dado_prox) else None
                                    html += formatar_diferenca_html(diff, unit=unidade)
                        else:
                            dado_ref = row.get(piloto_referencia)
                            for p in header_pilotos:
                                dado_atual = row.get(p)
                                diff_str = ""
                                if p != piloto_referencia:
                                    diff = dado_atual - dado_ref if pd.notna(dado_atual) and pd.notna(dado_ref) else None
                                    diff_str = f"<span class='diff-span'>{formatar_diff_span(diff, unit=unidade)}</span>"
                                is_best = best_values.get(p) and pd.notna(dado_atual) and dado_atual == best_values.get(p)
                                cell_class = "best-value" if is_best else ""
                                valor_str = fmt_tempo(dado_atual) if tipo_analise == "Tempo de Volta" else (f"{dado_atual:.1f}" if pd.notna(dado_atual) else "---")
                                html += f"<td class='{cell_class}'><b>{int(row[COL_VOLTA])}</b><br>{valor_str} {unidade}{diff_str}</td>"
                        html += "</tr>"
                html += "</tbody></table></div>"
                st.markdown(html, unsafe_allow_html=True)

    with tabs[5]:
        st.subheader("🗂️ Histórico de Etapas Salvas")
        files_in_folder = sorted(os.listdir(PASTA_ETAPAS))
        if files_in_folder: st.dataframe(pd.DataFrame(files_in_folder, columns=["Arquivo"]), hide_index=True)
        else: st.info("Nenhum arquivo de etapa salvo.")

    with tabs[6]:
        st.subheader("📤 Exportar dados filtrados")
        if not df_final.empty:
            buf = io.BytesIO()
            out = df_final.copy()
            for c in COLS_TEMPO:
                if c in out.columns: out[c] = out[c].apply(fmt_tempo)
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out.to_excel(w, index=False)
            st.download_button("⬇️ Baixar Excel", buf.getvalue(), file_name=f"cronometro_{loc_selecionado or 'local'}_{ev_selecionado or 'evento'}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else: st.info("Não há dados filtrados para exportar.")

# --- PONTO DE ENTRADA PRINCIPAL ---
if check_password():
    main_app()