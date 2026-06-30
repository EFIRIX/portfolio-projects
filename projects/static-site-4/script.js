const ALL_WORDS = [
  "довезЁнный","зАгнутый","зАнятый","зАпертый","заселЁнный",
  "кровоточАщий","нажИвший","налИвший","нанЯвшийся","начАвший",
  "нАчатый","низведЁнный","облегчЁнный","ободрЁнный","обострЁнный",
  "отключЁнный","повторЁнный","поделЁнный","понЯвший","прИнятый",
  "приручЁнный","прожИвший","снятА","сОгнутый","углублЁнный",

  "бралА","бралАсь","взялА","взялАсь","влилАсь","ворвалАсь",
  "воспринЯть","воспринялА","воссоздалА","вручИт","гналА",
  "гналАсь","добралА","добралАсь","дождалАсь","дозвонИтся",
  "дозИровать","ждалА","закУпорить","занЯть","зАнял","занялА",
  "зАняли","заперлА","запломбировАть","защемИт","звалА","звонИт",
  "кАшлянуть","клАла","клЕить","крАлась","кровоточИть","лгалА",
  "лилА","лилАсь","наделИт","надорвалАсь","назвалАсь","накренИтся",
  "налилА","нарвалА","начАть","нАчал","началА","нАчали",
  "обзвонИт","облегчИт","облегчИть","облилАсь","обнялАсь","обогналА",
  "ободралА","ободрИт","ободрИть","ободрИтся","ободрИться","обострИть","одолжИт","одолжИть",
  "озлОбить","оклЕить","окружИт","опОшлить","освЕдомиться","освЕдомится",
  "отбылА","отдалА","откУпорить","отозвалА","отозвалАсь",
  "перезвонИт","перелилА","плодоносИть","пломбировАть",
  "повторИт","позвалА","позвонИт","полилА","положИть",
  "положИл","понЯть","понялА","послАла","прибЫть","прИбыл",
  "прибылА","прИбыли","прИнял","принЯть","принялА","прИняли","занятА","заселенА","принятА","рвалА","сверлИт","снялА",
  "создалА","сорвалА","убралА","углубИть","укрепИт",
  "чЕрпать","щемИт","щЁлкать"
];

// ===== ЛОГИКА =====
const vowels = "аеёиоуыэюя";

function shuffle(arr) {
  return arr.sort(() => Math.random() - 0.5);
}

let cards = shuffle([...ALL_WORDS]);
let i = 0, correct = 0, wrong = 0;
let errors = [];
const startTime = Date.now();

const wordEl = document.getElementById("word");
const resultEl = document.getElementById("result");
const progressEl = document.getElementById("progress");
const summaryEl = document.getElementById("summary");
const errorsBtn = document.getElementById("errorsMode");

document.getElementById("themeToggle").onclick = () => {
  document.body.classList.toggle("dark");
  document.body.classList.toggle("light");
};

function render() {
  if (i >= cards.length) return finish();

  wordEl.innerHTML = "";
  resultEl.textContent = "";
  progressEl.textContent = `${i + 1} / ${cards.length}`;

  const correctWord = cards[i];
  const clean = correctWord.toLowerCase();
  const stressed = correctWord.match(/[А-ЯЁ]/)[0].toLowerCase();

  [...clean].forEach(char => {
    const span = document.createElement("span");
    span.textContent = char;
    span.classList.add("letter");

    if (vowels.includes(char)) {
      span.classList.add("vowel");
      span.onclick = () => check(char, stressed, correctWord);
    }

    wordEl.appendChild(span);
  });
}

function check(clicked, stressed, fullWord) {
  if (clicked === stressed) {
    correct++;
    i++;
    render();
  } else {
    wrong++;
    errors.push(fullWord);
    resultEl.textContent = `❌ Верно: ${fullWord}`;
  }
}

function finish() {
  document.getElementById("card").classList.add("hidden");

  const total = correct + wrong;
  const percent = total ? Math.round((correct / total) * 100) : 0;
  const t = Math.floor((Date.now() - startTime) / 1000);

  summaryEl.innerHTML = `
    <h2>Результат</h2>
    ✔ Правильных: ${correct}<br>
    ❌ Ошибок: ${wrong}<br>
    📊 Процент правильных: ${percent}%<br>
    ⏱ Время: ${Math.floor(t/3600)}ч ${Math.floor(t%3600/60)}м ${t%60}с
  `;
  summaryEl.classList.remove("hidden");

  if (errors.length) errorsBtn.classList.remove("hidden");
}

errorsBtn.onclick = () => {
  cards = shuffle([...errors]);
  i = correct = wrong = 0;
  errors = [];
  summaryEl.classList.add("hidden");
  document.getElementById("card").classList.remove("hidden");
  errorsBtn.classList.add("hidden");
  render();
};

render();