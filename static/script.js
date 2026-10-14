document.addEventListener('DOMContentLoaded', () => {
    // Navigation
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.content-section');
    const pageTitle = document.getElementById('page-title');
    const mainNav = document.getElementById('main-nav');
    const logoLink = document.getElementById('logo-link');
    const demoBtn = document.getElementById('load-demo-btn');

    // Logo reset functionality
    logoLink.addEventListener('click', (e) => {
        e.preventDefault();
        location.reload(); 
    });

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            if (mainNav.classList.contains('disabled')) return;

            const target = item.getAttribute('data-target');
            showSection(target);
            
            if (target === 'dashboard') loadDashboard();
            if (target === 'abc-xyz') loadAbcXyz();
            if (target === 'alerts') loadFullAlerts();
            if (target === 'suppliers') loadSuppliers();
            if (target === 'simulator') loadSimulator();
        });
    });

    // File Upload
    const fileUpload = document.getElementById('file-upload');
    fileUpload.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        showLoader(true);
        try {
            const res = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.error) alert(data.error);
            else {
                onDataLoaded();
            }
        } catch (err) {
            console.error(err);
        } finally {
            showLoader(false);
        }
    });

    // Demo Data
    demoBtn.addEventListener('click', async () => {
        showLoader(true);
        try {
            const res = await fetch('/api/load_demo', { method: 'POST' });
            const data = await res.json();
            if (data.error) alert(data.error);
            else {
                onDataLoaded();
            }
        } catch (err) {
            console.error(err);
        } finally {
            showLoader(false);
        }
    });

    // Simulator Sliders
    ['service', 'lead', 'demand', 'shortage'].forEach(id => {
        const input = document.getElementById(`sim-${id}`);
        const val = document.getElementById(`sim-${id}-val`);
        if (input && val) {
            input.addEventListener('input', () => {
                let suffix = '';
                if (id === 'service' || id === 'demand') suffix = '%';
                else if (id === 'lead') suffix = 'j';
                else if (id === 'shortage') suffix = 'x';
                
                val.textContent = (id === 'lead' && input.value >= 0 ? '+' : '') + input.value + suffix;
            });
        }
    });

    const runSimBtn = document.getElementById('run-sim-btn');
    if (runSimBtn) runSimBtn.addEventListener('click', runSimulation);

    // Initial check
    updateStatus(false);
});

function onDataLoaded() {
    updateStatus(true);
    enableNavigation();
    showSection('dashboard');
    loadDashboard();
    // Hide floating demo button after data load
    const demoBtn = document.getElementById('load-demo-btn');
    if (demoBtn) demoBtn.style.display = 'none';
}

function showLoader(show) {
    const loader = document.getElementById('loader');
    if (loader) loader.classList.toggle('hidden', !show);
}

function updateStatus(connected) {
    const status = document.getElementById('data-status');
    if (status) {
        status.innerHTML = connected 
            ? '<i class="fas fa-circle status-green"></i> Données Chargées' 
            : '<i class="fas fa-circle status-red"></i> Aucune Donnée';
    }
}

function enableNavigation() {
    const nav = document.getElementById('main-nav');
    if (nav) nav.classList.remove('disabled');
}

function showSection(targetId) {
    const sections = document.querySelectorAll('.content-section');
    const navItems = document.querySelectorAll('.nav-item');
    const pageTitle = document.getElementById('page-title');

    sections.forEach(s => s.classList.remove('active'));
    const targetSection = document.getElementById(targetId);
    if (targetSection) targetSection.classList.add('active');

    navItems.forEach(i => {
        const isActive = i.getAttribute('data-target') === targetId;
        i.classList.toggle('active', isActive);
        if (isActive && pageTitle) {
            pageTitle.textContent = i.querySelector('span').textContent;
        }
    });
    
    if (targetId === 'welcome' && pageTitle) pageTitle.textContent = 'Bienvenue';
}

