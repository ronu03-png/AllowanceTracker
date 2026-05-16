import csv
import io
import json
import os
import uuid
from calendar import monthrange
from pathlib import Path
from datetime import date, timedelta

from flask import Flask, Response, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / 'users.json'

app = Flask(__name__)
app.secret_key = os.getenv('ALLOWANCE_SECRET', 'dev-secret-key')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, username, password_hash=None, data=None):
        self.id = username
        self.password_hash = password_hash
        self.data = data or {'allowance': 100.0, 'entries': []}

def load_users():
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open('r', encoding='utf-8') as handle:
        return json.load(handle)

def save_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding='utf-8')

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id, users[user_id]['password_hash'], users[user_id]['data'])
    return None

@app.template_filter('currency')
def currency(value):
    return f'₱{value:,.2f}'

def get_monthly_spending(entries):
    """Calculate total spending by month."""
    monthly = {}
    for entry in entries:
        month_key = entry.get('date', '')[:7]  # YYYY-MM format
        if month_key:
            monthly[month_key] = monthly.get(month_key, 0) + entry.get('amount', 0)
    # Return sorted by month
    return dict(sorted(monthly.items()))

def get_daily_spending(entries, month=None):
    """Calculate total spending by day for a given month."""
    daily = {}
    for entry in entries:
        date_key = entry.get('date', '')  # YYYY-MM-DD format
        if not date_key:
            continue
        if month and not date_key.startswith(month):
            continue
        daily[date_key] = daily.get(date_key, 0) + entry.get('amount', 0)
    return dict(sorted(daily.items()))


def get_daily_by_category(entries, month=None):
    """Calculate spending per day grouped by category for a given month.
    Returns: { category: { 'YYYY-MM-DD': total_amount } }
    """
    grouped = {}
    for entry in entries:
        date_key = entry.get('date', '')
        if not date_key:
            continue
        if month and not date_key.startswith(month):
            continue
        category = entry.get('category', 'Other') or 'Other'
        grouped.setdefault(category, {})
        grouped[category][date_key] = grouped[category].get(date_key, 0) + entry.get('amount', 0)
    return grouped


def get_category_totals(entries, month=None):
    """Calculate total spending per category for a given month."""
    totals = {}
    for entry in entries:
        date_key = entry.get('date', '')
        if month and not date_key.startswith(month):
            continue
        category = entry.get('category', 'Other') or 'Other'
        totals[category] = totals.get(category, 0) + entry.get('amount', 0)
    return totals


DEFAULT_CATEGORIES = ['Food', 'Transport', 'Shopping', 'School', 'Other']


def ensure_user_data_shape(data):
    """Backfill optional fields on a user's data blob. Returns True if changed."""
    changed = False
    if 'entries' not in data:
        data['entries'] = []
        changed = True
    for entry in data.get('entries', []):
        if not entry.get('id'):
            entry['id'] = uuid.uuid4().hex[:10]
            changed = True
    if 'categories' not in data or not isinstance(data['categories'], list) or not data['categories']:
        data['categories'] = list(DEFAULT_CATEGORIES)
        changed = True
    if 'budgets' not in data or not isinstance(data['budgets'], dict):
        data['budgets'] = {}
        changed = True
    return changed


def days_left_in_month(today):
    """How many days (including today) remain in `today`'s month."""
    _, last_day = monthrange(today.year, today.month)
    return max(1, last_day - today.day + 1)


def _persist(data):
    """Helper: save current user's data back to disk."""
    users = load_users()
    users[current_user.id]['data'] = data
    save_users(users)


def parse_month_param(month_str, today):
    """Parse a 'YYYY-MM' string; return (key, year, month). Falls back to today."""
    if month_str:
        try:
            parts = month_str.split('-')
            year = int(parts[0])
            month = int(parts[1])
            if 1 <= month <= 12 and 1900 <= year <= 2999:
                return f'{year:04d}-{month:02d}', year, month
        except (ValueError, IndexError, AttributeError):
            pass
    return today.strftime('%Y-%m'), today.year, today.month


def shift_month(year, month, delta):
    """Return (year, month) shifted by delta months (positive or negative)."""
    index = year * 12 + (month - 1) + delta
    new_year = index // 12
    new_month = (index % 12) + 1
    return new_year, new_month


