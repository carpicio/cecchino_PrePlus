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
st.set_page_config(page_title="Sniper V82 - Dual Core", page_icon="⚔️", layout="wide")
st.title("⚔️ Sniper Bet V82 (Studio & Verifica)")
st.markdown("""
**Scegli la modalità di lavoro:**
1. **🧪 STUDIO STORICO:** Carica un file storico completo per testare e trovare i range vincenti.
2. **⚖️ VERIFICA (2 File):** Carica il file PRE-MATCH e il file RISULTATI separati per verificare le giocate.
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
        'HFA': base_hfa, 'PNL': 0, 'Esito': 'Pending', 'Dettaglio': '-'
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
        chosen_strat = None
        target_odds = 0
        target_pick_code = '' 
        
        # Strategia 1
        if strat1['active']:
            ev = ev1_perc if strat1['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat1['pick'] == '1 (Casa)' else o2
            if (strat1['min_ev'] <= ev <= strat1['max_ev']) and \
               (strat1['min_odd'] <= odd <= strat1['max_odd']):
                chosen_strat = 1
                res['Signal'] = '✅ STRATEGIA 1'
                res['Strategia'] = strat1['name']
                res['Pick'] = strat1['pick']
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                target_odds = odd
                target_pick_code = '1' if strat1['pick'] == '1 (Casa)' else '2'

        # Strategia 2
        if strat2['active'] and chosen_strat is None:
            ev = ev1_perc if strat2['pick'] == '1 (Casa)' else ev2_perc
            odd = o1 if strat2['pick'] == '1 (Casa)' else o2
            if (strat2['min_ev'] <= ev <= strat2['max_ev']) and \
               (strat2['min_odd'] <= odd <= strat2['max_odd']):
                chosen_strat = 2
                res['Signal'] = '🔹 STRATEGIA 2'
                res['Strategia'] = strat2['name']
                res['Pick'] = strat2['pick']
                res['EV'] = round(ev, 2)
                res['Quota'] = odd
                target_odds = odd
                target_pick_code = '1' if strat2['pick'] == '1 (Casa)' else '2'
        
        # --- CALCOLO ESITO DETTAGLIATO ---
        if chosen_strat is not None and row.get('Real_Res') != '-':
            real = row['Real_Res']
            
            if real == target_pick_code:
                res['PNL'] = target_odds - 1 
                res['Esito'] = 'WIN'
                res['Dettaglio'] = 'Vinta'
            else:
                res['PNL'] = -1 
                res['Esito'] = 'LOSS'
                # Dettaglio della sconfitta
                if real == 'X':
                    res['Dettaglio'] = 'Pareggio (X)'
                elif target_pick_code == '1' and real == '2':
                    res['Dettaglio'] = 'Vittoria Ospite (2)'
                elif target_pick_code == '2' and real == '1':
                    res['Dettaglio'] = 'Vittoria Casa (1)'
                    
        elif chosen_strat is not None:
             res['Esito'] = 'Pending'

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
            df = pd.read_excel(file)
        
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
            
        # Match ID Normalizzato (per incrocio file)
        # Rimuove spazi e mette minuscolo per creare una chiave unica
        if 'txtechipa1' in df.columns and 'txtechipa2' in df.columns:
            df['MatchID'] = df['txtechipa1'].astype(str).str.lower().str.replace(' ', '') + "-" + \
                            df['txtechipa2'].astype(str).str.lower().str.replace(' ', '')
        
        # Determina Risultato (se c'è)
        df['Real_Res'] = '-'
        if 'scor1' in df.columns and 'scor2' in df.columns:
            mask = df['scor1'].notna() & df['scor2'].notna()
            df.loc[mask & (df['scor1'] > df['scor2']), 'Real_Res'] = '1'
            df.loc[mask & (df['scor1'] == df['scor2']), 'Real_Res'] = 'X'
            df.loc[mask & (df['scor1'] < df['scor2']), 'Real_Res'] = '2'

        return df, None
    except Exception as e: return None, str(e)

# --- UI SIDEBAR ---
st.sidebar.header("⚙️ Configurazione")
base_hfa = st.sidebar.number_input("HFA Base", 90, step=10)
use_dyn = st.sidebar.checkbox("Usa HFA Dinamico", True)

st.sidebar.markdown("---")
st.sidebar.header("🏹 STRATEGIA 1")
s1_active = st.sidebar.checkbox("Attiva S1", True)
s1_name = st.sidebar.text_input("Nome S1", "Cluster Ospite", key="n1")
s1_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=1, key="p1")
s1_min_odd, s1_max_odd = st.sidebar.slider("Quote S1", 1.2, 5.0, (2.06, 2.80), key="o1")
s1_min_ev, s1_max_ev = st.sidebar.slider("EV S1 (%)", -5.0, 30.0, (11.0, 19.5), key="e1")
strat1 = {'active': s1_active, 'name': s1_name, 'pick': s1_pick, 'min_odd': s1_min_odd, 'max_odd': s1_max_odd, 'min_ev': s1_min_ev, 'max_ev': s1_max_ev}

st.sidebar.markdown("---")
st.sidebar.header("🗡️ STRATEGIA 2")
s2_active = st.sidebar.checkbox("Attiva S2", True)
s2_name = st.sidebar.text_input("Nome S2", "Cluster Casa", key="n2")
s2_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=0, key="p2")
s2_min_odd, s2_max_odd = st.sidebar.slider("Quote S2", 1.2, 5.0, (1.80, 2.20), key="o2")
s2_min_ev, s2_max_ev = st.sidebar.slider("EV S2 (%)", -5.0, 30.0, (5.0, 15.0), key="e2")
strat2 = {'active': s2_active, 'name': s2_name, 'pick': s2_pick, 'min_odd': s2_min_odd, 'max_odd': s2_max_odd, 'min_ev': s2_min_ev, 'max_ev': s2_max_ev}

# --- TABS ---
tab1, tab2 = st.tabs(["🧪 1. STUDIO STORICO (Single File)", "⚖️ 2. VERIFICA (Prematch + Postmatch)"])

# --- TAB 1: STUDIO STORICO ---
with tab1:
    st.info("Carica UN SOLO FILE che contiene già i risultati per studiare le strategie.")
    file_studio = st.file_uploader("Carica File Storico", type=["csv", "xlsx", "xls"], key="u1")
    
    if file_studio:
        df_stud, err = load_and_prep(file_studio)
        if df_stud is not None:
            # Calcoli
            calc_s = df_stud.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_s = pd.concat([df_stud, calc_s], axis=1)
            targets_s = final_s[final_s['Signal'] != 'SKIP']
            
            if not targets_s.empty and targets_s[targets_s['Real_Res'] != '-'].shape[0] > 0:
                st.success(f"Analisi su {len(targets_s)} partite concluse")
                
                # Totali
                pnl = targets_s['PNL'].sum()
                st.metric("Profitto Totale", f"{pnl:.2f} u", delta="Reale")
                
                # Dettaglio
                cols = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                
                def color_rows(row):
                    if row['Esito'] == 'WIN': return ['background-color: #d1e7dd; color: #0f5132'] * len(row)
                    if row['Esito'] == 'LOSS': return ['background-color: #f8d7da; color: #842029'] * len(row)
                    return [''] * len(row)
                    
                st.dataframe(targets_s[cols].style.apply(color_rows, axis=1), use_container_width=True)
            else:
                st.warning("Nessuna scommessa trovata o nessun risultato nel file.")

# --- TAB 2: VERIFICA DUE FILE ---
with tab2:
    st.info("Carica PRIMA il file con le quote (Prematch) e POI il file con i risultati (Postmatch) per incrociarli.")
    c1, c2 = st.columns(2)
    f_pre = c1.file_uploader("1. File PRE-MATCH (Quote)", type=["csv", "xlsx", "xls"], key="u2a")
    f_post = c2.file_uploader("2. File POST-MATCH (Risultati)", type=["csv", "xlsx", "xls"], key="u2b")
    
    if f_pre and f_post:
        df_pre, err1 = load_and_prep(f_pre)
        df_post, err2 = load_and_prep(f_post)
        
        if df_pre is not None and df_post is not None:
            # 1. Calcola Strategia sul Prematch
            calc_pre = df_pre.apply(lambda r: calc_hybrid(r, base_hfa, use_dyn, strat1, strat2), axis=1)
            final_pre = pd.concat([df_pre, calc_pre], axis=1)
            targets_pre = final_pre[final_pre['Signal'] != 'SKIP'].copy()
            
            if not targets_pre.empty:
                # 2. Crea Dizionario Risultati dal Postmatch (MatchID -> Real_Res)
                # Assumiamo che df_post abbia MatchID e Real_Res
                res_map = df_post.set_index('MatchID')['Real_Res'].to_dict()
                
                # 3. Applica Risultati
                def apply_match_result(row):
                    mid = row['MatchID']
                    real_res = res_map.get(mid, '-') # Cerca risultato nel file 2
                    
                    row['Real_Res'] = real_res
                    if real_res == '-':
                        row['Esito'] = 'Not Found'
                        row['Dettaglio'] = 'Match non trovato nel file risultati'
                        row['PNL'] = 0
                        return row
                        
                    # Ricalcola Esito
                    target_code = '1' if '1' in str(row['Pick']) else '2'
                    
                    if real_res == target_code:
                        row['PNL'] = row['Quota'] - 1
                        row['Esito'] = 'WIN'
                        row['Dettaglio'] = 'Vinta'
                    else:
                        row['PNL'] = -1
                        row['Esito'] = 'LOSS'
                        if real_res == 'X': row['Dettaglio'] = 'Pareggio (X)'
                        elif target_code == '1': row['Dettaglio'] = 'Vittoria Ospite (2)'
                        elif target_code == '2': row['Dettaglio'] = 'Vittoria Casa (1)'
                    return row

                # Applica logica incrocio
                final_verify = targets_pre.apply(apply_match_result, axis=1)
                
                # Risultati Incrocio
                found = final_verify[final_verify['Esito'] != 'Not Found']
                
                st.divider()
                st.subheader(f"📊 RISULTATO VERIFICA ({len(found)} match incrociati)")
                
                if not found.empty:
                    pnl_tot = found['PNL'].sum()
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Giocate Totali", len(found))
                    k2.metric("Vinte", len(found[found['Esito']=='WIN']))
                    k3.metric("Profitto Netto", f"{pnl_tot:.2f} u", delta="Reale")
                    
                    def color_rows_v(row):
                        if row['Esito'] == 'WIN': return ['background-color: #d1e7dd; color: #0f5132'] * len(row)
                        if row['Esito'] == 'LOSS': return ['background-color: #f8d7da; color: #842029'] * len(row)
                        return [''] * len(row)

                    cols = ['Signal', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'Dettaglio', 'PNL']
                    st.dataframe(found[cols].style.apply(color_rows_v, axis=1), use_container_width=True)
                else:
                    st.warning("Nessuna partita del file Prematch è stata trovata nel file Postmatch. Verifica che i nomi delle squadre siano uguali.")
            else:
                st.warning("Il file Prematch non contiene giocate valide per le strategie selezionate.")