async function loadDashboard() {
    try {
        const res = await fetch('/api/dashboard');
        if (!res.ok) return;
        const data = await res.json();
        
        document.getElementById('kpi-service').textContent = (data.kpis.taux_service_global * 100).toFixed(1) + '%';
        document.getElementById('kpi-value').textContent = formatCurrency(data.kpis.valeur_stock_total);
        document.getElementById('kpi-alerts').textContent = data.kpis.nb_alertes.CRITIQUE;
        document.getElementById('kpi-ruptures').textContent = data.kpis.articles_en_rupture;

        renderStockChart(data.chart_data);

        const tbody = document.querySelector('#alerts-table tbody');
        if (tbody) {
            tbody.innerHTML = '';
            data.alerts.slice(0, 10).forEach(alert => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge ${getBadgeClass(alert.niveau)}">${alert.niveau}</span></td>
                    <td>${alert.article_nom}</td>
                    <td>${alert.stock_actuel}</td>
                    <td>${alert.jours_avant_rupture.toFixed(1)} j</td>
                    <td><button class="btn-demo" style="padding: 5px 10px; font-size: 0.8rem;">Détails</button></td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) { console.error(err); }
}

function renderStockChart(data) {
    const chartDiv = document.getElementById('stock-chart');
    if (!chartDiv) return;

    const ids = data.map(d => d.article_id);
    const stocks = data.map(d => d.stock_actuel);
    const rops = data.map(d => d.rop);
    const sses = data.map(d => d.stock_securite);

    const trace1 = {
        x: ids, y: stocks, name: 'Stock Actuel', type: 'bar',
        marker: { 
            color: data.map(d => getStatusColor(d.statut_stock)),
            line: { color: 'rgba(0,0,0,0.1)', width: 1 }
        }
    };
    const trace2 = { x: ids, y: rops, name: 'ROP', type: 'scatter', line: { color: '#e67e22', width: 2, dash: 'dash' } };
    const trace3 = { x: ids, y: sses, name: 'SS', type: 'scatter', line: { color: '#e74c3c', width: 2, dash: 'dot' } };

    const layout = {
        template: 'plotly_white',
        margin: { t: 50, b: 80, l: 60, r: 20 },
        legend: { orientation: 'h', y: 1.15, x: 0.5, xanchor: 'center' },
        xaxis: { title: 'Articles', tickangle: -45 },
        yaxis: { title: 'Quantité' },
        hovermode: 'closest',
        height: 450
    };

    Plotly.newPlot('stock-chart', [trace1, trace2, trace3], layout, {responsive: true});
}

async function loadAbcXyz() {
    try {
        const res = await fetch('/api/abc_xyz');
        if (!res.ok) return;
        const data = await res.json();
        
        const abc = ['A', 'B', 'C'];
        const xyz = ['X', 'Y', 'Z'];
        const matrix = [[0,0,0],[0,0,0],[0,0,0]];
        const annotations = [];
        
        data.forEach(d => {
            const i = abc.indexOf(d.segment_abc);
            const j = xyz.indexOf(d.segment_xyz);
            if (i >= 0 && j >= 0) matrix[i][j]++;
        });

        // Generate annotations for heatmap cells
        for (let i = 0; i < abc.length; i++) {
            for (let j = 0; j < xyz.length; j++) {
                annotations.push({
                    x: xyz[j] === 'X' ? 'X (Stable)' : xyz[j] === 'Y' ? 'Y (Variable)' : 'Z (Incertain)',
                    y: abc[i] === 'A' ? 'A (Top)' : abc[i] === 'B' ? 'B (Moyen)' : 'C (Faible)',
                    text: matrix[i][j].toString(),
                    font: { family: 'Inter', size: 16, color: 'black', weight: 'bold' },
                    showarrow: false
                });
            }
        }

        const heatmapTrace = {
            z: matrix, 
            x: ['X (Stable)', 'Y (Variable)', 'Z (Incertain)'], 
            y: ['A (Top)', 'B (Moyen)', 'C (Faible)'], 
            type: 'heatmap',
            colorscale: [
                [0, '#e5fff9'], 
                [0.5, '#fff4e5'], 
                [1, '#ffe5e5']
            ],
            showscale: true,
            hoverinfo: 'z'
        };

        const heatmapLayout = {
            title: 'Répartition du Portefeuille (Nombre d\'articles)',
            template: 'plotly_white',
            height: 450,
            xaxis: { side: 'bottom', title: 'Stabilité (XYZ)' },
            yaxis: { autorange: 'reversed', title: 'Valeur (ABC)' },
            annotations: annotations
        };

        Plotly.newPlot('abc-xyz-heatmap', [heatmapTrace], heatmapLayout, {responsive: true});

        // Scatter plot with legend (separate traces for A, B, C)
        const segments = {
            'A': { name: 'Classe A (Haute Valeur)', color: '#e74c3c', x: [], y: [], text: [], size: [] },
            'B': { name: 'Classe B (Valeur Moyenne)', color: '#f39c12', x: [], y: [], text: [], size: [] },
            'C': { name: 'Classe C (Basse Valeur)', color: '#27ae60', x: [], y: [], text: [], size: [] }
        };

        data.forEach(d => {
            const seg = segments[d.segment_abc];
            if (seg) {
                seg.x.push(d.valeur_annuelle);
                seg.y.push(d.cv);
                seg.text.push(`${d.article_nom} (${d.segment})<br>Valeur: ${d.valeur_annuelle.toFixed(0)} MAD<br>CV: ${d.cv.toFixed(2)}`);
                seg.size.push(Math.log10(d.stock_actuel + 1) * 10 + 5);
            }
        });

        const scatterTraces = Object.values(segments).map(seg => ({
            x: seg.x,
            y: seg.y,
            name: seg.name,
            mode: 'markers',
            text: seg.text,
            marker: {
                size: seg.size,
                color: seg.color,
                opacity: 0.7,
                line: { color: 'white', width: 1 }
            }
        }));

        const scatterLayout = {
            title: 'Matrice Valeur vs Variabilité',
            template: 'plotly_white', 
            height: 450,
            xaxis: { title: 'Valeur Annuelle (MAD)', type: 'log' },
            yaxis: { title: 'Variabilité (Coeff. Variation)' },
            legend: { orientation: 'h', y: -0.2 },
            hovermode: 'closest'
        };

        Plotly.newPlot('abc-xyz-scatter', scatterTraces, scatterLayout, {responsive: true});
    } catch (err) { console.error(err); }
}

async function loadFullAlerts() {
    try {
        const res = await fetch('/api/dashboard');
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.querySelector('#full-alerts-table tbody');
        if (tbody) {
            tbody.innerHTML = '';
            data.alerts.forEach(alert => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge ${getBadgeClass(alert.niveau)}">${alert.niveau}</span></td>
                    <td>${alert.article_nom}</td>
                    <td>${alert.stock_actuel}</td>
                    <td>${alert.fournisseur_nom}</td>
                    <td>${alert.qte_suggeree}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) { console.error(err); }
}

async function loadSuppliers() {
    try {
        const res = await fetch('/api/suppliers');
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.querySelector('#suppliers-table tbody');
        if (tbody) {
            tbody.innerHTML = '';
            data.forEach(s => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${s.fournisseur_nom}</td>
                    <td><span class="badge ${s.score_fiabilite > 80 ? 'badge-green' : s.score_fiabilite > 60 ? 'badge-orange' : 'badge-red'}">${s.score_fiabilite}%</span></td>
                    <td>${s.delai_moyen_reel} j</td>
                    <td>${(s.taux_conformite * 100).toFixed(0)}%</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) { console.error(err); }
}

function loadSimulator() {
    // Initial plot if data exists
    runSimulation();
}

async function runSimulation() {
    const serviceInput = document.getElementById('sim-service');
    const leadInput = document.getElementById('sim-lead');
    const demandInput = document.getElementById('sim-demand');
    const shortageInput = document.getElementById('sim-shortage');

    if (!serviceInput) return;

    const params = {
        delta_service: (serviceInput.value / 100) - 0.95,
        delta_delai: parseFloat(leadInput.value),
        delta_demande: demandInput.value / 100,
        cout_rupture_facteur: parseFloat(shortageInput.value)
    };

    showLoader(true);
    try {
        const res = await fetch('/api/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        const data = await res.json();
        
        // Update Simulator KPIs
        const s = data.summary;
        document.getElementById('sim-kpi-cost').textContent = formatCurrency(s.total_cout_simule);
        updateDelta('sim-kpi-cost-delta', s.delta_cout_pct.toFixed(1) + '% vs actuel', s.delta_cout_pct > 0);
        
        document.getElementById('sim-kpi-cap').textContent = formatCurrency(s.total_capital_simule);
        updateDelta('sim-kpi-cap-delta', (s.delta_capital >= 0 ? '+' : '') + formatCurrency(s.delta_capital), s.delta_capital > 0);
        
        document.getElementById('sim-kpi-rupt').textContent = formatCurrency(s.total_rupture_simule);
        const ruptureDelta = s.total_cout_actuel > 0 ? (s.total_rupture_simule - s.total_rupture_actuel) / s.total_cout_actuel * 100 : 0;
        updateDelta('sim-kpi-rupt-delta', (ruptureDelta >= 0 ? '+' : '') + ruptureDelta.toFixed(1) + '% impact TCO', ruptureDelta > 0);

        // Render Chart
        renderSimChart(data.details);

        // Update Table (Top 10 by impact)
        const tbody = document.querySelector('#sim-table tbody');
        if (tbody) {
            tbody.innerHTML = '';
            const sorted = data.details.sort((a, b) => Math.abs(b.cout_total_simule - b.cout_total_actuel) - Math.abs(a.cout_total_simule - a.cout_total_actuel));
            sorted.slice(0, 10).forEach(d => {
                const delta = d.cout_total_simule - d.cout_total_actuel;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${d.article_nom}</td>
                    <td>${d.ss_simule.toFixed(1)}</td>
                    <td>${formatCurrency(d.cout_poss_simule)}</td>
                    <td>${formatCurrency(d.cout_rupt_simule)}</td>
                    <td class="${delta > 0 ? 'delta-positive' : 'delta-negative'}">${delta >= 0 ? '+' : ''}${formatCurrency(delta)}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) {
        console.error(err);
    } finally {
        showLoader(false);
    }
}

function updateDelta(id, text, isBad) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'kpi-delta ' + (isBad ? 'delta-positive' : 'delta-negative');
}

function renderSimChart(details) {
    const chartDiv = document.getElementById('sim-chart');
    if (!chartDiv) return;

    const sample = details.slice(0, 10);
    const ids = sample.map(d => d.article_id);
    
    // Data for Current
    const trace1 = {
        x: ids, y: sample.map(d => d.cout_cmd_actuel), 
        name: 'C. Commande (Act)', type: 'bar', stackgroup: 'one', marker: {color: '#1a1a2e', opacity: 0.6}
    };
    const trace2 = {
        x: ids, y: sample.map(d => d.cout_poss_actuel), 
        name: 'C. Possession (Act)', type: 'bar', stackgroup: 'one', marker: {color: '#16213e', opacity: 0.6}
    };
    const trace3 = {
        x: ids, y: sample.map(d => d.cout_rupt_actuel), 
        name: 'C. Rupture (Act)', type: 'bar', stackgroup: 'one', marker: {color: '#0f3460', opacity: 0.6}
    };

    // Data for Simulated
    const trace4 = {
        x: ids, y: sample.map(d => d.cout_cmd_simule), 
        name: 'C. Commande (Sim)', type: 'bar', stackgroup: 'two', marker: {color: '#e94560'}
    };
    const trace5 = {
        x: ids, y: sample.map(d => d.cout_poss_simule), 
        name: 'C. Possession (Sim)', type: 'bar', stackgroup: 'two', marker: {color: '#ff6b6b'}
    };
    const trace6 = {
        x: ids, y: sample.map(d => d.cout_rupt_simule), 
        name: 'C. Rupture (Sim)', type: 'bar', stackgroup: 'two', marker: {color: '#ff9f43'}
    };

    const layout = {
        barmode: 'group',
        template: 'plotly_white',
        height: 450,
        margin: { t: 50, b: 80, l: 60, r: 20 },
        legend: { orientation: 'h', y: 1.15, x: 0.5, xanchor: 'center', font: {size: 10} },
        xaxis: { title: 'Top 10 Articles par Impact', tickangle: -45 },
        yaxis: { title: 'Répartition du Coût Total (MAD)' }
    };

    Plotly.newPlot('sim-chart', [trace1, trace2, trace3, trace4, trace5, trace6], layout, {responsive: true});
}

function formatCurrency(val) {
    if (val === undefined || val === null) return '--';
    return val >= 1000000 
        ? (val / 1000000).toFixed(2) + 'M MAD' 
        : (val / 1000).toFixed(1) + 'K MAD';
}

function getBadgeClass(niveau) {
    if (niveau === 'CRITIQUE') return 'badge-red';
    if (niveau === 'PRÉVENTIF') return 'badge-orange';
    return 'badge-green';
}

function getStatusColor(statut) {
    if (statut === 'CRITIQUE') return '#e74c3c';
    if (statut === 'PRÉVENTIF') return '#f39c12';
    if (statut === 'OK') return '#27ae60';
    return '#95a5a6';
}
