import os
from decimal import Decimal
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'change-this-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///safecyberbank.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    transactions = db.relationship('Transaction', backref='user', lazy=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def serialize(self):
        return {
            'username': self.username,
            'role': self.role,
            'balance': format(self.balance, '.2f'),
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    from_user = db.Column(db.String(64), nullable=False)
    to_user = db.Column(db.String(64), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'type': self.type,
            'amount': format(self.amount, '.2f'),
            'from': self.from_user,
            'to': self.to_user,
            'timestamp': self.timestamp.isoformat(),
        }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'message': 'Authentication required'}), 401
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get('username')
        user = User.query.filter_by(username=username).first()
        if not user or user.role != 'admin':
            return jsonify({'message': 'Admin privileges required'}), 403
        return f(*args, **kwargs)

    return decorated


def get_current_user():
    username = session.get('username')
    if not username:
        return None
    return User.query.filter_by(username=username).first()


def serialize_profile(user):
    transactions = (
        Transaction.query.filter_by(user_id=user.id)
        .order_by(Transaction.timestamp.desc())
        .all()
    )
    debit_transactions = [
        t.serialize() for t in transactions if t.type == 'debit'
    ]
    credit_transactions = [
        t.serialize() for t in transactions if t.type == 'credit'
    ]
    return {
        'user': user.serialize(),
        'users': [u.serialize() for u in User.query.order_by(User.username).all()],
        'debit_transactions': debit_transactions,
        'credit_transactions': credit_transactions,
    }


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/login', methods=['POST'])
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username', '').strip()
    password = payload.get('password', '')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'message': 'Wrong username or password'}), 401

    session['username'] = user.username
    return jsonify(serialize_profile(user))


@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    session.pop('username', None)
    return jsonify({'message': 'Logged out'})


@app.route('/api/profile', methods=['GET'])
@login_required
def profile():
    user = get_current_user()
    if not user:
        return jsonify({'message': 'Authentication required'}), 401
    return jsonify(serialize_profile(user))


@app.route('/api/users', methods=['GET'])
@login_required
def list_users():
    return jsonify({'users': [u.serialize() for u in User.query.order_by(User.username).all()]})


@app.route('/api/send-money', methods=['POST'])
@login_required
def send_money():
    user = get_current_user()
    if user.role != 'client':
        return jsonify({'message': 'Only clients may send money'}), 403

    payload = request.get_json(silent=True) or {}
    recipient_name = payload.get('recipient', '').strip()
    amount_value = payload.get('amount')

    try:
        amount = Decimal(str(amount_value))
    except Exception:
        return jsonify({'message': 'Invalid amount'}), 400

    if amount <= 0:
        return jsonify({'message': 'Amount must be greater than zero'}), 400

    recipient = User.query.filter_by(username=recipient_name).first()
    if not recipient or recipient.role != 'client':
        return jsonify({'message': 'Recipient not found'}), 404

    if amount > user.balance:
        return jsonify({'message': 'Insufficient funds'}), 400

    user.balance -= amount
    recipient.balance += amount

    timestamp = datetime.utcnow()
    sender_tx = Transaction(
        user_id=user.id,
        type='debit',
        amount=amount,
        from_user=user.username,
        to_user=recipient.username,
        timestamp=timestamp,
    )
    recipient_tx = Transaction(
        user_id=recipient.id,
        type='credit',
        amount=amount,
        from_user=user.username,
        to_user=recipient.username,
        timestamp=timestamp,
    )

    db.session.add_all([sender_tx, recipient_tx])
    db.session.commit()
    return jsonify(serialize_profile(user))


@app.route('/api/add-credit', methods=['POST'])
@login_required
@admin_required
def add_credit():
    payload = request.get_json(silent=True) or {}
    target_username = payload.get('username', '').strip()
    amount_value = payload.get('amount')

    try:
        amount = Decimal(str(amount_value))
    except Exception:
        return jsonify({'message': 'Invalid amount'}), 400

    if amount <= 0:
        return jsonify({'message': 'Amount must be greater than zero'}), 400

    target_user = User.query.filter_by(username=target_username).first()
    if not target_user:
        return jsonify({'message': 'User not found'}), 404

    target_user.balance += amount
    tx = Transaction(
        user_id=target_user.id,
        type='credit',
        amount=amount,
        from_user=session['username'],
        to_user=target_user.username,
        timestamp=datetime.utcnow(),
    )

    db.session.add(tx)
    db.session.commit()
    return jsonify(serialize_profile(target_user))


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/<path:path>')
def static_file(path):
    return app.send_static_file(path)


def seed_data():
    if User.query.count() > 0:
        return

    users = [
        ('saran', 'saran2026', 'client', Decimal('1000.00')),
        ('naveen', 'naveen2026', 'client', Decimal('1000.00')),
        ('prasanna', 'prasanna2026', 'client', Decimal('1000.00')),
        ('administrator', 'admin2026', 'admin', Decimal('0.00')),
    ]

    for username, password, role, balance in users:
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            balance=balance,
        )
        db.session.add(user)

    db.session.commit()


def init_app():
    db.create_all()
    seed_data()


if __name__ == '__main__':
    with app.app_context():
        init_app()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=os.environ.get('FLASK_DEBUG', '1') == '1')
