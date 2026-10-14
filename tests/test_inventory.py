"""
test_inventory.py — Tests unitaires des formules du moteur de gestion de stock.

Teste les fonctions core/ avec des données synthétiques pour valider :
- Calcul du stock de sécurité (SS)
- Point de réapprovisionnement (ROP)
- Quantité économique de commande (EOQ)
- Segmentation ABC / XYZ
- Statut de stock
- Alertes
- KPIs
- Simulateur
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np
from scipy.stats import norm

# Ajout du répertoire parent au path pour importer core/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.inventory_engine import compute_all
from core.alert_engine import generate_alerts
from core.kpi_calculator import compute_kpis
from core.simulator import simulate


def _create_test_df(n: int = 5) -> pd.DataFrame:
    """Crée un DataFrame de test minimal avec n articles."""
    data = {
        "article_id": [f"ART-{i:03d}" for i in range(1, n + 1)],
        "article_nom": [f"Article Test {i}" for i in range(1, n + 1)],
        "stock_actuel": [100, 5, 50, 200, 0.5],  # Varié pour tester les statuts
        "consommation_moyenne_jour": [10, 20, 5, 2, 0.001],  # Dernier = dormant
        "ecart_type_consommation": [2, 5, 1, 0.5, 0.001],
        "delai_fournisseur_jours": [7, 14, 5, 10, 3],
        "delai_ecart_type": [1, 3, 0.5, 2, 0.5],
        "prix_unitaire": [100, 500, 50, 10, 200],
        "cout_commande": [50, 100, 30, 20, 10],
        "taux_possession": [0.25, 0.20, 0.30, 0.15, 0.25],
        "fournisseur_id": ["F01", "F02", "F01", "F03", "F02"],
        "fournisseur_nom": ["Alpha", "Beta", "Alpha", "Gamma", "Beta"],
        "derniere_livraison_date": pd.to_datetime([
            "2026-04-01", "2026-03-15", "2026-04-20",
            "2026-02-01", "2025-12-01"
        ]),
        "quantite_commandee_en_cours": [0, 100, 0, 0, 0],
    }
    return pd.DataFrame(data)


class TestInventoryEngine(unittest.TestCase):
    """Tests du moteur de calcul inventory_engine."""

    def setUp(self):
        self.df = _create_test_df()
        self.df_computed = compute_all(self.df, taux_service=0.95)

    def test_z_score(self):
        """Z-score correspond au taux de service 95%."""
        z_expected = norm.ppf(0.95)
        z_actual = self.df_computed["z_score"].iloc[0]
        self.assertAlmostEqual(z_actual, z_expected, places=6)

    def test_safety_stock_positive(self):
        """Le stock de sécurité doit être ≥ 0 pour tout article actif."""
        ss = self.df_computed["stock_securite"]
        self.assertTrue((ss >= 0).all(), "Stock de sécurité négatif détecté.")

    def test_safety_stock_formula(self):
        """
        Vérifie la formule SS = Z × √(L × σ_d² + D² × σ_L²)
        pour ART-001.
        """
        row = self.df_computed[self.df_computed["article_id"] == "ART-001"].iloc[0]
        z = norm.ppf(0.95)
        L = 7
        sigma_d = 2
        D = 10
        sigma_L = 1

        ss_expected = z * np.sqrt(L * sigma_d**2 + D**2 * sigma_L**2)
        self.assertAlmostEqual(row["stock_securite"], ss_expected, places=2)

    def test_rop_formula(self):
        """ROP = D × L + SS pour ART-001."""
        row = self.df_computed[self.df_computed["article_id"] == "ART-001"].iloc[0]
        rop_expected = 10 * 7 + row["stock_securite"]
        self.assertAlmostEqual(row["rop"], rop_expected, places=2)

    def test_eoq_positive(self):
        """EOQ doit être ≥ 0."""
        eoq = self.df_computed["eoq"]
        self.assertTrue((eoq >= 0).all(), "EOQ négatif détecté.")

    def test_eoq_formula(self):
        """
        Vérifie EOQ = √(2 × D_ann × S / (C × i)) pour ART-001.
        D_ann = 10 × 365, S = 50, C = 100, i = 0.25
        """
        row = self.df_computed[self.df_computed["article_id"] == "ART-001"].iloc[0]
        D_ann = 10 * 365
        S = 50
        C = 100
        i = 0.25
        eoq_expected = np.ceil(np.sqrt(2 * D_ann * S / (C * i)))
        self.assertEqual(row["eoq"], eoq_expected)

    def test_abc_segments_exist(self):
        """Tous les segments ABC doivent être A, B ou C."""
        segments = set(self.df_computed["segment_abc"].unique())
        self.assertTrue(segments.issubset({"A", "B", "C"}))

    def test_xyz_segments_exist(self):
        """Tous les segments XYZ doivent être X, Y ou Z."""
        segments = set(self.df_computed["segment_xyz"].unique())
        self.assertTrue(segments.issubset({"X", "Y", "Z"}))

    def test_combined_segment(self):
        """Le segment combiné = ABC + XYZ."""
        for _, row in self.df_computed.iterrows():
            self.assertEqual(
                row["segment"],
                row["segment_abc"] + row["segment_xyz"],
            )

    def test_statut_stock_values(self):
        """Statuts valides : CRITIQUE, PRÉVENTIF, OK, DORMANT."""
        statuts_valides = {"CRITIQUE", "PRÉVENTIF", "OK", "DORMANT"}
        statuts = set(self.df_computed["statut_stock"].unique())
        self.assertTrue(statuts.issubset(statuts_valides))

    def test_dormant_detection(self):
        """L'article avec conso ≈ 0 doit être classé DORMANT."""
        row = self.df_computed[
            self.df_computed["article_id"] == "ART-005"
        ].iloc[0]
        self.assertEqual(row["statut_stock"], "DORMANT")

    def test_critique_detection(self):
        """L'article avec stock très bas vs SS doit être CRITIQUE."""
        row = self.df_computed[
            self.df_computed["article_id"] == "ART-002"
        ].iloc[0]
        # Stock = 5, conso = 20/j, délai = 14j → SS sera élevé
        self.assertEqual(row["statut_stock"], "CRITIQUE")


