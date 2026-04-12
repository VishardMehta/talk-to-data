/**
 * Mock data used when the backend is offline.
 * Returns new QueryResult shape from @/types.
 */
import type { QueryResult } from "@/types";

const revenueByMonth: QueryResult = {
  question: "Show revenue trend",
  answer:
    "Revenue has grown **12.4% MoM** — March was the strongest month at ₹45.2L. The North region is the primary driver, contributing 41% of total revenue.",
  chart_type: "line",
  data: [
    { month: "Oct", revenue: 28.4 },
    { month: "Nov", revenue: 32.1 },
    { month: "Dec", revenue: 38.7 },
    { month: "Jan", revenue: 35.2 },
    { month: "Feb", revenue: 41.8 },
    { month: "Mar", revenue: 45.2 },
  ],
  x_key: "month",
  y_key: "revenue",
  table_name: "orders",
};

const regionBreakdown: QueryResult = {
  question: "Revenue by region",
  answer:
    "North dominates at ₹18.5L — nearly **2× the South region**. South is the only region showing a decline (-4%). Consider investigating complaint rates in the South.",
  chart_type: "bar",
  data: [
    { region: "North", revenue: 18.5 },
    { region: "East", revenue: 11.4 },
    { region: "South", revenue: 9.2 },
    { region: "West", revenue: 6.1 },
  ],
  x_key: "region",
  y_key: "revenue",
  table_name: "orders",
  follow_ups: [
    "Why is South declining?",
    "Compare East vs West",
    "Top cities in North region",
  ],
};

const topCities: QueryResult = {
  question: "Top 3 cities by orders",
  answer:
    "Mumbai leads with ₹8.3L, closely followed by Delhi. The top 3 cities alone account for **54% of total revenue**.",
  chart_type: "bar",
  data: [
    { city: "Mumbai", revenue: 8.3 },
    { city: "Delhi", revenue: 7.1 },
    { city: "Bangalore", revenue: 6.4 },
    { city: "Chennai", revenue: 4.2 },
    { city: "Hyderabad", revenue: 3.8 },
  ],
  x_key: "city",
  y_key: "revenue",
  table_name: "orders",
};

const categoryBreakdown: QueryResult = {
  question: "Category breakdown",
  answer:
    "Electronics dominates at **38% of revenue** — more than the next two categories combined. Books and Sports are underperforming; worth reviewing pricing strategy.",
  chart_type: "pie",
  data: [
    { name: "Electronics", value: 38 },
    { name: "Clothing", value: 24 },
    { name: "Home & Kitchen", value: 18 },
    { name: "Books", value: 11 },
    { name: "Sports", value: 9 },
  ],
  name_key: "name",
  value_key: "value",
  table_name: "products",
};

const totalRevenue: QueryResult = {
  question: "What is total revenue?",
  answer: "Total revenue for the period is **₹45.2L**, up 12.4% from the previous quarter.",
  chart_type: "stat_card",
  data: [{ metric: "Total Revenue", value: 45.2 }],
  x_key: "metric",
  y_key: "value",
  table_name: "orders",
};

const defaultResult: QueryResult = {
  question: "Overview",
  answer:
    "Here's an overview of your key metrics. Revenue is trending upward at ₹45.2L with strong order volume. The dip in average order value warrants attention.",
  chart_type: "line",
  data: [
    { month: "Oct", revenue: 28.4 },
    { month: "Nov", revenue: 32.1 },
    { month: "Dec", revenue: 38.7 },
    { month: "Jan", revenue: 35.2 },
    { month: "Feb", revenue: 41.8 },
    { month: "Mar", revenue: 45.2 },
  ],
  x_key: "month",
  y_key: "revenue",
  table_name: "orders",
  follow_ups: [
    "Revenue by region",
    "Top 5 customers by spending",
    "Category breakdown",
  ],
};

export function getMockResult(question: string): QueryResult {
  const q = question.toLowerCase();

  if (q.includes("total revenue") || q.match(/^what.*(revenue|sales)/))
    return totalRevenue;
  if (q.includes("revenue") && q.match(/month|trend|time|growth/))
    return revenueByMonth;
  if (q.match(/region|north|south|east|west/))
    return regionBreakdown;
  if (q.match(/cit|top 3|top 5|top cities/))
    return topCities;
  if (q.match(/categor|breakdown|distribution|pie/))
    return categoryBreakdown;

  return { ...defaultResult, question };
}
