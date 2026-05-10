/**
 * Pre-task script for PEAD intraday scanner.
 * Polls EDGAR's latest 8-K ATOM feed, checks for new Item 2.02 filings
 * from universe tickers not yet seen today. Returns wakeAgent: true
 * with ticker list if new filings found.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';

const CURSOR_PATH = '/workspace/agent/backtesting/paper_trading/pead_intraday_cursor.json';
const EDGAR_URL =
  'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K' +
  '&dateb=&owner=include&count=40&search_text=&output=atom';

// Universe ticker → company name substrings (lowercase)
const UNIVERSE_MAP = {
  AAPL:  ['apple inc', 'apple computer'],
  MSFT:  ['microsoft'],
  GOOGL: ['alphabet', 'google'],
  META:  ['meta platforms', 'facebook inc'],
  AMZN:  ['amazon.com', 'amazon com'],
  NVDA:  ['nvidia'],
  TSLA:  ['tesla'],
  JPM:   ['jpmorgan chase', 'jp morgan', 'j.p. morgan'],
  BAC:   ['bank of america'],
  WFC:   ['wells fargo'],
  JNJ:   ['johnson & johnson', 'johnson and johnson'],
  PFE:   ['pfizer'],
  MRK:   ['merck & co', 'merck and co'],
  XOM:   ['exxon mobil', 'exxonmobil'],
  CVX:   ['chevron'],
  WMT:   ['walmart', 'wal-mart'],
  COST:  ['costco wholesale'],
  HD:    ['home depot'],
  LOW:   ["lowe's companies", 'lowes companies'],
  SBUX:  ['starbucks'],
  V:     ['visa inc'],
  MA:    ['mastercard'],
  UNH:   ['unitedhealth group'],
  ABBV:  ['abbvie'],
  LLY:   ['eli lilly', 'lilly and co'],
  AVGO:  ['broadcom'],
  AMD:   ['advanced micro devices'],
  QCOM:  ['qualcomm'],
  INTC:  ['intel corporation', 'intel corp'],
  IBM:   ['international business machines'],
};

function matchTicker(companyName) {
  const name = companyName.toLowerCase();
  for (const [ticker, patterns] of Object.entries(UNIVERSE_MAP)) {
    if (patterns.some(p => name.includes(p))) return ticker;
  }
  return null;
}

// Load or reset cursor
const today = new Date().toISOString().slice(0, 10);
let cursor = { seen: [], last_date: today, last_check: null };
if (existsSync(CURSOR_PATH)) {
  try {
    const raw = JSON.parse(readFileSync(CURSOR_PATH, 'utf8'));
    // Reset daily
    cursor = raw.last_date === today ? raw : { seen: [], last_date: today, last_check: null };
  } catch (_) {}
}

// Fetch EDGAR ATOM feed
let xml;
try {
  const res = await fetch(EDGAR_URL, {
    headers: { 'User-Agent': 'george-nanoclaw george@nanoclaw.com' },
  });
  xml = await res.text();
} catch (err) {
  // Network failure — don't wake agent, retry next interval
  console.log(JSON.stringify({ wakeAgent: false, error: String(err) }));
  process.exit(0);
}

// Parse <entry> blocks
const entryBlocks = xml.match(/<entry>[\s\S]*?<\/entry>/g) ?? [];
const newFilings = [];

for (const block of entryBlocks) {
  const dateFiled = (block.match(/<date-filed>([\d-]+)<\/date-filed>/) ?? [])[1];
  if (dateFiled !== today) continue;

  const companyName = (block.match(/<company-name>([^<]+)<\/company-name>/) ?? [])[1] ?? '';
  // Accession numbers look like 0000320193-26-000123 in the id field
  const idField = (block.match(/<accession-number>([^<]+)<\/accession-number>/) ?? [])[1]
    ?? (block.match(/<id>[^<]*accession-number=([^&<"]+)/) ?? [])[1]
    ?? '';
  const accession = idField.replace(/-/g, '');

  if (!accession || cursor.seen.includes(accession)) continue;

  const ticker = matchTicker(companyName);
  if (!ticker) continue;

  newFilings.push({ ticker, accession, companyName });
  cursor.seen.push(accession);
}

// Update cursor
cursor.last_check = new Date().toISOString();
writeFileSync(CURSOR_PATH, JSON.stringify(cursor, null, 2));

if (newFilings.length > 0) {
  const tickers = [...new Set(newFilings.map(f => f.ticker))];
  console.log(JSON.stringify({
    wakeAgent: true,
    data: { tickers, filings: newFilings, date: today },
  }));
} else {
  console.log(JSON.stringify({ wakeAgent: false }));
}
