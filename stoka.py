import os
from flask import Flask, render_template_string, request, session, send_file, jsonify
from io import BytesIO, StringIO
import sqlite3
import logging
import csv
import json
from contextlib import contextmanager

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
    if not os.path.exists(db_path):
        logger.info(f"Creating database at: {db_path}")
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS products
                         (product_id INTEGER PRIMARY KEY,
                          product_name TEXT,
                          shelf_number INTEGER,
                          in_stock BOOLEAN)''')
            c.execute('''CREATE TABLE IF NOT EXISTS shelves
                         (shelf_number INTEGER PRIMARY KEY,
                          checked BOOLEAN)''')
            for shelf in range(1, 11):
                c.execute('INSERT OR IGNORE INTO shelves (shelf_number, checked) VALUES (?, ?)', 
                         (shelf, False))
            conn.commit()
            logger.info("Database initialized with shelves")

# HTML template with sub-tabs for Manage Products
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
        .logo { position: fixed; top: 20px; left: 20px; font-size: 2rem; font-weight: bold; color: #d2b48c; }
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
                                <div class="col-md-4 mb-2">
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
                <h3>Reorder List</h3>
                <div id="reorder-list-content">
                    {% if reorder_list %}
                    <ul class="list-group mb-3">
                        {% for product in reorder_list %}
                        <li class="list-group-item">{{ product['product_name'] }}</li>
                        {% endfor %}
                    </ul>
                    <div class="mb-3">
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
            } catch (error) {
                console.error('Error fetching reorder list:', error);
                alert('Error fetching reorder list: ' + error.message);
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
            document.querySelectorAll('#mainTabs button, #shelfTabs button, #manageTabs button').forEach(triggerEl => {
                if (triggerEl.classList.contains('active')) {
                    new bootstrap.Tab(triggerEl).show();
                }
            });
        });

        // Refresh reorder list when switching to Reorder tab
        document.getElementById('reorder-tab').addEventListener('shown.bs.tab', async () => {
            console.log('Reorder tab shown, refreshing list');
            await updateReorderList();
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
                                 active_tab='shelves', active_shelf_tab='shelf1', active_manage_tab='existing-products', shelf_filter='all')

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
            download_name='products_export.csv'
        )

@app.route('/export_reorder_list')
def export_reorder_list():
    session['show_inventory'] = True
    export_format = request.args.get('format', 'txt')
    if export_format not in ['txt', 'csv', 'json']:
        export_format = 'txt'
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.product_id, p.product_name, p.shelf_number
            FROM products p JOIN shelves s ON p.shelf_number = s.shelf_number
            WHERE p.in_stock = 0 AND s.checked = 1
            ORDER BY p.shelf_number, p.product_name
        ''')
        reorder_list = c.fetchall()
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
                download_name='reorder_list.txt'
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
                download_name='reorder_list.csv'
            )
        else:  # json
            product_names = [product['product_name'] for product in reorder_list]
            output = StringIO()
            json.dump(product_names, output, indent=2)
            output.seek(0)
            bytes_output = BytesIO(output.getvalue().encode('utf-8'))
            logger.info(f"Exported reorder list to JSON, count={len(reorder_list)}")
            return send_file(
                bytes_output,
                mimetype='application/json',
                as_attachment=True,
                download_name='reorder_list.json'
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

def show_inventory(active_tab='shelves', active_shelf_tab='shelf1', active_manage_tab='existing-products', shelf_filter='all'):
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
        logger.info(f"Rendering inventory: active_tab={active_tab}, shelf_filter={shelf_filter}, products={len(all_products)}, filtered={len(filtered_products)}, reorder={len(reorder_list)}")
        return render_template_string(HTML_TEMPLATE, shelves=shelves, all_products=all_products, filtered_products=filtered_products,
                                     reorder_list=reorder_list, active_tab=active_tab, active_shelf_tab=active_shelf_tab, 
                                     active_manage_tab=active_manage_tab, shelf_filter=shelf_filter)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)