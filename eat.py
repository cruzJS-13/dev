from flask import Flask, render_template, jsonify, request
import hashlib
import os
from square.http.auth.o_auth_2 import BearerAuthCredentials
from square.client import Client as SquareClient
import json
import time
import sqlite3

import uuid

app = Flask(__name__)

# Initialize Square client
square_client = SquareClient(
    bearer_auth_credentials=BearerAuthCredentials(
        access_token=os.getenv('SQUARE_ACCESS_TOKEN')
    ),
    environment='sandbox')

TOTAL_SUPPLY = 10000
current_price = 1.0  # Initial price per Rizzcoin

# Wallet system
wallets = {}

def create_wallet():
    address = str(uuid.uuid4())
    save_wallet(address, 0)
    return address

def get_rizzcoin_price():
    global current_price
    return current_price

@app.route('/price', methods=['GET', 'POST'])
def price():
    amount = request.args.get('amount', type=float, default=1.0)
    total_price = get_rizzcoin_price() * amount
    return jsonify({'price': total_price}), 200

@app.route('/create_wallet', methods=['POST'])
def create_wallet_route():
    address = create_wallet()
    return jsonify({'address': address}), 200

@app.route('/buy', methods=['POST'])
def buy():
    data = request.json
    address = data.get('address')
    amount = data.get('amount')
    balance = get_wallet_balance(address)
    # Here you would integrate with Square API to process the payment
    # For example, create a payment with square_client.payments.create_payment()
    if balance is not None and amount > 0:
        cost = amount * get_rizzcoin_price()
        new_balance = balance + amount
        update_wallet_balance(address, new_balance)
        return jsonify({'message': f'Bought {amount} Rizzcoin for ${cost}'}), 200
    return jsonify({'error': 'Invalid address or amount'}), 400

@app.route('/sell', methods=['POST'])
def sell():
    data = request.json
    address = data.get('address')
    amount = data.get('amount')
    nonce = data.get('nonce')
    idempotency_key = nonce + str(time.time()) + address + str(amount)
    balance = get_wallet_balance(address)
    result = square_client.payments.create_payment({
            "source_id": nonce,
            "idempotency_key": idempotency_key,
            "amount_money": {
                "amount": amount,
                "currency": "USD"
            },
            "location_id": os.getenv("SQUARE_LOCATION_ID")
        })
    if result.is_success():
        if balance is not None and 0 < amount <= balance:
            earnings = amount * get_rizzcoin_price()
            new_balance = balance - amount
            update_wallet_balance(address, new_balance)
            return jsonify({'message': f'Sold {amount} Rizzcoin for ${earnings}'}), 200
    else:
        return jsonify({'error': 'Payment failed'}), 400
    return jsonify({'error': 'Invalid address or amount'}), 400

# Initialize database
def init_db():
    conn = sqlite3.connect('blockchain.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS blockchain
                 (index INTEGER PRIMARY KEY, timestamp TEXT, data TEXT, previous_hash TEXT, hash TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS wallets
                 (address TEXT PRIMARY KEY, balance REAL)''')
    conn.commit()
    conn.close()

def save_wallet(address, balance):
    conn = sqlite3.connect('blockchain.db')
    c = conn.cursor()
    c.execute("INSERT INTO wallets (address, balance) VALUES (?, ?)", (address, balance))
    conn.commit()
    conn.close()

def update_wallet_balance(address, balance):
    conn = sqlite3.connect('blockchain.db')
    c = conn.cursor()
    c.execute("UPDATE wallets SET balance = ? WHERE address = ?", (balance, address))
    conn.commit()
    conn.close()

def get_wallet_balance(address):
    conn = sqlite3.connect('blockchain.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# Blockchain class
class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_block(previous_hash='0')

    def create_block(self, data='', previous_hash=''):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'data': data,
            'previous_hash': previous_hash,
            'hash': ''
        }
        block['hash'] = self.hash(block)
        self.chain.append(block)
        self.save_block(block)
        return block

    def hash(self, block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def save_block(self, block):
        conn = sqlite3.connect('blockchain.db')
        c = conn.cursor()
        c.execute("INSERT INTO blockchain (index, timestamp, data, previous_hash, hash) VALUES (?, ?, ?, ?, ?)",
                  (block['index'], block['timestamp'], block['data'], block['previous_hash'], block['hash']))
        conn.commit()
        conn.close()

    def get_chain(self):
        conn = sqlite3.connect('blockchain.db')
        c = conn.cursor()
        c.execute("SELECT * FROM blockchain")
        chain = c.fetchall()
        conn.close()
        return chain

blockchain = Blockchain()
init_db()

@app.route('/mine', methods=['POST'])
def mine():
    data = request.json.get('data', '')
    previous_block = blockchain.chain[-1]
    block = blockchain.create_block(data, previous_block['hash'])
    return jsonify(block), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    chain = blockchain.get_chain()
    return jsonify(chain), 200

@app.route('/')
def home():
    return render_template('index.html')
    print("eat")

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5000)