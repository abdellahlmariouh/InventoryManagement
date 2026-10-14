"""
simulator.py — Simulateur de scénarios what-if pour la gestion de stock.

Permet de tester l'impact de variations sur :
- Le délai fournisseur (lead time)
- Le taux de service cible
- Le niveau de demande
Sur les paramètres SS, ROP, EOQ et le coût total.
"""

import pandas as pd
import numpy as np
from statistics import NormalDist


def simulate(
    df: pd.DataFrame,
    delta_delai: float = 0.0,
    delta_service: float = 0.0,
    delta_demande: float = 0.0,
    cout_rupture_facteur: float = 2.0,  # Multiplicateur du prix unitaire pour le coût de rupture
) -> pd.DataFrame:
    """
    Simulateur avancé incluant le coût de rupture (Loss Function).
    """
    df = df.copy()

    # --- Préparation des variables ---
    normal = NormalDist()
    z_actuel_val = df["z_score"].iloc[0] if "z_score" in df and len(df) > 0 else normal.inv_cdf(0.95)
    taux_service_actuel = normal.cdf(z_actuel_val)
    taux_service_simule = np.clip(taux_service_actuel + delta_service, 0.50, 0.9999)
    z_simule = normal.inv_cdf(taux_service_simule)

    L_actuel = df["delai_fournisseur_jours"]
    L_simule = np.maximum(L_actuel + delta_delai, 1.0)

    D_actuel = df["consommation_moyenne_jour"]
    D_simule = np.maximum(D_actuel * (1 + delta_demande), 0.0)

    sigma_d = df["ecart_type_consommation"]
    sigma_L = df["delai_ecart_type"]

    # --- Écarts-types combinés (Demand during Lead Time) ---
    # sigma_DL = √(L × σ_d² + D² × σ_L²)
    sigma_DL_actuel = np.sqrt(L_actuel * sigma_d**2 + D_actuel**2 * sigma_L**2)
    sigma_DL_simule = np.sqrt(L_simule * sigma_d**2 + D_simule**2 * sigma_L**2)

    # --- Recalcul des niveaux ---
    ss_actuel = df["stock_securite"]
    ss_simule = z_simule * sigma_DL_simule

    rop_simule = D_simule * L_simule + ss_simule

    S = df["cout_commande"]
    C = df["prix_unitaire"]
    i = df["taux_possession"]
    denom = (C * i).replace(0, np.nan)
    
    eoq_simule = np.ceil(np.sqrt(2 * D_simule * 365 * S / denom).fillna(0)).astype(int)

    # --- CALCULS DES COÛTS (BUSINESS LOGIC) ---
    def _calculer_details_couts(d_jour, eoq_v, ss_v, s_v, c_v, i_v, z_v, sigma_dl_v):
        d_ann = d_jour * 365
        eoq_safe = np.where(eoq_v > 0, eoq_v, 1)
        
        # 1. Coût de passation (Ordering)
        c_cmd = (d_ann / eoq_safe) * s_v
        
        # 2. Coût de possession (Holding)
        # Inclut le stock cyclique (EOQ/2) et le stock de sécurité (SS)
        c_poss = (eoq_v / 2 + ss_v) * c_v * i_v
        
        # 3. Coût de rupture (Shortage)
        # Espérance de rupture par cycle : E(z) = σ_DL × G(z)
        # G(z) = f(z) - z(1 - F(z))
        gz = normal.pdf(z_v) - z_v * (1 - normal.cdf(z_v))
        rupture_par_cycle = sigma_dl_v * gz
        nb_cycles_an = d_ann / eoq_safe
        rupture_annuelle = rupture_par_cycle * nb_cycles_an
        
        cout_unitaire_rupture = c_v * cout_rupture_facteur
        c_rupt = rupture_annuelle * cout_unitaire_rupture
        
        return c_cmd, c_poss, c_rupt

    # Coûts actuels
    c_cmd_act, c_poss_act, c_rupt_act = _calculer_details_couts(
        D_actuel, df["eoq"], ss_actuel, S, C, i, z_actuel_val, sigma_DL_actuel
    )
    
    # Coûts simulés
    c_cmd_sim, c_poss_sim, c_rupt_sim = _calculer_details_couts(
        D_simule, eoq_simule, ss_simule, S, C, i, z_simule, sigma_DL_simule
    )

    result = pd.DataFrame({
        "article_id": df["article_id"],
        "article_nom": df["article_nom"],
        "segment_abc": df.get("segment_abc", "C"),
        "ss_actuel": np.round(ss_actuel, 1),
        "ss_simule": np.round(ss_simule, 1),
        "rop_actuel": np.round(df["rop"], 1),
        "rop_simule": np.round(rop_simule, 1),
        "capital_actuel": np.round(ss_actuel * C, 0),
        "capital_simule": np.round(ss_simule * C, 0),
        "cout_cmd_actuel": np.round(c_cmd_act, 0),
        "cout_cmd_simule": np.round(c_cmd_sim, 0),
        "cout_poss_actuel": np.round(c_poss_act, 0),
        "cout_poss_simule": np.round(c_poss_sim, 0),
        "cout_rupt_actuel": np.round(c_rupt_act, 0),
        "cout_rupt_simule": np.round(c_rupt_sim, 0),
        "cout_total_actuel": np.round(c_cmd_act + c_poss_act + c_rupt_act, 0),
        "cout_total_simule": np.round(c_cmd_sim + c_poss_sim + c_rupt_sim, 0),
    })

    return result

def get_simulation_summary(df_sim: pd.DataFrame) -> dict:
    """Agrège les résultats de la simulation pour le tableau de bord."""
    summary = {
        "total_cout_actuel": df_sim["cout_total_actuel"].sum(),
        "total_cout_simule": df_sim["cout_total_simule"].sum(),
        "total_capital_actuel": df_sim["capital_actuel"].sum(),
        "total_capital_simule": df_sim["capital_simule"].sum(),
        "total_rupture_actuel": df_sim["cout_rupt_actuel"].sum(),
        "total_rupture_simule": df_sim["cout_rupt_simule"].sum(),
        "delta_cout_pct": 0,
        "delta_capital": 0
    }
    
    if summary["total_cout_actuel"] > 0:
        summary["delta_cout_pct"] = (summary["total_cout_simule"] - summary["total_cout_actuel"]) / summary["total_cout_actuel"] * 100
    
    summary["delta_capital"] = summary["total_capital_simule"] - summary["total_capital_actuel"]
    
    return summary
