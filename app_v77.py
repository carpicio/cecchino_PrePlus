import streamlit as st
import pandas as pd
import numpy as np

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Sniper V77 - Loss Analyzer", page_icon="📉", layout="wide")
st.title("📉 Sniper Bet V77 (Analisi delle Sconfitte)")
st.markdown("""
Questa versione ti mostra il **dettaglio delle scommesse perse**:
Quante volte abbiamo perso per un **Pareggio (X)** e quante per una **Sconfitta Netta**?
Questo dato è cruciale per valutare coperture come il *Draw No Bet*.
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
        'HFA': base_hfa, 'PNL': 0, 'Esito': 'Pending'
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
            r1 = row.get('place1a') or row.get('Place 1a') or row.get('place 1a') or row.get('pos1')
            r2 = row.get('place2d') or row.get('Place 2d') or row.get('place 2d') or row.get('pos2')
            if pd.notna(r1) and pd.notna(r2):
                try:
                    curr_hfa += (float(r2) - float(r1)) * 3
                    curr_hfa = max(0, min(curr_hfa, 200))
                except: pass
        
        res['HFA'] = int(curr_hfa)
        
        # Calcoli Probabilità
        f1, fx, f2 = no_margin(o1, ox, o2)
        ph, pa = get_probs(elo_h, elo_a, curr_hfa)
        rem = 1 - fx
        fin1 = rem * ph
        fin2 = rem * pa 
        
        ev1_perc = ((o1 * fin1) - 1) * 100
        ev2_perc = ((o2 * fin2) - 1) * 100
        
        # --- DETERMINA SEGNALE ---
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

        # Strategia 2 (Solo se non è già Strat 1)
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
        
        # --- CALCOLO PROFITTO ---
        if chosen_strat is not None and row.get('Real_Res') != '-':
            if row['Real_Res'] == target_pick_code:
                res['PNL'] = target_odds - 1 
                res['Esito'] = 'WIN'
            else:
                res['PNL'] = -1 
                res['Esito'] = 'LOSS'
        elif chosen_strat is not None:
             res['Esito'] = 'Pending'

    except: pass
    return pd.Series(res)

@st.cache_data(ttl=0)
def load_data(file, hfa, dyn, s1, s2):
    try:
        try:
            df = pd.read_csv(file, sep=None, encoding='latin1', on_bad_lines='skip', engine='python')
        except:
            file.seek(0)
            df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', engine='python')

        df.columns = df.columns.str.strip()
        
        # MAPPING ROBUSTO
        ren = {
            '1': 'cotaa', 'cotaa': 'cotaa', 'quota1': 'cotaa',
            'x': 'cotae', 'cotae': 'cotae', 'quotax': 'cotae',
            '2': 'cotad', 'cotad': 'cotad', 'quota2': 'cotad',
            'eloc': 'elohomeo', 'elohomeo': 'elohomeo',
            'eloo': 'eloawayo', 'eloawayo': 'eloawayo',
            'gfinc': 'scor1', 'gfino': 'scor2', 'score1': 'scor1', 'score2': 'scor2',
            'home': 'txtechipa1', 'away': 'txtechipa2', 'casa': 'txtechipa1', 'ospite': 'txtechipa2',
            'data': 'datameci', 'date': 'datameci',
            'league': 'league', 'campionato': 'league'
        }
        
        new = {}
        for c in df.columns:
            if c.lower() in ren: new[c] = ren[c.lower()]
        df = df.rename(columns=new)
        
        if 'cotaa' not in df.columns:
            return None, f"Colonne non trovate. Trovate: {list(df.columns)}"

        df = df.dropna(subset=['cotaa'])
        
        for c in ['scor1', 'scor2']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        
        df['Real_Res'] = '-'
        if 'scor1' in df.columns and 'scor2' in df.columns:
            mask = df['scor1'].notna() & df['scor2'].notna()
            df.loc[mask & (df['scor1'] > df['scor2']), 'Real_Res'] = '1'
            df.loc[mask & (df['scor1'] == df['scor2']), 'Real_Res'] = 'X'
            df.loc[mask & (df['scor1'] < df['scor2']), 'Real_Res'] = '2'
        
        if not df.empty:
            calc = df.apply(lambda r: calc_hybrid(r, hfa, dyn, s1, s2), axis=1)
            df = pd.concat([df, calc], axis=1)
        return df, None
    except Exception as e: return None, str(e)

# --- HELPER PER ANALISI SCONFITTE ---
def analyze_losses(df_strat):
    if df_strat.empty: return 0, 0, 0
    
    losses = df_strat[df_strat['Esito'] == 'LOSS']
    total_losses = len(losses)
    
    if total_losses == 0: return 0, 0, 0
    
    # Conta i Pareggi (X)
    draws = len(losses[losses['Real_Res'] == 'X'])
    
    # Conta le Sconfitte Nette (Tutto ciò che non è X e non è WIN)
    # Se ho giocato 2, la sconfitta netta è 1.
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

# --- MAIN APP ---
uploaded = st.file_uploader("Carica File CSV", type=["csv"])

if uploaded:
    df, err = load_data(uploaded, base_hfa, use_dyn, strat1, strat2)
    
    if df is not None:
        targets = df[df['Signal'] != 'SKIP'].copy()
        
        if not targets.empty:
            has_results = targets[targets['Real_Res'] != '-'].shape[0] > 0
            
            if has_results:
                # --- BACKTEST CON ANALISI SCONFITTE ---
                st.success(f"📊 BACKTEST COMPLETATO ({len(targets)} partite)")
                
                t_s1 = targets[targets['Signal'] == '✅ STRATEGIA 1']
                t_s2 = targets[targets['Signal'] == '🔹 STRATEGIA 2']
                
                # Calcoli Base
                pnl_s1 = t_s1['PNL'].sum()
                pnl_s2 = t_s2['PNL'].sum()
                
                # METRICHE PRINCIPALI
                st.markdown("### 💰 Profitto Totale")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric(f"{s1_name} (Bets)", len(t_s1))
                k2.metric(f"Profitto {s1_name}", f"{pnl_s1:.2f} u", delta="Reale")
                k3.metric(f"{s2_name} (Bets)", len(t_s2))
                k4.metric(f"Profitto {s2_name}", f"{pnl_s2:.2f} u", delta="Reale")
                
                st.markdown("---")
                
                # ANALISI DETTAGLIATA SCONFITTE
                st.markdown("### 📉 Analisi delle Perdite (Perché abbiamo perso?)")
                
                c1, c2 = st.columns(2)
                
                # Analisi S1
                tot_l1, draws1, direct1 = analyze_losses(t_s1)
                with c1:
                    st.info(f"**{s1_name}** - Dettaglio Sconfitte")
                    if tot_l1 > 0:
                        st.write(f"Totale Perse: **{tot_l1}**")
                        # Bar Chart semplice
                        chart_data = pd.DataFrame({
                            'Tipo': ['Pareggi (X)', 'Sconfitte Nette'],
                            'Quantità': [draws1, direct1]
                        })
                        st.bar_chart(chart_data.set_index('Tipo'))
                        
                        perc_x = (draws1 / tot_l1) * 100
                        if perc_x > 50:
                            st.warning(f"⚠️ Il **{perc_x:.1f}%** delle perdite è dovuto a Pareggi! Considera il **Draw No Bet**.")
                    else:
                        st.success("Nessuna sconfitta in questa strategia!")

                # Analisi S2
                tot_l2, draws2, direct2 = analyze_losses(t_s2)
                with c2:
                    st.info(f"**{s2_name}** - Dettaglio Sconfitte")
                    if tot_l2 > 0:
                        st.write(f"Totale Perse: **{tot_l2}**")
                        chart_data2 = pd.DataFrame({
                            'Tipo': ['Pareggi (X)', 'Sconfitte Nette'],
                            'Quantità': [draws2, direct2]
                        })
                        st.bar_chart(chart_data2.set_index('Tipo'))
                        
                        perc_x2 = (draws2 / tot_l2) * 100
                        if perc_x2 > 50:
                            st.warning(f"⚠️ Il **{perc_x2:.1f}%** delle perdite è dovuto a Pareggi! Considera il **Draw No Bet**.")
                    else:
                        st.success("Nessuna sconfitta in questa strategia!")

                st.markdown("---")
                st.markdown("### 📝 Lista Scommesse")
                
                def highlight_res(row):
                    if row['Esito'] == 'WIN': return ['background-color: #d1e7dd; color: #0f5132; font-weight: bold'] * len(row)
                    if row['Esito'] == 'LOSS': return ['background-color: #f8d7da; color: #842029; font-weight: bold'] * len(row)
                    return [''] * len(row)

                cols_view = ['Signal', 'datameci', 'league', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'Real_Res', 'Esito', 'PNL']
                final_cols = [c for c in cols_view if c in targets.columns]
                st.dataframe(targets[final_cols].style.apply(highlight_res, axis=1), use_container_width=True)
                
            else:
                # --- PREVISIONI FUTURE ---
                st.info(f"🔮 PREVISIONI FUTURE ({len(targets)} partite)")
                def highlight_strat(val):
                    if 'STRATEGIA 1' in str(val): return 'background-color: #c3e6cb; color: #155724; font-weight: bold'
                    elif 'STRATEGIA 2' in str(val): return 'background-color: #b6d4fe; color: #084298; font-weight: bold'
                    return ''
                cols_view = ['Signal', 'datameci', 'league', 'txtechipa1', 'txtechipa2', 'Pick', 'Quota', 'EV', 'HFA']
                final_cols = [c for c in cols_view if c in targets.columns]
                st.dataframe(targets[final_cols].style.applymap(highlight_strat, subset=['Signal']), use_container_width=True)

        else:
            st.warning("Nessuna partita soddisfa i criteri.")
            
        with st.expander("Vedi database completo"):
            st.dataframe(df)
    else:
        st.error(err)
