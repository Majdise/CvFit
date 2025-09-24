const form = document.getElementById('analyzeForm');
const spinner = document.getElementById('spinner');
const results = document.getElementById('results');
const suggestionsEl = document.getElementById('suggestions');
const fitBar = document.getElementById('fitBar');
const fitScoreLabel = document.getElementById('fitScoreLabel');
const fitReason = document.getElementById('fitReason');
const salaryNote = document.getElementById('salaryNote');
const rawJson = document.getElementById('rawJson');
const copyJsonBtn = document.getElementById('copyJsonBtn');
const submitBtn = document.getElementById('submitBtn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Basic client-side checks
  const cvInput = document.getElementById('cv');
  const jdInput = document.getElementById('jd');
  if (!cvInput.files.length || !jdInput.value.trim()) return;

  // UI state
  spinner.classList.remove('hidden');
  submitBtn.disabled = true;
  results.classList.add('hidden');

  try {
    const data = new FormData();
    data.append('cv_file', cvInput.files[0]);
    data.append('job_description', jdInput.value);

    const res = await fetch('/analyze', { method: 'POST', body: data });
    const json = await res.json();

    if (!res.ok) {
      throw new Error(json?.detail || `HTTP ${res.status}`);
    }

    // Render
    fitScoreLabel.textContent = `${json.fit_score}/100`;
    fitBar.style.width = `${Math.max(0, Math.min(100, json.fit_score))}%`;
    fitBar.className =
      `h-3 rounded-full ${json.fit_score >= 70 ? 'bg-green-500'
                         : json.fit_score >= 40 ? 'bg-yellow-500'
                         : 'bg-red-500'}`;
    fitReason.textContent = json.fit_reason || '';
    salaryNote.textContent = json.expected_salary_note || '';

    suggestionsEl.innerHTML = '';
    (json.improvement_suggestions || []).forEach(s => {
      const li = document.createElement('li');
      li.textContent = s;
      suggestionsEl.appendChild(li);
    });

    rawJson.textContent = JSON.stringify(json, null, 2);
    results.classList.remove('hidden');
  } catch (err) {
    alert(`Analyze failed: ${err.message}`);
  } finally {
    spinner.classList.add('hidden');
    submitBtn.disabled = false;
  }
});

copyJsonBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(rawJson.textContent || '');
    copyJsonBtn.textContent = 'Copied!';
    setTimeout(() => (copyJsonBtn.textContent = 'Copy raw JSON'), 1200);
  } catch {}
});