import os
import threading
import queue
import subprocess
import time

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import pygame

# Inicializa el mixer de pygame para audio
pygame.mixer.init()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

SONG_FOLDER = os.path.join(os.getcwd(), 'songs')
play_queue = queue.Queue()
current_song = None
queue_lock = threading.Lock()

def player_worker():
    global current_song
    while True:
        song = play_queue.get()
        if song is None:
            break
        path = os.path.join(SONG_FOLDER, song)
        if not os.path.isfile(path):
            play_queue.task_done()
            continue

        with queue_lock:
            current_song = song
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.5)
        except Exception as e:
            print(f"[ERROR PLAYBACK] {e}")
        with queue_lock:
            current_song = None
        play_queue.task_done()

# Arranca el hilo de reproducción
threading.Thread(target=player_worker, daemon=True).start()

# Vista Usuario
@app.route('/')
def index():
    return render_template('index.html')

# Vista Admin oculta en /home/albertito
@app.route('/albertitoeselmejor')
def admin_view():
    return render_template('admin.html')

# API: listar canciones recursivamente
@app.route('/api/songs', methods=['GET'])
def get_songs():
    song_list = []
    for root, _, files in os.walk(SONG_FOLDER):
        for f in files:
            if f.lower().endswith(('.mp3', '.wav')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, SONG_FOLDER).replace('\\', '/')
                song_list.append(rel_path)
    return jsonify(song_list)

# API: estado de la cola
@app.route('/api/queue', methods=['GET'])
def get_queue():
    with queue_lock:
        cola = []
        if current_song:
            cola.append(current_song)
        cola.extend(list(play_queue.queue))
    return jsonify(cola)

# API: añadir canción
@app.route('/api/queue', methods=['POST'])
def add_to_queue():
    song = request.get_json().get('song')
    path = os.path.join(SONG_FOLDER, song or '')
    if not song or not os.path.isfile(path):
        return jsonify({'error': 'Canción no encontrada'}), 404
    play_queue.put(song)
    return jsonify({'status': 'ok'}), 201

# API: eliminar canción (solo admin)
@app.route('/api/queue', methods=['DELETE'])
def remove_from_queue():
    song = request.get_json().get('song')
    if not song:
        return jsonify({'error': 'No song specified'}), 400

    removed = False
    with play_queue.mutex:
        try:
            play_queue.queue.remove(song)
            removed = True
        except ValueError:
            pass

    # Si estaba sonando, deténla
    global current_song
    with queue_lock:
        if not removed and current_song == song:
            pygame.mixer.music.stop()
            current_song = None
            removed = True

    if not removed:
        return jsonify({'error': 'Song not in queue'}), 404
    return jsonify({'status': 'removed'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
