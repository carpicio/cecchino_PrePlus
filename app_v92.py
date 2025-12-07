import streamlit as st
import pandas as pd
import numpy as np
import io
import re

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V92 - Force Decimal", page_icon="🔨", layout="wide")
st.title("🔨 Sniper Bet V92 (Force Decimal Fix)")
st.markdown("""
**Fix Decimale:** Questa versione forza la conversione `2,50` -> `2.50` per evitare errori di lettura.
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
        'HFA': base_hfa, 'Quota': 0, 'Pick_Code': '-'
    }
    try:
        elo_h = row.get('elohomeo', 1500)
        elo_a = row.get('eloawayo', 1500)
        o1 = row.get('cotaa', 0)
        ox = row.get('cotae', 0)
        o2 = row.get('cotad', 0)
        
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
        
        # Calcolo EV
        # Stima P(1) reale = (1-ProbX_Book) * ProbEloHome
        rem = 1 - fx
        real_p1 = rem * ph
        real_p2 = rem * pa
        
        ev1_perc = ((o1 * real_p1) - 1) * 100
        ev2_perc = ((o2 * real_p2) - 1) * 100
        
        chosen = False
        
        # S1
        if strat1['active']:
            ev = ev1_perc if strat1['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat1['pick'] == '1 (Casa)' else o2
            if (strat1['min_ev'] <= ev <= strat1['max_ev']) and \
               (strat1['min_odd'] <= odd <= strat1['max_odd']):
                res['Signal'] = '✅ STRATEGIA 1'
                res['Strategia'] = strat1['name']
                res['Pick'] = strat1['pick']
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                res['Pick_Code'] = '1' if strat1['pick'] == '1 (Casa)' else '2'
                chosen = True

        # S2
        if strat2['active'] and not chosen:
            ev = ev1_perc if strat2['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat2['pick'] == '1 (Casa)' else o2
            if (strat2['min_ev'] <= ev <= strat2['max_ev']) and \
               (strat2['min_odd'] <= odd <= strat2['max_odd']):
                res['Signal'] = '🔹 STRATEGIA 2'
                res['Strategia'] = strat2['name']
                res['Pick'] = strat2['pick']
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                res['Pick_Code'] = '1' if strat2['pick'] == '1 (Casa)' else '2'
                chosen = True

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
        
        # --- FIX DECIMALI BRUTALE ---
        # Converte tutte le colonne numeriche sostituendo ',' con '.'
        numeric_cols = ['cotaa', 'cotae', 'cotad', 'elohomeo', 'eloawayo', 'scor1', 'scor2']
        for col in numeric_cols:
            if col in df.columns:
                # Forza stringa, rimpiazza virgola, converti a numero
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'cotaa' not in df.columns: return None, f"Colonne quote mancanti. Trovate: {list(df.columns)}"
        
        df = df.dropna(subset=['cotaa'])

        # Estrazione Classifica
        if 'raw_place_1' in df.columns:
            df['rank_h_home'] = df['raw_place_1'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_h_home'] = df['rank_h_home'].fillna(df['raw_place_1'])
            # Pulizia extra per rank se contiene virgole
            df['rank_h_home'] = df['rank_h_home'].astype(str).str.replace(',', '.', regex=False)
            df['rank_h_home'] = pd.to_numeric(df['rank_h_home'], errors='coerce')
            
        if 'raw_place_2' in df.columns:
            df['rank_a_away'] = df['raw_place_2'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_a_away'] = df['rank_a_away'].fillna(df['raw_place_2'])
            df['rank_a_away'] = df['rank_a_away'].astype(str).str.replace(',', '.', regex=False)
            df['rank_a_away'] = pd.to_numeric(df['rank_a_away'], errors='coerce')

        # Match ID
        if 'txtechipa1' in df.columns and 'txtechipa2' in df.columns:
            df['MatchID'] = df['txtechipa1'].astype(str).str.lower().str.replace(' ', '') + "-" + \
                            df['txtechipa2'].astype(str).str.lower().str.replace(' ', '')
        
        df['Real_Res'] = '-'
        if 'scor1' in df.columns and 'scor2' in df.columns:
            mask = df['scor1'].notna() & df['scor2'].notna()
            df.loc[mask & (df['scor1'] > df['scor2']), 'Real_Res'] = '1'
            df.loc[mask & (df['scor1'] == df['scor2']), 'Real_Res'] = 'X'
            df.loc[mask & (df['scor1'] < df['scor2']), 'Real_Res'] = '2'

        return df, None
    except Exception as e: return None, str(e)

# --- EXPORT ---
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sniper_Data')
    return output.getvalue()

# --- UI SIDEBAR ---
st.sidebar.header("⚙️ Configurazione")
base_hfa = st.sidebar.number_input("HFA Base", 90, step=10)
use_dyn = st.sidebar.checkbox("Usa HFA Dinamico", True)

st.sidebar.markdown("---")
st.sidebar.header("🏹 STRATEGIA 1 (Verde)")
s1_active = st.sidebar.checkbox("Attiva S1", True)
s1_name = st.sidebar.text_input("Nome S1", "Cluster Ospite", key="n1")
s1_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=1, key="p1")
s1_min_odd, s1_max_odd = st.sidebar.slider("Quote S1", 1.2, 5.0, (2.06, 2.80), key="o1")
s1_min_ev, s1_max_ev = st.sidebar.slider("EV S1 (%)", -5.0, 30.0, (11.0, 19.5), key="e1")
strat1 = {'active': s1_active, 'name': s1_name, 'pick': s1_pick, 'min_odd': s1_min_odd, 'max_odd': s1_max_odd, 'min_ev': s1_min_ev, 'max_ev': s1_max_ev}

st.sidebar.markdown("---")
st.sidebar.header("🗡️ STRATEGIA 2 (Blu)")
s2_active = st.sidebar.checkbox("Attiva S2", True)
s2_name = st.sidebar.text_input("Nome S2", "Cluster Casa", key="n2")
s2_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=0, key="p2")
s2_min_odd, s2_max_odd = st.sidebar.slider("Quote S2", 1.2, 5.0, (1.80, 2.20), key="o2")
s2_min_ev, s2_max_ev = st.sidebar.slider("EV S2 (%)", -5.0, 30.0, (5.0, 15.0), key="e2")
strat2 = {'active': s2_active, 'name': s2_name, 'pick': s2_pick, 'min_odd': s2_min_odd, 'max_odd': s2_max_odd, 'min_ev': s2_min_ev, 'max_ev': s2_max_ev}

st.sidebar.markdown("---")
st.sidebar.header("📥 DOWNLOAD")
dl_placeholder = st.sidebar.empty()

# --- TABS ---
tab1, tab2 = st.tabs(["🧪 STUDIO STORICO", "⚖️ VERIFICA (Pre/Post)"])

# --- TAB 1: STUDIO ---
with tab1:
    st.info("Carica UN SOLO FILE (Quote + Risultati).")
    file_studio = st.file_uploader("File Storico", type=["csv", "xlsx", "xls"], key="u1")
    
    if file_studio:
        df_stud, err = load_and_prep(file_studio)
        if df_stud is not None:
            calc_s = df_stud.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_s = pd.concat([df_stud, calc_s], axis=1)
            targets_s = final_s[final_s['Signal'] != 'SKIP']
            
            if not targets_s.empty:
                has_res = 'Real_Res' in targets_s.columns and targets_s['Real_Res'].ne('-').any()
                if has_res:
                    def check_res(row):
                        if row['Real_Res'] == '-': return row
                        if row['Real_Res'] == row['Pick_Code']:
                            row['PNL'] = row['Quota'] - 1; row['Esito'] = 'WIN'; row['Dettaglio'] = 'Vinta'
                        else:
                            row['PNL'] = -1; row['Esito'] = 'LOSS'
                            if row['Real_Res'] == 'X': row['Dettaglio'] = 'Pareggio (X)'
                            elif row['Pick_Code'] == '1': row['Dettaglio'] = 'Vittoria Ospite (2)'
                            elif row['Pick_Code'] == '2': row['Dettaglio'] = 'Vittoria Casa (1)'
                        return row
                    targets_s = targets_s.apply(check_res, axis=1)
                    
                    st.subheader("📊 Performance")
                    res_counts = targets_s['Real_Res'].value_counts(normalize=True) * 100
                    c1, c2, c3 = st.columns(3)
                    c1.metric("1 (%)", f"{res_counts.get('1', 0):.1f}%")
                    c2.metric("X (%)", f"{res_counts.get('X', 0):.1f}%")
                    c3.metric("2 (%)", f"{res_counts.get('2', 0):.1f}%")
                    
                    st.markdown("---")
                    c_s1 = targets_s[targets_s['Signal'] == '✅ STRATEGIA 1']
                    c_s2 = targets_s[targets_s['Signal'] == '🔹 STRATEGIA 2']
                    
                    colA, colB = st.columns(2)
                    with colA:
                        st.info(f"{s1_name} ({len(c_s1)})")
                        if not c_s1.empty:
                            pnl = c_s1['PNL'].sum()
                            st.write(f"Utile: **{pnl:.2f}u** | ROI: **{(pnl/len(c_s1))*100:.1f}%**")
                    with colB:
                        st.info(f"{s2_name} ({len(c_s2)})")
                        if not c_s2.empty:
                            pnl = c_s2['PNL'].sum()
                            st.write(f"Utile: **{pnl:.2f}u** | ROI: **{(pnl/len(c_s2))*100:.1f}%**")
                    
                    def color_rows(row):
                        if row['Esito'] == 'WIN': return ['background-color: #28a745; color: white; font-weight: bold'] * len(row)
                        if row['Esito'] == 'LOSS': return ['background-color: #dc3545; color: white; font-weight: bold'] * len(row)
                        return ['color: black'] * len(row)
                    
                    cols = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                    final_c = [c for c in cols if c in targets_s.columns]
                    st.dataframe(targets_s[final_c].style.apply(color_rows, axis=1), use_container_width=True)
                    
                    d_data = to_excel(targets_s[final_c])
                    dl_placeholder.download_button("💾 SCARICA STORICO", d_data, "sniper_storico.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.info("Solo Previsioni")
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
                    if 'STRATEGIA 1' in str(val): return 'background-color: #d4edda; color: #155724'
                    if 'STRATEGIA 2' in str(val): return 'background-color: #cce5ff; color: #004085'
                    return ''
                st.dataframe(targets_pre[final_cols_pre].style.applymap(color_strat, subset=['Signal']), use_container_width=True)
                
                d_data = to_excel(targets_pre[final_cols_pre])
                dl_placeholder.download_button("💾 SCARICA LISTA PRE-MATCH", d_data, "sniper_prematch.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
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
                            if real == '-':
                                row['Esito'] = 'Non Trovata'; row['Dettaglio'] = '-'; return row
                            if real == row['Pick_Code']:
                                row['PNL'] = row['Quota'] - 1; row['Esito'] = 'WIN'; row['Dettaglio'] = '✅ Vinta'
                            else:
                                row['PNL'] = -1; row['Esito'] = 'LOSS'
                                if real == 'X': row['Dettaglio'] = '❌ Pareggio (X)'
                                elif row['Pick_Code'] == '1': row['Dettaglio'] = '❌ Vittoria Ospite (2)'
                                elif row['Pick_Code'] == '2': row['Dettaglio'] = '❌ Vittoria Casa (1)'
                            return row
                        
                        found_res = targets_pre.apply(check_outcome, axis=1)
                        found_res = found_res[found_res['Esito'] != 'Non Trovata']
                        
                        if not found_res.empty:
                            st.metric("Profitto Reale", f"{found_res['PNL'].sum():.2f} u")
                            
                            def color_res(row):
                                if row['Esito'] == 'WIN': return ['background-color: #28a745; color: white; font-weight: bold'] * len(row)
                                if row['Esito'] == 'LOSS': return ['background-color: #dc3545; color: white; font-weight: bold'] * len(row)
                                return ['color: black'] * len(row)
                            
                            cols_post = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                            final_cols_post = [c for c in cols_post if c in found_res.columns]
                            st.dataframe(found_res[final_cols_post].style.apply(color_res, axis=1), use_container_width=True)
                            
                            losses = found_res[found_res['Esito'] == 'LOSS']
                            if not losses.empty:
                                draws = len(losses[losses['Real_Res'] == 'X'])
                                cA, cB = st.columns(2)
                                cA.error(f"Pareggi (X): {draws}")
                                cB.error(f"Sconfitte Nette: {len(losses)-draws}")
                            
                            d_data2 = to_excel(found_res[final_cols_post])
                            dl_placeholder.download_button("💾 SCARICA REPORT VERIFICA", d_data2, "sniper_verifica.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        else: st.warning("Nessuna corrispondenza trovata.")
        else: st.error(err1)
