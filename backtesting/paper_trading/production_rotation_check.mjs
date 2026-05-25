/**
 * Pre-task script for production_rotation.py
 * Wakes the agent if today is the first 3 trading days of the month
 * AND we haven't already rebalanced this month.
 */
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATE_FILE = join(__dirname, "production_rotation_state.json");

function isWeekday(d) {
  const day = d.getDay();
  return day !== 0 && day !== 6;
}

function alreadyRanThisMonth() {
  try {
    const state = JSON.parse(readFileSync(STATE_FILE, "utf8"));
    const last = state.last_rebalance;
    if (!last) return false;
    const lastDt = new Date(last);
    const today = new Date();
    return (
      lastDt.getFullYear() === today.getFullYear() &&
      lastDt.getMonth() === today.getMonth()
    );
  } catch {
    return false; // file doesn't exist → never ran
  }
}

function isFirstThreeTradingDaysOfMonth() {
  const today = new Date();
  // Count trading days since start of month
  let tradingDays = 0;
  for (let d = 1; d <= today.getDate(); d++) {
    const dt = new Date(today.getFullYear(), today.getMonth(), d);
    if (isWeekday(dt)) tradingDays++;
  }
  return tradingDays <= 3;
}

const shouldWake =
  isFirstThreeTradingDaysOfMonth() && !alreadyRanThisMonth();

console.log(
  JSON.stringify({
    wakeAgent: shouldWake,
    data: {
      today: new Date().toISOString().slice(0, 10),
      isFirstThreeTradingDays: isFirstThreeTradingDaysOfMonth(),
      alreadyRanThisMonth: alreadyRanThisMonth(),
    },
  })
);
