from flask import Flask, render_template
from flask_socketio import SocketIO, send

app = Flask(__name__)

app.config["SECRET"]="RwandaChat"

socketio=SocketIO(app,cors_allowed_origins="*")

@socketio.on("message")

def handle_messege(message):
    print("Recived message: " + message)
    if message != "User connected":
        send(message, broadcast=True)

@app.route("/")
def index():
    return render_template("test.html")

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000 ,host="192.168.1.178")


