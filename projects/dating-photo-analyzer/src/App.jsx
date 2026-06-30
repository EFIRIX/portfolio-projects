import { useMemo, useRef, useState } from "react";
import {
  Aperture,
  Check,
  Crown,
  ImageUp,
  Info,
  Lightbulb,
  Smile,
  RefreshCcw,
  Shield,
  Sparkles,
  Target,
  ScanFace,
  Upload,
  X,
  Zap,
} from "lucide-react";

const metricLabels = {
  appearance: "Внешность",
  light: "Свет",
  sharpness: "Резкость",
  framing: "Кадр",
  background: "Фон",
  color: "Тон",
};

const weights = {
  appearance: 0.26,
  light: 0.2,
  sharpness: 0.18,
  framing: 0.18,
  background: 0.1,
  color: 0.08,
};

const defaultTips = [
  "Загрузите портретное фото, где лицо хорошо видно.",
  "Лучше всего работают дневной свет, чистый фон и естественный ракурс.",
  "Анализ выполняется в браузере, фото не отправляется на сервер.",
];

const looksmaxTiers = {
  male: [
    { min: 0, label: "Sub 3", tone: "low", note: "слабая dating-подача в этом фото" },
    { min: 34, label: "Sub 5", tone: "low", note: "ниже среднего, фото сильно мешает внешности" },
    { min: 50, label: "LTN", tone: "warn", note: "low tier normie: внешность читается, но кадр не усиливает" },
    { min: 68, label: "HTM", tone: "good", note: "high tier male: сильная база для профиля" },
    { min: 84, label: "Chad lite", tone: "great", note: "выраженно привлекательная подача" },
    { min: 94, label: "Chad", tone: "elite", note: "топовая подача для dating-фото" },
  ],
  female: [
    { min: 0, label: "Sub 3", tone: "low", note: "слабая dating-подача в этом фото" },
    { min: 34, label: "Sub 5", tone: "low", note: "ниже среднего, фото сильно мешает внешности" },
    { min: 50, label: "LTN", tone: "warn", note: "low tier normie: внешность читается, но кадр не усиливает" },
    { min: 68, label: "HTB", tone: "good", note: "high tier beauty: сильная база для профиля" },
    { min: 84, label: "Stacy lite", tone: "great", note: "выраженно привлекательная подача" },
    { min: 94, label: "Stacy", tone: "elite", note: "топовая подача для dating-фото" },
  ],
};

const tierExamples = {
  male: [
    {
      label: "Sub 3",
      look: "Лицо плохо читается: сильная тень, смаз, неудачный угол, закрытые черты.",
      signals: "часто выглядит уставше, неуверенно или случайно снято",
      upgrade: "дать свет на лицо, убрать смаз, поднять камеру до уровня глаз",
    },
    {
      label: "Sub 5",
      look: "Обычная внешность, но фото не помогает: жесткий свет, слабая поза, грязный фон.",
      signals: "черты видны, но нет выразительности и четкой подачи",
      upgrade: "нейтральный фон, прическа/стайлинг, спокойная уверенная мимика",
    },
    {
      label: "LTN",
      look: "Нормальная база: лицо читается, пропорции не провалены, но кадр средний.",
      signals: "есть потенциал, но фото не дает вау-эффекта",
      upgrade: "лучший свет, чуть более сильный ракурс, четкая линия лица",
    },
    {
      label: "HTM",
      look: "Выше среднего: аккуратные черты, уверенная поза, лицо хорошо отделено от фона.",
      signals: "в кадре есть структура: челюсть, глаза, волосы/стиль работают вместе",
      upgrade: "добавить более дорогой свет, чистый образ, выражение с характером",
    },
    {
      label: "Chad lite",
      look: "Сильная внешняя подача: четкие черты, хорошая челюсть/глаза, уверенный кадр.",
      signals: "фото уже выглядит как сильное первое фото в dating",
      upgrade: "убрать мелкие шумы: пересветы, лишний фон, случайную позу рук",
    },
    {
      label: "Chad",
      look: "Максимально сильная подача: лицо, свет, стиль, поза и композиция работают без слабых мест.",
      signals: "сразу читается модельная/топовая dating-фотография",
      upgrade: "держать уровень, делать серию с разными контекстами",
    },
  ],
  female: [
    {
      label: "Sub 3",
      look: "Лицо плохо видно: темнота, смаз, жесткий ракурс, закрытые черты.",
      signals: "фото не показывает внешность и снижает первое впечатление",
      upgrade: "мягкий свет, открытое лицо, камера на уровне глаз",
    },
    {
      label: "Sub 5",
      look: "Обычная внешность, но кадр не усиливает: фон, свет или выражение мешают.",
      signals: "черты читаются, но образ не выглядит собранным",
      upgrade: "ровный тон света, аккуратная укладка, спокойная поза",
    },
    {
      label: "LTN",
      look: "Нормальная база: лицо открыто, пропорции читаются, но фото выглядит средне.",
      signals: "есть приятность, но не хватает polish и выразительности",
      upgrade: "лучший свет, чище фон, более сильная мимика и кадрирование",
    },
    {
      label: "HTB",
      look: "Выше среднего: черты, стиль, волосы/макияж и свет создают цельный образ.",
      signals: "кадр уже хорошо работает для dating, внешность заметно усилена",
      upgrade: "сделать фото более премиальным: фон, одежда, цвет, поза",
    },
    {
      label: "Stacy lite",
      look: "Сильная привлекательная подача: лицо выразительное, свет мягкий, образ собран.",
      signals: "фото выглядит как сильное первое фото профиля",
      upgrade: "убрать мелкие отвлекающие детали и сделать серию в разных сценариях",
    },
    {
      label: "Stacy",
      look: "Топовая подача: лицо, свет, стиль, поза и композиция дают модельный эффект.",
      signals: "фото сразу выглядит premium и почти не имеет визуальных провалов",
      upgrade: "сохранять уровень, варьировать настроение и контекст",
    },
  ],
};

function clamp(value, min = 0, max = 100) {
  return Math.min(max, Math.max(min, value));
}

function scoreRange(value, ideal, tolerance, hardLimit) {
  const distance = Math.abs(value - ideal);
  if (distance <= tolerance) return 100;
  return clamp(100 - ((distance - tolerance) / hardLimit) * 100);
}

function strictRange(value, ideal, tolerance, hardLimit) {
  return Math.round(scoreRange(value, ideal, tolerance, hardLimit) * 0.86);
}

function capForWeakness(score, metrics, faceInfo) {
  let capped = score;
  const weakCount = Object.values(metrics).filter((value) => value < 50).length;
  const severeCount = Object.values(metrics).filter((value) => value < 38).length;

  capped -= weakCount * 4 + severeCount * 6;

  if (!faceInfo.detected) capped = Math.min(capped, 34);
  if (faceInfo.method === "fallback") capped = Math.min(capped, 82);
  if (faceInfo.method === "manual") capped = Math.min(capped, 86);
  if (metrics.light < 42) capped = Math.min(capped, 58);
  if (metrics.sharpness < 42) capped = Math.min(capped, 62);
  if (metrics.framing < 42) capped = Math.min(capped, 58);
  if (metrics.color < 38) capped = Math.min(capped, 66);
  if (metrics.background < 34) capped = Math.min(capped, 68);
  if (metrics.light < 55 && metrics.sharpness < 55) capped = Math.min(capped, 64);
  if (metrics.light > 86 && metrics.sharpness > 84 && metrics.framing > 84 && metrics.color > 78 && metrics.background > 72) {
    capped += 4;
  }

  return clamp(capped);
}

