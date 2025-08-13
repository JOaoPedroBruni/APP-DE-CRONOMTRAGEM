import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import io
import os
import re
from io import StringIO

# ---------------- Configuração ----------------
st.set_page_config(page_title="Plataforma Cronometragem", layout="wide")
st.title("🏎️ Plataforma de Cronometragem")

PASTA_ETAPAS = "etapas_salvas"; os.makedirs(PASTA_ETAPAS, exist_ok=True)
PASTA_MAPAS = "mapas"; os.makedirs(PASTA_MAPAS, exist_ok=True)

# ---------------- Constantes e Funções (sem alterações) ------------------
COL_LOCAL, COL_EVENTO = "Local", "Evento"
COL_CAT, COL_PILOTO = "CATEGORIA", "Piloto"
COL_VOLTA, COL_TT = "Volta", "Tempo Total da Volta"
COL_S1, COL_S2, COL_S3 = "Setor 1", "Setor 2", "Setor 3"
COL_VEL = "TOP SPEED"; COLS_TEMPO = [COL_TT, COL_S1, COL_S2, COL_S3]
EXTS_MAPA = (".png", ".jpg", ".jpeg", ".svg", ".gif")
def parse_tempo(txt):
    if pd.isna(txt): return pd.NaT
    s = str(txt).strip().replace(',', '.');
    if re.fullmatch(r"\d{1,2}:\d{2}\.\d{1,3}", s): m, r = s.split(':'); return pd.to_timedelta(int(m)*60+float(r),unit='s')
    if re.fullmatch(r"\d{1,3}\.\d{1,3}", s): return pd.to_timedelta(float(s), unit='s')
    return pd.to_timedelta(s, errors='coerce')
