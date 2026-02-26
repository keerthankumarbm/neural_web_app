from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import yfinance as yf
import pandas as pd

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- DATABASE CONFIG ----------------

database_url = os.getenv("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///local.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Create tables in production also
with app.app_context():
    db.create_all()

# ---------------- MODELS ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(120))
    password = db.Column(db.String(200))


class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    stock_symbol = db.Column(db.String(20))
    model_used = db.Column(db.String(50))
    predicted_value = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    rating = db.Column(db.Integer)
    message = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return redirect('/login')

# REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form['password'])
        user = User(
            username=request.form['username'],
            email=request.form['email'],
            password=hashed_pw
        )
        db.session.add(user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect('/dashboard')
    return render_template('login.html')

# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# DASHBOARD
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        symbol = request.form['symbol']
        model = request.form['model']

        try:
            data = yf.download(symbol, period="6mo")

            if data.empty:
                return "Invalid stock symbol or no data available"

            data['MA20'] = data['Close'].rolling(window=20).mean()
            data = data.dropna()

            current_price = float(data['Close'].values[-1])
            predicted_price = current_price * 1.02

            trend = "Bullish 📈" if predicted_price > current_price else "Bearish 📉"

            # Save prediction
            new_prediction = Prediction(
                user_id=session['user_id'],
                stock_symbol=symbol,
                model_used=model,
                predicted_value=predicted_price
            )
            db.session.add(new_prediction)
            db.session.commit()

            return render_template(
                'result.html',
                symbol=symbol,
                current=round(current_price, 2),
                predicted=round(predicted_price, 2),
                trend=trend,
                dates=data.index.strftime('%Y-%m-%d').tolist(),
                closes=data['Close'].round(2).values.tolist(),
                ma20=data['MA20'].round(2).values.tolist()
            )

        except Exception as e:
            print("Prediction Error:", e)
            return "Prediction Failed. Check logs."

    return render_template('dashboard.html')

# FEEDBACK
@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        fb = Feedback(
            user_id=session['user_id'],
            rating=int(request.form['rating']),
            message=request.form['message']
        )
        db.session.add(fb)
        db.session.commit()
        return redirect('/dashboard')

    return render_template('feedback.html')

# ADMIN
@app.route('/admin')
def admin():
    feedbacks = Feedback.query.all()
    total_predictions = Prediction.query.count()
    total_users = User.query.count()

    avg_rating = db.session.query(db.func.avg(Feedback.rating)).scalar()
    avg_rating = round(avg_rating, 2) if avg_rating else 0

    most_used_model = db.session.query(
        Prediction.model_used,
        db.func.count(Prediction.model_used)
    ).group_by(Prediction.model_used).order_by(
        db.func.count(Prediction.model_used).desc()
    ).first()

    most_used_model = most_used_model[0] if most_used_model else "No Data"

    return render_template(
        'admin.html',
        feedbacks=feedbacks,
        total_predictions=total_predictions,
        total_users=total_users,
        avg_rating=avg_rating,
        most_used_model=most_used_model
    )

# ---------------- RUN ----------------

if __name__ == '__main__':
    app.run(debug=True)