function createAdvice(metrics, faceInfo) {
  const advice = [];

  if (metrics.appearance < 62) {
    advice.push("Внешняя подача в кадре слабая: выберите фото с открытым лицом, мягким светом и более уверенным выражением.");
  } else {
    advice.push("Внешность в кадре считывается выигрышно: лицо заметно, подача выглядит открытой и аккуратной.");
  }

  if (metrics.light < 68) {
    advice.push("Переснимите при мягком дневном свете: лицо должно быть светлее фона, без жестких теней.");
  } else {
    advice.push("Свет выглядит достаточно читаемым для первого фото в профиле.");
  }

  if (metrics.sharpness < 62) {
    advice.push("Фото кажется мягким или смазанным. Возьмите исходник без сжатия и сфокусируйтесь по глазам.");
  } else {
    advice.push("Резкость подходит: детали лица не теряются при просмотре на телефоне.");
  }

  if (metrics.framing < 62) {
    advice.push(faceInfo.detected ? "Попробуйте кадр по грудь или пояс, оставив немного пространства над головой." : "Лицо не найдено автоматически. Выберите фото, где вы смотрите в камеру и лицо не закрыто.");
  } else {
    advice.push("Композиция выглядит сбалансированной: главный объект легко считывается.");
  }

  if (metrics.background < 58) {
    advice.push("Фон визуально перегружен. Упростите окружение или увеличьте дистанцию до фона для легкого размытия.");
  }

  if (metrics.color < 58) {
    advice.push("Цветовой тон выглядит неидеально. Избегайте зеленого/синего офисного света и слишком теплых фильтров.");
  }

  return advice.slice(0, 5);
}

function createAppearanceProfile(score, metrics, faceInfo) {
  const confidence = faceInfo.method === "native" ? "Высокая" : faceInfo.detected ? "Средняя" : "Низкая";
  const label =
    score >= 90
      ? "Очень привлекательная подача"
      : score >= 76
        ? "Привлекательная подача"
        : score >= 60
          ? "Средняя подача"
          : "Слабая подача";

  const strengths = [];
  const fixes = [];

  if (faceInfo.detected) strengths.push("лицо хорошо участвует в кадре");
  else fixes.push("выбрать фото, где лицо видно крупнее и без перекрытий");

  if (metrics.light >= 70) strengths.push("свет помогает внешности");
  else fixes.push("переснять при мягком дневном свете");

  if (metrics.sharpness >= 68) strengths.push("черты выглядят четко");
  else fixes.push("убрать смаз и сжатие, сфокусироваться по глазам");

  if (metrics.color >= 64) strengths.push("тон кожи и цвета выглядят естественно");
  else fixes.push("избегать цветных фильтров и офисного света");

  return {
    score,
    label,
    confidence,
    summary:
      "Это оценка внешности именно в этом фото: насколько снимок визуально усиливает лицо, стиль и открытость для dating.",
    strengths: strengths.slice(0, 3),
    fixes: fixes.slice(0, 3),
  };
}

function gradeFromScore(score) {
  if (score >= 90) return { label: "Сильное фото", tone: "great" };
  if (score >= 76) return { label: "Можно публиковать", tone: "good" };
  if (score >= 60) return { label: "Нужна доработка", tone: "warn" };
  return { label: "Лучше переснять", tone: "low" };
}

function createLooksmaxTier(score, scale) {
  const tiers = looksmaxTiers[scale];
  const tier = tiers.reduce((current, item) => (score >= item.min ? item : current), tiers[0]);
  return {
    ...tier,
    scaleLabel: scale === "male" ? "Мужская шкала" : "Женская шкала",
  };
}

function createGuideSummary(analysis) {
  const box = analysis?.faceInfo?.box;
  const size = analysis?.renderSize;
  if (!box || !size) {
    return [
      "Лицо не найдено: геометрические линии недоступны.",
      "Оценка использует только общие признаки фото: свет, резкость, фон и цвет.",
    ];
  }

  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  const faceArea = Math.round((box.width * box.height) / (size.width * size.height) * 100);
  const horizontalOffset = Math.round(Math.abs(centerX / size.width - 0.5) * 100);
  const verticalPosition = Math.round(centerY / size.height * 100);
  const offsetAngle = Math.round(Math.atan2(centerY - size.height / 2, centerX - size.width / 2) * 180 / Math.PI);

  return [
    `Размер лица в кадре: ${faceArea}% площади изображения.`,
    `Смещение от центральной оси: ${horizontalOffset}% ширины кадра.`,
    `Угол вектора от центра кадра к центру лица: ${offsetAngle}°.`,
    `Вертикальная позиция центра лица: ${verticalPosition}% высоты кадра.`,
    "Горизонтальные линии глаз/рта используются как визуальные ориентиры, а не как точная биометрия.",
  ];
}

function formatSigned(value, unit = "") {
  return `${value > 0 ? "+" : ""}${value}${unit}`;
}

function scoreImpact(score) {
  if (score >= 78) return "сильный плюс";
  if (score >= 62) return "плюс";
  if (score >= 48) return "нейтрально";
  return "минус";
}

