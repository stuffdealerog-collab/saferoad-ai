// SafeRoad AI — investor/government pitch deck (RU), 18 slides, 16:9 wide
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const icons = require("react-icons/fa");

// ---------- palette (road-safety: asphalt night + safety amber) ----------
const C = {
  dark: "141E2E",      // asphalt night (dominant on dark slides)
  dark2: "1D2B40",     // card on dark
  amber: "FFB020",     // safety amber accent
  amberDeep: "E89A0C",
  slate: "5B6B7F",     // muted text
  ink: "1A2332",       // body text on light
  light: "FFFFFF",
  ice: "EEF2F7",       // light card bg
  iceLine: "D8E0EA",
  green: "3BA55D",
  red: "D64545",
};
const F = { head: "Arial", body: "Calibri" };

// ---------- icon rasterization ----------
async function iconPng(name, hexColor, px = 256) {
  const El = icons[name];
  if (!El) throw new Error("no icon " + name);
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(El, { color: "#" + hexColor, size: px })
  );
  const buf = await sharp(Buffer.from(svg)).resize(px, px, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const ICON = {};
  const wanted = [
    ["video", "FaVideo", "FFFFFF"],
    ["crash", "FaCarCrash", "FFFFFF"],
    ["chart", "FaChartLine", "FFFFFF"],
    ["shield", "FaShieldAlt", "FFFFFF"],
    ["road", "FaRoad", "FFFFFF"],
    ["eye", "FaEye", "FFFFFF"],
    ["cog", "FaCog", "FFFFFF"],
    ["check", "FaCheckCircle", "FFFFFF"],
    ["map", "FaMapMarkedAlt", "FFFFFF"],
    ["lock", "FaLock", "FFFFFF"],
    ["rocket", "FaRocket", "FFFFFF"],
    ["users", "FaUsers", "FFFFFF"],
    ["bolt", "FaBolt", "FFFFFF"],
    ["search", "FaSearchLocation", "FFFFFF"],
    ["balance", "FaBalanceScale", "FFFFFF"],
    ["city", "FaCity", "FFFFFF"],
    ["walk", "FaWalking", "FFFFFF"],
    ["clock", "FaClock", "FFFFFF"],
    ["darkVideo", "FaVideo", "FFB020"],
    ["darkChart", "FaChartLine", "FFB020"],
    ["darkShield", "FaShieldAlt", "FFB020"],
    ["darkMap", "FaMapMarkedAlt", "FFB020"],
  ];
  for (const [key, name, color] of wanted) ICON[key] = await iconPng(name, color);

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  const W = 13.33, H = 7.5;

  // ---------- helpers ----------
  function iconCircle(slide, dataKey, x, y, d, circleColor) {
    slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: circleColor || C.amber } });
    const pad = d * 0.26;
    slide.addImage({ data: ICON[dataKey], x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
  }
  let _pgNum = 1;
  function pageFooter(slide, n, darkBg) {
    _pgNum++;
    slide.addText("SafeRoad AI", {
      x: 0.55, y: H - 0.42, w: 2.5, h: 0.3, fontFace: F.body, fontSize: 9,
      color: darkBg ? "6E7E93" : "9AA7B5", margin: 0,
    });
    slide.addText(String(_pgNum), {
      x: W - 1.0, y: H - 0.42, w: 0.5, h: 0.3, fontFace: F.body, fontSize: 9,
      color: darkBg ? "6E7E93" : "9AA7B5", align: "right", margin: 0,
    });
  }
  function title(slide, txt, opts = {}) {
    slide.addText(txt, {
      x: 0.55, y: 0.42, w: opts.w || 12.2, h: 0.75, fontFace: F.head, fontSize: 30, bold: true,
      color: opts.color || C.ink, margin: 0,
    });
  }
  function kicker(slide, txt, opts = {}) {
    slide.addText(txt.toUpperCase(), {
      x: 0.55, y: 1.12, w: 12.2, h: 0.32, fontFace: F.body, fontSize: 12,
      color: opts.color || C.slate, charSpacing: 2, margin: 0,
    });
  }

  // =================================================================
  // SLIDE 1 — TITLE (dark)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.dark };
    // faint "road lane" dashes as motif
    for (let i = 0; i < 6; i++) {
      s.addShape("rect", { x: 1.0 + i * 2.1, y: 6.55, w: 1.0, h: 0.08, fill: { color: C.amber, transparency: 78 } });
    }
    iconCircle(s, "shield", 0.85, 0.85, 0.75);
    s.addText("SafeRoad AI", {
      x: 0.8, y: 2.35, w: 11.7, h: 1.15, fontFace: F.head, fontSize: 60, bold: true, color: C.light, margin: 0,
    });
    s.addText("Обнаружить опасный перекрёсток до аварии", {
      x: 0.8, y: 3.55, w: 11.7, h: 0.6, fontFace: F.head, fontSize: 24, color: C.amber, margin: 0,
    });
    s.addText(
      "Превентивная аналитика дорожной безопасности: существующие городские камеры становятся сенсорами почти-аварий (near-miss) — опасные места видны до того, как случится ДТП.",
      { x: 0.8, y: 4.35, w: 9.6, h: 0.95, fontFace: F.body, fontSize: 15, color: "C7D2E0", margin: 0 }
    );
    s.addText("Узбекистан · 2026 · Government AI", {
      x: 0.8, y: 5.65, w: 8, h: 0.35, fontFace: F.body, fontSize: 12, color: "8EA0B5", margin: 0,
    });
  }

  // =================================================================
  // SLIDE 2 — PROBLEM (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Статистика ДТП видит опасность только после аварий");
    kicker(s, "Проблема · реактивная модель безопасности");

    const stats = [
      { big: "1,19 млн", small: "погибших на дорогах мира ежегодно (ВОЗ, 2023)" },
      { big: "1 854", small: "погибших в ДТП в Узбекистане за 2025 год (СБДД)" },
      { big: "9 245", small: "ДТП за 2025 год; 7 391 человек ранены (СБДД)" },
      { big: "~3% ВВП", small: "цена дорожных аварий для большинства стран (оценка ВОЗ)" },
    ];
    const cw = 2.92, gap = 0.18, x0 = 0.55, y0 = 1.75;
    stats.forEach((st, i) => {
      const x = x0 + i * (cw + gap);
      s.addShape("roundRect", { x, y: y0, w: cw, h: 1.95, fill: { color: C.ice }, rectRadius: 0.08 });
      s.addText(st.big, { x: x + 0.18, y: y0 + 0.22, w: cw - 0.36, h: 0.75, fontFace: F.head, fontSize: 30, bold: true, color: C.ink, margin: 0 });
      s.addText(st.small, { x: x + 0.18, y: y0 + 1.0, w: cw - 0.36, h: 0.85, fontFace: F.body, fontSize: 11.5, color: C.slate, margin: 0 });
    });

    s.addText(
      [
        { text: "Опасное место месяцами генерирует экстренные торможения, конфликты с пешеходами и почти-столкновения — ", options: {} },
        { text: "но попадает в статистику только тогда, когда аварии уже произошли.", options: { bold: true } },
      ],
      { x: 0.55, y: 4.15, w: 12.2, h: 0.75, fontFace: F.body, fontSize: 16, color: C.ink, margin: 0 }
    );

    // reactive chain
    const chain = ["Авария", "Протокол", "Статистика", "Вмешательство"];
    const bw = 2.55, by = 5.35;
    chain.forEach((c, i) => {
      const x = 0.9 + i * (bw + 0.55);
      s.addShape("roundRect", { x, y: by, w: bw, h: 0.72, fill: { color: C.light }, line: { color: C.red, width: 1.5 }, rectRadius: 0.08 });
      s.addText(c, { x, y: by, w: bw, h: 0.72, align: "center", valign: "middle", fontFace: F.body, fontSize: 15, bold: true, color: C.red, margin: 0 });
      if (i < chain.length - 1) {
        s.addText("→", { x: x + bw + 0.04, y: by, w: 0.5, h: 0.72, align: "center", valign: "middle", fontFace: F.body, fontSize: 20, color: C.slate, margin: 0 });
      }
    });
    s.addText("Сегодняшний цикл: вмешательство приходит после жертв", {
      x: 0.9, y: 6.25, w: 11, h: 0.35, fontFace: F.body, fontSize: 12, italic: true, color: C.slate, margin: 0,
    });
    pageFooter(s, 2, false);
  }

  // =================================================================
  // SLIDE 3 — INSIGHT / SOLUTION (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Решение: считать не аварии, а почти-аварии");
    kicker(s, "Суррогатные показатели безопасности — 50 лет науки, впервые в масштабе");

    // left: pyramid concept
    const px = 0.85, pw = 4.9;
    const rows = [
      { label: "ДТП с жертвами", w: 1.7, color: C.red, tc: "FFFFFF" },
      { label: "ДТП без жертв", w: 2.9, color: "E08A3C", tc: "FFFFFF" },
      { label: "Near-miss: почти-столкновения", w: 4.1, color: C.amber, tc: C.ink },
      { label: "Конфликты и опасные манёвры", w: 4.9, color: C.ice, tc: C.ink },
    ];
    let py = 2.0;
    rows.forEach((r) => {
      s.addShape("roundRect", { x: px + (pw - r.w) / 2, y: py, w: r.w, h: 0.78, fill: { color: r.color }, rectRadius: 0.06 });
      s.addText(r.label, { x: px + (pw - r.w) / 2, y: py, w: r.w, h: 0.78, align: "center", valign: "middle", fontFace: F.body, fontSize: 12.5, bold: true, color: r.tc, margin: 0 });
      py += 0.92;
    });
    s.addText("На каждое ДТП приходятся десятки и сотни наблюдаемых конфликтов — исследования дорожных конфликтов (Traffic Conflict Technique, FHWA SSAM) связывают их частоту с будущими авариями.", {
      x: px, y: py + 0.1, w: pw, h: 1.15, fontFace: F.body, fontSize: 12, color: C.slate, margin: 0,
    });

    // right: what SafeRoad does
    const rx = 6.35, rw = 6.4;
    s.addShape("roundRect", { x: rx, y: 1.95, w: rw, h: 4.75, fill: { color: C.dark }, rectRadius: 0.1 });
    s.addText("SafeRoad AI превращает существующие камеры в превентивные сенсоры", {
      x: rx + 0.35, y: 2.25, w: rw - 0.7, h: 0.85, fontFace: F.head, fontSize: 17, bold: true, color: C.light, margin: 0,
    });
    const feats = [
      ["darkVideo", "Видео с обычной камеры — единственный вход. Новое оборудование не требуется."],
      ["darkChart", "Физика, а не мнение: TTC, PET, скорость, траектории — детерминированные метрики."],
      ["darkMap", "Карта риска: где произойдёт следующая серьёзная авария — до того, как она произошла."],
      ["darkShield", "Каждое событие — с видеодоказательством, которое проверит инженер."],
    ];
    let fy = 3.3;
    feats.forEach(([ic, txt]) => {
      s.addShape("ellipse", { x: rx + 0.35, y: fy, w: 0.52, h: 0.52, fill: { color: C.dark2 } });
      s.addImage({ data: ICON[ic], x: rx + 0.35 + 0.13, y: fy + 0.13, w: 0.26, h: 0.26 });
      s.addText(txt, { x: rx + 1.05, y: fy - 0.06, w: rw - 1.45, h: 0.75, fontFace: F.body, fontSize: 12.5, color: "D5DEE9", valign: "middle", margin: 0 });
      fy += 0.82;
    });
    pageFooter(s, 3, false);
  }

  // =================================================================
  // SLIDE 4 — HOW IT WORKS (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Как это работает");
    kicker(s, "Детерминированный конвейер · без чёрного ящика");

    const steps = [
      ["video", "Видео", "Существующая камера или загруженный файл; проверка качества и реального времени кадров"],
      ["eye", "Детекция и трекинг", "Каждый участник движения получает устойчивый ID и траекторию (YOLO + ByteTrack)"],
      ["map", "Калибровка", "Проекция на плоскость дороги: пиксели превращаются в метры и км/ч с оценкой погрешности"],
      ["bolt", "Физика конфликтов", "TTC, PET, дистанции, торможения, геометрия конфликта — математика, не нейро-догадки"],
      ["search", "Near-miss события", "Прозрачные правила с reason codes: видно, почему событие сработало"],
      ["chart", "Доказательства и риск", "Видеоклип с метриками + карта риска перекрёстка для инженера"],
    ];
    const cols = 3, cw2 = 3.95, ch = 2.15, gx = 0.2, gy = 0.35, x0 = 0.55, y0 = 1.75;
    steps.forEach((st, i) => {
      const cx = x0 + (i % cols) * (cw2 + gx);
      const cy = y0 + Math.floor(i / cols) * (ch + gy);
      s.addShape("roundRect", { x: cx, y: cy, w: cw2, h: ch, fill: { color: C.ice }, rectRadius: 0.08 });
      iconCircle(s, st[0], cx + 0.25, cy + 0.25, 0.55);
      s.addText(String(i + 1) + ". " + st[1], { x: cx + 0.95, y: cy + 0.28, w: cw2 - 1.15, h: 0.5, fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(st[2], { x: cx + 0.25, y: cy + 0.95, w: cw2 - 0.5, h: 1.05, fontFace: F.body, fontSize: 11.5, color: C.slate, margin: 0 });
    });

    s.addText("Ключевой принцип: решения о физике принимает геометрия и математика. LLM — только для отчётов, никогда для измерений.", {
      x: 0.55, y: 6.75, w: 12.2, h: 0.4, fontFace: F.body, fontSize: 12.5, italic: true, color: C.ink, margin: 0,
    });
    pageFooter(s, 4, false);
  }

  // =================================================================
  // SLIDE 5 — PRODUCT (light) — event card mock
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Продукт: каждое событие можно проверить глазами");
    kicker(s, "MVP · один перекрёсток · инспектируемые доказательства");

    // left: mock evidence card (dark, like a video still)
    const mx = 0.55, my = 1.8, mw = 6.4, mh = 4.6;
    s.addShape("roundRect", { x: mx, y: my, w: mw, h: mh, fill: { color: C.dark }, rectRadius: 0.1 });
    s.addText("Перекрёсток «Чиланзар-7» · 00:32.1–00:36.8 · поворот × пешеход", {
      x: mx + 0.3, y: my + 0.2, w: mw - 0.6, h: 0.3, fontFace: F.body, fontSize: 10.5, color: "8EA0B5", margin: 0,
    });
    // fake trajectories
    // lines must have positive w/h (negative extents corrupt the file in PowerPoint) — use flips instead
    s.addShape("line", { x: mx + 0.7, y: my + 1.4, w: 4.6, h: 2.2, flipV: true, line: { color: C.amber, width: 3, dashType: "dash" } });
    s.addShape("line", { x: mx + 1.5, y: my + 0.9, w: 3.4, h: 2.9, flipH: true, line: { color: "7FB2E5", width: 3, dashType: "dash" } });
    s.addShape("ellipse", { x: mx + 2.55, y: my + 2.25, w: 0.85, h: 0.85, fill: { color: C.red, transparency: 35 } });
    s.addText("зона конфликта", { x: mx + 1.7, y: my + 3.15, w: 2.6, h: 0.3, fontFace: F.body, fontSize: 10, color: "E8B0B0", align: "center", margin: 0 });
    s.addText("Авто #48 · 37 км/ч", { x: mx + 4.55, y: my + 0.55, w: 1.8, h: 0.3, fontFace: F.body, fontSize: 11, bold: true, color: "7FB2E5", margin: 0 });
    s.addText("Пешеход #91", { x: mx + 0.55, y: my + 3.75, w: 2.0, h: 0.3, fontFace: F.body, fontSize: 11, bold: true, color: C.amber, margin: 0 });
    // metric chips
    const chips = ["TTC 1,2 с", "Дистанция 0,9 м", "Критично"];
    let chx = mx + 0.3;
    chips.forEach((c, i) => {
      const w = 1.15 + c.length * 0.03;
      s.addShape("roundRect", { x: chx, y: my + mh - 0.62, w, h: 0.42, fill: { color: i === 2 ? C.red : C.dark2 }, rectRadius: 0.21 });
      s.addText(c, { x: chx, y: my + mh - 0.62, w, h: 0.42, align: "center", valign: "middle", fontFace: F.body, fontSize: 10.5, bold: i === 2, color: "FFFFFF", margin: 0 });
      chx += w + 0.15;
    });

    // right: dashboard bullets
    const rx = 7.35, rw = 5.4;
    s.addText("Дашборд для инженера:", { x: rx, y: 1.85, w: rw, h: 0.4, fontFace: F.head, fontSize: 16, bold: true, color: C.ink, margin: 0 });
    const items = [
      ["check", "Лента конфликтов с severity, метриками и переходом к видеомоменту в один клик"],
      ["chart", "Аналитика: конфликты по времени суток, типам, тепловая карта опасных зон"],
      ["walk", "Отдельный фокус: конфликты «транспорт × пешеход» и уязвимые участники"],
      ["clock", "До/после: измеримый эффект каждого вмешательства — главный KPI для государства"],
    ];
    let iy = 2.45;
    items.forEach(([ic, txt]) => {
      iconCircle(s, ic, rx, iy, 0.5);
      s.addText(txt, { x: rx + 0.72, y: iy - 0.12, w: rw - 0.75, h: 0.95, fontFace: F.body, fontSize: 12.5, color: C.ink, valign: "middle", margin: 0 });
      iy += 1.0;
    });
    pageFooter(s, 5, false);
  }

  // =================================================================
  // SLIDE 6 — WHY NOW (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Почему сейчас");
    const cards = [
      ["city", "Камеры уже висят", "Национальный проект «Безопасный город» развернул видеонаблюдение по всей стране — SafeRoad добавляет интеллект к уже сделанным инвестициям, а не требует новых."],
      ["rocket", "Госкурс на ИИ", "Стратегия цифровизации и President AI Award (категория Government AI) создают спрос и канал внедрения для отечественных ИИ-решений."],
      ["bolt", "Технологии созрели", "Детекция и трекинг объектов достигли качества, при котором near-miss аналитика стала возможной на обычном городском видео — нужна инженерная дисциплина, а не научный прорыв."],
    ];
    const cw3 = 3.95, x0 = 0.55, y0 = 1.6, ch3 = 4.3;
    cards.forEach((c, i) => {
      const x = x0 + i * (cw3 + 0.2);
      s.addShape("roundRect", { x, y: y0, w: cw3, h: ch3, fill: { color: C.ice }, rectRadius: 0.08 });
      iconCircle(s, c[0], x + 0.3, y0 + 0.35, 0.62);
      s.addText(c[1], { x: x + 0.3, y: y0 + 1.2, w: cw3 - 0.6, h: 0.5, fontFace: F.head, fontSize: 16, bold: true, color: C.ink, margin: 0 });
      s.addText(c[2], { x: x + 0.3, y: y0 + 1.8, w: cw3 - 0.6, h: 2.3, fontFace: F.body, fontSize: 12.5, color: C.slate, margin: 0 });
    });
    s.addText("Окно возможности: города уже платят за камеры, которые пока только записывают. Мы делаем их превентивными.", {
      x: 0.55, y: 6.25, w: 12.2, h: 0.5, fontFace: F.body, fontSize: 14, italic: true, color: C.ink, margin: 0,
    });
    pageFooter(s, 6, false);
  }

  // =================================================================
  // SLIDE 7 — GOVERNMENT IMPACT (dark)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.dark };
    title(s, "Ценность для государства", { color: C.light });
    kicker(s, "Доказательная приоритизация дорожного бюджета", { color: "8EA0B5" });

    const rows = [
      ["map", "Рейтинг опасных мест", "Перекрёстки города, ранжированные по наблюдаемому риску: куда направить ограниченный бюджет в первую очередь"],
      ["balance", "Обоснование решений", "Каждая рекомендация подкреплена видеодоказательствами и метриками — аудируемо для любых проверок"],
      ["clock", "Оценка «до/после»", "Сработала ли реконструкция: конфликты/неделю до и после вмешательства — измеримый KPI эффективности"],
    ];
    let ry = 1.85;
    rows.forEach(([ic, h, t]) => {
      s.addShape("roundRect", { x: 0.55, y: ry, w: 8.1, h: 1.35, fill: { color: C.dark2 }, rectRadius: 0.08 });
      iconCircle(s, ic, 0.85, ry + 0.36, 0.62);
      s.addText(h, { x: 1.75, y: ry + 0.18, w: 6.7, h: 0.45, fontFace: F.head, fontSize: 15, bold: true, color: C.light, margin: 0 });
      s.addText(t, { x: 1.75, y: ry + 0.62, w: 6.7, h: 0.65, fontFace: F.body, fontSize: 11.5, color: "AFBDCD", margin: 0 });
      ry += 1.55;
    });

    // example before/after stat panel
    const px2 = 8.95, pw2 = 3.8;
    s.addShape("roundRect", { x: px2, y: 1.85, w: pw2, h: 4.45, fill: { color: C.dark2 }, line: { color: C.amber, width: 1 }, rectRadius: 0.1 });
    s.addText("Пример эффекта вмешательства*", { x: px2 + 0.25, y: 2.05, w: pw2 - 0.5, h: 0.4, fontFace: F.head, fontSize: 12.5, bold: true, color: C.amber, margin: 0 });
    const pairs = [
      ["Критические конфликты / нед.", "47 → 15"],
      ["Пешеходные конфликты / нед.", "31 → 9"],
      ["Средняя скорость", "43 → 32 км/ч"],
    ];
    let py2 = 2.6;
    pairs.forEach(([l, v]) => {
      s.addText(l, { x: px2 + 0.25, y: py2, w: pw2 - 0.5, h: 0.3, fontFace: F.body, fontSize: 11, color: "AFBDCD", margin: 0 });
      s.addText(v, { x: px2 + 0.25, y: py2 + 0.28, w: pw2 - 0.5, h: 0.55, fontFace: F.head, fontSize: 22, bold: true, color: C.green, margin: 0 });
      py2 += 1.02;
    });
    s.addText("* иллюстративный сценарий целевого KPI, не результаты пилота", {
      x: px2 + 0.25, y: 5.8, w: pw2 - 0.5, h: 0.45, fontFace: F.body, fontSize: 9, italic: true, color: "8EA0B5", margin: 0,
    });
    pageFooter(s, 7, true);
  }

  // =================================================================
  // SLIDE 8 — MARKET & MODEL (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Рынок и бизнес-модель");
    kicker(s, "B2G SaaS · от пилота к городу · от города к региону");

    // left: expansion ladder
    const ladder = [
      ["Пилот", "1 перекрёсток, договор с хокимиятом / СБДД", C.ice, C.ink],
      ["Город", "SaaS-подписка за перекрёсток: Ташкент — сотни камер «Безопасного города»", "FFE9C2", C.ink],
      ["Страна", "Областные центры Узбекистана + интеграция с гос-KPI безопасности", C.amber, C.ink],
      ["Регион", "Экспорт в Центральную Азию и СНГ: те же камеры, те же проблемы", C.dark, "FFFFFF"],
    ];
    let ly = 1.75;
    ladder.forEach(([h, t, bg, tc], i) => {
      const x = 0.55 + i * 0.45, w = 7.0 - i * 0.45;
      s.addShape("roundRect", { x, y: ly, w, h: 1.05, fill: { color: bg }, rectRadius: 0.08 });
      s.addText([
        { text: h + "  ", options: { bold: true, fontSize: 14 } },
        { text: t, options: { fontSize: 11.5 } },
      ], { x: x + 0.25, y: ly, w: w - 0.5, h: 1.05, fontFace: F.body, color: tc, valign: "middle", margin: 0 });
      ly += 1.18;
    });

    // right: model card
    const rx = 8.15, rw = 4.6;
    s.addShape("roundRect", { x: rx, y: 1.75, w: rw, h: 4.55, fill: { color: C.ice }, rectRadius: 0.1 });
    s.addText("Модель дохода", { x: rx + 0.3, y: 2.0, w: rw - 0.6, h: 0.4, fontFace: F.head, fontSize: 16, bold: true, color: C.ink, margin: 0 });
    const rev = [
      "Подписка за камеру/перекрёсток (анализ + дашборд + отчёты)",
      "Проекты «до/после» для оценки реконструкций",
      "Аналитические отчёты для планирования инфраструктуры",
      "Долгосрочно: городской ситуационный центр безопасности",
    ];
    s.addText(rev.map((t, i) => ({ text: t, options: { bullet: { code: "2022", indent: 12 }, breakLine: i < rev.length - 1, paraSpaceAfter: 10 } })), {
      x: rx + 0.3, y: 2.5, w: rw - 0.6, h: 3.6, fontFace: F.body, fontSize: 12.5, color: C.ink, margin: 0, valign: "top",
    });

    s.addText("Опорные цифры спроса: 9 245 ДТП и 1 854 погибших в 2025 году; безопасность дорожного движения — публичный приоритет государства.", {
      x: 0.55, y: 6.55, w: 12.2, h: 0.55, fontFace: F.body, fontSize: 11.5, italic: true, color: C.slate, margin: 0,
    });
    pageFooter(s, 8, false);
  }

  // =================================================================
  // SLIDE 8b — REVENUE MODEL (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Модель заработка");
    kicker(s, "Что продаётся, кому и когда появляется выручка");

    const streams = [
      ["1", "Платный пилот", "Развёртывание на 1–3 перекрёстках: калибровка, анализ, отчёт с доказательными клипами.",
       "Разовый проект", "Первая выручка", C.amber],
      ["2", "SaaS-подписка за перекрёсток", "Постоянный анализ, дашборд, лента конфликтов, ежемесячный отчёт по риску.",
       "Регулярный платёж", "Основной поток", C.amber],
      ["3", "Проекты «до / после»", "Замер конфликтов и скоростей до и после реконструкции — доказательство эффекта вмешательства.",
       "Проект под объект", "Высокая маржа", C.ice],
      ["4", "Городской аудит и отчёты", "Ранжирование десятков перекрёстков по риску для планирования дорожного бюджета.",
       "Крупный контракт", "Масштаб", C.ice],
    ];
    let y = 1.72;
    streams.forEach(([n, h, d, kind, role, bg]) => {
      s.addShape("roundRect", { x: 0.55, y, w: 8.55, h: 1.16, fill: { color: C.ice }, rectRadius: 0.08 });
      s.addShape("ellipse", { x: 0.82, y: y + 0.33, w: 0.5, h: 0.5, fill: { color: bg === C.amber ? C.amber : C.slate } });
      s.addText(n, { x: 0.82, y: y + 0.33, w: 0.5, h: 0.5, align: "center", valign: "middle",
                     fontFace: F.head, fontSize: 15, bold: true, color: bg === C.amber ? C.ink : "FFFFFF", margin: 0 });
      s.addText(h, { x: 1.55, y: y + 0.16, w: 4.2, h: 0.4, fontFace: F.head, fontSize: 14, bold: true, color: C.ink, margin: 0 });
      s.addText(d, { x: 1.55, y: y + 0.55, w: 7.3, h: 0.55, fontFace: F.body, fontSize: 11, color: C.slate, margin: 0 });
      s.addText(kind, { x: 5.9, y: y + 0.16, w: 3.0, h: 0.4, align: "right", fontFace: F.body, fontSize: 11.5, bold: true, color: C.ink, margin: 0 });
      y += 1.26;
    });

    // right column: pricing logic
    const rx = 9.4, rw = 3.4;
    s.addShape("roundRect", { x: rx, y: 1.72, w: rw, h: 4.7, fill: { color: C.dark }, rectRadius: 0.1 });
    s.addText("Логика цены", { x: rx + 0.28, y: 1.95, w: rw - 0.56, h: 0.35,
      fontFace: F.head, fontSize: 14.5, bold: true, color: C.amber, margin: 0 });
    s.addText("Подписка за один перекрёсток — доли процента от стоимости его реконструкции.\n\nГород платит не за видео, а за ответ на вопрос: какой из ста перекрёстков ремонтировать первым.\n\nОшибка приоритизации стоит дороже всей подписки.",
      { x: rx + 0.28, y: 2.4, w: rw - 0.56, h: 3.1, fontFace: F.body, fontSize: 11.5, color: "D5DEE9", margin: 0 });
    s.addText("Тарифы фиксируются по итогам первого платного пилота", {
      x: rx + 0.28, y: 5.6, w: rw - 0.56, h: 0.6, fontFace: F.body, fontSize: 10, italic: true, color: "8EA0B5", margin: 0 });

    s.addText("Ценность на кону: ВВП Узбекистана за 2025 год — свыше $147 млрд; ВОЗ оценивает потери от ДТП примерно в 3% ВВП, то есть порядка $4 млрд в год.", {
      x: 0.55, y: 6.65, w: 12.2, h: 0.5, fontFace: F.body, fontSize: 11, italic: true, color: C.slate, margin: 0 });
    pageFooter(s, 9, false);
  }

  // =================================================================
  // SLIDE — PRICING (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Тарифы");
    kicker(s, "Ориентировочные цены · фиксируются по итогам первого платного пилота");

    const tiers = [
      { name: "Пилот", price: "60 млн сум", usd: "≈ $5 000", per: "разово, 4–6 недель",
        items: ["1 перекрёсток", "калибровка камеры", "анализ записей и события",
                "отчёт с доказательными клипами", "презентация результатов"], hi: false },
      { name: "Подписка «Базовый»", price: "1,5 млн сум", usd: "≈ $125", per: "в месяц за перекрёсток",
        items: ["анализ пиковых часов", "дашборд и лента конфликтов", "ежемесячный отчёт по риску",
                "доказательные клипы критичных событий", "договор от 12 месяцев"], hi: true },
      { name: "Подписка «Полный»", price: "3 млн сум", usd: "≈ $250", per: "в месяц за перекрёсток",
        items: ["непрерывный анализ", "все события с клипами", "выгрузка данных и API",
                "приоритетная поддержка", "от 50 перекрёстков — 1 млн сум"], hi: false },
    ];
    const cw = 3.95, y0 = 1.72, ch = 4.0;
    tiers.forEach((t, i) => {
      const x = 0.55 + i * (cw + 0.2);
      s.addShape("roundRect", { x, y: y0, w: cw, h: ch,
        fill: { color: t.hi ? C.dark : C.ice }, rectRadius: 0.1 });
      if (t.hi) {
        s.addShape("roundRect", { x: x + cw - 1.75, y: y0 + 0.22, w: 1.5, h: 0.34,
          fill: { color: C.amber }, rectRadius: 0.17 });
        s.addText("ОСНОВНОЙ", { x: x + cw - 1.75, y: y0 + 0.22, w: 1.5, h: 0.34, align: "center",
          valign: "middle", fontFace: F.body, fontSize: 9, bold: true, color: C.ink, margin: 0 });
      }
      s.addText(t.name, { x: x + 0.28, y: y0 + 0.24, w: cw - 2.0, h: 0.35,
        fontFace: F.head, fontSize: 13.5, bold: true, color: t.hi ? C.amber : C.ink, margin: 0 });
      s.addText(t.price, { x: x + 0.28, y: y0 + 0.68, w: cw - 0.56, h: 0.55,
        fontFace: F.head, fontSize: 24, bold: true, color: t.hi ? C.light : C.ink, margin: 0 });
      s.addText(t.usd + "  ·  " + t.per, { x: x + 0.28, y: y0 + 1.22, w: cw - 0.56, h: 0.3,
        fontFace: F.body, fontSize: 10.5, color: t.hi ? "8EA0B5" : C.slate, margin: 0 });
      s.addShape("rect", { x: x + 0.28, y: y0 + 1.6, w: cw - 0.56, h: 0.012,
        fill: { color: t.hi ? "3A4A62" : C.iceLine } });
      s.addText(t.items.map((it, k) => ({ text: it, options: { bullet: { code: "2022", indent: 11 },
        breakLine: k < t.items.length - 1, paraSpaceAfter: 7 } })), {
        x: x + 0.28, y: y0 + 1.78, w: cw - 0.56, h: 2.0, fontFace: F.body, fontSize: 11,
        color: t.hi ? "D5DEE9" : C.slate, margin: 0, valign: "top" });
    });

    // extra services strip
    const extras = [
      ["Проект «до / после»", "от 90 млн сум · ≈ $7 500 за объект"],
      ["Городской аудит", "от 300 млн сум · ≈ $25 000 за 30–50 перекрёстков"],
      ["Интеграция и обучение", "по объёму работ"],
    ];
    const ew = 3.95;
    extras.forEach(([h, p], i) => {
      const x = 0.55 + i * (ew + 0.2), y = 5.95;
      s.addShape("roundRect", { x, y, w: ew, h: 0.72, fill: { color: C.light },
        line: { color: C.iceLine, width: 1 }, rectRadius: 0.08 });
      s.addText(h, { x: x + 0.22, y: y + 0.09, w: ew - 0.44, h: 0.28,
        fontFace: F.head, fontSize: 11.5, bold: true, color: C.ink, margin: 0 });
      s.addText(p, { x: x + 0.22, y: y + 0.37, w: ew - 0.44, h: 0.28,
        fontFace: F.body, fontSize: 10.5, color: C.slate, margin: 0 });
    });

    s.addText("Расчёт при курсе около 11 900 сум за доллар. Цены — рабочая гипотеза: себестоимость подключения перекрёстка станет известна после первого пилота.", {
      x: 0.55, y: 6.85, w: 12.2, h: 0.4, fontFace: F.body, fontSize: 10, italic: true, color: C.slate, margin: 0 });
    pageFooter(s, 0, false);
  }

  // =================================================================
  // SLIDE 8c — UNIT ECONOMICS (dark)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.dark };
    title(s, "Почему модель масштабируется", { color: C.light });
    kicker(s, "Экономика одной камеры", { color: "8EA0B5" });

    const cols = [
      ["Что стоит денег сейчас", [
        "Калибровка камеры — ручная работа инженера",
        "Вычисления на анализ видео",
        "Хранение доказательных клипов",
        "Экспертная проверка событий на пилоте",
      ], C.dark2, C.light],
      ["Что снижается с масштабом", [
        "Калибровка — полуавтоматическая по разметке",
        "Пакетная обработка пиковых часов вместо 24/7",
        "Хранятся траектории и метаданные, не всё видео",
        "Проверка выборочная после валидации порогов",
      ], C.dark2, C.light],
      ["Что остаётся неизменным", [
        "Подписка за каждый подключённый перекрёсток",
        "Один и тот же движок на всех камерах",
        "Каждый новый город — те же алгоритмы",
      ], "2A3B24", C.light],
    ];
    const cw = 3.95;
    cols.forEach(([h, items, bg, tc], i) => {
      const x = 0.55 + i * (cw + 0.2);
      s.addShape("roundRect", { x, y: 1.75, w: cw, h: 3.5, fill: { color: bg }, rectRadius: 0.1 });
      s.addText(h, { x: x + 0.28, y: 1.98, w: cw - 0.56, h: 0.4,
        fontFace: F.head, fontSize: 13.5, bold: true, color: i === 2 ? C.green : C.amber, margin: 0 });
      s.addText(items.map((t, k) => ({ text: t, options: { bullet: { code: "2022", indent: 11 },
        breakLine: k < items.length - 1, paraSpaceAfter: 8 } })), {
        x: x + 0.28, y: 2.48, w: cw - 0.56, h: 2.6, fontFace: F.body, fontSize: 11, color: "D5DEE9", margin: 0, valign: "top" });
    });

    s.addShape("roundRect", { x: 0.55, y: 5.5, w: 12.2, h: 1.15, fill: { color: C.dark2 }, rectRadius: 0.1 });
    s.addText([
      { text: "Ключевая метрика для инвестора: ", options: { bold: true, color: C.amber } },
      { text: "стоимость подключения одного нового перекрёстка. Пока она измеряется днями инженера — бизнес проектный. Когда падает до часов — начинается настоящий SaaS. Именно на это направлена автоматизация калибровки в дорожной карте.", options: { color: "D5DEE9" } },
    ], { x: 0.9, y: 5.68, w: 11.5, h: 0.85, fontFace: F.body, fontSize: 12, valign: "middle", margin: 0 });
    pageFooter(s, 10, true);
  }

  // =================================================================
  // SLIDE — FINANCIAL PROJECTION (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Финансовый прогноз");
    kicker(s, "Консервативный сценарий · выручка по годам");

    const years = [
      { y: "2027", sum: "0,55 млрд сум", usd: "≈ $46 000", h: 0.9,
        parts: "2 платных пилота · 15 перекрёстков подписки · 1 городской аудит" },
      { y: "2028", sum: "1,8 млрд сум", usd: "≈ $151 000", h: 2.2,
        parts: "60 перекрёстков подписки · 3 проекта «до/после» · 2 аудита" },
      { y: "2029", sum: "4,1 млрд сум", usd: "≈ $343 000", h: 3.5,
        parts: "200 перекрёстков подписки · проекты и аудиты в областях" },
    ];
    const baseY = 5.55, bw = 1.5;
    years.forEach((yr, i) => {
      const x = 1.1 + i * 2.4;
      s.addShape("roundRect", { x, y: baseY - yr.h, w: bw, h: yr.h,
        fill: { color: i === 2 ? C.amber : (i === 1 ? C.amberDeep : C.iceLine) }, rectRadius: 0.06 });
      s.addText(yr.sum, { x: x - 0.45, y: baseY - yr.h - 0.72, w: bw + 0.9, h: 0.34, align: "center",
        fontFace: F.head, fontSize: 13, bold: true, color: C.ink, margin: 0 });
      s.addText(yr.usd, { x: x - 0.45, y: baseY - yr.h - 0.4, w: bw + 0.9, h: 0.3, align: "center",
        fontFace: F.body, fontSize: 11, color: C.slate, margin: 0 });
      s.addText(yr.y, { x: x - 0.45, y: baseY + 0.12, w: bw + 0.9, h: 0.34, align: "center",
        fontFace: F.head, fontSize: 15, bold: true, color: C.ink, margin: 0 });
    });
    s.addShape("rect", { x: 0.85, y: baseY, w: 7.0, h: 0.014, fill: { color: C.iceLine } });

    // right column: what drives it
    const rx = 8.35, rw = 4.4;
    s.addShape("roundRect", { x: rx, y: 1.72, w: rw, h: 4.55, fill: { color: C.ice }, rectRadius: 0.1 });
    s.addText("Из чего складывается", { x: rx + 0.3, y: 1.96, w: rw - 0.6, h: 0.36,
      fontFace: F.head, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    let ly = 2.45;
    years.forEach((yr) => {
      s.addText(yr.y, { x: rx + 0.3, y: ly, w: 0.9, h: 0.3, fontFace: F.head, fontSize: 12,
        bold: true, color: C.amberDeep, margin: 0 });
      s.addText(yr.parts, { x: rx + 0.3, y: ly + 0.28, w: rw - 0.6, h: 0.95,
        fontFace: F.body, fontSize: 11, color: C.slate, margin: 0 });
      ly += 1.35;
    });

    s.addText([
      { text: "Это не хоккейная клюшка. ", options: { bold: true } },
      { text: "Государственные закупки идут медленно, поэтому в модель заложен реальный темп: один город, затем области. Ускорение возможно после публичного отчёта о точности — он снимает главный барьер доверия.", options: {} },
    ], { x: 0.55, y: 6.35, w: 12.2, h: 0.75, fontFace: F.body, fontSize: 11.5, color: C.ink, margin: 0 });
    pageFooter(s, 0, false);
  }

  // =================================================================
  // SLIDE — MARKET LESSONS (dark)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.dark };
    title(s, "Уроки рынка: разбор чужих кейсов", { color: C.light });
    kicker(s, "Мы изучили всех, кто делал near-miss аналитику до нас", { color: "8FA2B8" });

    const cases = [
      ["MicroTraffic", "Куплена Miovision, 2023", "Лидер именно near-miss аналитики — поглощён платформой, у которой уже стояли камеры"],
      ["Brisk Synergies", "Куплена Transoft", "Технология сильная, канал продаж — чужой"],
      ["Waycare", "Куплена Rekor за $61 млн", "Покупатель к 2026 г. — в предбанкротном состоянии"],
      ["Hayden AI", "Выручка ~$20k/камера/год", "Единственная растущая: платят не из бюджета развития, а из штрафов"],
    ];
    const cwS = 2.98, chS = 2.05;
    cases.forEach((c, i) => {
      const x = 0.55 + i * (cwS + 0.13);
      s.addShape("roundRect", { x, y: 1.68, w: cwS, h: chS, fill: { color: C.dark2 }, rectRadius: 0.08 });
      s.addText(c[0], { x: x + 0.25, y: 1.85, w: cwS - 0.5, h: 0.36, fontFace: F.head, fontSize: 15, bold: true, color: C.light, margin: 0 });
      s.addText(c[1], { x: x + 0.25, y: 2.22, w: cwS - 0.5, h: 0.34, fontFace: F.body, fontSize: 11.5, bold: true, color: i === 3 ? C.green : C.amber, margin: 0 });
      s.addText(c[2], { x: x + 0.25, y: 2.62, w: cwS - 0.5, h: 1.0, fontFace: F.body, fontSize: 11, color: "9FB0C4", margin: 0 });
    });

    s.addShape("roundRect", { x: 0.55, y: 4.05, w: 12.2, h: 1.02, fill: { color: "24344B" }, rectRadius: 0.08 });
    s.addText([
      { text: "Независимых выживших: 0 из 4.  ", options: { bold: true, color: C.amber } },
      { text: "«Near-miss аналитика» — это метод, а не бизнес-модель. Бизнес строится вокруг того, за что государство уже обязано платить.", options: { color: "D5DEE9" } },
    ], { x: 0.9, y: 4.15, w: 11.5, h: 0.82, fontFace: F.body, fontSize: 13.5, valign: "middle", margin: 0 });

    const lessons = [
      "Категории «near-miss» в бюджете не существует — закупка идёт как ИТС или общественная безопасность",
      "Выживает тот, кому платит не бюджет развития: штрафы, гранты, деньги банков развития",
      "Пилот — не продажа, а юридическое основание для закупки без тендера",
    ];
    let ly = 5.35;
    lessons.forEach((t) => {
      s.addShape("ellipse", { x: 0.62, y: ly + 0.07, w: 0.13, h: 0.13, fill: { color: C.amber } });
      s.addText(t, { x: 0.95, y: ly - 0.03, w: 11.8, h: 0.42, fontFace: F.body, fontSize: 12.5, color: "B8C6D6", margin: 0 });
      ly += 0.5;
    });
    pageFooter(s, 0, true);
  }

  // =================================================================
  // SLIDE — GO-TO-MARKET STRATEGY (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Стратегия выхода на рынок");
    kicker(s, "Не продавать ИИ — стать оператором обязательной государственной функции");

    const hor = [
      ["0–12 мес.", "Услуга, а не софт", "Продукт — «Аудит безопасности перекрёстка»: отчёт, ранжирование опасных мест, видеодоказательства. Услугу госзаказчику купить быстрее, чем подписку на ПО.", "Результат: первый платящий заказчик + отчёт о точности, проверенный независимым экспертом"],
      ["12–30 мес.", "Подписка поверх доказанной точности", "Переход аудитов в годовую подписку, «до/после» под каждую реконструкцию, включение методики в нормативные документы и реестр отечественного ПО.", "Результат: регуляторное встраивание + первый заказчик за пределами Узбекистана через партнёра"],
      ["30–60 мес.", "Инфраструктура, а не подрядчик", "Национальная платформа мониторинга индекса «Безопасная дорога»; обезличенные данные как продукт для страховых, проектировщиков и банков развития.", "Результат: экспорт в страны с тем же профилем — камеры есть, смертность высокая, есть донорские деньги"],
    ];
    let hy = 1.72;
    hor.forEach(([per, name, body, out], i) => {
      s.addShape("roundRect", { x: 0.55, y: hy, w: 12.2, h: 1.3, fill: { color: C.ice }, rectRadius: 0.08 });
      s.addShape("roundRect", { x: 0.55, y: hy, w: 0.09, h: 1.3, fill: { color: i === 0 ? C.amber : (i === 1 ? C.amberDeep : C.slate) }, rectRadius: 0.03 });
      s.addText(per, { x: 0.85, y: hy + 0.14, w: 1.55, h: 0.3, fontFace: F.head, fontSize: 12.5, bold: true, color: C.amberDeep, margin: 0 });
      s.addText(name, { x: 0.85, y: hy + 0.46, w: 3.6, h: 0.7, fontFace: F.head, fontSize: 14, bold: true, color: C.ink, margin: 0 });
      s.addText(body, { x: 4.7, y: hy + 0.14, w: 5.1, h: 1.02, fontFace: F.body, fontSize: 11, color: C.slate, margin: 0 });
      s.addText(out, { x: 10.0, y: hy + 0.14, w: 2.6, h: 1.02, fontFace: F.body, fontSize: 10, color: C.ink, italic: true, margin: 0 });
      hy += 1.42;
    });

    s.addShape("roundRect", { x: 0.55, y: hy + 0.06, w: 12.2, h: 1.02, fill: { color: C.dark }, rectRadius: 0.08 });
    s.addText("Что реально защищает бизнес", { x: 0.9, y: hy + 0.16, w: 4.0, h: 0.3, fontFace: F.head, fontSize: 12.5, bold: true, color: C.amber, margin: 0 });
    s.addText([
      { text: "1) Регуляторное встраивание методики  •  2) Валидированный датасет Центральной Азии  •  3) Исторические ряды «до/после».  ", options: { color: "D5DEE9" } },
      { text: "Алгоритмы моатом не являются — и мы этого не утверждаем.", options: { color: C.amber, bold: true } },
    ], { x: 0.9, y: hy + 0.48, w: 11.5, h: 0.5, fontFace: F.body, fontSize: 11.5, margin: 0 });
    pageFooter(s, 0, false);
  }

  // =================================================================
  // SLIDE 9 — COMPETITION (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Чем мы отличаемся");
    kicker(s, "Ниша: превентивная аналитика, а не штрафы и не записи");

    const rowsC = [
      ["Штрафные камеры (радары, «Автоураган»)", "Фиксируют нарушение после факта; не видят near-miss и не ранжируют инфраструктурный риск"],
      ["Детекция аварий / инцидент-менеджмент", "Реагируют, когда авария уже произошла — это скорая помощь, а не профилактика"],
      ["Generic smart-city платформы", "Подсчёт трафика и загруженность; нет физики конфликтов, нет доказательной безопасности"],
    ];
    let cy = 1.7;
    rowsC.forEach(([h, t]) => {
      s.addShape("roundRect", { x: 0.55, y: cy, w: 12.2, h: 1.0, fill: { color: C.ice }, rectRadius: 0.08 });
      s.addText(h, { x: 0.85, y: cy + 0.12, w: 4.6, h: 0.8, fontFace: F.head, fontSize: 13, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(t, { x: 5.6, y: cy + 0.12, w: 6.9, h: 0.8, fontFace: F.body, fontSize: 12, color: C.slate, valign: "middle", margin: 0 });
      cy += 1.12;
    });

    s.addShape("roundRect", { x: 0.55, y: cy + 0.1, w: 12.2, h: 1.55, fill: { color: C.dark }, rectRadius: 0.08 });
    iconCircle(s, "shield", 0.9, cy + 0.42, 0.9);
    s.addText([
      { text: "SafeRoad AI: ", options: { bold: true, color: C.amber } },
      { text: "единственный фокус — предсказать место следующей аварии по наблюдаемому поведению. Объяснимая физика вместо чёрного ящика, доказательные клипы вместо голых скорингов, приватность по построению — без распознавания лиц и номеров.", options: { color: "D5DEE9" } },
    ], { x: 2.1, y: cy + 0.25, w: 10.4, h: 1.25, fontFace: F.body, fontSize: 13, valign: "middle", margin: 0 });
    pageFooter(s, 11, false);
  }

  // =================================================================
  // SLIDE 10 — DISCIPLINE / TRUST (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Инженерная дисциплина = доверие государства");
    kicker(s, "Система спроектирована под аудит, а не под демо");

    const cards = [
      ["cog", "Детерминированная физика", "TTC/PET/скорости считает математика с юнит-тестами; у каждой метрики — единицы и оценка погрешности. LLM не принимает решений."],
      ["check", "Валидация до заявлений", "«Золотой набор» размеченных экспертами клипов; publish: точность, полнота, ошибка скорости. Экспериментальные пороги всегда помечены."],
      ["eye", "Полная объяснимость", "У каждого события — reason codes и видеодоказательство: инженер может проверить и опровергнуть любой вывод системы."],
      ["lock", "Приватность по построению", "Без распознавания лиц и номеров; хранятся траектории и метаданные, а не персональные данные. Ролевой доступ, журнал аудита."],
    ];
    const cw4 = 6.0, ch4 = 2.15;
    cards.forEach((c, i) => {
      const x = 0.55 + (i % 2) * (cw4 + 0.23);
      const y = 1.7 + Math.floor(i / 2) * (ch4 + 0.3);
      s.addShape("roundRect", { x, y, w: cw4, h: ch4, fill: { color: C.ice }, rectRadius: 0.08 });
      iconCircle(s, c[0], x + 0.28, y + 0.3, 0.58);
      s.addText(c[1], { x: x + 1.05, y: y + 0.33, w: cw4 - 1.3, h: 0.52, fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(c[2], { x: x + 0.28, y: y + 1.0, w: cw4 - 0.56, h: 1.05, fontFace: F.body, fontSize: 11.5, color: C.slate, margin: 0 });
    });
    pageFooter(s, 12, false);
  }

  // =================================================================
  // SLIDE — RISKS (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Риски и как мы их снижаем");
    kicker(s, "То, о чём спросит любой технически грамотный инвестор");

    const rows = [
      ["Точность на реальном видео", "Система проверена на сценах с известной истиной, но не на реальном перекрёстке.",
       "Пилот с экспертной разметкой и публичный отчёт precision / recall до любых заявлений о точности."],
      ["Качество городского видео", "Низкий FPS, переменная частота кадров, ночь и дождь ломают измерения.",
       "Модуль инжеста отклоняет непригодное видео с явной причиной; критерии отбора камер зафиксированы."],
      ["Доступ к государственным камерам", "Согласование доступа к CCTV может занять месяцы.",
       "Пилот не требует интеграции: достаточно записей с одной камеры или собственной съёмки."],
      ["Регуляторика и приватность", "Работа с городским видео — чувствительная тема.",
       "Без распознавания лиц и номеров by design; хранятся траектории и метаданные, а не архив видео."],
      ["Длинный цикл госзакупок", "Бюджеты планируются на год вперёд, решения принимаются медленно.",
       "Дешёвый входной пилот вместо крупного контракта; параллельно областные центры и экспорт."],
    ];
    let y = 1.72;
    rows.forEach(([h, risk, fix], i) => {
      s.addShape("roundRect", { x: 0.55, y, w: 12.2, h: 0.92,
        fill: { color: i % 2 ? C.light : C.ice }, rectRadius: 0.06 });
      s.addText(h, { x: 0.85, y: y + 0.14, w: 3.1, h: 0.64, fontFace: F.head, fontSize: 12,
        bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(risk, { x: 4.1, y: y + 0.14, w: 4.0, h: 0.64, fontFace: F.body, fontSize: 10.5,
        color: C.red, valign: "middle", margin: 0 });
      s.addText(fix, { x: 8.3, y: y + 0.14, w: 4.2, h: 0.64, fontFace: F.body, fontSize: 10.5,
        color: C.slate, valign: "middle", margin: 0 });
      y += 1.0;
    });
    s.addText("Риск                                          Как снижаем", {
      x: 4.1, y: 1.42, w: 8.4, h: 0.26, fontFace: F.body, fontSize: 9.5, bold: true,
      color: C.slate, charSpacing: 1, margin: 0 });
    pageFooter(s, 0, false);
  }

  // =================================================================
  // SLIDE 11 — ROADMAP (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Дорожная карта");
    kicker(s, "Сначала доверие к одной камере — потом масштаб");

    const stages = [
      ["Q4 2026", "MVP", "Полный конвейер на одном перекрёстке: видео → события → доказательства → дашборд", C.amber],
      ["Q1 2027", "Пилот", "Реальный перекрёсток с хокимиятом/СБДД; экспертная разметка, «золотой набор»", C.amber],
      ["Q2 2027", "Валидация", "Публичный отчёт точности: precision/recall событий, ошибка скорости, до/после", C.amberDeep],
      ["H2 2027", "Город", "10+ перекрёстков, рейтинг риска, интеграция с процессами дорожных служб", C.dark],
      ["2028", "Платформа", "Городской центр безопасности; экспорт в Центральную Азию", C.dark],
    ];
    const bw2 = 2.32, gap2 = 0.16, x0 = 0.55, ty = 2.3;
    // connecting line
    s.addShape("line", { x: x0 + 0.3, y: ty - 0.28, w: (bw2 + gap2) * 4, h: 0, line: { color: C.iceLine, width: 2 } });
    stages.forEach((st, i) => {
      const x = x0 + i * (bw2 + gap2);
      s.addShape("ellipse", { x: x + 0.18, y: ty - 0.4, w: 0.24, h: 0.24, fill: { color: st[3] } });
      s.addText(st[0], { x, y: ty + 0.0, w: bw2, h: 0.3, fontFace: F.body, fontSize: 11, bold: true, color: C.slate, margin: 0 });
      s.addShape("roundRect", { x, y: ty + 0.35, w: bw2, h: 2.6, fill: { color: i < 3 ? C.ice : C.dark }, rectRadius: 0.08 });
      s.addText(st[1], { x: x + 0.16, y: ty + 0.5, w: bw2 - 0.32, h: 0.42, fontFace: F.head, fontSize: 15, bold: true, color: i < 3 ? C.ink : C.amber, margin: 0 });
      s.addText(st[2], { x: x + 0.16, y: ty + 0.95, w: bw2 - 0.32, h: 1.9, fontFace: F.body, fontSize: 10.5, color: i < 3 ? C.slate : "C7D2E0", margin: 0 });
    });

    s.addText("Принцип последовательности: город не масштабируется, пока точность на одном перекрёстке не подтверждена независимой разметкой.", {
      x: 0.55, y: 5.7, w: 12.2, h: 0.5, fontFace: F.body, fontSize: 12.5, italic: true, color: C.ink, margin: 0,
    });
    pageFooter(s, 13, false);
  }

  // =================================================================
  // SLIDE — TEAM (light)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Команда");
    kicker(s, "Кто делает продукт и кого нанимаем на пилот");

    const people = [
      { role: "Основатель, продукт и разработка", name: "Джавохир", now: true,
        note: "Архитектура системы, конвейер компьютерного зрения, дашборд. Довёл MVP до полного цикла: видео → события → доказательства." },
      { role: "Инженер компьютерного зрения", name: "Открытая позиция", now: false,
        note: "Трекинг, калибровка, качество детекции на реальных записях. Ключевой найм на этапе пилота." },
      { role: "Инженер по данным и валидации", name: "Открытая позиция", now: false,
        note: "Золотой набор, экспертная разметка событий, отчёт о точности — то, что делает заявления проверяемыми." },
      { role: "Советник по дорожной безопасности", name: "Ищем", now: false,
        note: "Дорожный инженер или специалист СБДД: проверка методологии и выход на пилотный перекрёсток." },
    ];
    const cw = 3.0, gap = 0.18;
    people.forEach((p, i) => {
      const x = 0.55 + i * (cw + gap);
      s.addShape("roundRect", { x, y: 1.72, w: cw, h: 3.85,
        fill: { color: p.now ? C.dark : C.ice }, rectRadius: 0.1 });
      s.addShape("ellipse", { x: x + 0.28, y: 1.98, w: 0.62, h: 0.62,
        fill: { color: p.now ? C.amber : C.iceLine } });
      s.addText(p.now ? "Д" : "+", { x: x + 0.28, y: 1.98, w: 0.62, h: 0.62, align: "center",
        valign: "middle", fontFace: F.head, fontSize: 20, bold: true,
        color: p.now ? C.ink : C.slate, margin: 0 });
      s.addText(p.name, { x: x + 0.28, y: 2.75, w: cw - 0.56, h: 0.34,
        fontFace: F.head, fontSize: 14, bold: true, color: p.now ? C.light : C.ink, margin: 0 });
      s.addText(p.role, { x: x + 0.28, y: 3.09, w: cw - 0.56, h: 0.55,
        fontFace: F.body, fontSize: 11, bold: true, color: p.now ? C.amber : C.amberDeep, margin: 0 });
      s.addText(p.note, { x: x + 0.28, y: 3.72, w: cw - 0.56, h: 1.6,
        fontFace: F.body, fontSize: 10.5, color: p.now ? "C7D2E0" : C.slate, margin: 0 });
    });

    s.addShape("roundRect", { x: 0.55, y: 5.85, w: 12.2, h: 1.0, fill: { color: C.ice }, rectRadius: 0.08 });
    s.addText([
      { text: "Что уже сделано силами одного человека: ", options: { bold: true } },
      { text: "полный конвейер от инжеста видео до объяснимых near-miss событий с доказательными клипами и дашбордом, 67 автоматических тестов, техническая документация и открытая методология. Финансирование нужно, чтобы превратить это в проверенный на реальной дороге продукт.", options: {} },
    ], { x: 0.9, y: 6.02, w: 11.5, h: 0.7, fontFace: F.body, fontSize: 11.5, color: C.ink, valign: "middle", margin: 0 });
    pageFooter(s, 0, false);
  }

  // =================================================================
  // SLIDE — ASK (dark)
  // =================================================================
  {
    const s = pres.addSlide();
    s.background = { color: C.dark };
    for (let i = 0; i < 6; i++) {
      s.addShape("rect", { x: 1.0 + i * 2.1, y: 7.05, w: 1.0, h: 0.07, fill: { color: C.amber, transparency: 78 } });
    }
    s.addText("Что мы просим", {
      x: 0.8, y: 0.55, w: 11.7, h: 0.75, fontFace: F.head, fontSize: 32, bold: true, color: C.light, margin: 0 });
    s.addText("РАУНД НА 12 МЕСЯЦЕВ ДО ВАЛИДИРОВАННОГО ПИЛОТА", {
      x: 0.8, y: 1.28, w: 11.7, h: 0.32, fontFace: F.body, fontSize: 12, color: "8EA0B5", charSpacing: 2, margin: 0 });

    // headline amount
    s.addShape("roundRect", { x: 0.8, y: 1.85, w: 5.0, h: 2.25, fill: { color: C.dark2 },
      line: { color: C.amber, width: 1.5 }, rectRadius: 0.12 });
    s.addText("1,4 млрд сум", { x: 1.1, y: 2.12, w: 4.4, h: 0.75,
      fontFace: F.head, fontSize: 34, bold: true, color: C.amber, margin: 0 });
    s.addText("≈ $120 000 · 12 месяцев", { x: 1.1, y: 2.9, w: 4.4, h: 0.35,
      fontFace: F.body, fontSize: 13, color: C.light, margin: 0 });
    s.addText("До результата: работающий пилот на реальном перекрёстке и публичный отчёт о точности.", {
      x: 1.1, y: 3.3, w: 4.4, h: 0.7, fontFace: F.body, fontSize: 11, color: "8EA0B5", margin: 0 });

    // budget split
    const budget = [
      ["Команда: 2 инженера + разметчик", "70%", "≈ $84 000", 3.5],
      ["Вычисления, хранение, оборудование", "10%", "≈ $12 000", 0.5],
      ["Разметка данных и валидация", "10%", "≈ $12 000", 0.5],
      ["Пилотные расходы, юридическое, поездки", "10%", "≈ $12 000", 0.5],
    ];
    let by = 1.95;
    budget.forEach(([h, pct, usd, barW]) => {
      s.addText(h, { x: 6.2, y: by, w: 4.0, h: 0.3, fontFace: F.body, fontSize: 11.5, color: C.light, margin: 0 });
      s.addText(pct + "  ·  " + usd, { x: 10.3, y: by, w: 2.4, h: 0.3, align: "right",
        fontFace: F.body, fontSize: 11.5, bold: true, color: C.amber, margin: 0 });
      s.addShape("rect", { x: 6.2, y: by + 0.32, w: 6.5, h: 0.09, fill: { color: "2A3A52" } });
      s.addShape("rect", { x: 6.2, y: by + 0.32, w: 6.5 * (barW / 5), h: 0.09, fill: { color: C.amber } });
      by += 0.62;
    });

    // three asks
    const asks = [
      ["users", "Пилотный партнёр", "Хокимият или СБДД: один перекрёсток и доступ к записям камеры"],
      ["rocket", "Инвестиции в пилот", "1,4 млрд сум на 12 месяцев до валидированного результата"],
      ["shield", "Государственный трек", "Заявка на President AI Award с работающим MVP и данными пилота"],
    ];
    const aw = 3.95;
    asks.forEach((a, i) => {
      const x = 0.8 + i * (aw + 0.2), y = 4.45;
      s.addShape("roundRect", { x, y, w: aw, h: 1.85, fill: { color: C.dark2 }, rectRadius: 0.1 });
      iconCircle(s, a[0], x + 0.28, y + 0.26, 0.5);
      s.addText(a[1], { x: x + 0.9, y: y + 0.3, w: aw - 1.2, h: 0.42, fontFace: F.head,
        fontSize: 13.5, bold: true, color: C.amber, valign: "middle", margin: 0 });
      s.addText(a[2], { x: x + 0.28, y: y + 0.92, w: aw - 0.56, h: 0.8,
        fontFace: F.body, fontSize: 11, color: "C7D2E0", margin: 0 });
    });

    s.addText("SafeRoad AI · Джавохир · stuffdealerog@gmail.com", {
      x: 0.8, y: 6.5, w: 11.7, h: 0.35, fontFace: F.body, fontSize: 13, color: "8EA0B5", margin: 0 });
    pageFooter(s, 0, true);
  }

  await pres.writeFile({ fileName: "/home/user/saferoad/deck/SafeRoad_AI_Pitch_Deck.pptx" });
  console.log("done");
})().catch((e) => { console.error(e); process.exit(1); });
