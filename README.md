# SafeRoad AI

Превентивная аналитика дорожной безопасности: детекция near-miss (почти-аварий)
на видео с обычных городских камер. Технический план: `docs/` (техплан v2 —
канонический контекст проекта).

**Статус: Вехи 0–2.5 (инжест, детекция/трекинг, гейт качества, калибровка,
Калман/RTS).** Конфликтные зоны, TTC/PET и near-miss — следующие вехи; см. план.

## Быстрый старт

```bash
pip install -r requirements.txt
# torch ставится CPU-сборкой, чтобы не тянуть CUDA:
#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 1. Синтетический прогон (без YOLO, известная истина, с калибровкой):
python scripts/make_synthetic_video.py
python -m pipeline.run --video sample_data/synthetic_intersection.mp4 \
    --tracker fake --script sample_data/synthetic_detections.json \
    --camera configs/cameras/synthetic_cam.yaml

# 2. Реальное видео (YOLO + ByteTrack; без --camera остановится на image space):
python -m pipeline.run --video path/to/intersection.mp4 \
    --camera configs/cameras/your_cam.yaml

# 3. Тесты:
python -m pytest tests/ -q
```

Каждый прогон создаёт `output/runs/<run_id>/` со стадийными артефактами:

```
manifest.json            версии, конфиг, git-ревизия
00_ingest/               ingest_report.json (вердикт пригодности), pts_map.json
01_tracks_raw/           сырой выход трекера (jsonl по кадрам)
03_tracks_gated/         tracks.json, quarantine/, health.json (метрики здоровья)
08_evidence/             annotated.mp4
```

## Ключевые инварианты (не нарушать)

1. Время берётся ТОЛЬКО из PTS-карты инжеста, никогда `frame_idx / fps`.
2. Треки с разрывом > `max_gap_s` режутся, не интерполируются молча.
3. Мусорные треки уходят в карантин с причиной, не в анализ безопасности.
4. Все пороги — в `configs/thresholds/` и помечены экспериментальными.
5. Пиксельные и метровые координаты не смешиваются (суффиксы `_px`, `_m`, `_s`).

## Структура

```
core/       общие типы (Detection, Track), логирование
ingest/     Веха 0: PTS, VFR, критерии отклонения видео
vision/     Веха 1: YOLO+ByteTrack, гейт качества, рендер
motion/     Веха 2.5: Калман/RTS (заглушка)
geometry/   Веха 4: конфликтные зоны (заглушка)
safety/     Вехи 4-5: TTC/PET/риск (заглушка)
pipeline/   стадийный раннер
validation/ Веха 3: разметка, золотой набор (заглушка)
tests/      unit + синтетические end-to-end
```