function createGeometryModel(analysis) {
  const box = analysis?.faceInfo?.box;
  const size = analysis?.renderSize;
  if (!box || !size) return null;

  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  const faceRatio = box.width / Math.max(1, box.height);
  const faceAreaRatio = (box.width * box.height) / (size.width * size.height);
  const horizontalOffset = Math.abs(centerX / size.width - 0.5);
  const verticalPosition = centerY / size.height;
  const poseTilt = clamp((centerX / size.width - 0.5) * -18 + (faceRatio - 0.62) * 8, -9, 9);
  const eyeTiltDeg = Math.round(poseTilt * 10) / 10;
  const eyeHalfWidth = box.width * 0.29;
  const eyeBaseY = box.y + box.height * 0.38;
  const eyeDeltaY = Math.tan((eyeTiltDeg * Math.PI) / 180) * eyeHalfWidth;
  const leftEye = { x: centerX - eyeHalfWidth, y: eyeBaseY - eyeDeltaY };
  const rightEye = { x: centerX + eyeHalfWidth, y: eyeBaseY + eyeDeltaY };
  const mouthLeft = { x: centerX - box.width * 0.2, y: box.y + box.height * 0.68 };
  const mouthRight = { x: centerX + box.width * 0.2, y: box.y + box.height * 0.68 };
  const leftJaw = { x: box.x + box.width * 0.18, y: box.y + box.height * 0.77 };
  const rightJaw = { x: box.x + box.width * 0.82, y: box.y + box.height * 0.77 };
  const chin = { x: centerX, y: box.y + box.height * 0.95 };
  const jawAngle = Math.round(
    Math.atan2(chin.y - leftJaw.y, chin.x - leftJaw.x) * 180 / Math.PI,
  );
  const jawScore = Math.round(
    clamp((analysis.metrics.sharpness || 0) * 0.5 + scoreRange(faceRatio, 0.62, 0.18, 0.42) * 0.35 + (analysis.metrics.light || 0) * 0.15),
  );
  const eyeTiltScore = Math.round(scoreRange(Math.abs(eyeTiltDeg), 2, 3, 9));
  const thirdsScore = Math.round(scoreRange(verticalPosition, 0.43, 0.14, 0.3));
  const framingScore = Math.round(
    scoreRange(faceAreaRatio, 0.16, 0.09, 0.22) * 0.45 +
      scoreRange(horizontalOffset, 0, 0.08, 0.24) * 0.35 +
      thirdsScore * 0.2,
  );
  const symmetryScore = Math.round(
    scoreRange(horizontalOffset, 0, 0.06, 0.24) * 0.62 + eyeTiltScore * 0.38,
  );
  const facialThirds = [
    box.y + box.height * 0.33,
    box.y + box.height * 0.66,
  ];

  return {
    centerX,
    centerY,
    faceAreaPercent: Math.round(faceAreaRatio * 100),
    horizontalOffsetPercent: Math.round(horizontalOffset * 100),
    verticalPercent: Math.round(verticalPosition * 100),
    eyeTiltDeg,
    jawAngle,
    jawScore,
    eyeTiltScore,
    thirdsScore,
    framingScore,
    symmetryScore,
    points: {
      leftEye,
      rightEye,
      mouthLeft,
      mouthRight,
      leftJaw,
      rightJaw,
      chin,
      facialThirds,
    },
  };
}

function createDetailedExplanation(analysis, looksmaxTier) {
  const geometry = createGeometryModel(analysis);
  if (!analysis || !geometry) {
    return {
      factors: [
        {
      title: "Геометрия лица",
          value: "Недоступно",
          impact: "минус",
          text: "Tier снижается, потому что приложение не смогло надежно найти область лица. Включите ручную коррекцию и кликните по центру лица.",
        },
      ],
      tier: ["Без лица в кадре looksmaxing-tier считается по общему качеству фото, поэтому результат менее надежен."],
    };
  }

  const factors = [
    {
      title: "Линия челюсти",
      value: `${geometry.jawScore}/100`,
      impact: scoreImpact(geometry.jawScore),
      text: `Оценивается как прокси: четкость кадра + пропорция найденной области лица + свет. Условный угол нижней линии около ${geometry.jawAngle}°.`,
    },
    {
      title: "Наклон глаз",
      value: `${formatSigned(geometry.eyeTiltDeg, "°")}`,
      impact: scoreImpact(geometry.eyeTiltScore),
      text: "Это estimated eye tilt: линия строится по области лица и позе в кадре. Малый контролируемый наклон выглядит стабильнее, сильный наклон снижает уверенность.",
    },
    {
      title: "Центровка и симметрия",
      value: `${geometry.symmetryScore}/100`,
      impact: scoreImpact(geometry.symmetryScore),
      text: `Центр лица смещен от оси кадра на ${geometry.horizontalOffsetPercent}% ширины. Чем ближе к оси, тем выше восприятие симметрии на фото.`,
    },
    {
      title: "Пропорции в кадре",
      value: `${geometry.framingScore}/100`,
      impact: scoreImpact(geometry.framingScore),
      text: `Лицо занимает ${geometry.faceAreaPercent}% изображения, центр лица расположен на ${geometry.verticalPercent}% высоты. Это влияет на tier сильнее, чем фон.`,
    },
  ];

  const tier = [
    `${looksmaxTier.label} выбран потому, что score внешней подачи равен ${analysis.appearance.score}/100 и попал в диапазон текущей ${looksmaxTier.scaleLabel.toLowerCase()}.`,
    `Главные веса: внешность ${Math.round(weights.appearance * 100)}%, свет ${Math.round(weights.light * 100)}%, резкость ${Math.round(weights.sharpness * 100)}%, кадр ${Math.round(weights.framing * 100)}%.`,
    `По текущему фото: внешность ${analysis.metrics.appearance}, свет ${analysis.metrics.light}, резкость ${analysis.metrics.sharpness}, кадр ${analysis.metrics.framing}, фон ${analysis.metrics.background}, тон ${analysis.metrics.color}.`,
  ];

  return { factors, tier };
}

function createAppearanceBreakdown(analysis) {
  const geometry = createGeometryModel(analysis);
  if (!analysis) {
    return {
      summary: "Загрузите фото, чтобы получить подробную оценку внешней подачи.",
      aspects: [],
      blockers: [],
      upgrades: [],
    };
  }

  const metrics = analysis.metrics;
  const faceFound = Boolean(analysis.faceInfo?.detected);
  const structureScore = geometry
    ? Math.round(geometry.jawScore * 0.52 + geometry.symmetryScore * 0.28 + geometry.framingScore * 0.2)
    : Math.round(metrics.appearance * 0.55);
  const eyeScore = geometry
    ? Math.round(geometry.eyeTiltScore * 0.45 + metrics.sharpness * 0.35 + metrics.light * 0.2)
    : Math.round(metrics.sharpness * 0.55 + metrics.light * 0.45);
  const skinToneScore = Math.round(metrics.light * 0.48 + metrics.color * 0.38 + metrics.sharpness * 0.14);
  const styleScore = Math.round(metrics.background * 0.42 + metrics.color * 0.25 + metrics.framing * 0.2 + metrics.sharpness * 0.13);
  const expressionScore = Math.round(metrics.framing * 0.35 + metrics.light * 0.24 + metrics.appearance * 0.24 + metrics.sharpness * 0.17);
  const photogenicScore = Math.round(metrics.appearance * 0.38 + metrics.light * 0.2 + metrics.framing * 0.18 + metrics.sharpness * 0.14 + metrics.background * 0.1);

  const aspects = [
    {
      title: "Читаемость лица",
      score: faceFound ? Math.max(58, metrics.framing) : 35,
      verdict: faceFound ? "лицо участвует в оценке" : "лицо не найдено надежно",
      text: faceFound
        ? `Источник: ${analysis.faceInfo.method === "manual" ? "ручная разметка" : analysis.faceInfo.method === "fallback" ? "портретный fallback" : "браузерный детектор"}. Чем увереннее найдена область лица, тем надежнее score.`
        : "Внешность нельзя честно оценить детально, если лицо не выделено. Используйте ручную разметку.",
    },
    {
      title: "Структура лица",
      score: structureScore,
      verdict: scoreImpact(structureScore),
      text: geometry
        ? `Учитываются условная линия челюсти, пропорция найденной области лица и центровка. Jaw proxy: ${geometry.jawScore}/100, симметрия кадра: ${geometry.symmetryScore}/100.`
        : "Без области лица структура оценивается только косвенно через качество кадра.",
    },
    {
      title: "Глаза и взгляд",
      score: eyeScore,
      verdict: scoreImpact(eyeScore),
      text: geometry
        ? `Estimated eye tilt: ${formatSigned(geometry.eyeTiltDeg, "°")}. На восприятие также влияют резкость и свет в зоне лица.`
        : "Оценка строится по резкости и свету, потому что линия глаз недоступна.",
    },
    {
      title: "Кожа и тон",
      score: skinToneScore,
      verdict: scoreImpact(skinToneScore),
      text: "Смотрю на яркость, цветовой сдвиг и детализацию. Зеленый/желтый свет, шум и сильные тени снижают этот пункт.",
    },
    {
      title: "Волосы, стиль, силуэт",
      score: styleScore,
      verdict: scoreImpact(styleScore),
      text: "Это не распознавание брендов или прически, а визуальная цельность: чистый фон, цветовая гармония, отделение головы/силуэта от окружения.",
    },
    {
      title: "Выражение и уверенность",
      score: expressionScore,
      verdict: scoreImpact(expressionScore),
      text: "Прокси по кадрированию, свету, резкости и общей внешней подаче. Открытое лицо, спокойная мимика и прямой ракурс обычно поднимают оценку.",
    },
    {
      title: "Фотогеничность для dating",
      score: photogenicScore,
      verdict: scoreImpact(photogenicScore),
      text: "Итоговая прикладная оценка: насколько фото быстро считывается в анкете и усиливает первое впечатление.",
    },
  ];

  const blockers = aspects
    .filter((item) => item.score < 58)
    .map((item) => item.title)
    .slice(0, 3);
  const upgrades = [
    metrics.light < 68 ? "переснять при мягком фронтальном свете" : null,
    metrics.sharpness < 62 ? "взять более резкий исходник без шума и смаза" : null,
    metrics.framing < 62 ? "поставить лицо ближе к верхней трети и центру кадра" : null,
    metrics.background < 58 ? "упростить фон и убрать визуальный шум" : null,
    metrics.color < 58 ? "убрать зеленый/желтый цветовой сдвиг" : null,
  ].filter(Boolean);

  return {
    summary: `Подробная оценка внешности в этом фото: ${analysis.appearance.score}/100. Это score визуальной подачи, а не объективная оценка человека вне кадра.`,
    aspects,
    blockers,
    upgrades: upgrades.slice(0, 4),
  };
}

