from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit
from flask_cors import CORS
import chess
import time
import json
import os

app = Flask(__name__)
CORS(app) # Разрешаем запросы с GitHub Pages
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

games = {}
HISTORY_FILE = "history.json"

if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r") as f:
            saved_games = json.load(f)
            for room_id, g_data in saved_games.items():
                board = chess.Board(g_data.get('fen', chess.STARTING_FEN))
                games[room_id] = {
                    'board': board,
                    'players': g_data.get('players', {}),
                    'history': g_data.get('history', []),
                    'status': 'finished',
                    'time_left': {'w': 0, 'b': 0},
                    'time_control': g_data.get('time_control', 600)
                }
    except Exception as e:
        print("Ошибка загрузки истории:", e)

def save_history():
    safe_games = {}
    for r_id, g in games.items():
        if g['status'] == 'finished':
            safe_games[r_id] = {
                'fen': g['board'].fen(),
                'history': g['history'],
                'players': {uid: {'name': p['name'], 'photo': p.get('photo', '')} for uid, p in g['players'].items()},
                'status': g['status'],
                'time_control': g['time_control']
            }
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(safe_games, f)
    except Exception as e:
        print("Ошибка сохранения:", e)

@app.route('/get_game/<room_id>')
def get_game(room_id):
    if room_id in games:
        g = games[room_id]
        if g['status'] != 'finished':
            return {"error": "Партия еще не завершена"}, 400
        return {
            'history': g['history'],
            'players': g['players'],
            'status': g['status'],
            'fen': g['board'].fen(),
            'time_control': g['time_control']
        }
    return {"error": "Game not found"}, 404

@socketio.on('join')
def on_join(data):
    room = data['room']
    user_name = data.get('name', 'Игрок')
    user_id = data.get('user_id', str(request.sid)) 
    user_photo = data.get('photo_url', '')
    time_control = data.get('time_control', 600)
    
    join_room(room)
    
    if room not in games:
        games[room] = {
            'board': chess.Board(),
            'players': {},
            'time_control': time_control,
            'time_left': {'w': time_control, 'b': time_control},
            'turn_start_time': time.time(),
            'history': [],
            'status': 'waiting'
        }
    else:
        if games[room]['status'] == 'waiting':
            games[room]['status'] = 'playing'
            games[room]['turn_start_time'] = time.time()
    
    games[room]['players'][user_id] = {'name': user_name, 'photo': user_photo, 'sid': request.sid}
    
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
    
    now = time.time()
    elapsed = now - game['turn_start_time']
    current_turn = 'w' if board.turn == chess.WHITE else 'b'
    
    game['time_left'][current_turn] -= elapsed
    if game['time_left'][current_turn] < 0: game['time_left'][current_turn] = 0
        
    try:
        from_sq, to_sq = move_data['from'], move_data['to']
        piece = board.piece_at(chess.parse_square(from_sq))
        
        if piece and piece.piece_type == chess.PAWN and (to_sq[1] == '8' or to_sq[1] == '1'):
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}q")
        else:
            chess_move = chess.Move.from_uci(f"{from_sq}{to_sq}")
            
        if chess_move in board.legal_moves:
            move_san = board.san(chess_move) 
            board.push(chess_move)
            game['history'].append(move_san)
            game['turn_start_time'] = time.time()
            
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
    room, color = data['room'], data['color']
    if room in games and games[room]['status'] == 'playing':
        games[room]['status'] = 'finished'
        winner = 'black' if color == 'w' else 'white'
        emit('game_over', {'result': 'timeout', 'winner': winner}, room=room)
        save_history()