def get_streak(entries, today):
    """Consecutive days ending today (or yesterday) with at least one entry."""
    days = {e.get('date', '') for e in entries if e.get('date')}
    cursor = today
    # If today has no entry yet, allow the streak to start from yesterday.
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@app.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    data = current_user.data
    # Backfill ids / categories / budgets for older accounts
    if ensure_user_data_shape(data):
        _persist(data)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_allowance':
            allowance_value = request.form.get('allowance')
            try:
                amount = float(allowance_value)
            except (TypeError, ValueError):
                amount = 0.0

            if amount <= 0:
                flash('Allowance must be a positive number.', 'danger')
            else:
                data['allowance'] = amount
                _persist(data)
                flash('Allowance updated. Your history is safe.', 'success')
            return redirect(url_for('dashboard'))

        if action == 'reset_entries':
            confirm = request.form.get('confirm', '')
            if confirm != 'RESET':
                flash('Type RESET to confirm clearing your spending history.', 'danger')
            else:
                data['entries'] = []
                _persist(data)
                flash('Spending history cleared.', 'success')
            return redirect(url_for('dashboard'))

        if action == 'save_entry':
            amount_value = request.form.get('amount')
            category = request.form.get('category', '').strip()
            location = request.form.get('location', '').strip()
            entry_date = request.form.get('date', '').strip() or date.today().isoformat()
            description = request.form.get('description', '').strip()

            try:
                amount = float(amount_value)
            except (TypeError, ValueError):
                amount = 0.0

            if amount <= 0 or not category or not location or not entry_date:
                flash('Enter a valid amount, category, location, and date.', 'danger')
                return redirect(url_for('dashboard'))

            data['entries'].append({
                'id': uuid.uuid4().hex[:10],
                'amount': amount,
                'category': category,
                'location': location,
                'date': entry_date,
                'description': description,
            })
            _persist(data)
            flash('Allowance entry saved.', 'success')
            return redirect(url_for('dashboard'))

        if action == 'delete_entry':
            entry_id = request.form.get('entry_id', '').strip()
            before = len(data.get('entries', []))
            data['entries'] = [e for e in data.get('entries', []) if e.get('id') != entry_id]
            if len(data['entries']) < before:
                _persist(data)
                flash('Entry deleted.', 'success')
            else:
                flash('Could not find that entry.', 'danger')
            return redirect(url_for('dashboard'))

        if action == 'add_category':
            name = request.form.get('category_name', '').strip()
            if not name:
                flash('Category name is required.', 'danger')
            elif len(name) > 30:
                flash('Category name is too long (max 30 chars).', 'danger')
            elif name in data['categories']:
                flash(f'"{name}" already exists.', 'danger')
            else:
                data['categories'].append(name)
                _persist(data)
                flash(f'Added category "{name}".', 'success')
            return redirect(url_for('dashboard'))

        if action == 'rename_category':
            old = request.form.get('old_name', '').strip()
            new = request.form.get('new_name', '').strip()
            if not new:
                flash('New name is required.', 'danger')
            elif len(new) > 30:
                flash('Category name is too long (max 30 chars).', 'danger')
            elif old not in data['categories']:
                flash('That category no longer exists.', 'danger')
            elif new != old and new in data['categories']:
                flash(f'"{new}" already exists.', 'danger')
            elif new == old:
                flash('Name is unchanged.', 'info')
            else:
                idx = data['categories'].index(old)
                data['categories'][idx] = new
                # Update all entries using the old name
                for e in data.get('entries', []):
                    if e.get('category') == old:
                        e['category'] = new
                # Move budget cap, if any
                if old in data['budgets']:
                    data['budgets'][new] = data['budgets'].pop(old)
                _persist(data)
                flash(f'Renamed "{old}" to "{new}".', 'success')
            return redirect(url_for('dashboard'))

        if action == 'remove_category':
            name = request.form.get('category_name', '').strip()
            if name not in data['categories']:
                flash('Category not found.', 'danger')
            elif len(data['categories']) <= 1:
                flash('You need at least one category.', 'danger')
            elif any(e.get('category') == name for e in data.get('entries', [])):
                flash(f'Cannot remove "{name}" — it is used by existing entries. Rename or delete those entries first.', 'danger')
            else:
                data['categories'].remove(name)
                data['budgets'].pop(name, None)
                _persist(data)
                flash(f'Removed category "{name}".', 'success')
            return redirect(url_for('dashboard'))

        if action == 'update_budgets':
            new_budgets = {}
            for cat in data['categories']:
                raw = (request.form.get(f'budget_{cat}', '') or '').strip()
                if not raw:
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if val > 0:
                    new_budgets[cat] = val
            data['budgets'] = new_budgets
            _persist(data)
            flash('Category budgets updated.', 'success')
            return redirect(url_for('dashboard'))

    today = date.today()
    entries = data.get('entries', [])
    spent = sum(entry.get('amount', 0) for entry in entries)
    allowance = data.get('allowance', 0)
    remaining = allowance - spent
    percent_used = (spent / allowance * 100) if allowance > 0 else 0
    days_left = days_left_in_month(today)
    daily_budget = max(remaining, 0) / days_left if days_left else 0
    streak = get_streak(entries, today)

    # Selected month (via ?month=YYYY-MM); defaults to current month
    selected_month, sel_year, sel_month = parse_month_param(
        request.args.get('month', '').strip(), today
    )
    is_current_month = (sel_year == today.year and sel_month == today.month)
    prev_y, prev_m = shift_month(sel_year, sel_month, -1)
    next_y, next_m = shift_month(sel_year, sel_month, +1)
    prev_month_key = f'{prev_y:04d}-{prev_m:02d}'
    next_month_key = f'{next_y:04d}-{next_m:02d}'
    # Disable forward navigation when we'd go past the current month
    next_disabled = (next_y, next_m) > (today.year, today.month)
    month_display = date(sel_year, sel_month, 1).strftime('%B %Y')

    daily_spending = get_daily_spending(entries, month=selected_month)
    daily_by_category = get_daily_by_category(entries, month=selected_month)
    category_totals = get_category_totals(entries, month=selected_month)
    monthly_total = sum(category_totals.values())

    # Filter chip / form options: union of user's categories + any orphans
    user_categories = data.get('categories', list(DEFAULT_CATEGORIES))
    extra_categories = [c for c in category_totals.keys() if c not in user_categories]
    categories = list(user_categories) + extra_categories

    # Per-category budget progress (against current month for clarity)
    current_month_totals = (
        category_totals if is_current_month
        else get_category_totals(entries, month=today.strftime('%Y-%m'))
    )
    budgets = data.get('budgets', {})
    budget_rows = []
    for cat in user_categories:
        cap = float(budgets.get(cat, 0) or 0)
        used = float(current_month_totals.get(cat, 0) or 0)
        pct = (used / cap * 100) if cap > 0 else 0
        if cap <= 0:
            state = 'none'
        elif pct >= 100:
            state = 'over'
        elif pct >= 80:
            state = 'warn'
        else:
            state = 'ok'
        budget_rows.append({
            'category': cat,
            'cap': cap,
            'used': used,
            'pct': pct,
            'pct_clamped': min(pct, 100),
            'state': state,
        })

    return render_template(
        'dashboard.html',
        data=data,
        spent=spent,
        remaining=remaining,
        percent_used=percent_used,
        days_left=days_left,
        daily_budget=daily_budget,
        streak=streak,
        today=today.isoformat(),
        daily_spending=daily_spending,
        daily_by_category=daily_by_category,
        category_totals=category_totals,
        monthly_total=monthly_total,
        categories=categories,
        user_categories=user_categories,
        budget_rows=budget_rows,
        current_month=selected_month,
        month_display=month_display,
        is_current_month=is_current_month,
        prev_month_key=prev_month_key,
        next_month_key=next_month_key,
        next_disabled=next_disabled,
    )