async function detectFace(imageEl) {
  if (!("FaceDetector" in window)) {
    return { detected: false, supported: false, method: "none", box: null };
  }

  try {
    const detector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 });
    const faces = await detector.detect(imageEl);
    if (!faces.length) return { detected: false, supported: true, method: "native", box: null };
    const largest = faces.sort((a, b) => {
      const areaA = a.boundingBox.width * a.boundingBox.height;
      const areaB = b.boundingBox.width * b.boundingBox.height;
      return areaB - areaA;
    })[0];
    return { detected: true, supported: true, method: "native", box: largest.boundingBox };
  } catch {
    return { detected: false, supported: false, method: "none", box: null };
  }
}

function isLikelySkin(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const chroma = max - min;
  const y = 0.299 * r + 0.587 * g + 0.114 * b;
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;

  return (
    y > 55 &&
    y < 248 &&
    chroma > 10 &&
    cb > 76 &&
    cb < 145 &&
    cr > 128 &&
    cr < 188 &&
    cr - cb > 10 &&
    r > b * 0.9 &&
    r > g * 0.86
  );
}

function luminance(r, g, b) {
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

function isLowLightSkin(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const y = luminance(r, g, b);
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;

  return (
    y > 35 &&
    y < 210 &&
    max - min > 5 &&
    cb > 92 &&
    cb < 148 &&
    cr > 124 &&
    cr < 178 &&
    r > b * 0.75 &&
    r > g * 0.68
  );
}

function isDarkFeature(r, g, b) {
  return luminance(r, g, b) < 82 && Math.max(r, g, b) - Math.min(r, g, b) > 8;
}

function ramp(value, min, max) {
  return clamp((value - min) / (max - min), 0, 1);
}

function estimateFaceFromSkin(data, width, height) {
  const cell = Math.max(8, Math.round(Math.max(width, height) / 90));
  const cols = Math.ceil(width / cell);
  const rows = Math.ceil(height / cell);
  const mask = new Uint8Array(cols * rows);
  const counts = new Uint16Array(cols * rows);
  const maxY = Math.round(height * 0.78);

  for (let y = 0; y < maxY; y += 2) {
    for (let x = 0; x < width; x += 2) {
      const i = (y * width + x) * 4;
      if (isLikelySkin(data[i], data[i + 1], data[i + 2])) {
        counts[Math.floor(y / cell) * cols + Math.floor(x / cell)] += 1;
      }
    }
  }

  const cellSamples = Math.max(1, Math.round((cell * cell) / 4));
  for (let i = 0; i < counts.length; i += 1) {
    mask[i] = counts[i] > cellSamples * 0.08 ? 1 : 0;
  }

  const visited = new Uint8Array(mask.length);
  const queue = [];
  let best = null;

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const start = row * cols + col;
      if (!mask[start] || visited[start]) continue;

      let minCol = col;
      let maxCol = col;
      let minRow = row;
      let maxRow = row;
      let cells = 0;
      let skinPixels = 0;
      visited[start] = 1;
      queue.length = 0;
      queue.push(start);

      for (let q = 0; q < queue.length; q += 1) {
        const current = queue[q];
        const currentRow = Math.floor(current / cols);
        const currentCol = current % cols;
        cells += 1;
        skinPixels += counts[current];
        minCol = Math.min(minCol, currentCol);
        maxCol = Math.max(maxCol, currentCol);
        minRow = Math.min(minRow, currentRow);
        maxRow = Math.max(maxRow, currentRow);

        const neighbors = [
          current - cols,
          current + cols,
          currentCol > 0 ? current - 1 : -1,
          currentCol < cols - 1 ? current + 1 : -1,
        ];

        for (const next of neighbors) {
          if (next >= 0 && next < mask.length && mask[next] && !visited[next]) {
            visited[next] = 1;
            queue.push(next);
          }
        }
      }

      const boxWidth = (maxCol - minCol + 1) * cell;
      const boxHeight = (maxRow - minRow + 1) * cell;
      const areaRatio = (boxWidth * boxHeight) / (width * height);
      const centerX = ((minCol + maxCol + 1) * cell) / 2 / width;
      const centerY = ((minRow + maxRow + 1) * cell) / 2 / height;
      const aspect = boxWidth / Math.max(1, boxHeight);

      if (
        cells < 8 ||
        areaRatio < 0.012 ||
        areaRatio > 0.3 ||
        centerY < 0.12 ||
        centerY > 0.68 ||
        centerX < 0.16 ||
        centerX > 0.84 ||
        aspect < 0.38 ||
        aspect > 1.75
      ) {
        continue;
      }

      const centerScore = 1 - Math.min(1, Math.abs(centerX - 0.5) / 0.42);
      const verticalScore = 1 - Math.min(1, Math.abs(centerY - 0.38) / 0.34);
      const sizeScore = 1 - Math.min(1, Math.abs(areaRatio - 0.075) / 0.16);
      const score = skinPixels * (0.45 + centerScore * 0.25 + verticalScore * 0.2 + sizeScore * 0.1);

      if (!best || score > best.score) {
        best = { minCol, maxCol, minRow, maxRow, score };
      }
    }
  }

  if (!best) return null;

  const rawX = best.minCol * cell;
  const rawY = best.minRow * cell;
  const rawWidth = (best.maxCol - best.minCol + 1) * cell;
  const rawHeight = (best.maxRow - best.minRow + 1) * cell;
  const rawAreaRatio = (rawWidth * rawHeight) / (width * height);
  const x = rawAreaRatio > 0.16 ? clamp(rawX + rawWidth * 0.02, 0, width - 1) : clamp(rawX - rawWidth * 0.34, 0, width - 1);
  const y = rawAreaRatio > 0.16 ? clamp(rawY, 0, height - 1) : clamp(rawY - rawHeight * 0.34, 0, height - 1);
  const right =
    rawAreaRatio > 0.16
      ? clamp(rawX + rawWidth * 0.98, x + 1, width)
      : clamp(rawX + rawWidth * 1.34, x + 1, width);
  const bottom =
    rawAreaRatio > 0.16
      ? clamp(rawY + rawHeight * 0.82, y + 1, height)
      : clamp(rawY + rawHeight * 1.42, y + 1, height);

  return {
    x,
    y,
    width: right - x,
    height: bottom - y,
  };
}

