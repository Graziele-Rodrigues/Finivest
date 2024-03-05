import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get user's cash balance
    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # Get user's stocks and their current prices
    user_stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
                             session["user_id"])

    total_portfolio_value = user_cash

    # Calculate total value of each stock and overall portfolio value
    for stock in user_stocks:
        quote_info = lookup(stock["symbol"])
        stock["name"] = quote_info["name"]
        stock["price"] = quote_info["price"]
        stock["total_value"] = stock["price"] * stock["total_shares"]
        total_portfolio_value += stock["total_value"]

    return render_template("index.html", user_stocks=user_stocks, user_cash=user_cash, total_portfolio_value=total_portfolio_value)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 403)

        # Ensure shares is a positive integer
        try:
            shares = int(request.form.get("shares"))
            if shares <= 0:
                raise ValueError
        except ValueError:
            return apology("shares must be a positive integer", 403)

        # Lookup the symbol
        quote_info = lookup(request.form.get("symbol"))

        # Ensure symbol is valid
        if not quote_info:
            return apology("invalid symbol", 403)

        # Calculate total price
        total_price = quote_info["price"] * shares

        # Get user's cash balance
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # Ensure user can afford the purchase
        if user_cash < total_price:
            return apology("can't afford the purchase", 403)

        # Deduct purchase amount from user's cash balance
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_price, session["user_id"])

        # Add transaction to transactions table
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], quote_info["symbol"], shares, quote_info["price"], "buy")

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get user's transaction history
    transactions = db.execute("SELECT symbol, shares, price, transaction_type, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC",
                              session["user_id"])

    return render_template("history.html", transactions=transactions)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Lookup the symbol
        quote_info = lookup(request.form.get("symbol"))

        # Ensure symbol is valid
        if not quote_info:
            return apology("invalid symbol", 403)

        return render_template("quoted.html", quote_info=quote_info)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 403)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        # Hash password
        hash_password = generate_password_hash(request.form.get("password"))

        # Insert user into database
        result = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                            request.form.get("username"), hash_password)

        # Check if username already exists
        if not result:
            return apology("username already exists", 403)

        # Remember user session
        session["user_id"] = result

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 403)

        # Ensure shares is a positive integer
        try:
            shares = int(request.form.get("shares"))
            if shares <= 0:
                raise ValueError
        except ValueError:
            return apology("shares must be a positive integer", 403)

        # Lookup the symbol
        quote_info = lookup(request.form.get("symbol"))

        # Ensure symbol is valid
        if not quote_info:
            return apology("invalid symbol", 403)

        # Get user's shares of the symbol
        user_shares = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = ? AND symbol = ?",
                                 session["user_id"], quote_info["symbol"])[0]["total_shares"]

        # Ensure user has enough shares
        if user_shares < shares:
            return apology("not enough shares to sell", 403)

        # Deduct sold shares from user's stocks
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], quote_info["symbol"], -shares, quote_info["price"], "sell")

        # Update user's cash balance
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", quote_info["price"] * shares, session["user_id"])

        # Redirect user to home page
        return redirect("/")

    else:
        # Get user's stocks to populate select options
        user_stocks = db.execute("SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0",
                                  session["user_id"])

        return render_template("sell.html", user_stocks=user_stocks)



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