class TestAlertEngine(unittest.TestCase):
    """Tests du moteur d'alertes."""

    def setUp(self):
        self.df = compute_all(_create_test_df())
        self.alertes = generate_alerts(self.df)

    def test_alertes_not_empty(self):
        """Des alertes doivent être générées pour les données de test."""
        self.assertGreater(len(self.alertes), 0)

    def test_alertes_columns(self):
        """Vérifier les colonnes obligatoires des alertes."""
        colonnes_requises = {
            "niveau", "article_id", "message",
            "qte_suggeree", "fournisseur_nom"
        }
        self.assertTrue(colonnes_requises.issubset(set(self.alertes.columns)))

    def test_alertes_sorted_by_priority(self):
        """Les alertes doivent être triées par priorité."""
        priorities = self.alertes["priorite_num"].tolist()
        self.assertEqual(priorities, sorted(priorities))

    def test_critique_alert_exists(self):
        """Au moins une alerte CRITIQUE doit exister."""
        niveaux = self.alertes["niveau"].unique()
        self.assertIn("CRITIQUE", niveaux)


class TestKPIs(unittest.TestCase):
    """Tests des KPIs."""

    def setUp(self):
        self.df = compute_all(_create_test_df())
        self.kpis = compute_kpis(self.df)

    def test_kpi_keys(self):
        """Toutes les clés KPI doivent être présentes."""
        cles = {
            "taux_service_global", "valeur_stock_total",
            "valeur_par_segment", "taux_rotation_moyen",
            "nb_alertes", "articles_en_rupture"
        }
        self.assertTrue(cles.issubset(set(self.kpis.keys())))

    def test_taux_service_range(self):
        """Le taux de service doit être entre 0 et 1."""
        ts = self.kpis["taux_service_global"]
        self.assertGreaterEqual(ts, 0)
        self.assertLessEqual(ts, 1)

    def test_valeur_stock_positive(self):
        """La valeur du stock total doit être positive."""
        self.assertGreater(self.kpis["valeur_stock_total"], 0)

    def test_segments_abc_in_valeur(self):
        """Les 3 segments A, B, C doivent être présents dans valeur_par_segment."""
        self.assertTrue(
            {"A", "B", "C"}.issubset(set(self.kpis["valeur_par_segment"].keys()))
        )


class TestSimulator(unittest.TestCase):
    """Tests du simulateur."""

    def setUp(self):
        self.df = compute_all(_create_test_df())

    def test_no_change_scenario(self):
        """Sans delta, les valeurs simulées doivent ≈ actuelles."""
        result = simulate(self.df, 0, 0, 0)
        for _, row in result.iterrows():
            self.assertAlmostEqual(row["ss_actuel"], row["ss_simule"], places=0)
            self.assertAlmostEqual(row["rop_actuel"], row["rop_simule"], places=0)

    def test_increased_service_increases_ss(self):
        """Augmenter le taux de service doit augmenter le SS."""
        result = simulate(self.df, delta_service=+0.04)
        # Au moins un article doit avoir SS_simule > SS_actuel
        self.assertTrue((result["ss_simule"] >= result["ss_actuel"]).all())

    def test_increased_lead_time_increases_rop(self):
        """Augmenter le lead time doit augmenter le ROP."""
        result = simulate(self.df, delta_delai=+5)
        # Filtrer les articles actifs (non dormants)
        actifs = result[result["rop_actuel"] > 0]
        self.assertTrue((actifs["rop_simule"] >= actifs["rop_actuel"]).all())

    def test_output_columns(self):
        """Le DataFrame de sortie doit contenir les colonnes comparatives."""
        result = simulate(self.df)
        colonnes = {"ss_actuel", "ss_simule", "rop_actuel", "rop_simule",
                     "eoq_actuel", "eoq_simule", "cout_actuel", "cout_simule"}
        self.assertTrue(colonnes.issubset(set(result.columns)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
