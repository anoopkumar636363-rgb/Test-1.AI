const API = '/api';
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '\"': '&quot;'
  })[char]);
}

function addMessage(role, text) {
  const box = $('chat');
  const message = document.createElement('div');
  message.className = `message ${role}`;
  message.innerHTML = role === 'bot'
    ? `<b>BIS AI</b><p>${escapeHtml(text).replace(/\n/g, '<br>')}</p>`
    : `<p>${escapeHtml(text)}</p>`;
  box.appendChild(message);
  box.scrollTop = box.scrollHeight;
  return message;
}

function useText(text) {
  $('question').value = text;
  focusAssistant();
}

function usePrompt(button) {
  useText(button.textContent);
}

function focusAssistant() {
  document.querySelector('#assistant').scrollIntoView({ behavior: 'smooth' });
  setTimeout(() => $('question').focus(), 400);
}

async function health() {
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    $('apiBadge').textContent = data.ai_configured ? '● AI connected' : '● API online';
  } catch {
    $('apiBadge').textContent = '● Offline';
  }
}

$('askForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (!question) return;

  addMessage('user', question);
  $('question').value = '';
  const button = $('askBtn');
  button.disabled = true;
  button.textContent = 'Thinking…';
  const typing = addMessage('bot', 'Thinking…');

  try {
    const response = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    const data = await response.json();
    typing.remove();
    addMessage('bot', data.answer || 'No answer was returned.');
  } catch {
    typing.remove();
    addMessage('bot', 'The backend is not reachable. Start FastAPI with: uvicorn backend.main:app --reload');
  } finally {
    button.disabled = false;
    button.textContent = 'Ask AI';
  }
});

async function searchStandards() {
  const query = $('standardSearch').value.trim();
  const box = $('standardResults');
  box.innerHTML = '<p class="muted">Searching…</p>';

  try {
    const response = await fetch(`${API}/standards${query ? `?q=${encodeURIComponent(query)}` : ''}`);
    const data = await response.json();

    box.innerHTML = data.length
      ? data.map((item) => `
        <article class="result">
          <span class="id">${escapeHtml(item.id || 'STANDARD')}</span>
          <h3>${escapeHtml(item.title || 'Untitled')}</h3>
          <p>${escapeHtml(item.product || '')} · ${escapeHtml(item.category || '')}</p>
          <p>${escapeHtml(item.summary || '')}</p>
          <span class="source">${escapeHtml(item.source || 'Verified source to be added')}</span>
        </article>`).join('')
      : '<p class="muted">No BIS records are connected yet. Verified BIS information will be added here.</p>';
  } catch {
    box.innerHTML = '<p class="muted">Backend unavailable.</p>';
  }
}

$('standardSearch').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') searchStandards();
});

$('verifyForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const number = $('license').value.trim();
  const box = $('verifyResult');
  box.textContent = 'Checking…';

  try {
    const response = await fetch(`${API}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ license_number: number })
    });
    const data = await response.json();
    box.innerHTML = data.found
      ? `<b>Record found</b><br>${escapeHtml(data.result.product || '')} · ${escapeHtml(data.result.status || '')}`
      : `<b>Live verification is not connected yet.</b><br>${escapeHtml(data.message || '')}`;
  } catch {
    box.textContent = 'Backend unavailable.';
  }
});

health();
searchStandards();