function estimateFaceFromPortraitWindow(data, width, height) {
  let best = null;
  const candidateHeights = [0.22, 0.26, 0.3, 0.34].map((ratio) => Math.round(height * ratio));

  for (const boxHeight of candidateHeights) {
    const boxWidth = Math.round(boxHeight * 0.72);
    const step = Math.max(12, Math.round(boxWidth / 8));
    const startY = Math.round(height * 0.06);
    const endY = Math.round(height * 0.45);
    const startX = Math.round(width * 0.18);
    const endX = Math.round(width * 0.82 - boxWidth);

    for (let y = startY; y <= endY; y += step) {
      for (let x = startX; x <= endX; x += step) {
        let skinCount = 0;
        let upperDarkCount = 0;
        let upperCount = 0;
        let count = 0;
        let lumSum = 0;
        let lumSq = 0;
        let edgeSum = 0;

        for (let py = y; py < Math.min(height, y + boxHeight); py += 6) {
          for (let px = x; px < Math.min(width, x + boxWidth); px += 6) {
            const i = (py * width + px) * 4;
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const yValue = luminance(r, g, b);
            count += 1;
            lumSum += yValue;
            lumSq += yValue * yValue;

            if (isLowLightSkin(r, g, b)) skinCount += 1;
            if (py < y + boxHeight * 0.38) {
              upperCount += 1;
              if (isDarkFeature(r, g, b)) upperDarkCount += 1;
            }
            if (px + 6 < width) {
              const next = (py * width + px + 6) * 4;
              edgeSum += Math.abs(yValue - luminance(data[next], data[next + 1], data[next + 2]));
            }
          }
        }

        if (!count) continue;

        const skinDensity = skinCount / count;
        const upperDarkDensity = upperDarkCount / Math.max(1, upperCount);
        const meanLum = lumSum / count;
        const contrast = Math.sqrt(Math.max(0, lumSq / count - meanLum * meanLum));
        const edgeDensity = edgeSum / count;
        const centerX = (x + boxWidth / 2) / width;
        const centerY = (y + boxHeight / 2) / height;
        const positionScore =
          Math.max(0, 1 - Math.abs(centerX - 0.5) / 0.24) * 0.65 +
          Math.max(0, 1 - Math.abs(centerY - 0.3) / 0.22) * 0.35;
        const skinScore = Math.min(1, ramp(skinDensity, 0.12, 0.45)) * (skinDensity < 0.82 ? 1 : 0.65);
        const upperScore =
          Math.min(1, ramp(upperDarkDensity, 0.06, 0.22)) * (upperDarkDensity < 0.58 ? 1 : 0.72);
        const contrastScore = Math.min(1, contrast / 45);
        const edgeScore = Math.min(1, edgeDensity / 18);
        let score =
          skinScore * 0.28 +
          upperScore * 0.2 +
          contrastScore * 0.18 +
          edgeScore * 0.12 +
          positionScore * 0.22;

        if (skinDensity < 0.1 || upperDarkDensity < 0.04 || meanLum < 32 || meanLum > 190) {
          score *= 0.45;
        }

        if (!best || score > best.score) {
          best = { x, y, width: boxWidth, height: boxHeight, score };
        }
      }
    }
  }

  if (!best || best.score < 0.56) return null;

  return {
    x: clamp(best.x, 0, width - 1),
    y: clamp(best.y, 0, height - 1),
    width: clamp(best.width, 1, width - best.x),
    height: clamp(best.height, 1, height - best.y),
  };
}

function analyzePixels(canvas, context, faceInfo) {
  const { width, height } = canvas;
  const imageData = context.getImageData(0, 0, width, height);
  const { data } = imageData;
  const total = width * height;
  let luminanceSum = 0;
  let luminanceSq = 0;
  let saturationSum = 0;
  let warmCool = 0;
  let edgeSum = 0;

  const sampleStep = 4;
  const gray = new Float32Array(total);

  for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    gray[p] = lum;
    luminanceSum += lum;
    luminanceSq += lum * lum;
    saturationSum += max === 0 ? 0 : (max - min) / max;
    warmCool += (r - b) / 255;
  }

  for (let y = 1; y < height - 1; y += sampleStep) {
    for (let x = 1; x < width - 1; x += sampleStep) {
      const idx = y * width + x;
      const laplacian =
        gray[idx - width] +
        gray[idx - 1] -
        4 * gray[idx] +
        gray[idx + 1] +
        gray[idx + width];
      edgeSum += Math.abs(laplacian);
    }
  }

  const meanLum = luminanceSum / total;
  const contrast = Math.sqrt(luminanceSq / total - meanLum * meanLum);
  const saturation = saturationSum / total;
  const warmth = warmCool / total;
  const edgeDensity = edgeSum / (total / sampleStep / sampleStep);

  const exposureScore = strictRange(meanLum, 145, 20, 76);
  const contrastScore = strictRange(contrast, 54, 16, 58);
  const light = clamp(exposureScore * 0.72 + contrastScore * 0.28);
  const sharpness = clamp(strictRange(edgeDensity, 32, 12, 44) - Math.max(0, edgeDensity - 72) * 0.35);
  const backgroundClutter = Math.max(0, edgeDensity - 28) * 1.65 + Math.max(0, saturation - 0.46) * 80;
  const background = clamp(86 - backgroundClutter);
  const color = clamp(strictRange(warmth, 0.04, 0.08, 0.26) * 0.7 + strictRange(saturation, 0.32, 0.16, 0.42) * 0.3);
  const fallbackBox = faceInfo.detected
    ? null
    : estimateFaceFromSkin(data, width, height) ?? estimateFaceFromPortraitWindow(data, width, height);
  const resolvedFaceInfo = fallbackBox
    ? {
        detected: true,
        supported: faceInfo.supported,
        method: "fallback",
        box: fallbackBox,
      }
    : faceInfo;
  let framing = 34;

  if (resolvedFaceInfo.detected && resolvedFaceInfo.box) {
    const box = resolvedFaceInfo.box;
    const faceAreaRatio = (box.width * box.height) / (width * height);
    const centerX = (box.x + box.width / 2) / width;
    const centerY = (box.y + box.height / 2) / height;
    const sizeScore = strictRange(faceAreaRatio, 0.14, 0.06, 0.18);
    const centerScore = strictRange(centerX, 0.5, 0.08, 0.26);
    const verticalScore = strictRange(centerY, 0.41, 0.1, 0.24);
    framing = clamp(sizeScore * 0.42 + centerScore * 0.28 + verticalScore * 0.3);
  } else if (resolvedFaceInfo.supported) {
    framing = 24;
  }

  const facePresence = resolvedFaceInfo.detected
    ? resolvedFaceInfo.method === "native"
      ? 86
      : resolvedFaceInfo.method === "manual"
        ? 78
        : 72
    : 14;

  const baseMetrics = {
    light: Math.round(light),
    sharpness: Math.round(sharpness),
    framing: Math.round(framing),
    background: Math.round(background),
    color: Math.round(color),
  };
  const rawAppearance = clamp(
    facePresence * 0.24 +
      light * 0.24 +
      sharpness * 0.2 +
      framing * 0.2 +
      color * 0.08 +
      background * 0.04,
  );
  const appearance = capForWeakness(rawAppearance, baseMetrics, resolvedFaceInfo);

  const metrics = {
    appearance: Math.round(appearance),
    ...baseMetrics,
  };

  const weightedScore = Object.entries(metrics).reduce((sum, [key, value]) => sum + value * weights[key], 0);
  const totalScore = Math.round(capForWeakness(weightedScore, baseMetrics, resolvedFaceInfo));

  return {
    score: totalScore,
    metrics,
    details: {
      brightness: Math.round(meanLum),
      contrast: Math.round(contrast),
      saturation: Number(saturation.toFixed(2)),
      warmth: Number(warmth.toFixed(2)),
      edgeDensity: Math.round(edgeDensity),
    },
    faceInfo: resolvedFaceInfo,
    appearance: createAppearanceProfile(Math.round(appearance), metrics, resolvedFaceInfo),
    advice: createAdvice(metrics, resolvedFaceInfo),
  };
}

