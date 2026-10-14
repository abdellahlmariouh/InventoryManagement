import os
import json
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Import core logic
from core.data_loader import load_file, save_to_sqlite, load_from_sqlite
from core.inventory_engine import compute_all
from core.alert_engine import generate_alerts, generate_purchase_orders
from core.kpi_calculator import compute_kpis
from core.simulator import simulate
from core.supplier_scorer import score_suppliers, get_supplier_details

app = Flask(__name__, static_folder='static')
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Global variable to store current data in memory for simplicity in this session
# In a real app, this would be in a DB or user-specific session
current_df = None

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/logo.png')
def serve_logo():
    return send_from_directory('.', 'logo.png')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    global current_df
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        df_raw, rapport = load_file(filepath)
        df_enriched = compute_all(df_raw)
        df_enriched = score_suppliers(df_enriched)
        current_df = df_enriched
        save_to_sqlite(df_enriched)
        
        # Convert date to string for JSON
        df_json = df_enriched.copy()
        df_json['derniere_livraison_date'] = df_json['derniere_livraison_date'].dt.strftime('%Y-%m-%d')
        
        return jsonify({
            "message": "File uploaded successfully",
            "rapport": rapport,
            "count": len(df_enriched)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/load_demo', methods=['POST'])
def load_demo():
    global current_df
    sample_path = 'sample_data.xlsx'
    if os.path.exists(sample_path):
        try:
            df_raw, rapport = load_file(sample_path)
            df_enriched = compute_all(df_raw)
            df_enriched = score_suppliers(df_enriched)
            current_df = df_enriched
            save_to_sqlite(df_enriched)
            return jsonify({"message": "Demo data loaded", "rapport": rapport})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Sample data not found"}), 404

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    global current_df
    if current_df is None:
        return jsonify({"error": "No data loaded"}), 404

    kpis = compute_kpis(current_df)
    alerts = generate_alerts(current_df).head(10).to_dict(orient='records')
    
    chart_data = current_df[['article_id', 'stock_actuel', 'rop', 'stock_securite', 'statut_stock']].head(30).to_dict(orient='records')
    
    return jsonify({
        "kpis": kpis,
        "alerts": alerts,
        "chart_data": chart_data
    })

@app.route('/api/reset', methods=['POST'])
def reset_data():
    global current_df
    current_df = None
    return jsonify({"message": "Data reset successfully"})

@app.route('/api/abc_xyz', methods=['GET'])
def get_abc_xyz():
    global current_df
    if current_df is None: return jsonify({"error": "No data"}), 404
    
    abc_xyz_data = current_df[['article_id', 'article_nom', 'segment_abc', 'segment_xyz', 'segment', 'valeur_annuelle', 'cv', 'stock_actuel']].to_dict(orient='records')
    return jsonify(abc_xyz_data)

@app.route('/api/suppliers', methods=['GET'])
def get_suppliers():
    global current_df
    if current_df is None: return jsonify({"error": "No data"}), 404
    
    suppliers = get_supplier_details(current_df).to_dict(orient='records')
    return jsonify(suppliers)

@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    global current_df
    if current_df is None: return jsonify({"error": "No data"}), 404
    
    params = request.json
    delta_delai = params.get('delta_delai', 0)
    delta_service = params.get('delta_service', 0)
    delta_demande = params.get('delta_demande', 0)
    cout_rupture_facteur = params.get('cout_rupture_facteur', 2.0)
    
    df_sim = simulate(current_df, delta_delai, delta_service, delta_demande, cout_rupture_facteur)
    
    # Import summary function locally to avoid circular import if any
    from core.simulator import get_simulation_summary
    summary = get_simulation_summary(df_sim)
    
    return jsonify({
        "summary": summary,
        "details": df_sim.to_dict(orient='records')
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
