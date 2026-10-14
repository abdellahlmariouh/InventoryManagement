"""
inventory_engine.py — Moteur de calcul des paramètres de gestion de stock.

Implémente les formules classiques de gestion de stock :
- Stock de sécurité (Safety Stock) avec modèle probabiliste
- Point de réapprovisionnement (Reorder Point — ROP)
- Quantité économique de commande (EOQ — Wilson)
- Segmentation ABC par valeur cumulée (Pareto)
- Segmentation XYZ par coefficient de variation
- Classification du statut de stock
"""

import pandas as pd
import numpy as np
from statistics import NormalDist


def compute_all(df: pd.DataFrame, taux_service: float = 0.95) -> pd.DataFrame:
    """
    Enrichit le DataFrame avec toutes les colonnes de gestion de stock calculées.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame issu de data_loader avec les colonnes obligatoires.
    taux_service : float
        Niveau de service cible (probabilité de non-rupture).
        Par défaut 0.95 (95%).

    Returns
    -------
    pd.DataFrame
        DataFrame enrichi avec les colonnes :
        z_score, stock_securite, rop, eoq, segment_abc, segment_xyz,
        segment, statut_stock
    """
    df = df.copy()

    # --- 1. Z-Score pour le taux de service ---
    # Z = Φ⁻¹(taux_service) — quantile de la loi normale standard
    # Source : Silver, Pyke & Thomas (2017), "Inventory and Production Management"
    z = NormalDist().inv_cdf(taux_service)
    df["z_score"] = z

    # --- 2. Stock de sécurité (Safety Stock) ---
    # Formule combinée tenant compte de la variabilité de la demande ET du lead time
    # SS = Z × √(L × σ_d² + D² × σ_L²)
    # Où :
    #   L    = lead time moyen (delai_fournisseur_jours)
    #   σ_d  = écart-type de la demande journalière (ecart_type_consommation)
    #   D    = demande journalière moyenne (consommation_moyenne_jour)
    #   σ_L  = écart-type du lead time (delai_ecart_type)
    # Source : Chopra & Meindl (2019), "Supply Chain Management", ch. 12
    L = df["delai_fournisseur_jours"]
    sigma_d = df["ecart_type_consommation"]
    D = df["consommation_moyenne_jour"]
    sigma_L = df["delai_ecart_type"]

    df["stock_securite"] = z * np.sqrt(
        L * sigma_d**2 + D**2 * sigma_L**2
    )

    # --- 3. Point de réapprovisionnement (Reorder Point — ROP) ---
    # ROP = D_moy × L + SS
    # Commande déclenchée quand stock atteint ce niveau
    df["rop"] = D * L + df["stock_securite"]

    # --- 4. Quantité économique de commande (EOQ — formule de Wilson) ---
    # EOQ = √(2 × D_annuel × S / (C × i))
    # Où :
    #   D_annuel = demande annuelle = D × 365
    #   S        = coût fixe par commande (cout_commande)
    #   C        = prix unitaire (prix_unitaire)
    #   i        = taux de possession annuel (taux_possession)
    # Source : Harris (1913), "How many parts to make at once"
    D_annuel = D * 365
    S = df["cout_commande"]
    C = df["prix_unitaire"]
    i = df["taux_possession"]

    # Protection division par zéro : si C*i = 0, EOQ = 0
    denominateur = C * i
    denominateur = denominateur.replace(0, np.nan)
    df["eoq"] = np.sqrt(2 * D_annuel * S / denominateur).fillna(0)

    # Arrondir EOQ à l'entier supérieur (on commande des unités entières)
    df["eoq"] = np.ceil(df["eoq"]).astype(int)

    # --- 5. Segmentation ABC (Pareto par valeur consommée) ---
    # Valeur consommée annuelle = D_annuel × prix_unitaire
    # A : 0-80% de la valeur cumulée
    # B : 80-95%
    # C : 95-100%
    df["valeur_annuelle"] = D_annuel * C
    df = _compute_abc(df)

    # --- 6. Segmentation XYZ (par coefficient de variation) ---
    # CV = σ_d / D_moy
    # X : CV < 0.2  (demande stable)
    # Y : 0.2 ≤ CV < 0.5  (demande modérée)
    # Z : CV ≥ 0.5  (demande erratique)
    df = _compute_xyz(df)

    # --- 7. Segment combiné ---
    df["segment"] = df["segment_abc"] + df["segment_xyz"]

    # --- 8. Statut du stock ---
    df = _compute_statut(df)

    return df


def _compute_abc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule la segmentation ABC basée sur la valeur consommée annuelle (Pareto).

    Seuils :
        A : articles représentant 0–80% de la valeur cumulée
        B : articles représentant 80–95%
        C : articles représentant 95–100%
    """
    df = df.copy()
    # Trier par valeur annuelle décroissante
    df = df.sort_values("valeur_annuelle", ascending=False).reset_index(drop=True)

    total_valeur = df["valeur_annuelle"].sum()
    if total_valeur == 0:
        df["segment_abc"] = "C"
        df["pct_valeur_cumulee"] = 0.0
        return df

    df["pct_valeur_cumulee"] = df["valeur_annuelle"].cumsum() / total_valeur

    conditions = [
        df["pct_valeur_cumulee"] <= 0.80,
        df["pct_valeur_cumulee"] <= 0.95,
    ]
    choix = ["A", "B"]
    df["segment_abc"] = np.select(conditions, choix, default="C")

    return df


def _compute_xyz(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule la segmentation XYZ basée sur le coefficient de variation (CV).

    CV = écart_type / moyenne
        X : CV < 0.2   (stable)
        Y : 0.2 ≤ CV < 0.5 (variable)
        Z : CV ≥ 0.5   (erratique)
    """
    df = df.copy()
    # CV = σ / μ — protection div/0 si consommation = 0
    df["cv"] = np.where(
        df["consommation_moyenne_jour"] > 0,
        df["ecart_type_consommation"] / df["consommation_moyenne_jour"],
        999.0,  # Si pas de consommation → considéré comme erratique (Z)
    )

    conditions = [
        df["cv"] < 0.2,
        df["cv"] < 0.5,
    ]
    choix = ["X", "Y"]
    df["segment_xyz"] = np.select(conditions, choix, default="Z")

    return df


def _compute_statut(df: pd.DataFrame) -> pd.DataFrame:
    """
    Détermine le statut du stock de chaque article.

    Règles :
        CRITIQUE    : stock_actuel < stock_sécurité
        PRÉVENTIF   : stock_sécurité ≤ stock_actuel < ROP
        OK          : stock_actuel ≥ ROP
        DORMANT     : consommation_moyenne_jour ≈ 0 (< 0.01)
    """
    df = df.copy()

    conditions = [
        df["consommation_moyenne_jour"] < 0.01,          # DORMANT
        df["stock_actuel"] < df["stock_securite"],        # CRITIQUE
        df["stock_actuel"] < df["rop"],                   # PRÉVENTIF
    ]
    choix = ["DORMANT", "CRITIQUE", "PRÉVENTIF"]
    df["statut_stock"] = np.select(conditions, choix, default="OK")

    return df
