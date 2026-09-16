const button = document.getElementById('testButton');
const message = document.getElementById('message');

button.addEventListener('click', () => {
  message.textContent = 'It works! ChatGPT changed your GitHub repo. 🚀';
  button.textContent = 'Test Passed ✓';
});
