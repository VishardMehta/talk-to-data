import type { ChartType } from "@/types";

export type { ChartType };

export function selectChartType(
  question: string,
  rowCount: number,
  colCount: number
): ChartType {
  const q = question.toLowerCase();

  if (rowCount === 0) return "stat_card";
  if (rowCount === 1 && colCount === 1) return "stat_card";
  if (rowCount === 1) return "stat_card";

  if (q.match(/trend|over time|monthly|yearly|daily|weekly|growth|history/))
    return "line";
  if (q.match(/percent|proportion|share|breakdown|composition|distribution by/))
    return "pie";
  if (q.match(/distribution|spread|range|frequency|histogram/))
    return "histogram";
  if (rowCount >= 2 && rowCount <= 15) return "bar";
  if (rowCount > 15) return "table";

  return "table";
}

export function inferKeys(
  data: Record<string, unknown>[],
  question: string
): { xKey: string; yKey: string; nameKey: string; valueKey: string } {
  if (!data || data.length === 0)
    return { xKey: "", yKey: "", nameKey: "", valueKey: "" };

  const keys = Object.keys(data[0]);
  const numericKeys = keys.filter((k) => typeof data[0][k] === "number");
  const stringKeys = keys.filter((k) => typeof data[0][k] === "string");

  const xKey = stringKeys[0] || keys[0] || "";
  const yKey = numericKeys[0] || keys[1] || "";

  return {
    xKey,
    yKey,
    nameKey: xKey,
    valueKey: yKey,
  };
}