def fmt_tempo(td):
    if pd.isna(td) or td is None: return "---"
    s = td.total_seconds(); m = int((s % 1) * 1000); n = int(s // 60); c = int(s % 60); return f"{n:01d}:{c:02d}.{m:03d}"
def formatar_diferenca_html(td_or_float, unit=""):
    if pd.isna(td_or_float): return "<td></td>"
    value = td_or_float.total_seconds() if isinstance(td_or_float, pd.Timedelta) else td_or_float
    if pd.isna(value): return "<td></td>"
    sinal = "+" if value > 0 else ""; classe = "diff-pos" if value > 0 else "diff-neg"; icone = "▲" if value > 0 else "▼"
    if value == 0: return f"<td>0.000 {unit}</td>"
    return f"<td class='{classe}'>{sinal}{value:.3f} {icone} {unit}</td>"
def formatar_diff_span(td_or_float, unit=""):
    if pd.isna(td_or_float): return ""
    value = td_or_float.total_seconds() if isinstance(td_or_float, pd.Timedelta) else td_or_float
    if pd.isna(value): return ""
    if value == 0: return f"<span class='diff-zero'>0.000 {unit}</span>"
    sinal = "+" if value > 0 else ""; classe = "diff-pos" if value > 0 else "diff-neg"; icone = "▲" if value > 0 else "▼"
    return f"<span class='{classe}'>{sinal}{value:.3f} {icone} {unit}</span>"
def normalizar(df):
    for c in COLS_TEMPO:
        if c in df.columns: df[c] = df[c].apply(parse_tempo)
    return df
def ler_csv_auto(src):
    try: df = pd.read_csv(src, sep=';', encoding='windows-1252', low_memory=False)
    except: df = pd.read_csv(src, sep=';', low_memory=False)
    if {COL_PILOTO, COL_VOLTA, COL_S1}.issubset(df.columns): return normalizar(df)
    raw = src.getvalue().decode("utf-8", "ignore") if hasattr(src, "getvalue") else open(src, "r", encoding="utf-8", errors="ignore").read()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    try:
        hdr = next(i for i, l in enumerate(lines) if "Lap Tm" in l and "Lap" in l)
        df_alt = pd.read_csv(StringIO("\n".join(lines[hdr:])), sep=',', quotechar='"', engine='python')
        hora_pat = re.compile(r"^\d{1,2}:\d{2}:\d{2}\.\d{1,3}$")
        col_hora = next(c for c in df_alt.columns if df_alt[c].astype(str).str.match(hora_pat).sum() > 0)
        df_alt["Piloto_tmp"] = df_alt[col_hora].where(~df_alt[col_hora].str.match(hora_pat, na=False)).ffill()
        df_map = pd.DataFrame({
            COL_LOCAL: "Desconhecido", COL_EVENTO: "Sprint Trophy", COL_CAT: "N/A", COL_PILOTO: df_alt["Piloto_tmp"],
            "Horário": df_alt[col_hora], COL_VOLTA: df_alt["Lap"], COL_TT: df_alt["Lap Tm"], COL_S1: df_alt["S1 Tm"],
            COL_S2: df_alt["S2 Tm"], COL_S3: df_alt["S3 Tm"], COL_VEL: df_alt["Speed"],
        })
        return normalizar(df_map)
    except (StopIteration, ValueError):
        st.error(f"Não foi possível processar o arquivo. Formato desconhecido."); return pd.DataFrame()

# ===== LÓGICA DE CARREGAMENTO E FILTRAGEM (sem alterações) =====
st.sidebar.header("📁 Importar Dados") 
up = st.sidebar.file_uploader("Importar novo CSV", type="csv")
dfs_salvos = []
for f in sorted(os.listdir(PASTA_ETAPAS)):
    if f.endswith('.csv'):
        try: dfs_salvos.append(ler_csv_auto(os.path.join(PASTA_ETAPAS, f)))
        except Exception as e: st.warning(f"Não foi possível ler a etapa salva '{f}': {e}")
df_completo = pd.concat(dfs_salvos, ignore_index=True) if dfs_salvos else pd.DataFrame()
if up:
    df_upload = ler_csv_auto(up)
    if st.sidebar.button("Salvar etapa importada"):
        with open(os.path.join(PASTA_ETAPAS, up.name), "wb") as f: f.write(up.getvalue())
        st.sidebar.success("Etapa salva! Recarregando..."); st.rerun()
    df_completo = pd.concat([df_completo, df_upload], ignore_index=True)
if df_completo.empty:
    st.info("Nenhuma etapa de corrida encontrada. Importe um arquivo CSV para começar."); st.stop()
MAPA_PILOTO = None
for ext in (".csv", ".xlsx"):
    f = f"pilotos_categoria{ext}";
    if os.path.exists(f): MAPA_PILOTO = f; break
if MAPA_PILOTO:
    mapa = pd.read_excel(MAPA_PILOTO) if MAPA_PILOTO.endswith(".xlsx") else pd.read_csv(MAPA_PILOTO, sep=';')
    mapa[COL_PILOTO] = mapa[COL_PILOTO].str.strip(); mapa[COL_CAT] = mapa[COL_CAT].str.strip()
    df_completo = df_completo.drop(columns=[COL_CAT], errors="ignore").merge(mapa[[COL_PILOTO, COL_CAT]], on=COL_PILOTO, how="left")
st.sidebar.header("🔍 Filtros")
locais_disponiveis = sorted(df_completo[COL_LOCAL].dropna().unique())
loc_selecionado = st.sidebar.selectbox("Local", locais_disponiveis, index=0 if locais_disponiveis else None)
df_filtrado_loc = df_completo[df_completo[COL_LOCAL] == loc_selecionado]
eventos_disponiveis = sorted(df_filtrado_loc[COL_EVENTO].dropna().unique())
ev_selecionado = st.sidebar.selectbox("Evento", eventos_disponiveis, index=0 if eventos_disponiveis else None)
df_filtrado_ev = df_filtrado_loc[df_filtrado_loc[COL_EVENTO] == ev_selecionado]
categorias_disponiveis = sorted(df_filtrado_ev[COL_CAT].dropna().unique())
cats_selecionadas = st.sidebar.multiselect("Categorias", categorias_disponiveis, default=categorias_disponiveis)
df = df_filtrado_ev[df_filtrado_ev[COL_CAT].isin(cats_selecionadas)]
mapas_disp = [f for f in os.listdir(PASTA_MAPAS) if f.lower().endswith(EXTS_MAPA)]
default_map = next((f for f in mapas_disp if os.path.splitext(f)[0].lower() == loc_selecionado.lower()), "— nenhum —") if loc_selecionado else "— nenhum —"
map_select = st.sidebar.selectbox("🗺️ Escolher mapa", ["— nenhum —"] + mapas_disp, index=(["— nenhum —"] + mapas_disp).index(default_map))
if map_select != "— nenhum —": st.sidebar.image(os.path.join(PASTA_MAPAS, map_select), use_container_width=True)
pil = sorted(df[COL_PILOTO].dropna().unique())
sel_p = st.sidebar.multiselect("Pilotos", pil, default=pil[:5])
df_final = df[df[COL_PILOTO].isin(sel_p)]
if not df_final.empty:
    voltas = sorted(df_final[COL_VOLTA].dropna().unique())
    sel_v = st.sidebar.multiselect("Voltas", voltas, default=voltas)
    df_final = df_final[df_final[COL_VOLTA].isin(sel_v)].reset_index(drop=True)

# ===== ABAS =====
tab_titles = ["Comparativo Visual", "Geral", "Volta Rápida", "Velocidade", "Gráficos", "Histórico", "Exportar"]
tabs = st.tabs(tab_titles)

# ===== ABA "COMPARATIVO VISUAL" - TOTALMENTE REFEITA COM O NOVO SELETOR =====
with tabs[0]:
    st.header("📊 Comparativo Visual de Voltas")
    if len(sel_p) < 2:
        st.warning("⚠️ Por favor, selecione de 2 a 5 pilotos na barra lateral para fazer a comparação."); st.stop()

    # --- NOVOS SELETORES DE ANÁLISE ---
    col1, col2 = st.columns(2)
    with col1:
        tipo_analise = st.radio(
            "Selecione o Tipo de Análise:",
            ("Tempo de Volta", "Velocidade Máxima"),
            horizontal=True, key="tipo_analise"
        )
    with col2:
        opcoes_referencia = ["-- Comparação Sequencial --"] + sel_p
        modo_comparacao = st.selectbox(
            "Selecione o modo de comparação:",
            opcoes_referencia, key="modo_comp"
        )
    st.markdown("---")

    # --- LÓGICA CONDICIONAL PARA O TIPO DE ANÁLISE ---
    
    if tipo_analise == "Tempo de Volta":
        # --- ANÁLISE DE TEMPO DE VOLTA ---
        dados_pilotos = [df_final[df_final[COL_PILOTO] == p][[COL_VOLTA, COL_TT]].set_index(COL_VOLTA).rename(columns={COL_TT: p}) for p in sel_p]
        coluna_dado = COL_TT
        unidade = ""
        y_label = "Tempo de Volta (M:SS)"
    else:
        # --- ANÁLISE DE VELOCIDADE MÁXIMA ---
        dados_pilotos = [df_final[df_final[COL_PILOTO] == p][[COL_VOLTA, COL_VEL]].set_index(COL_VOLTA).rename(columns={COL_VEL: p}) for p in sel_p]
        coluna_dado = COL_VEL
        unidade = "km/h"
        y_label = f"Velocidade Máxima ({unidade})"

    # --- PREPARAÇÃO DE DADOS E GRÁFICO (COMUM A AMBOS) ---
    df_comp = dados_pilotos[0] if dados_pilotos else pd.DataFrame()
    if len(dados_pilotos) > 1:
        for i in range(1, len(dados_pilotos)): df_comp = df_comp.join(dados_pilotos[i], how='outer')
    if not df_comp.empty:
        df_comp = df_comp.sort_index().reset_index()

    fig, ax = plt.subplots(figsize=(12, 6))
    if tipo_analise == "Tempo de Volta":
        def format_yticks(seconds, pos): return f'{int(seconds // 60)}:{int(seconds % 60):02d}'
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(format_yticks))
    
    # --- RENDERIZAÇÃO CONDICIONAL (SEQUENCIAL VS REFERÊNCIA) ---
    piloto_referencia = modo_comparacao if modo_comparacao != "-- Comparação Sequencial --" else None
    
    for p in sel_p:
        piloto_df_plot = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
        dados_y = piloto_df_plot[coluna_dado].dt.total_seconds() if tipo_analise == "Tempo de Volta" else piloto_df_plot[coluna_dado]
        
        if piloto_referencia and p == piloto_referencia:
            ax.plot(piloto_df_plot[COL_VOLTA], dados_y, marker='o', markersize=7, linewidth=3, linestyle='--', label=f"{p} (Ref.)", zorder=10)
        else:
            ax.plot(piloto_df_plot[COL_VOLTA], dados_y, marker='o', markersize=6, linewidth=2, label=p, alpha=0.8)

    ax.set_xlabel("Volta"); ax.set_ylabel(y_label); ax.set_title(f"Comparativo de {tipo_analise}")
    ax.legend(fontsize='small'); ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    if not df_final.empty: ax.set_xticks(sorted(df_final[COL_VOLTA].dropna().unique().astype(int)))
    st.pyplot(fig, use_container_width=True)
    st.markdown("---")

    # --- TABELA DE COMPARAÇÃO (COMUM A AMBOS) ---
    st.subheader(f"Análise Detalhada: {tipo_analise}")
    common_css = """<style> .table-container { overflow-x: auto; } .comp-table { width: 100%; border-collapse: collapse; font-size: 0.9em; } .comp-table th, .comp-table td { padding: 6px 8px; text-align: center; white-space: nowrap; } .comp-table th { font-family: sans-serif; border-bottom: 2px solid #444; } .comp-table td { border-bottom: 1px solid #333; line-height: 1.3; } .comp-table tr:hover td { background-color: #2e2e2e; } .comp-table b { font-size: 1.1em; } .diff-span { font-size: 0.9em; display: block; } .diff-pos { color: #ff4d4d; } .diff-neg { color: #4dff4d; } .diff-zero { color: #888; } .fastest-lap { background-color: #483D8B; border-radius: 4px; } </style>"""
    html = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr>"

    if not piloto_referencia: # Modo Sequencial
        for i, p in enumerate(sel_p):
            html += f"<th>{p}</th>"
            if i < len(sel_p) - 1: html += "<th>VS</th>"
    else: # Modo Referência
        for p in sel_p: html += f"<th>{p}</th>"
    html += "</tr></thead><tbody>"

    if not df_comp.empty:
        fastest_laps = {p: df_final[df_final[COL_PILOTO] == p][coluna_dado].min() for p in sel_p if not df_final[df_final[COL_PILOTO] == p].empty}
        for _, row in df_comp.iterrows():
            html += "<tr>"
            if not piloto_referencia: # Modo Sequencial
                for i, p in enumerate(sel_p):
                    dado_atual = row.get(p)
                    is_fastest = fastest_laps.get(p) and dado_atual == fastest_laps.get(p)
                    cell_class = "fastest-lap" if is_fastest and tipo_analise == "Tempo de Volta" else ""
                    valor_str = fmt_tempo(dado_atual) if tipo_analise == "Tempo de Volta" else f"{dado_atual:.1f}"
                    html += f"<td class='{cell_class}'><b>{row[COL_VOLTA]}</b><br>{valor_str} {unidade}</td>"
                    if i < len(sel_p) - 1:
                        dado_prox = row.get(sel_p[i+1])
                        diff = dado_prox - dado_atual if pd.notna(dado_atual) and pd.notna(dado_prox) else None
                        html += formatar_diferenca_html(diff, unit="" if tipo_analise == "Tempo de Volta" else "km/h")
            else: # Modo Referência
                dado_ref = row.get(piloto_referencia)
                for p in sel_p:
                    dado_atual = row.get(p); diff_str = ""
                    if p != piloto_referencia:
                        diff = dado_atual - dado_ref if pd.notna(dado_atual) and pd.notna(dado_ref) else None
                        diff_str = f"<span class='diff-span'>{formatar_diff_span(diff, unit='' if tipo_analise == 'Tempo de Volta' else 'km/h')}</span>"
                    is_fastest = fastest_laps.get(p) and dado_atual == fastest_laps.get(p)
                    cell_class = "fastest-lap" if is_fastest and tipo_analise == "Tempo de Volta" else ""
                    valor_str = fmt_tempo(dado_atual) if tipo_analise == "Tempo de Volta" else f"{dado_atual:.1f}"
                    html += f"<td class='{cell_class}'><b>{row[COL_VOLTA]}</b><br>{valor_str} {unidade}{diff_str}</td>"
            html += "</tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)
