import os
import threading
import queue
import time

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pygame

pygame.mixer.init()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

SONG_FOLDER = os.path.join(os.getcwd(), 'songs')
UPLOAD_FOLDER = os.path.join(SONG_FOLDER, 'reggaeton')
ALLOWED_EXTENSIONS = {'mp3', 'wav'}

play_queue = queue.Queue()
current_song = None
queue_lock = threading.Lock()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

threading.Thread(target=player_worker, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/albertitoeselmejor')
def admin_view():
    return render_template('admin.html')

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

@app.route('/api/upload', methods=['POST'])
def upload_song():
    # espera multipart/form-data con campo 'song'
    if 'song' not in request.files:
        return jsonify({'error': 'No se ha enviado ningún fichero'}), 400
    file = request.files['song']
    if file.filename == '':
        return jsonify({'error': 'Nombre de fichero vacío'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        dest = os.path.join(UPLOAD_FOLDER, filename)
        file.save(dest)
        return jsonify({'status': 'ok'}), 201
    else:
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

@app.route('/api/queue', methods=['GET'])
def get_queue():
    with queue_lock:
        cola = []
        if current_song:
            cola.append(current_song)
        cola.extend(list(play_queue.queue))
    return jsonify(cola)

@app.route('/api/queue', methods=['POST'])
def add_to_queue():
    data = request.get_json()
    song = data.get('song')
    pos = data.get('position')
    path = os.path.join(SONG_FOLDER, song or '')
    if not song or not os.path.isfile(path):
        return jsonify({'error': 'Canción no encontrada'}), 404

    play_queue.put(song)

    if pos is not None:
        try:
            pos_int = int(pos)
        except ValueError:
            return jsonify({'error': 'Posición inválida'}), 400

        with play_queue.mutex:
            q = play_queue.queue
            last = q.pop()  # recién añadido
            idx = pos_int - 2
            if idx < 0:
                idx = 0
            if idx > len(q):
                idx = len(q)
            q.insert(idx, last)

    return jsonify({'status': 'ok'}), 201

@app.route('/api/queue', methods=['DELETE'])
def remove_from_queue():
    data = request.get_json()
    song = data.get('song')
    if not song:
        return jsonify({'error': 'No song specified'}), 400

    removed = False
    with play_queue.mutex:
        try:
            play_queue.queue.remove(song)
            removed = True
        except ValueError:
            pass

    global current_song
    with queue_lock:
        if not removed and current_song == song:
            pygame.mixer.music.stop()
            current_song = None
            removed = True

    if not removed:
        return jsonify({'error': 'Song not in queue'}), 404
    return jsonify({'status': 'removed'}), 200

@app.route('/api/queue/move', methods=['POST'])
def move_in_queue():
    data = request.get_json()
    song = data.get('song')
    pos = data.get('position')
    if not song or pos is None:
        return jsonify({'error': 'Faltan datos'}), 400

    try:
        pos_int = int(pos)
    except ValueError:
        return jsonify({'error': 'Posición inválida'}), 400

    with play_queue.mutex:
        q = play_queue.queue
        try:
            q.remove(song)
        except ValueError:
            return jsonify({'error': 'Canción no está en la cola'}), 404

        idx = pos_int - 2
        if idx < 0:
            idx = 0
        if idx > len(q):
            idx = len(q)
        q.insert(idx, song)

    return jsonify({'status': 'moved'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
