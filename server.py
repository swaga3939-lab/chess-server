from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit
import chess

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

games = {}

@socketio.on('join')
def on_join(data):
    room = data['room']
    user_name = data.get('name', 'Соперник')
    join_room(room)
    
    if room not in games:
        games[room] = {'board': chess.Board(), 'players': {}}
    
    games[room]['players'][request.sid] = user_name
    
    # Отправляем список игроков в комнату
    emit('players_update', {'players': list(games[room]['players'].values())}, room=room)
    # Отправляем текущую позицию доски
    emit('board_state', {'fen': games[room]['board'].fen()}, room=room)

@socketio.on('move')
def on_move(data):
    room = data['room']
    move_data = data['move']
    
    if room not in games:
        return
    
    board = games[room]['board']
    try:
        # Поддержка превращения пешки (по умолчанию в ферзя)
        promo = move_data.get('promotion', 'q')
        chess_move = chess.Move.from_uci(f"{move_data['from']}{move_data['to']}{promo}")
        
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
    # Если игрок выходит, убираем его из комнаты
    for room, game_data in list(games.items()):
        if request.sid in game_data['players']:
            del game_data['players'][request.sid]
            emit('players_update', {'players': list(game_data['players'].values())}, room=room)
            if len(game_data['players']) == 0:
                del games[room]