async function analyzePhoto(file, manualFaceInfo = null) {
  const imageUrl = URL.createObjectURL(file);
  const image = new Image();
  image.decoding = "async";
  image.src = imageUrl;
  await image.decode();

  const maxSide = 900;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);

  const faceInfo = manualFaceInfo ?? await detectFace(image);
  const scaledFace = manualFaceInfo
    ? manualFaceInfo
    : faceInfo.box
      ? {
          ...faceInfo,
          box: {
            x: faceInfo.box.x * scale,
            y: faceInfo.box.y * scale,
            width: faceInfo.box.width * scale,
            height: faceInfo.box.height * scale,
          },
        }
      : faceInfo;

  return {
    imageUrl,
    name: file.name,
    size: file.size,
    dimensions: { width: image.naturalWidth, height: image.naturalHeight },
    renderSize: { width, height },
    faceInfo: scaledFace,
    ...analyzePixels(canvas, context, scaledFace),
  };
}

function PhotoGuides({ analysis, visible }) {
  if (!visible || !analysis?.renderSize) return null;

  const { width, height } = analysis.renderSize;
  const box = analysis.faceInfo?.box;
  const geometry = createGeometryModel(analysis);
  const imageCenterX = width / 2;
  const imageCenterY = height / 2;

  return (
    <svg
      className="photo-guides"
      preserveAspectRatio="xMidYMid slice"
      viewBox={`0 0 ${width} ${height}`}
      aria-label="Линии анализа фото"
    >
      <line className="guide-soft" x1={width / 3} x2={width / 3} y1="0" y2={height} />
      <line className="guide-soft" x1={(width / 3) * 2} x2={(width / 3) * 2} y1="0" y2={height} />
      <line className="guide-soft" x1="0" x2={width} y1={height / 3} y2={height / 3} />
      <line className="guide-soft" x1="0" x2={width} y1={(height / 3) * 2} y2={(height / 3) * 2} />
      <line className="guide-center" x1={imageCenterX} x2={imageCenterX} y1="0" y2={height} />
      <line className="guide-center" x1="0" x2={width} y1={imageCenterY} y2={imageCenterY} />
      <text className="guide-label" x={imageCenterX + 10} y={24}>центр кадра</text>

      {box && geometry ? (
        <>
          <rect className="guide-face" x={box.x} y={box.y} width={box.width} height={box.height} />
          <line className="guide-third" x1={box.x} x2={box.x + box.width} y1={geometry.points.facialThirds[0]} y2={geometry.points.facialThirds[0]} />
          <line className="guide-third" x1={box.x} x2={box.x + box.width} y1={geometry.points.facialThirds[1]} y2={geometry.points.facialThirds[1]} />
          <line
            className="guide-main"
            x1={box.x + box.width / 2}
            x2={box.x + box.width / 2}
            y1={box.y}
            y2={box.y + box.height}
          />
          <line
            className="guide-eye guide-tilt"
            x1={geometry.points.leftEye.x}
            x2={geometry.points.rightEye.x}
            y1={geometry.points.leftEye.y}
            y2={geometry.points.rightEye.y}
          />
          <line
            className="guide-mouth"
            x1={geometry.points.mouthLeft.x}
            x2={geometry.points.mouthRight.x}
            y1={geometry.points.mouthLeft.y}
            y2={geometry.points.mouthRight.y}
          />
          <line
            className="guide-jaw-side"
            x1={geometry.points.leftJaw.x}
            x2={geometry.points.chin.x}
            y1={geometry.points.leftJaw.y}
            y2={geometry.points.chin.y}
          />
          <line
            className="guide-jaw-side"
            x1={geometry.points.chin.x}
            x2={geometry.points.rightJaw.x}
            y1={geometry.points.chin.y}
            y2={geometry.points.rightJaw.y}
          />
          <polyline
            className="guide-jaw"
            points={`${geometry.points.leftJaw.x},${geometry.points.leftJaw.y} ${geometry.points.chin.x},${geometry.points.chin.y} ${geometry.points.rightJaw.x},${geometry.points.rightJaw.y}`}
          />
          <line
            className="guide-vector"
            x1={imageCenterX}
            x2={box.x + box.width / 2}
            y1={imageCenterY}
            y2={box.y + box.height / 2}
          />
          <circle className="guide-dot" cx={box.x + box.width / 2} cy={box.y + box.height / 2} r={7} />
          <text className="guide-label" x={box.x + 8} y={Math.max(22, box.y - 10)}>область лица</text>
          <text className="guide-label" x={geometry.points.rightEye.x + 6} y={geometry.points.rightEye.y - 8}>eye tilt {formatSigned(geometry.eyeTiltDeg, "°")}</text>
          <text className="guide-label" x={geometry.points.mouthRight.x + 6} y={geometry.points.mouthRight.y - 8}>mouth</text>
          <text className="guide-label" x={geometry.points.chin.x + 8} y={geometry.points.chin.y + 24}>jaw {geometry.jawAngle}°</text>
          <text className="guide-label" x={box.x + 8} y={geometry.points.facialThirds[0] - 8}>thirds</text>
        </>
      ) : null}
    </svg>
  );
}

