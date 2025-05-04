const API = '';
const songsPerPage = 20;
let currentPage = 1;
let allSongs = [];
let selectedCategory = 'Todas';
let categories = ['Todas'];
let draggedSong = null;
let dropTarget = null;

async function fetchSongs() {
  const data = (await axios.get(`${API}/api/songs`)).data;
  categories = ['Todas'];
  data.forEach(p => {
    const c = p.split('/')[0];
    if (c && !categories.includes(c)) categories.push(c);
  });
  return data;
}

async function fetchQueue() {
  return (await axios.get(`${API}/api/queue`)).data;
}

function stripExt(n) {
  return n.replace(/\.[^/.]+$/, '');
}

function renderCategories() {
  const c = document.getElementById('categories');
  c.innerHTML = '';
  categories.forEach(cat => {
    const btn = document.createElement('button');
    btn.textContent = cat;
    btn.className = 'button';
    if (cat === selectedCategory) btn.classList.add('is-primary');
    else if (cat === 'Todas') btn.classList.add('is-white');
    else btn.classList.add('is-light');
    btn.onclick = () => {
      selectedCategory = cat;
      currentPage = 1;
      renderSongs();
    };
    c.appendChild(btn);
  });
}

function updatePagination(f) {
  const tp = Math.max(1, Math.ceil(f.length / songsPerPage));
  document.getElementById('prev-page').disabled = currentPage <= 1;
  document.getElementById('next-page').disabled = currentPage >= tp;
  document.getElementById('page-info').textContent = `Página ${currentPage} de ${tp}`;
}

async function renderSongs() {
  renderCategories();
  const term = document.getElementById('search').value.toLowerCase();
  let list = allSongs.filter(s => s.toLowerCase().includes(term));
  if (selectedCategory !== 'Todas') {
    list = list.filter(s => s.startsWith(selectedCategory + '/'));
  }
  const start = (currentPage - 1) * songsPerPage;
  const page = list.slice(start, start + songsPerPage);
  const tb = document.querySelector('#song-list tbody');
  tb.innerHTML = '';
  page.forEach(song => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${stripExt(song.split('/').pop())}</td>
      <td><button class="button is-small is-primary">Añadir</button></td>
    `;
    tr.querySelector('button').onclick = async () => {
      await axios.post(`${API}/api/queue`, { song });
      renderAll();
    };
    tb.appendChild(tr);
  });
  updatePagination(list);
}

function setupDragDrop() {
  const rows = Array.from(document.querySelectorAll('#queue tbody tr'));
  rows.forEach((tr, idx) => {
    const song = tr.dataset.song;
    tr.draggable = idx > 0;
    tr.classList.toggle('draggable', idx > 0);

    tr.addEventListener('touchstart', e => {
      if (e.target.closest('button')) return;
      draggedSong = song;
      tr.classList.add('over');
      e.preventDefault();
    });

    tr.addEventListener('touchmove', e => {
      if (!draggedSong) return;
      e.preventDefault();
      const touch = e.touches[0];
      const el = document.elementFromPoint(touch.clientX, touch.clientY);
      const row = el && el.closest('tr');
      if (row && row.dataset.song && row.dataset.song !== draggedSong) {
        document.querySelectorAll('#queue tbody tr.over').forEach(r => r.classList.remove('over'));
        row.classList.add('over');
        dropTarget = row.dataset.song;
      }
    });

    tr.addEventListener('touchend', async () => {
      document.querySelectorAll('#queue tbody tr.over').forEach(r => r.classList.remove('over'));
      if (draggedSong && dropTarget) {
        const q = await fetchQueue();
        const toIndex = q.indexOf(dropTarget) + 1;
        await axios.post(`${API}/api/queue/move`, { song: draggedSong, position: toIndex });
        renderAll();
      }
      draggedSong = null;
      dropTarget = null;
    });
  });
}

async function renderQueue() {
  const q = await fetchQueue();
  const tb = document.querySelector('#queue tbody');
  tb.innerHTML = '';
  q.forEach((song, idx) => {
    const tr = document.createElement('tr');
    tr.dataset.song = song;
    tr.innerHTML = `
      <td>${stripExt(song.split('/').pop())}</td>
      <td><button class="button is-small is-danger">Eliminar</button></td>
    `;
    const del = tr.querySelector('button');
    del.setAttribute('draggable', 'false');
    del.addEventListener('click', async e => {
      e.stopPropagation();
      await axios.delete(`${API}/api/queue`, { data: { song } });
      renderAll();
    });
    del.addEventListener('touchstart', e => e.stopPropagation());
    del.addEventListener('dragstart', e => e.stopPropagation());
    tb.appendChild(tr);
  });
  setupDragDrop();
}

function renderAll() {
  renderSongs();
  renderQueue();
}

document.getElementById('search').addEventListener('input', () => {
  currentPage = 1; renderSongs();
});
document.getElementById('prev-page').addEventListener('click', () => {
  currentPage--; renderSongs();
});
document.getElementById('next-page').addEventListener('click', () => {
  currentPage++; renderSongs();
});

(async () => {
  allSongs = await fetchSongs();
  renderAll();
  setInterval(renderAll, 5000);
})();
