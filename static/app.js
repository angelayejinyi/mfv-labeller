// Minimal frontend app that interacts with the backend
// - POST /register to get participant and shuffled samples
// - POST /submit for each rating

let APP = {
  participant_id: null,
  samples: [],
  index: 0,
  responses: {}, // sample_id -> {rating, note}
};

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function registerAndLoad() {
  // collect optional attendee name (CSCI699 students)
  const nameInput = document.getElementById('attendee-name');
  const name = nameInput ? nameInput.value.trim() : '';
  const payload = name ? { name } : {};
  const res = await postJSON('/register', payload);
  APP.participant_id = res.participant_id;
  APP.samples = res.samples;
  APP.index = 0;
  document.getElementById('intro').style.display = 'none';
  document.getElementById('task').style.display = 'block';
  document.getElementById('info').textContent = `Participant: ${APP.participant_id} — Foundations: ${res.assigned_foundations.join(', ')}`;
  renderCurrent();
}

function renderCurrent() {
  const total = APP.samples.length;
  document.getElementById('progress').textContent = `Item ${APP.index + 1} / ${total}`;
  const s = APP.samples[APP.index];
  document.getElementById('scenario-title').textContent = s.title || '';
  document.getElementById('scenario-text').textContent = s.scenario || s.description || '';

  // rating buttons
  const rb = document.getElementById('rating-buttons');
  rb.innerHTML = '';
  for (let i = 0; i <= 4; i++) {
    const btn = document.createElement('button');
    btn.textContent = i;
    btn.onclick = () => {
      APP.responses[s.id] = { rating: i };
      // reflect selection visually by toggling 'selected' class
      Array.from(rb.children).forEach(c => c.classList.remove('selected'));
      btn.classList.add('selected');
    };
    rb.appendChild(btn);
    // mark previously selected
    if (APP.responses[s.id] && APP.responses[s.id].rating === i) {
      btn.classList.add('selected');
    }
  }
}

function saveCurrentToLocal() {
  const s = APP.samples[APP.index];
  if (!APP.responses[s.id]) APP.responses[s.id] = { rating: null };
}

async function submitAll() {
  // submit each response to backend
  const pid = APP.participant_id;
  for (const s of APP.samples) {
    const resp = APP.responses[s.id];
    if (resp && typeof resp.rating === 'number') {
      try {
        await postJSON('/submit', { participant_id: pid, sample_id: s.id, rating: resp.rating });
      } catch (err) {
        console.error('submit error', err);
      }
    }
  }
  document.getElementById('task').style.display = 'none';
  document.getElementById('done').style.display = 'block';
  document.getElementById('done-info').textContent = `Participant ${pid}: ${Object.keys(APP.responses).length} items submitted.`;
}

// Wire UI
window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('start').addEventListener('click', () => registerAndLoad());
  document.getElementById('next').addEventListener('click', () => {
    saveCurrentToLocal();
    if (APP.index < APP.samples.length - 1) {
      APP.index += 1;
      renderCurrent();
    }
  });
  document.getElementById('prev').addEventListener('click', () => {
    saveCurrentToLocal();
    if (APP.index > 0) {
      APP.index -= 1;
      renderCurrent();
    }
  });
  document.getElementById('submitAll').addEventListener('click', async () => {
    saveCurrentToLocal();
    if (!confirm('Submit all responses?')) return;
    await submitAll();
  });
});