function pointFromImageClick(event, renderSize) {
  const rect = event.currentTarget.getBoundingClientRect();
  const scale = Math.max(rect.width / renderSize.width, rect.height / renderSize.height);
  const drawnWidth = renderSize.width * scale;
  const drawnHeight = renderSize.height * scale;
  const offsetX = (rect.width - drawnWidth) / 2;
  const offsetY = (rect.height - drawnHeight) / 2;
  const x = (event.clientX - rect.left - offsetX) / scale;
  const y = (event.clientY - rect.top - offsetY) / scale;

  return {
    x: clamp(x, 0, renderSize.width),
    y: clamp(y, 0, renderSize.height),
  };
}

function createManualFaceBox(point, renderSize, currentBox) {
  const height = currentBox?.height
    ? clamp(currentBox.height, renderSize.height * 0.18, renderSize.height * 0.38)
    : renderSize.height * 0.29;
  const width = currentBox?.width
    ? clamp(currentBox.width, renderSize.width * 0.16, renderSize.width * 0.36)
    : height * 0.72;

  return {
    detected: true,
    supported: true,
    method: "manual",
    box: {
      x: clamp(point.x - width / 2, 0, renderSize.width - width),
      y: clamp(point.y - height * 0.46, 0, renderSize.height - height),
      width,
      height,
    },
  };
}

