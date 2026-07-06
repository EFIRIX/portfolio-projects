"use client";

import { useState } from "react";

interface GeneratedField {
  label: string;
  text: string;
  charCount: number;
  maxChars: number;
  withinLimit: boolean;
  attempts: number;
}

interface PlatformCard {
  platformId: "wildberries" | "ozon";
  platformName: string;
  title: GeneratedField;
  description: GeneratedField;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? "Ошибка запроса");
  return data as T;
}

function FieldView({ field }: { field: GeneratedField }) {
  return (
    <div className="field-out">
      <div className="head">
        <span className="name">{field.label}</span>
        <span className={`counter${field.withinLimit ? "" : " over"}`}>
          {field.charCount} / {field.maxChars}
        </span>
      </div>
      <div className="value">{field.text}</div>
      {field.attempts > 1 && field.withinLimit && (
        <div className="retry-note">
          Уложились с {field.attempts}-й попытки (было длиннее лимита — попросили модель сократить)
        </div>
      )}
      {!field.withinLimit && (
        <div className="retry-note">
          ⚠ Модель не уложилась за несколько попыток — текст обрезан как крайний фолбэк
        </div>
      )}
    </div>
  );
}

function CardView({ card }: { card: PlatformCard }) {
  const cls = card.platformId === "wildberries" ? "wb" : "ozon";
  return (
    <div className="card">
      <h2>
        <span className={`badge ${cls}`}>{card.platformName}</span>
      </h2>
      <FieldView field={card.title} />
      <FieldView field={card.description} />
    </div>
  );
}

export default function Home() {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [features, setFeatures] = useState("");

  const [cards, setCards] = useState<PlatformCard[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [review, setReview] = useState("");
  const [reviewReply, setReviewReply] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState("");

  async function handleGenerate() {
    setError("");
    setLoading(true);
    setCards([]);
    setKeywords([]);
    try {
      const input = { name, category, features };
      // Карточки и SEO — независимые запросы, шлём параллельно.
      const [gen, seo] = await Promise.all([
        postJson<{ cards: PlatformCard[] }>("/api/generate", input),
        postJson<{ keywords: string[] }>("/api/seo", input),
      ]);
      setCards(gen.cards);
      setKeywords(seo.keywords);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  }

  async function handleReview() {
    setReviewError("");
    setReviewLoading(true);
    setReviewReply("");
    try {
      const data = await postJson<{ response: string }>(
        "/api/review-response",
        { review, productName: name || undefined },
      );
      setReviewReply(data.response);
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setReviewLoading(false);
    }
  }

  const canGenerate = name.trim() && category.trim() && features.trim() && !loading;

  return (
    <div className="container">
      <h1>Маркетплейс-копайлот</h1>
      <p className="subtitle">
        Карточка товара под лимиты Wildberries и Ozon отдельно, SEO-ключи и
        ответы на отзывы. Лимиты символов проверяются кодом после генерации.
      </p>

      <div className="card">
        <h2>Товар</h2>
        <label htmlFor="name">Название товара</label>
        <input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Например: Беспроводные наушники TWS Pro"
        />
        <label htmlFor="category">Категория</label>
        <input
          id="category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Например: Электроника / Наушники"
        />
        <label htmlFor="features">Ключевые характеристики</label>
        <textarea
          id="features"
          rows={4}
          value={features}
          onChange={(e) => setFeatures(e.target.value)}
          placeholder="Bluetooth 5.3, шумоподавление, 30 часов работы, влагозащита IPX5, сенсорное управление"
        />
        <button onClick={handleGenerate} disabled={!canGenerate}>
          {loading ? (
            <span className="spinner">Генерирую…</span>
          ) : (
            "Сгенерировать карточки"
          )}
        </button>
        {error && <div className="error">{error}</div>}
      </div>

      {cards.length > 0 && (
        <div className="section grid">
          {cards.map((c) => (
            <CardView key={c.platformId} card={c} />
          ))}
        </div>
      )}

      {keywords.length > 0 && (
        <div className="section card">
          <h2>SEO-ключевые слова ({keywords.length})</h2>
          <div className="keywords">
            {keywords.map((k, i) => (
              <span className="chip" key={i}>
                {k}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="section card">
        <h2>Ответ на негативный отзыв</h2>
        <label htmlFor="review">Текст отзыва покупателя</label>
        <textarea
          id="review"
          rows={4}
          value={review}
          onChange={(e) => setReview(e.target.value)}
          placeholder="Наушники пришли с царапиной на корпусе, и правый динамик тише левого. Ожидал большего за эти деньги."
        />
        <button
          className="secondary"
          onClick={handleReview}
          disabled={!review.trim() || reviewLoading}
        >
          {reviewLoading ? (
            <span className="spinner">Пишу ответ…</span>
          ) : (
            "Сгенерировать ответ"
          )}
        </button>
        {reviewError && <div className="error">{reviewError}</div>}
        {reviewReply && (
          <div className="field-out" style={{ marginTop: 16 }}>
            <div className="value">{reviewReply}</div>
          </div>
        )}
      </div>
    </div>
  );
}
