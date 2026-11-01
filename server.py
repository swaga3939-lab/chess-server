from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit
import chess
import time
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

games = {}
HISTORY_FILE = "history.json"

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(games, f)
    except Exception as e:
        print("Ошибка сохранения истории:", e)

@app.route('/get_game/<room_id>')
def get_game(room_id):
    if room_id in games:
        return games[room_id]
    return {"error": "Game not found"}, 404

@socketio.on('join')
def on_join(data):
    room = data['room']
    user_name = data.get('name', 'Игрок')
    user_id = data.get('user_id', str(request.sid)) 
    user_photo = data.get('photo_url', '')
    time_control = data.get('time_control', 600) # По умолчанию 10 минут
    action = data.get('action', 'join') # create или join
    
    join_room(room)
    
    if room not in games:
        # Создаем новую игру
        games[room] = {
            'board': chess.Board(),
            'players': {},
            'time_control': time_control,
            'time_left': {'w': time_control, 'b': time_control},
            'turn_start_time': time.time(),
            'history': [],
            'status': 'waiting' # waiting, playing, finished
        }
    else:
        # Если игра уже идет (присоединение)
        if games[room]['status'] == 'waiting':
            games[room]['status'] = 'playing'
            games[room]['turn_start_time'] = time.time()
    
    # Добавляем игрока
    games[room]['players'][user_id] = {
        'name': user_name, 
        'photo': user_photo,
        'sid': request.sid
    }
    
    print(f"Игрок {user_name} зашел в комнату {room}. Режим: {time_control} сек.")
    
    # Отправляем данные всем в комнате
    emit('players_update', games[room]['players'], room=room)
    emit('game_state', {
        'fen': games[room]['board'].fen(),
        'status': games[room]['status'],
        'time_left': games[room]['time_left'],
        'history': games[room]['history'],
        'time_control': games[room]['time_control']
    }, room=room)

@socketio.on('move')
def on_move(data):
    room = data['room']
    move_data = data['move']
    
    if room not in games or games[room]['status'] != 'playing': return
    
    game = games[room]
    board = game['board']
    
    # Считаем время
    now = time.time()
    elapsed = now - game['turn_start_time']
    current_turn = 'w' if board.turn == chess.WHITE else 'b'
    
    # Вычитаем время
    game['time_left'][current_turn] -= elapsed
    if game['time_left'][current_turn] < 0:
        game['time_left'][current_turn] = 0
        
    try:
        from_sq = move_data['from']
        to_sq = move_data['to']
        
        piece = board.piece_at(chess.parse_square(from_sq))
        if piece and piece.piece_type == chess.PAWN and (to_sq[1] == '8' or to_sq[1] == '1'):
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}q")
        else:
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}")
            
        if chess_move in board.legal_moves:
            # ВОТ ТУТ МАГИЯ: получаем красивую нотацию (f4, Nf3) ДО хода
            move_san = board.san(chess_move) 
            
            board.push(chess_move)
            game['history'].append(move_san) # Сохраняем красивую нотацию
            game['turn_start_time'] = time.time() # Сброс таймера для следующего
            
            # Проверка на конец игры
            if board.is_checkmate():
                game['status'] = 'finished'
                winner = 'white' if board.turn == chess.BLACK else 'black'
                emit('game_over', {'result': 'checkmate', 'winner': winner}, room=room)
                save_history()
            elif board.is_stalemate() or board.is_insufficient_material():
                game['status'] = 'finished'
                emit('game_over', {'result': 'draw'}, room=room)
                save_history()
            else:
                emit('game_state', {
                    'fen': board.fen(),
                    'status': game['status'],
                    'time_left': game['time_left'],
                    'history': game['history']
                }, room=room)
        else:
            emit('invalid_move', {'msg': 'Нелегальный ход'}, to=request.sid)
    except Exception as e:
        emit('invalid_move', {'msg': 'Ошибка сервера'}, to=request.sid)

@socketio.on('timeout')
def on_timeout(data):
    room = data['room']
    color = data['color'] # Кто просрочил время
    if room in games and games[room]['status'] == 'playing':
        games[room]['status'] = 'finished'
        winner = 'black' if color == 'w' else 'white'
        emit('game_over', {'result': 'timeout', 'winner': winner}, room=room)
        save_history()
