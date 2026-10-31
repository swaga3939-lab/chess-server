from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit
import chess

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

games = {}

@app.route('/')
def index():
    return "Chess Server is running!"

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    if room not in games:
        games[room] = {'board': chess.Board(), 'players': []}
    
    games[room]['players'].append(request.sid)
    print(f"Player {request.sid} joined room {room}")
    
    emit('board_state', {'fen': games[room]['board'].fen()}, room=room)

@socketio.on('move')
def on_move(data):
    room = data['room']
    move = data['move']
    
    if room not in games:
        return
    
    board = games[room]['board']
    try:
        chess_move = chess.Move.from_uci(f"{move['from']}{move['to']}")
        if chess_move in board.legal_moves:
            board.push(chess_move)
            emit('board_state', {'fen': board.fen()}, room=room)
            
            if board.is_checkmate():
                winner = 'black' if board.turn == chess.WHITE else 'white'
                emit('game_over', {'result': 'checkmate', 'winner': winner}, room=room)
            elif board.is_stalemate():
                emit('game_over', {'result': 'stalemate'}, room=room)
        else:
            emit('invalid_move', {'msg': 'Нелегальный ход'}, to=request.sid)
    except Exception as e:
        emit('invalid_move', {'msg': str(e)}, to=request.sid)

@socketio.on('disconnect')
def on_disconnect():
    print(f"Player {request.sid} disconnected")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
