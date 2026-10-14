"""
alert_engine.py — Moteur d'alertes et génération de bons de commande.

Produit des alertes priorisées basées sur le statut de stock calculé
par inventory_engine. Génère des fiches commande actionnables pour
les gestionnaires.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Génère un DataFrame d'alertes trié par priorité décroissante.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame enrichi par inventory_engine.compute_all()
        (contient statut_stock, rop, stock_securite, eoq, etc.)

    Returns
    -------
    pd.DataFrame
        DataFrame d'alertes avec colonnes :
        - niveau : 'CRITIQUE' / 'PRÉVENTIF' / 'SURVEILLANCE' / 'DORMANT'
        - article_id : référence article
        - article_nom : libellé
        - message : texte explicite pour le gestionnaire
        - qte_suggeree : quantité EOQ recommandée
        - fournisseur_id : identifiant fournisseur
        - fournisseur_nom : nom fournisseur à contacter
        - date_limite : date estimée avant rupture
        - stock_actuel : niveau de stock actuel
        - jours_avant_rupture : nombre de jours avant rupture
        - priorite_num : score numérique pour le tri (1=max urgence)
    """
    alertes = []

    for _, row in df.iterrows():
        alerte = _evaluer_article(row)
        if alerte is not None:
            alertes.append(alerte)

    if not alertes:
        return pd.DataFrame(columns=[
            "niveau", "article_id", "article_nom", "message",
            "qte_suggeree", "fournisseur_id", "fournisseur_nom",
            "date_limite", "stock_actuel", "jours_avant_rupture", "priorite_num"
        ])

    df_alertes = pd.DataFrame(alertes)

    # Tri : priorité numérique croissante (1 = plus urgent), puis jours avant rupture
    df_alertes = df_alertes.sort_values(
        ["priorite_num", "jours_avant_rupture"],
        ascending=[True, True]
    ).reset_index(drop=True)

    return df_alertes


def _evaluer_article(row: pd.Series) -> dict | None:
    """
    Évalue un article et retourne un dictionnaire d'alerte si nécessaire.

    Règles d'alerte :
        CRITIQUE     : stock < stock_sécurité → rupture imminente
        PRÉVENTIF    : stock < ROP → réapprovisionnement nécessaire bientôt
        SURVEILLANCE : stock < 1.5 × ROP → à surveiller
        DORMANT      : consommation quasi-nulle → stock dormant à évaluer
    """
    statut = row.get("statut_stock", "OK")
    stock = row["stock_actuel"]
    conso = row["consommation_moyenne_jour"]
    rop = row.get("rop", 0)
    ss = row.get("stock_securite", 0)
    eoq = row.get("eoq", 0)

    # Calcul des jours avant rupture (sans réapprovisionnement)
    if conso > 0:
        jours_avant_rupture = round(stock / conso, 1)
    else:
        jours_avant_rupture = 999.0

    # Date limite estimée
    date_limite = datetime.now() + timedelta(days=jours_avant_rupture)

    base = {
        "article_id": row["article_id"],
        "article_nom": row["article_nom"],
        "qte_suggeree": int(eoq) if eoq > 0 else 0,
        "fournisseur_id": row["fournisseur_id"],
        "fournisseur_nom": row["fournisseur_nom"],
        "date_limite": date_limite.strftime("%Y-%m-%d"),
        "stock_actuel": stock,
        "jours_avant_rupture": jours_avant_rupture,
    }

    if statut == "DORMANT":
        return {
            **base,
            "niveau": "DORMANT",
            "message": (
                f"⚪ Article dormant — stock de {stock:.0f} unités "
                f"sans consommation significative. Évaluer la pertinence "
                f"du maintien en stock."
            ),
            "priorite_num": 4,
        }

    if statut == "CRITIQUE":
        return {
            **base,
            "niveau": "CRITIQUE",
            "message": (
                f"🔴 URGENT — Stock ({stock:.0f}) sous le stock de sécurité "
                f"({ss:.0f}). Rupture estimée dans {jours_avant_rupture:.0f} jour(s). "
                f"Commander {eoq:.0f} unités immédiatement chez {row['fournisseur_nom']}."
            ),
            "priorite_num": 1,
        }

    if statut == "PRÉVENTIF":
        return {
            **base,
            "niveau": "PRÉVENTIF",
            "message": (
                f"🟠 Réapprovisionnement conseillé — Stock ({stock:.0f}) "
                f"sous le point de commande ({rop:.0f}). "
                f"Planifier une commande de {eoq:.0f} unités."
            ),
            "priorite_num": 2,
        }

    # SURVEILLANCE : stock entre ROP et 1.5 × ROP
    if stock < 1.5 * rop and conso > 0:
        return {
            **base,
            "niveau": "SURVEILLANCE",
            "message": (
                f"🟡 À surveiller — Stock ({stock:.0f}) proche du point "
                f"de commande ({rop:.0f}). Préparer un réapprovisionnement."
            ),
            "priorite_num": 3,
        }

    # Pas d'alerte si stock est OK et largement au-dessus du ROP
    return None


def generate_purchase_orders(df_alertes: pd.DataFrame) -> pd.DataFrame:
    """
    Génère des bons de commande à partir des alertes sélectionnées.

    Parameters
    ----------
    df_alertes : pd.DataFrame
        Sous-ensemble d'alertes pour lesquelles créer un bon.

    Returns
    -------
    pd.DataFrame
        Bons de commande avec colonnes formatées pour export CSV.
    """
    if df_alertes.empty:
        return pd.DataFrame()

    bons = df_alertes[["article_id", "article_nom", "qte_suggeree",
                        "fournisseur_id", "fournisseur_nom", "niveau",
                        "date_limite"]].copy()
    bons = bons.rename(columns={
        "qte_suggeree": "quantite_commandee",
        "date_limite": "date_livraison_souhaitee",
    })
    bons["date_emission"] = datetime.now().strftime("%Y-%m-%d")
    bons["statut_commande"] = "À ÉMETTRE"

    return bons