# ... (código das outras abas sem alteração) ...
with tabs[1]:
    st.subheader("📋 Tabela Completa de Voltas")
    cols_to_show = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
    show = df_final[cols_to_show].copy()
    for c in COLS_TEMPO: show[c] = show[c].apply(fmt_tempo)
    st.dataframe(show, hide_index=True, use_container_width=True)
with tabs[2]:
    st.subheader("🏆 Melhor Volta de Cada Piloto")
    if not df_final.empty and COL_PILOTO in df_final and COL_TT in df_final:
        idx_best = df_final.loc[df_final.groupby(COL_PILOTO)[COL_TT].idxmin()]
        cols_to_show_best = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
        best_df = idx_best[cols_to_show_best].copy().sort_values(by=COL_TT)
        for c in COLS_TEMPO: best_df[c] = best_df[c].apply(fmt_tempo)
        st.dataframe(best_df, hide_index=True, use_container_width=True)
with tabs[3]:
    st.subheader("🚀 Maior Top Speed de Cada Piloto")
    if not df_final.empty and COL_PILOTO in df_final and COL_VEL in df_final:
        idx_sp = df_final.loc[df_final.groupby(COL_PILOTO)[COL_VEL].idxmax()]; sp_df = idx_sp[[COL_PILOTO, COL_CAT, "Horário", COL_VOLTA, COL_VEL] + COLS_TEMPO].copy().sort_values(by=COL_VEL, ascending=False)
        for c in COLS_TEMPO: sp_df[c] = sp_df[c].apply(fmt_tempo); st.dataframe(sp_df, hide_index=True, use_container_width=True)
