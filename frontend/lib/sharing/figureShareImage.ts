import { figureSourceText, SHARE_CARD_COLORS as colors, SHARE_CARD_SITE, type PublicFigureShareData } from './figureShare';

const WIDTH = 1080;
const PADDING = 64;
const LINE_WIDTH = WIDTH - 2 * PADDING;
const MAX_HEIGHT = 4096;
const MAX_VALUE_SIZE = 112;
const MIN_VALUE_SIZE = 56;

/** Keep paragraphs and wrap complete words first, then break long individual tokens. */
function wrapText(context: CanvasRenderingContext2D, text: string) {
  const rows: string[] = [];
  for (const paragraph of text.split(/\r\n?|\n/)) {
    let line = '';
    for (const token of paragraph.match(/\S+|\s+/g) ?? []) {
      if (context.measureText(line + token).width <= LINE_WIDTH) {
        line += token;
      } else {
        if (line.trim()) rows.push(line.trimEnd());
        line = '';
        if (!token.trim()) continue;
        for (const glyph of Array.from(token)) {
          if (line && context.measureText(line + glyph).width > LINE_WIDTH) {
            rows.push(line);
            line = '';
          }
          line += glyph;
        }
      }
    }
    rows.push(line.trimEnd());
  }
  return rows;
}

export async function createPublicFigurePng(figure: PublicFigureShareData, fonts: { body: string; display: string }) {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  const surface = canvas.getContext('2d');
  if (!surface) throw new Error('Canvas unavailable');
  const context = surface;

  const metricFont = `600 48px ${fonts.body}`;
  const preferredValueFont = `600 ${MAX_VALUE_SIZE}px ${fonts.display}`;
  const receiptFont = `400 34px ${fonts.body}`;
  const receipt = `${figureSourceText(figure)} · ${SHARE_CARD_SITE}`;
  if (document.fonts) {
    await Promise.all([
      document.fonts.load(metricFont, figure.metric),
      document.fonts.load(preferredValueFont, figure.value),
      document.fonts.load(receiptFont, receipt),
    ]);
  }

  context.font = metricFont;
  const metric = wrapText(context, figure.metric);
  // Keep a wide numeric value together when it still fits at a readable size.
  context.font = preferredValueFont;
  const valueWidth = figure.value.split(/\r\n?|\n/).reduce(
    (max, line) => Math.max(max, context.measureText(line).width), 1
  );
  const valueSize = Math.max(MIN_VALUE_SIZE, Math.min(MAX_VALUE_SIZE, Math.floor(MAX_VALUE_SIZE * LINE_WIDTH / valueWidth)));
  const valueFont = `600 ${valueSize}px ${fonts.display}`;
  const valueLineHeight = Math.ceil(valueSize * 1.18);
  context.font = valueFont;
  const values = wrapText(context, figure.value);
  context.font = receiptFont;
  const sources = wrapText(context, receipt);
  canvas.height = PADDING * 2 + metric.length * 62 + values.length * valueLineHeight + sources.length * 46 + 92;
  if (canvas.height > MAX_HEIGHT) throw new Error('Share image exceeds the canvas height limit');

  context.fillStyle = colors.paper;
  context.fillRect(0, 0, WIDTH, canvas.height);
  context.fillStyle = colors.accent;
  context.fillRect(0, 0, WIDTH, 8);
  context.textBaseline = 'top';

  let y = PADDING;
  function draw(rows: string[], font: string, color: string, lineHeight: number) {
    context.font = font;
    context.fillStyle = color;
    for (const line of rows) {
      context.fillText(line, PADDING, y);
      y += lineHeight;
    }
  }
  draw(metric, metricFont, colors.ink, 62);
  y += 14;
  draw(values, valueFont, colors.ink, valueLineHeight);
  y += 30;
  context.fillStyle = colors.rule;
  context.fillRect(PADDING, y, LINE_WIDTH, 2);
  y += 30;
  draw(sources, receiptFont, colors.muted, 46);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(blob => {
      if (blob) resolve(blob);
      else reject(new Error('PNG unavailable'));
    }, 'image/png');
  });
}
