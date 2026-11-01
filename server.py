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
    user_id = data.get('user_id', str(request.sid)) # Используем Telegram ID
    user_name = data.get('name', 'Игрок')
    join_room(room)
    
    if room not in games:
        games[room] = {'board': chess.Board(), 'players': {}}
    
    # Сохраняем игрока по его Telegram ID
    games[room]['players'][user_id] = user_name
    print(f"ВОШЕЛ В КОМНАТУ {room}: {user_name} (ID: {user_id})")
    
    emit('players_update', games[room]['players'], room=room)
    emit('board_state', {'fen': games[room]['board'].fen()}, room=room)

@socketio.on('move')
def on_move(data):
    room = data['room']
    move_data = data['move']
    
    if room not in games: return
    
    board = games[room]['board']
    try:
        from_sq = move_data['from']
        to_sq = move_data['to']
        
        piece = board.piece_at(chess.parse_square(from_sq))
        
        if piece and piece.piece_type == chess.PAWN and (to_sq[1] == '8' or to_sq[1] == '1'):
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
        emit('invalid_move', {'msg': 'Ошибка сервера'}, to=request.sid)

@socketio.on('disconnect')
def on_disconnect():
    # МЫ БОЛЬШЕ НЕ УДАЛЯЕМ ИГРОКА ЗДЕСЬ!
    # Просто выводим лог, чтобы комната жила, пока игрок спит в фоне.
    print(f"ОТКЛЮЧЕН (свернул приложение): {request.sid}")
