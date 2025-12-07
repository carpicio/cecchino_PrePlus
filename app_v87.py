import streamlit as st
import pandas as pd
import numpy as np
import sys
import subprocess

# --- AUTO-INSTALLAZIONE ---
try:
    import openpyxl
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
        import openpyxl
    except: pass

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V87 - Analytics", page_icon="📊", layout="wide")
st.title("📊 Sniper Bet V87 (Analytics & High Contrast)")
st.markdown("""
**Novità:**
- **Analisi 1X2:** Distribuzione percentuale dei segni reali sulle partite filtrate.
- **ROI & Utile:** Calcolo dettagliato per capire quale strategia rende di più.
- **Alto Contrasto:** Tabella risultati ottimizzata per la lettura.
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
        def to_f(v):
            try: return float(str(v).replace(',', '.'))
            except: return 0.0

        elo_h = to_f(row.get('elohomeo', 1500))
        elo_a = to_f(row.get('eloawayo', 1500))
        o1 = to_f(row.get('cotaa', 0))
        ox = to_f(row.get('cotae', 0))
        o2 = to_f(row.get('cotad', 0))
        
        # HFA Dinamico
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
        
        # Calcoli
        f1, fx, f2 = no_margin(o1, ox, o2)
        ph, pa = get_probs(elo_h, elo_a, curr_hfa)
        rem = 1 - fx
        fin1 = rem * ph
        fin2 = rem * pa 
        
        ev1_perc = ((o1 * fin1) - 1) * 100
        ev2_perc = ((o2 * fin2) - 1) * 100
        
        # --- SEGNALI ---
        chosen = False
        
        # Strategia 1
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

        # Strategia 2
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

        df.columns = df.columns.astype(str).str.strip()
        
        # MAPPING
        ren = {
            '1': 'cotaa', 'cotaa': 'cotaa', 'quota1': 'cotaa',
            'x': 'cotae', 'cotae': 'cotae', 'quotax': 'cotae',
            '2': 'cotad', 'cotad': 'cotad', 'quota2': 'cotad',
            'eloc': 'elohomeo', 'elohomeo': 'elohomeo',
            'eloo': 'eloawayo', 'eloawayo': 'eloawayo',
            'gfinc': 'scor1', 'gfino': 'scor2', 'score1': 'scor1', 'score2': 'scor2',
            'home': 'txtechipa1', 'away': 'txtechipa2', 'casa': 'txtechipa1', 'ospite': 'txtechipa2',
            'data': 'datameci', 'date': 'datameci',
            'league': 'league', 'campionato': 'league',
            'place 1': 'raw_place_1', 'place1': 'raw_place_1',
            'place 2': 'raw_place_2', 'place2': 'raw_place_2',
            'place 1a': 'rank_h_home', 'place1a': 'rank_h_home',
            'place 2d': 'rank_a_away', 'place2d': 'rank_a_away'
        }
        
        new = {}
        for c in df.columns:
            if c.lower() in ren: new[c] = ren[c.lower()]
        df = df.rename(columns=new)
        
        if 'cotaa' not in df.columns: return None, f"Colonne quote mancanti. Trovate: {list(df.columns)}"
        
        df = df.dropna(subset=['cotaa'])

        # Estrazione Classifica
        if 'raw_place_1' in df.columns:
            df['rank_h_home'] = df['raw_place_1'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_h_home'] = df['rank_h_home'].fillna(df['raw_place_1'])
            df['rank_h_home'] = pd.to_numeric(df['rank_h_home'], errors='coerce')
        if 'raw_place_2' in df.columns:
            df['rank_a_away'] = df['raw_place_2'].astype(str).str.extract(r'\((\d+)\)')[0]
            df['rank_a_away'] = df['rank_a_away'].fillna(df['raw_place_2'])
            df['rank_a_away'] = pd.to_numeric(df['rank_a_away'], errors='coerce')

        # Pulizia Risultati
        for c in ['scor1', 'scor2']:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
            
        # Match ID Normalizzato
        if 'txtechipa1' in df.columns and 'txtechipa2' in df.columns:
            df['MatchID'] = df['txtechipa1'].astype(str).str.lower().str.replace(' ', '') + "-" + \
                            df['txtechipa2'].astype(str).str.lower().str.replace(' ', '')
        
        # Determina Risultato
        df['Real_Res'] = '-'
        if 'scor1' in df.columns and 'scor2' in df.columns:
            mask = df['scor1'].notna() & df['scor2'].notna()
            df.loc[mask & (df['scor1'] > df['scor2']), 'Real_Res'] = '1'
            df.loc[mask & (df['scor1'] == df['scor2']), 'Real_Res'] = 'X'
            df.loc[mask & (df['scor1'] < df['scor2']), 'Real_Res'] = '2'

        return df, None
    except Exception as e: return None, str(e)

# --- HELPER SCONFITTE ---
def analyze_losses(df_strat):
    if df_strat.empty: return 0, 0, 0
    losses = df_strat[df_strat['Esito'] == 'LOSS']
    total_losses = len(losses)
    if total_losses == 0: return 0, 0, 0
    draws = len(losses[losses['Real_Res'] == 'X'])
    direct_loss = total_losses - draws
    return total_losses, draws, direct_loss

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

# --- TABS ---
tab1, tab2 = st.tabs(["🧪 STUDIO STORICO (Single File)", "⚖️ VERIFICA (Step-by-Step)"])

# --- TAB 1: STUDIO ---
with tab1:
    st.info("Carica UN SOLO FILE che contiene già i risultati.")
    file_studio = st.file_uploader("Carica File Storico", type=["csv", "xlsx", "xls"], key="u1")
    
    if file_studio:
        df_stud, err = load_and_prep(file_studio)
        if df_stud is not None:
            calc_s = df_stud.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_s = pd.concat([df_stud, calc_s], axis=1)
            targets_s = final_s[final_s['Signal'] != 'SKIP']
            
            if not targets_s.empty:
                # Applica esito se c'è risultato
                if 'Real_Res' in targets_s.columns and targets_s['Real_Res'].ne('-').any():
                    def check_res(row):
                        if row['Real_Res'] == '-': return row
                        if row['Real_Res'] == row['Pick_Code']:
                            row['PNL'] = row['Quota'] - 1
                            row['Esito'] = 'WIN'
                            row['Dettaglio'] = 'Vinta'
                        else:
                            row['PNL'] = -1
                            row['Esito'] = 'LOSS'
                            if row['Real_Res'] == 'X': row['Dettaglio'] = 'Pareggio (X)'
                            elif row['Pick_Code'] == '1': row['Dettaglio'] = 'Vittoria Ospite (2)'
                            elif row['Pick_Code'] == '2': row['Dettaglio'] = 'Vittoria Casa (1)'
                        return row
                    
                    targets_s = targets_s.apply(check_res, axis=1)
                    
                    # --- ANALYTICS 1X2 ---
                    st.subheader("📊 Analisi Performance")
                    
                    # 1. Distribuzione Segni Reali
                    res_counts = targets_s['Real_Res'].value_counts(normalize=True) * 100
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Segno 1 Uscito", f"{res_counts.get('1', 0):.1f}%")
                    c2.metric("Segno X Uscito", f"{res_counts.get('X', 0):.1f}%")
                    c3.metric("Segno 2 Uscito", f"{res_counts.get('2', 0):.1f}%")
                    
                    st.markdown("---")
                    
                    # 2. Performance Strategie
                    c_s1 = targets_s[targets_s['Signal'] == '✅ STRATEGIA 1']
                    c_s2 = targets_s[targets_s['Signal'] == '🔹 STRATEGIA 2']
                    
                    colA, colB = st.columns(2)
                    
                    with colA:
                        st.info(f"**{s1_name}** ({len(c_s1)} bets)")
                        if not c_s1.empty:
                            pnl1 = c_s1['PNL'].sum()
                            roi1 = (pnl1 / len(c_s1)) * 100
                            st.write(f"Utile: **{pnl1:.2f} u**")
                            st.write(f"ROI: **{roi1:.2f}%**")
                    
                    with colB:
                        st.info(f"**{s2_name}** ({len(c_s2)} bets)")
                        if not c_s2.empty:
                            pnl2 = c_s2['PNL'].sum()
                            roi2 = (pnl2 / len(c_s2)) * 100
                            st.write(f"Utile: **{pnl2:.2f} u**")
                            st.write(f"ROI: **{roi2:.2f}%**")
                    
                    # Verdetto
                    best_profit = -9999
                    best_strat = "Nessuna"
                    if not c_s1.empty and c_s1['PNL'].sum() > best_profit:
                        best_profit = c_s1['PNL'].sum()
                        best_strat = s1_name
                    if not c_s2.empty and c_s2['PNL'].sum() > best_profit:
                        best_profit = c_s2['PNL'].sum()
                        best_strat = s2_name
                        
                    if best_profit > 0:
                        st.success(f"🏆 La strategia migliore è **{best_strat}** con un utile di **{best_profit:.2f} u**")
                    else:
                        st.error("⚠️ Nessuna strategia è in profitto con questi parametri.")

                    st.markdown("---")
                    
                    # TABLE STYLE
                    def color_rows(row):
                        if row['Esito'] == 'WIN': return ['background-color: #28a745; color: white; font-weight: bold'] * len(row)
                        if row['Esito'] == 'LOSS': return ['background-color: #dc3545; color: white; font-weight: bold'] * len(row)
                        return ['color: black'] * len(row)
                    
                    cols = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                    final_c = [c for c in cols if c in targets_s.columns]
                    st.dataframe(targets_s[final_c].style.apply(color_rows, axis=1), use_container_width=True)
                else:
                    st.info("Solo previsioni (senza risultati).")
                    st.dataframe(targets_s)
        else:
            st.error(err)

# --- TAB 2: VERIFICA ---
with tab2:
    st.markdown("### 1. FASE PRE-MATCH")
    f_pre = st.file_uploader("Carica File QUOTE", type=["csv", "xlsx", "xls"], key="u2a")
    
    if f_pre:
        df_pre, err1 = load_and_prep(f_pre)
        if df_pre is not None:
            calc_pre = df_pre.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_pre = pd.concat([df_pre, calc_pre], axis=1)
            targets_pre = final_pre[final_pre['Signal'] != 'SKIP'].copy()
            
            if not targets_pre.empty:
                st.success(f"✅ TROVATE {len(targets_pre)} PARTITE DA GIOCARE:")
                
                cols_pre = ['Signal', 'datameci', 'league', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'EV', 'HFA']
                final_cols_pre = [c for c in cols_pre if c in targets_pre.columns]
                
                def color_strat(val):
                    if 'STRATEGIA 1' in str(val): return 'background-color: #d4edda; color: #155724'
                    if 'STRATEGIA 2' in str(val): return 'background-color: #cce5ff; color: #004085'
                    return ''
                    
                st.dataframe(targets_pre[final_cols_pre].style.applymap(color_strat, subset=['Signal']), use_container_width=True)
                
                st.divider()
                st.markdown("### 2. FASE POST-MATCH")
                f_post = st.file_uploader("Carica File RISULTATI", type=["csv", "xlsx", "xls"], key="u2b")
                
                if f_post:
                    df_post, err2 = load_and_prep(f_post)
                    if df_post is not None:
                        res_map = df_post.set_index('MatchID')['Real_Res'].to_dict()
                        
                        def check_outcome(row):
                            mid = row['MatchID']
                            real = res_map.get(mid, '-')
                            row['Real_Res'] = real
                            if real == '-':
                                row['Esito'] = 'Non Trovata'
                                row['Dettaglio'] = '-'
                                return row
                            
                            if real == row['Pick_Code']:
                                row['PNL'] = row['Quota'] - 1
                                row['Esito'] = 'WIN'
                                row['Dettaglio'] = '✅ Vinta'
                            else:
                                row['PNL'] = -1
                                row['Esito'] = 'LOSS'
                                if real == 'X': row['Dettaglio'] = '❌ Pareggio (X)'
                                elif row['Pick_Code'] == '1': row['Dettaglio'] = '❌ Vittoria Ospite (2)' 
                                elif row['Pick_Code'] == '2': row['Dettaglio'] = '❌ Vittoria Casa (1)'
                            return row
                        
                        results_df = targets_pre.apply(check_outcome, axis=1)
                        found_res = results_df[results_df['Esito'] != 'Non Trovata']
                        
                        st.write(f"Incrociate **{len(found_res)}** partite.")
                        if not found_res.empty:
                            pnl_tot = found_res['PNL'].sum()
                            st.metric("Profitto Reale", f"{pnl_tot:.2f} u", delta="Netto")
                            
                            # HIGH CONTRAST STYLE
                            def color_res(row):
                                if row['Esito'] == 'WIN': return ['background-color: #28a745; color: white; font-weight: bold'] * len(row)
                                if row['Esito'] == 'LOSS': return ['background-color: #dc3545; color: white; font-weight: bold'] * len(row)
                                return ['color: black'] * len(row)
                            
                            cols_post = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Dettaglio', 'PNL']
                            final_cols_post = [c for c in cols_post if c in found_res.columns]
                            
                            st.dataframe(found_res[final_cols_post].style.apply(color_res, axis=1), use_container_width=True)
                            
                            # LOSS BREAKDOWN TAB 2
                            st.markdown("#### 📉 Analisi Sconfitte (Perché abbiamo perso?)")
                            losses = found_res[found_res['Esito'] == 'LOSS']
                            if not losses.empty:
                                draws = len(losses[losses['Real_Res'] == 'X'])
                                opp_wins = len(losses) - draws
                                
                                cA, cB = st.columns(2)
                                cA.error(f"Pareggi (X): **{draws}**")
                                cB.error(f"Vittorie Avversario: **{opp_wins}**")
                            else:
                                st.success("Nessuna sconfitta rilevata!")
                                
                        else:
                            st.warning("Nessuna corrispondenza trovata tra i due file.")
        else:
            st.error(err1)
