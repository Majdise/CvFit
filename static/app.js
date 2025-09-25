/* Utilities */
const $ = (sel) => document.querySelector(sel);
const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

const state = {
  lastJSON: null,
  lastBullets: [],              // rendered bullets (from API or fallback)
  apiBullets: [],               // experience_enhancement from API
};

/* Init */
window.addEventListener('DOMContentLoaded', () => {
  $("#year").textContent = new Date().getFullYear();

  $("#btnUseSample").addEventListener('click', useSampleJD);
  $("#btnClearJD").addEventListener('click', () => $("#job_description").value = "");
  $("#btnClearAll").addEventListener('click', clearAll);

  $("#analyzeForm").addEventListener('submit', onAnalyze);
  $("#btnCopySuggestions").addEventListener('click', onCopySuggestions);
  $("#btnDownloadJSON").addEventListener('click', onDownloadJSON);
  $("#btnGenBullets").addEventListener('click', onGenerateBullets);
  $("#btnCopyBullets").addEventListener('click', onCopyBullets);
  $("#btnToggleDebug").addEventListener('click', toggleDebug);
});

/* Sample JD text */
function useSampleJD() {
  $("#job_description").value =
`We’re hiring a Tier 2 Technical Support Engineer for our SaaS video platform.
Must have: 2–4 years SaaS support, strong SQL, REST APIs & JSON, log analysis, AWS (CloudWatch, S3, Athena), Grafana/OpenSearch.
Nice: Python/Bash scripting, Live events support, excellent English.`;
}

/* Clear */
function clearAll() {
  $("#cv_file").value = "";
  $("#job_description").value = "";
  $("#results").classList.add("hidden");
  $("#errorBox").classList.add("hidden");
  $("#rawJSON").textContent = "";
  $("#debug").classList.add("hidden");
  $("#xpBullets").innerHTML = "";
  $("#btnCopyBullets").disabled = true;

  state.lastJSON = null;
  state.lastBullets = [];
  state.apiBullets = [];
}

/* Analyze */
async function onAnalyze(e) {
  e.preventDefault();
  const fd = new FormData($("#analyzeForm"));
  const cv = fd.get("cv_file");
  const jd = (fd.get("job_description") || "").toString().trim();

  if (!cv || !cv.name) return showError("Please attach a CV file.");
  if (!jd) return showError("Please paste the job description.");

  setLoading(true);
  try {
    const res = await fetch("/analyze", { method: "POST", body: fd });
    const text = await res.text();
    if (!res.ok) {
      throw new Error(`API error (${res.status}): ${text}`);
    }
    const data = JSON.parse(text);
    state.lastJSON = data;
    renderResults(data);
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setLoading(false);
  }
}

/* Render */
function renderResults(data) {
  $("#results").classList.remove("hidden");
  $("#errorBox").classList.add("hidden");

  const score = Number(data.fit_score ?? 0);
  $("#fitScore").textContent = `${score}/100`;
  $("#fitScore").style.background = score >= 75 ? "#85f0c3" : score >= 55 ? "#ffd178" : "#ff9aa5";
  $("#fitReason").textContent = data.fit_reason || "";
  $("#salaryNote").textContent = data.expected_salary_note || "";

  // suggestions
  const ul = $("#suggestions");
  ul.innerHTML = "";
  (data.improvement_suggestions || []).forEach(s => {
    const li = el("li"); li.textContent = s; ul.appendChild(li);
  });

  // raw debug
  $("#rawJSON").textContent = JSON.stringify(data, null, 2);

  // EXPERIENCE ENHANCEMENT (from API if present)
  const apiEnh = Array.isArray(data.experience_enhancement) ? data.experience_enhancement : [];
  state.apiBullets = apiEnh.slice();
  renderXpBullets(apiEnh);

  // If API gave bullets, enable copy right away
  $("#btnCopyBullets").disabled = apiEnh.length === 0;
}

/* Render XP bullets helper */
function renderXpBullets(bullets) {
  const ul = $("#xpBullets");
  ul.innerHTML = "";
  state.lastBullets = bullets.slice();
  bullets.forEach(b => {
    const li = el("li"); li.innerHTML = sanitize(b); ul.appendChild(li);
  });
}

