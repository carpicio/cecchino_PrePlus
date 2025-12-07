import streamlit as st
import pandas as pd
import numpy as np
import io

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V97 - Ultimate Report", page_icon="📊", layout="wide")
st.title("📊 Sniper Bet V97 (Report Manageriale)")
st.markdown("""
**Analisi Profonda:**
Il software ora genera un report dettagliato con **ROI per ogni segno** e **Risultati Esatti** più frequenti.
""")
st.markdown("---")

# --- CORE LOGIC ---
def get_probs(elo_h, elo_a, hfa):
    try:
        diff = elo_a - (elo_h + hfa)
        exp = diff / 400
        p_h = 1 / (1 + 10**exp)
        return p_h, 1 - p_h
    except: return 0, 0

def no_margin(o1, ox, o2):
    try:
        if o1<=0 or ox<=0 or o2<=0: return 0,0,0
        i1 = 1/o1; ix = 1/ox; i2 = 1/o2
        s = i1 + ix + i2
        return i1/s, ix/s, i2/s
    except: return 0,0,0

def calc_hybrid(row, base_hfa, dyn, strat1, strat2):
    res = {
        'Signal': 'SKIP', 'Strategia': '-', 'EV': 0, 'Pick': '-', 
        'HFA': base_hfa, 'Quota': 0, 'Pick_Code': '-', 
        'Is_S1': False, 'Is_S2': False
    }
    try:
        def to_f(v):
            try: return float(str(v).replace(',', '.'))
            except: return 0.0

        elo_h = to_f(row.get('elohomeo', 1500))
        elo_a = to_f(row.get('eloawayo', 1500))
        o1 = to_f(row.get('cotaa', 0))
        ox = to_f(row.get('cotae', 0))
        o2 = to_f(row.get('cotad', 0))
        
        curr_hfa = base_hfa
        if dyn:
            r1 = row.get('rank_h_home')
            r2 = row.get('rank_a_away')
            if pd.notna(r1) and pd.notna(r2):
                try:
                    curr_hfa += (float(r2) - float(r1)) * 3
                    curr_hfa = max(0, min(curr_hfa, 200))
                except: pass
        
        res['HFA'] = int(curr_hfa)
        
        f1, fx, f2 = no_margin(o1, ox, o2)
        ph, pa = get_probs(elo_h, elo_a, curr_hfa)
        
        rem = 1 - fx
        prob_1 = rem * ph
        prob_2 = rem * pa
        
        ev1_perc = ((o1 * prob_1) - 1) * 100
        ev2_perc = ((o2 * prob_2) - 1) * 100
        
        matches = []
        
        # S1
        if strat1['active']:
            ev = ev1_perc if strat1['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat1['pick'] == '1 (Casa)' else o2
            if (strat1['min_ev'] <= ev <= strat1['max_ev']) and \
               (strat1['min_odd'] <= odd <= strat1['max_odd']):
                res['Is_S1'] = True
                matches.append("S1")
                res['Pick'] = strat1['pick']
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                res['Pick_Code'] = '1' if strat1['pick'] == '1 (Casa)' else '2'

        # S2
        if strat2['active']:
            ev = ev1_perc if strat2['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat2['pick'] == '1 (Casa)' else o2
            if (strat2['min_ev'] <= ev <= strat2['max_ev']) and \
               (strat2['min_odd'] <= odd <= strat2['max_odd']):
                res['Is_S2'] = True
                matches.append("S2")
                res['Pick'] = strat2['pick'] # S2 ha priorità visiva se attiva
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                res['Pick_Code'] = '1' if strat2['pick'] == '1 (Casa)' else '2'

        if len(matches) > 0:
            if "S1" in matches and "S2" in matches:
                res['Signal'] = "✅ S1 + 🔹 S2"
                res['Strategia'] = "DOUBLE MATCH"
            elif "S1" in matches:
                res['Signal'] = "✅ S1"
                res['Strategia'] = strat1['name']
            elif "S2" in matches:
                res['Signal'] = "🔹 S2" # Teoricamente impossibile se S2 subset S1, ma gestiamo
                res['Strategia'] = strat2['name']

    except: pass
    return pd.Series(res)

@st.cache_data(ttl=0)
def load_and_prep(file):
    try:
        filename = file.name.lower()
        df = None
        if filename.endswith('.csv'):
            try: df = pd.read_csv(file, sep=None, encoding='latin1', on_bad_lines='skip', engine='python')
            except: 
                file.seek(0)
                df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', engine='python')
        elif filename.endswith(('.xls', '.xlsx')):
            try: df = pd.read_excel(file)
            except Exception as e: return None, f"Errore Excel: {e}"
        
        if df is None: return None, "Formato non valido"

        df.columns = df.columns.astype(str).str.strip().str.lower()
        
        ren = {
            '1': 'cotaa', 'cotaa': 'cotaa', 'quota1': 'cotaa',
            'x': 'cotae', 'cotae': 'cotae', 'quotax': 'cotae',
            '2': 'cotad', 'cotad': 'cotad', 'quota2': 'cotad',
            'eloc': 'elohomeo', 'elohomeo': 'elohomeo',
            'eloo': 'eloawayo', 'eloawayo': 'eloawayo',
            'gfinc': 'scor1', 'gfino': 'scor2', 'score1': 'scor1', 'score2': 'scor2', 'scor1': 'scor1', 'scor2': 'scor2',
            'home': 'txtechipa1', 'away': 'txtechipa2', 'casa': 'txtechipa1', 'ospite': 'txtechipa2', 'txtechipa1': 'txtechipa1', 'txtechipa2': 'txtechipa2',
            'data': 'datameci', 'date': 'datameci', 'datameci': 'datameci',
            'league': 'league', 'campionato': 'league',
            'place 1': 'raw_place_1', 'place1': 'raw_place_1',
            'place 2': 'raw_place_2', 'place2': 'raw_place_2',
            'place 1a': 'rank_h_home', 'place1a': 'rank_h_home',
            'place 2d': 'rank_a_away', 'place2d': 'rank_a_away'
        }
        
        new = {}
        for c in df.columns:
            if c in ren: new[c] = ren[c]
        df = df.rename(columns=new)
        
        cols_num = ['cotaa', 'cotae', 'cotad', 'elohomeo', 'eloawayo', 'scor1', 'scor2']
        for c in cols_num:
            if c in df.columns:
                df[c] = df[c].astype(str).str.replace(',', '.', regex=False)
                df[c] = pd.to_numeric(df[c], errors='coerce')

        if 'cotaa' not in df.columns: return None, f"Colonne quote mancanti. Trovate: {list(df.columns)}"
        
        df = df.dropna(subset=['cotaa'])

        if 'raw_place_1' in df.columns:
            df['rank_h_home'] = df['raw_place_1'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_h_home'] = df['rank_h_home'].fillna(df['raw_place_1'])
            df['rank_h_home'] = df['rank_h_home'].astype(str).str.replace(',', '.', regex=False)
            df['rank_h_home'] = pd.to_numeric(df['rank_h_home'], errors='coerce')
        if 'raw_place_2' in df.columns:
            df['rank_a_away'] = df['raw_place_2'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_a_away'] = df['rank_a_away'].fillna(df['raw_place_2'])
            df['rank_a_away'] = df['rank_a_away'].astype(str).str.replace(',', '.', regex=False)
            df['rank_a_away'] = pd.to_numeric(df['rank_a_away'], errors='coerce')

        if 'txtechipa1' in df.columns and 'txtechipa2' in df.columns:
            df['MatchID'] = df['txtechipa1'].astype(str).str.lower().str.replace(' ', '') + "-" + \
                            df['txtechipa2'].astype(str).str.lower().str.replace(' ', '')
        
        df['Real_Res'] = '-'
        df['Correct_Score'] = 'ND'
        
        if 'scor1' in df.columns and 'scor2' in df.columns:
            mask = df['scor1'].notna() & df['scor2'].notna()
            df.loc[mask & (df['scor1'] > df['scor2']), 'Real_Res'] = '1'
            df.loc[mask & (df['scor1'] == df['scor2']), 'Real_Res'] = 'X'
            df.loc[mask & (df['scor1'] < df['scor2']), 'Real_Res'] = '2'
            
            # Crea colonna Risultato Esatto
            df.loc[mask, 'Correct_Score'] = df.loc[mask, 'scor1'].astype(int).astype(str) + "-" + df.loc[mask, 'scor2'].astype(int).astype(str)

        return df, None
    except Exception as e: return None, str(e)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sniper_Data')
    return output.getvalue()

# --- ANALYTICS ENGINE ---
def analyze_segment(df_seg, label):
    if df_seg.empty:
        st.warning(f"{label}: Nessuna partita trovata.")
        return

    st.markdown(f"### 📌 {label}")
    total = len(df_seg)
    
    # 1. Analisi Esiti
    res_counts = df_seg['Real_Res'].value_counts()
    n1 = res_counts.get('1', 0)
    nx = res_counts.get('X', 0)
    n2 = res_counts.get('2', 0)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Totale Partite", total)
    col2.metric("Vittorie 1", f"{n1} ({n1/total*100:.1f}%)")
    col3.metric("Pareggi X", f"{nx} ({nx/total*100:.1f}%)")
    col4.metric("Vittorie 2", f"{n2} ({n2/total*100:.1f}%)")
    
    # 2. Analisi Economica (ROI) su tutti i segni
    # Se avessi puntato sempre 1:
    pnl_1 = df_seg.apply(lambda r: r['cotaa'] - 1 if r['Real_Res'] == '1' else -1, axis=1).sum()
    roi_1 = (pnl_1 / total) * 100
    
    # Se avessi puntato sempre X:
    pnl_x = df_seg.apply(lambda r: r['cotae'] - 1 if r['Real_Res'] == 'X' else -1, axis=1).sum()
    roi_x = (pnl_x / total) * 100
    
    # Se avessi puntato sempre 2:
    pnl_2 = df_seg.apply(lambda r: r['cotad'] - 1 if r['Real_Res'] == '2' else -1, axis=1).sum()
    roi_2 = (pnl_2 / total) * 100
    
    # Visualizzazione ROI
    c_roi1, c_roi2, c_roi3 = st.columns(3)
    
    def format_kpi(val, lab):
        color = "green" if val > 0 else "red"
        return f"**{lab}**: :{color}[{val:.2f} u] ({val/total*100:.1f}%)"

    c_roi1.markdown(f"📉 **Bet 1 (Casa)**\n\nProfit: {pnl_1:.2f}u\n\nROI: {roi_1:.1f}%")
    c_roi2.markdown(f"😐 **Bet X (Pareggio)**\n\nProfit: {pnl_x:.2f}u\n\nROI: {roi_x:.1f}%")
    c_roi3.markdown(f"🏆 **Bet 2 (Ospite)**\n\nProfit: {pnl_2:.2f}u\n\nROI: {roi_2:.1f}%")
    
    # 3. Risultati Esatti
    st.markdown("**⚽ Top 5 Risultati Esatti:**")
    cs_counts = df_seg['Correct_Score'].value_counts().head(5)
    cs_text = "  |  ".join([f"**{idx}** ({val} volte, {val/total*100:.1f}%)" for idx, val in cs_counts.items()])
    st.info(cs_text)
    
    st.markdown("---")

# --- UI ---
st.sidebar.header("⚙️ Configurazione")
base_hfa = st.sidebar.number_input("HFA Base", 90, step=5)
use_dyn = st.sidebar.checkbox("Usa HFA Dinamico", True)

st.sidebar.markdown("---")
st.sidebar.header("Strategia 1 (Verde)")
s1_active = st.sidebar.checkbox("Attiva S1", True)
s1_name = st.sidebar.text_input("Nome S1", "S1 (Base)", key="n1")
s1_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=1, key="p1")
c1, c2 = st.sidebar.columns(2)
s1_min_odd = c1.number_input("Q Min S1", 2.20, step=0.05, key="o1_min")
s1_max_odd = c2.number_input("Q Max S1", 2.80, step=0.05, key="o1_max")
c3, c4 = st.sidebar.columns(2)
s1_min_ev = c3.number_input("EV Min S1", 10.0, step=0.5, key="e1_min")
s1_max_ev = c4.number_input("EV Max S1", 30.0, step=0.5, key="e1_max")
strat1 = {'active': s1_active, 'name': s1_name, 'pick': s1_pick, 'min_odd': s1_min_odd, 'max_odd': s1_max_odd, 'min_ev': s1_min_ev, 'max_ev': s1_max_ev}

st.sidebar.markdown("---")
st.sidebar.header("Strategia 2 (Blu)")
s2_active = st.sidebar.checkbox("Attiva S2", True)
s2_name = st.sidebar.text_input("Nome S2", "S2 (Top)", key="n2")
s2_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=1, key="p2")
c5, c6 = st.sidebar.columns(2)
s2_min_odd = c5.number_input("Q Min S2", 2.50, step=0.05, key="o2_min")
s2_max_odd = c6.number_input("Q Max S2", 2.80, step=0.05, key="o2_max")
c7, c8 = st.sidebar.columns(2)
s2_min_ev = c7.number_input("EV Min S2", 12.0, step=0.5, key="e2_min")
s2_max_ev = c8.number_input("EV Max S2", 30.0, step=0.5, key="e2_max")
strat2 = {'active': s2_active, 'name': s2_name, 'pick': s2_pick, 'min_odd': s2_min_odd, 'max_odd': s2_max_odd, 'min_ev': s2_min_ev, 'max_ev': s2_max_ev}

st.sidebar.markdown("---")
st.sidebar.header("📥 DOWNLOAD")
dl_placeholder = st.sidebar.empty()

# --- TABS ---
tab1, tab2 = st.tabs(["🧪 STUDIO STORICO (Report)", "⚖️ VERIFICA (Pre/Post)"])

# --- TAB 1 ---
with tab1:
    st.info("Carica il file storico per generare il Report Manageriale.")
    file_studio = st.file_uploader("File Storico", type=["csv", "xlsx", "xls"], key="u1")
    
    if file_studio:
        df_stud, err = load_and_prep(file_studio)
        if df_stud is not None:
            calc_s = df_stud.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_s = pd.concat([df_stud, calc_s], axis=1)
            targets_s = final_s[final_s['Signal'] != 'SKIP']
            
            if not targets_s.empty:
                if 'Real_Res' in targets_s.columns and targets_s['Real_Res'].ne('-').any():
                    # Definisci i due gruppi
                    # S1 Esclusiva = (Is_S1 True) AND (Is_S2 False)
                    # S2 Top = (Is_S2 True)
                    
                    df_s1_excl = targets_s[ (targets_s['Is_S1'] == True) & (targets_s['Is_S2'] == False) ]
                    df_s2_top = targets_s[ targets_s['Is_S2'] == True ]
                    df_total = targets_s # Tutto
                    
                    st.subheader("📊 REPORT ANALITICO DETTAGLIATO")
                    
                    with st.expander("1️⃣ STRATEGIA 1 ESCLUSIVA (Quote Base)", expanded=True):
                        analyze_segment(df_s1_excl, "Partite Solo S1 (Escluse le Top)")
                        
                    with st.expander("2️⃣ STRATEGIA 2 TOP (Quote Alte)", expanded=True):
                        analyze_segment(df_s2_top, "Partite Top S2 (Best Value)")
                        
                    with st.expander("3️⃣ TOTALE (S1 + S2)", expanded=False):
                        analyze_segment(df_total, "Tutte le partite filtrate")
                    
                    # Tabella Dati
                    st.markdown("### 📝 Lista Partite")
                    def color_rows(row):
                        real = row['Real_Res']
                        pick = row['Pick_Code']
                        if real == pick: return ['background-color: #28a745; color: white'] * len(row)
                        if real != '-' and real != pick: return ['background-color: #dc3545; color: white'] * len(row)
                        return [''] * len(row)
                    
                    cols = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Correct_Score', 'EV']
                    final_c = [c for c in cols if c in targets_s.columns]
                    st.dataframe(targets_s[final_c].style.apply(color_rows, axis=1), use_container_width=True)
                    
                    d_data = to_excel(targets_s[final_c])
                    dl_placeholder.download_button("💾 SCARICA REPORT", d_data, "sniper_report.xlsx")
                else:
                    st.warning("Il file non contiene risultati (colonne 'scor1'/'scor2' mancanti o vuote).")
                    st.dataframe(targets_s)
        else: st.error(err)

# --- TAB 2 ---
with tab2:
    st.markdown("### 1. FASE PRE-MATCH")
    f_pre = st.file_uploader("File QUOTE", type=["csv", "xlsx", "xls"], key="u2a")
    if f_pre:
        df_pre, err1 = load_and_prep(f_pre)
        if df_pre is not None:
            calc_pre = df_pre.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_pre = pd.concat([df_pre, calc_pre], axis=1)
            targets_pre = final_pre[final_pre['Signal'] != 'SKIP'].copy()
            if not targets_pre.empty:
                st.success(f"✅ {len(targets_pre)} Partite Trovate")
                cols_pre = ['Signal', 'datameci', 'league', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'EV', 'HFA']
                final_cols_pre = [c for c in cols_pre if c in targets_pre.columns]
                def color_strat(val):
                    if '✅ S1' in str(val): return 'background-color: #d4edda; color: #155724'
                    if '🔹 S2' in str(val): return 'background-color: #cce5ff; color: #004085'
                    if '✅ S1 + 🔹 S2' in str(val): return 'background-color: #fff3cd; color: #856404; font-weight: bold'
                    return ''
                st.dataframe(targets_pre[final_cols_pre].style.applymap(color_strat, subset=['Signal']), use_container_width=True)
                d_data = to_excel(targets_pre[final_cols_pre])
                dl_placeholder.download_button("💾 SCARICA LISTA PRE-MATCH", d_data, "sniper_prematch.xlsx")
                
                st.divider()
                st.markdown("### 2. FASE POST-MATCH")
                f_post = st.file_uploader("File RISULTATI", type=["csv", "xlsx", "xls"], key="u2b")
                if f_post:
                    df_post, err2 = load_and_prep(f_post)
                    if df_post is not None:
                        res_map = df_post.set_index('MatchID')['Real_Res'].to_dict()
                        def check_outcome(row):
                            mid = row['MatchID']
                            real = res_map.get(mid, '-')
                            row['Real_Res'] = real
                            if real == '-': row['Esito'] = 'Non Trovata'; row['Dettaglio'] = '-'; return row
                            if real == row['Pick_Code']: row['PNL'] = row['Quota'] - 1; row['Esito'] = 'WIN'; row['Dettaglio'] = '✅ Vinta'
                            else: row['PNL'] = -1; row['Esito'] = 'LOSS'; row['Dettaglio'] = f"❌ Uscito {real}"
                            return row
                        
                        found_res = targets_pre.apply(check_outcome, axis=1)
                        found_res = found_res[found_res['Esito'] != 'Non Trovata']
                        if not found_res.empty:
                            st.metric("Profitto Reale", f"{found_res['PNL'].sum():.2f} u")
                            def color_res(row):
                                if row['Esito'] == 'WIN': return ['background-color: #28a745; color: white'] * len(row)
                                if row['Esito'] == 'LOSS': return ['background-color: #dc3545; color: white'] * len(row)
                                return ['color: black'] * len(row)
                            cols_post = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                            final_cols_post = [c for c in cols_post if c in found_res.columns]
                            st.dataframe(found_res[final_cols_post].style.apply(color_res, axis=1), use_container_width=True)
                            
                            d_data2 = to_excel(found_res[final_cols_post])
                            dl_placeholder.download_button("💾 SCARICA REPORT VERIFICA", d_data2, "sniper_verifica.xlsx")
                        else: st.warning("Nessuna corrispondenza trovata.")
        else: st.error(err1)
