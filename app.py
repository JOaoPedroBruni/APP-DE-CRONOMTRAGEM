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

# ---------------- Constantes ------------------
COL_LOCAL, COL_EVENTO = "Local", "Evento"
COL_CAT, COL_PILOTO = "CATEGORIA", "Piloto"
COL_VOLTA, COL_TT = "Volta", "Tempo Total da Volta"
COL_S1, COL_S2, COL_S3 = "Setor 1", "Setor 2", "Setor 3"
COL_VEL = "TOP SPEED"; COLS_TEMPO = [COL_TT, COL_S1, COL_S2, COL_S3]
EXTS_MAPA = (".png", ".jpg", ".jpeg", ".svg", ".gif")

# ---------------- Funções tempo ----------------
def parse_tempo(txt):
    if pd.isna(txt): return pd.NaT
    s = str(txt).strip().replace(',', '.');
    if re.fullmatch(r"\d{1,2}:\d{2}\.\d{1,3}", s): m, r = s.split(':'); return pd.to_timedelta(int(m)*60+float(r),unit='s')
    if re.fullmatch(r"\d{1,3}\.\d{1,3}", s): return pd.to_timedelta(float(s), unit='s')
    return pd.to_timedelta(s, errors='coerce')

def fmt_tempo(td):
    if pd.isna(td) or td is None: return "---"
    s = td.total_seconds(); m = int((s % 1) * 1000); n = int(s // 60); c = int(s % 60); return f"{n:01d}:{c:02d}.{m:03d}"

def formatar_diferenca_html_sequencial(td):
    if pd.isna(td) or td is None: return "<td></td>"
    s = td.total_seconds()
    sinal = "+" if s > 0 else ""; classe = "diff-pos" if s > 0 else "diff-neg"; icone = "▲" if s > 0 else "▼"
    if s == 0: return "<td>0.000</td>"
    return f"<td class='{classe}'>{sinal}{s:.3f} {icone}</td>"

def formatar_diff_span_referencia(td):
    if pd.isna(td) or td is None: return ""
    s = td.total_seconds()
    if s == 0: return f"<span class='diff-zero'>0.000</span>"
    sinal = "+" if s > 0 else ""; classe = "diff-pos" if s > 0 else "diff-neg"; icone = "▲" if s > 0 else "▼"
    return f"<span class='{classe}'>{sinal}{s:.3f} {icone}</span>"

def normalizar(df):
    for c in COLS_TEMPO:
        if c in df.columns: df[c] = df[c].apply(parse_tempo)
    return df

def ler_csv_auto(src):
    try: df = pd.read_csv(src, sep=';', encoding='windows-1252')
    except: df = pd.read_csv(src, sep=';')
    if {COL_PILOTO, COL_VOLTA, COL_S1}.issubset(df.columns): return normalizar(df)
    raw = src.getvalue().decode("utf-8", "ignore") if hasattr(src, "getvalue") else open(src, "r", encoding="utf-8", errors="ignore").read()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
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

st.sidebar.header("📁 Importar"); up = st.sidebar.file_uploader("CSV", type="csv"); files = sorted(os.listdir(PASTA_ETAPAS)); sel = st.sidebar.selectbox("Etapas salvas:", ["---"] + files)
df = ler_csv_auto(up) if up else ler_csv_auto(os.path.join(PASTA_ETAPAS, sel)) if sel != "---" else None
if up and df is not None and st.sidebar.button("Salvar etapa"):
    with open(os.path.join(PASTA_ETAPAS, up.name), "wb") as f: f.write(up.getbuffer()); st.sidebar.success("Etapa salva!")
if df is None: st.info("📤 Importe um CSV ou escolha uma etapa salva na barra lateral."); st.stop()

MAPA_PILOTO = None
for ext in (".csv", ".xlsx"):
    f = f"pilotos_categoria{ext}"
    if os.path.exists(f): MAPA_PILOTO = f; break
if MAPA_PILOTO:
    mapa = pd.read_excel(MAPA_PILOTO) if MAPA_PILOTO.endswith(".xlsx") else pd.read_csv(MAPA_PILOTO, sep=';')
    mapa[COL_PILOTO] = mapa[COL_PILOTO].str.strip(); mapa[COL_CAT] = mapa[COL_CAT].str.strip()
    df = df.drop(columns=[COL_CAT], errors="ignore").merge(mapa[[COL_PILOTO, COL_CAT]], on=COL_PILOTO, how="left")

st.sidebar.header("🔍 Filtros"); loc = st.sidebar.selectbox("Local", sorted(df[COL_LOCAL].unique())); df = df[df[COL_LOCAL] == loc]
mapas_disp = [f for f in os.listdir(PASTA_MAPAS) if f.lower().endswith(EXTS_MAPA)]; default_map = next((f for f in mapas_disp if os.path.splitext(f)[0].lower()==loc.lower()), "— nenhum —")
map_select = st.sidebar.selectbox("🗺️ Escolher mapa", ["— nenhum —"] + mapas_disp, index=(["— nenhum —"] + mapas_disp).index(default_map))
if map_select != "— nenhum —": st.sidebar.image(os.path.join(PASTA_MAPAS, map_select), use_container_width=True)
st.sidebar.markdown("---"); new_map = st.sidebar.file_uploader("📷 Adicionar novo mapa", type=[e.strip('.') for e in EXTS_MAPA], key="map_upl")
if new_map is not None:
    with open(os.path.join(PASTA_MAPAS, new_map.name), "wb") as f: f.write(new_map.getbuffer()); st.sidebar.success("Mapa salvo! Selecione‑o na lista."); st.rerun()
ev = st.sidebar.selectbox("Evento", sorted(df[COL_EVENTO].unique()))

# ===== ALTERAÇÃO PRINCIPAL AQUI =====
# De selectbox para multiselect
categorias_disponiveis = sorted(df[COL_CAT].dropna().unique())
# Seleciona a primeira categoria por padrão para não começar vazio
default_cat = [categorias_disponiveis[0]] if categorias_disponiveis else []
cats_selecionadas = st.sidebar.multiselect("Categorias", categorias_disponiveis, default=default_cat)
# Filtra o dataframe usando isin para aceitar a lista de categorias
df = df[df[COL_CAT].isin(cats_selecionadas)]

pil = sorted(df[COL_PILOTO].unique()); sel_p = st.sidebar.multiselect("Pilotos", pil, default=pil[:2] if len(pil) >= 2 else pil, max_selections=5)
df_filtrado = df[df[COL_PILOTO].isin(sel_p)]; voltas = sorted(df_filtrado[COL_VOLTA].unique()); sel_v = st.sidebar.multiselect("Voltas", voltas, default=voltas)
df_final = df_filtrado[df_filtrado[COL_VOLTA].isin(sel_v)].reset_index(drop=True)

tab_titles = ["Comparativo Visual", "Geral", "Volta Rápida", "Velocidade", "Gráficos", "Histórico", "Exportar"]
tabs = st.tabs(tab_titles)

# ... (código da aba "Comparativo Visual" permanece o mesmo e funcionará com a nova seleção) ...
with tabs[0]:
    st.header("📊 Comparativo Visual de Voltas")
    if len(sel_p) < 2:
        st.warning("⚠️ Por favor, selecione de 2 a 5 pilotos na barra lateral para fazer a comparação."); st.stop()
    opcoes_referencia = ["-- Comparação Sequencial --"] + sel_p
    modo_comparacao = st.selectbox("Selecione o modo de comparação ou um piloto de referência:",opcoes_referencia)
    st.markdown("---")
    show_labels = st.checkbox("Mostrar tempo em cada ponto do gráfico", value=True if len(sel_p) <= 3 else False)
    fig, ax = plt.subplots(figsize=(12, 6))
    def format_yticks(seconds, pos): return f'{int(seconds // 60)}:{int(seconds % 60):02d}'
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(format_yticks))
    dados_pilotos = [df_final[df_final[COL_PILOTO] == p][[COL_VOLTA, COL_TT]].set_index(COL_VOLTA).rename(columns={COL_TT: p}) for p in sel_p]
    df_comp = dados_pilotos[0] if dados_pilotos else pd.DataFrame()
    if len(dados_pilotos) > 1:
        for i in range(1, len(dados_pilotos)): df_comp = df_comp.join(dados_pilotos[i], how='outer')
    df_comp = df_comp.sort_index().reset_index()
    fastest_laps = {p: df_final[df_final[COL_PILOTO] == p][COL_TT].min() for p in sel_p if not df_final[df_final[COL_PILOTO] == p].empty}
    common_css = """<style> .table-container { overflow-x: auto; } .comp-table { width: 100%; border-collapse: collapse; font-size: 0.9em; } .comp-table th, .comp-table td { padding: 6px 8px; text-align: center; white-space: nowrap; } .comp-table th { font-family: sans-serif; border-bottom: 2px solid #444; } .comp-table td { border-bottom: 1px solid #333; line-height: 1.3; } .comp-table tr:hover td { background-color: #2e2e2e; } .comp-table b { font-size: 1.1em; } .diff-span { font-size: 0.9em; display: block; } .diff-pos { color: #ff4d4d; } .diff-neg { color: #4dff4d; } .diff-zero { color: #888; } .fastest-lap { background-color: #483D8B; border-radius: 4px; } </style>"""
    if modo_comparacao == "-- Comparação Sequencial --":
        st.subheader("Análise Sequencial Volta a Volta")
        for p in sel_p:
            piloto_df_plot = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
            ax.plot(piloto_df_plot[COL_VOLTA], piloto_df_plot[COL_TT].dt.total_seconds(), marker='o', markersize=6, linewidth=2, label=p)
            if show_labels:
                for _, point in piloto_df_plot.iterrows():
                    ax.text(point[COL_VOLTA], point[COL_TT].total_seconds() + 0.3, fmt_tempo(point[COL_TT]), ha='center', va='bottom', fontsize=8)
        html = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr>"
        for i, p in enumerate(sel_p):
            html += f"<th>{p}</th>"
            if i < len(sel_p) - 1: html += "<th>VS</th>"
        html += "</tr></thead><tbody>"
        for _, row in df_comp.iterrows():
            html += "<tr>"
            for i, p in enumerate(sel_p):
                tempo_atual = row.get(p)
                is_fastest = fastest_laps.get(p) and tempo_atual == fastest_laps[p]
                cell_class = "fastest-lap" if is_fastest else ""
                html += f"<td class='{cell_class}'><b>{row[COL_VOLTA]}</b><br>{fmt_tempo(tempo_atual)}</td>"
                if i < len(sel_p) - 1:
                    tempo_prox = row.get(sel_p[i+1])
                    diff = tempo_prox - tempo_atual if pd.notna(tempo_atual) and pd.notna(tempo_prox) else None
                    html += formatar_diferenca_html_sequencial(diff)
            html += "</tr>"
        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)
    else:
        piloto_referencia = modo_comparacao
        st.subheader(f"Análise Volta a Volta vs. {piloto_referencia.split(' - ')[0]}")
        for p in sel_p:
            piloto_df_plot = df_final[df_final[COL_PILOTO] == p].sort_values(by=COL_VOLTA)
            if p == piloto_referencia:
                ax.plot(piloto_df_plot[COL_VOLTA], piloto_df_plot[COL_TT].dt.total_seconds(), marker='o', markersize=7, linewidth=3, linestyle='--', label=f"{p} (Ref.)", zorder=10)
            else:
                ax.plot(piloto_df_plot[COL_VOLTA], piloto_df_plot[COL_TT].dt.total_seconds(), marker='o', markersize=6, linewidth=2, label=p, alpha=0.8)
            if show_labels:
                for _, point in piloto_df_plot.iterrows():
                    ax.text(point[COL_VOLTA], point[COL_TT].total_seconds() + 0.3, fmt_tempo(point[COL_TT]), ha='center', va='bottom', fontsize=8)
        html = f"{common_css}<div class='table-container'><table class='comp-table'><thead><tr>"
        for p in sel_p: html += f"<th>{p}</th>"
        html += "</tr></thead><tbody>"
        for _, row in df_comp.iterrows():
            html += "<tr>"
            tempo_ref = row.get(piloto_referencia)
            for p in sel_p:
                tempo_atual = row.get(p); diff_str = ""
                if p != piloto_referencia:
                    diff = tempo_atual - tempo_ref if pd.notna(tempo_atual) and pd.notna(tempo_ref) else None
                    diff_str = f"<span class='diff-span'>{formatar_diff_span_referencia(diff)}</span>"
                is_fastest = fastest_laps.get(p) and tempo_atual == fastest_laps[p]
                cell_class = "fastest-lap" if is_fastest else ""
                html += f"<td class='{cell_class}'><b>{row[COL_VOLTA]}</b><br>{fmt_tempo(tempo_atual)}{diff_str}</td>"
            html += "</tr>"
        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)
    ax.legend(fontsize='small'); ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    if not df_final.empty: ax.set_xticks(sorted(df_final[COL_VOLTA].unique()))
    st.pyplot(fig, use_container_width=True)