/* Generate bullets (fallback if API didn't return any) */
function onGenerateBullets() {
  if (!state.lastJSON) return showError("Run Analyze first.");

  // If API already gave experience_enhancement, just re-render it (or tweak if desired).
  if (state.apiBullets.length > 0) {
    renderXpBullets(state.apiBullets);
    $("#btnCopyBullets").disabled = state.apiBullets.length === 0;
    toast("Using AI-generated experience bullets from the API");
    return;
  }

  // Otherwise fallback: synthesize from suggestions + JD keywords (your previous logic)
  const jd = $("#job_description").value.trim();
  const suggestions = state.lastJSON.improvement_suggestions || [];

  const keyTerms = Array.from(new Set(
    jd.toLowerCase()
      .replace(/[^\w\s/+.()-]/g, " ")
      .split(/\s+/)
      .filter(w => w.length > 3)
  ))
  .sort((a,b)=> b.length - a.length)
  .slice(0, 8);

  const bullets = suggestions.map((sug) => {
    let line = sug.replace(new RegExp(`\\b(${keyTerms.join("|")})\\b`, "gi"), '<strong>$1</strong>');
    if (!/[.?!)]$/.test(line)) {
      line += " to improve reliability and customer outcomes.";
    }
    if (!/^(Built|Led|Implemented|Automated|Optimized|Designed|Owned|Introduced|Developed|Resolved|Reduced|Improved|Created|Maintained|Collaborated)/i.test(line)) {
      line = `Implemented ${line.charAt(0).toLowerCase() + line.slice(1)}`;
    }
    return `• ${line}`;
  });

  renderXpBullets(bullets);
  $("#btnCopyBullets").disabled = bullets.length === 0;
  toast("Generated experience bullets (fallback)");
}

/* Copy helpers */
function onCopySuggestions(){
  if (!state.lastJSON) return showError("Run Analyze first.");
  const text = (state.lastJSON.improvement_suggestions || []).map(s=>`• ${s}`).join("\n");
  navigator.clipboard.writeText(text).then(()=> toast("Suggestions copied"));
}
function onCopyBullets(){
  if (!state.lastBullets.length) return showError("No bullets to copy.");
  // Strip any markup when copying
  const plain = state.lastBullets
    .map(b => b.replace(/<[^>]+>/g, "")) // remove tags like <strong>
    .join("\n");
  navigator.clipboard.writeText(plain).then(()=> toast("Experience bullets copied"));
}
function onDownloadJSON(){
  if (!state.lastJSON) return showError("Nothing to download yet.");
  const blob = new Blob([JSON.stringify(state.lastJSON, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "cv_analyzer_result.json";
  a.click();
  URL.revokeObjectURL(a.href);
}

/* UI helpers */
function showError(msg){
  const box = $("#errorBox");
  box.textContent = msg;
  box.classList.remove("hidden");
  window.scrollTo({top:0, behavior:"smooth"});
}
function setLoading(is){
  $("#spinner").classList.toggle("hidden", !is);
  $("#btnAnalyze").disabled = is;
}
function toggleDebug(){
  $("#debug").classList.toggle("hidden");
}
function toast(msg){
  const t = el("div","toast"); t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=> t.classList.add("show"), 10);
  setTimeout(()=> { t.classList.remove("show"); setTimeout(()=>t.remove(), 250) }, 1600);
}

/* Basic sanitizer for innerHTML usage */
function sanitize(s){
  // very light safe transform: convert **bold** to <strong>, escape other tags
  const esc = s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  return esc.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

/* Tiny toast style */
const style = document.createElement("style");
style.textContent = `
.toast{
  position: fixed; left:50%; bottom:24px; transform: translateX(-50%) translateY(20px);
  background:#0d1329; color:#dfe7ff; border:1px solid #263255; padding:.45rem .7rem; border-radius:8px;
  opacity:0; transition: all .25s ease; z-index:9999;
}
.toast.show{ opacity:1; transform: translateX(-50%) translateY(0) }
`;
document.head.appendChild(style);