with tabs[4]:
    st.header("📈 Análises Gráficas Adicionais")
    if df_final.empty or len(sel_p) == 0:
        st.warning("Selecione pilotos para visualizar os gráficos."); st.stop()
    st.subheader("Velocidade Máxima por Volta")
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    for p in sel_p:
        g = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
        if not g.empty and COL_VEL in g.columns:
            ax1.plot(g[COL_VOLTA], g[COL_VEL], marker='s', markersize=4, linestyle='--', label=p.split(' - ')[0])
    ax1.set_xlabel("Volta"); ax1.set_ylabel("Velocidade (km/h)"); ax1.set_title("Comparativo de Top Speed por Volta")
    ax1.grid(True, linestyle='--', alpha=0.6); ax1.legend()
    st.pyplot(fig1, use_container_width=True)
    st.markdown("---")
    st.subheader("Consistência dos Tempos de Volta (Desvio Padrão)")
    consistencia = {}
    for p in sel_p:
        tempos_s = df_final[df_final[COL_PILOTO] == p][COL_TT].dt.total_seconds().dropna()
        q1, q3 = tempos_s.quantile(0.25), tempos_s.quantile(0.75); iqr = q3 - q1
        limite_inferior = q1 - 1.5 * iqr; limite_superior = q3 + 1.5 * iqr
        tempos_filtrados = tempos_s[(tempos_s >= limite_inferior) & (tempos_s <= limite_superior)]
        if not tempos_filtrados.empty: consistencia[p] = tempos_filtrados.std()
    if consistencia:
        pilotos_nomes = [p.split(' - ')[0] for p in consistencia.keys()]
        valores_std = list(consistencia.values())
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        bars = ax2.bar(pilotos_nomes, valores_std, color='skyblue')
        ax2.set_ylabel("Desvio Padrão (em segundos)"); ax2.set_title("Menor a barra, mais consistente o piloto")
        ax2.bar_label(bars, fmt='%.3f')
        st.pyplot(fig2, use_container_width=True)
    else: st.info("Não há dados suficientes para calcular a consistência.")
    st.markdown("---")
    st.subheader("Análise de Setores da Melhor Volta")
    try:
        idx_melhores_voltas = df_final.groupby(COL_PILOTO)[COL_TT].idxmin()
        df_melhores_voltas = df_final.loc[idx_melhores_voltas].dropna(subset=[COL_S1, COL_S2, COL_S3])
        if not df_melhores_voltas.empty:
            pilotos_nomes = [p.split(' - ')[0] for p in df_melhores_voltas[COL_PILOTO]]
            s1 = df_melhores_voltas[COL_S1].dt.total_seconds(); s2 = df_melhores_voltas[COL_S2].dt.total_seconds(); s3 = df_melhores_voltas[COL_S3].dt.total_seconds()
            fig3, ax3 = plt.subplots(figsize=(10, 5))
            ax3.bar(pilotos_nomes, s1, label='Setor 1', color='#1f77b4'); ax3.bar(pilotos_nomes, s2, bottom=s1, label='Setor 2', color='#ff7f0e'); ax3.bar(pilotos_nomes, s3, bottom=s1+s2, label='Setor 3', color='#2ca02c')
            ax3.set_ylabel("Tempo da volta (segundos)"); ax3.set_title("Composição da Melhor Volta por Setores"); ax3.legend()
            st.pyplot(fig3, use_container_width=True)
        else: st.info("Não há dados de setores para a melhor volta dos pilotos selecionados.")
    except KeyError: st.error("Colunas de setores (Setor 1, Setor 2, Setor 3) não encontradas nos dados.")
with tabs[5]:
    st.subheader("🗂️ Etapas Salvas"); files_in_folder = sorted(os.listdir(PASTA_ETAPAS))
    st.dataframe(pd.DataFrame(files_in_folder, columns=["Arquivo"]), hide_index=True)
with tabs[6]:
    st.subheader("📤 Exportar dados filtrados"); buf = io.BytesIO(); out = df_final.copy();
    for c in COLS_TEMPO: out[c] = out[c].apply(fmt_tempo)
    with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out.to_excel(w, index=False)
    st.download_button("⬇️ Baixar Excel", buf.getvalue(), file_name=f"cronometro_{loc_selecionado}_{ev_selecionado}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")