# ===== ABAS "GERAL" E "VOLTA RÁPIDA" ATUALIZADAS PARA MOSTRAR CATEGORIA =====
best_lap = df_final[COL_TT].min() if not df_final.empty else None; best_spd = df_final[COL_VEL].max() if not df_final.empty else None; best_sec = {c: df_final[c].min() for c in (COL_S1, COL_S2, COL_S3)} if not df_final.empty else {}
with tabs[1]:
    st.subheader("📋 Tabela Completa de Voltas")
    # Adicionando COL_CAT para exibição
    cols_to_show = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
    show = df_final[cols_to_show].copy()
    for c in COLS_TEMPO: show[c] = show[c].apply(fmt_tempo)
    st.dataframe(show, hide_index=True, use_container_width=True)

with tabs[2]:
    st.subheader("🏆 Melhor Volta de Cada Piloto")
    if not df_final.empty and COL_PILOTO in df_final and COL_TT in df_final:
        idx_best = df_final.loc[df_final.groupby(COL_PILOTO)[COL_TT].idxmin()]
        # Adicionando COL_CAT para exibição
        cols_to_show_best = [COL_PILOTO, COL_CAT, "Horário", COL_VOLTA] + COLS_TEMPO + [COL_VEL]
        best_df = idx_best[cols_to_show_best].copy().sort_values(by=COL_TT)
        for c in COLS_TEMPO: best_df[c] = best_df[c].apply(fmt_tempo)
        st.dataframe(best_df, hide_index=True, use_container_width=True)

