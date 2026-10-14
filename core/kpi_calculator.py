"""
kpi_calculator.py — Calcul des indicateurs de performance (KPIs) globaux.

Fournit une vue synthétique de la santé du stock :
taux de service, valeur immobilisée, rotation, alertes par niveau.
"""

import pandas as pd
import numpy as np
from typing import Any


def compute_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcule les KPIs globaux à partir du DataFrame enrichi.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame enrichi par inventory_engine.compute_all()

    Returns
    -------
    dict avec :
        - taux_service_global : float (0-1)
            Proportion d'articles dont le stock ≥ ROP
        - valeur_stock_total : float
            Σ(stock_actuel × prix_unitaire) en MAD
        - valeur_par_segment : dict {'A': float, 'B': float, 'C': float}
            Valeur immobilisée par segment ABC
        - taux_rotation_moyen : float
            Ratio moyen consommation_annuelle / stock_actuel
        - nb_alertes : dict {'CRITIQUE': int, 'PRÉVENTIF': int, ...}
            Nombre d'articles par statut
        - articles_en_rupture : int
            Nombre d'articles avec stock < stock_sécurité
        - couverture_moyenne_jours : float
            Nombre moyen de jours de stock restant
        - cout_total_immobilise : float
            Valeur totale × taux de possession moyen
    """
    kpis: dict[str, Any] = {}

    # --- 1. Taux de service global ---
    # Proportion d'articles dont le stock couvre au-dessus du ROP
    # Approximation : articles "OK" / total articles actifs
    articles_actifs = df[df["consommation_moyenne_jour"] >= 0.01]
    if len(articles_actifs) > 0:
        nb_ok = (articles_actifs["stock_actuel"] >= articles_actifs["rop"]).sum()
        kpis["taux_service_global"] = round(nb_ok / len(articles_actifs), 4)
    else:
        kpis["taux_service_global"] = 1.0

    # --- 2. Valeur totale du stock (capital immobilisé) ---
    # Valeur = Σ(stock_actuel × prix_unitaire)
    df_calc = df.copy()
    df_calc["valeur_stock"] = df_calc["stock_actuel"] * df_calc["prix_unitaire"]
    kpis["valeur_stock_total"] = round(df_calc["valeur_stock"].sum(), 2)

    # --- 3. Valeur par segment ABC ---
    valeur_par_seg = {}
    for seg in ["A", "B", "C"]:
        masque = df_calc["segment_abc"] == seg
        valeur_par_seg[seg] = round(df_calc.loc[masque, "valeur_stock"].sum(), 2)
    kpis["valeur_par_segment"] = valeur_par_seg

    # --- 4. Taux de rotation moyen ---
    # Rotation = Consommation annuelle / Stock moyen
    # On utilise stock_actuel comme proxy du stock moyen
    rotations = []
    for _, row in df_calc.iterrows():
        if row["stock_actuel"] > 0 and row["consommation_moyenne_jour"] > 0:
            rotation = (row["consommation_moyenne_jour"] * 365) / row["stock_actuel"]
            rotations.append(rotation)
    kpis["taux_rotation_moyen"] = round(np.mean(rotations), 2) if rotations else 0.0

    # --- 5. Nombre d'alertes par statut ---
    statuts = df["statut_stock"].value_counts().to_dict()
    kpis["nb_alertes"] = {
        "CRITIQUE": statuts.get("CRITIQUE", 0),
        "PRÉVENTIF": statuts.get("PRÉVENTIF", 0),
        "OK": statuts.get("OK", 0),
        "DORMANT": statuts.get("DORMANT", 0),
    }

    # --- 6. Articles en rupture ---
    # Un article est considéré en rupture si stock < stock_sécurité
    kpis["articles_en_rupture"] = int(
        (df["stock_actuel"] < df["stock_securite"]).sum()
    )

    # --- 7. Couverture moyenne en jours ---
    # Jours = stock / consommation_moyenne_jour (pour articles actifs)
    couvertures = []
    for _, row in articles_actifs.iterrows():
        if row["consommation_moyenne_jour"] > 0:
            couvertures.append(row["stock_actuel"] / row["consommation_moyenne_jour"])
    kpis["couverture_moyenne_jours"] = (
        round(np.mean(couvertures), 1) if couvertures else 0.0
    )

    # --- 8. Coût total de possession ---
    taux_moyen = df["taux_possession"].mean() if len(df) > 0 else 0.25
    kpis["cout_total_immobilise"] = round(
        kpis["valeur_stock_total"] * taux_moyen, 2
    )

    return kpis
