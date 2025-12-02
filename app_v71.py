import streamlit as st
import pandas as pd
import numpy as np

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V71 - Multi Target", page_icon="🎯", layout="wide")
st.title("🎯 Sniper Bet V71 (Gestione Multi-Strategia)")
st.markdown("""
Qui puoi configurare **due strategie di caccia** contemporaneamente.
Il sistema cercherà le partite che soddisfano i criteri della **Strategia 1** O della **Strategia 2**.
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

def calc_multi_sniper(row, base_hfa, dyn, strat1, strat2):
    res = {'Signal': 'SKIP', 'Strategia': '-', 'EV': 0, 'Pick': '-', 'HFA': base_hfa}
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
            r1 = row.get('place1a') or row.get('Place 1a') or row.get('place 1a')
            r2 = row.get('place2d') or row.get('Place 2d') or row.get('place 2d')
            
            if pd.notna(r1) and pd.notna(r2):
                try:
                    curr_hfa += (float(r2) - float(r1)) * 3
                    curr_hfa = max(0, min(curr_hfa, 200))
                except: pass
        
        res['HFA'] = int(curr_hfa)
        
        # Calcoli Probabilità e EV
        f1, fx, f2 = no_margin(o1, ox, o2)
        ph, pa = get_probs(elo_h, elo_a, curr_hfa)
        rem = 1 - fx
        fin1 = rem * ph
        fin2 = rem * pa # Probabilità Ospite
        
        ev1_perc = ((o1 * fin1) - 1) * 100
        ev2_perc = ((o2 * fin2) - 1) * 100
        
        # --- VERIFICA STRATEGIA 1 ---
        match_s1 = False
        if strat1['active']:
            # Verifica Pick
            target_ev = 0
            target_odds = 0
            if strat1['pick'] == '1 (Casa)':
                target_ev = ev1_perc
                target_odds = o1
            elif strat1['pick'] == '2 (Ospite)':
                target_ev = ev2_perc
                target_odds = o2
            
            # Verifica Range
            if (strat1['min_ev'] <= target_ev <= strat1['max_ev']) and \
               (strat1['min_odd'] <= target_odds <= strat1['max_odd']):
                res['Signal'] = '✅ STRATEGIA 1'
                res['Strategia'] = strat1['name']
                res['Pick'] = strat1['pick']
                res['EV'] = round(target_ev, 2)
                res['Quota'] = target_odds
                match_s1 = True

        # --- VERIFICA STRATEGIA 2 (Se non ha già matchato la 1 o se vogliamo mostrarle tutte) ---
        if strat2['active'] and not match_s1:
            target_ev = 0
            target_odds = 0
            if strat2['pick'] == '1 (Casa)':
                target_ev = ev1_perc
                target_odds = o1
            elif strat2['pick'] == '2 (Ospite)':
                target_ev = ev2_perc
                target_odds = o2
            
            if (strat2['min_ev'] <= target_ev <= strat2['max_ev']) and \
               (strat2['min_odd'] <= target_odds <= strat2['max_odd']):
                res['Signal'] = '🔹 STRATEGIA 2'
                res['Strategia'] = strat2['name']
                res['Pick'] = strat2['pick']
                res['EV'] = round(target_ev, 2)
                res['Quota'] = target_odds

    except: pass
    return pd.Series(res)

@st.cache_data(ttl=0)
def load_data(file, hfa, dyn, s1, s2):
    try:
        df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', engine='python')
        df.columns = df.columns.str.strip()
        ren = {
            '1': 'cotaa', '2': 'cotad', 'x': 'cotae', 'X': 'cotae', 
            'eloc': 'elohomeo', 'eloo': 'eloawayo',
            'home': 'txtechipa1', 'away': 'txtechipa2', 'casa': 'txtechipa1', 'ospite': 'txtechipa2'
        }
        new = {}
        for c in df.columns:
            if c.lower() in ren: new[c] = ren[c.lower()]
        df = df.rename(columns=new)
        df = df.dropna(subset=['cotaa'])
        
        if not df.empty:
            calc = df.apply(lambda r: calc_multi_sniper(r, hfa, dyn, s1, s2), axis=1)
            df = pd.concat([df, calc], axis=1)
        return df, None
    except Exception as e: return None, str(e)

# --- UI SIDEBAR ---
st.sidebar.header("⚙️ Configurazione Globale")
base_hfa = st.sidebar.number_input("HFA Base", 90, step=10)
use_dyn = st.sidebar.checkbox("Usa HFA Dinamico", True)

st.sidebar.markdown("---")
st.sidebar.header("🏹 STRATEGIA 1 (Primary)")
s1_active = st.sidebar.checkbox("Attiva Strategia 1", True)
s1_name = st.sidebar.text_input("Nome", "Cluster Ospite Gold", key="n1")
s1_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=1, key="p1")
s1_min_odd, s1_max_odd = st.sidebar.slider("Range Quota", 1.2, 5.0, (2.06, 2.80), key="o1")
s1_min_ev, s1_max_ev = st.sidebar.slider("Range EV (%)", -5.0, 30.0, (11.0, 19.5), key="e1")

strat1 = {
    'active': s1_active, 'name': s1_name, 'pick': s1_pick,
    'min_odd': s1_min_odd, 'max_odd': s1_max_odd,
    'min_ev': s1_min_ev, 'max_ev': s1_max_ev
}

st.sidebar.markdown("---")
st.sidebar.header("🗡️ STRATEGIA 2 (Secondary)")
s2_active = st.sidebar.checkbox("Attiva Strategia 2", False)
s2_name = st.sidebar.text_input("Nome", "Nuovo Cluster", key="n2")
s2_pick = st.sidebar.selectbox("Punta su", ["1 (Casa)", "2 (Ospite)"], index=0, key="p2")
s2_min_odd, s2_max_odd = st.sidebar.slider("Range Quota", 1.2, 5.0, (1.50, 2.20), key="o2")
s2_min_ev, s2_max_ev = st.sidebar.slider("Range EV (%)", -5.0, 30.0, (2.0, 10.0), key="e2")

strat2 = {
    'active': s2_active, 'name': s2_name, 'pick': s2_pick,
    'min_odd': s2_min_odd, 'max_odd': s2_max_odd,
    'min_ev': s2_min_ev, 'max_ev': s2_max_ev
}

# --- MAIN APP ---
uploaded = st.file_uploader("Carica File Partite Future (CSV)", type=["csv"])

if uploaded:
    df, err = load_data(uploaded, base_hfa, use_dyn, strat1, strat2)
    
    if df is not None:
        # Filtra risultati
        targets = df[df['Signal'] != 'SKIP'].copy()
        
        if not targets.empty:
            st.success(f"🎯 TROVATE {len(targets)} OPPORTUNITÀ!")
            
            # Styling differenziato
            def highlight_strat(val):
                if 'STRATEGIA 1' in str(val):
                    return 'background-color: #d4edda; color: #155724; font-weight: bold' # Verde
                elif 'STRATEGIA 2' in str(val):
                    return 'background-color: #cce5ff; color: #004085; font-weight: bold' # Blu
                return ''

            cols_show = ['Strategia', 'datameci', 'league', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'EV', 'HFA']
            final_cols = [c for c in cols_show if c in targets.columns]
            
            st.dataframe(
                targets[final_cols].style.applymap(highlight_strat, subset=['Signal']),
                use_container_width=True,
                height=600
            )
            
            # Statistiche veloci
            c1, c2 = st.columns(2)
            n_s1 = len(targets[targets['Signal'] == '✅ STRATEGIA 1'])
            n_s2 = len(targets[targets['Signal'] == '🔹 STRATEGIA 2'])
            c1.metric(f"Totale {s1_name}", n_s1)
            c2.metric(f"Totale {s2_name}", n_s2)
            
        else:
            st.warning("Nessuna partita soddisfa i criteri delle strategie attive.")
            
        with st.expander("Vedi database completo"):
            st.dataframe(df)
    else:
        st.error(f"Errore: {err}")