@app.route('/export.csv')
@login_required
def export_csv():
    """Download all (or one month's) entries as CSV."""
    data = current_user.data
    ensure_user_data_shape(data)
    entries = data.get('entries', [])
    month = request.args.get('month', '').strip()
    if month:
        entries = [e for e in entries if e.get('date', '').startswith(month)]
    entries_sorted = sorted(entries, key=lambda e: e.get('date', ''))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Category', 'Amount', 'Location', 'Description'])
    for e in entries_sorted:
        writer.writerow([
            e.get('date', ''),
            e.get('category', ''),
            f"{float(e.get('amount', 0)):.2f}",
            e.get('location', ''),
            e.get('description', ''),
        ])
    csv_text = output.getvalue()
    output.close()

    filename = f"allowance_{month or 'all'}.csv"
    return Response(
        csv_text,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        
        users = load_users()
        if username in users and check_password_hash(users[username]['password_hash'], password):
            user = User(username, users[username]['password_hash'], users[username]['data'])
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            flash('Username and password are required.', 'danger')
        elif password != confirm_password:
            flash('Passwords do not match.', 'danger')
        else:
            users = load_users()
            if username in users:
                flash('Username already exists.', 'danger')
            else:
                password_hash = generate_password_hash(password)
                users[username] = {
                    'password_hash': password_hash,
                    'data': {
                        'allowance': 100.0,
                        'entries': [],
                        'categories': list(DEFAULT_CATEGORIES),
                        'budgets': {},
                    },
                }
                save_users(users)
                user = User(username, password_hash, users[username]['data'])
                login_user(user)
                flash('Account created successfully.', 'success')
                return redirect(url_for('dashboard'))
    
    return render_template('signup.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
