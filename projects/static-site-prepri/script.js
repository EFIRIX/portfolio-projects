// ===== СЛОВА (ЕГЭ) =====
// correct: "е" или "и"
const WORDS = [
  { base: "пр_дварительно", correct: "е" },
  { base: "пр_достеречь", correct: "е" },
  { base: "пр_дтеча", correct: "е" },
  { base: "пр_двосхитить", correct: "е" },
  { base: "пр_баутка", correct: "и" },
  { base: "пр_вередливый", correct: "и" },
  { base: "пр_верженец", correct: "и" },
  { base: "пр_годный", correct: "и" },
  { base: "пр_губить (вино)", correct: "и" },
  { base: "пр_есться", correct: "и" },
  { base: "непр_менимый", correct: "е" },
  { base: "пр_непрерывный", correct: "е" },
  { base: "пр_скорбный", correct: "и" },
  { base: "пр_вольный", correct: "и" },
  { base: "пр_людный", correct: "и" },
  { base: "пр_спешник", correct: "и" },
  { base: "пр_оритетный", correct: "и" },
  { base: "пр_станище", correct: "и" },
  { base: "непр_ступный", correct: "и" },
  { base: "пр_страститься", correct: "и" },
  { base: "впр_прыжку", correct: "и" },
  { base: "пр_чудливый", correct: "и" },
  { base: "пр_рост", correct: "и" },
  { base: "пр_говор", correct: "и" },
  { base: "пр_вратник", correct: "и" },
  { base: "пр_терпеться", correct: "и" },
  { base: "пр_давать (форму)", correct: "и" },

  { base: "пр_возносить", correct: "е" },
  { base: "пр_даваться", correct: "е" },
  { base: "пр_поднести", correct: "е" },
  { base: "пр_исполниться", correct: "е" },
  { base: "пр_обладать", correct: "е" },
  { base: "пр_клоняться (уважать)", correct: "е" },
  { base: "пр_валировать", correct: "е" },
  { base: "пр_дания (старины)", correct: "е" },
  { base: "непр_ложный (закон)", correct: "е" },
  { base: "пр_вратное (мнение)", correct: "е" },
  { base: "беспр_дельный", correct: "е" },
  { base: "пр_пираться", correct: "е" },
  { base: "пр_поны", correct: "е" },
  { base: "пр_кословить", correct: "е" },
  { base: "пр_клонный (возраст)", correct: "е" },
  { base: "пр_старелый", correct: "е" },
  { base: "пр_зрительно", correct: "е" },
  { base: "пр_много (благодарен)", correct: "е" },
  { base: "пр_сытится", correct: "е" },
  { base: "пр_смыкаться", correct: "е" },
  { base: "пр_льстить", correct: "е" },
  { base: "пр_славутый", correct: "е" },
  { base: "пр_амбула", correct: "е" },

  { base: "пр_поручить", correct: "е" },
  { base: "пр_исполнены", correct: "е" },
  { base: "пр_людия", correct: "е" },
  { base: "не пр_минул", correct: "е" },
  { base: "пр_зумпция", correct: "е" },
  { base: "пр_вентивный", correct: "е" },
  { base: "пр_градить", correct: "е" },
  { base: "пр_емственность", correct: "е" },
  { base: "пр_исполнены", correct: "е" },
  { base: "пр_небрежение", correct: "е" },
  { base: "пр_проводить", correct: "е" },
  { base: "пр_тендент", correct: "е" }
];

// ===== УТИЛИТЫ =====
function shuffle(arr) {
  return arr.sort(() => Math.random() - 0.5);
}

// ===== СОСТОЯНИЕ =====
let cards = shuffle([...WORDS]);
let i = 0;
let correct = 0;
let wrong = 0;
let errors = [];
let lastTyped = "?";
const startTime = Date.now();

// ===== DOM =====
const wordEl = document.getElementById("word");
const inputEl = document.getElementById("input");
const resultEl = document.getElementById("result");
const typedHintEl = document.getElementById("typedHint");
const progressEl = document.getElementById("progress");
const summaryEl = document.getElementById("summary");
const errorsBtn = document.getElementById("errorsMode");

function showTypedLetter(letter) {
  typedHintEl.textContent = `Вы ввели: ${letter ? letter.toUpperCase() : "—"}`;
}

// ===== ТЕМА =====
document.getElementById("themeToggle").onclick = () => {
  document.body.classList.toggle("dark");
  document.body.classList.toggle("light");
};

// ===== РЕНДЕР =====
function render() {
  if (i >= cards.length) return finish();
  const card = cards[i];
  wordEl.textContent = card.base;
  inputEl.value = "";
  inputEl.placeholder = lastTyped.toUpperCase();
  inputEl.focus();
  showTypedLetter("");
  progressEl.textContent = `${i + 1} / ${cards.length}`;
}

// ===== ПРОВЕРКА =====
inputEl.addEventListener("input", () => {
  const value = inputEl.value.toLowerCase();
  if (!["е", "и"].includes(value)) {
    inputEl.value = "";
    lastTyped = "?";
    inputEl.placeholder = lastTyped;
    showTypedLetter("");
    return;
  }

  lastTyped = value;
  inputEl.placeholder = lastTyped.toUpperCase();
  showTypedLetter(value);

  const card = cards[i];

  if (value === card.correct) {
    correct++;
    resultEl.textContent = `✅ Вы ввели: ${value.toUpperCase()}. Верно: ${card.base.replace("_", card.correct)}`;
    i++;
    render();
  } else {
    wrong++;
    errors.push(card);
    resultEl.textContent = `❌ Вы ввели: ${value.toUpperCase()}. Верно: ${card.base.replace("_", card.correct)}`;
    inputEl.value = "";
    inputEl.focus();
  }
});

// ===== ФИНИШ =====
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

// ===== РЕЖИМ ОШИБОК =====
errorsBtn.onclick = () => {
  cards = shuffle([...errors]);
  i = correct = wrong = 0;
  errors = [];
  summaryEl.classList.add("hidden");
  document.getElementById("card").classList.remove("hidden");
  errorsBtn.classList.add("hidden");
  render();
};

// ===== СТАРТ =====
render();
