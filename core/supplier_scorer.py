"""
supplier_scorer.py — Scoring et évaluation de la fiabilité des fournisseurs.

Calcule un score composite de fiabilité (0-100) basé sur :
- Respect des délais (40%)
- Conformité des quantités (30%)
- Régularité des livraisons (30%)
"""

import pandas as pd
import numpy as np
from datetime import datetime


def score_suppliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les scores de fiabilité par fournisseur et les réinjecte
    dans le DataFrame principal.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame enrichi par inventory_engine.compute_all()

    Returns
    -------
    pd.DataFrame
        DataFrame avec la colonne 'score_fournisseur' ajoutée.
    """
    df = df.copy()

    # Supprimer la colonne si elle existe déjà (cas de rechargement SQLite)
    if "score_fournisseur" in df.columns:
        df = df.drop(columns=["score_fournisseur"])

    # Calcul des métriques par fournisseur
    scores_df = _compute_supplier_metrics(df)

    # Fusion des scores dans le DataFrame principal
    df = df.merge(
        scores_df[["fournisseur_id", "score_fiabilite"]],
        on="fournisseur_id",
        how="left",
    )
    df = df.rename(columns={"score_fiabilite": "score_fournisseur"})
    df["score_fournisseur"] = df["score_fournisseur"].fillna(50)

    return df


def get_supplier_details(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retourne un DataFrame détaillé des métriques fournisseurs
    pour affichage dans la page dédiée.

    Returns
    -------
    pd.DataFrame
        Colonnes : fournisseur_id, fournisseur_nom, score_fiabilite,
        delai_moyen_reel, taux_conformite, nb_articles,
        score_delai, score_quantite, score_regularite
    """
    return _compute_supplier_metrics(df)


def _compute_supplier_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les métriques détaillées par fournisseur.

    Score composite (0-100) :
        score_fiabilite = 0.40 × score_delai + 0.30 × score_quantite + 0.30 × score_regularite

    Composantes :
        score_delai (0-100) :
            Basé sur le ratio écart-type / moyenne du lead time.
            Plus le ratio est faible, plus le fournisseur est fiable.

        score_quantite (0-100) :
            Basé sur le taux de conformité des quantités livrées
            (quantite_commandee_en_cours par rapport à la consommation).

        score_regularite (0-100) :
            Basé sur la fraîcheur et la régularité des livraisons
            (jours depuis la dernière livraison).
    """
    suppliers = []

    for fid, group in df.groupby("fournisseur_id"):
        fnom = group["fournisseur_nom"].iloc[0]
        nb_articles = len(group)

        # --- Score Délai (40%) ---
        # CV du lead time : plus c'est bas, plus c'est fiable
        delai_moyen = group["delai_fournisseur_jours"].mean()
        delai_ecart = group["delai_ecart_type"].mean()

        if delai_moyen > 0:
            cv_delai = delai_ecart / delai_moyen
            # Score inversement proportionnel au CV, normalisé 0-100
            # CV=0 → 100, CV=1 → 0
            score_delai = max(0, min(100, (1 - cv_delai) * 100))
        else:
            score_delai = 50  # Valeur neutre si pas de données

        # --- Score Quantité / Conformité (30%) ---
        # On évalue si les commandes en cours sont cohérentes avec la consommation
        # Articles avec commandes en cours vs articles qui en auraient besoin
        articles_besoin = group[group["statut_stock"].isin(["CRITIQUE", "PRÉVENTIF"])]
        if len(articles_besoin) > 0:
            articles_couverts = (
                articles_besoin["quantite_commandee_en_cours"] > 0
            ).sum()
            taux_conformite = articles_couverts / len(articles_besoin)
        else:
            taux_conformite = 1.0  # Pas de besoin = tout est conforme

        score_quantite = taux_conformite * 100

        # --- Score Régularité (30%) ---
        # Basé sur la fraîcheur des livraisons
        # Plus la dernière livraison est récente, mieux c'est
        today = pd.Timestamp(datetime.now().date())
        jours_depuis_livraison = (
            (today - group["derniere_livraison_date"]).dt.days
        ).mean()

        if np.isnan(jours_depuis_livraison):
            jours_depuis_livraison = 90

        # Score : 100 si livré aujourd'hui, 0 si > 90 jours
        score_regularite = max(0, min(100, (1 - jours_depuis_livraison / 90) * 100))

        # --- Score composite ---
        # Pondération : Délai 40% + Quantité 30% + Régularité 30%
        score_fiabilite = round(
            0.40 * score_delai + 0.30 * score_quantite + 0.30 * score_regularite,
            1,
        )

        suppliers.append({
            "fournisseur_id": fid,
            "fournisseur_nom": fnom,
            "score_fiabilite": score_fiabilite,
            "delai_moyen_reel": round(delai_moyen, 1),
            "delai_ecart_type": round(delai_ecart, 1),
            "taux_conformite": round(taux_conformite, 4),
            "nb_articles": nb_articles,
            "score_delai": round(score_delai, 1),
            "score_quantite": round(score_quantite, 1),
            "score_regularite": round(score_regularite, 1),
        })

    return pd.DataFrame(suppliers).sort_values(
        "score_fiabilite", ascending=False
    ).reset_index(drop=True)
