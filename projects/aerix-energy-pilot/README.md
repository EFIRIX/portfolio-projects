# AERIX Energy Pilot (РФ)

## Описание
AERIX — ИИ-система предиктивного управления энергопотреблением,
снижающая пиковые нагрузки энергосистем и промышленных предприятий.

## Проблема
- Пиковые нагрузки увеличивают стоимость генерации
- Неэффективное распределение мощности
- Рост выбросов CO2
- Недостаточная цифровизация управления нагрузкой

## Решение
AI-модуль, который:
- прогнозирует почасовое потребление
- выявляет будущие пики
- оптимизирует распределение нагрузки
- рассчитывает экономический и экологический эффект

## Архитектура
Data → Preprocessing → Feature Engineering → Forecast Model →
Peak Detection → Optimization → Economic & CO2 Analysis → Visualization

## Данные
- Источник: PJM (AEP)
- Период: 2004–2018
- Объём: 121 296 часов

## Модели
- Linear Regression (baseline)
- Random Forest (основная)

## Результаты
- MAE (RF): 1334 МВт
- Улучшение над baseline: 3.71%
- Снижение пика: 16.9%
- Снижение мощности: 10 169 МВт

## Экономический эффект
≈ 76 млн ₽ экономии за один пиковый час
(при 7 500 ₽/МВт·ч)

## Экологический эффект
≈ 4.6 тыс. тонн CO2 снижения за пик

## Запуск
```bash
python3 main.py
```

## Конфигурация
`configs/config.py`

## Структура проекта
```text
aerix_energy_pilot/
├── README.md
├── configs/
│   └── config.py
├── data/
│   ├── AEP_hourly.csv
│   └── energy_consumption.csv
├── main.py
├── models/
│   └── random_forest.pkl
├── outputs/
│   ├── detected_peaks.png
│   ├── forecast_vs_actual.png
│   └── historical_consumption.png
├── requirements.txt
└── src/
    ├── __init__.py
    ├── data_loader.py
    ├── feature_engineering.py
    ├── model.py
    ├── optimization.py
    ├── peak_detection.py
    ├── preprocessing.py
    ├── utils.py
    └── visualization.py
```

## Roadmap
- Интеграция с промышленными системами
- Прогнозирование для предприятий
- Оптимизация энергопотребления заводов
- Переход к платформе управления инфраструктурой

## Статус
MVP / прототип AERIX Energy Module
