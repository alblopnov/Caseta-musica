const API = '';
const songsPerPage = 20;
let currentPage = 1;
let allSongs = [];
let selectedCategory = 'Todas';
let categories = ['Todas'];

async function fetchSongs() {
  const data = (await axios.get(`${API}/api/songs`)).data;
  categories = ['Todas'];
  data.forEach(path => {
    const parts = path.split('/');
    if (parts.length > 1 && !categories.includes(parts[0])) {
      categories.push(parts[0]);
    }
  });
  return data;
}

async function fetchQueue() {
  return (await axios.get(`${API}/api/queue`)).data;
}

async function fetchQueueDuration() {
  return (await axios.get(`${API}/api/queue/duration`)).data.total_duration;
}

function stripExtension(filename) {
  return filename.replace(/\.[^/.]+$/, '');
}

function renderCategories() {
  const container = document.getElementById('categories');
  container.innerHTML = '';
  categories.forEach(cat => {
    const btn = document.createElement('button');
    btn.textContent = cat;
    btn.className = 'button';
    if (cat === selectedCategory) {
      btn.classList.add('is-primary');
    } else if (cat === 'Todas') {
      btn.classList.add('is-white');
    } else {
      btn.classList.add('is-light');
    }
    btn.onclick = () => {
      selectedCategory = cat;
      currentPage = 1;
      renderSongs();
    };
    container.appendChild(btn);
  });
}

function updatePagination(filtered) {
  const totalPages = Math.max(1, Math.ceil(filtered.length / songsPerPage));
  document.getElementById('prev-page').disabled = currentPage <= 1;
  document.getElementById('next-page').disabled = currentPage >= totalPages;
  document.getElementById('page-info').textContent = `Página ${currentPage} de ${totalPages}`;
}

function renderSongs() {
  renderCategories();

  const term = document.getElementById('search').value.toLowerCase();
  let filtered = allSongs.filter(s => s.toLowerCase().includes(term));
  if (selectedCategory !== 'Todas') {
    filtered = filtered.filter(s => s.startsWith(selectedCategory + '/'));
  }

  const start = (currentPage - 1) * songsPerPage;
  const pageSongs = filtered.slice(start, start + songsPerPage);

  const tbody = document.querySelector('#song-list table tbody');
  tbody.innerHTML = '';
  pageSongs.forEach(song => {
    const name = stripExtension(song.split('/').pop());
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${name}</td>
      <td><button class="button is-small is-primary">Añadir</button></td>
    `;
    tr.querySelector('button').onclick = async () => {
      await axios.post(`${API}/api/queue`, { song });
      renderQueue();
    };
    tbody.appendChild(tr);
  });

  updatePagination(filtered);
}

async function renderQueue() {
  // 1) obtenemos la lista
  const q = await fetchQueue();
  const tbody = document.querySelector('#queue table tbody');
  tbody.innerHTML = '';
  q.forEach(song => {
    const name = stripExtension(song.split('/').pop());
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${name}</td>`;
    tbody.appendChild(tr);
  });

  // 2) obtenemos la duración total aproximada
  const total = await fetchQueueDuration();

  // 3) mostramos conteo y tiempo
  const count = q.length;
  let text = `${count} canción${count !== 1 ? 'es' : ''} en la cola`;

  if (total < 3600) {
    const mins = Math.round(total / 60);
    text += ` | Duración aprox.: ${mins} minuto${mins !== 1 ? 's' : ''}`;
  } else {
    const hrs = Math.floor(total / 3600);
    const mins = Math.round((total % 3600) / 60);
    text += ` | Duración aprox.: ${hrs} hora${hrs !== 1 ? 's' : ''}` +
            (mins > 0 ? ` y ${mins} minuto${mins !== 1 ? 's' : ''}` : '');
  }

  document.getElementById('queue-info').textContent = text;
}

// Event listeners
document.getElementById('search').addEventListener('input', () => {
  currentPage = 1;
  renderSongs();
});
document.getElementById('prev-page').addEventListener('click', () => {
  currentPage--;
  renderSongs();
});
document.getElementById('next-page').addEventListener('click', () => {
  currentPage++;
  renderSongs();
});

// Lógica de subida
document.getElementById('upload-btn').onclick = async () => {
  const input = document.getElementById('upload-input');
  if (!input.files.length) {
    return alert('Selecciona un archivo .mp3 o .wav');
  }
  const file = input.files[0];
  const form = new FormData();
  form.append('song', file);

  try {
    await axios.post(`${API}/api/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    allSongs = await fetchSongs();
    selectedCategory = 'reggaeton';
    currentPage = 1;
    renderSongs();
    input.value = '';
    alert('¡Canción subida y guardada en Reggaeton!');
  } catch (err) {
    console.error(err);
    alert(err.response?.data?.error || 'Error al subir la canción');
  }
};

// Inicialización
(async () => {
  allSongs = await fetchSongs();
  renderSongs();
  renderQueue();
  setInterval(renderQueue, 5000);
})();
