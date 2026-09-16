const modal = document.getElementById('modal');
const title = document.getElementById('modalTitle');
const text = document.getElementById('modalText');

function openModal(t, body) {
  title.textContent = t;
  text.textContent = body;
  modal.classList.remove('hidden');
}

document.getElementById('closeModal').onclick = () => modal.classList.add('hidden');
modal.onclick = (e) => { if (e.target === modal) modal.classList.add('hidden'); };

document.getElementById('assessmentBtn').onclick = () => openModal(
  'Skill Assessment',
  'Sample flow: answer 10 technical and soft-skill questions. The backend will calculate your verified skill profile and compare it with industry requirements.'
);

document.getElementById('portfolioBtn').onclick = () => openModal(
  'Digital Portfolio',
  'Sample portfolio: skills, projects, certificates, internships and achievements in one verified student profile.'
);

document.getElementById('roadmapBtn').onclick = () => openModal(
  'Your Learning Roadmap',
  'Based on this sample profile: learn React fundamentals → build one project → complete a REST API project → take the React skill verification test.'
);

document.querySelectorAll('.apply').forEach(button => {
  button.onclick = () => openModal(
    button.dataset.role,
    'Demo application flow opened. In the real version, this will create an application record and let the student track its status.'
  );
});

document.querySelectorAll('.nav-btn').forEach(button => {
  button.onclick = () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    const role = button.dataset.view;
    if (role === 'student') openModal('Student Portal', 'Student dashboard: skill assessment, skill gaps, portfolio, internships and placement applications.');
    if (role === 'industry') openModal('Industry Portal', 'Industry dashboard: create an opportunity, define required skills, and shortlist students by explainable skill match.');
    if (role === 'institution') openModal('Institution Portal', 'Institution dashboard: monitor student skill readiness, internship participation, placement progress and industry skill demand.');
  };
});
