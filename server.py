from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit
import chess

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

games = {}

@socketio.on('connect')
def on_connect():
    print(f"ПОДКЛЮЧЕН: {request.sid}")

@socketio.on('join')
def on_join(data):
    room = data['room']
    user_name = data.get('name', 'Игрок')
    join_room(room)
    
    if room not in games:
        games[room] = {'board': chess.Board(), 'players': {}}
    
    games[room]['players'][request.sid] = user_name
    
    print(f"ВОШЕЛ В КОМНАТУ {room}: {user_name} ({request.sid})")
    
    emit('players_update', games[room]['players'], room=room)
    emit('board_state', {'fen': games[room]['board'].fen()}, room=room)

@socketio.on('move')
def on_move(data):
    room = data['room']
    move_data = data['move']
    print(f"ПОЛУЧЕН ХОД В {room}: {move_data}")
    
    if room not in games:
        return
    
    board = games[room]['board']
    try:
        from_sq = move_data['from']
        to_sq = move_data['to']
        
        if (to_sq[1] == '8' or to_sq[1] == '1'):
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}q")
        else:
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}")
            
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
        print(f"ОШИБКА: {e}")
        emit('invalid_move', {'msg': 'Ошибка сервера'}, to=request.sid)

@socketio.on('disconnect')
def on_disconnect():
    print(f"ОТКЛЮЧЕН: {request.sid}")
    for room, game_data in list(games.items()):
        if request.sid in game_data['players']:
            del game_data['players'][request.sid]
            emit('players_update', game_data['players'], room=room)
            if len(game_data['players']) == 0:
                del games[room]
