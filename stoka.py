import os
from flask import Flask, render_template_string, request, session, send_file, jsonify, make_response
from io import BytesIO, StringIO
import sqlite3
import logging
import csv
import json
from contextlib import contextmanager
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Set database path for production
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_URL', os.path.join(BASE_DIR, 'inventory.db'))
app.config['DATABASE'] = DB_PATH

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database context manager
@contextmanager
def get_db():
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        logger.debug("Connected to database")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        conn.close()
        logger.debug("Database connection closed")

# Initialize database
def init_db():
    db_path = app.config['DATABASE']
    logger.info(f"Checking database at: {db_path}")
    try:
        with get_db() as conn:
            c = conn.cursor()
            # Create products table
            c.execute('''CREATE TABLE IF NOT EXISTS products
                         (product_id INTEGER PRIMARY KEY,
                          product_name TEXT NOT NULL,
                          shelf_number INTEGER,
                          in_stock BOOLEAN)''')
            # Create shelves table
            c.execute('''CREATE TABLE IF NOT EXISTS shelves
                         (shelf_number INTEGER PRIMARY KEY,
                          checked BOOLEAN)''')
            # Create reorder_lists table
            c.execute('''CREATE TABLE IF NOT EXISTS reorder_lists
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          timestamp TEXT,
                          content TEXT)''')
            # Initialize shelves
            c.execute('SELECT COUNT(*) FROM shelves')
            if c.fetchone()[0] == 0:
                for shelf in range(1, 11):
                    c.execute('INSERT OR IGNORE INTO shelves (shelf_number, checked) VALUES (?, ?)', 
                             (shelf, False))
            # Initialize sample products for Shelf 1 (49 products)
            c.execute('SELECT COUNT(*) FROM products WHERE shelf_number = 1')
            if c.fetchone()[0] == 0:
                sample_products = [
                    ('ALLMOX 125 SUS', 1, True), ('AMOXICILLIN 250 CAP', 1, True), ('ASPIRIN 81MG TAB', 1, True),
                    ('PARACETAMOL 500 TAB', 1, True), ('IBUPROFEN 400 TAB', 1, True), ('CETIRIZINE 10 TAB', 1, True),
                    ('LORATADINE 10 TAB', 1, True), ('OMEPRAZOLE 20 CAP', 1, True), ('RANITIDINE 150 TAB', 1, True),
                    ('METFORMIN 500 TAB', 1, True), ('ATORVASTATIN 20 TAB', 1, True), ('LISINOPRIL 10 TAB', 1, True),
                    ('AMLODIPINE 5 TAB', 1, True), ('HYDROCHLOROTHIAZIDE 25 TAB', 1, True), ('FUROSEMIDE 40 TAB', 1, True),
                    ('CLOPIDOGREL 75 TAB', 1, True), ('WARFARIN 5 TAB', 1, True), ('DIGOXIN 0.25 TAB', 1, True),
                    ('METOPROLOL 50 TAB', 1, True), ('ENALAPRIL 10 TAB', 1, True), ('LOSARTAN 50 TAB', 1, True),
                    ('GLIPIZIDE 5 TAB', 1, True), ('INSULIN 100U/ML', 1, True), ('LEVOTHYROXINE 100 TAB', 1, True),
                    ('PREDNISONE 10 TAB', 1, True), ('BUDESONIDE INH', 1, True), ('SALBUTAMOL INH', 1, True),
                    ('MONTELUKAST 10 TAB', 1, True), ('AZITHROMYCIN 250 TAB', 1, True), ('CIPROFLOXACIN 500 TAB', 1, True),
                    ('DOXYCYCLINE 100 CAP', 1, True), ('AMOXICILLIN 500 CAP', 1, True), ('PENICILLIN VK 500 TAB', 1, True),
                    ('CLARITHROMYCIN 500 TAB', 1, True), ('FLUCONAZOLE 150 TAB', 1, True), ('METRONIDAZOLE 500 TAB', 1, True),
                    ('ONDANSETRON 4 TAB', 1, True), ('LOPERAMIDE 2 CAP', 1, True), ('BISMUTH SUBSALICYLATE TAB', 1, True),
                    ('MECLIZINE 25 TAB', 1, True), ('DIPHENHYDRAMINE 25 CAP', 1, True), ('ALBUTEROL INH', 1, True),
                    ('EPINEPHRINE INJ', 1, True), ('NALOXONE INJ', 1, True), ('ACETAMINOPHEN 325 TAB', 1, True),
                    ('KETOROLAC 10 TAB', 1, True), ('TRAMADOL 50 TAB', 1, True), ('CODEINE 30 TAB', 1, True),
                    ('MORPHINE 10 INJ', 1, True)
                ]
                for i, (name, shelf, in_stock) in enumerate(sample_products, 1):
                    c.execute('INSERT OR IGNORE INTO products (product_id, product_name, shelf_number, in_stock) VALUES (?, ?, ?, ?)',
                             (i, name, shelf, in_stock))
            conn.commit()
            logger.info("Database initialized with products, shelves, and reorder_lists")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# HTML template with sub-tabs for Manage Products and Reorder List
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>STOKA</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #fffef5; color: #333; }
        .container { max-width: 800px; margin-top: 80px; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .logo { position: fixed; top: 10px; left: 10px; font-size: 2rem; font-weight: bold; color: #d2b48c; z-index: 1100; }
        .nav-tabs { border-bottom: 2px solid #d2b48c; margin-bottom: 0; }
        .nav-link { color: #333; }
        .nav-link.active { background-color: #d2b48c !important; color: #fff !important; }
        .form-check-input:checked { background-color: #d2b48c; border-color: #d2b48c; }
        .btn-primary { background-color: #d2b48c; border-color: #d2b48c; }
        .btn-primary:hover { background-color: #b89778; border-color: #b89778; }
        .btn-danger { background-color: #dc3545; border-color: #dc3545; }
        .btn-danger:hover { background-color: #c82333; border-color: #c82333; }
        .tab-content { padding: 10px 0; min-height: 400px; }
        .tab-pane { padding: 10px; margin: 0; }
        #sessionModal { display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 1000; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.3); }
        #sessionModal.show { display: block; }
        #overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 999; }
        #overlay.show { display: block; }
        .footer-btn { margin-top: 20px; }
        .alert { margin-top: 10px; }
        .sub-tabs { margin-top: 10px; }
        .form-section { margin-bottom: 20px; }
        .table-container { max-height: 400px; overflow-y: auto; }
        @media (max-width: 576px) {
            .container { margin-top: 60px; padding: 15px; }
            .logo { font-size: 1.5rem; top: 5px; left: 5px; }
        }
    </style>
</head>
<body>
    <div id="overlay"></div>
    <div id="sessionModal">
        <h3>Session Management</h3>
        <form method="post" action="/start_session">
            <button type="submit" name="session_type" value="new" class="btn btn-primary m-2">New Session</button>
            <button type="submit" name="session_type" value="continue" class="btn btn-primary m-2">Continue Previous Session</button>
        </form>
    </div>
    <div class="logo">STOKA</div>
    <div class="container">
        {% with messages = get_flashed_messages() %}
        {% if messages %}
        {% for message in messages %}
        <div class="alert alert-danger">{{ message }}</div>
        {% endfor %}
        {% endif %}
        {% endwith %}
        {% if not session.get('show_inventory') %}
        <form method="post" action="/start_session">
            <button type="submit" name="session_type" value="new" class="btn btn-primary m-2">New Session</button>
            <button type="submit" name="session_type" value="continue" class="btn btn-primary m-2">Continue Previous Session</button>
        </form>
        {% else %}
        <ul class="nav nav-tabs" id="mainTabs">
            <li class="nav-item">
                <button class="nav-link {% if active_tab == 'shelves' %}active{% endif %}" id="shelves-tab" 
                        data-bs-toggle="tab" data-bs-target="#shelves" type="button">Shelves</button>
            </li>
            <li class="nav-item">
                <button class="nav-link {% if active_tab == 'reorder' %}active{% endif %}" id="reorder-tab" 
                        data-bs-toggle="tab" data-bs-target="#reorder" type="button">Reorder List</button>
            </li>
            <li class="nav-item">
                <button class="nav-link {% if active_tab == 'manage-products' %}active{% endif %}" id="manage-products-tab" 
                        data-bs-toggle="tab" data-bs-target="#manage-products" type="button">Manage Products</button>
            </li>
        </ul>
        <div class="tab-content" id="mainTabContent">
            <div class="tab-pane fade {% if active_tab == 'shelves' %}show active{% endif %}" id="shelves">
                <ul class="nav nav-tabs sub-tabs" id="shelfTabs">
                    {% for shelf in range(1, 11) %}
                    <li class="nav-item">
                        <button class="nav-link {% if active_shelf_tab == 'shelf' + shelf|string %}active{% endif %}" id="shelf{{ shelf }}-tab" 
                                data-bs-toggle="tab" data-bs-target="#shelf{{ shelf }}" type="button">Shelf {{ shelf }}</button>
                    </li>
                    {% endfor %}
                </ul>
                <div class="tab-content" id="shelfTabContent">
                    {% for shelf in range(1, 11) %}
                    <div class="tab-pane fade {% if active_shelf_tab == 'shelf' + shelf|string %}show active{% endif %}" id="shelf{{ shelf }}">
                        <form class="shelf-form" data-shelf="{{ shelf }}" action="/update_shelf/{{ shelf }}" method="post">
                            <div class="mb-3">
                                <label class="form-check-label">
                                    <input type="checkbox" class="form-check-input shelf-checkbox" name="shelf_checked" 
                                           {% if shelves[shelf-1]['checked'] %}checked{% endif %}>
                                    Shelf {{ shelf }} Checked
                                </label>
                            </div>
                            <div class="row">
                                {% set shelf_products = all_products | selectattr('shelf_number', 'equalto', shelf) | list %}
                                {% if shelf_products %}
                                {% for product in shelf_products %}
                                <div class="col-md-6 mb-2">
                                    <label class="form-check-label">
                                        <input type="checkbox" class="form-check-input product-checkbox" name="product_{{ product['product_id'] }}" 
                                               {% if product['in_stock'] %}checked{% endif %}>
                                        {{ product['product_name'] }}
                                    </label>
                                </div>
                                {% endfor %}
                                {% else %}
                                <p>No products on Shelf {{ shelf }}.</p>
                                {% endif %}
                            </div>
                        </form>
                    </div>
                    {% endfor %}
                </div>
            </div>
            <div class="tab-pane fade {% if active_tab == 'reorder' %}show active{% endif %}" id="reorder">
                <ul class="nav nav-tabs sub-tabs" id="reorderTabs">
                    <li class="nav-item">
                        <button class="nav-link {% if active_reorder_tab == 'current-reorder' %}active{% endif %}" id="current-reorder-tab" 
                                data-bs-toggle="tab" data-bs-target="#current-reorder" type="button">Current Reorder List</button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link {% if active_reorder_tab == 'saved-reorder' %}active{% endif %}" id="saved-reorder-tab" 
                                data-bs-toggle="tab" data-bs-target="#saved-reorder" type="button">Saved Reorder Lists</button>
                    </li>
                </ul>
                <div class="tab-content" id="reorderTabContent">
                    <div class="tab-pane fade {% if active_reorder_tab == 'current-reorder' %}show active{% endif %}" id="current-reorder">
                        <h3>Current Reorder List</h3>
                        <div id="reorder-list-content">
                            {% if reorder_list %}
                            <ul class="list-group mb-3">
                                {% for product in reorder_list %}
                                <li class="list-group-item">{{ product['product_name'] }}</li>
                                {% endfor %}
                            </ul>
                            <div class="mb-3">
                                <button id="save-reorder-list" class="btn btn-primary me-2">Save List</button>
                                <label class="form-label">Download Format</label>
                                <select id="reorder-export-format" class="form-control" style="width: 200px; display: inline-block;">
                                    <option value="txt" selected>Text (.txt)</option>
                                    <option value="csv">CSV (.csv)</option>
                                    <option value="json">JSON (.json)</option>
                                </select>
                                <a href="/export_reorder_list?format=txt" id="export-reorder-link" class="btn btn-primary ms-2">Download Reorder List</a>
                            </div>
                            {% else %}
                            <p>No items in the reorder list.</p>
                            {% endif %}
                        </div>
                    </div>
                    <div class="tab-pane fade {% if active_reorder_tab == 'saved-reorder' %}show active{% endif %}" id="saved-reorder">
                        <h3>Saved Reorder Lists</h3>
                        <div id="saved-reorder-list-content">
                            {% if saved_reorder_lists %}
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Timestamp</th>
                                        <th>Products</th>
                                        <th>Download</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody id="saved-reorder-table-body">
                                    {% for saved_list in saved_reorder_lists %}
                                    <tr data-list-id="{{ saved_list['id'] }}">
                                        <td>{{ saved_list['timestamp'] }}</td>
                                        <td>{{ saved_list['products'] | join(', ') }}</td>
                                        <td>
                                            <select class="saved-reorder-format form-control" style="width: 120px; display: inline-block;" data-list-id="{{ saved_list['id'] }}">
                                                <option value="txt" selected>Text (.txt)</option>
                                                <option value="csv">CSV (.csv)</option>
                                                <option value="json">JSON (.json)</option>
                                            </select>
                                            <a href="/download_saved_reorder_list/{{ saved_list['id'] }}?format=txt" class="saved-reorder-download btn btn-primary btn-sm ms-2" data-list-id="{{ saved_list['id'] }}">Download</a>
                                        </td>
                                        <td>
                                            <button class="delete-reorder-list btn btn-danger btn-sm" data-list-id="{{ saved_list['id'] }}">Delete</button>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                            {% else %}
                            <p>No saved reorder lists.</p>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            <div class="tab-pane fade {% if active_tab == 'manage-products' %}show active{% endif %}" id="manage-products">
                <h3>Manage Products</h3>
                <ul class="nav nav-tabs sub-tabs" id="manageTabs">
                    <li class="nav-item">
                        <button class="nav-link {% if active_manage_tab == 'add-product' %}active{% endif %}" id="add-product-tab" 
                                data-bs-toggle="tab" data-bs-target="#add-product" type="button">Add Manually</button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link {% if active_manage_tab == 'import-export' %}active{% endif %}" id="import-export-tab" 
                                data-bs-toggle="tab" data-bs-target="#import-export" type="button">Import/Export</button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link {% if active_manage_tab == 'existing-products' %}active{% endif %}" id="existing-products-tab" 
                                data-bs-toggle="tab" data-bs-target="#existing-products" type="button">Existing Products</button>
                    </li>
                </ul>
                <div class="tab-content" id="manageTabContent">
                    <div class="tab-pane fade {% if active_manage_tab == 'add-product' %}show active{% endif %}" id="add-product">
                        <div class="form-section">
                            <h4>Add New Product</h4>
                            <form id="add-product-form" action="/add_product" method="post">
                                <div class="mb-3">
                                    <label class="form-label">Product Name</label>
                                    <input type="text" class="form-control" name="product_name" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Shelf Number</label>
                                    <select class="form-control" name="shelf_number" required>
                                        {% for shelf in range(1, 11) %}
                                        <option value="{{ shelf }}">Shelf {{ shelf }}</option>
                                        {% endfor %}
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label class="form-check-label">
                                        <input type="checkbox" class="form-check-input" name="in_stock" checked>
                                        In Stock
                                    </label>
                                </div>
                                <button type="submit" class="btn btn-primary">Add Product</button>
                            </form>
                        </div>
                    </div>
                    <div class="tab-pane fade {% if active_manage_tab == 'import-export' %}show active{% endif %}" id="import-export">
                        <div class="form-section">
                            <h4>Import/Export Products</h4>
                            <form id="import-products-form" action="/import_products" method="post" enctype="multipart/form-data">
                                <div class="mb-3">
                                    <label class="form-label">Import Products (CSV)</label>
                                    <input type="file" class="form-control" name="file" accept=".csv" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Default Shelf Number</label>
                                    <select class="form-control" name="default_shelf_number">
                                        {% for shelf in range(1, 11) %}
                                        <option value="{{ shelf }}" {% if shelf == 1 %}selected{% endif %}>Shelf {{ shelf }}</option>
                                        {% endfor %}
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label class="form-check-label">
                                        <input type="checkbox" class="form-check-input" name="default_in_stock" checked>
                                        Default In Stock
                                    </label>
                                </div>
                                <button type="submit" class="btn btn-primary">Import CSV</button>
                            </form>
                            <a href="/export_products" class="btn btn-primary mt-2">Export All Products to CSV</a>
                        </div>
                    </div>
                    <div class="tab-pane fade {% if active_manage_tab == 'existing-products' %}show active{% endif %}" id="existing-products">
                        <div class="form-section">
                            <h4>Existing Products</h4>
                            <form id="filter-products-form" action="#" method="get" class="mb-3">
                                <label class="form-label">Filter by Shelf</label>
                                <select class="form-control" name="shelf_filter" onchange="this.form.dispatchEvent(new Event('submit'))">
                                    <option value="all" {% if shelf_filter == 'all' %}selected{% endif %}>All Shelves</option>
                                    {% for shelf in range(1, 11) %}
                                    <option value="{{ shelf }}" {% if shelf_filter == shelf|string %}selected{% endif %}>Shelf {{ shelf }}</option>
                                    {% endfor %}
                                </select>
                            </form>
                            <button class="btn btn-primary mb-3" type="button" data-bs-toggle="collapse" data-bs-target="#productsTable">
                                Toggle Products List
                            </button>
                            <div class="collapse show table-container" id="productsTable">
                                <table class="table table-striped">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Name</th>
                                            <th>Shelf</th>
                                            <th>In Stock</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="products-table-body">
                                        {% if filtered_products %}
                                        {% for product in filtered_products %}
                                        <tr data-product-id="{{ product['product_id'] }}">
                                            <td>{{ product['product_id'] }}</td>
                                            <td>{{ product['product_name'] }}</td>
                                            <td>{{ product['shelf_number'] }}</td>
                                            <td>{{ 'Yes' if product['in_stock'] else 'No' }}</td>
                                            <td>
                                                <form class="edit-product-form" data-product-id="{{ product['product_id'] }}" action="/edit_product/{{ product['product_id'] }}" method="post">
                                                    <input type="number" name="product_id" value="{{ product['product_id'] }}" min="1" required>
                                                    <input type="text" name="product_name" value="{{ product['product_name'] }}" required>
                                                    <input type="number" name="shelf_number" value="{{ product['shelf_number'] }}" min="1" max="10" required>
                                                    <label><input type="checkbox" name="in_stock" {% if product['in_stock'] %}checked{% endif %}> In Stock</label>
                                                    <button type="submit" class="btn btn-primary btn-sm">Edit</button>
                                                </form>
                                                <form class="delete-product-form" data-product-id="{{ product['product_id'] }}" action="/delete_product/{{ product['product_id'] }}" method="post">
                                                    <button type="submit" class="btn btn-danger btn-sm">Delete</button>
                                                </form>
                                            </td>
                                        </tr>
                                        {% endfor %}
                                        {% else %}
                                        <tr><td colspan="5">No products found for this shelf.</td></tr>
                                        {% endif %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="footer-btn">
            <form method="post" action="/start_session">
                <button type="submit" name="session_type" value="new" class="btn btn-primary">New Session</button>
            </form>
        </div>
        {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Inactivity timer
        function inactivityTime() {
            let time;
            const modal = document.getElementById('sessionModal');
            const overlay = document.getElementById('overlay');
            const resetTimer = () => {
                console.log('Resetting inactivity timer');
                clearTimeout(time);
                modal.classList.remove('show');
                overlay.classList.remove('show');
                time = setTimeout(() => {
                    if ({{ session.get('show_inventory') | tojson }}) {
                        console.log('Showing session modal due to inactivity');
                        modal.classList.add('show');
                        overlay.classList.add('show');
                    }
                }, 120000);
            };
            window.onload = () => {
                console.log('Window loaded, show_inventory:', {{ session.get('show_inventory') | tojson }});
                if (!{{ session.get('show_inventory') | tojson }}) {
                    modal.classList.add('show');
                    overlay.classList.add('show');
                } else {
                    resetTimer();
                }
            };
            document.onmousemove = resetTimer;
            document.onkeypress = resetTimer;
            document.onclick = resetTimer;
            document.querySelectorAll('form').forEach(form => {
                form.addEventListener('submit', resetTimer);
            });
        }
        inactivityTime();

        // Update products table
        function updateProductsTable(products, shelfFilter) {
            console.log('Updating products table, shelf_filter:', shelfFilter, 'products:', products.length);
            const tbody = document.getElementById('products-table-body');
            if (!tbody) {
                console.error('Error: #products-table-body not found in DOM');
                return;
            }
            tbody.innerHTML = '';
            if (products.length > 0) {
                products.forEach(product => {
                    const tr = document.createElement('tr');
                    tr.setAttribute('data-product-id', product.product_id);
                    tr.innerHTML = `
                        <td>${product.product_id}</td>
                        <td>${product.product_name}</td>
                        <td>${product.shelf_number}</td>
                        <td>${product.in_stock ? 'Yes' : 'No'}</td>
                        <td>
                            <form class="edit-product-form" data-product-id="${product.product_id}" action="/edit_product/${product.product_id}" method="post">
                                <input type="number" name="product_id" value="${product.product_id}" min="1" required>
                                <input type="text" name="product_name" value="${product.product_name}" required>
                                <input type="number" name="shelf_number" value="${product.shelf_number}" min="1" max="10" required>
                                <label><input type="checkbox" name="in_stock" ${product.in_stock ? 'checked' : ''}> In Stock</label>
                                <button type="submit" class="btn btn-primary btn-sm">Edit</button>
                            </form>
                            <form class="delete-product-form" data-product-id="${product.product_id}" action="/delete_product/${product.product_id}" method="post">
                                <button type="submit" class="btn btn-danger btn-sm">Delete</button>
                            </form>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = '<tr><td colspan="5">No products found for this shelf.</td></tr>';
            }
            attachEditDeleteListeners();
        }

        // Update reorder list
        async function updateReorderList() {
            console.log('Fetching reorder list');
            try {
                const response = await fetch('/get_reorder_list');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const reorderList = await response.json();
                console.log('Reorder list fetched:', reorderList);
                const reorderTab = document.getElementById('reorder-list-content');
                if (!reorderTab) {
                    console.error('Error: #reorder-list-content not found in DOM');
                    return;
                }
                if (reorderList.length > 0) {
                    let html = '<ul class="list-group mb-3">';
                    reorderList.forEach(product => {
                        html += `<li class="list-group-item">${product.product_name}</li>`;
                    });
                    html += `</ul>
                        <div class="mb-3">
                            <button id="save-reorder-list" class="btn btn-primary me-2">Save List</button>
                            <label class="form-label">Download Format</label>
                            <select id="reorder-export-format" class="form-control" style="width: 200px; display: inline-block;">
                                <option value="txt" selected>Text (.txt)</option>
                                <option value="csv">CSV (.csv)</option>
                                <option value="json">JSON (.json)</option>
                            </select>
                            <a href="/export_reorder_list?format=txt" id="export-reorder-link" class="btn btn-primary ms-2">Download Reorder List</a>
                        </div>`;
                    reorderTab.innerHTML = html;
                } else {
                    reorderTab.innerHTML = '<p>No items in the reorder list.</p>';
                }
                attachExportFormatListener();
                attachSaveReorderListListener();
            } catch (error) {
                console.error('Error fetching reorder list:', error);
                alert('Error fetching reorder list: ' + error.message);
            }
        }

        // Update saved reorder lists
        async function updateSavedReorderLists() {
            console.log('Fetching saved reorder lists');
            try {
                const response = await fetch('/saved_reorder_lists');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const savedLists = await response.json();
                console.log('Saved reorder lists fetched:', savedLists);
                const savedTab = document.getElementById('saved-reorder-list-content');
                if (!savedTab) {
                    console.error('Error: #saved-reorder-list-content not found in DOM');
                    return;
                }
                if (savedLists.length > 0) {
                    let html = '<table class="table table-striped"><thead><tr><th>Timestamp</th><th>Products</th><th>Download</th><th>Action</th></tr></thead><tbody id="saved-reorder-table-body">';
                    savedLists.forEach(list => {
                        html += `<tr data-list-id="${list.id}">
                            <td>${list.timestamp}</td>
                            <td>${list.products.join(', ')}</td>
                            <td>
                                <select class="saved-reorder-format form-control" style="width: 120px; display: inline-block;" data-list-id="${list.id}">
                                    <option value="txt" selected>Text (.txt)</option>
                                    <option value="csv">CSV (.csv)</option>
                                    <option value="json">JSON (.json)</option>
                                </select>
                                <a href="/download_saved_reorder_list/${list.id}?format=txt" class="saved-reorder-download btn btn-primary btn-sm ms-2" data-list-id="${list.id}">Download</a>
                            </td>
                            <td>
                                <button class="delete-reorder-list btn btn-danger btn-sm" data-list-id="${list.id}">Delete</button>
                            </td>
                        </tr>`;
                    });
                    html += '</tbody></table>';
                    savedTab.innerHTML = html;
                } else {
                    savedTab.innerHTML = '<p>No saved reorder lists.</p>';
                }
                attachSavedReorderFormatListeners();
                attachDeleteReorderListListeners();
            } catch (error) {
                console.error('Error fetching saved reorder lists:', error);
                alert('Error fetching saved reorder lists: ' + error.message);
            }
        }

        // Handle export format selection
        function attachExportFormatListener() {
            const formatSelect = document.getElementById('reorder-export-format');
            const exportLink = document.getElementById('export-reorder-link');
            if (formatSelect && exportLink) {
                formatSelect.addEventListener('change', () => {
                    const selectedFormat = formatSelect.value;
                    console.log('Export format selected:', selectedFormat);
                    exportLink.href = `/export_reorder_list?format=${selectedFormat}`;
                });
            } else {
                console.error('Error: #reorder-export-format or #export-reorder-link not found in DOM');
            }
        }

        // Handle saved reorder list format selection
        function attachSavedReorderFormatListeners() {
            document.querySelectorAll('.saved-reorder-format').forEach(select => {
                const listId = select.getAttribute('data-list-id');
                const downloadLink = document.querySelector(`.saved-reorder-download[data-list-id="${listId}"]`);
                if (downloadLink) {
                    select.addEventListener('change', () => {
                        const selectedFormat = select.value;
                        console.log(`Saved reorder list ${listId} format selected:`, selectedFormat);
                        downloadLink.href = `/download_saved_reorder_list/${listId}?format=${selectedFormat}`;
                    });
                } else {
                    console.error(`Error: .saved-reorder-download for list ${listId} not found in DOM`);
                }
            });
        }

        // Handle save reorder list
        function attachSaveReorderListListener() {
            const saveButton = document.getElementById('save-reorder-list');
            if (saveButton) {
                saveButton.addEventListener('click', async () => {
                    console.log('Save reorder list button clicked');
                    const scrollY = window.scrollY;
                    try {
                        const response = await fetch('/save_reorder_list', { method: 'POST' });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const result = await response.json();
                        if (result.status === 'success') {
                            console.log('Reorder list saved successfully');
                            alert(result.message);
                            if (document.getElementById('saved-reorder').classList.contains('show')) {
                                await updateSavedReorderLists();
                            }
                            window.scrollTo(0, scrollY);
                        } else {
                            console.error('Error saving reorder list:', result.message);
                            alert('Error saving reorder list: ' + result.message);
                        }
                    } catch (error) {
                        console.error('Error saving reorder list:', error);
                        alert('Error saving reorder list: ' + error.message);
                    }
                });
            } else {
                console.error('Error: #save-reorder-list not found in DOM');
            }
        }

        // Handle delete reorder list
        function attachDeleteReorderListListeners() {
            document.querySelectorAll('.delete-reorder-list').forEach(button => {
                button.addEventListener('click', async () => {
                    const listId = button.getAttribute('data-list-id');
                    console.log('Delete reorder list button clicked, list_id:', listId);
                    if (!confirm('Are you sure you want to delete this reorder list?')) {
                        return;
                    }
                    const scrollY = window.scrollY;
                    try {
                        const response = await fetch(`/delete_reorder_list/${listId}`, { method: 'POST' });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const result = await response.json();
                        if (result.status === 'success') {
                            console.log('Reorder list deleted successfully, list_id:', listId);
                            await updateSavedReorderLists();
                            window.scrollTo(0, scrollY);
                            alert('Reorder list deleted successfully');
                        } else {
                            console.error('Error deleting reorder list:', result.message);
                            alert('Error deleting reorder list: ' + result.message);
                        }
                    } catch (error) {
                        console.error('Error deleting reorder list:', error);
                        alert('Error deleting reorder list: ' + error.message);
                    }
                });
            });
        }

        // Handle shelf form submissions
        document.querySelectorAll('.shelf-form').forEach(form => {
            form.querySelectorAll('.shelf-checkbox, .product-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', async () => {
                    console.log('Shelf checkbox changed, shelf:', form.getAttribute('data-shelf'));
                    const scrollY = window.scrollY;
                    const formData = new FormData(form);
                    try {
                        const response = await fetch(form.action, { method: 'POST', body: formData });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const result = await response.json();
                        if (result.status === 'success') {
                            console.log('Shelf updated successfully');
                            await updateReorderList();
                            window.scrollTo(0, scrollY);
                        } else {
                            console.error('Error updating shelf:', result.message);
                            alert('Error updating shelf: ' + result.message);
                        }
                    } catch (error) {
                        console.error('Error updating shelf:', error);
                        alert('Error updating shelf: ' + error.message);
                    }
                });
            });
        });

        // Handle add/import product forms
        function handleFormSubmit(formId, action, successMessage) {
            const form = document.getElementById(formId);
            if (form) {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    console.log(`${formId} submitted`);
                    const scrollY = window.scrollY;
                    const formData = new FormData(form);
                    try {
                        const response = await fetch(action, { method: 'POST', body: formData });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const result = await response.json();
                        if (result.status === 'success') {
                            console.log(successMessage);
                            form.reset();
                            window.scrollTo(0, scrollY);
                            alert(result.message || successMessage);
                            const shelfFilter = document.querySelector('#filter-products-form select[name="shelf_filter"]')?.value || 'all';
                            const filterResponse = await fetch(`/filter_products?shelf_filter=${shelfFilter}`);
                            if (filterResponse.ok) {
                                const filterResult = await filterResponse.json();
                                if (filterResult.status === 'success') {
                                    updateProductsTable(filterResult.products, shelfFilter);
                                }
                            }
                        } else {
                            console.error(`Error in ${formId}:`, result.message);
                            alert(`Error in ${formId}: ${result.message}`);
                        }
                    } catch (error) {
                        console.error(`Error in ${formId}:`, error);
                        alert(`Error in ${formId}: ${error.message}`);
                    }
                });
            } else {
                console.error(`Error: #${formId} not found in DOM`);
            }
        }
        handleFormSubmit('add-product-form', '/add_product', 'Product added successfully');
        handleFormSubmit('import-products-form', '/import_products', 'Products imported successfully');

        // Handle filter products form
        const filterForm = document.getElementById('filter-products-form');
        if (filterForm) {
            filterForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const shelfFilter = filterForm.querySelector('select[name="shelf_filter"]').value;
                console.log('Filter products form submitted, shelf_filter:', shelfFilter);
                const scrollY = window.scrollY;
                try {
                    const response = await fetch(`/filter_products?shelf_filter=${shelfFilter}`, { method: 'GET' });
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const result = await response.json();
                    console.log('Filter products response:', result);
                    if (result.status === 'success') {
                        updateProductsTable(result.products, shelfFilter);
                        window.scrollTo(0, scrollY);
                    } else {
                        console.error('Error filtering products:', result.message);
                        alert('Error filtering products: ' + result.message);
                    }
                } catch (error) {
                    console.error('Error filtering products:', error);
                    alert('Error filtering products: ' + error.message);
                }
            });
        } else {
            console.error('Error: #filter-products-form not found in DOM');
        }

        // Handle edit/delete product forms
        function attachEditDeleteListeners() {
            document.querySelectorAll('.edit-product-form, .delete-product-form').forEach(form => {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const isEdit = form.classList.contains('edit-product-form');
                    const productId = form.getAttribute('data-product-id');
                    console.log(`${isEdit ? 'Edit' : 'Delete'} product form submitted, product_id:`, productId);
                    const scrollY = window.scrollY;
                    try {
                        const response = await fetch(form.action, { method: 'POST', body: new FormData(form) });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const result = await response.json();
                        if (result.status === 'success') {
                            console.log(`Product ${isEdit ? 'updated' : 'deleted'} successfully`);
                            const shelfFilter = document.querySelector('#filter-products-form select[name="shelf_filter"]')?.value || 'all';
                            const filterResponse = await fetch(`/filter_products?shelf_filter=${shelfFilter}`);
                            if (filterResponse.ok) {
                                const filterResult = await filterResponse.json();
                                if (filterResult.status === 'success') {
                                    updateProductsTable(filterResult.products, shelfFilter);
                                }
                            }
                            window.scrollTo(0, scrollY);
                            alert(`Product ${isEdit ? 'updated' : 'deleted'} successfully`);
                        } else {
                            console.error(`Error ${isEdit ? 'updating' : 'deleting'} product:`, result.message);
                            alert(`Error ${isEdit ? 'updating' : 'deleting'} product: ${result.message}`);
                        }
                    } catch (error) {
                        console.error(`Error ${isEdit ? 'updating' : 'deleting'} product:`, error);
                        alert(`Error ${isEdit ? 'updating' : 'deleting'} product: ${error.message}`);
                    }
                });
            });
        }
        attachEditDeleteListeners();

        // Initialize Bootstrap tabs
        document.addEventListener('DOMContentLoaded', () => {
            console.log('Initializing Bootstrap tabs');
            document.querySelectorAll('#mainTabs button, #shelfTabs button, #manageTabs button, #reorderTabs button').forEach(triggerEl => {
                if (triggerEl.classList.contains('active')) {
                    new bootstrap.Tab(triggerEl).show();
                }
            });
        });

        // Refresh reorder list when switching to Current Reorder tab
        document.getElementById('current-reorder-tab').addEventListener('shown.bs.tab', async () => {
            console.log('Current Reorder tab shown, refreshing list');
            await updateReorderList();
        });

        // Refresh saved reorder lists when switching to Saved Reorder tab
        document.getElementById('saved-reorder-tab').addEventListener('shown.bs.tab', async () => {
            console.log('Saved Reorder tab shown, refreshing list');
            await updateSavedReorderLists();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    init_db()
    if not session.get('show_inventory'):
        session['show_inventory'] = False
    return render_template_string(HTML_TEMPLATE, shelves=[], all_products=[], filtered_products=[], reorder_list=[],
                                 saved_reorder_lists=[], active_tab='shelves', active_shelf_tab='shelf1', 
                                 active_manage_tab='existing-products', active_reorder_tab='current-reorder', shelf_filter='all')

@app.route('/favicon.ico')
def favicon():
    return make_response('', 204)

@app.route('/start_session', methods=['POST'])
def start_session():
    init_db()
    session_type = request.form.get('session_type')
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        if session_type == 'new':
            c.execute('UPDATE products SET in_stock = 1')
            c.execute('UPDATE shelves SET checked = 0')
            conn.commit()
            logger.info("New session started, reset products and shelves")
        else:
            logger.info("Continuing previous session")
        return show_inventory()

@app.route('/add_product', methods=['POST'])
def add_product():
    session['show_inventory'] = True
    product_name = request.form.get('product_name')
    shelf_number = int(request.form.get('shelf_number'))
    in_stock = 'in_stock' in request.form
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('INSERT INTO products (product_name, shelf_number, in_stock) VALUES (?, ?, ?)',
                     (product_name, shelf_number, in_stock))
            conn.commit()
            logger.info(f"Added product: {product_name}, Shelf: {shelf_number}, In Stock: {in_stock}")
            return jsonify({'status': 'success'})
        except sqlite3.Error as e:
            logger.error(f"Error adding product: {e}")
            return jsonify({'status': 'error', 'message': 'Error adding product to database.'})

@app.route('/edit_product/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    session['show_inventory'] = True
    new_product_id = int(request.form.get('product_id'))
    product_name = request.form.get('product_name')
    shelf_number = int(request.form.get('shelf_number'))
    in_stock = 'in_stock' in request.form
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT product_id FROM products WHERE product_id = ? AND product_id != ?', 
                 (new_product_id, product_id))
        if c.fetchone():
            logger.warning(f"Attempted to set duplicate product_id: {new_product_id}")
            return jsonify({'status': 'error', 'message': 'Product ID already exists.'})
        try:
            c.execute('UPDATE products SET product_id = ?, product_name = ?, shelf_number = ?, in_stock = ? WHERE product_id = ?',
                     (new_product_id, product_name, shelf_number, in_stock, product_id))
            conn.commit()
            logger.info(f"Edited product ID {product_id} to {new_product_id}: {product_name}, Shelf: {shelf_number}")
            return jsonify({'status': 'success'})
        except sqlite3.Error as e:
            logger.error(f"Error editing product: {e}")
            return jsonify({'status': 'error', 'message': 'Error editing product.'})

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('DELETE FROM products WHERE product_id = ?', (product_id,))
            conn.commit()
            logger.info(f"Deleted product ID: {product_id}")
            return jsonify({'status': 'success'})
        except sqlite3.Error as e:
            logger.error(f"Error deleting product: {e}")
            return jsonify({'status': 'error', 'message': 'Error deleting product.'})

@app.route('/update_shelf/<int:shelf_number>', methods=['POST'])
def update_shelf(shelf_number):
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        shelf_checked = 'shelf_checked' in request.form
        c.execute('UPDATE shelves SET checked = ? WHERE shelf_number = ?', 
                 (shelf_checked, shelf_number))
        c.execute('SELECT product_id FROM products WHERE shelf_number = ?', (shelf_number,))
        all_product_ids = [row['product_id'] for row in c.fetchall()]
        checked_product_ids = [int(key.split('_')[1]) for key in request.form if key.startswith('product_')]
        for product_id in all_product_ids:
            c.execute('UPDATE products SET in_stock = ? WHERE product_id = ?', 
                     (product_id in checked_product_ids, product_id))
        try:
            conn.commit()
            logger.info(f"Updated shelf {shelf_number}, checked: {shelf_checked}")
            return jsonify({'status': 'success'})
        except sqlite3.Error as e:
            logger.error(f"Error updating shelf: {e}")
            return jsonify({'status': 'error', 'message': 'Error updating shelf.'})

@app.route('/save_reorder_list', methods=['POST'])
def save_reorder_list():
    session['show_inventory'] = True
    timestamp = datetime.now().strftime('%d-%m-%y_%I:%M%p').lower()
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.product_id, p.product_name, p.shelf_number
            FROM products p JOIN shelves s ON p.shelf_number = s.shelf_number
            WHERE p.in_stock = 0 AND s.checked = 1
            ORDER BY p.shelf_number, p.product_name
        ''')
        reorder_list = c.fetchall()
        if not reorder_list:
            logger.warning("Attempted to save empty reorder list")
            return jsonify({'status': 'error', 'message': 'No items in the reorder list to save.'})
        product_names = [product['product_name'] for product in reorder_list]
        try:
            c.execute('INSERT INTO reorder_lists (timestamp, content) VALUES (?, ?)',
                     (timestamp, json.dumps(product_names)))
            conn.commit()
            logger.info(f"Saved reorder list to database, timestamp={timestamp}, count={len(reorder_list)}")
            return jsonify({'status': 'success', 'message': 'Reorder list saved successfully.'})
        except sqlite3.Error as e:
            logger.error(f"Error saving reorder list: {e}")
            return jsonify({'status': 'error', 'message': 'Error saving reorder list.'})

@app.route('/delete_reorder_list/<int:list_id>', methods=['POST'])
def delete_reorder_list(list_id):
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM reorder_lists WHERE id = ?', (list_id,))
        if not c.fetchone():
            logger.error(f"Attempted to delete non-existent reorder list: id={list_id}")
            return jsonify({'status': 'error', 'message': 'Reorder list not found.'})
        try:
            c.execute('DELETE FROM reorder_lists WHERE id = ?', (list_id,))
            conn.commit()
            logger.info(f"Deleted reorder list ID: {list_id}")
            return jsonify({'status': 'success', 'message': 'Reorder list deleted successfully.'})
        except sqlite3.Error as e:
            logger.error(f"Error deleting reorder list: {e}")
            return jsonify({'status': 'error', 'message': 'Error deleting reorder list.'})

@app.route('/import_products', methods=['POST'])
def import_products():
    session['show_inventory'] = True
    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        return jsonify({'status': 'error', 'message': 'Please upload a valid CSV file.'})
    default_shelf_number = int(request.form.get('default_shelf_number', 1))
    default_in_stock = 'default_in_stock' in request.form
    with get_db() as conn:
        c = conn.cursor()
        try:
            csv_content = file.stream.read().decode('utf-8').splitlines()
            csv_reader = csv.DictReader(csv_content)
            column_mapping = {
                'product_id': ['product_id', 'id', 'ID', 'Product ID'],
                'product_name': ['product_name', 'name', 'Name', 'Product Name', 'product'],
                'shelf_number': ['shelf_number', 'shelf', 'Shelf', 'Shelf Number', 'location'],
                'in_stock': ['in_stock', 'stock', 'Stock', 'In Stock', 'stock_status', 'Available']
            }
            is_names_only = len(csv_reader.fieldnames) == 1
            product_name_col = next((f for f in csv_reader.fieldnames if f.lower() in [a.lower() for a in column_mapping['product_name']]), csv_reader.fieldnames[0]) if is_names_only else None
            mapped_columns = {}
            if not is_names_only:
                for db_col, aliases in column_mapping.items():
                    for alias in aliases:
                        if alias in csv_reader.fieldnames:
                            mapped_columns[db_col] = alias
                            break
                    if db_col == 'product_name':
                        product_name_col = mapped_columns.get('product_name')
                    if db_col not in mapped_columns and db_col != 'product_id':
                        return jsonify({'status': 'error', 'message': f'Missing column for {db_col}.'})
            if not product_name_col:
                return jsonify({'status': 'error', 'message': 'Missing product name column.'})
            c.execute('SELECT MAX(product_id) FROM products')
            next_id = (c.fetchone()[0] or 0) + 1
            rows_imported = 0
            rows_skipped = 0
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    product_name = row[product_name_col].strip()
                    if not product_name:
                        logger.warning(f"Row {row_num}: Skipping empty product_name")
                        rows_skipped += 1
                        continue
                    if is_names_only:
                        product_id = next_id
                        shelf_number = default_shelf_number
                        in_stock = default_in_stock
                        next_id += 1
                    else:
                        product_id = int(row.get(mapped_columns.get('product_id', ''), '') or next_id)
                        if not row.get(mapped_columns.get('product_id', '')):
                            next_id += 1
                        c.execute('SELECT product_id FROM products WHERE product_id = ?', (product_id,))
                        if c.fetchone():
                            logger.warning(f"Row {row_num}: Skipping duplicate product_id: {product_id}")
                            rows_skipped += 1
                            continue
                        shelf_number = int(row.get(mapped_columns.get('shelf_number', ''), '') or default_shelf_number)
                        if not 1 <= shelf_number <= 10:
                            logger.warning(f"Row {row_num}: Invalid shelf_number: {shelf_number}")
                            rows_skipped += 1
                            continue
                        in_stock_raw = row.get(mapped_columns.get('in_stock', ''), '').strip().lower()
                        in_stock = default_in_stock if not in_stock_raw else {'true': 1, '1': 1, 'yes': 1, 'y': 1, 't': 1,
                                                                             'false': 0, '0': 0, 'no': 0, 'n': 0, 'f': 0}.get(in_stock_raw)
                        if in_stock is None:
                            logger.warning(f"Row {row_num}: Invalid in_stock: {in_stock_raw}")
                            rows_skipped += 1
                            continue
                    c.execute('INSERT INTO products (product_id, product_name, shelf_number, in_stock) VALUES (?, ?, ?, ?)',
                             (product_id, product_name, shelf_number, in_stock))
                    rows_imported += 1
                except (ValueError, sqlite3.Error) as e:
                    logger.warning(f"Row {row_num}: Skipping due to error: {e}")
                    rows_skipped += 1
                    continue
            conn.commit()
            logger.info(f"Imported {rows_imported} products, skipped {rows_skipped} rows")
            return jsonify({
                'status': 'success',
                'message': f'Imported {rows_imported} products. {rows_skipped} rows skipped.'
            })
        except sqlite3.Error as e:
            logger.error(f"Error importing CSV: {e}")
            return jsonify({'status': 'error', 'message': f'Error importing CSV: {str(e)}'})

@app.route('/export_products')
def export_products():
    session['show_inventory'] = True
    timestamp = datetime.now().strftime('%d-%m-%y_%I:%M%p').lower()
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM products ORDER BY product_id')
        products = c.fetchall()
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=['product_id', 'product_name', 'shelf_number', 'in_stock'], lineterminator='\n')
        writer.writeheader()
        for product in products:
            writer.writerow({
                'product_id': product['product_id'],
                'product_name': product['product_name'],
                'shelf_number': product['shelf_number'],
                'in_stock': 1 if product['in_stock'] else 0
            })
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8'))
        logger.info(f"Exported all products to CSV, count={len(products)}")
        return send_file(
            bytes_output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'products_export_{timestamp}.csv'
        )

@app.route('/export_reorder_list')
def export_reorder_list():
    session['show_inventory'] = True
    export_format = request.args.get('format', 'txt')
    if export_format not in ['txt', 'csv', 'json']:
        export_format = 'txt'
    timestamp = datetime.now().strftime('%d-%m-%y_%I:%M%p').lower()
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.product_id, p.product_name, p.shelf_number
            FROM products p JOIN shelves s ON p.shelf_number = s.shelf_number
            WHERE p.in_stock = 0 AND s.checked = 1
            ORDER BY p.shelf_number, p.product_name
        ''')
        reorder_list = c.fetchall()
        product_names = [product['product_name'] for product in reorder_list]
        # Save to reorder_lists table
        try:
            c.execute('INSERT INTO reorder_lists (timestamp, content) VALUES (?, ?)',
                     (timestamp, json.dumps(product_names)))
            conn.commit()
            logger.info(f"Saved reorder list to database, timestamp={timestamp}, count={len(reorder_list)}")
        except sqlite3.Error as e:
            logger.error(f"Error saving reorder list: {e}")
        if export_format == 'txt':
            output = StringIO()
            for product in reorder_list:
                output.write(f"{product['product_name']}\n")
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Exported reorder list to TXT, count={len(reorder_list)}")
            return send_file(
                bytes_output,
                mimetype='text/plain',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.txt'
            )
        elif export_format == 'csv':
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=['product_id', 'product_name', 'shelf_number'], lineterminator='\n')
            writer.writeheader()
            for product in reorder_list:
                writer.writerow({
                    'product_id': product['product_id'],
                    'product_name': product['product_name'],
                    'shelf_number': product['shelf_number']
                })
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Exported reorder list to CSV, count={len(reorder_list)}")
            return send_file(
                bytes_output,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.csv'
            )
        else:  # json
            output = StringIO()
            json.dump(product_names, output, indent=2)
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Exported reorder list to JSON, count={len(reorder_list)}")
            return send_file(
                bytes_output,
                mimetype='application/json',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.json'
            )

@app.route('/saved_reorder_lists')
def saved_reorder_lists():
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, timestamp, content FROM reorder_lists ORDER BY id DESC')
        saved_lists = c.fetchall()
        parsed_lists = [
            {'id': sl['id'], 'timestamp': sl['timestamp'], 'products': json.loads(sl['content'])}
            for sl in saved_lists
        ]
        logger.info(f"Fetched saved reorder lists, count={len(saved_lists)}")
        return jsonify(parsed_lists)

@app.route('/download_saved_reorder_list/<int:list_id>')
def download_saved_reorder_list(list_id):
    session['show_inventory'] = True
    export_format = request.args.get('format', 'txt')
    if export_format not in ['txt', 'csv', 'json']:
        export_format = 'txt'
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT timestamp, content FROM reorder_lists WHERE id = ?', (list_id,))
        saved_list = c.fetchone()
        if not saved_list:
            logger.error(f"Saved reorder list not found: id={list_id}")
            return jsonify({'status': 'error', 'message': 'Saved reorder list not found.'})
        timestamp = saved_list['timestamp']
        product_names = json.loads(saved_list['content'])
        if export_format == 'txt':
            output = StringIO()
            for name in product_names:
                output.write(f"{name}\n")
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Downloaded saved reorder list id={list_id} as TXT")
            return send_file(
                bytes_output,
                mimetype='text/plain',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.txt'
            )
        elif export_format == 'csv':
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=['product_name'], lineterminator='\n')
            writer.writeheader()
            for name in product_names:
                writer.writerow({'product_name': name})
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Downloaded saved reorder list id={list_id} as CSV")
            return send_file(
                bytes_output,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.csv'
            )
        else:  # json
            output = StringIO()
            json.dump(product_names, output, indent=2)
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Downloaded saved reorder list id={list_id} as JSON")
            return send_file(
                bytes_output,
                mimetype='application/json',
                as_attachment=True,
                download_name=f'reorder_list_{timestamp}.json'
            )

@app.route('/filter_products', methods=['GET'])
def filter_products():
    session['show_inventory'] = True
    shelf_filter = request.args.get('shelf_filter', 'all')
    with get_db() as conn:
        c = conn.cursor()
        if shelf_filter == 'all':
            c.execute('SELECT * FROM products ORDER BY shelf_number, product_id')
        else:
            c.execute('SELECT * FROM products WHERE shelf_number = ? ORDER BY product_id', (int(shelf_filter),))
        products = c.fetchall()
        logger.info(f"Filtered products for shelf_filter={shelf_filter}, count={len(products)}")
        return jsonify({
            'status': 'success',
            'products': [{'product_id': p['product_id'], 'product_name': p['product_name'], 
                         'shelf_number': p['shelf_number'], 'in_stock': p['in_stock']} for p in products]
        })

@app.route('/get_reorder_list', methods=['GET'])
def get_reorder_list():
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.product_id, p.product_name, p.shelf_number
            FROM products p JOIN shelves s ON p.shelf_number = s.shelf_number
            WHERE p.in_stock = 0 AND s.checked = 1
            ORDER BY p.shelf_number, p.product_name
        ''')
        reorder_list = c.fetchall()
        logger.info(f"Reorder list fetched, count={len(reorder_list)}")
        return jsonify([{'product_id': p['product_id'], 'product_name': p['product_name'], 
                        'shelf_number': p['shelf_number']} for p in reorder_list])

def show_inventory(active_tab='shelves', active_shelf_tab='shelf1', active_manage_tab='existing-products', 
                  active_reorder_tab='current-reorder', shelf_filter='all'):
    session['show_inventory'] = True
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM shelves ORDER BY shelf_number')
        shelves = c.fetchall()
        c.execute('SELECT * FROM products ORDER BY shelf_number, product_id')
        all_products = c.fetchall()
        if shelf_filter == 'all':
            c.execute('SELECT * FROM products ORDER BY shelf_number, product_id')
        else:
            c.execute('SELECT * FROM products WHERE shelf_number = ? ORDER BY product_id', (int(shelf_filter),))
        filtered_products = c.fetchall()
        c.execute('''
            SELECT p.product_id, p.product_name, p.shelf_number
            FROM products p JOIN shelves s ON p.shelf_number = s.shelf_number
            WHERE p.in_stock = 0 AND s.checked = 1
            ORDER BY p.shelf_number, p.product_name
        ''')
        reorder_list = c.fetchall()
        c.execute('SELECT id, timestamp, content FROM reorder_lists ORDER BY id DESC')
        saved_lists = c.fetchall()
        saved_reorder_lists = [
            {'id': sl['id'], 'timestamp': sl['timestamp'], 'products': json.loads(sl['content'])}
            for sl in saved_lists
        ]
        logger.info(f"Rendering inventory: active_tab={active_tab}, shelf_filter={shelf_filter}, products={len(all_products)}, filtered={len(filtered_products)}, reorder={len(reorder_list)}, saved_reorder={len(saved_reorder_lists)}")
        return render_template_string(HTML_TEMPLATE, shelves=shelves, all_products=all_products, filtered_products=filtered_products,
                                     reorder_list=reorder_list, saved_reorder_lists=saved_reorder_lists, active_tab=active_tab, 
                                     active_shelf_tab=active_shelf_tab, active_manage_tab=active_manage_tab, 
                                     active_reorder_tab=active_reorder_tab, shelf_filter=shelf_filter)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)