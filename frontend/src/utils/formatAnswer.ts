/**
 * Format numbers with Indian numbering system (lakhs/crores) or international.
 */
export function formatNumber(value: number | string): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return String(value);
  if (Math.abs(num) >= 1e7) return `${(num / 1e7).toFixed(2)}Cr`;
  if (Math.abs(num) >= 1e5) return `${(num / 1e5).toFixed(2)}L`;
  if (Math.abs(num) >= 1e3) return num.toLocaleString("en-IN");
  return num.toFixed(num % 1 === 0 ? 0 : 2);
}

/**
 * Bold **text** markdown segments.
 */
export function parseBold(text: string): Array<{ bold: boolean; text: string }> {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  return parts.map((part) => ({
    bold: part.startsWith("**") && part.endsWith("**"),
    text: part.startsWith("**") && part.endsWith("**") ? part.slice(2, -2) : part,
  }));
}
