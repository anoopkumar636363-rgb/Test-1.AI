const API = '/api';
const HISTORY_KEY = 'bis_ai_chat_history_v1';
const $ = (id) => document.getElementById(id);

let chats = loadChats();
let activeChatId = null;
let isSending = false;
let requestController = null;
let activeTyping = null;
let activeAnimationCancel = null;
let requestSequence = 0;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>\"]/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '\"': '&quot;'
  })[char]);
}

function createChat() {
  return {
    id: `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: 'New BIS chat',
    updatedAt: Date.now(),
    messages: []
  };
}

function loadChats() {
  try {
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function saveChats() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(chats));
}

function getActiveChat() {
  return chats.find((chat) => chat.id === activeChatId);
}

function ensureActiveChat() {
  let chat = getActiveChat();
  if (!chat) {
    chat = createChat();
    chats.unshift(chat);
    activeChatId = chat.id;
    saveChats();
  }
  return chat;
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(timestamp);
}

function renderHistory() {
  const list = $('historyList');
  if (!chats.length) {
    list.innerHTML = '<div class="empty-history">No saved chats yet.<br>Start a conversation to create one.</div>';
    return;
  }

  const sorted = [...chats].sort((a, b) => b.updatedAt - a.updatedAt);
  list.innerHTML = sorted.map((chat) => `
    <div class="history-item ${chat.id === activeChatId ? 'selected' : ''}" data-id="${escapeHtml(chat.id)}">
      <button class="history-open" type="button">
        <span class="history-bubble">◌</span>
        <span class="history-copy">
          <b>${escapeHtml(chat.title)}</b>
          <small>${formatTime(chat.updatedAt)}</small>
        </span>
      </button>
      <button class="delete-chat" type="button" title="Delete chat" aria-label="Delete chat">×</button>
    </div>
  `).join('');

  list.querySelectorAll('.history-item').forEach((item) => {
    const id = item.dataset.id;
    item.querySelector('.history-open').addEventListener('click', () => loadChat(id));
    item.querySelector('.delete-chat').addEventListener('click', (event) => {
      event.stopPropagation();
      deleteChat(id);
    });
  });
}

function stopAI() {
  if (!isSending && !requestController && !activeTyping && !activeAnimationCancel) return;

  requestSequence += 1;
  if (requestController) requestController.abort();
  requestController = null;

  if (activeTyping) {
    activeTyping.remove();
    activeTyping = null;
  }

  if (activeAnimationCancel) {
    activeAnimationCancel();
    activeAnimationCancel = null;
  }

  isSending = false;
  const button = $('askBtn');
  button.disabled = false;
  button.classList.remove('stop-btn');
  button.textContent = '➤';
  button.setAttribute('aria-label', 'Send question');
  button.title = 'Send question';
}

function setSendingState(sending) {
  isSending = sending;
  const button = $('askBtn');
  button.disabled = false;
  button.classList.toggle('stop-btn', sending);
  button.textContent = sending ? '■' : '➤';
  button.setAttribute('aria-label', sending ? 'Stop response' : 'Send question');
  button.title = sending ? 'Stop response' : 'Send question';
}

function newChat() {
  stopAI();
  const chat = createChat();
  chats.unshift(chat);
  activeChatId = chat.id;
  saveChats();
  renderHistory();
  renderActiveChat();
  $('question').focus();
}

function deleteChat(id) {
  if (activeChatId === id) stopAI();
  chats = chats.filter((chat) => chat.id !== id);
  if (activeChatId === id) {
    activeChatId = chats[0]?.id || null;
  }
  saveChats();
  if (!activeChatId) newChat();
  else {
    renderHistory();
    renderActiveChat();
  }
}

function clearHistory() {
  if (!chats.length) return;
  if (!confirm('Delete all saved BIS chats from this browser?')) return;
  stopAI();
  chats = [];
  activeChatId = null;
  saveChats();
  newChat();
}

function loadChat(id) {
  if (!chats.some((chat) => chat.id === id)) return;
  stopAI();
  activeChatId = id;
  renderHistory();
  renderActiveChat();
}

function renderActiveChat() {
  const box = $('chat');
  const chat = ensureActiveChat();
  box.innerHTML = '';

  if (!chat.messages.length) {
    addWelcomeMessage(box);
    return;
  }

  chat.messages.forEach((message) => {
    if (message.role === 'user') renderUserMessage(box, message.text);
    else renderBotMessage(box, message.text, message.sources || [], false);
  });
  box.scrollTop = box.scrollHeight;
}

function addWelcomeMessage(box = $('chat')) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot welcome-message';
  wrapper.innerHTML = `
    <div class="bot-label"><span class="mini-bis">BIS</span><b>BIS AI</b></div>
    <p>Hello! 👋 I'm the BIS AI Assistant. I can help with Indian Standards, certification, testing, hallmarking, licence verification and BIS services.</p>
    <div class="welcome-prompts">
      <button type="button" onclick="useText('What is BIS?')">What is BIS?</button>
      <button type="button" onclick="useText('How do I get BIS certification?')">How to get BIS certification?</button>
      <button type="button" onclick="useText('Find an IS standard for a product')">Find IS standard for a product</button>
      <button type="button" onclick="useDemoLicense('CM/L-DEMO-001')">Verify a BIS licence</button>
    </div>
  `;
  box.appendChild(wrapper);
}

function renderUserMessage(box, text) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message user';
  wrapper.innerHTML = `<p>${escapeHtml(text)}</p>`;
  box.appendChild(wrapper);
}

function renderBotMessage(box, text, sources = [], animate = false, onAnimationDone = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot';
  wrapper.innerHTML = `
    <div class="bot-label"><span class="mini-bis">BIS</span><b>BIS AI</b></div>
    <p class="bot-text"></p>
  `;
  box.appendChild(wrapper);

  const textNode = wrapper.querySelector('.bot-text');
  if (!animate) {
    textNode.textContent = text;
  } else {
    activeAnimationCancel = animateText(textNode, text, onAnimationDone);
  }

  if (sources.length) {
    const sourceBox = document.createElement('div');
    sourceBox.className = 'sources';
    sourceBox.innerHTML = `<b>Official BIS sources</b>${sources.map((item) =>
      `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.source || item.title || 'BIS source')} ↗</a>`
    ).join('')}`;
    wrapper.appendChild(sourceBox);
  }
  box.scrollTop = box.scrollHeight;
  return wrapper;
}

function animateText(node, text, onDone = null) {
  node.textContent = '';
  let index = 0;
  let timer = null;
  let cancelled = false;

  const finish = () => {
    if (typeof onDone === 'function') onDone();
  };

  const step = () => {
    if (cancelled) return;
    node.textContent += text[index] || '';
    index += 1;
    if (index < text.length) {
      const delay = text[index - 1] === '\n' ? 35 : 11;
      timer = setTimeout(step, delay);
    } else {
      finish();
    }
  };

  step();

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}

function addThinkingMessage(box) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot thinking-message';
  wrapper.innerHTML = `
    <div class="bot-label"><span class="mini-bis">BIS</span><b>BIS AI</b></div>
    <div class="thinking-row"><span>Thinking</span><i></i><i></i><i></i></div>
  `;
  box.appendChild(wrapper);
  box.scrollTop = box.scrollHeight;
  return wrapper;
}

function addMessageToHistory(role, text, sources = []) {
  const chat = ensureActiveChat();
  chat.messages.push({ role, text, sources, createdAt: Date.now() });
  if (role === 'user' && chat.title === 'New BIS chat') {
    chat.title = text.length > 32 ? `${text.slice(0, 32)}…` : text;
  }
  chat.updatedAt = Date.now();
  saveChats();
  renderHistory();
}

function useText(text) {
  $('question').value = text;
  resizeTextarea();
  $('question').focus();
}

function usePrompt(button) {
  useText(button.textContent);
}

function focusAssistant() {
  document.querySelector('.assistant-column').scrollIntoView({ behavior: 'smooth', block: 'start' });
  setTimeout(() => $('question').focus(), 350);
}

function openTool(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function health() {
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    $('apiBadge').textContent = data.ai_configured ? '● AI connected' : '● API online';
    $('apiBadge').classList.toggle('offline', !data.ai_configured);
  } catch {
    $('apiBadge').textContent = '● Offline';
    $('apiBadge').classList.add('offline');
  }
}

async function askAI(question) {
  const box = $('chat');
  const button = $('askBtn');
  const typing = addThinkingMessage(box);
  const sequence = ++requestSequence;
  requestController = new AbortController();
  activeTyping = typing;
  setSendingState(true);

  try {
    const response = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal: requestController.signal
    });
    if (!response.ok) throw new Error('Request failed');
    const data = await response.json();

    if (sequence !== requestSequence) return;

    typing.remove();
    activeTyping = null;
    addMessageToHistory('bot', data.answer || 'No answer was returned.', data.sources || []);

    renderBotMessage(box, data.answer || 'No answer was returned.', data.sources || [], true, () => {
      if (sequence !== requestSequence) return;
      activeAnimationCancel = null;
      requestController = null;
      setSendingState(false);
    });
  } catch (error) {
    if (error?.name === 'AbortError' || sequence !== requestSequence) return;

    typing.remove();
    activeTyping = null;
    const message = 'The backend is not reachable. Please check the server and try again.';
    addMessageToHistory('bot', message, []);
    renderBotMessage(box, message, [], true, () => {
      if (sequence !== requestSequence) return;
      activeAnimationCancel = null;
      requestController = null;
      setSendingState(false);
    });
  } finally {
    if (sequence === requestSequence && !activeAnimationCancel) {
      requestController = null;
      setSendingState(false);
    }
  }
}

$('askForm').addEventListener('submit', async (event) => {
  event.preventDefault();

  if (isSending) {
    stopAI();
    return;
  }

  const question = $('question').value.trim();
  if (!question) return;

  const box = $('chat');
  if (!getActiveChat()?.messages.length) box.innerHTML = '';
  addMessageToHistory('user', question);
  renderUserMessage(box, question);
  $('question').value = '';
  resizeTextarea();
  await askAI(question);
});

async function searchStandards(queryOverride = null) {
  const query = queryOverride ?? $('standardSearch').value.trim();
  const box = $('standardResults');
  box.innerHTML = '<div class="tool-loading">Searching BIS records…</div>';

  try {
    const response = await fetch(`${API}/standards${query ? `?q=${encodeURIComponent(query)}` : ''}`);
    const data = await response.json();
    box.innerHTML = data.length
      ? data.slice(0, 6).map((item) => `
        <article class="standard-result">
          <span class="result-id">${escapeHtml(item.id || 'BIS')}</span>
          <b>${escapeHtml(item.title || 'Untitled')}</b>
          <small>${escapeHtml(item.product || item.category || '')}</small>
          <p>${escapeHtml(item.summary || '')}</p>
          ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">Official BIS record ↗</a>` : ''}
        </article>
      `).join('')
      : '<div class="tool-empty">No matching BIS records were found. Try “electrical cables”, “IS 302”, “plugs”, or “IS 694”.</div>';
  } catch {
    box.innerHTML = '<div class="tool-empty">Backend unavailable.</div>';
  }
}

$('standardForm').addEventListener('submit', (event) => {
  event.preventDefault();
  searchStandards();
});

async function showCertification() {
  const box = $('certificationResults');
  box.innerHTML = '<div class="tool-loading">Loading official BIS guidance…</div>';
  try {
    const response = await fetch(`${API}/certification`);
    const data = await response.json();
    box.innerHTML = data.map((item, index) => `
      <article class="cert-step">
        <span>0${index + 1}</span>
        <div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.summary)}</p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.source)} ↗</a></div>
      </article>
    `).join('');
  } catch {
    box.innerHTML = '<div class="tool-empty">Certification guidance is temporarily unavailable.</div>';
  }
}

$('certificationBtn').addEventListener('click', showCertification);

async function verifyLicense(numberOverride = null) {
  const number = (numberOverride ?? $('license').value).trim();
  if (!number) return;
  $('license').value = number;
  const box = $('verifyResult');
  box.innerHTML = '<div class="tool-loading">Checking demo registry…</div>';

  try {
    const response = await fetch(`${API}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ license_number: number })
    });
    const data = await response.json();

    if (data.found && data.demo) {
      const item = data.result;
      box.innerHTML = `
        <div class="verify-success"><strong>✓ Demo record found</strong><span>${escapeHtml(item.status)}</span></div>
        <dl>
          <dt>Licence</dt><dd>${escapeHtml(item.license_number)}</dd>
          <dt>Product</dt><dd>${escapeHtml(item.product)}</dd>
          <dt>Standard</dt><dd>${escapeHtml(item.standard)}</dd>
          <dt>Manufacturer</dt><dd>${escapeHtml(item.manufacturer)}</dd>
        </dl>
        <div class="demo-warning">⚠ Synthetic SIH demo record — not a real BIS licence.</div>
      `;
      return;
    }

    box.innerHTML = `
      <div class="verify-info"><strong>Live lookup not connected</strong><p>${escapeHtml(data.message)}</p>
      <a href="${escapeHtml(data.official_url || 'https://www.bis.gov.in/bis-apps/?lang=en')}" target="_blank" rel="noopener noreferrer">Open official BIS verification information ↗</a></div>
    `;
  } catch {
    box.innerHTML = '<div class="tool-empty">Backend unavailable.</div>';
  }
}

$('verifyForm').addEventListener('submit', (event) => {
  event.preventDefault();
  verifyLicense();
});

function useDemoLicense(number) {
  openTool('verify');
  $('license').value = number;
  verifyLicense(number);
}

function resizeTextarea() {
  const textarea = $('question');
  textarea.style.height = 'auto';
  textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
}

$('question').addEventListener('input', resizeTextarea);
$('question').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    $('askForm').requestSubmit();
  }
});

$('newChatBtn').addEventListener('click', newChat);
$('clearHistoryBtn').addEventListener('click', clearHistory);
$('closeHistory').addEventListener('click', () => document.body.classList.add('history-closed'));
$('openHistory').addEventListener('click', () => document.body.classList.remove('history-closed'));

window.addEventListener('hashchange', () => {
  document.querySelectorAll('.nav-link').forEach((link) => link.classList.toggle('active', link.getAttribute('href') === window.location.hash));
});

function init() {
  if (!activeChatId && chats.length) activeChatId = chats.sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
  if (!activeChatId) newChat();
  else {
    renderHistory();
    renderActiveChat();
  }
  health();
  searchStandards();
  resizeTextarea();
}

init();