function MetricBar({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-head">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="bar" aria-hidden="true">
        <span style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function App() {
  const [analysis, setAnalysis] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [looksmaxScale, setLooksmaxScale] = useState("male");
  const [showGuides, setShowGuides] = useState(true);
  const [manualMode, setManualMode] = useState(false);
  const [sourceFile, setSourceFile] = useState(null);
  const inputRef = useRef(null);

  const grade = useMemo(() => gradeFromScore(analysis?.score ?? 0), [analysis]);
  const looksmaxTier = useMemo(
    () => createLooksmaxTier(analysis?.appearance.score ?? 0, looksmaxScale),
    [analysis, looksmaxScale],
  );
  const guideSummary = useMemo(() => createGuideSummary(analysis), [analysis]);
  const detailedExplanation = useMemo(
    () => createDetailedExplanation(analysis, looksmaxTier),
    [analysis, looksmaxTier],
  );
  const appearanceBreakdown = useMemo(() => createAppearanceBreakdown(analysis), [analysis]);

  async function handleFile(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Нужен файл изображения: JPG, PNG, WebP или другой формат, который поддерживает браузер.");
      return;
    }

    setIsAnalyzing(true);
    setError("");
    try {
      setSourceFile(file);
      setManualMode(false);
      const result = await analyzePhoto(file);
      setAnalysis((current) => {
        if (current?.imageUrl) URL.revokeObjectURL(current.imageUrl);
        return result;
      });
    } catch {
      setError("Не удалось прочитать изображение. Попробуйте другой файл или экспорт в JPG/PNG.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleManualFaceClick(event) {
    if (!manualMode || !analysis?.renderSize || !sourceFile) return;

    event.preventDefault();
    event.stopPropagation();
    const point = pointFromImageClick(event, analysis.renderSize);
    const manualFaceInfo = createManualFaceBox(point, analysis.renderSize, analysis.faceInfo?.box);

    setIsAnalyzing(true);
    setError("");
    try {
      const result = await analyzePhoto(sourceFile, manualFaceInfo);
      setAnalysis((current) => {
        if (current?.imageUrl) URL.revokeObjectURL(current.imageUrl);
        return result;
      });
      setShowGuides(true);
      setManualMode(false);
    } catch {
      setError("Не удалось применить ручную разметку. Попробуйте загрузить фото заново.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  function onDrop(event) {
    event.preventDefault();
    setDragActive(false);
    handleFile(event.dataTransfer.files?.[0]);
  }

  return (
    <main className="shell">
      <section className="workspace">
        <div className="panel upload-panel">
          <div className="brand-row">
            <div className="brand-mark">
              <Sparkles size={19} />
            </div>
            <div>
              <p className="eyebrow">Dating Photo Analyzer</p>
              <h1>Оценка фото для профиля знакомств</h1>
            </div>
          </div>

          <button
            className={`dropzone ${dragActive ? "active" : ""} ${manualMode ? "manual-mode" : ""}`}
            onClick={() => {
              if (!manualMode) inputRef.current?.click();
            }}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            type="button"
          >
            {analysis ? (
              <span
                className="preview-wrap"
                onClick={handleManualFaceClick}
                role={manualMode ? "button" : undefined}
                tabIndex={manualMode ? 0 : undefined}
              >
                <img className="preview" src={analysis.imageUrl} alt="Загруженное фото" />
                <PhotoGuides analysis={analysis} visible={showGuides} />
                {manualMode ? <span className="manual-hint">Кликните по центру лица</span> : null}
              </span>
            ) : (
              <span className="empty-preview">
                <ImageUp size={54} />
                <span>Перетащите фото сюда или выберите файл</span>
              </span>
            )}
            <span className="upload-action">
              <Upload size={17} />
              {analysis ? "Заменить фото" : "Загрузить фото"}
            </span>
          </button>

          <input
            ref={inputRef}
            accept="image/*"
            className="file-input"
            onChange={(event) => handleFile(event.target.files?.[0])}
            type="file"
          />

          {error ? <p className="error">{error}</p> : null}

          <div className="scale-control">
            <span>Looksmaxing шкала</span>
            <div role="group" aria-label="Looksmaxing шкала">
              <button
                className={looksmaxScale === "male" ? "selected" : ""}
                onClick={() => setLooksmaxScale("male")}
                type="button"
              >
                Мужская
              </button>
              <button
                className={looksmaxScale === "female" ? "selected" : ""}
                onClick={() => setLooksmaxScale("female")}
                type="button"
              >
                Женская
              </button>
            </div>
          </div>

          {analysis ? (
            <div className="photo-tools">
              <button
                className={`guide-toggle ${showGuides ? "selected" : ""}`}
                onClick={() => setShowGuides((current) => !current)}
                type="button"
              >
                {showGuides ? "Скрыть линии" : "Показать линии"}
              </button>
              <button
                className={`manual-toggle ${manualMode ? "selected" : ""}`}
                onClick={() => setManualMode((current) => !current)}
                type="button"
              >
                <ScanFace size={17} />
                {manualMode ? "Отменить разметку" : "Указать лицо вручную"}
              </button>
            </div>
          ) : null}

          <div className="privacy-note">
            <Shield size={18} />
            <span>Фото анализируется локально в браузере. Серверная отправка не используется.</span>
          </div>
        </div>

        <div className="panel result-panel">
          {analysis ? (
            <>
              <div className="score-grid">
                <div className={`score-card ${grade.tone}`}>
                  <div className="score-ring" style={{ "--score-angle": `${analysis.score * 3.6}deg` }}>
                    <span>{analysis.score}</span>
                  </div>
                  <div>
                    <p className="eyebrow">Готовность</p>
                    <h2>{grade.label}</h2>
                    <p>
                      Итог включает качество фото и обязательную оценку внешней подачи в кадре.
                    </p>
                  </div>
                </div>

                <div className="quick-facts">
                  <div>
                    <Aperture size={19} />
                    <span>{analysis.dimensions.width} × {analysis.dimensions.height}</span>
                  </div>
                  <div>
                    <Target size={19} />
                    <span>
                      {analysis.faceInfo.detected
                        ? analysis.faceInfo.method === "manual"
                          ? "Лицо указано вручную"
                          : analysis.faceInfo.method === "fallback"
                            ? "Лицо найдено по портрету"
                            : "Лицо найдено"
                        : "Лицо не найдено"}
                    </span>
                  </div>
                  <div>
                    <Zap size={19} />
                    <span>{Math.round(analysis.size / 1024)} КБ</span>
                  </div>
                </div>
              </div>

              <div className="metrics">
                {Object.entries(analysis.metrics).map(([key, value]) => (
                  <MetricBar key={key} label={metricLabels[key]} value={value} />
                ))}
              </div>

              <section className="appearance-card">
                <div className="appearance-head">
                  <div className="appearance-icon">
                    <Smile size={22} />
                  </div>
                  <div>
                    <p className="eyebrow">Оценка внешности</p>
                    <h3>{analysis.appearance.label}</h3>
                  </div>
                  <strong>{analysis.appearance.score}</strong>
                </div>
                <p>{analysis.appearance.summary}</p>
                <div className="appearance-notes">
                  <span>Уверенность: {analysis.appearance.confidence}</span>
                  {(analysis.appearance.strengths.length
                    ? analysis.appearance.strengths
                    : analysis.appearance.fixes
                  ).map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </section>

              <section className="appearance-detail-card">
                <div className="section-title">
                  <Smile size={19} />
                  <h3>Подробная оценка внешности</h3>
                </div>
                <p>{appearanceBreakdown.summary}</p>
                <div className="appearance-breakdown">
                  {appearanceBreakdown.aspects.map((aspect) => (
                    <article key={aspect.title}>
                      <div>
                        <span>{aspect.title}</span>
                        <strong>{aspect.score}</strong>
                      </div>
                      <div className="mini-bar" aria-hidden="true">
                        <span style={{ width: `${aspect.score}%` }} />
                      </div>
                      <em>{aspect.verdict}</em>
                      <p>{aspect.text}</p>
                    </article>
                  ))}
                </div>
                <div className="appearance-summary-grid">
                  <div>
                    <strong>Главные просадки</strong>
                    <span>
                      {appearanceBreakdown.blockers.length
                        ? appearanceBreakdown.blockers.join(", ")
                        : "критичных просадок нет"}
                    </span>
                  </div>
                  <div>
                    <strong>Быстрый апгрейд</strong>
                    <span>
                      {appearanceBreakdown.upgrades.length
                        ? appearanceBreakdown.upgrades.join("; ")
                        : "сохранять текущий уровень и сделать серию фото"}
                    </span>
                  </div>
                </div>
              </section>

              <section className={`looksmax-card ${looksmaxTier.tone}`}>
                <div className="looksmax-head">
                  <div className="looksmax-icon">
                    <Crown size={22} />
                  </div>
                  <div>
                    <p className="eyebrow">Looksmaxing tier</p>
                    <h3>{looksmaxTier.label}</h3>
                  </div>
                  <span>{looksmaxTier.scaleLabel}</span>
                </div>
                <p>{looksmaxTier.note}. Tier считается по внешней подаче на фото, а не как объективный рейтинг человека.</p>
                <div className="tier-explain">
                  {detailedExplanation.tier.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
                <div className="tier-row" aria-label="Шкала looksmaxing">
                  {looksmaxTiers[looksmaxScale].map((tier) => (
                    <span
                      className={tier.label === looksmaxTier.label ? "active" : ""}
                      key={tier.label}
                    >
                      {tier.label}
                    </span>
                  ))}
                </div>
              </section>

              <section className="tier-examples-card">
                <div className="section-title">
                  <Crown size={19} />
                  <h3>Примеры подтипов</h3>
                </div>
                <p>
                  Это условные примеры внешней подачи в кадре. Они описывают не человека целиком,
                  а то, как фото обычно считывается в dating.
                </p>
                <div className="tier-examples">
                  {tierExamples[looksmaxScale].map((tier) => (
                    <article
                      className={tier.label === looksmaxTier.label ? "active" : ""}
                      key={tier.label}
                    >
                      <strong>{tier.label}</strong>
                      <span>{tier.look}</span>
                      <em>{tier.signals}</em>
                      <small>Апгрейд: {tier.upgrade}</small>
                    </article>
                  ))}
                </div>
              </section>

              <section className="geometry-card">
                <div className="section-title">
                  <Target size={19} />
                  <h3>Линии и углы на фото</h3>
                </div>
                <p>
                  Рисунки показывают геометрию, которая участвует в оценке композиции и внешней подачи:
                  центр кадра, правило третей, область лица и примерные оси лица.
                </p>
                <ul>
                  {guideSummary.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              <section className="deep-card">
                <div className="section-title">
                  <Info size={19} />
                  <h3>Почему такой уровень</h3>
                </div>
                <div className="factor-grid">
                  {detailedExplanation.factors.map((factor) => (
                    <article className="factor-card" key={factor.title}>
                      <div>
                        <span>{factor.title}</span>
                        <strong>{factor.value}</strong>
                      </div>
                      <em>{factor.impact}</em>
                      <p>{factor.text}</p>
                    </article>
                  ))}
                </div>
              </section>

              <section className="advice">
                <div className="section-title">
                  <Lightbulb size={19} />
                  <h3>Что улучшить</h3>
                </div>
                <ul>
                  {analysis.advice.map((item) => (
                    <li key={item}>
                      <Check size={17} />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="details">
                <div className="section-title">
                  <Info size={19} />
                  <h3>Технические сигналы</h3>
                </div>
                <div className="detail-grid">
                  <span>Яркость: {analysis.details.brightness}</span>
                  <span>Контраст: {analysis.details.contrast}</span>
                  <span>Насыщенность: {analysis.details.saturation}</span>
                  <span>Детализация: {analysis.details.edgeDensity}</span>
                </div>
              </section>

              <button className="secondary-button" onClick={() => inputRef.current?.click()} type="button">
                <RefreshCcw size={17} />
                Проверить другое фото
              </button>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">
                {isAnalyzing ? <RefreshCcw className="spin" size={32} /> : <Target size={32} />}
              </div>
              <h2>{isAnalyzing ? "Анализирую фото" : "Здесь появится разбор"}</h2>
              <p>
                {isAnalyzing
                  ? "Считаю свет, резкость, композицию и визуальную чистоту кадра."
                  : "Загрузите снимок, чтобы получить score и рекомендации по улучшению dating-профиля."}
              </p>
              <ul>
                {defaultTips.map((tip) => (
                  <li key={tip}>
                    <X size={0} aria-hidden="true" />
                    {tip}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

export default App;
