import streamlit as st
import pandas as pd
import numpy as np
import io

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V98 - Final Stable", page_icon="🚀", layout="wide")
st.title("🚀 Sniper Bet V98 (Final Stable)")
st.markdown("""
**Versione Definitiva:**
- Analisi Storica con Report Finanziario e Risultati Esatti.
- Verifica Pre/Post Match.
- Export Excel funzionante.
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
                res['Pick'] = strat2['pick'] 
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
                res['Signal'] = "🔹 S2"
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
            df.loc[mask, 'Correct_Score'] = df.loc[mask, 'scor1'].astype(int).astype(str) + "-" + df.loc[mask, 'scor2'].astype(int).astype(str)

        return df, None
    except Exception as e: return None, str(e)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sniper_Data')
    return output.getvalue()

# --- ANALYTICS ---
def analyze_segment(df_seg, label):
    if df_seg.empty:
        st.warning(f"{label}: Nessuna partita trovata.")
        return

    st.markdown(f"### 📌 {label}")
    total = len(df_seg)
    
    res_counts = df_seg['Real_Res'].value_counts()
    n1 = res_counts.get('1', 0)
    nx = res_counts.get('X', 0)
    n2 = res_counts.get('2', 0)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Totale", total)
    col2.metric("Vittorie 1", f"{n1} ({n1/total*100:.1f}%)")
    col3.metric("Pareggi X", f"{nx} ({nx/total*100:.1f}%)")
    col4.metric("Vittorie 2", f"{n2} ({n2/total*100:.1f}%)")
    
    # ROI
    pnl_1 = df_seg.apply(lambda r: r['cotaa'] -