# ... (código das outras abas permanece o mesmo) ...
with tabs[3]:
    st.subheader("🚀 Maior Top Speed de Cada Piloto")
    if not df_final.empty and COL_PILOTO in df_final and COL_VEL in df_final:
        idx_sp = df_final.loc[df_final.groupby(COL_PILOTO)[COL_VEL].idxmax()]; sp_df = idx_sp[[COL_PILOTO, COL_CAT, "Horário", COL_VOLTA, COL_VEL] + COLS_TEMPO].copy().sort_values(by=COL_VEL, ascending=False)
        for c in COLS_TEMPO: sp_df[c] = sp_df[c].apply(fmt_tempo); st.dataframe(sp_df, hide_index=True, use_container_width=True)
with tabs[4]:
    st.subheader("📈 Gráficos Individuais"); st.subheader("Tempo por Volta"); fig, ax = plt.subplots()
    for p in sel_p: lab = p.split(" - ")[0]; g = df_final[df_final[COL_PILOTO] == p]; ax.plot(g[COL_VOLTA], g[COL_TT].dt.total_seconds(), marker='o', markersize=4, linewidth=1, label=lab)
    ax.set_xlabel("Volta"); ax.set_ylabel("Tempo (s)"); ax.grid(); ax.legend(fontsize=8, bbox_to_anchor=(1.04, 1), loc="upper left", borderaxespad=0); st.pyplot(fig, use_container_width=True)
with tabs[5]:
    st.subheader("🗂️ Etapas Salvas")
    st.dataframe(pd.DataFrame(files, columns=["Arquivo"]), hide_index=True)
with tabs[6]:
    st.subheader("📤 Exportar dados filtrados")
    buf = io.BytesIO(); out = df_final.copy();
    for c in COLS_TEMPO: out[c] = out[c].apply(fmt_tempo)
    with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out.to_excel(w, index=False)
    st.download_button("⬇️ Baixar Excel", buf.getvalue(), file_name=f"cronometro_{loc}_{ev}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")