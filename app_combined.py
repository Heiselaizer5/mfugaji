from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from datetime import datetime

app = FastAPI()

# --- Python Backend Logic ---
def calculate_profit(chicks, feed_cost, med_cost, revenue):
    total_cost = chicks * 500 + feed_cost + med_cost
    profit = revenue - total_cost
    return total_cost, profit

# --- HTML Page (design) embedded in Python ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mfugaji Kwanza Lite</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: linear-gradient(135deg, #0a0a1a, #1a1a2e);
            color: #fff;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .card {
            background: linear-gradient(145deg, #1a1a2e, #16213e);
            border: 1px solid #2a2a4a;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        h1 {
            color: #00E676;
            font-size: 28px;
            text-align: center;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #888;
            text-align: center;
            font-size: 13px;
            margin-bottom: 24px;
        }
        label {
            color: #AAA;
            font-size: 13px;
            font-weight: 600;
            display: block;
            margin-top: 14px;
            margin-bottom: 4px;
        }
        input {
            width: 100%;
            padding: 12px 16px;
            background: #0a0a1a;
            border: 1px solid #3a3a5a;
            border-radius: 12px;
            color: #FFF;
            font-size: 15px;
            outline: none;
        }
        input:focus {
            border-color: #00E676;
            box-shadow: 0 0 0 2px rgba(0,230,118,0.15);
        }
        button {
            width: 100%;
            padding: 14px;
            margin-top: 20px;
            background: linear-gradient(135deg, #00E676, #00c853);
            color: #000;
            border: none;
            border-radius: 14px;
            font-size: 16px;
            font-weight: 800;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(0,230,118,0.4);
        }
        .result {
            margin-top: 20px;
            padding: 16px;
            border-radius: 12px;
            text-align: center;
            font-size: 18px;
            font-weight: 700;
        }
        .profit { background: #0a2a0a; border: 1px solid #00E676; color: #00E676; }
        .loss { background: #2a0a0a; border: 1px solid #FF5252; color: #FF5252; }
        .footer {
            text-align: center;
            margin-top: 20px;
            color: #555;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>🐔 Mfugaji Kwanza</h1>
        <p class="subtitle">Profit Calculator — Lite Version</p>

        <label>Number of Chicks</label>
        <input type="number" id="chicks" value="100" min="0">

        <label>Feed Cost (TSH)</label>
        <input type="number" id="feed" value="50000" min="0">

        <label>Medicine Cost (TSH)</label>
        <input type="number" id="med" value="10000" min="0">

        <label>Total Revenue (TSH)</label>
        <input type="number" id="revenue" value="200000" min="0">

        <button onclick="calculate()">💰 Calculate Profit</button>

        <div id="result"></div>
        <div class="footer" id="footer"></div>
    </div>

    <script>
        function calculate() {
            const chicks = document.getElementById('chicks').value;
            const feed = document.getElementById('feed').value;
            const med = document.getElementById('med').value;
            const revenue = document.getElementById('revenue').value;

            fetch('/api/calculate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chicks, feed_cost: feed, med_cost: med, revenue })
            })
            .then(res => res.json())
            .then(data => {
                const div = document.getElementById('result');
                if (data.profit >= 0) {
                    div.className = 'result profit';
                    div.innerHTML = `🎉 Profit: <strong>${data.profit.toLocaleString()} TSH</strong>`;
                } else {
                    div.className = 'result loss';
                    div.innerHTML = `⚠️ Loss: <strong>${Math.abs(data.profit).toLocaleString()} TSH</strong>`;
                }
                document.getElementById('footer').textContent = `Total Cost: ${data.total_cost.toLocaleString()} TSH`;
            });
        }

        calculate();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML_PAGE

@app.post("/api/calculate")
async def calc(data: dict):
    chicks = int(data.get("chicks", 0))
    feed = float(data.get("feed_cost", 0))
    med = float(data.get("med_cost", 0))
    revenue = float(data.get("revenue", 0))
    total_cost, profit = calculate_profit(chicks, feed, med, revenue)
    return {"total_cost": total_cost, "profit": profit}

@app.get("/api/time")
async def get_time():
    return {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
